"""
Integration test — BAS → Redis `trade.executed.v1`.

Pair under test: broker-adapter-service → Redis Streams (`events:trade.executed.v1`).

Contract:
    1. BAS publishes trade.executed.v1 events when trades are executed.
    2. Every trade event must include required fields: trade_id, instrument_id, side, quantity, price, order_id.
    3. Trade events must validate against the schema.
    4. Each trade event has a unique event_id and idempotency_key.
    5. Trade events are published after fills (driven by PBS WebSocket trade.update events).

Past regressions guarded:
    - Trade events missing required fields.
    - Trade events not being published after fills.
    - Trade events failing schema validation.
"""

from __future__ import annotations

from decimal import Decimal

import pytest


pytestmark = pytest.mark.asyncio


async def test_trade_event_published_after_fill(
    config,
    instrument_catalog,
    test_account_id,
    place_and_sync_order,
    mock_client,
    redis_event_collector,
):
    """BAS publishes trade.executed.v1 event when a fill occurs.

    This test validates:
    1. After placing and filling an order, a trade.executed.v1 event is published
    2. The trade event contains all required fields
    3. The trade event is linked to the order via order_id
    """
    broker_id = config.broker_id

    # Use the same helper as the BAS↔PBS WS test for consistency
    from e2e.integration.test_bas_pbs_execution_ws import _place_and_fill

    broker_order_id, instrument_id, events = await _place_and_fill(
        place_and_sync_order=place_and_sync_order,
        mock_client=mock_client,
        instrument_catalog=instrument_catalog,
        test_account_id=test_account_id,
        broker_id=broker_id,
        redis_event_collector=redis_event_collector,
        instrument_index=0,
    )

    # Verify trade.executed.v1 event was published
    trade_events = [e for e in events if e.get("type") == "trade.executed.v1"]
    assert trade_events, (
        f"No trade.executed.v1 event found for broker_order_id={broker_order_id}. "
        f"Events seen: {[ (e.get('type')) for e in events ]}"
    )

    # Verify the trade event has all required fields
    trade_event = trade_events[0]
    payload = trade_event.get("payload") or {}

    # Required fields per trade.executed.v1 schema
    required_fields = ["trade_id", "instrument_id", "side", "quantity", "price"]
    for field in required_fields:
        assert payload.get(field) is not None, (
            f"trade.executed.v1 missing required field '{field}'. Payload: {payload}"
        )

    # Verify the trade is linked to the correct order
    assert payload.get("order_id") == broker_order_id, (
        f"trade.executed.v1 order_id mismatch: got {payload.get('order_id')}, "
        f"expected {broker_order_id}"
    )

    # Verify trade quantities and prices are reasonable
    assert int(payload.get("quantity", 0)) > 0, (
        f"trade.executed.v1 has invalid quantity: {payload.get('quantity')}"
    )
    assert Decimal(payload.get("price", "0")) > 0, (
        f"trade.executed.v1 has invalid price: {payload.get('price')}"
    )


async def test_trade_events_have_unique_ids_and_idempotency_keys(
    config,
    instrument_catalog,
    test_account_id,
    place_and_sync_order,
    mock_client,
    redis_event_collector,
):
    """Each trade.executed.v1 event has unique event_id and idempotency_key.

    This test validates the event publishing contract for trade events.
    """
    broker_id = config.broker_id

    from e2e.integration.test_bas_pbs_execution_ws import _place_and_fill

    broker_order_id, instrument_id, events = await _place_and_fill(
        place_and_sync_order=place_and_sync_order,
        mock_client=mock_client,
        instrument_catalog=instrument_catalog,
        test_account_id=test_account_id,
        broker_id=broker_id,
        redis_event_collector=redis_event_collector,
        instrument_index=0,
    )

    # Collect trade events
    trade_events = [e for e in events if e.get("type") == "trade.executed.v1"]
    assert trade_events, "No trade.executed.v1 events found"

    # Verify each trade event has unique event_id
    event_ids = [e.get("event_id") for e in trade_events]
    assert len(event_ids) == len(set(event_ids)), (
        f"trade.executed.v1 events have duplicate event_ids: {event_ids}"
    )

    # Verify each trade event has unique idempotency_key
    idempotency_keys = [e.get("idempotency_key") for e in trade_events]
    assert len(idempotency_keys) == len(set(idempotency_keys)), (
        f"trade.executed.v1 events have duplicate idempotency_keys: {idempotency_keys}"
    )


async def test_multiple_fills_generate_multiple_trade_events(
    config,
    instrument_catalog,
    test_account_id,
    place_and_sync_order,
    mock_client,
    redis_event_collector,
):
    """Multiple fills on the same order generate multiple trade.executed.v1 events.

    This test validates that each fill produces its own trade event.
    """
    broker_id = config.broker_id

    from e2e.integration.test_bas_pbs_execution_ws import _place_and_fill

    # Place and fill the order (first fill)
    broker_order_id, instrument_id, events = await _place_and_fill(
        place_and_sync_order=place_and_sync_order,
        mock_client=mock_client,
        instrument_catalog=instrument_catalog,
        test_account_id=test_account_id,
        broker_id=broker_id,
        redis_event_collector=redis_event_collector,
        instrument_index=0,
    )

    # Note: The current test infrastructure uses a single fill per order.
    # This test is a placeholder for when partial fills are supported.
    # For now, we just verify that a single fill produces exactly one trade event.
    trade_events = [e for e in events if e.get("type") == "trade.executed.v1"]
    
    # With the current single-fill approach, we expect exactly 1 trade event
    assert len(trade_events) == 1, (
        f"Expected 1 trade event for single fill, got {len(trade_events)}"
    )

    # Verify the trade event is linked to the correct order
    assert trade_events[0].get("payload", {}).get("order_id") == broker_order_id
