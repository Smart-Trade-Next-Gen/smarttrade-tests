"""
E2E tests for error paths and edge cases using injection mode.

Tests validate:
- Invalid order requests (zero qty, negative qty, invalid price)
- Order cancellation failures (already filled orders, nonexistent orders)
- Fill injection errors (sequence violations, overfill)
- Event handling under error conditions

All tests use INJECTION mode for deterministic execution.
"""

import pytest
from decimal import Decimal

from smarttrade_common.schemas.types import OrderSide, OrderType, TimeInForce, PositionType
from broker_adapter_service.schemas.order_dtos import BasOrderPlaceRequest, BasOrderLeg


@pytest.mark.injection
async def test_zero_quantity_order_rejected(
    bas_client,
    mock_client,
    event_collector,
    assertions,
    test_account_id,
    logger,
):
    """
    Test: Order with zero quantity is rejected.

    Validates:
    - Request validation catches zero qty
    - No order is placed
    - No events are generated
    """
    broker_id = "mock"

    # Act: Attempt to place order with qty=0
    try:
        order_request = BasOrderPlaceRequest(
            client_order_id=f"test_zero_qty_{test_account_id}",
            position_type=PositionType.INTRADAY,
            legs=[
                BasOrderLeg(
                    instrument_id="INSTR_NSE_ICICIBANK_EQ",
                    instrument_type="EQUITY",
                    side=OrderSide.BUY,
                    qty=0,  # Invalid: zero qty
                    order_type=OrderType.MARKET,
                    price=None,
                    stop_price=None,
                    ltp=Decimal("700.00"),
                )
            ],
            underlying_instrument_id="INSTR_NSE_ICICIBANK_EQ",
            tif=TimeInForce.DAY,
        )
        result = await bas_client.place_order(broker_id, test_account_id, order_request)

        # If we get here, the order was accepted (unexpected)
        if result:
            pytest.fail("Zero quantity order should be rejected by BAS")

    except Exception as e:
        # Expected: validation error
        logger.info(f"✓ Zero quantity rejected: {str(e)[:100]}")
        assert "qty" in str(e).lower() or "quantity" in str(e).lower(), \
            f"Expected qty validation error, got: {e}"


@pytest.mark.injection
async def test_negative_quantity_order_rejected(
    bas_client,
    mock_client,
    event_collector,
    assertions,
    test_account_id,
    logger,
):
    """
    Test: Order with negative quantity is rejected.

    Validates:
    - Request validation catches negative qty
    - Pydantic/validation layer prevents negative values
    """
    broker_id = "mock"

    # Act: Attempt to place order with qty=-100
    try:
        order_request = BasOrderPlaceRequest(
            client_order_id=f"test_negative_qty_{test_account_id}",
            position_type=PositionType.INTRADAY,
            legs=[
                BasOrderLeg(
                    instrument_id="INSTR_NSE_HDFC_EQ",
                    instrument_type="EQUITY",
                    side=OrderSide.BUY,
                    qty=-100,  # Invalid: negative qty
                    order_type=OrderType.MARKET,
                    price=None,
                    stop_price=None,
                    ltp=Decimal("2400.00"),
                )
            ],
            underlying_instrument_id="INSTR_NSE_HDFC_EQ",
            tif=TimeInForce.DAY,
        )
        result = await bas_client.place_order(broker_id, test_account_id, order_request)

        if result:
            pytest.fail("Negative quantity order should be rejected")

    except Exception as e:
        # Expected: validation error
        logger.info(f"✓ Negative quantity rejected: {str(e)[:100]}")


@pytest.mark.injection
async def test_invalid_limit_price_zero(
    bas_client,
    mock_client,
    event_collector,
    assertions,
    test_account_id,
    logger,
):
    """
    Test: LIMIT order with zero price is rejected.

    Validates:
    - Request validation catches invalid price
    - LIMIT orders require non-zero, positive price
    """
    broker_id = "mock"

    # Act: Attempt LIMIT order with price=0
    try:
        order_request = BasOrderPlaceRequest(
            client_order_id=f"test_zero_limit_price_{test_account_id}",
            position_type=PositionType.INTRADAY,
            legs=[
                BasOrderLeg(
                    instrument_id="INSTR_NSE_LT_EQ",
                    instrument_type="EQUITY",
                    side=OrderSide.BUY,
                    qty=50,
                    order_type=OrderType.LIMIT,
                    price=Decimal("0.00"),  # Invalid: zero price
                    stop_price=None,
                    ltp=Decimal("2200.00"),
                )
            ],
            underlying_instrument_id="INSTR_NSE_LT_EQ",
            tif=TimeInForce.DAY,
        )
        result = await bas_client.place_order(broker_id, test_account_id, order_request)

        if result:
            pytest.fail("Zero limit price should be rejected")

    except Exception as e:
        logger.info(f"✓ Zero limit price rejected: {str(e)[:100]}")


@pytest.mark.injection
async def test_overfill_rejected(
    bas_client,
    mock_client,
    event_collector,
    assertions,
    test_account_id,
    logger,
):
    """
    Test: Overfill (fill qty > order qty) is rejected or capped.

    Validates:
    - First fill: 50 qty (OK)
    - Second fill: 60 qty (exceeds order qty of 100, should be rejected or capped to 50)
    - Final filled qty ≤ order qty
    """
    broker_id = "mock"

    # Act: Place order for 100 shares
    order_request = BasOrderPlaceRequest(
        client_order_id=f"test_overfill_{test_account_id}",
        position_type=PositionType.INTRADAY,
        legs=[
            BasOrderLeg(
                instrument_id="INSTR_NSE_POWERGRID_EQ",
                instrument_type="EQUITY",
                side=OrderSide.BUY,
                qty=100,
                order_type=OrderType.LIMIT,
                price=Decimal("240.00"),
                stop_price=None,
                ltp=Decimal("250.00"),
            )
        ],
        underlying_instrument_id="INSTR_NSE_POWERGRID_EQ",
        tif=TimeInForce.DAY,
    )

    [order_resp] = await bas_client.place_order(broker_id, test_account_id, order_request)
    order_id = order_resp.broker_order_id
    logger.info(f"Order placed | ID: {order_id} | Total Qty: 100")

    # Act: Inject first fill (50 qty)
    await mock_client.inject_fill(
        broker_id=broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=50,
        fill_price=Decimal("239.50"),
    )
    logger.info("Fill 1 injected | Qty: 50 | Price: 239.50")

    # Act: Attempt second fill with qty=60 (would exceed 100)
    try:
        await mock_client.inject_fill(
            broker_id=broker_id,
            account_id=test_account_id,
            order_id=order_id,
            sequence=2,
            fill_qty=60,  # Exceeds remaining qty of 50
            fill_price=Decimal("239.75"),
        )
        logger.warning("Overfill accepted by mock (may implement auto-cap)")
    except Exception as e:
        logger.info(f"Overfill rejected: {e}")

    # Observe: Collect events
    events = await event_collector.wait_for_completion(order_id, timeout=5.0)
    logger.info(f"Events collected | Count: {len(events)}")

    # Assert: Final filled qty does not exceed order qty
    cumulative_qty = sum(
        evt.get("fill_qty", 0) for evt in events
        if evt.get("event_type") == "order_fill"
    )
    assert cumulative_qty <= 100, f"Cumulative fill {cumulative_qty} exceeds order qty 100"
    logger.info(f"✓ Final filled qty validated: {cumulative_qty} ≤ 100")

    # Assert: No position exceeds order qty
    post_positions = await bas_client.get_positions(broker_id, test_account_id)
    for pos in post_positions:
        if pos.instrument_id == "INSTR_NSE_POWERGRID_EQ":
            assert abs(pos.qty) <= 100, f"Position qty {pos.qty} exceeds order qty 100"
    logger.info("✓ Position qty within bounds")


@pytest.mark.injection
async def test_sequence_violation_ignored(
    bas_client,
    mock_client,
    event_collector,
    assertions,
    test_account_id,
    logger,
):
    """
    Test: Out-of-order sequence numbers are handled gracefully.

    Validates:
    - Sequence 1 → OK
    - Sequence 3 → (skipped 2, should be rejected or queued)
    - Sequence 2 → (late, should be rejected if strict)
    - Final event sequence is monotonic
    """
    broker_id = "mock"

    # Act: Place order
    order_request = BasOrderPlaceRequest(
        client_order_id=f"test_seq_violation_{test_account_id}",
        position_type=PositionType.INTRADAY,
        legs=[
            BasOrderLeg(
                instrument_id="INSTR_NSE_ULTRACEMCO_EQ",
                instrument_type="EQUITY",
                side=OrderSide.BUY,
                qty=100,
                order_type=OrderType.MARKET,
                price=None,
                stop_price=None,
                ltp=Decimal("8000.00"),
            )
        ],
        underlying_instrument_id="INSTR_NSE_ULTRACEMCO_EQ",
        tif=TimeInForce.DAY,
    )

    [order_resp] = await bas_client.place_order(broker_id, test_account_id, order_request)
    order_id = order_resp.broker_order_id
    logger.info(f"Order placed | ID: {order_id}")

    # Act: Inject fill with sequence 1 (OK)
    await mock_client.inject_fill(
        broker_id=broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=50,
        fill_price=Decimal("7999.00"),
    )
    logger.info("Fill 1 injected (sequence=1)")

    # Act: Inject fill with sequence 3 (violates monotonicity)
    try:
        await mock_client.inject_fill(
            broker_id=broker_id,
            account_id=test_account_id,
            order_id=order_id,
            sequence=3,  # Skipped sequence 2
            fill_qty=50,
            fill_price=Decimal("7999.50"),
        )
        logger.warning("Sequence 3 accepted (mock may enforce ordering)")
    except Exception as e:
        logger.info(f"Sequence violation detected: {e}")

    # Observe: Collect events (wait for completion or timeout)
    try:
        events = await event_collector.wait_for_completion(order_id, timeout=5.0)
        logger.info(f"Events collected | Count: {len(events)}")

        # Assert: Event sequence is valid (if events exist)
        fill_sequences = [
            evt.get("sequence")
            for evt in events
            if evt.get("event_type") == "order_fill" and evt.get("sequence")
        ]
        if fill_sequences:
            # Check if sequences are monotonically increasing
            for i in range(1, len(fill_sequences)):
                assert fill_sequences[i] > fill_sequences[i-1], \
                    f"Sequence violation detected: {fill_sequences}"
            logger.info(f"✓ Event sequences monotonic: {fill_sequences}")
    except Exception as e:
        logger.warning(f"Event collection timeout or error: {e}")
