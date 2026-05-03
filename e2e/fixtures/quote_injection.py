"""Quote injection fixture for E2E tests - Two-level injection (Redis + PBS)."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal

import redis.asyncio as redis

log = logging.getLogger(__name__)


class QuoteInjector:
    """
    Two-level quote injection for BAS QuoteStore population and PBS price execution.

    Level 1: Publish to Redis stream `market.quote.v1` for BAS QuoteStore
    Level 2: POST to PBS /api/v1/price/{broker_id} for price-driven execution
    """

    def __init__(self, redis_url: str, mock_client):
        """
        Initialize quote injector.

        Args:
            redis_url: Redis connection URL
            mock_client: MockClient instance for PBS price injection
        """
        self.redis_url = redis_url
        self.mock_client = mock_client
        self.redis = None
        self._sequence_counters = {}

    async def _connect_redis(self) -> None:
        """Connect to Redis if not already connected."""
        if self.redis is None:
            try:
                self.redis = await redis.from_url(self.redis_url, decode_responses=True)
                await self.redis.ping()
                log.debug(f"✅ Connected to Redis for quote injection")
            except Exception as e:
                log.error(f"Failed to connect to Redis: {e}")
                raise

    async def inject(
        self,
        instrument_id: str,
        ltp: Decimal,
        broker_id: str,
        bid: Decimal = None,
        ask: Decimal = None,
        sequence_number: int = None,
    ) -> None:
        """
        Inject quote at two levels.

        Level 1: XADD to Redis stream `market.quote.v1` (BAS QuoteStore)
        Level 2: POST to PBS price endpoint (price execution)

        Args:
            instrument_id: Instrument ID
            ltp: Last traded price
            broker_id: Broker ID
            bid: Bid price (optional)
            ask: Ask price (optional)
            sequence_number: Sequence number (auto-incremented if not provided)
        """
        await self._connect_redis()

        # Auto-increment sequence number per instrument
        if sequence_number is None:
            self._sequence_counters[instrument_id] = (
                self._sequence_counters.get(instrument_id, 0) + 1
            )
            sequence_number = self._sequence_counters[instrument_id]

        timestamp = datetime.now(timezone.utc).isoformat()

        # Level 1: Inject to Redis stream (BAS QuoteStore)
        try:
            stream_key = "market.quote.v1"  # Bare key, not prefixed with events:
            quote_data = {
                "instrument_id": instrument_id,
                "ltp": str(ltp),
                "sequence_number": str(sequence_number),
                "timestamp": timestamp,
            }
            if bid is not None:
                quote_data["bid"] = str(bid)
            if ask is not None:
                quote_data["ask"] = str(ask)

            await self.redis.xadd(stream_key, quote_data)
            log.info(
                f"✅ Quote injected (Redis): {instrument_id} ltp={ltp} seq={sequence_number}"
            )
        except Exception as e:
            log.error(f"Failed to inject quote to Redis stream: {e}")
            # Don't fail, Level 2 might still work

        # Level 2: Inject to PBS price endpoint (Price Execution)
        try:
            await self.mock_client.inject_price_update(
                broker_id=broker_id,
                instrument_id=instrument_id,
                ltp=ltp,
                bid=bid,
                ask=ask,
            )
            log.info(f"✅ Quote injected (PBS): {instrument_id} ltp={ltp}")
        except Exception as e:
            log.error(f"Failed to inject price to PBS: {e}")
            # Don't fail on PBS error either

    async def inject_multiple(
        self,
        quotes: list[dict],
        broker_id: str,
    ) -> None:
        """
        Inject multiple quotes at once.

        Each quote dict should have: `instrument_id`, `ltp`, and optionally `bid`, `ask`

        Args:
            quotes: List of quote dictionaries
            broker_id: Broker ID
        """
        for quote in quotes:
            await self.inject(
                instrument_id=quote["instrument_id"],
                ltp=Decimal(str(quote["ltp"])),
                broker_id=broker_id,
                bid=Decimal(str(quote.get("bid"))) if quote.get("bid") else None,
                ask=Decimal(str(quote.get("ask"))) if quote.get("ask") else None,
            )

    async def inject_price_sequence(
        self,
        instrument_id: str,
        prices: list[Decimal],
        broker_id: str,
        interval_ms: int = 100,
    ) -> None:
        """
        Inject a sequence of prices with delays between them.

        Useful for simulating price movement or multi-fill scenarios.

        Args:
            instrument_id: Instrument ID
            prices: List of prices to inject sequentially
            broker_id: Broker ID
            interval_ms: Delay between price injections in milliseconds
        """
        for i, price in enumerate(prices):
            await self.inject(
                instrument_id=instrument_id,
                ltp=price,
                broker_id=broker_id,
                sequence_number=i + 1,
            )
            if i < len(prices) - 1:
                await asyncio.sleep(interval_ms / 1000.0)

    async def close(self) -> None:
        """Close Redis connection."""
        if self.redis:
            try:
                await self.redis.close()
                log.debug("✅ Redis connection closed")
            except Exception as e:
                log.warning(f"Error closing Redis connection: {e}")
