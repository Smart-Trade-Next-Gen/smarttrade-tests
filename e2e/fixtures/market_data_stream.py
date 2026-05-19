"""
Mock market data stream fixture for real execution mode tests.

Publishes price updates on the production Redis stream `market.quote` so
both BAS QuoteStore and PBS PriceExecutionEngine see them through their
real consumer paths. Also calls the PBS `/price/{broker_id}` HTTP endpoint
to synchronously trigger order evaluation — this avoids consumer-group lag
flakiness in price-driven LIMIT/STOP tests.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List
from dataclasses import dataclass
from collections import deque

import redis.asyncio as redis

log = logging.getLogger(__name__)


@dataclass
class PriceUpdate:
    """Market price update for a single instrument."""
    instrument_id: str
    ltp: Decimal  # Last traded price
    bid: Optional[Decimal] = None
    ask: Optional[Decimal] = None
    volume: Optional[int] = None
    timestamp: Optional[float] = None


class MockMarketDataStream:
    """
    Injects price updates that drive both BAS QuoteStore and PBS execution.

    Two-level injection:
      1. XADD to Redis stream `market.quote` — the production path that
         BAS' MarketDataConsumer and PBS' PBSMarketDataConsumer both read.
      2. POST to PBS `/api/v1/price/{broker_id}` — a deterministic test
         shortcut that synchronously triggers PriceExecutionEngine, used to
         keep LIMIT/STOP tests stable when consumer-group lag is non-zero.

    Usage:
        await market_stream.update_price("INSTR_NSE_SBIN_EQ", Decimal("550.00"))
        await market_stream.update_price("INSTR_NSE_TCS_EQ", Decimal("3799.50"))
    """

    QUOTE_STREAM = "market.quote"

    def __init__(
        self,
        mock_client,
        broker_id: str = "mock",
        redis_url: str = "redis://localhost:6379/0",
    ):
        """
        Initialize market data stream.

        Args:
            mock_client: MockClient for HTTP price injection (deterministic trigger)
            broker_id: Broker ID for price updates (default: "mock")
            redis_url: Redis connection URL for stream publishing
        """
        self.mock_client = mock_client
        self.broker_id = broker_id
        self.redis_url = redis_url
        self._redis: Optional[redis.Redis] = None
        self._sequence_counters: dict[str, int] = {}
        self._price_cache = {}  # instrument_id -> last_price
        self._update_history = deque(maxlen=500)  # Bounded debug history

    async def _connect_redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = await redis.from_url(self.redis_url, decode_responses=True)
        return self._redis

    async def update_price(
        self,
        instrument_id: str,
        ltp: Decimal,
        bid: Optional[Decimal] = None,
        ask: Optional[Decimal] = None,
        volume: Optional[int] = None,
    ) -> None:
        """
        Inject price update on the production Redis stream and via the PBS
        HTTP shortcut (for deterministic execution).

        Args:
            instrument_id: Instrument ID (e.g., "INSTR_NSE_SBIN_EQ")
            ltp: Last traded price
            bid: Bid price (optional)
            ask: Ask price (optional)
            volume: Trading volume (optional)
        """
        update = PriceUpdate(
            instrument_id=instrument_id,
            ltp=ltp,
            bid=bid,
            ask=ask,
            volume=volume,
        )

        # Cache for reference
        self._price_cache[instrument_id] = ltp
        self._update_history.append(update)

        log.info(
            f"Market update | Instrument: {instrument_id} | LTP: {ltp} | "
            f"Bid: {bid} | Ask: {ask}"
        )

        # Level 1 (production path): publish to Redis stream so BAS QuoteStore
        # and PBS PriceExecutionEngine both pick it up via their consumers.
        # Use a ms-since-epoch sequence so PBS' per-instrument idempotency
        # check (which survives across pytest invocations because PBS is
        # long-lived) doesn't drop our quote as a duplicate.
        try:
            r = await self._connect_redis()
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            self._sequence_counters[instrument_id] = now_ms
            quote_data = {
                "instrument_id": instrument_id,
                "ltp": str(ltp),
                "sequence_number": str(now_ms),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if bid is not None:
                quote_data["bid"] = str(bid)
            if ask is not None:
                quote_data["ask"] = str(ask)
            await r.xadd(self.QUOTE_STREAM, quote_data)
        except Exception as e:
            log.error(f"Failed to publish quote to Redis stream: {e}")

        # Level 2 (test shortcut): synchronously trigger PBS execution to
        # avoid consumer-group lag flakiness in LIMIT/STOP tests.
        result = await self.mock_client.inject_price_update(
            broker_id=self.broker_id,
            instrument_id=instrument_id,
            ltp=ltp,
            bid=bid,
            ask=ask,
        )

        if result.get("status") == "not_implemented":
            log.warning(
                "PBS /price endpoint not available; relying on Redis-stream "
                "consumer path. Tests asserting tight LIMIT/STOP triggers may "
                "see consumer-group lag."
            )

    async def update_prices_gradual(
        self,
        instrument_id: str,
        prices: List[Decimal],
        interval_ms: int = 100,
    ) -> None:
        """
        Inject prices gradually to simulate market movement.

        Useful for testing partial fills and streaming execution.

        Args:
            instrument_id: Instrument ID
            prices: List of prices to inject in order
            interval_ms: Delay between price updates (milliseconds)
        """
        log.info(
            f"Gradual price update started | Instrument: {instrument_id} | "
            f"Prices: {prices} | Interval: {interval_ms}ms"
        )

        for price in prices:
            await self.update_price(instrument_id, price)
            if len(prices) > 1:
                # Don't wait after last price
                await asyncio.sleep(interval_ms / 1000.0)

        log.info(f"Gradual price update completed | Instrument: {instrument_id}")

    async def trigger_limit_buy(
        self,
        instrument_id: str,
        limit_price: Decimal,
        current_price: Optional[Decimal] = None,
    ) -> None:
        """
        Trigger a LIMIT BUY order by moving price below limit.

        Args:
            instrument_id: Instrument ID
            limit_price: Order's limit price
            current_price: Current market price (if known)
        """
        # Move price from above limit to below limit
        if current_price is None:
            current_price = limit_price + Decimal("10.00")

        log.info(
            f"Triggering LIMIT BUY | Instrument: {instrument_id} | "
            f"Limit: {limit_price} | Current: {current_price}"
        )

        # Price above limit (no fill)
        await self.update_price(instrument_id, current_price)
        await asyncio.sleep(0.1)

        # Price crosses down (triggers fill)
        await self.update_price(instrument_id, limit_price - Decimal("0.50"))

    async def trigger_limit_sell(
        self,
        instrument_id: str,
        limit_price: Decimal,
        current_price: Optional[Decimal] = None,
    ) -> None:
        """
        Trigger a LIMIT SELL order by moving price above limit.

        Args:
            instrument_id: Instrument ID
            limit_price: Order's limit price
            current_price: Current market price (if known)
        """
        # Move price from below limit to above limit
        if current_price is None:
            current_price = limit_price - Decimal("10.00")

        log.info(
            f"Triggering LIMIT SELL | Instrument: {instrument_id} | "
            f"Limit: {limit_price} | Current: {current_price}"
        )

        # Price below limit (no fill)
        await self.update_price(instrument_id, current_price)
        await asyncio.sleep(0.1)

        # Price crosses up (triggers fill)
        await self.update_price(instrument_id, limit_price + Decimal("0.50"))

    async def trigger_stop_buy(
        self,
        instrument_id: str,
        stop_price: Decimal,
        current_price: Optional[Decimal] = None,
    ) -> None:
        """
        Trigger a STOP BUY order by moving price above stop level.

        Args:
            instrument_id: Instrument ID
            stop_price: Order's stop price
            current_price: Current market price (if known)
        """
        if current_price is None:
            current_price = stop_price - Decimal("10.00")

        log.info(
            f"Triggering STOP BUY | Instrument: {instrument_id} | "
            f"Stop: {stop_price} | Current: {current_price}"
        )

        await self.update_price(instrument_id, current_price)
        await asyncio.sleep(0.1)
        await self.update_price(instrument_id, stop_price + Decimal("0.50"))

    async def trigger_stop_sell(
        self,
        instrument_id: str,
        stop_price: Decimal,
        current_price: Optional[Decimal] = None,
    ) -> None:
        """
        Trigger a STOP SELL order by moving price below stop level.

        Args:
            instrument_id: Instrument ID
            stop_price: Order's stop price
            current_price: Current market price (if known)
        """
        if current_price is None:
            current_price = stop_price + Decimal("10.00")

        log.info(
            f"Triggering STOP SELL | Instrument: {instrument_id} | "
            f"Stop: {stop_price} | Current: {current_price}"
        )

        await self.update_price(instrument_id, current_price)
        await asyncio.sleep(0.1)
        await self.update_price(instrument_id, stop_price - Decimal("0.50"))

    def get_price(self, instrument_id: str) -> Optional[Decimal]:
        """Get last known price for instrument."""
        return self._price_cache.get(instrument_id)

    def get_history(self) -> List[PriceUpdate]:
        """Get all price updates injected during test."""
        return list(self._update_history)

    def reset(self) -> None:
        """Reset cache and history."""
        self._price_cache.clear()
        self._update_history.clear()
        self._sequence_counters.clear()

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis is not None:
            try:
                await self._redis.close()
            except Exception as e:
                log.warning(f"Error closing Redis connection: {e}")
            self._redis = None
