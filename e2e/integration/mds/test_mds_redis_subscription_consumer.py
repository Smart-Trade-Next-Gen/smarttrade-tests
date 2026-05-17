"""
Integration test — MDS subscription consumer on the real
`market.subscription.request.v1` stream.

Pair under test: market-data-service ←→ Redis Streams
(`market.subscription.request.v1`).

Contract:
    1. MDS owns the `mds-subscription-consumer` group on the real
       `market.subscription.request.v1` stream (see
       SubscriptionConsumer.STREAM / GROUP).
    2. When a SUBSCRIBE request lands on the stream, MDS' consumer
       picks it up and ACKs it (the group's pending count must not
       accumulate).
    3. MDS' consumer is request-id based (not sequence based), so two
       SUBSCRIBE requests for the same instrument with different
       request_ids are both consumed.

What this test does NOT cover (intentional):
    - End-to-end broker WS subscribe call. That requires seeded broker
      credentials, which the e2e env does not have. The
      SubscriptionConsumer wraps the broker call in a try/except
      anyway, so a credential-less env still ACKs the request — that's
      what this test asserts.

Past regression this test guards against:
    - The previous version of this file created its own throw-away
      stream (`market.subscription.request.v1.test.<uuid>`), did its own
      xadd, and read it back with its own group. It tested Redis, not
      MDS. The `mds-subscription-consumer` group could be missing in
      production and the previous test wouldn't notice.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid

import pytest
import redis.asyncio as redis


pytestmark = pytest.mark.asyncio


REAL_SUBSCRIPTION_STREAM = "market.subscription.request.v1"
MDS_CONSUMER_GROUP = "mds-subscription-consumer"


async def _publish_subscription_request(
    redis_url: str,
    *,
    broker_id: str,
    instrument_ids: list[str],
    action: str = "subscribe",
    user_id: str | None = None,
) -> tuple[str, str]:
    """Publish a subscribe/unsubscribe request the same way BAS / PBS do.

    Returns (message_id, request_id).
    """
    client = await redis.from_url(redis_url, decode_responses=True)
    try:
        request_id = str(uuid.uuid4())
        msg_id = await client.xadd(
            REAL_SUBSCRIPTION_STREAM,
            {
                "service_id": "e2e-test",
                "instance_id": f"e2e-{uuid.uuid4().hex[:8]}",
                "broker_id": broker_id,
                "action": action,
                "instrument_ids": json.dumps(instrument_ids),
                "request_id": request_id,
                "lease_ttl_seconds": "60",
                "user_id": user_id or "",
                "timestamp": str(int(time.time() * 1000)),
            },
        )
        return msg_id, request_id
    finally:
        await client.close()


async def test_mds_consumer_group_is_attached_to_real_subscription_stream(config):
    """MDS owns the `mds-subscription-consumer` group on the production
    subscription request stream. Without it, every backend
    (BAS / PBS / portfolio) that publishes subscription requests
    receives no response.
    """
    client = await redis.from_url(config.redis_url, decode_responses=True)
    try:
        # The stream may not exist at all if no service has subscribed
        # yet. In that case the group can't exist either — and that is a
        # legitimate failure: MDS is supposed to create the stream and
        # group at startup (BaseStreamConsumer.start does mkstream=True).
        try:
            groups = await client.xinfo_groups(REAL_SUBSCRIPTION_STREAM)
        except redis.ResponseError as e:
            pytest.fail(
                f"`{REAL_SUBSCRIPTION_STREAM}` does not exist or has no "
                f"groups. MDS' SubscriptionConsumer is not attached. "
                f"Redis says: {e}"
            )
    finally:
        await client.close()
    group_names = {g.get("name") for g in groups}
    assert MDS_CONSUMER_GROUP in group_names, (
        f"`{MDS_CONSUMER_GROUP}` is not attached to "
        f"`{REAL_SUBSCRIPTION_STREAM}`. Existing groups: "
        f"{sorted(group_names)}. Without this group, backend "
        f"subscription requests go unprocessed."
    )


async def test_mds_consumes_subscribe_request_and_does_not_accumulate_pending(
    config,
    instrument_catalog,
    test_user_id,
):
    """Publish a SUBSCRIBE request and assert MDS' consumer ACKs it
    (its group's pending count goes back to baseline within a few
    seconds). This is the same path BAS / PBS use to ask MDS to start
    streaming an instrument.

    Even if the broker subscribe call itself fails (credentials missing
    in the e2e env), the consumer still processes the message and
    XACKs it — the SubscriptionConsumer wraps broker calls in
    try/except for exactly this reason. A growing pending count would
    indicate the consumer is dead or broken.
    """
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]

    client = await redis.from_url(config.redis_url, decode_responses=True)
    try:
        # Baseline: how many entries are currently delivered to the MDS
        # group? We'll wait until that advances past our publish.
        groups = await client.xinfo_groups(REAL_SUBSCRIPTION_STREAM)
        mds_group = next(
            (g for g in groups if g.get("name") == MDS_CONSUMER_GROUP), None
        )
        assert mds_group is not None, (
            f"Cannot run consumption test: {MDS_CONSUMER_GROUP} not "
            f"attached to `{REAL_SUBSCRIPTION_STREAM}`."
        )
        baseline_pending = int(mds_group.get("pending") or 0)
        baseline_entries_read = int(mds_group.get("entries-read") or 0)
    finally:
        await client.close()

    msg_id, request_id = await _publish_subscription_request(
        config.redis_url,
        broker_id=config.broker_id,
        instrument_ids=[instrument_id],
        action="subscribe",
        user_id=test_user_id,
    )

    # Wait for MDS' consumer to advance entries-read past baseline AND
    # not leave the message permanently pending. 5s should be plenty —
    # MDS' BLOCK_MS is 100, and the consumer ACKs immediately after
    # process_message returns.
    deadline = asyncio.get_event_loop().time() + 5.0
    client = await redis.from_url(config.redis_url, decode_responses=True)
    try:
        while asyncio.get_event_loop().time() < deadline:
            groups = await client.xinfo_groups(REAL_SUBSCRIPTION_STREAM)
            mds_group = next(
                (g for g in groups if g.get("name") == MDS_CONSUMER_GROUP),
                None,
            )
            if mds_group is None:
                pytest.fail(
                    f"{MDS_CONSUMER_GROUP} disappeared during the test."
                )
            entries_read = int(mds_group.get("entries-read") or 0)
            pending = int(mds_group.get("pending") or 0)
            if entries_read > baseline_entries_read and pending <= baseline_pending:
                return
            await asyncio.sleep(0.2)
    finally:
        await client.close()

    pytest.fail(
        f"MDS' {MDS_CONSUMER_GROUP} did not consume the request "
        f"request_id={request_id} (msg_id={msg_id}) within 5s. "
        f"baseline entries_read={baseline_entries_read} pending="
        f"{baseline_pending}; current entries_read={entries_read} "
        f"pending={pending}."
    )


async def test_mds_consumes_subscribe_then_unsubscribe(
    config,
    instrument_catalog,
    test_user_id,
):
    """SubscribeConsumer must process both subscribe and unsubscribe
    actions in sequence; pending must drain in both directions.

    Guards against an action-routing regression where one of the two
    paths leaks pending entries or crashes the consumer loop.
    """
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]

    client = await redis.from_url(config.redis_url, decode_responses=True)
    try:
        groups = await client.xinfo_groups(REAL_SUBSCRIPTION_STREAM)
        mds_group = next(
            (g for g in groups if g.get("name") == MDS_CONSUMER_GROUP), None
        )
        assert mds_group is not None
        baseline_pending = int(mds_group.get("pending") or 0)
        baseline_entries_read = int(mds_group.get("entries-read") or 0)
    finally:
        await client.close()

    await _publish_subscription_request(
        config.redis_url,
        broker_id=config.broker_id,
        instrument_ids=[instrument_id],
        action="subscribe",
        user_id=test_user_id,
    )
    await _publish_subscription_request(
        config.redis_url,
        broker_id=config.broker_id,
        instrument_ids=[instrument_id],
        action="unsubscribe",
        user_id=test_user_id,
    )

    deadline = asyncio.get_event_loop().time() + 5.0
    client = await redis.from_url(config.redis_url, decode_responses=True)
    try:
        while asyncio.get_event_loop().time() < deadline:
            groups = await client.xinfo_groups(REAL_SUBSCRIPTION_STREAM)
            mds_group = next(
                (g for g in groups if g.get("name") == MDS_CONSUMER_GROUP),
                None,
            )
            entries_read = int(mds_group.get("entries-read") or 0)
            pending = int(mds_group.get("pending") or 0)
            if (
                entries_read >= baseline_entries_read + 2
                and pending <= baseline_pending
            ):
                return
            await asyncio.sleep(0.2)
    finally:
        await client.close()

    pytest.fail(
        f"MDS did not drain subscribe+unsubscribe within 5s. "
        f"baseline entries_read={baseline_entries_read} pending="
        f"{baseline_pending}; current entries_read={entries_read} "
        f"pending={pending}."
    )
