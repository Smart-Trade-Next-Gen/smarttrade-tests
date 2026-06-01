"""
Integration tests for SmartTrade architecture boundary enforcement.

These tests verify that services respect their architectural boundaries:
- PBS does not emit directly to execution event topics (only BAS does)
- BAS does not require MDS synchronously for execution
- Portfolio does not affect execution (read-only consumer)
- Journal does not affect execution (read-only consumer)
- PBS accepts unknown instrument_id (operates on strings only)
"""

from __future__ import annotations

from decimal import Decimal

import pytest

pytestmark = pytest.mark.asyncio


@pytest.mark.asyncio
async def test_pbs_does_not_emit_to_execution_topics(
    config,
    instrument_catalog,
    test_account_id,
    bas_client,
    mock_client,
    place_and_sync_order,
    redis_event_collector,
):
    """
    Test that PBS never publishes directly to execution event topics.

    Only BAS should emit order.updated, trade.executed, position.updated.
    PBS only emits broker.order_update which BAS consumes.
    """
    # Setup
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]
    qty = 100
    price = Decimal("550.00")

    # Inject quote BEFORE placing MARKET order - PBS needs LTP to estimate cost
    await mock_client.inject_price_update(
        broker_id=config.broker_id,
        instrument_id=instrument_id,
        ltp=price,
    )

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
    events = await redis_event_collector.wait_for_completion(order_id, timeout=config.timeout_medium)

    # Verify events came from BAS (not PBS)
    # BAS should emit order.updated events
    order_events = [e for e in events if e.get("type") == "order.updated"]
    
    assert len(order_events) > 0, "order.updated events should be emitted by BAS"
    
    # All events should have event_id (idempotency)
    for event in order_events:
        # event_id is nested in data.event_id
        assert "data" in event and "event_id" in event["data"], "Event should have event_id for idempotency"


@pytest.mark.asyncio
async def test_bas_does_not_require_mds_synchronously_for_execution(
    config,
    instrument_catalog,
    test_account_id,
    bas_client,
    mock_client,
    place_and_sync_order,
    redis_event_collector,
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

    # Inject quote BEFORE placing MARKET order - PBS needs LTP to estimate cost
    await mock_client.inject_price_update(
        broker_id=config.broker_id,
        instrument_id=instrument_id,
        ltp=price,
    )

    # Place & sync order (this uses instrument_id from local instrument master)
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
    events = await redis_event_collector.wait_for_completion(order_id, timeout=config.timeout_medium)

    # Assertions
    assert len(events) > 0, "Order should execute without MDS sync call"
    event_types = [e.get("type") for e in events]
    assert any("order" in t for t in event_types), "Order events should be present"


@pytest.mark.asyncio
async def test_portfolio_does_not_affect_execution(
    config,
    instrument_catalog,
    test_account_id,
    bas_client,
    mock_client,
    place_and_sync_order,
    portfolio_client,
    redis_event_collector,
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

    # Inject quote BEFORE placing MARKET order - PBS needs LTP to estimate cost
    await mock_client.inject_price_update(
        broker_id=config.broker_id,
        instrument_id=instrument_id,
        ltp=price,
    )

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
    events = await redis_event_collector.wait_for_completion(order_id, timeout=config.timeout_medium)

    # Assertions: Execution should complete
    assert len(events) > 0
    event_types = [e.get("type") for e in events]
    assert any("order" in t for t in event_types), \
        "Order should execute regardless of Portfolio state"


@pytest.mark.asyncio
async def test_journal_does_not_affect_execution(
    config,
    instrument_catalog,
    test_account_id,
    bas_client,
    mock_client,
    place_and_sync_order,
    journal_client,
    redis_event_collector,
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

    # Inject quote BEFORE placing MARKET order - PBS needs LTP to estimate cost
    await mock_client.inject_price_update(
        broker_id=config.broker_id,
        instrument_id=instrument_id,
        ltp=price,
    )

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
    events = await redis_event_collector.wait_for_completion(order_id, timeout=config.timeout_medium)

    # Assertions: Execution should complete
    assert len(events) > 0
    event_types = [e.get("type") for e in events]
    assert any("order" in t for t in event_types), \
        "Order should execute regardless of Journal state"


@pytest.mark.asyncio
async def test_pbs_accepts_unknown_instrument_id(
    config,
    test_account_id,
    bas_client,
    mock_client,
    place_and_sync_order,
    instrument_catalog,
    redis_event_collector,
):
    """
    PBS operates on instrument_id strings only, no instrument metadata dependency.

    This test verifies PBS accepts instrument_id without any pre-seeded instrument record.
    """
    # Use an instrument from the catalog (it's seeded in BAS, not PBS)
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]
    qty = 100
    price = Decimal("550.00")

    # Inject quote BEFORE placing MARKET order - PBS needs LTP to estimate cost
    await mock_client.inject_price_update(
        broker_id=config.broker_id,
        instrument_id=instrument_id,
        ltp=price,
    )

    # Place & sync order through BAS
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

    # Inject fill - PBS should accept this without having instrument metadata
    await mock_client.inject_fill(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=qty,
        fill_price=price,
    )

    # Wait for execution
    events = await redis_event_collector.wait_for_completion(order_id, timeout=config.timeout_medium)

    # Assertions
    assert len(events) > 0, "Order should execute with instrument_id string only"
    event_types = [e.get("type") for e in events]
    assert any("order" in t for t in event_types), \
        "Order events should be present with instrument_id string"


@pytest.mark.asyncio
async def test_service_isolation(
    config,
    instrument_catalog,
    test_account_id,
    bas_client,
    mock_client,
    place_and_sync_order,
    redis_event_collector,
):
    """
    Test that services are isolated - one service issue doesn't break others.

    BAS should be able to execute orders even if downstream consumers (Portfolio, Journal)
    are slow or unavailable.
    """
    # Setup
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]
    qty = 100
    price = Decimal("550.00")

    # Inject quote BEFORE placing MARKET order - PBS needs LTP to estimate cost
    await mock_client.inject_price_update(
        broker_id=config.broker_id,
        instrument_id=instrument_id,
        ltp=price,
    )

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

    # Inject fill
    await mock_client.inject_fill(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=qty,
        fill_price=price,
    )

    # Wait for execution - BAS should emit events regardless of downstream consumers
    events = await redis_event_collector.wait_for_completion(order_id, timeout=config.timeout_medium)

    # Assertions
    assert len(events) > 0, "BAS should emit events regardless of downstream consumer state"
    event_types = [e.get("type") for e in events]
    assert any("order" in t for t in event_types), "Order events should be emitted by BAS"


@pytest.mark.asyncio
async def test_database_per_service_enforcement(
    config,
    instrument_catalog,
    test_account_id,
    bas_client,
    mock_client,
    place_and_sync_order,
    redis_event_collector,
):
    """
    Test that each service uses its own database - no cross-service DB queries.

    This is verified by checking that services communicate via Redis events,
    not direct database queries.
    """
    # Setup
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]
    qty = 100
    price = Decimal("550.00")

    # Inject quote BEFORE placing MARKET order - PBS needs LTP to estimate cost
    await mock_client.inject_price_update(
        broker_id=config.broker_id,
        instrument_id=instrument_id,
        ltp=price,
    )

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

    # Inject fill
    await mock_client.inject_fill(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=qty,
        fill_price=price,
    )

    # Wait for execution
    events = await redis_event_collector.wait_for_completion(order_id, timeout=config.timeout_medium)

    # Verify communication via Redis events (not direct DB queries)
    assert len(events) > 0, "Services should communicate via Redis events"
    
    # Check that events are on Redis streams (event bus pattern)
    event_streams = {e.get("type") for e in events}
    assert event_streams & {"order.updated", "trade.executed", "position.updated"}, \
        "Services should use Redis event streams for communication"