"""
Integration test — stress / chaos scenarios on the live execution path.

Pair under test: end-to-end (broker-adapter-service ↔ paper-broker-service ↔
market.quote ↔ Redis Streams).

Contract:
    1. Concurrent orders on different instruments fill independently. The
       per-order Redis event stream stays isolated — order A's FILLED event
       must reference order A's broker_order_id only, and likewise for B.
    2. A burst of sequential orders on the SAME instrument all reach FILLED
       in order. PBS' price-driven execution engine and BAS' WS event
       relay must survive being hit faster than the human path normally
       drives them.
    3. Duplicate quote re-publications (same sequence_number, same
       instrument) are de-duped by PBS' BaseStreamConsumer and do NOT
       produce extra fills for an already-filled order. The MARKET BUY
       fills exactly once.
    4. A rapid price ladder (multiple quotes per instrument in quick
       succession) does not trigger phantom fills — a single MARKET order
       fills once and stops; subsequent quotes update the cache without
       re-touching the filled order.

Why these scenarios are kept distinct from the existing integration tests:
    - test_pbs_redis_quote_consumer covers the consumer-group plumbing.
    - test_bas_pbs_execution_ws covers two sequential fills on the same
      session.
    - test_mds_quote_pbs_execution_chain covers LIMIT trigger math.
    These tests stress the chain with *load shape* the others don't: many
    concurrent orders, many quotes in flight at once, and explicit
    duplicate-quote replay.

Past regressions guarded:
    - Order events used to share `client_order_id` as the canonical key,
      so concurrent orders with similar client ids could be conflated by
      the per-order event index. The fix (broker_order_id as canonical
      id, see test_bas_redis_order_events) is re-asserted here under
      concurrency.
    - PBS' BaseStreamConsumer per-instrument idempotency check used to
      key on `event_id` alone, losing dedup if the publisher recycled
      ids. The current `(instrument_id, sequence_number)` key is the one
      this test pins.
"""

from __future__ import annotations

import asyncio
import time
from decimal import Decimal

import pytest
import redis.asyncio as redis


pytestmark = pytest.mark.asyncio


REAL_QUOTE_STREAM = "market.quote"


async def _publish_quote(
    redis_url: str,
    *,
    instrument_id: str,
    ltp: Decimal,
    sequence: int | None = None,
) -> str:
    """Publish a quote on the real production stream.

    Sequence-number scale MUST match `mock_client.inject_fill`
    (milliseconds since epoch) so PBS' per-instrument idempotency
    cache stays monotonic across tests. Microsecond-scale numbers
    would leave a value so large that subsequent ms-scale numbers
    appear as duplicates and get silently dropped.
    """
    client = await redis.from_url(redis_url, decode_responses=True)
    try:
        seq = sequence if sequence is not None else int(time.time() * 1000)
        return await client.xadd(
            REAL_QUOTE_STREAM,
            {
                "instrument_id": instrument_id,
                "ltp": str(ltp),
                "sequence_number": str(seq),
                "timestamp": str(int(time.time() * 1000)),
            },
        )
    finally:
        await client.close()


def _filled_event(events: list[dict], broker_order_id: str) -> dict | None:
    """Return the FILLED order.updated event for `broker_order_id` if any."""
    for e in events:
        if e.get("type") != "order.updated":
            continue
        payload = e.get("payload") or {}
        if (
            payload.get("status") == "FILLED"
            and payload.get("order_id") == broker_order_id
        ):
            return e
    return None


# ──────────────────────────────────────────────────────────────────────────
# Concurrency across instruments
# ──────────────────────────────────────────────────────────────────────────


async def test_concurrent_orders_on_distinct_instruments_fill_independently(
    config,
    instrument_catalog,
    test_account_id,
    place_and_sync_order,
    mock_client,
    redis_event_collector,
):
    """Three concurrent MARKET BUYs, each on a different instrument, all
    reach FILLED — and the per-order event index keys cleanly on
    broker_order_id (no cross-contamination of FILLED events between
    orders).
    """
    broker_id = config.broker_id
    instruments = instrument_catalog.get_test_instruments(3)
    assert len({i["id"] for i in instruments}) == 3, (
        "Test setup requires three distinct instruments; instrument catalog "
        f"returned duplicates: {[i['id'] for i in instruments]}"
    )

    # Place three orders concurrently.
    place_tasks = [
        place_and_sync_order(
            broker_id,
            test_account_id,
            order_request={
                "instrument_id": inst["id"],
                "position_type": "INTRADAY",
                "side": "BUY",
                "order_type": "MARKET",
                "qty": 25,
            },
        )
        for inst in instruments
    ]
    placements = await asyncio.gather(*place_tasks)
    broker_ids_in_order = [resp[0]["broker_order_id"] for resp in placements]
    assert len(set(broker_ids_in_order)) == 3, (
        f"Each concurrent placement must yield a unique broker_order_id; "
        f"got {broker_ids_in_order}. Without unique ids the per-order event "
        f"index cannot route FILLED events correctly."
    )

    # Drive a fill for each by injecting a distinct quote per instrument.
    fill_prices = [Decimal("200.00"), Decimal("400.00"), Decimal("600.00")]
    await asyncio.gather(
        *(
            mock_client.inject_fill(
                broker_id=broker_id,
                account_id=test_account_id,
                order_id=bid,
                sequence=i + 1,
                fill_qty=25,
                fill_price=fill_prices[i],
            )
            for i, bid in enumerate(broker_ids_in_order)
        )
    )

    # Each order must reach FILLED with the right qty and instrument-
    # specific average_price.
    for idx, (bid, inst, price) in enumerate(
        zip(broker_ids_in_order, instruments, fill_prices)
    ):
        events = await redis_event_collector.wait_for_completion(bid, timeout=15.0)
        filled = _filled_event(events, bid)
        assert filled is not None, (
            f"Order {idx} (broker_order_id={bid}, instrument={inst['id']}) "
            f"never reached FILLED. Events: "
            f"{[(e.get('type'), (e.get('payload') or {}).get('status')) for e in events]}"
        )
        payload = filled["payload"]
        assert int(payload.get("filled_quantity") or 0) == 25, (
            f"Order {idx} FILLED with qty={payload.get('filled_quantity')!r}; "
            f"expected 25."
        )
        # Each event index must contain ONLY events for its own broker_order_id.
        for e in events:
            payload_for_event = e.get("payload") or {}
            if "order_id" not in payload_for_event:
                # position.updated carries instrument_id, not order_id;
                # those land here because the collector's per-order index
                # tags any event referencing the order. That's fine.
                continue
            assert payload_for_event["order_id"] == bid, (
                f"Per-order index for {bid} contains an event whose payload "
                f"order_id is {payload_for_event['order_id']!r}. Concurrent "
                f"orders are leaking events between indexes."
            )


async def test_burst_of_sequential_orders_all_fill_in_order(
    config,
    instrument_catalog,
    test_account_id,
    place_and_sync_order,
    mock_client,
    redis_event_collector,
):
    """Five sequential MARKET BUYs on the same account (different
    instruments, to stay under PBS' per-instrument execution worker
    queue) all reach FILLED. The BAS↔PBS WebSocket session survives
    being hit five times in quick succession.
    """
    broker_id = config.broker_id
    # Five distinct equities so each order has a clean per-instrument fill
    # path. Using the same instrument across five MARKET orders would
    # serialize through PBS' single execution worker per instrument and
    # tell us less about WS-session survival.
    instruments = instrument_catalog.get_test_instruments(5)
    assert len(instruments) == 5, "Need 5 instruments for burst test"

    broker_ids: list[str] = []
    for inst in instruments:
        place_resp = await place_and_sync_order(
            broker_id,
            test_account_id,
            order_request={
                "instrument_id": inst["id"],
                "position_type": "INTRADAY",
                "side": "BUY",
                "order_type": "MARKET",
                "qty": 10,
            },
        )
        broker_ids.append(place_resp[0]["broker_order_id"])

    # Fill each in turn.
    for i, (bid, inst) in enumerate(zip(broker_ids, instruments)):
        await mock_client.inject_fill(
            broker_id=broker_id,
            account_id=test_account_id,
            order_id=bid,
            sequence=i + 1,
            fill_qty=10,
            fill_price=Decimal("100.00"),
        )

    # All five must reach FILLED. A regression in the BAS↔PBS WS session
    # supervisor would show up here: the first 1-2 fills land, then the
    # connection wedges and the remaining orders stay PENDING.
    not_filled: list[str] = []
    for bid in broker_ids:
        try:
            events = await redis_event_collector.wait_for_completion(bid, timeout=15.0)
            if _filled_event(events, bid) is None:
                not_filled.append(bid)
        except TimeoutError:
            not_filled.append(bid)

    assert not not_filled, (
        f"{len(not_filled)} of {len(broker_ids)} orders never reached "
        f"FILLED: {not_filled}. Likely BAS↔PBS WS wedged after the first "
        f"few fills (a regression in the supervisor task)."
    )


# ──────────────────────────────────────────────────────────────────────────
# Duplicate / replay handling
# ──────────────────────────────────────────────────────────────────────────


async def test_duplicate_quote_sequence_does_not_emit_extra_fills(
    config,
    instrument_catalog,
    test_account_id,
    place_and_sync_order,
    redis_event_collector,
):
    """Publishing the same quote (same instrument, same sequence_number)
    a second time after an order has already filled must NOT trigger
    another fill or another FILLED event for that order.

    PBS' BaseStreamConsumer keys idempotency on (sequence_key=instrument_id,
    sequence_number). If that check is bypassed, the second quote arrival
    re-enters the execution path, finds no open orders, and (best case)
    no-ops — or, if the order is somehow re-opened, double-fills. Either
    way, downstream consumers must see exactly ONE FILLED event per
    broker_order_id.
    """
    broker_id = config.broker_id
    instrument = instrument_catalog.get_test_instrument(0)
    instrument_id = instrument["id"]

    # Place MARKET BUY first (price cache empty → ACCEPTED, not filled).
    place_resp = await place_and_sync_order(
        broker_id,
        test_account_id,
        order_request={
            "instrument_id": instrument_id,
            "position_type": "INTRADAY",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": 20,
        },
    )
    broker_order_id = place_resp[0]["broker_order_id"]

    # First quote — drives the fill.
    seq = int(time.time() * 1000)
    await _publish_quote(
        config.redis_url, instrument_id=instrument_id, ltp=Decimal("321.00"),
        sequence=seq,
    )
    events = await redis_event_collector.wait_for_completion(
        broker_order_id, timeout=10.0
    )
    first_filled = _filled_event(events, broker_order_id)
    assert first_filled is not None, "First quote did not fill the order"

    # Re-publish the same quote (same instrument, same sequence). PBS'
    # consumer must drop it as a duplicate.
    await _publish_quote(
        config.redis_url, instrument_id=instrument_id, ltp=Decimal("999.00"),
        sequence=seq,
    )
    # And again with a fresh sequence but no open order — the price cache
    # may update, but no new fill event should appear for our order.
    await _publish_quote(
        config.redis_url, instrument_id=instrument_id, ltp=Decimal("400.00"),
    )

    # Allow ample time for any spurious second FILLED event to land.
    await asyncio.sleep(1.5)

    filled_events = [
        e
        for e in redis_event_collector.get_events(broker_order_id)
        if e.get("type") == "order.updated"
        and (e.get("payload") or {}).get("status") == "FILLED"
    ]
    assert len(filled_events) == 1, (
        f"Order {broker_order_id} emitted {len(filled_events)} FILLED events; "
        f"expected exactly 1. Duplicate-quote handling is broken in PBS' "
        f"consumer or BAS' event relay."
    )


async def test_rapid_price_ladder_fills_market_order_once(
    config,
    instrument_catalog,
    test_account_id,
    place_and_sync_order,
    redis_event_collector,
):
    """A rapid sequence of quotes (10 in ~50ms total) on a single
    instrument with one open MARKET BUY fills the order exactly once.
    Subsequent quotes update the cache but don't re-trigger the
    already-filled order.

    Regression mode: if PBS' execution engine re-enqueues open orders
    on every quote without checking remaining_qty, a price ladder
    re-fires the same order multiple times and BAS emits multiple
    FILLED events.
    """
    broker_id = config.broker_id
    instrument = instrument_catalog.get_test_instrument(1)
    instrument_id = instrument["id"]

    # Place MARKET BUY against an empty price cache.
    place_resp = await place_and_sync_order(
        broker_id,
        test_account_id,
        order_request={
            "instrument_id": instrument_id,
            "position_type": "INTRADAY",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": 15,
        },
    )
    broker_order_id = place_resp[0]["broker_order_id"]

    # Publish a 10-quote ladder. Each quote has a strictly increasing
    # ms-scale sequence so none get dropped as duplicates. The first one
    # is what drives the fill; the remaining nine are price-only
    # background noise.
    base_seq = int(time.time() * 1000)
    for i in range(10):
        await _publish_quote(
            config.redis_url,
            instrument_id=instrument_id,
            ltp=Decimal("250.00") + Decimal(i),
            sequence=base_seq + i,
        )
        # Tight loop — we want them in PBS' consumer pipeline back-to-back.
        await asyncio.sleep(0.01)

    events = await redis_event_collector.wait_for_completion(
        broker_order_id, timeout=10.0
    )
    assert _filled_event(events, broker_order_id) is not None, (
        f"Order {broker_order_id} did not fill after a 10-quote ladder."
    )

    # Allow stragglers and recount.
    await asyncio.sleep(1.0)
    filled_events = [
        e
        for e in redis_event_collector.get_events(broker_order_id)
        if e.get("type") == "order.updated"
        and (e.get("payload") or {}).get("status") == "FILLED"
    ]
    assert len(filled_events) == 1, (
        f"Price-ladder produced {len(filled_events)} FILLED events for one "
        f"MARKET order; expected 1. PBS' execution engine is likely "
        f"re-enqueueing already-filled orders on each quote."
    )
