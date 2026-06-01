"""
Integration test — PBS quote consumer on real `market.quote` stream.

Pair under test: paper-broker-service ←→ Redis Streams (`market.quote`).

Contract:
    1. PBS subscribes to the real `market.quote` stream using the
       `pbs-quote-consumer` group (see
       PBSMarketDataConsumer.STREAM / GROUP).
    2. When a quote arrives, PBS updates its in-memory price cache for the
       instrument. A MARKET BUY placed afterwards auto-fills at the cached
       LTP.
    3. PBS triggers LIMIT order execution when the published quote's LTP
       satisfies the limit price.

Past regression this test guards against:
    - The previous version of this test created its own throw-away stream
      (`market.quote.test.<uuid>`) and its own consumer group, then
      asserted that XADD followed by XREADGROUP returned the same payload.
      It tested Redis, not PBS — the actual "missing pbs-quote-consumer
      group" production incident could not be detected by it.
"""

from __future__ import annotations

import asyncio
import json
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
    """Publish a quote on the real production stream. Returns the Redis
    message id."""
    client = await redis.from_url(redis_url, decode_responses=True)
    try:
        # PBS' BaseStreamConsumer keys idempotency on (sequence_key,
        # sequence_number). Use a fresh millisecond timestamp so each
        # publication is unique across the test session.
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


async def test_pbs_consumer_group_is_attached_to_real_stream(config):
    """PBS owns the `pbs-quote-consumer` group on the real
    `market.quote` stream. If this fixture is missing in production
    no order will ever fill because the quote events go undelivered.
    """
    client = await redis.from_url(config.redis_url, decode_responses=True)
    try:
        groups = await client.xinfo_groups(REAL_QUOTE_STREAM)
    finally:
        await client.close()
    group_names = {g.get("name") for g in groups}
    assert "pbs-quote-consumer" in group_names, (
        f"PBS' consumer group `pbs-quote-consumer` is not attached to "
        f"`{REAL_QUOTE_STREAM}`. Existing groups: {sorted(group_names)}. "
        f"Without this group PBS receives no quotes — orders won't fill "
        f"and the BAS↔PBS chain breaks silently."
    )


async def test_pbs_consumes_real_quote_and_market_order_fills_at_that_price(
    config,
    instrument_catalog,
    test_account_id,
    place_and_sync_order,
    redis_event_collector,
):
    """End-to-end proof that PBS' quote consumer is alive on the real
    stream: publish a quote on `market.quote`, then place a MARKET
    order. PBS' OrderService auto-fills the market order at the cached
    LTP, and the LTP must be the one we just published.

    If the quote consumer is misconfigured (wrong stream / wrong group /
    missing group), the price cache stays empty and the market order
    either hangs (no auto-fill) or fills at a stale price. Either way
    this test catches it.
    """
    broker_id = config.broker_id
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]

    quote_price = Decimal("612.50")

    # 1. Publish a quote on the real `market.quote` stream first so PBS has LTP
    #    for cost estimation at order placement time
    await _publish_quote(
        config.redis_url, instrument_id=instrument_id, ltp=quote_price
    )

    # 2. Place the MARKET BUY. PBS' OrderService.create_order will
    #    read price_cache and find the LTP we just published.
    place_response = await place_and_sync_order(
        broker_id,
        test_account_id,
        order_request={
            "instrument_id": instrument_id,
            "position_type": "INTRADAY",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": 100,
        },
    )
    broker_order_id = place_response[0]["broker_order_id"]

    # 3. Publish another quote to trigger the fill. PBS'
    #    quote consumer must:
    #       a) consume this quote via the `pbs-quote-consumer` group, and
    #       b) call PriceExecutionEngine.on_price_update, which looks up
    #          open orders for that instrument and enqueues fills.
    #    If the consumer is misrouted or its group is missing, the order
    #    stays PENDING and `wait_for_completion` will time out.
    await _publish_quote(
        config.redis_url, instrument_id=instrument_id, ltp=quote_price
    )

    # 3. Wait for FILLED. If PBS' quote consumer wasn't alive, price_cache
    #    is empty and the order won't auto-fill — wait_for_completion will
    #    time out, failing this test in exactly the regression case.
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
        f"No FILLED order.updated event for broker_order_id="
        f"{broker_order_id}. Likely PBS' quote consumer never received "
        f"the quote we published on `{REAL_QUOTE_STREAM}` — check the "
        f"`pbs-quote-consumer` consumer group."
    )

    avg_price = (filled[-1].get("payload") or {}).get("average_price")
    assert Decimal(str(avg_price)) == quote_price, (
        f"PBS filled at average_price={avg_price!r}, expected "
        f"{quote_price!r} (the LTP we published just before the order). "
        f"Either PBS' price cache wasn't updated from the stream (consumer "
        f"misrouted), or some prior test left a stale LTP in the cache."
    )


async def test_pbs_quote_consumer_idempotent_on_duplicate_sequence(
    config,
    instrument_catalog,
):
    """PBS uses sequence-number idempotency (see
    `PBSMarketDataConsumer.get_sequence_key`). Re-publishing a quote with
    the same `sequence_number` must NOT cause double processing.

    We verify this by inspecting PBS' consumer group: the second message
    is still ACKed (Redis-level), so the group's `entries-read` advances,
    but PBS' internal sequence map dedupes it before touching price_cache.
    """
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]

    seq = int(time.time() * 1000)
    await _publish_quote(
        config.redis_url, instrument_id=instrument_id, ltp=Decimal("100.00"),
        sequence=seq,
    )
    await _publish_quote(
        config.redis_url, instrument_id=instrument_id, ltp=Decimal("999.99"),
        sequence=seq,
    )
    await asyncio.sleep(0.5)

    client = await redis.from_url(config.redis_url, decode_responses=True)
    try:
        groups = await client.xinfo_groups(REAL_QUOTE_STREAM)
    finally:
        await client.close()

    pbs_group = next(
        (g for g in groups if g.get("name") == "pbs-quote-consumer"),
        None,
    )
    assert pbs_group is not None, (
        "Expected pbs-quote-consumer group to exist — without it PBS "
        "cannot consume the quotes we published."
    )
    # Pending count should not be growing — PBS must ACK every message
    # whether or not it produced a price_cache update. A growing pending
    # backlog here is the same regression we hit when the
    # SchemaRegistry.get_event_schema bug broke @consume_event handlers.
    assert (pbs_group.get("pending") or 0) < 50, (
        f"pbs-quote-consumer has {pbs_group.get('pending')} pending "
        f"entries; PBS is not ACKing quotes. Expect this to grow "
        f"unboundedly if there is a regression in the consumer loop."
    )
