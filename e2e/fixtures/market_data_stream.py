"""
Mock market data stream fixture for real execution mode tests.

Allows tests to inject price updates that trigger execution via PriceExecutionEngine.
Simulates realistic market scenarios: gradual price movement, limit order trigger, etc.
"""

import asyncio
import logging
from decimal import Decimal
from typing import Optional, List
from dataclasses import dataclass

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
    Injects price updates into Mock service to drive execution.

    Usage:
        # Gradually move price from 550 to 560
        await market_stream.update_price("INSTR_NSE_SBIN_EQ", Decimal("550.00"))
        await market_stream.update_price("INSTR_NSE_SBIN_EQ", Decimal("555.00"))
        await market_stream.update_price("INSTR_NSE_SBIN_EQ", Decimal("560.00"))

        # Trigger fills by crossing limit price
        await market_stream.update_price(
            "INSTR_NSE_TCS_EQ",
            Decimal("3799.50")  # Crosses limit BUY @ 3800
        )
    """

    def __init__(self, mock_client, broker_id: str = "mock"):
        """
        Initialize market data stream.

        Args:
            mock_client: MockClient for price update injection
            broker_id: Broker ID for price updates (default: "mock")
        """
        self.mock_client = mock_client
        self.broker_id = broker_id
        self._price_cache = {}  # instrument_id -> last_price
        self._update_history = []  # For debugging

    async def update_price(
        self,
        instrument_id: str,
        ltp: Decimal,
        bid: Optional[Decimal] = None,
        ask: Optional[Decimal] = None,
        volume: Optional[int] = None,
    ) -> None:
        """
        Inject price update to trigger execution.

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

        # Send to mock service to trigger price-driven execution
        result = await self.mock_client.inject_price_update(
            broker_id=self.broker_id,
            instrument_id=instrument_id,
            ltp=ltp,
            bid=bid,
            ask=ask,
        )

        if result.get("status") == "not_implemented":
            log.warning(
                f"Price injection not available. Consider using inject_fill() "
                f"for deterministic Phase 5 tests instead of Phase 6 real execution."
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
        return self._update_history.copy()

    def reset(self) -> None:
        """Reset cache and history."""
        self._price_cache.clear()
        self._update_history.clear()
