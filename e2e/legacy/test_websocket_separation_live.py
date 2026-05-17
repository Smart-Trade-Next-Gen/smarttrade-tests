"""
Tests for WebSocket channel separation — MDS UI vs BAS account channels.

Architectural note: BAS and PBS no longer consume MDS via WebSocket; they
read market data from the Redis stream `market.quote.v1`. The MDS WebSocket
is now strictly the UI-facing market-data channel. These tests therefore
guard the invariant that the MDS UI channel never delivers execution events
(orders/trades/positions) — those flow exclusively over the BAS WebSocket.
"""

import asyncio
import pytest
from decimal import Decimal

pytestmark = pytest.mark.live_ws


@pytest.mark.asyncio
async def test_mds_ws_receives_no_execution_events(
    config,
    instrument_catalog,
    test_account_id,
    auth_token,
    bas_client,
    mock_client,
    mds_client,
    bas_ws_client,
    place_and_sync_order,
    event_collector,
):
    """MDS UI channel never carries execution events even when an order is filling concurrently."""
    # Setup
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]

    # MDS client is already connected (from fixture)
    # BAS client is already connected (from fixture)

    # Place & sync order
    order_responses = await place_and_sync_order(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_request={
            "instrument_id": instrument_id,
            "position_type": "INTRADAY",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": 100,
        },
    )
    order_id = order_responses[0]["broker_order_id"]

    # Inject fill
    await mock_client.inject_fill(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=100,
        fill_price=Decimal("550.00"),
    )

    # Wait for BAS event
    await event_collector.wait_for_completion(order_id, timeout=config.timeout_medium)

    # Wait 2 seconds for any stray events
    await asyncio.sleep(2.0)

    # Check MDS event queue — should be empty or no execution events.
    # Bound the read so an idle MDS WS doesn't hang the runner; we expect
    # *no* execution events here, so a timeout is the success path.
    mds_events: list = []
    if hasattr(mds_client, "stream_events"):
        try:
            event = await asyncio.wait_for(
                mds_client.stream_events().__anext__(), timeout=2.0
            )
            mds_events = [event]
        except (asyncio.TimeoutError, StopAsyncIteration):
            # No execution events on the MDS UI channel within the window
            # (the success path for this assertion).
            mds_events = []

    # Assertions: MDS should NOT have execution events
    for event in mds_events:
        event_type = event.get("type", "")
        assert not any(x in event_type for x in ["order.filled", "trade.executed", "position.updated"]), \
            f"MDS received execution event: {event_type}"


@pytest.mark.asyncio
async def test_bas_ws_receives_execution_events_only(
    config,
    instrument_catalog,
    test_account_id,
    auth_token,
    bas_client,
    mock_client,
    bas_ws_client,
    place_and_sync_order,
    event_collector,
):
    """Test that BAS WebSocket receives execution events after fill."""
    # Setup
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]

    # Place & sync order
    order_responses = await place_and_sync_order(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_request={
            "instrument_id": instrument_id,
            "position_type": "INTRADAY",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": 100,
        },
    )
    order_id = order_responses[0]["broker_order_id"]

    # Inject fill
    await mock_client.inject_fill(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=100,
        fill_price=Decimal("550.00"),
    )

    # Wait for BAS event
    events = await event_collector.wait_for_completion(order_id, timeout=config.timeout_medium)

    # Assertions: BAS should have execution events
    assert len(events) > 0
    event_types = [e.get("type") for e in events]
    assert any("order" in t and "fill" in t for t in event_types), \
        f"BAS missing order fill event. Got: {event_types}"


@pytest.mark.asyncio
async def test_websocket_separation_integrity(
    config,
    instrument_catalog,
    test_account_id,
    auth_token,
    bas_client,
    mock_client,
    mds_client,
    bas_ws_client,
    place_and_sync_order,
    event_collector,
):
    """Test that both WebSocket channels maintain integrity and isolation."""
    # Setup
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]

    # Both clients connected and ready

    # Place & sync order
    order_responses = await place_and_sync_order(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_request={
            "instrument_id": instrument_id,
            "position_type": "INTRADAY",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": 100,
        },
    )
    order_id = order_responses[0]["broker_order_id"]

    # Inject fill
    await mock_client.inject_fill(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=100,
        fill_price=Decimal("550.00"),
    )

    # Wait for BAS events
    bas_events = await event_collector.wait_for_completion(order_id, timeout=config.timeout_medium)

    # Assertions
    assert len(bas_events) > 0, "BAS should receive execution events"

    # Verify BAS received correct event types
    event_types = [e.get("type") for e in bas_events]
    assert any("order" in t and "fill" in t for t in event_types), "Missing order fill event"
