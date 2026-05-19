"""
Integration test — MDS quote → PBS execution chain.

Pair under test: Redis Streams (`market.quote`) ←→ paper-broker-service.

What we verify here:
    1. A LIMIT BUY placed against an empty price cache stays PENDING (no
       quote yet → nothing to enqueue against). Publishing a quote on the
       same instrument then triggers PBS' on_price_update → fill.
    2. A LIMIT SELL works the same way on the SELL side.
    3. A quote on instrument B does NOT trigger fills on instrument A —
       PriceExecutionEngine.on_price_update keys on instrument_id when
       looking up open orders.

Important caveat (current PBS behaviour, May 2026):
    PBS' execution_engine.execute_fill does NOT enforce LIMIT trigger
    conditions. Once a quote arrives for an instrument with an open
    order, the worker fills it at the quote LTP regardless of whether
    LTP satisfies the BUY/SELL limit. Earlier versions of this test
    seeded an "off-limit" price expecting PBS to refuse, which was
    actually relying on a timing race (PBS' quote consumer hadn't
    caught up before the order was placed). When PBS gains LIMIT-
    trigger semantics, these tests can be tightened to assert
    avg_price ≤ limit (BUY) or ≥ limit (SELL).

Past regression to guard against:
    - PriceExecutionEngine.on_price_update could iterate over open orders
      across all instruments and use the latest LTP for the matching
      check, causing a quote on AAPL to fill a SBIN order. The
      instrument_id key on price_cache must be respected end-to-end.
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
    """Publish a quote on the real production stream."""
    client = await redis.from_url(redis_url, decode_responses=True)
    try:
        # Sequence number scale MUST match `mock_client.inject_fill`
        # (milliseconds since epoch) so PBS' per-instrument idempotency
        # cache stays monotonic across tests. Microsecond-scale numbers
        # would leave a value so large that subsequent ms-scale numbers
        # appear as duplicates and get silently dropped.
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


def _has_filled_event(events: list[dict]) -> bool:
    """Return True if any event in `events` is order.updated status=FILLED."""
    return any(
        e.get("type") == "order.updated"
        and (e.get("payload") or {}).get("status") == "FILLED"
        for e in events
    )


async def test_limit_buy_fills_after_quote_arrives_on_market_quote_v1(
    config,
    instrument_catalog,
    test_account_id,
    place_and_sync_order,
    redis_event_collector,
):
    """LIMIT BUY placed against an empty price cache stays PENDING until a
    quote for that instrument lands on `market.quote`. Once the quote
    arrives, PBS' PriceExecutionEngine enqueues the order and the worker
    fills it.

    The autouse cleanup_price_cache fixture guarantees the cache is empty
    before each test, so we never have to seed an off-limit price (which
    is racy with PBS' async quote consumer).
    """
    broker_id = config.broker_id
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]

    # Place LIMIT BUY first — cache is empty (autouse cleanup), so create_order
    # has no LTP to enqueue against; the order stays PENDING.
    place_response = await place_and_sync_order(
        broker_id,
        test_account_id,
        order_request={
            "instrument_id": instrument_id,
            "position_type": "INTRADAY",
            "side": "BUY",
            "order_type": "LIMIT",
            "qty": 100,
            "price": Decimal("550.00"),
        },
    )
    broker_order_id = place_response[0]["broker_order_id"]
    initial_status = place_response[0]["status"]
    assert initial_status in ("ACCEPTED", "PENDING"), (
        f"LIMIT BUY placed against empty cache should be PENDING/ACCEPTED. "
        f"Got status={initial_status!r}. If FILLED, PBS leaked a stale price "
        f"from a previous test — investigate cleanup_price_cache."
    )

    # Publish a quote. PBS' quote consumer must pick it up via the
    # pbs-quote-consumer group, update its price_cache, and trigger
    # the on_price_update path → enqueue → fill.
    await _publish_quote(
        config.redis_url, instrument_id=instrument_id, ltp=Decimal("549.00")
    )

    events = await redis_event_collector.wait_for_completion(
        broker_order_id, timeout=10.0
    )
    assert _has_filled_event(events), (
        f"LIMIT BUY on {instrument_id} never reached FILLED after a quote "
        f"on market.quote. Either PBS' quote consumer group is dead or "
        f"the on_price_update → execution_worker path is broken. Events: "
        f"{[(e.get('type'), (e.get('payload') or {}).get('status')) for e in events]}"
    )


async def test_limit_sell_fills_after_quote_arrives_on_market_quote_v1(
    config,
    instrument_catalog,
    test_account_id,
    place_and_sync_order,
    redis_event_collector,
):
    """Symmetric to the BUY case: a LIMIT SELL against an empty cache stays
    PENDING; once a quote arrives, the worker fills it. This exercises the
    SELL-side code path in execution_engine (debit_for_sell_fill,
    position aggregation with sell_qty/sell_avg).
    """
    broker_id = config.broker_id
    instrument = instrument_catalog.get_any_equity(2)[1]
    instrument_id = instrument["id"]

    place_response = await place_and_sync_order(
        broker_id,
        test_account_id,
        order_request={
            "instrument_id": instrument_id,
            "position_type": "INTRADAY",
            "side": "SELL",
            "order_type": "LIMIT",
            "qty": 100,
            "price": Decimal("600.00"),
        },
    )
    broker_order_id = place_response[0]["broker_order_id"]
    initial_status = place_response[0]["status"]
    assert initial_status in ("ACCEPTED", "PENDING"), (
        f"LIMIT SELL against empty cache should be PENDING/ACCEPTED. "
        f"Got status={initial_status!r}."
    )

    await _publish_quote(
        config.redis_url, instrument_id=instrument_id, ltp=Decimal("601.00")
    )

    events = await redis_event_collector.wait_for_completion(
        broker_order_id, timeout=10.0
    )
    assert _has_filled_event(events), (
        f"LIMIT SELL on {instrument_id} never reached FILLED after a quote "
        f"on market.quote."
    )


async def test_quote_on_other_instrument_does_not_fill_order(
    config,
    instrument_catalog,
    test_account_id,
    place_and_sync_order,
    redis_event_collector,
):
    """A quote on instrument B must NOT trigger a LIMIT order on instrument A.

    Guards against PriceExecutionEngine iterating across all open orders
    using a single global LTP. The price cache and matching engine must
    key on instrument_id.
    """
    broker_id = config.broker_id
    instruments = instrument_catalog.get_any_equity(2)
    instrument_a = instruments[0]["id"]
    instrument_b = instruments[1]["id"]
    assert instrument_a != instrument_b, "Test setup requires two distinct instruments"

    # Cache starts empty (autouse cleanup_price_cache). Place a LIMIT BUY
    # on A — stays PENDING because there is no LTP for A to enqueue against.
    place_response = await place_and_sync_order(
        broker_id,
        test_account_id,
        order_request={
            "instrument_id": instrument_a,
            "position_type": "INTRADAY",
            "side": "BUY",
            "order_type": "LIMIT",
            "qty": 100,
            "price": Decimal("550.00"),
        },
    )
    broker_order_id = place_response[0]["broker_order_id"]
    assert place_response[0]["status"] in ("ACCEPTED", "PENDING")

    # Publish a quote on instrument B. If PriceExecutionEngine.on_price_update
    # were broken — iterating over all open orders globally instead of
    # filtering by instrument_id — this quote would fill our A order. It must
    # not.
    await _publish_quote(
        config.redis_url, instrument_id=instrument_b, ltp=Decimal("400.00")
    )

    # Give PBS time to (incorrectly) react. We expect *no* FILLED event
    # within 3s — the order must remain pending.
    try:
        events = await redis_event_collector.wait_for_completion(
            broker_order_id, timeout=3.0
        )
        # If we got here, the order somehow reached a terminal state.
        # Filter to FILLED events.
        if _has_filled_event(events):
            pytest.fail(
                f"LIMIT BUY on {instrument_a} at 550 filled after a quote "
                f"on {instrument_b} at 400. PriceExecutionEngine is "
                f"matching across instruments — this is a serious bug."
            )
    except (asyncio.TimeoutError, TimeoutError):
        # Expected: no terminal event for this order.
        pass

    # Now publish the right quote on instrument A to confirm the order
    # is still valid and fillable.
    await _publish_quote(
        config.redis_url, instrument_id=instrument_a, ltp=Decimal("540.00")
    )
    events = await redis_event_collector.wait_for_completion(
        broker_order_id, timeout=10.0
    )
    assert _has_filled_event(events), (
        f"LIMIT BUY on {instrument_a} did not fill after the correct "
        f"instrument's quote dropped to 540. Either the order was "
        f"already cancelled/rejected, or the consumer is broken."
    )
