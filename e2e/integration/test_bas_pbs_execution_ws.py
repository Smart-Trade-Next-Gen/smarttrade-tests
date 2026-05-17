"""
Integration test — BAS ↔ Paper Broker execution-updates WebSocket.

Pair under test: broker-adapter-service ←→ paper-broker-service (internal WS).

Contract:
    1. When BAS bootstraps an account session (lazily, on first order / first
       account-scoped request), it MUST open a WebSocket to PBS at
       `/internal/api/v1/execution-updates` and keep it open for the life of
       the session.
    2. When PBS executes a fill (driven by a quote on `market.quote.v1`), it
       broadcasts `order.update` + `trade.update` + `position.update` over
       that WebSocket.
    3. BAS receives those WS events and converts each into the corresponding
       domain event on Redis Streams:
            order.update    → events:order.updated.v1 (status=FILLED)
            trade.update    → events:trade.executed.v1
            position.update → events:position.updated.v1
    4. The connection survives multiple sequential fills — a second fill on a
       different order on the same session also produces all three Redis
       events.

This test does NOT validate the *content* of the domain events beyond what is
needed to prove the WS path is alive (qty > 0, status FILLED, broker_order_id
present). Field-level contract checks belong in the BAS-→Redis test.

Past regressions this test guards against:
    - `asyncio.create_task` reference dropped in session bootstrap → the
      start_ws task was garbage-collected and BAS never connected.
    - PBS WS connection closed inside `_emit_position_event_with_outbox`
      after the first position event, breaking every subsequent fill.
    - BAS plugin reading wrong PBS payload field names (`net_quantity` vs
      `net_qty`, `avg_price` vs `average_price`) → events with all-zero fields.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest


pytestmark = pytest.mark.asyncio


async def _place_and_fill(
    *,
    place_and_sync_order,
    mock_client,
    instrument_catalog,
    test_account_id: str,
    broker_id: str,
    redis_event_collector,
    instrument_index: int,
    qty: int = 100,
    price: Decimal = Decimal("550.00"),
) -> tuple[str, str, list[dict]]:
    """Place a MARKET BUY through BAS, inject a quote on market.quote.v1 to
    drive PBS execution, and wait for the order to reach a terminal status
    via the Redis event stream.

    Returns (broker_order_id, instrument_id, collected events for that order).
    """
    instrument = instrument_catalog.get_any_equity(instrument_index + 1)[instrument_index]
    instrument_id = instrument["id"]

    place_response = await place_and_sync_order(
        broker_id,
        test_account_id,
        order_request={
            "instrument_id": instrument_id,
            "position_type": "INTRADAY",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": qty,
        },
    )
    broker_order_id = place_response[0]["broker_order_id"]

    # Drive the fill: publish a quote at `price` for this instrument. PBS'
    # market-data consumer picks it up, the execution worker fills any open
    # order on that instrument, then PBS broadcasts on the WS.
    await mock_client.inject_fill(
        broker_id=broker_id,
        account_id=test_account_id,
        order_id=broker_order_id,
        sequence=1,
        fill_qty=qty,
        fill_price=price,
    )

    events = await redis_event_collector.wait_for_completion(
        broker_order_id, timeout=10.0
    )

    # FILLED on order.updated.v1 is published first; trade.executed.v1 and
    # position.updated.v1 follow within milliseconds. Give the reader loop a
    # short grace period to drain them into the per-order index before the
    # test inspects `events`.
    deadline = asyncio.get_event_loop().time() + 2.0
    while asyncio.get_event_loop().time() < deadline:
        per_order = redis_event_collector.get_events(broker_order_id)
        per_order_types = {e.get("type") for e in per_order}
        positions = [
            e
            for e in redis_event_collector.get_events_on_stream(
                "events:position.updated.v1"
            )
            if (e.get("payload") or {}).get("instrument_id") == instrument_id
        ]
        if (
            {"order.updated.v1", "trade.executed.v1"}.issubset(per_order_types)
            and positions
        ):
            break
        await asyncio.sleep(0.05)
    return broker_order_id, instrument_id, redis_event_collector.get_events(broker_order_id)


def _assert_filled_event(events: list[dict], broker_order_id: str, qty: int) -> dict:
    """Find the FILLED order.updated.v1 event and return it for further checks."""
    filled = [
        e
        for e in events
        if (e.get("payload") or {}).get("status") == "FILLED"
        and e.get("type") == "order.updated.v1"
    ]
    assert filled, (
        f"No FILLED order.updated.v1 event for broker_order_id={broker_order_id}. "
        f"Events seen: {[ (e.get('type'), (e.get('payload') or {}).get('status')) for e in events ]}"
    )
    event = filled[-1]
    payload = event["payload"]
    assert payload.get("order_id") == broker_order_id, (
        f"FILLED event order_id mismatch: payload={payload.get('order_id')} "
        f"expected={broker_order_id}"
    )
    assert int(payload.get("filled_quantity") or 0) == qty, (
        f"FILLED event filled_quantity mismatch: got {payload.get('filled_quantity')} "
        f"expected {qty}"
    )
    return event


async def test_bas_receives_pbs_execution_events_and_publishes_to_redis(
    config,
    instrument_catalog,
    test_account_id,
    place_and_sync_order,
    mock_client,
    redis_event_collector,
):
    """A single fill produces all three downstream Redis events.

    If BAS' WS connection to PBS is broken, none of these events will appear
    — PBS will broadcast to 0 connected clients and the FILLED state stays
    inside PBS' DB only.
    """
    broker_id = config.broker_id

    broker_order_id, instrument_id, events = await _place_and_fill(
        place_and_sync_order=place_and_sync_order,
        mock_client=mock_client,
        instrument_catalog=instrument_catalog,
        test_account_id=test_account_id,
        broker_id=broker_id,
        redis_event_collector=redis_event_collector,
        instrument_index=0,
    )

    # 1. BAS must have published an order.updated.v1 with status=FILLED.
    _assert_filled_event(events, broker_order_id, qty=100)

    # 2. trade.executed.v1 must exist for this order.
    trade_events = [e for e in events if e.get("type") == "trade.executed.v1"]
    assert trade_events, (
        "No trade.executed.v1 emitted by BAS — BAS' _handle_trade_update either "
        "didn't fire (WS broken) or failed schema validation on its way to outbox."
    )

    # 3. position.updated.v1 must exist for this instrument with non-zero qty.
    #    Position events don't carry order_id (they're keyed on instrument),
    #    so look them up on the stream and filter by instrument_id.
    #    Past regressions sent net_quantity=0 because the plugin read the
    #    wrong PBS field name.
    position_events = [
        e
        for e in redis_event_collector.get_events_on_stream(
            "events:position.updated.v1"
        )
        if (e.get("payload") or {}).get("instrument_id") == instrument_id
    ]
    assert position_events, (
        f"No position.updated.v1 emitted for instrument_id={instrument_id}."
    )
    last_position_payload = position_events[-1].get("payload") or {}
    assert int(last_position_payload.get("net_quantity") or 0) != 0, (
        f"position.updated.v1 has net_quantity=0 — likely a PBS↔BAS field "
        f"name mismatch (e.g. net_qty vs net_quantity). Payload: "
        f"{last_position_payload}"
    )


async def test_bas_pbs_ws_survives_multiple_sequential_fills(
    config,
    instrument_catalog,
    test_account_id,
    place_and_sync_order,
    mock_client,
    redis_event_collector,
):
    """A second order on the same session must also fill end-to-end.

    Guards against the regression where BAS closed the PBS WebSocket inside
    `_emit_position_event_with_outbox` after the first fill, leaving every
    subsequent order stuck in PENDING because the WS was dead.
    """
    broker_id = config.broker_id

    first_order_id, _first_instrument, first_events = await _place_and_fill(
        place_and_sync_order=place_and_sync_order,
        mock_client=mock_client,
        instrument_catalog=instrument_catalog,
        test_account_id=test_account_id,
        broker_id=broker_id,
        redis_event_collector=redis_event_collector,
        instrument_index=0,
    )
    _assert_filled_event(first_events, first_order_id, qty=100)

    # Small breather so the second order isn't racing the first
    # fill's downstream consumers — not required for correctness, just for
    # cleaner logs when this fails.
    await asyncio.sleep(0.2)

    second_order_id, _second_instrument, second_events = await _place_and_fill(
        place_and_sync_order=place_and_sync_order,
        mock_client=mock_client,
        instrument_catalog=instrument_catalog,
        test_account_id=test_account_id,
        broker_id=broker_id,
        redis_event_collector=redis_event_collector,
        instrument_index=1,
    )
    _assert_filled_event(second_events, second_order_id, qty=100)
