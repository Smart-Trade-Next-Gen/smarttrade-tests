"""
Integration test — MDS quote → PBS execution chain (LIMIT orders + isolation).

Pair under test: Redis Streams (`market.quote.v1`) ←→ paper-broker-service.

Contract:
    1. A LIMIT BUY at price X stays PENDING while the quote LTP is above X
       and only fills when a quote LTP <= X arrives on `market.quote.v1`.
    2. A LIMIT SELL at price X stays PENDING while the quote LTP is below X
       and only fills when a quote LTP >= X arrives.
    3. Quotes for instrument A do NOT trigger orders on instrument B —
       the price cache and execution engine must key on instrument_id.

This test complements `test_pbs_redis_quote_consumer.py` (which proves the
consumer group is alive and a MARKET order fills at the published quote
LTP). Here we verify the *price-matching* behaviour: LIMIT triggers, NOT
trigger-on-bad-price, and instrument-level isolation.

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


REAL_QUOTE_STREAM = "market.quote.v1"


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
    """Return True if any event in `events` is order.updated.v1 status=FILLED."""
    return any(
        e.get("type") == "order.updated.v1"
        and (e.get("payload") or {}).get("status") == "FILLED"
        for e in events
    )


async def test_limit_buy_triggers_when_quote_drops_to_limit(
    config,
    instrument_catalog,
    test_account_id,
    place_and_sync_order,
    redis_event_collector,
):
    """LIMIT BUY at price X fills only when an LTP <= X is published.

    1. Publish a quote at LTP=600 (above the limit price 550)
    2. Place a LIMIT BUY at 550
    3. Verify order is PENDING/ACCEPTED, not FILLED
    4. Publish a quote at LTP=549 (at/below the limit)
    5. Verify order transitions to FILLED with average_price == 549
    """
    broker_id = config.broker_id
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]

    # 1. Set price above the limit so the order does not auto-fill on placement.
    await _publish_quote(
        config.redis_url, instrument_id=instrument_id, ltp=Decimal("600.00")
    )
    await asyncio.sleep(0.3)  # let PBS consume + update price_cache

    # 2. Place LIMIT BUY at 550 — should be PENDING/ACCEPTED, not FILLED.
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
            "ltp": Decimal("600.00"),
        },
    )
    broker_order_id = place_response[0]["broker_order_id"]
    initial_status = place_response[0]["status"]
    assert initial_status in ("ACCEPTED", "PENDING"), (
        f"LIMIT BUY at 550 with LTP=600 should not auto-fill. "
        f"Got status={initial_status!r}."
    )

    # 3. Quote drops to 549 — now the limit is satisfied.
    await _publish_quote(
        config.redis_url, instrument_id=instrument_id, ltp=Decimal("549.00")
    )

    # 4. Wait for FILLED.
    events = await redis_event_collector.wait_for_completion(
        broker_order_id, timeout=10.0
    )
    assert _has_filled_event(events), (
        f"LIMIT BUY at 550 did not fill after quote dropped to 549. "
        f"Events: {[(e.get('type'), (e.get('payload') or {}).get('status')) for e in events]}"
    )

    # 5. Fill price must be at/below the limit. PBS typically fills at the
    #    triggering quote LTP (549), not at the limit price (550).
    filled = [
        e
        for e in events
        if e.get("type") == "order.updated.v1"
        and (e.get("payload") or {}).get("status") == "FILLED"
    ]
    avg_price = Decimal(str((filled[-1]["payload"]).get("average_price")))
    assert avg_price <= Decimal("550.00"), (
        f"LIMIT BUY at 550 filled at {avg_price} — fill price must be "
        f"<= limit price for a BUY."
    )


async def test_limit_sell_triggers_when_quote_rises_to_limit(
    config,
    instrument_catalog,
    test_account_id,
    place_and_sync_order,
    redis_event_collector,
):
    """LIMIT SELL at price X fills only when an LTP >= X is published.

    Symmetric to the LIMIT BUY test: SELL waits for the price to rise to
    or above the limit before filling.
    """
    broker_id = config.broker_id
    instrument = instrument_catalog.get_any_equity(2)[1]
    instrument_id = instrument["id"]

    # Seed a low price so the SELL does not auto-fill on placement.
    await _publish_quote(
        config.redis_url, instrument_id=instrument_id, ltp=Decimal("500.00")
    )
    await asyncio.sleep(0.3)

    # LIMIT SELL at 600 with LTP=500 — should be PENDING/ACCEPTED, not FILLED.
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
            "ltp": Decimal("500.00"),
        },
    )
    broker_order_id = place_response[0]["broker_order_id"]
    initial_status = place_response[0]["status"]
    assert initial_status in ("ACCEPTED", "PENDING"), (
        f"LIMIT SELL at 600 with LTP=500 should not auto-fill. "
        f"Got status={initial_status!r}."
    )

    # Quote rises to 601 — limit is satisfied.
    await _publish_quote(
        config.redis_url, instrument_id=instrument_id, ltp=Decimal("601.00")
    )

    events = await redis_event_collector.wait_for_completion(
        broker_order_id, timeout=10.0
    )
    assert _has_filled_event(events), (
        f"LIMIT SELL at 600 did not fill after quote rose to 601. "
        f"Events: {[(e.get('type'), (e.get('payload') or {}).get('status')) for e in events]}"
    )

    filled = [
        e
        for e in events
        if e.get("type") == "order.updated.v1"
        and (e.get("payload") or {}).get("status") == "FILLED"
    ]
    avg_price = Decimal(str((filled[-1]["payload"]).get("average_price")))
    assert avg_price >= Decimal("600.00"), (
        f"LIMIT SELL at 600 filled at {avg_price} — fill price must be "
        f">= limit price for a SELL."
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

    # Seed both instruments with high prices so the LIMIT BUY on A is pending.
    await _publish_quote(
        config.redis_url, instrument_id=instrument_a, ltp=Decimal("600.00")
    )
    await _publish_quote(
        config.redis_url, instrument_id=instrument_b, ltp=Decimal("600.00")
    )
    await asyncio.sleep(0.3)

    # LIMIT BUY on A at 550 — pending.
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
            "ltp": Decimal("600.00"),
        },
    )
    broker_order_id = place_response[0]["broker_order_id"]
    assert place_response[0]["status"] in ("ACCEPTED", "PENDING")

    # Publish a quote on instrument B that *would* trigger the order if
    # the engine were broken (LTP=400 satisfies the 550 BUY limit).
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
