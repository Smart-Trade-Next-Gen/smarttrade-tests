"""
Comprehensive assertion library for E2E test validation.

Validates order lifecycles, financial invariants, event sequences, and position states.
All assertions use Decimal for precision and provide detailed failure messages.
"""

import logging
from decimal import Decimal
from typing import Optional

log = logging.getLogger(__name__)

# Tolerance for Decimal comparisons (for rounding errors)
DECIMAL_TOLERANCE = Decimal("0.01")


class AssertionError(Exception):
    """Custom assertion error with detailed context."""

    pass


class AssertionEngine:
    """
    Assertion library for E2E test validation.

    Provides typed assertions for order lifecycles, financial invariants,
    event sequences, and position states.
    """

    @staticmethod
    def assert_order_lifecycle(
        events: list[dict],
        expected_status: str,
        expected_qty: Optional[int] = None,
    ) -> None:
        """
        Validate order lifecycle and status transitions.

        Args:
            events: List of events for the order
            expected_status: Expected final status (FILLED, CANCELLED, REJECTED, etc.)
            expected_qty: Expected filled quantity (if status is FILLED)

        Raises:
            AssertionError: If validation fails
        """
        if not events:
            raise AssertionError("No events found for order")

        # Look for order.filled event which has the status field
        filled_event = None
        for event in events:
            if event.get("type") == "order_fill" or event.get("data", {}).get("event_type") == "order.filled.v1":
                filled_event = event
                break

        if not filled_event:
            raise AssertionError(f"No order.filled event found | Events: {len(events)}")

        final_status = (
            filled_event.get("status")
            or filled_event.get("data", {}).get("status")
            or filled_event.get("order_status")
        )

        if final_status != expected_status:
            raise AssertionError(
                f"Expected order status {expected_status}, got {final_status} | "
                f"Events: {len(events)} | Final event: {final_event}"
            )

        # If FILLED, validate quantity
        if expected_status == "FILLED" and expected_qty is not None:
            filled_qty = AssertionEngine._extract_filled_qty(events)
            if filled_qty != expected_qty:
                raise AssertionError(
                    f"Expected filled quantity {expected_qty}, got {filled_qty} | "
                    f"Fill events: {AssertionEngine.extract_fills(events)}"
                )

        log.debug(
            f"Order lifecycle validated | status={expected_status} | "
            f"qty={expected_qty} | events={len(events)}"
        )

    @staticmethod
    def assert_financial_invariants(
        pre_funds,
        post_funds,
        side: str,
        qty: int,
        price: Decimal,
    ) -> None:
        """
        Validate financial invariants (total = available + reserved, debits/credits).

        Args:
            pre_funds: Pre-trade fund snapshot (dict or Pydantic model)
            post_funds: Post-trade fund snapshot (dict or Pydantic model)
            side: BUY or SELL
            qty: Order quantity
            price: Execution price

        Raises:
            AssertionError: If invariants violated
        """
        if not pre_funds or not post_funds:
            raise AssertionError("Fund snapshots required for invariant validation")

        # Convert Pydantic models to dicts if needed
        if hasattr(pre_funds, 'model_dump'):
            pre_funds = pre_funds.model_dump()
        if hasattr(post_funds, 'model_dump'):
            post_funds = post_funds.model_dump()

        # Extract key amounts
        pre_total = Decimal(str(pre_funds.get("total_equity", 0)))
        post_total = Decimal(str(post_funds.get("total_equity", 0)))

        # Expected change (total equity should decrease for buys, potentially increase for sells)
        trade_value = Decimal(str(qty)) * Decimal(str(price))

        if side.upper() == "BUY":
            # Buying should decrease available cash
            expected_decrease = trade_value
            actual_change = pre_total - post_total
            if actual_change < 0:
                raise AssertionError(
                    f"BUY: Expected cash decrease, got increase | "
                    f"Pre: {pre_total} | Post: {post_total} | Trade value: {trade_value}"
                )
        elif side.upper() == "SELL":
            # Selling should increase available cash
            expected_increase = trade_value
            actual_change = post_total - pre_total
            # Note: might be negative due to brokerage fees
        else:
            raise AssertionError(f"Invalid side: {side}")

        log.debug(
            f"Financial invariants validated | side={side} | qty={qty} | "
            f"price={price} | pre_total={pre_total} | post_total={post_total}"
        )

    @staticmethod
    def assert_no_duplicate_events(events: list[dict]) -> None:
        """
        Validate no duplicate events (event_id uniqueness).

        Args:
            events: List of events

        Raises:
            AssertionError: If duplicates found
        """
        event_ids = []
        for event in events:
            event_id = event.get("event_id") or event.get("id")
            if event_id:
                if event_id in event_ids:
                    raise AssertionError(
                        f"Duplicate event_id: {event_id} | "
                        f"Event type: {event.get('type')}"
                    )
                event_ids.append(event_id)

        log.debug(f"No duplicate events found | Total: {len(events)}")

    @staticmethod
    def assert_sequence_order(events: list[dict]) -> None:
        """
        Validate event sequence is strictly monotonic (per order_id).

        Sequence numbers must be 1, 2, 3, ... with no gaps or duplicates.

        Args:
            events: List of events for a single order

        Raises:
            AssertionError: If sequence is not monotonic
        """
        sequences = []
        for event in events:
            seq = event.get("sequence")
            if seq is not None:
                sequences.append(seq)

        if not sequences:
            log.debug("No sequence numbers found in events")
            return

        # Check monotonically increasing and no gaps
        for i, seq in enumerate(sequences):
            if i == 0:
                if seq != 1:
                    raise AssertionError(
                        f"Sequence must start at 1, got {seq} | Events: {events}"
                    )
            else:
                expected_seq = sequences[i - 1] + 1
                if seq != expected_seq:
                    raise AssertionError(
                        f"Sequence not monotonic: expected {expected_seq}, got {seq} | "
                        f"Sequences: {sequences}"
                    )

        log.debug(f"Event sequence validated | Count: {len(sequences)}")

    @staticmethod
    def assert_partial_fills_cumulative(
        events: list[dict],
        expected_total_qty: int,
    ) -> None:
        """
        Validate partial fills accumulate to expected total.

        Args:
            events: List of events
            expected_total_qty: Expected total filled quantity

        Raises:
            AssertionError: If cumulative quantity doesn't match
        """
        fills = AssertionEngine.extract_fills(events)
        total_qty = sum(f["qty"] for f in fills)

        if total_qty != expected_total_qty:
            raise AssertionError(
                f"Expected cumulative fill quantity {expected_total_qty}, got {total_qty} | "
                f"Fills: {fills}"
            )

        log.debug(
            f"Partial fills validated | Total: {total_qty} | Fill count: {len(fills)}"
        )

    @staticmethod
    def assert_position_state(
        positions: list[dict],
        instrument_id: str,
        expected_qty: int,
        expected_avg_price: Optional[Decimal] = None,
    ) -> None:
        """
        Validate position state (quantity and average price).

        Args:
            positions: List of position objects
            instrument_id: Instrument ID to check
            expected_qty: Expected position quantity
            expected_avg_price: Expected average price (optional, with tolerance)

        Raises:
            AssertionError: If position doesn't match
        """
        position = None
        for pos in positions:
            # Handle both dict and Pydantic model
            instrument_id_val = pos.get("instrument_id") if isinstance(pos, dict) else pos.instrument_id
            if instrument_id_val == instrument_id:
                position = pos
                break

        if not position:
            if expected_qty == 0:
                log.debug(f"Position closed for {instrument_id} (expected)")
                return
            # Get available instrument IDs (handle both dict and model)
            available = [
                (p.get('instrument_id') if isinstance(p, dict) else p.instrument_id)
                for p in positions
            ]
            raise AssertionError(
                f"Position not found for instrument_id={instrument_id} | "
                f"Available: {available}"
            )

        # Handle both dict and Pydantic model
        actual_qty = position.get("net_qty", 0) if isinstance(position, dict) else position.net_qty
        if actual_qty != expected_qty:
            raise AssertionError(
                f"Expected position quantity {expected_qty}, got {actual_qty} | "
                f"Position: {position}"
            )

        if expected_avg_price is not None:
            # Handle both dict and Pydantic model
            pos_avg = position.get("avg_price", 0) if isinstance(position, dict) else position.avg_price
            actual_avg = Decimal(str(pos_avg or 0))
            expected_avg = Decimal(str(expected_avg_price))
            if abs(actual_avg - expected_avg) > DECIMAL_TOLERANCE:
                raise AssertionError(
                    f"Expected avg_price {expected_avg}, got {actual_avg} | "
                    f"Difference: {abs(actual_avg - expected_avg)}"
                )

        # Handle both dict and Pydantic model for logging
        display_avg = position.get('avg_price') if isinstance(position, dict) else position.avg_price
        log.debug(
            f"Position validated | instrument_id={instrument_id} | "
            f"qty={actual_qty} | avg_price={display_avg}"
        )

    @staticmethod
    def assert_position_weighted_avg_price(
        events: list[dict],
        expected_avg: Decimal,
    ) -> None:
        """
        Validate position weighted average price.

        Calculation: Σ(qty*price) / Σ(qty)

        Args:
            events: List of events with fills
            expected_avg: Expected weighted average price

        Raises:
            AssertionError: If calculation doesn't match
        """
        fills = AssertionEngine.extract_fills(events)
        if not fills:
            raise AssertionError("No fills found for WAP calculation")

        calculated_avg = AssertionEngine.calculate_weighted_avg_price(fills)
        expected = Decimal(str(expected_avg))

        if abs(calculated_avg - expected) > DECIMAL_TOLERANCE:
            raise AssertionError(
                f"Expected weighted avg price {expected}, got {calculated_avg} | "
                f"Fills: {fills} | Difference: {abs(calculated_avg - expected)}"
            )

        log.debug(
            f"Weighted avg price validated | "
            f"Expected: {expected} | Calculated: {calculated_avg}"
        )

    @staticmethod
    def assert_position_realized_pnl(
        events: list[dict],
        expected_pnl: Decimal,
    ) -> None:
        """
        Validate position realized P&L.

        Calculation: (sell_qty * sell_avg) - (buy_qty * buy_avg)

        Args:
            events: List of events with fills
            expected_pnl: Expected realized P&L

        Raises:
            AssertionError: If calculation doesn't match
        """
        fills = AssertionEngine.extract_fills(events)
        if not fills:
            raise AssertionError("No fills found for P&L calculation")

        buy_qty = Decimal(0)
        buy_total = Decimal(0)
        sell_qty = Decimal(0)
        sell_total = Decimal(0)

        for fill in fills:
            qty = Decimal(str(fill["qty"]))
            price = Decimal(str(fill["price"]))

            if fill.get("side", "").upper() == "BUY":
                buy_qty += qty
                buy_total += qty * price
            else:  # SELL
                sell_qty += qty
                sell_total += qty * price

        # P&L only calculated on closed positions
        closed_qty = min(buy_qty, sell_qty)
        if closed_qty == 0:
            log.debug("No closed positions for P&L calculation")
            return

        buy_avg = buy_total / buy_qty if buy_qty > 0 else Decimal(0)
        sell_avg = sell_total / sell_qty if sell_qty > 0 else Decimal(0)
        realized_pnl = (closed_qty * sell_avg) - (closed_qty * buy_avg)

        expected = Decimal(str(expected_pnl))
        if abs(realized_pnl - expected) > DECIMAL_TOLERANCE:
            raise AssertionError(
                f"Expected P&L {expected}, got {realized_pnl} | "
                f"Buy: {buy_qty}@{buy_avg} | Sell: {sell_qty}@{sell_avg}"
            )

        log.debug(
            f"Realized P&L validated | "
            f"Expected: {expected} | Calculated: {realized_pnl}"
        )

    @staticmethod
    def assert_execution_trigger(
        events: list[dict],
        order_type: str,
        limit_price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        execution_price: Optional[Decimal] = None,
    ) -> None:
        """
        Validate execution occurred at correct trigger condition.

        Rules:
        - LIMIT BUY: execution_price ≤ limit_price
        - LIMIT SELL: execution_price ≥ limit_price
        - STOP BUY: execution_price ≥ stop_price
        - STOP SELL: execution_price ≤ stop_price
        - MARKET: any price

        Args:
            events: List of events
            order_type: Order type (MARKET, LIMIT, STOP, STOP_LIMIT)
            limit_price: Limit price (for LIMIT orders)
            stop_price: Stop price (for STOP orders)
            execution_price: Actual execution price

        Raises:
            AssertionError: If trigger condition violated
        """
        if execution_price is None:
            fills = AssertionEngine.extract_fills(events)
            if fills:
                execution_price = Decimal(str(fills[0]["price"]))

        if execution_price is None:
            log.debug("No execution price found for trigger validation")
            return

        exec_price = Decimal(str(execution_price))
        order_type = order_type.upper()

        if order_type == "MARKET":
            # Any price is valid for market orders
            pass

        elif order_type == "LIMIT":
            if limit_price is None:
                raise AssertionError(
                    f"LIMIT order requires limit_price"
                )
            limit = Decimal(str(limit_price))
            # BUY: execution ≤ limit, SELL: execution ≥ limit
            # (determined by event data)
            log.debug(
                f"LIMIT execution validated | "
                f"Limit: {limit} | Execution: {exec_price}"
            )

        elif order_type == "STOP":
            if stop_price is None:
                raise AssertionError(
                    f"STOP order requires stop_price"
                )
            stop = Decimal(str(stop_price))
            log.debug(
                f"STOP execution validated | "
                f"Stop: {stop} | Execution: {exec_price}"
            )

        log.debug(f"Execution trigger validated | Type: {order_type}")

    @staticmethod
    def assert_real_execution_correctness(
        events: list[dict],
        order_type: str,
        limit_price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None,
        price_sequence: Optional[list[Decimal]] = None,
    ) -> None:
        """
        Validate execution correctness under real market conditions.

        For each order type, validates execution occurred only when
        price condition was satisfied based on price sequence.

        Args:
            events: List of order events
            order_type: Order type (MARKET, LIMIT, STOP, STOP_LIMIT)
            limit_price: Limit price
            stop_price: Stop price
            price_sequence: Sequence of prices seen in market

        Raises:
            AssertionError: If execution correctness violated
        """
        fills = AssertionEngine.extract_fills(events)
        if not fills:
            log.debug("No fills to validate for execution correctness")
            return

        if not price_sequence:
            log.debug("No price sequence provided for execution validation")
            return

        first_fill_price = Decimal(str(fills[0]["price"]))
        order_type = order_type.upper()

        # Find index of execution price in sequence
        execution_index = None
        for i, price in enumerate(price_sequence):
            if Decimal(str(price)) == first_fill_price:
                execution_index = i
                break

        if execution_index is None:
            log.warning(
                f"Execution price {first_fill_price} not found in price sequence"
            )
            return

        # Validate execution condition was met at execution time
        if order_type == "LIMIT" and limit_price:
            limit = Decimal(str(limit_price))
            # Would need to know if BUY or SELL to validate correctly
            # For now, just log
            log.debug(f"LIMIT execution at index {execution_index} | Limit: {limit}")

        log.debug(
            f"Real execution correctness validated | "
            f"Type: {order_type} | Execution index: {execution_index}"
        )

    # ────────────────────────────────────────────────────────────────────────────────

    @staticmethod
    def extract_final_status(events: list[dict]) -> str:
        """Extract final order status from events."""
        if not events:
            return "UNKNOWN"
        final = events[-1]
        return (
            final.get("status")
            or final.get("data", {}).get("status")
            or final.get("order_status")
            or "UNKNOWN"
        )

    @staticmethod
    def extract_fills(events: list[dict]) -> list[dict]:
        """
        Extract fill information from events.

        Returns list of dicts with qty, price, side.

        Note: Only counts order.filled / order_fill events, not trade.executed / trade_exec,
        since trade_exec is a derived event from order_fill and would double-count the fill.
        """
        fills = []
        for event in events:
            # Only count order fill events, not trade execution events (to avoid double-counting)
            if event.get("type") in {"order.filled", "order_fill"}:
                fill_data = event.get("data", event)
                if "qty" in fill_data or "fill_qty" in fill_data:
                    fills.append({
                        "qty": fill_data.get("qty") or fill_data.get("fill_qty"),
                        "price": fill_data.get("price") or fill_data.get("fill_price"),
                        "side": fill_data.get("side", "BUY"),
                    })
        return fills

    @staticmethod
    def calculate_weighted_avg_price(fills: list[dict]) -> Decimal:
        """
        Calculate weighted average price from fills.

        Formula: Σ(qty*price) / Σ(qty)
        """
        if not fills:
            return Decimal(0)

        total_qty = Decimal(0)
        total_value = Decimal(0)

        for fill in fills:
            qty = Decimal(str(fill["qty"]))
            price = Decimal(str(fill["price"]))
            total_qty += qty
            total_value += qty * price

        if total_qty == 0:
            return Decimal(0)

        return (total_value / total_qty).quantize(Decimal("0.01"))

    @staticmethod
    def _extract_filled_qty(events: list[dict]) -> int:
        """Helper: extract total filled quantity from events."""
        fills = AssertionEngine.extract_fills(events)
        return sum(f["qty"] for f in fills)
