"""
Integration test — Outbox poller: rows in `event_outbox` table → events
on the real `events:*` Redis stream.

Pair under test: smarttrade-common OutboxPoller (running inside BAS) ↔
Postgres `event_outbox` table ↔ Redis Streams (`events:*`).

Contract:
    1. A row inserted into a service's `event_outbox` table with
       `published_at = NULL` is picked up by that service's running
       OutboxPoller and published to `events:<event_name>` via the
       EventBus.
    2. After publish, `published_at` is set to a non-NULL timestamp
       so the row is not re-published on subsequent polls.
    3. A row that has already been published (published_at NOT NULL)
       is not re-emitted.

Past regression this test guards against:
    - The previous version of this file XADD'd to a hand-crafted
      `events:test.outbox.<uuid>` stream and read it back itself.
      It never inserted into `event_outbox` and never observed the
      poller. There was no scenario under which it could detect a
      broken poller — including the one we hit in this very session
      where every consumer with `validate_schema=True` silently
      dropped events because of the SchemaRegistry.get_event_schema bug.
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
    return (
        f"postgresql://{pg_user}:{pg_pass}@{host}:{pg_port}/{BAS_DB_NAME}"
    )


async def _insert_outbox_row(
    dsn: str,
    *,
    event_name: str,
    event_data: dict,
    aggregate_id: str | None = None,
) -> int:
    """Insert a row directly into BAS' event_outbox table the same way
    BAS' own services do inside @transactional blocks. Returns the row
    id so the test can read it back."""
    conn = await asyncpg.connect(dsn)
    try:
        row = await conn.fetchrow(
            """
            INSERT INTO event_outbox
              (event_name, event_data, aggregate_id, created_at, retry_count)
            VALUES ($1, $2::json, $3, NOW(), 0)
            RETURNING id
            """,
            event_name,
            json.dumps(event_data),
            aggregate_id,
        )
        return int(row["id"])
    finally:
        await conn.close()


async def _wait_for_row_published(
    dsn: str, *, row_id: int, timeout: float = 10.0
) -> dict:
    """Poll the outbox row until `published_at` is non-NULL. Returns
    the row dict."""
    deadline = asyncio.get_event_loop().time() + timeout
    conn = await asyncpg.connect(dsn)
    try:
        while True:
            row = await conn.fetchrow(
                "SELECT id, event_name, published_at, retry_count, last_error "
                "FROM event_outbox WHERE id = $1",
                row_id,
            )
            if row is None:
                raise AssertionError(
                    f"Outbox row id={row_id} disappeared while waiting "
                    f"for it to be published."
                )
            if row["published_at"] is not None:
                return dict(row)
            if asyncio.get_event_loop().time() >= deadline:
                raise TimeoutError(
                    f"Outbox row id={row_id} not published within "
                    f"{timeout}s. retry_count={row['retry_count']} "
                    f"last_error={row['last_error']!r}. BAS' OutboxPoller "
                    f"is either not running or failing to publish."
                )
            await asyncio.sleep(0.2)
    finally:
        await conn.close()


async def _scan_stream_for_marker(
    redis_url: str,
    *,
    stream: str,
    marker: str,
    timeout: float = 10.0,
) -> dict | None:
    """Scan the real `events:*` stream after a publish, looking for a
    payload containing our unique marker. Returns the matched event
    envelope (as a dict) or None."""
    client = await redis.from_url(redis_url, decode_responses=True)
    deadline = asyncio.get_event_loop().time() + timeout
    try:
        while asyncio.get_event_loop().time() < deadline:
            entries = await client.xrevrange(stream, count=50)
            for _msg_id, fields in entries:
                raw = fields.get("event", "{}")
                try:
                    envelope = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                blob = json.dumps(envelope)
                if marker in blob:
                    return envelope
            await asyncio.sleep(0.2)
    finally:
        await client.close()
    return None


async def test_outbox_row_is_published_to_redis_and_marked(config):
    """The integration contract: inserting a fresh row into BAS'
    `event_outbox` causes BAS' running OutboxPoller to:
      1. Publish the event onto `events:<event_name>` in Redis, and
      2. Set `published_at` to a non-NULL value on the row.

    A unique marker in the payload lets us match the publish back to
    our row even when other tests are producing events concurrently.
    """
    dsn = _bas_dsn(config.redis_url)
    marker = f"e2e-outbox-test-{uuid.uuid4().hex}"

    # Use a real event_name so the EventBus / SchemaRegistry path is
    # exercised. order.updated.v1 is the most heavily-trafficked event
    # in this codebase; a regression in the poller affects it first.
    #
    # The envelope must match the shape DomainEventPublisher.to_dict()
    # produces (user_id, trace_id, request_id, idempotency_key at top
    # level) — otherwise the journal/notification consumers that also
    # subscribe to `events:order.updated.v1` raise EventValidationError
    # and spam ERROR logs on every test run. This event is supposed to
    # be picked up and processed cleanly by every subscriber.
    event_name = "order.updated.v1"
    event_id = str(uuid.uuid4())
    user_id = "00000000-0000-0000-0000-000000000001"
    event_data = {
        "event_name": event_name,
        "event_id": event_id,
        "event_version": "1.0",
        "timestamp": int(time.time() * 1000),
        "user_id": user_id,
        "trace_id": str(uuid.uuid4()),
        "request_id": str(uuid.uuid4()),
        "idempotency_key": f"outbox-test-{marker}-accepted",
        "payload": {
            "marker": marker,  # ← our needle
            "order_id": f"outbox-test-{marker}",
            "broker_order_id": f"outbox-test-{marker}",
            "client_order_id": f"outbox-test-{marker}",
            "user_id": user_id,
            "broker_id": "fyers",
            "account_id": "TEST_E2E_OUTBOX",
            "status": "ACCEPTED",
            "side": "BUY",
            "quantity": 1,
            "instrument_id": "TEST:E2E:EQ",
            "order_type": "MARKET",
        },
    }
    row_id = await _insert_outbox_row(
        dsn,
        event_name=event_name,
        event_data=event_data,
        aggregate_id=f"outbox-test-{marker}",
    )

    # 1. Poller must mark the row as published.
    row = await _wait_for_row_published(dsn, row_id=row_id, timeout=10.0)
    assert row["published_at"] is not None
    assert row["retry_count"] == 0, (
        f"Outbox poller hit retries (retry_count={row['retry_count']}, "
        f"last_error={row['last_error']!r}). Even if the event eventually "
        f"published, this surfaces a broken publish path."
    )

    # 2. Event must land on `events:<event_name>` with our marker.
    envelope = await _scan_stream_for_marker(
        config.redis_url,
        stream=f"events:{event_name}",
        marker=marker,
        timeout=10.0,
    )
    assert envelope is not None, (
        f"Row id={row_id} was marked published but no event with "
        f"marker={marker!r} appeared on `events:{event_name}` within "
        f"10s. The poller may be ACKing rows without actually publishing "
        f"to Redis."
    )


async def test_outbox_already_published_rows_are_not_republished(config):
    """A row inserted with `published_at` already set (representing a
    row the poller has previously handled) must NOT be re-emitted on
    the next poll. The poller selects only rows with
    `published_at IS NULL`, so a re-publish would indicate a query bug.
    """
    dsn = _bas_dsn(config.redis_url)
    marker = f"e2e-outbox-prepublished-{uuid.uuid4().hex}"

    conn = await asyncpg.connect(dsn)
    try:
        row = await conn.fetchrow(
            """
            INSERT INTO event_outbox
              (event_name, event_data, aggregate_id, created_at,
               published_at, retry_count)
            VALUES ($1, $2::json, $3, NOW(), NOW(), 0)
            RETURNING id
            """,
            "order.updated.v1",
            json.dumps(
                {
                    "event_name": "order.updated.v1",
                    "event_id": str(uuid.uuid4()),
                    "payload": {"marker": marker},
                }
            ),
            f"prepublished-{marker}",
        )
        row_id = int(row["id"])
    finally:
        await conn.close()

    # Give the poller more than one full cycle to (incorrectly) pick this
    # row up if its query is broken. The poller's default poll_interval
    # is 1s.
    await asyncio.sleep(2.5)

    envelope = await _scan_stream_for_marker(
        config.redis_url,
        stream="events:order.updated.v1",
        marker=marker,
        timeout=1.0,
    )
    assert envelope is None, (
        f"Pre-published outbox row id={row_id} was emitted to Redis "
        f"(marker={marker!r}). The poller must skip rows whose "
        f"published_at is already set — a regression here would cause "
        f"every poll to re-emit the entire historical outbox."
    )
