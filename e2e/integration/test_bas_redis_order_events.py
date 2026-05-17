"""
Integration test — BAS → Redis `order.updated.v1`.

Pair under test: broker-adapter-service → Redis Streams (`events:order.updated.v1`).

Contract:
    1. BAS publishes order.updated.v1 events for every order state transition:
       PLACED → ACCEPTED → FILLED (or CANCELLED / REJECTED for terminal failures).
    2. Every event must publish `payload.order_id` equal to the `broker_order_id`
       returned by the broker. BAS is stateless — `broker_order_id` is the
       canonical identity. `client_order_id` is only an idempotency token.
       (See memory: bas-stateless-order-identity.)
    3. Every event must include `payload.broker_order_id` AND `payload.client_order_id`.
    4. Every event must validate against its schema (no entry should fail the
       publisher's validate step or land in the DLQ).
    5. Each event has a unique `event_id` and a unique `idempotency_key`.
    6. Status sequence for a successful market fill: PLACED → ACCEPTED →
       FILLED (or PLACED → PENDING → FILLED, where ACCEPTED's value is
       overridden by the broker's response status).
    7. The FILLED event carries `filled_quantity` and `average_price` fields
       populated from the broker's payload.

Past regressions guarded:
    - BAS used to set `payload.order_id = client_order_id` for PLACED/ACCEPTED
      and `broker_order_id` only for FILLED → split lifecycle across two ids,
      no downstream consumer could track the full sequence by a single key.
    - BAS used to emit PLACED BEFORE calling the broker — but BAS has no
      durable state, so the pre-broker PLACED had no `broker_order_id` and
      added no value. PLACED now follows the broker response.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest


pytestmark = pytest.mark.asyncio


async def _place_and_collect_order_events(
    *,
    place_and_sync_order,
    mock_client,
    instrument_catalog,
    test_account_id: str,
    broker_id: str,
    redis_event_collector,
    qty: int = 100,
    price: Decimal = Decimal("550.00"),
) -> tuple[str, str, list[dict]]:
    """Place a MARKET BUY, drive the fill, and return all order.updated.v1
    events for that order.
    """
    instrument = instrument_catalog.get_any_equity(1)[0]
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
    client_order_id = place_response[0].get("client_order_id")

    await mock_client.inject_fill(
        broker_id=broker_id,
        account_id=test_account_id,
        order_id=broker_order_id,
        sequence=1,
        fill_qty=qty,
        fill_price=price,
    )

    await redis_event_collector.wait_for_completion(broker_order_id, timeout=10.0)

    # Drain a short grace period so any post-FILLED events also land.
    deadline = asyncio.get_event_loop().time() + 0.5
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.05)

    all_events = redis_event_collector.get_events(broker_order_id)
    order_events = [e for e in all_events if e.get("type") == "order.updated.v1"]
    return broker_order_id, client_order_id, order_events


async def test_every_order_event_uses_broker_order_id_as_canonical_id(
    config,
    instrument_catalog,
    test_account_id,
    place_and_sync_order,
    mock_client,
    redis_event_collector,
):
    """Per the stateless-BAS invariant, every order.updated.v1 event MUST
    carry `payload.order_id = broker_order_id` so downstream consumers can
    track the full lifecycle by a single key.
    """
    broker_order_id, client_order_id, order_events = await _place_and_collect_order_events(
        place_and_sync_order=place_and_sync_order,
        mock_client=mock_client,
        instrument_catalog=instrument_catalog,
        test_account_id=test_account_id,
        broker_id=config.broker_id,
        redis_event_collector=redis_event_collector,
    )

    assert len(order_events) >= 2, (
        f"Expected at least ACCEPTED + FILLED order.updated.v1 events; got "
        f"{[(e.get('payload') or {}).get('status') for e in order_events]}"
    )

    for ev in order_events:
        payload = ev["payload"]
        assert payload.get("order_id") == broker_order_id, (
            f"order.updated.v1 event with status={payload.get('status')} has "
            f"order_id={payload.get('order_id')!r}; expected broker_order_id="
            f"{broker_order_id!r}. BAS must not use client_order_id as the "
            f"canonical id (see memory: bas-stateless-order-identity)."
        )
        assert payload.get("broker_order_id") == broker_order_id, (
            f"order.updated.v1 event missing broker_order_id in payload: {payload}"
        )
        if client_order_id is not None:
            assert payload.get("client_order_id") == client_order_id, (
                f"order.updated.v1 client_order_id mismatch: "
                f"got {payload.get('client_order_id')!r} expected {client_order_id!r}"
            )


async def test_order_event_status_sequence_reaches_filled(
    config,
    instrument_catalog,
    test_account_id,
    place_and_sync_order,
    mock_client,
    redis_event_collector,
):
    """The first order.updated.v1 event MUST be ACCEPTED (broker took the
    order and assigned a broker_order_id) — BAS is stateless and does not
    emit PLACED before the broker call. FILLED MUST follow later.

    Brokers may inject intermediate states (PENDING etc.) between
    ACCEPTED and FILLED; this test checks the checkpoints, not the exact
    sequence.
    """
    _, _, order_events = await _place_and_collect_order_events(
        place_and_sync_order=place_and_sync_order,
        mock_client=mock_client,
        instrument_catalog=instrument_catalog,
        test_account_id=test_account_id,
        broker_id=config.broker_id,
        redis_event_collector=redis_event_collector,
    )

    statuses = [(e.get("payload") or {}).get("status") for e in order_events]

    accepted_idx = next((i for i, s in enumerate(statuses) if s == "ACCEPTED"), None)
    filled_idx = next((i for i, s in enumerate(statuses) if s == "FILLED"), None)
    assert accepted_idx is not None, f"No ACCEPTED status in order events: {statuses}"
    assert filled_idx is not None, f"No FILLED status in order events: {statuses}"
    assert accepted_idx < filled_idx, (
        f"ACCEPTED must precede FILLED. Got status sequence: {statuses}"
    )
    assert "PLACED" not in statuses, (
        f"BAS must not emit PLACED — that's a pre-broker state with no "
        f"broker_order_id. Got status sequence: {statuses}"
    )


async def test_filled_event_carries_fill_quantity_and_price(
    config,
    instrument_catalog,
    test_account_id,
    place_and_sync_order,
    mock_client,
    redis_event_collector,
):
    """The FILLED order.updated.v1 must carry `filled_quantity` and a non-zero
    `average_price`. A regression set average_price to "0" because the BAS
    plugin was reading `payload.get('avg_price')` while PBS' WS payload sent
    `average_price`.
    """
    qty = 100
    price = Decimal("550.00")
    _, _, order_events = await _place_and_collect_order_events(
        place_and_sync_order=place_and_sync_order,
        mock_client=mock_client,
        instrument_catalog=instrument_catalog,
        test_account_id=test_account_id,
        broker_id=config.broker_id,
        redis_event_collector=redis_event_collector,
        qty=qty,
        price=price,
    )

    filled = [e for e in order_events if (e.get("payload") or {}).get("status") == "FILLED"]
    assert filled, "No FILLED event found in order events"
    payload = filled[-1]["payload"]

    assert int(payload.get("filled_quantity") or 0) == qty, (
        f"FILLED event filled_quantity={payload.get('filled_quantity')!r}, "
        f"expected {qty}"
    )
    average_price = payload.get("average_price")
    assert average_price not in (None, "0", "0.0", "", 0), (
        f"FILLED event has average_price={average_price!r} — looks like a "
        f"PBS↔BAS field name regression (avg_price vs average_price)."
    )
    assert Decimal(str(average_price)) == price, (
        f"FILLED event average_price={average_price!r} expected {price}"
    )


async def test_order_event_ids_and_idempotency_keys_are_unique(
    config,
    instrument_catalog,
    test_account_id,
    place_and_sync_order,
    mock_client,
    redis_event_collector,
):
    """Each order.updated.v1 emission MUST have unique event_id and unique
    idempotency_key. Duplicate keys would let consumers skip a state
    transition, breaking the lifecycle.
    """
    _, _, order_events = await _place_and_collect_order_events(
        place_and_sync_order=place_and_sync_order,
        mock_client=mock_client,
        instrument_catalog=instrument_catalog,
        test_account_id=test_account_id,
        broker_id=config.broker_id,
        redis_event_collector=redis_event_collector,
    )

    event_ids: list[str] = []
    idempotency_keys: list[str] = []
    for ev in order_events:
        data = ev.get("data") or {}
        eid = data.get("event_id")
        ikey = data.get("idempotency_key")
        assert eid, f"order.updated.v1 event missing event_id: {data}"
        assert ikey, f"order.updated.v1 event missing idempotency_key: {data}"
        event_ids.append(eid)
        idempotency_keys.append(ikey)

    assert len(set(event_ids)) == len(event_ids), (
        f"Duplicate event_id in order events: {event_ids}"
    )
    assert len(set(idempotency_keys)) == len(idempotency_keys), (
        f"Duplicate idempotency_key in order events: {idempotency_keys}"
    )
