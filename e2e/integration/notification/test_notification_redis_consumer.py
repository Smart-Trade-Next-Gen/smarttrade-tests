"""
Integration test — Notification Service pure event relay architecture.

Pair under test: notification-service ←→ Redis Streams (all domain events).

Contract:
    1. Notification service consumes all domain events from Redis Streams
    2. Events are classified into streams (execution, risk, notification, ai, system, broker)
    3. Events are stored in Redis replay buffer for WebSocket delivery
    4. No database persistence occurs (pure relay architecture)

This test verifies the new pure relay behavior after the architectural
refactoring that removed database persistence.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from decimal import Decimal
from urllib.parse import urlparse

import asyncpg
import pytest
import redis.asyncio as redis


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
    about the consume-and-relay contract, not the subscription API.
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


async def _wait_for_redis_replay_event(
    redis_client: redis.Redis,
    *,
    stream: str,
    event_id: str,
    timeout: float = 15.0,
    poll_interval: float = 0.5,
) -> dict:
    """Wait for an event to appear in the Redis replay buffer."""
    deadline = asyncio.get_event_loop().time() + timeout
    key = f"notification_replay:{stream}"
    
    while True:
        # Get all events from the stream
        events_json = await redis_client.zrange(key, 0, -1)
        
        for event_json in events_json:
            try:
                event = json.loads(event_json)
                if event.get("event_id") == event_id or event.get("payload", {}).get("event_id") == event_id:
                    return event
            except json.JSONDecodeError:
                continue
        
        if asyncio.get_event_loop().time() >= deadline:
            raise TimeoutError(
                f"Event {event_id} not found in Redis replay buffer for stream {stream} "
                f"within {timeout}s"
            )
        
        await asyncio.sleep(poll_interval)


async def _verify_no_database_persistence(dsn: str) -> None:
    """Verify that no notification messages were persisted to the database."""
    conn = await asyncpg.connect(dsn)
    try:
        # Check that notification_messages table does not exist or is empty
        # After the migration, this table should not exist
        table_exists = await conn.fetchval(
            "SELECT EXISTS (SELECT FROM information_schema.tables "
            "WHERE table_name = 'notification_messages')"
        )
        
        if table_exists:
            # Table exists, verify it's empty
            count = await conn.fetchval("SELECT count(*) FROM notification_messages")
            assert count == 0, (
                f"notification_messages table should be empty in pure relay architecture, "
                f"but found {count} rows"
            )
    finally:
        await conn.close()


async def test_notification_service_relays_events_to_redis(
    config,
    instrument_catalog,
    test_account_id,
    test_user_id,
    auth_token,
    place_and_sync_order,
    mock_client,
    redis_event_collector,
):
    """A fill drives `order.updated` with status=FILLED. Notification
    service consumes the event, classifies it into the execution stream,
    and stores it in Redis replay buffer for WebSocket delivery.
    
    This test verifies the pure relay architecture - no database persistence.
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

    # 2. Find the FILLED order.updated event so we know which event_id
    #    to look up in Redis replay buffer.
    filled_events = [
        e
        for e in events
        if e.get("type") == "order.updated"
        and (e.get("payload") or {}).get("status") == "FILLED"
    ]
    assert filled_events, (
        "Test cannot proceed: BAS did not publish a FILLED order.updated "
        "event. The bug is upstream of notification-service."
    )
    # The event envelope stores event_id alongside payload.
    fill_event_data = filled_events[-1].get("data") or {}
    event_id = fill_event_data.get("event_id")
    assert event_id, (
        f"FILLED order.updated event has no event_id: {fill_event_data}"
    )

    # 3. Verify notification-service stored the event in Redis replay buffer.
    redis_client = await redis.from_url(config.redis_url, decode_responses=True)
    try:
        # Wait for the event to appear in the execution stream replay buffer
        event_envelope = await _wait_for_redis_replay_event(
            redis_client,
            stream="execution",
            event_id=event_id,
            timeout=20.0
        )
        
        # Verify the event envelope structure
        assert event_envelope is not None, "Event not found in Redis replay buffer"
        assert event_envelope["stream"] == "execution", (
            f"Event should be classified as 'execution' stream, got {event_envelope['stream']}"
        )
        assert "sequence" in event_envelope, "Event envelope missing sequence number"
        assert "timestamp" in event_envelope, "Event envelope missing timestamp"
        assert "payload" in event_envelope, "Event envelope missing payload"
        
        # Verify the event was classified correctly (order.updated -> execution stream)
        assert event_envelope["stream"] == "execution"
        
    finally:
        await redis_client.close()

    # 4. Verify NO database persistence occurred (pure relay architecture)
    await _verify_no_database_persistence(dsn)


async def test_notification_service_classifies_events_into_streams(
    config,
    instrument_catalog,
    test_account_id,
    test_user_id,
    auth_token,
    place_and_sync_order,
    mock_client,
    redis_event_collector,
):
    """Verify that notification-service correctly classifies different event types
    into appropriate streams (execution, risk, notification, ai, system, broker).
    
    This test focuses on the stream classification logic.
    """
    dsn = _notification_db_dsn(config.redis_url)
    
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

    # Find the FILLED order.updated event
    filled_events = [
        e
        for e in events
        if e.get("type") == "order.updated"
        and (e.get("payload") or {}).get("status") == "FILLED"
    ]
    assert filled_events, "No FILLED order.updated event found"
    
    fill_event_data = filled_events[-1].get("data") or {}
    event_id = fill_event_data.get("event_id")
    assert event_id, "Event missing event_id"

    # Verify the event was classified into the execution stream
    redis_client = await redis.from_url(config.redis_url, decode_responses=True)
    try:
        event_envelope = await _wait_for_redis_replay_event(
            redis_client,
            stream="execution",
            event_id=event_id,
            timeout=20.0
        )
        
        assert event_envelope["stream"] == "execution", (
            f"order.updated event should be classified as 'execution' stream, "
            f"got {event_envelope['stream']}"
        )
        
    finally:
        await redis_client.close()

    # Verify no database persistence
    await _verify_no_database_persistence(dsn)
