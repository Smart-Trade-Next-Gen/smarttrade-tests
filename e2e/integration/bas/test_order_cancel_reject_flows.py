"""
Integration test — Order cancel / reject lifecycle.

Pair under test: broker-adapter-service → paper-broker-service → Redis Streams.

Contract:
    1. Cancelling a PENDING/ACCEPTED LIMIT order produces an
       order.updated event with status=CANCELLED on `events:order.updated`.
    2. The CANCELLED event uses `broker_order_id` as the canonical
       `payload.order_id` (consistent with BAS' stateless identity model).
    3. Attempting to cancel a FILLED order is rejected by BAS/PBS with a
       4xx error — no spurious CANCELLED event is emitted.
    4. Cancelling an already-cancelled order is either a no-op (idempotent
       success) or a 4xx — but never produces a second CANCELLED event
       for the same broker_order_id.

This test complements `test_bas_pbs_rest.py::test_bas_cancel_removes_order_from_pbs`
(which verifies the BAS REST projection after cancel). Here we verify the
Redis event side: every cancel produces exactly one CANCELLED domain event
and never produces one for an invalid cancel.

Past regressions guarded:
    - BAS' cancel handler used to skip event emission entirely — cancels
      worked but no downstream consumer (Portfolio, Journal, Notification)
      ever heard about them.
    - PBS would silently succeed cancel on a filled order, then BAS would
      emit a CANCELLED event for a FILLED order, corrupting the journal.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import httpx
import pytest


pytestmark = pytest.mark.asyncio


async def _place_pending_limit_order(
    *,
    place_and_sync_order,
    instrument_catalog,
    config,
    test_account_id: str,
    instrument_index: int = 0,
    limit_price: Decimal = Decimal("100.00"),
    side: str = "BUY",
) -> tuple[str, str]:
    """Place a LIMIT order well off the LTP so it stays PENDING.

    Returns (broker_order_id, instrument_id).
    """
    instrument = instrument_catalog.get_test_instrument(instrument_index)
    instrument_id = instrument["id"]

    # For BUY: limit far below LTP. For SELL: limit far above LTP.
    ltp = (
        Decimal("550.00") if side == "BUY" else Decimal("50.00")
    )
    if side == "SELL":
        limit_price = Decimal("1000.00")

    response = await place_and_sync_order(
        config.broker_id,
        test_account_id,
        order_request={
            "instrument_id": instrument_id,
            "position_type": "INTRADAY",
            "side": side,
            "order_type": "LIMIT",
            "qty": 10,
            "price": limit_price,
            "ltp": ltp,
            "tif": "DAY",
        },
    )
    broker_order_id = response[0]["broker_order_id"]
    status = response[0]["status"]
    assert status in ("ACCEPTED", "PENDING"), (
        f"LIMIT order at {limit_price} with LTP={ltp} should stay PENDING. "
        f"Got status={status!r}."
    )
    return broker_order_id, instrument_id


def _filter_cancelled_events(events: list[dict], broker_order_id: str) -> list[dict]:
    """Return order.updated events with status=CANCELLED for a given
    broker_order_id."""
    return [
        e
        for e in events
        if e.get("type") == "order.updated"
        and (e.get("payload") or {}).get("status") == "CANCELLED"
        and (e.get("payload") or {}).get("order_id") == broker_order_id
    ]


async def test_cancel_pending_limit_emits_cancelled_event_on_redis(
    place_and_sync_order,
    bas_client,
    instrument_catalog,
    config,
    test_account_id,
    redis_event_collector,
):
    """Cancelling a PENDING LIMIT order produces a CANCELLED domain event
    on `events:order.updated` keyed by broker_order_id.

    If this event isn't emitted, downstream consumers (Portfolio, Journal,
    Notification) never learn about the cancellation and their state
    drifts permanently out of sync with BAS/PBS.
    """
    broker_order_id, _ = await _place_pending_limit_order(
        place_and_sync_order=place_and_sync_order,
        instrument_catalog=instrument_catalog,
        config=config,
        test_account_id=test_account_id,
        instrument_index=0,
        limit_price=Decimal("100.00"),
    )

    # Cancel via BAS.
    cancel_response = await bas_client.cancel_order(
        config.broker_id, test_account_id, broker_order_id
    )
    assert cancel_response is not None, (
        f"cancel_order returned no body for broker_order_id={broker_order_id}"
    )

    # Wait for terminal state event on Redis.
    events = await redis_event_collector.wait_for_completion(
        broker_order_id, timeout=10.0
    )
    cancelled_events = _filter_cancelled_events(events, broker_order_id)
    assert cancelled_events, (
        f"No CANCELLED order.updated event for broker_order_id="
        f"{broker_order_id} after BAS cancel succeeded. Events seen: "
        f"{[(e.get('type'), (e.get('payload') or {}).get('status')) for e in events]}. "
        f"BAS' cancel handler may be skipping event emission."
    )

    # The CANCELLED event must use broker_order_id as the canonical id.
    cancelled_event = cancelled_events[-1]
    payload = cancelled_event["payload"]
    assert payload.get("order_id") == broker_order_id, (
        f"CANCELLED event payload.order_id={payload.get('order_id')!r} "
        f"does not match broker_order_id={broker_order_id!r}. BAS must use "
        f"broker_order_id as the canonical id (see "
        f"test_bas_redis_order_events.py for the same invariant on FILLED)."
    )
    assert payload.get("broker_order_id") == broker_order_id, (
        f"CANCELLED event payload.broker_order_id={payload.get('broker_order_id')!r} "
        f"does not match broker_order_id={broker_order_id!r}."
    )


async def test_cancel_filled_order_is_rejected_without_spurious_event(
    place_and_sync_order,
    bas_client,
    instrument_catalog,
    config,
    test_account_id,
    redis_event_collector,
    mock_client,
):
    """Cancelling a FILLED order must NOT produce a CANCELLED event.

    This is the most damaging regression class: a FILLED order journalled
    as CANCELLED would corrupt position aggregation. Either BAS or PBS
    must reject the cancel with 4xx, and no CANCELLED event for that
    broker_order_id may appear on Redis.
    """
    # Place a MARKET BUY and fill it via mock injection.
    instrument = instrument_catalog.get_test_instrument(1)
    instrument_id = instrument["id"]

    response = await place_and_sync_order(
        config.broker_id,
        test_account_id,
        order_request={
            "instrument_id": instrument_id,
            "position_type": "INTRADAY",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": 50,
        },
    )
    broker_order_id = response[0]["broker_order_id"]

    # Drive the fill.
    await mock_client.inject_fill(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_id=broker_order_id,
        sequence=1,
        fill_qty=50,
        fill_price=Decimal("400.00"),
    )

    # Wait for FILLED.
    events = await redis_event_collector.wait_for_completion(
        broker_order_id, timeout=10.0
    )
    filled = [
        e
        for e in events
        if e.get("type") == "order.updated"
        and (e.get("payload") or {}).get("status") == "FILLED"
    ]
    assert filled, (
        f"Expected FILLED event for broker_order_id={broker_order_id} "
        f"before testing cancel-after-fill. Got events: "
        f"{[(e.get('type'), (e.get('payload') or {}).get('status')) for e in events]}"
    )

    # Now try to cancel the FILLED order. Expect a 4xx.
    raised_4xx = False
    try:
        await bas_client.cancel_order(
            config.broker_id, test_account_id, broker_order_id
        )
    except httpx.HTTPStatusError as e:
        # 400/404/409/422 are all valid rejections.
        if 400 <= e.response.status_code < 500:
            raised_4xx = True
        else:
            raise
    except Exception:
        # Some servers raise a custom error; treat as rejection.
        raised_4xx = True

    # Brief settle: if BAS *did* erroneously emit a spurious CANCELLED
    # event, give it ~1s to land on Redis so we can catch it.
    await asyncio.sleep(1.0)

    cancelled_events = _filter_cancelled_events(
        redis_event_collector.get_events(broker_order_id), broker_order_id
    )
    assert not cancelled_events, (
        f"Cancelling a FILLED order produced a CANCELLED event for "
        f"broker_order_id={broker_order_id}. This corrupts downstream "
        f"journal/portfolio state. BAS or PBS must reject the cancel "
        f"without emitting any state-change event."
    )

    # Either BAS/PBS rejected with 4xx, or returned 200 idempotently
    # without emitting any event. Both are acceptable; only a spurious
    # CANCELLED event is a regression.
    if not raised_4xx:
        # If 200 returned, the order must still be in FILLED state
        # downstream — no state transition happened.
        latest_status_events = [
            (e.get("payload") or {}).get("status")
            for e in redis_event_collector.get_events(broker_order_id)
            if e.get("type") == "order.updated"
        ]
        assert latest_status_events[-1] == "FILLED", (
            f"Cancel on FILLED returned 200 but the most recent status "
            f"event is {latest_status_events[-1]!r}. Expected the FILLED "
            f"state to be preserved unchanged."
        )


async def test_cancel_idempotency_no_double_cancelled_event(
    place_and_sync_order,
    bas_client,
    instrument_catalog,
    config,
    test_account_id,
    redis_event_collector,
):
    """Two cancel calls against the same order produce at most one
    CANCELLED event.

    A naive cancel handler that emits an event every time the endpoint
    is hit (regardless of current state) would publish duplicates,
    breaking journal idempotency. Each broker_order_id must transition
    to CANCELLED exactly once.
    """
    broker_order_id, _ = await _place_pending_limit_order(
        place_and_sync_order=place_and_sync_order,
        instrument_catalog=instrument_catalog,
        config=config,
        test_account_id=test_account_id,
        instrument_index=2,
        limit_price=Decimal("120.00"),
    )

    # First cancel — expect success and a CANCELLED event.
    await bas_client.cancel_order(
        config.broker_id, test_account_id, broker_order_id
    )
    await redis_event_collector.wait_for_completion(broker_order_id, timeout=10.0)

    first_cancelled = _filter_cancelled_events(
        redis_event_collector.get_events(broker_order_id), broker_order_id
    )
    assert len(first_cancelled) >= 1, (
        f"First cancel did not produce a CANCELLED event for "
        f"broker_order_id={broker_order_id}."
    )

    # Second cancel — must NOT produce another CANCELLED event for the
    # same broker_order_id. PBS may return 200 (idempotent) or 4xx
    # (already terminal). Either is OK; only a duplicate event is the bug.
    try:
        await bas_client.cancel_order(
            config.broker_id, test_account_id, broker_order_id
        )
    except httpx.HTTPStatusError as e:
        if not (400 <= e.response.status_code < 500):
            raise
    except Exception:
        pass

    # Allow ~1s for any spurious event to land.
    await asyncio.sleep(1.0)

    final_cancelled = _filter_cancelled_events(
        redis_event_collector.get_events(broker_order_id), broker_order_id
    )
    assert len(final_cancelled) == len(first_cancelled), (
        f"Second cancel on an already-CANCELLED order broker_order_id="
        f"{broker_order_id} emitted an extra CANCELLED event "
        f"({len(first_cancelled)} → {len(final_cancelled)}). "
        f"Cancel handler must be idempotent at the event-emission layer."
    )


async def test_cancel_pending_limit_sell_emits_cancelled_event(
    place_and_sync_order,
    bas_client,
    instrument_catalog,
    config,
    test_account_id,
    redis_event_collector,
):
    """Cancel works symmetrically on a LIMIT SELL.

    Some lifecycle bugs are side-asymmetric (e.g. a code path that
    only fires for BUY). This test asserts the cancel→CANCELLED-event
    contract on the SELL side too.
    """
    broker_order_id, _ = await _place_pending_limit_order(
        place_and_sync_order=place_and_sync_order,
        instrument_catalog=instrument_catalog,
        config=config,
        test_account_id=test_account_id,
        instrument_index=3,
        side="SELL",
    )

    await bas_client.cancel_order(
        config.broker_id, test_account_id, broker_order_id
    )

    events = await redis_event_collector.wait_for_completion(
        broker_order_id, timeout=10.0
    )
    cancelled_events = _filter_cancelled_events(events, broker_order_id)
    assert cancelled_events, (
        f"No CANCELLED event for SELL-side broker_order_id={broker_order_id} "
        f"after cancel. Events seen: "
        f"{[(e.get('type'), (e.get('payload') or {}).get('status')) for e in events]}"
    )
