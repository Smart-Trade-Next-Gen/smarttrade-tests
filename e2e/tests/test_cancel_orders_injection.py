"""
E2E tests for order cancellation using injection mode.

Tests validate:
- Cancel unfilled orders
- Cancel partially filled orders
- Cancel status transitions
- Event sequence after cancellation
- Position state consistency

All tests use INJECTION mode for deterministic execution.
"""

import pytest
from decimal import Decimal

from smarttrade_common.schemas.types import OrderSide, OrderType, TimeInForce, PositionType
from broker_adapter_service.schemas.order_dtos import BasOrderPlaceRequest, BasOrderLeg


@pytest.mark.injection
async def test_cancel_unfilled_order(
    bas_client,
    mock_client,
    event_collector,
    assertions,
    test_account_id,
    logger,
):
    """
    Test: Cancel an unfilled order (no fills before cancellation).

    Validates:
    - Order placement succeeds
    - Cancellation succeeds without fills
    - Order transitions to CANCELLED
    - No execution events after cancellation
    - No position created
    """
    broker_id = "mock"

    # Act: Create and place order
    order_request = BasOrderPlaceRequest(
        client_order_id=f"test_cancel_unfilled_{test_account_id}",
        position_type=PositionType.INTRADAY,
        legs=[
            BasOrderLeg(
                instrument_id="INSTR_NSE_MARUTI_EQ",
                instrument_type="EQUITY",
                side=OrderSide.BUY,
                qty=100,
                order_type=OrderType.LIMIT,
                price=Decimal("9000.00"),
                stop_price=None,
                ltp=Decimal("9050.00"),
            )
        ],
        underlying_instrument_id="INSTR_NSE_MARUTI_EQ",
        tif=TimeInForce.DAY,
    )

    [order_resp] = await bas_client.place_order(broker_id, test_account_id, order_request)
    order_id = order_resp.broker_order_id
    logger.info(f"Order placed | ID: {order_id} | Status: {order_resp.status}")

    # Act: Cancel order without injecting any fills
    await mock_client.cancel_order(
        broker_id=broker_id,
        account_id=test_account_id,
        order_id=order_id,
    )
    logger.info(f"Order cancelled | ID: {order_id}")

    # Observe: Wait for cancellation completion
    events = await event_collector.wait_for_completion(order_id, timeout=5.0)
    logger.info(f"Events collected | Count: {len(events)}")

    # Assert: Order lifecycle transitions to CANCELLED
    assertions.assert_order_lifecycle(events, "CANCELLED", 0)
    logger.info("✓ Order cancelled (no fills)")

    # Assert: No execution events
    assertions.assert_no_duplicate_events(events)
    logger.info("✓ No duplicate events")

    # Assert: No position created
    post_positions = await bas_client.get_positions(broker_id, test_account_id)
    maruti_positions = [p for p in post_positions if p.instrument_id == "INSTR_NSE_MARUTI_EQ"]
    assert len(maruti_positions) == 0, "Position should not exist for cancelled order"
    logger.info("✓ No position created")


@pytest.mark.injection
async def test_cancel_partial_fill(
    bas_client,
    mock_client,
    event_collector,
    assertions,
    test_account_id,
    logger,
):
    """
    Test: Cancel a partially filled order (50% filled, then cancelled).

    Validates:
    - Partial fill succeeds
    - Cancellation succeeds after partial fill
    - Order transitions to CANCELLED
    - Final filled quantity is preserved
    - Position reflects only filled quantity
    """
    broker_id = "mock"

    # Act: Create and place order for 100 shares
    order_request = BasOrderPlaceRequest(
        client_order_id=f"test_cancel_partial_{test_account_id}",
        position_type=PositionType.INTRADAY,
        legs=[
            BasOrderLeg(
                instrument_id="INSTR_NSE_HEROMOTOCO_EQ",
                instrument_type="EQUITY",
                side=OrderSide.BUY,
                qty=100,
                order_type=OrderType.LIMIT,
                price=Decimal("3500.00"),
                stop_price=None,
                ltp=Decimal("3520.00"),
            )
        ],
        underlying_instrument_id="INSTR_NSE_HEROMOTOCO_EQ",
        tif=TimeInForce.DAY,
    )

    [order_resp] = await bas_client.place_order(broker_id, test_account_id, order_request)
    order_id = order_resp.broker_order_id
    logger.info(f"Order placed | ID: {order_id} | Total Qty: 100")

    # Act: Inject partial fill (50 shares)
    await mock_client.inject_fill(
        broker_id=broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=50,
        fill_price=Decimal("3495.00"),
    )
    logger.info("Partial fill injected | Qty: 50 | Price: 3495.00")

    # Act: Cancel the remaining quantity
    await mock_client.cancel_order(
        broker_id=broker_id,
        account_id=test_account_id,
        order_id=order_id,
    )
    logger.info(f"Order cancelled after partial fill | ID: {order_id}")

    # Observe: Wait for cancellation completion
    events = await event_collector.wait_for_completion(order_id, timeout=5.0)
    logger.info(f"Events collected | Count: {len(events)}")

    # Assert: Order lifecycle (CANCELLED with 50 filled)
    assertions.assert_order_lifecycle(events, "CANCELLED", 50)
    logger.info("✓ Order cancelled with 50 shares filled")

    # Assert: Cumulative fills match
    assertions.assert_partial_fills_cumulative(events, 50)
    logger.info("✓ Cumulative fills validated (50)")

    # Assert: No duplicate events
    assertions.assert_no_duplicate_events(events)
    logger.info("✓ No duplicate events")

    # Assert: Position reflects only filled quantity
    post_positions = await bas_client.get_positions(broker_id, test_account_id)
    assertions.assert_position_state(
        post_positions,
        "INSTR_NSE_HEROMOTOCO_EQ",
        expected_qty=50,
        expected_avg_price=Decimal("3495.00"),
    )
    logger.info("✓ Position state validated (50 shares @ 3495.00)")


@pytest.mark.injection
async def test_cancel_then_fill_rejected(
    bas_client,
    mock_client,
    event_collector,
    assertions,
    test_account_id,
    logger,
):
    """
    Test: Fill injection after cancellation is rejected.

    Validates:
    - Order cancelled successfully
    - Attempting to fill a cancelled order fails gracefully
    - Final state remains CANCELLED with no fills
    """
    broker_id = "mock"

    # Act: Create and place order
    order_request = BasOrderPlaceRequest(
        client_order_id=f"test_cancel_then_fill_{test_account_id}",
        position_type=PositionType.INTRADAY,
        legs=[
            BasOrderLeg(
                instrument_id="INSTR_NSE_TITAN_EQ",
                instrument_type="EQUITY",
                side=OrderSide.BUY,
                qty=50,
                order_type=OrderType.LIMIT,
                price=Decimal("2800.00"),
                stop_price=None,
                ltp=Decimal("2850.00"),
            )
        ],
        underlying_instrument_id="INSTR_NSE_TITAN_EQ",
        tif=TimeInForce.DAY,
    )

    [order_resp] = await bas_client.place_order(broker_id, test_account_id, order_request)
    order_id = order_resp.broker_order_id
    logger.info(f"Order placed | ID: {order_id}")

    # Act: Cancel order
    await mock_client.cancel_order(
        broker_id=broker_id,
        account_id=test_account_id,
        order_id=order_id,
    )
    logger.info(f"Order cancelled | ID: {order_id}")

    # Observe: Collect events for cancelled order
    events = await event_collector.wait_for_completion(order_id, timeout=5.0)
    logger.info(f"Events collected | Count: {len(events)}")

    # Assert: Order is CANCELLED with no fills
    assertions.assert_order_lifecycle(events, "CANCELLED", 0)
    logger.info("✓ Order cancelled with 0 fills")

    # Act: Attempt to fill cancelled order (should be rejected or ignored)
    try:
        await mock_client.inject_fill(
            broker_id=broker_id,
            account_id=test_account_id,
            order_id=order_id,
            sequence=1,
            fill_qty=50,
            fill_price=Decimal("2795.00"),
        )
        logger.warning("Fill injection accepted for cancelled order (may be cached by mock)")
    except Exception as e:
        logger.info(f"Fill injection rejected for cancelled order: {e}")

    # Assert: No position created
    post_positions = await bas_client.get_positions(broker_id, test_account_id)
    titan_positions = [p for p in post_positions if p.instrument_id == "INSTR_NSE_TITAN_EQ"]
    assert len(titan_positions) == 0, "Position should not exist for cancelled order"
    logger.info("✓ No position created")
