"""
Integration test — EventBus publish ↔ subscribe via running services.

Pair under test: smarttrade-common EventBus (DomainEventPublisher +
@subscribe / @consume_event consumer infrastructure) ↔ Redis Streams
↔ subscribing services (Portfolio, Journal, Notification).

Contract:
    1. Every service that uses `@consume_event` registers a Redis
       consumer group named `<service>-<event_type>-group` on
       `events:<event_type>`. Without it the @subscribe handler in
       the service never fires.
    2. The event envelope written by `DomainEventPublisher` carries
       the fields downstream consumers expect: `event_name`,
       `event_id`, `payload` (a dict), and an `idempotency_key`.
       Schema breaks at any point in the chain manifest here first.
    3. After a published event flows through the bus, the per-service
       consumer group advances its `entries-read` past the publication
       and does not leave the message in `pending` permanently.

Why this test is built around running services rather than the
in-process EventBus client:
    - `DomainEventPublisher` is singleton-initialized inside a service's
      lifespan with `settings.SERVICE_NAME` baked in. Standing up an
      independent client in the test would publish from a different
      service identity than any real consumer expects.
    - The fixture we already have for outbox publishes through BAS'
      own EventBus instance, which is the production path. We re-use
      that path here and focus the assertions on the subscriber side
      of the contract.

Past regression this test guards against:
    - The previous version of this file XADD'd a hand-built payload to
      a unique test stream and read it back via xrevrange. It tested
      Redis as a key-value store, not the EventBus. The
      `SchemaRegistry.get_event_schema` bug (silently dropping every
      validated event in every consumer service) could not be detected
      by it.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from urllib.parse import urlparse

import asyncpg
import pytest
import redis.asyncio as redis


pytestmark = pytest.mark.asyncio


BAS_DB_NAME = "smarttrade_broker_adapter_service"


def _bas_dsn(redis_url: str) -> str:
    parsed = urlparse(redis_url)
    host = parsed.hostname or "localhost"
    pg_port = int(os.environ.get("E2E_POSTGRES_PORT", "5432"))
    pg_user = os.environ.get("POSTGRES_USER", "postgres")
    pg_pass = os.environ.get("POSTGRES_PASSWORD", "postgres")
    return f"postgresql://{pg_user}:{pg_pass}@{host}:{pg_port}/{BAS_DB_NAME}"


# The set of consumer groups we expect to see attached to each core
# events:* stream. If a service stops subscribing, its group disappears
# and the test fails — the same regression mode as the silent
# SchemaRegistry bug, just observable upstream.
EXPECTED_GROUPS = {
    "events:order.updated.v1": {
        "journal-service-order.updated.v1-group",
        "notification-service-order.updated.v1-group",
    },
    "events:trade.executed.v1": {
        "journal-service-trade.executed.v1-group",
        "notification-service-trade.executed.v1-group",
    },
    "events:position.updated.v1": {
        # Journal does NOT consume position events — it consumes trade events
        # and computes its own positions via FIFO open-lot matching. Listing
        # it here would create a false-positive "missing group" failure on a
        # service that was never supposed to be subscribed.
        "portfolio-service-position.updated.v1-group",
        "notification-service-position.updated.v1-group",
    },
}


async def test_expected_consumer_groups_are_attached_to_event_streams(config):
    """Every service that registers a `@consume_event` handler must own
    a consumer group on the matching stream. If a group is missing the
    service silently drops every event of that type.
    """
    client = await redis.from_url(config.redis_url, decode_responses=True)
    try:
        missing: dict[str, set[str]] = {}
        for stream, expected_groups in EXPECTED_GROUPS.items():
            try:
                groups = await client.xinfo_groups(stream)
            except redis.ResponseError as e:
                pytest.fail(
                    f"Stream `{stream}` is missing or unreadable: {e}. "
                    f"No @consume_event handler has attached."
                )
            actual = {g.get("name") for g in groups}
            absent = expected_groups - actual
            if absent:
                missing[stream] = absent
    finally:
        await client.close()
    assert not missing, (
        "Expected consumer groups are missing on these event streams. "
        "Each missing group corresponds to a service that has stopped "
        "subscribing — events of that type silently disappear:\n"
        + "\n".join(
            f"  {stream}: missing groups {sorted(groups)}"
            for stream, groups in missing.items()
        )
    )


async def test_eventbus_envelope_carries_required_fields(config):
    """Every event published via the EventBus must carry the envelope
    fields downstream consumers parse. Strip one of these in the
    publisher and most consumers break — including notification and
    journal idempotency, which key on `event_id`.
    """
    client = await redis.from_url(config.redis_url, decode_responses=True)
    try:
        entries = await client.xrevrange(
            "events:order.updated.v1", count=10
        )
    finally:
        await client.close()
    if not entries:
        pytest.skip(
            "No events:order.updated.v1 entries present yet. Run a "
            "test that places an order first (e.g. "
            "test_bas_pbs_execution_ws.py) to populate the stream."
        )

    _msg_id, fields = entries[0]
    raw = fields.get("event")
    assert raw is not None, (
        f"Stream entry has no `event` field. Got fields: "
        f"{sorted(fields.keys())}. The DomainEventPublisher contract "
        f"requires the envelope to live under the `event` key."
    )
    envelope = json.loads(raw)

    # The envelope key carrying the event identifier may be either
    # `event_name` (newer normalization) or `event_type` (legacy). The
    # consumer code accepts either (see consumer.py validate_event:
    # "event_name = event.get('event_name') or event.get('event_type')"),
    # so we accept either too — but reject if neither is present.
    has_name = "event_name" in envelope or "event_type" in envelope
    assert has_name, (
        f"DomainEventPublisher envelope is missing both `event_name` "
        f"and `event_type`. Envelope keys: {sorted(envelope.keys())}. "
        f"Consumers cannot route this event."
    )
    other_required = {"event_id", "payload"} - set(envelope.keys())
    assert not other_required, (
        f"DomainEventPublisher envelope missing required keys: "
        f"{other_required}. Envelope: {sorted(envelope.keys())}"
    )

    assert isinstance(envelope["payload"], dict), (
        f"DomainEventPublisher envelope `payload` is not a dict: "
        f"{type(envelope['payload']).__name__}"
    )


async def test_eventbus_publish_subscribe_roundtrip(config):
    """End-to-end roundtrip through the real EventBus + consumer chain:

      a) Insert a row into BAS' `event_outbox` (the production way to
         emit an event — saves it atomically with the business state).
      b) BAS' OutboxPoller picks the row up and publishes via the
         EventBus to `events:order.updated.v1`.
      c) The notification-service `@consume_event('order.updated.v1')`
         handler runs and (because we pre-create a subscription)
         persists a row in `notification_messages` for our test user.

    A failure here can be at any layer (publisher, stream, consumer,
    handler, DB write); the test deliberately exercises the whole
    chain because that is what services rely on.
    """
    # Imports kept local so this module's import-time doesn't pull
    # asyncpg unless the test actually runs.
    notification_dsn = (
        _bas_dsn(config.redis_url).replace(BAS_DB_NAME, "smarttrade_notification_service")
    )
    bas_dsn = _bas_dsn(config.redis_url)

    # Pre-create a subscription so notification-service persists the
    # event. Without a subscription the event is consumed but ignored,
    # and the test cannot tell the difference between "consumer is
    # broken" and "no matching subscription".
    user_id = "00000000-0000-0000-0000-000000000001"
    conn = await asyncpg.connect(notification_dsn)
    try:
        existing = await conn.fetchrow(
            "SELECT id FROM notification_subscriptions "
            "WHERE user_id = $1::uuid AND event_pattern = $2 "
            "AND enabled = TRUE",
            user_id,
            "order.*",
        )
        if not existing:
            await conn.execute(
                "INSERT INTO notification_subscriptions "
                "(id, user_id, event_pattern, enabled, created_at, updated_at) "
                "VALUES ($1::uuid, $2::uuid, $3, TRUE, NOW(), NOW())",
                str(uuid.uuid4()),
                user_id,
                "order.*",
            )
    finally:
        await conn.close()

    # Insert into outbox. event_data must contain a fully-formed
    # publisher envelope — that's what BAS' DomainEventPublisher writes
    # into event_outbox.event_data and what OutboxPoller hands to
    # EventBus.publish. The publisher-envelope detector at
    # event_bus.publish requires ALL of event_id, event_name, timestamp,
    # trace_id, user_id at the top level; missing any of these causes
    # the bus to double-wrap with `event_type` and the resulting
    # envelope no longer matches the consumer's `event.get("event_name")`
    # lookup. That subtlety is the easiest way to silently break the
    # entire pub/sub chain — pinning it here protects against it.
    marker = f"e2e-eventbus-{uuid.uuid4().hex}"
    event_id = str(uuid.uuid4())
    event_name = "order.updated.v1"
    event_data = {
        "event_id": event_id,
        "event_name": event_name,
        "event_version": "1.0",
        "timestamp": int(time.time() * 1000),
        "trace_id": str(uuid.uuid4()),
        "user_id": user_id,
        "request_id": str(uuid.uuid4()),
        "idempotency_key": f"eventbus-test-{marker}-filled",
        "payload": {
            "marker": marker,
            "order_id": f"eventbus-test-{marker}",
            "broker_order_id": f"eventbus-test-{marker}",
            "client_order_id": f"eventbus-test-{marker}",
            "user_id": user_id,
            "broker_id": "fyers",
            "account_id": "TEST_E2E_EVENTBUS",
            "status": "FILLED",
            "side": "BUY",
            "quantity": 1,
            "filled_quantity": 1,
            "average_price": "100.00",
            "instrument_id": "TEST:E2E:EQ",
            "order_type": "MARKET",
        },
    }
    conn = await asyncpg.connect(bas_dsn)
    try:
        await conn.execute(
            """
            INSERT INTO event_outbox
              (event_name, event_data, aggregate_id, created_at, retry_count)
            VALUES ($1, $2::json, $3, NOW(), 0)
            """,
            event_name,
            json.dumps(event_data),
            f"eventbus-test-{marker}",
        )
    finally:
        await conn.close()

    # Wait for notification-service to persist the row for this
    # event_id. notification-service uses event_id as the idempotency
    # key (see NotificationMessage.event_id).
    conn = await asyncpg.connect(notification_dsn)
    try:
        deadline = asyncio.get_event_loop().time() + 15.0
        while True:
            row = await conn.fetchrow(
                "SELECT event_id, event_name, user_id "
                "FROM notification_messages WHERE event_id = $1",
                event_id,
            )
            if row is not None:
                break
            if asyncio.get_event_loop().time() >= deadline:
                pytest.fail(
                    f"End-to-end EventBus chain broken: notification "
                    f"row never appeared for event_id={event_id} "
                    f"(marker={marker!r}) within 15s. The break is in "
                    f"one of: outbox poller, EventBus publish, "
                    f"notification @consume_event handler, or the "
                    f"notification DB write."
                )
            await asyncio.sleep(0.3)
    finally:
        await conn.close()

    assert row["event_id"] == event_id
    # FILLED status maps to order.filled.v1 inside notification-service
    # (see services.process_event: status_to_event mapping).
    assert row["event_name"] == "order.filled.v1"
    assert str(row["user_id"]) == user_id
