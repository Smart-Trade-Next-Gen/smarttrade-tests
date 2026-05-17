"""
E2E tests for order cancellation using injection mode.

Tests validate:
- Cancel unfilled orders
- Cancel status transitions
- Event sequence after cancellation (via Redis Streams)
- Broker state verification (source of truth)
- Position state consistency

All tests use INJECTION mode for deterministic execution.
Updated for v4.0 stateless architecture.
"""

import pytest
import uuid
from decimal import Decimal

from smarttrade_common.schemas.types import OrderSide, OrderType, TimeInForce, PositionType
from broker_adapter_service.schemas.order_dtos import BasOrderPlaceRequest, BasOrderLeg


@pytest.mark.injection
@pytest.mark.asyncio
async def test_cancel_unfilled_order(
    config,
    bas_client,
    mock_client,
    redis_event_collector,
    broker_state_client,
    assertions,
    test_account_id,
    logger,
    instrument_catalog,
):
    """
    Test: Cancel an unfilled order (no fills before cancellation).

    Validates:
    - Order placement succeeds
    - Cancellation succeeds without fills
    - Order transitions to CANCELLED (via Redis Streams)
    - No execution events after cancellation
    - Broker state verification
    - No position created
    """
    maruti_inst = instrument_catalog.get_equity("MARUTI")
    broker_id = config.broker_id

    # Act: Create and place order
    order_request = BasOrderPlaceRequest(
        client_order_id=f"test_cancel_unfilled_{test_account_id}_{uuid.uuid4().hex[:8]}",
        position_type=PositionType.INTRADAY,
        legs=[
            BasOrderLeg(
                instrument_id=maruti_inst["id"],
                instrument_type="EQUITY",
                side=OrderSide.BUY,
                qty=100,
                order_type=OrderType.LIMIT,
                price=Decimal("9000.00"),
                stop_price=None,
                ltp=Decimal("9050.00"),
            )
        ],
        underlying_symbol="MARUTI",
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

    # Observe: Wait for cancellation completion via Redis Streams
    events = await redis_event_collector.wait_for_completion(order_id, timeout=15.0)
    logger.info(f"Events collected | Count: {len(events)}")

    # Assert: Order lifecycle transitions to CANCELLED
    assertions.assert_order_lifecycle(events, "CANCELLED", 0)
    logger.info("✓ Order cancelled (no fills)")

    # Assert: Status transitions correct
    assertions.assert_status_transition_correct(events, ["PLACED", "CANCELLED"])
    logger.info("✓ Status transitions validated")

    # Assert: No duplicate events
    assertions.assert_no_duplicate_events(events)
    logger.info("✓ No duplicate events")

    # Assert: Broker state matches events
    broker_order = await broker_state_client.get_order_state(broker_id, test_account_id, order_id)
    assertions.assert_broker_state_matches_events(broker_order, events)
    logger.info("✓ Broker state matches events")

    # Assert: No position created
    broker_positions = await broker_state_client.get_position_state(broker_id, test_account_id, maruti_inst["id"])
    assert not broker_positions or broker_positions.get("net_qty", 0) == 0, "Position should not exist for cancelled order"
    logger.info("✓ No position created")


@pytest.mark.injection
@pytest.mark.asyncio
async def test_cancel_then_fill_rejected(
    config,
    bas_client,
    mock_client,
    redis_event_collector,
    broker_state_client,
    assertions,
    test_account_id,
    logger,
    instrument_catalog,
):
    """
    Test: Fill injection after cancellation is rejected.

    Validates:
    - Order cancelled successfully
    - Attempting to fill a cancelled order fails gracefully
    - Final state remains CANCELLED with no fills (via Redis Streams)
    - Broker state verification
    """
    titan_inst = instrument_catalog.get_equity("TITAN")
    broker_id = config.broker_id

    # Act: Create and place order
    order_request = BasOrderPlaceRequest(
        client_order_id=f"test_cancel_then_fill_{test_account_id}_{uuid.uuid4().hex[:8]}",
        position_type=PositionType.INTRADAY,
        legs=[
            BasOrderLeg(
                instrument_id=titan_inst["id"],
                instrument_type="EQUITY",
                side=OrderSide.BUY,
                qty=50,
                order_type=OrderType.LIMIT,
                price=Decimal("2800.00"),
                stop_price=None,
                ltp=Decimal("2850.00"),
            )
        ],
        underlying_symbol="TITAN",
        tif=TimeInForce.DAY,
    )

    [order_resp] = await bas_client.place_order(broker_id, test_account_id, order_request)
    order_id = order_resp.broker_order_id
    logger.info(f"Order placed | ID: {order_id} | Status: {order_resp.status}")

    # Act: Cancel order
    await mock_client.cancel_order(
        broker_id=broker_id,
        account_id=test_account_id,
        order_id=order_id,
    )
    logger.info(f"Order cancelled | ID: {order_id}")

    # Wait for cancellation event
    events = await redis_event_collector.wait_for_completion(order_id, timeout=15.0)
    logger.info(f"Cancellation events collected | Count: {len(events)}")

    # Act: Try to inject fill after cancellation (should be rejected by broker)
    try:
        await mock_client.inject_fill(
            broker_id=broker_id,
            account_id=test_account_id,
            order_id=order_id,
            sequence=1,
            fill_qty=50,
            fill_price=Decimal("2810.00"),
        )
        logger.info("Fill injection attempted after cancellation")
    except Exception as e:
        logger.info(f"Fill injection rejected as expected: {e}")

    # Observe: Final state should remain CANCELLED
    final_events = await redis_event_collector.get_events(order_id)
    logger.info(f"Final events collected | Count: {len(final_events)}")

    # Assert: Order lifecycle shows CANCELLED
    assertions.assert_order_lifecycle(final_events, "CANCELLED", 0)
    logger.info("✓ Order remains CANCELLED")

    # Assert: Broker state verification
    broker_order = await broker_state_client.get_order_state(broker_id, test_account_id, order_id)
    assert broker_order.get("status") == "CANCELLED", f"Expected CANCELLED, got {broker_order.get('status')}"
    logger.info("✓ Broker state confirmed CANCELLED")

    # Assert: No fills in broker state
    broker_order_qty = broker_order.get("filled_qty", broker_order.get("qty", 0))
    assert broker_order_qty == 0, f"Expected 0 fills, got {broker_order_qty}"
    logger.info("✓ No fills in broker state")
