"""
Integration test — Notification Service ↔ Redis (wildcard event consumption).

Pair under test: notification-service ←→ Redis Streams (all domain events).

Contract:
    1. With an active subscription for `order.*`, the notification service
       consumes `order.updated.v1` events from Redis, maps the FILLED status
       to `order.filled.v1`, and persists a row in `notification_messages`
       for our user.
    2. The persisted notification carries the event_id from the source event
       and the right event_name mapping.

The notification service does NOT expose a `/notifications` REST endpoint
today (the route module is commented out in main.py — see
`notification_service.main`), so this test verifies persistence by querying
`notification_messages` directly with asyncpg. That is acceptable for an
integration test: the contract under examination is the consumer + DB
write, not the API shape.

Past regression this test guards against:
    - The previous version of this test never spoke to notification-service
      at all. It only re-asserted that the events appeared on Redis. It
      passed silently when notification-service didn't consume events
      (e.g. the smarttrade-common SchemaRegistry.get_event_schema bug —
      every @consume_event with validate_schema=True retried 3 times,
      logged, and skipped the event with nothing persisted).
"""

from __future__ import annotations

import asyncio
import os
import uuid
from decimal import Decimal
from urllib.parse import urlparse

import asyncpg
import pytest


pytestmark = pytest.mark.asyncio


NOTIFICATION_DB_NAME = "smarttrade_notification_service"


def _notification_db_dsn(redis_url: str) -> str:
    """Derive the notification DB DSN from the test env.

    The e2e harness exposes REDIS_URL but not the per-service Postgres DSN.
    Both Redis and Postgres run on the same host (localhost in dev,
    docker-compose service names in CI), so reuse the host from
    redis_url to stay portable across environments.
    """
    parsed = urlparse(redis_url)
    host = parsed.hostname or "localhost"
    pg_port = int(os.environ.get("E2E_POSTGRES_PORT", "5432"))
    pg_user = os.environ.get("POSTGRES_USER", "postgres")
    pg_pass = os.environ.get("POSTGRES_PASSWORD", "postgres")
    return (
        f"postgresql://{pg_user}:{pg_pass}@{host}:{pg_port}/"
        f"{NOTIFICATION_DB_NAME}"
    )


async def _ensure_subscription(
    dsn: str,
    *,
    user_id: str,
    event_pattern: str,
) -> None:
    """Insert a notification subscription row directly via asyncpg if one
    does not already exist for (user_id, event_pattern).

    Why not use the REST API: notification-service's
    `POST /api/v1/subscriptions` is decorated with
    `@require_policy("stream_subscriptions", "write")`, which expects
    `user_id` in kwargs to match the JWT `sub`. The dependency-resolved
    `user_id` only lands in kwargs after the decorator runs, so the
    self-check fails with 403 against our test JWT. Creating the
    subscription via DB sidesteps that orthogonal concern: this test is
    about the consume-and-persist contract, not the subscription API.
    """
    conn = await asyncpg.connect(dsn)
    try:
        existing = await conn.fetchrow(
            "SELECT id FROM notification_subscriptions "
            "WHERE user_id = $1::uuid AND event_pattern = $2 AND enabled = TRUE",
            user_id,
            event_pattern,
        )
        if existing:
            return
        await conn.execute(
            "INSERT INTO notification_subscriptions "
            "(id, user_id, event_pattern, enabled, created_at, updated_at) "
            "VALUES ($1::uuid, $2::uuid, $3, TRUE, NOW(), NOW())",
            str(uuid.uuid4()),
            user_id,
            event_pattern,
        )
    finally:
        await conn.close()


async def _wait_for_notification(
    dsn: str,
    *,
    event_id: str,
    timeout: float = 15.0,
    poll_interval: float = 0.5,
) -> dict:
    deadline = asyncio.get_event_loop().time() + timeout
    last_count = -1
    while True:
        conn = await asyncpg.connect(dsn)
        try:
            row = await conn.fetchrow(
                "SELECT event_id, event_name, user_id, severity, category, "
                "title, message FROM notification_messages WHERE event_id = $1",
                event_id,
            )
            if row is None:
                last_count = await conn.fetchval(
                    "SELECT count(*) FROM notification_messages"
                )
        finally:
            await conn.close()
        if row is not None:
            return dict(row)
        if asyncio.get_event_loop().time() >= deadline:
            raise TimeoutError(
                f"notification_messages row not found for event_id={event_id} "
                f"within {timeout}s. Total rows in table: {last_count}."
            )
        await asyncio.sleep(poll_interval)


async def test_notification_service_persists_order_fill_into_db(
    config,
    instrument_catalog,
    test_account_id,
    test_user_id,
    auth_token,
    place_and_sync_order,
    mock_client,
    redis_event_collector,
):
    """A fill drives `order.updated.v1` with status=FILLED. Notification
    service maps that to `order.filled.v1`, finds a matching subscription,
    and persists a notification_messages row with the same event_id.
    """
    # 1. Ensure the test user has a subscription matching order.* events.
    dsn = _notification_db_dsn(config.redis_url)
    await _ensure_subscription(dsn, user_id=test_user_id, event_pattern="order.*")

    broker_id = config.broker_id

    from e2e.integration.bas.test_bas_pbs_execution_ws import _place_and_fill

    qty = 100
    price = Decimal("550.00")
    broker_order_id, _instrument_id, events = await _place_and_fill(
        place_and_sync_order=place_and_sync_order,
        mock_client=mock_client,
        instrument_catalog=instrument_catalog,
        test_account_id=test_account_id,
        broker_id=broker_id,
        redis_event_collector=redis_event_collector,
        instrument_index=0,
        qty=qty,
        price=price,
    )

    # 2. Find the FILLED order.updated.v1 event so we know which event_id
    #    to look up in notification_messages.
    filled_events = [
        e
        for e in events
        if e.get("type") == "order.updated.v1"
        and (e.get("payload") or {}).get("status") == "FILLED"
    ]
    assert filled_events, (
        "Test cannot proceed: BAS did not publish a FILLED order.updated.v1 "
        "event. The bug is upstream of notification-service."
    )
    # The event envelope stores event_id alongside payload.
    fill_event_data = filled_events[-1].get("data") or {}
    event_id = fill_event_data.get("event_id")
    assert event_id, (
        f"FILLED order.updated.v1 event has no event_id: {fill_event_data}"
    )

    # 3. Verify notification-service persisted a notification for it.
    row = await _wait_for_notification(dsn, event_id=event_id, timeout=20.0)

    assert row["event_id"] == event_id
    # notification-service maps order.updated.v1 (status=FILLED) → order.filled.v1
    assert row["event_name"] == "order.filled.v1", (
        f"Notification event_name={row['event_name']!r}; expected "
        f"order.filled.v1 (notification-service must map order.updated.v1 "
        f"status=FILLED to the legacy fine-grained event_name for "
        f"subscription matching)."
    )
    assert str(row["user_id"]) == test_user_id


async def test_notification_service_does_not_double_persist(
    config,
    instrument_catalog,
    test_account_id,
    test_user_id,
    auth_token,
    place_and_sync_order,
    mock_client,
    redis_event_collector,
):
    """A single event_id must produce at most one notification row per user.

    This guards the unique constraint
    `uq_notification_messages_event_id_user_id` (see
    notification_service.models.NotificationMessage). Without it,
    re-deliveries on the consumer group would create duplicate
    notifications.
    """
    dsn = _notification_db_dsn(config.redis_url)
    await _ensure_subscription(dsn, user_id=test_user_id, event_pattern="order.*")

    broker_id = config.broker_id

    from e2e.integration.bas.test_bas_pbs_execution_ws import _place_and_fill

    _broker_order_id, _instrument_id, events = await _place_and_fill(
        place_and_sync_order=place_and_sync_order,
        mock_client=mock_client,
        instrument_catalog=instrument_catalog,
        test_account_id=test_account_id,
        broker_id=broker_id,
        redis_event_collector=redis_event_collector,
        instrument_index=0,
    )

    filled = [
        e for e in events
        if e.get("type") == "order.updated.v1"
        and (e.get("payload") or {}).get("status") == "FILLED"
    ]
    assert filled
    event_id = (filled[-1].get("data") or {}).get("event_id")
    assert event_id

    await _wait_for_notification(dsn, event_id=event_id, timeout=20.0)

    conn = await asyncpg.connect(dsn)
    try:
        count = await conn.fetchval(
            "SELECT count(*) FROM notification_messages "
            "WHERE event_id = $1 AND user_id = $2",
            event_id,
            uuid.UUID(test_user_id),
        )
    finally:
        await conn.close()
    assert count == 1, (
        f"Expected exactly one notification row for event_id={event_id} and "
        f"user_id={test_user_id}; found {count}. Possible regression on "
        f"uq_notification_messages_event_id_user_id."
    )
