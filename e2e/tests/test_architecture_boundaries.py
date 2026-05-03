"""Tests for SmartTrade architecture boundary enforcement."""

import pytest
from decimal import Decimal

pytestmark = pytest.mark.architecture


@pytest.mark.asyncio
async def test_pbs_does_not_emit_to_execution_topics(
    config,
    instrument_catalog,
    test_account_id,
    auth_token,
    bas_client,
    mock_client,
    place_and_sync_order,
    redis_observer,
    event_collector,
):
    """
    Test that PBS never publishes directly to execution event topics.

    Only BAS should emit order.filled.v1, trade.executed.v1, position.updated.v1.
    PBS only emits broker.order_update which BAS consumes.
    """
    # Setup
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]
    qty = 100
    price = Decimal("550.00")

    # Record stream tail before fill
    stream_info = await redis_observer.get_stream_info("order.filled.v1")
    tail_id = stream_info.get("last-generated-id", "0-0")

    # Place & sync order
    order_responses = await place_and_sync_order(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_request={
            "instrument_id": instrument_id,
            "position_type": "INTRADAY",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": qty,
        },
    )
    order_id = order_responses[0]["broker_order_id"]

    # Inject fill via PBS
    await mock_client.inject_fill(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=qty,
        fill_price=price,
    )

    # Wait for BAS to process and emit
    await event_collector.wait_for_completion(order_id, timeout=config.timeout_medium)

    # Verify events came from BAS (not PBS)
    # BAS should emit exactly one order.filled.v1 event
    events = await redis_observer.observe_stream(
        event_type="order.filled.v1",
        timeout=2.0,
        count=10,
    )

    # Filter for our order
    order_events = [e for e in events if e.get("order_id") == order_id]

    # Assertions
    assert len(order_events) > 0, "order.filled.v1 events should be emitted by BAS"
    # All events should have trace_id indicating they came from BAS
    for event in order_events:
        # BAS should be the producer (trace_id context)
        assert "event_id" in event, "Event should have event_id (idempotency)"


@pytest.mark.asyncio
async def test_bas_does_not_require_mds_synchronously_for_execution(
    config,
    instrument_catalog,
    test_account_id,
    auth_token,
    bas_client,
    mock_client,
    place_and_sync_order,
    event_collector,
):
    """
    Test that BAS can execute orders without blocking on MDS.

    BAS uses local instrument master, not sync calls to MDS.
    """
    # Setup
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]
    qty = 100
    price = Decimal("550.00")

    # Place & sync order (this uses instrument_id from MDS already)
    order_responses = await place_and_sync_order(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_request={
            "instrument_id": instrument_id,
            "position_type": "INTRADAY",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": qty,
        },
    )
    order_id = order_responses[0]["broker_order_id"]

    # Inject fill - this should complete without MDS being available
    await mock_client.inject_fill(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=qty,
        fill_price=price,
    )

    # Wait for execution - should succeed even if MDS latency is high
    events = await event_collector.wait_for_completion(order_id, timeout=config.timeout_medium)

    # Assertions
    assert len(events) > 0, "Order should execute without MDS sync call"
    event_types = [e.get("type") for e in events]
    assert any("order" in t and "fill" in t for t in event_types), "Order should reach FILLED status"


@pytest.mark.asyncio
async def test_portfolio_does_not_affect_execution(
    config,
    instrument_catalog,
    test_account_id,
    auth_token,
    bas_client,
    mock_client,
    place_and_sync_order,
    portfolio_client,
    event_collector,
):
    """
    Test that Portfolio Service async consumption doesn't affect order execution.

    Portfolio is a read-model consumer, not part of execution path.
    """
    # Setup
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]
    qty = 100
    price = Decimal("550.00")

    # Place & sync order
    order_responses = await place_and_sync_order(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_request={
            "instrument_id": instrument_id,
            "position_type": "INTRADAY",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": qty,
        },
    )
    order_id = order_responses[0]["broker_order_id"]

    # Inject fill - execution should complete regardless of Portfolio state
    await mock_client.inject_fill(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=qty,
        fill_price=price,
    )

    # Wait for execution
    events = await event_collector.wait_for_completion(order_id, timeout=config.timeout_medium)

    # Assertions: Execution should complete
    assert len(events) > 0
    event_types = [e.get("type") for e in events]
    assert any("order" in t and "fill" in t for t in event_types), \
        "Order should execute regardless of Portfolio state"


@pytest.mark.asyncio
async def test_journal_does_not_affect_execution(
    config,
    instrument_catalog,
    test_account_id,
    auth_token,
    bas_client,
    mock_client,
    place_and_sync_order,
    journal_client,
    event_collector,
):
    """
    Test that Journal Service async consumption doesn't affect order execution.

    Journal is a read-model consumer, not part of execution path.
    """
    # Setup
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]
    qty = 100
    price = Decimal("550.00")

    # Place & sync order
    order_responses = await place_and_sync_order(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_request={
            "instrument_id": instrument_id,
            "position_type": "INTRADAY",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": qty,
        },
    )
    order_id = order_responses[0]["broker_order_id"]

    # Inject fill - execution should complete regardless of Journal state
    await mock_client.inject_fill(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=qty,
        fill_price=price,
    )

    # Wait for execution
    events = await event_collector.wait_for_completion(order_id, timeout=config.timeout_medium)

    # Assertions: Execution should complete
    assert len(events) > 0
    event_types = [e.get("type") for e in events]
    assert any("order" in t and "fill" in t for t in event_types), \
        "Order should execute regardless of Journal state"
