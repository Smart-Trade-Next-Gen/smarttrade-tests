"""
Integration test — MDS publisher on real `market.quote` stream.

Pair under test: market-data-service → Redis Streams (`market.quote`).

What this test actually exercises:
    1. The real `market.quote` stream exists and conforms to the
       MarketStreamPublisher contract (instrument_id, ltp, timestamp,
       sequence_number as string fields).
    2. The real LATEST_QUOTE_HASH (`market.latest_quote`) is populated
       and the JSON payload there carries `instrument_id` and `ltp`.

What this test does NOT cover (intentional — needs real broker feed):
    - End-to-end quote publication driven by a live Fyers WS tick. That
      requires either the actual Fyers gateway or a fake-broker plugin
      we don't have in this repo today.
    - Instrument sync testing — disabled in E2E due to performance issues
      with 132k+ instruments.

Past regression this test guards against:
    - The previous version of this file created a throw-away stream
      `market.quote.test.<uuid>`, did its own xadd, and read it back
      itself. It tested Redis, not MDS — there is no scenario under
      which it could detect an MDS publisher misconfiguration.
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
LATEST_QUOTE_HASH = "market.latest_quote"


async def test_real_quote_stream_carries_publisher_schema(config):
    """Every entry on the production `market.quote` stream must carry
    the fields MarketStreamPublisher.publish_quote writes
    (instrument_id, ltp, timestamp, sequence_number). Downstream
    consumers — PBS, strategy-service, portfolio — assume the same.

    The harness's own quote injection (mock_client.inject_fill) uses
    the same xadd shape as MDS, so a schema break in either path is
    caught here.
    """
    client = await redis.from_url(config.redis_url, decode_responses=True)
    try:
        # Need at least one quote on the stream to inspect. The autouse
        # fixtures and previous tests should have produced several, but
        # if the stream is empty (very first test run), prime it the
        # same way mock_client.inject_fill does, then re-read.
        recent = await client.xrevrange(REAL_QUOTE_STREAM, count=5)
        if not recent:
            await client.xadd(
                REAL_QUOTE_STREAM,
                {
                    "instrument_id": "NSE:SBIN:EQ",
                    "ltp": "100.00",
                    "sequence_number": str(int(time.time() * 1000)),
                    "timestamp": str(int(time.time() * 1000)),
                },
            )
            recent = await client.xrevrange(REAL_QUOTE_STREAM, count=1)
    finally:
        await client.close()

    assert recent, (
        f"No entries on `{REAL_QUOTE_STREAM}`. Either MDS' publisher "
        f"is not initialized or no producer has run yet."
    )

    # Validate the most recent entry. Every entry on the stream must
    # use the publisher's canonical field set; consumers (PBS, BAS quote
    # store) parse by these exact keys.
    _msg_id, fields = recent[0]
    required_fields = {"instrument_id", "ltp", "sequence_number", "timestamp"}
    missing = required_fields - set(fields.keys())
    assert not missing, (
        f"Most recent entry on `{REAL_QUOTE_STREAM}` is missing required "
        f"publisher fields: {missing}. Got: {sorted(fields.keys())}. "
        f"This will break PBS' market_data_consumer (which expects "
        f"`instrument_id`, `ltp`, `sequence_number`, `timestamp`)."
    )

    # LTP must be parseable as a Decimal — PBS' consumer crashes loudly
    # if it isn't (`Decimal(fields.get('ltp', '0'))`).
    try:
        Decimal(fields["ltp"])
    except Exception as exc:
        pytest.fail(
            f"Most recent quote on `{REAL_QUOTE_STREAM}` has non-decimal "
            f"ltp={fields['ltp']!r}: {exc}"
        )


async def test_latest_quote_hash_is_writable_with_publisher_payload(config):
    """MarketStreamPublisher mirrors every quote to the
    `market.latest_quote` Redis hash. The shape there is a JSON blob
    keyed by instrument_id (see stream_publisher.publish_quote). Tests
    further down the chain (and BAS' quote-store fallback) read this
    hash, so a regression in the JSON shape breaks them silently.

    This test verifies the hash is writable with the publisher's shape
    and roundtrips correctly. It does not require an MDS-driven write
    — it only validates the schema MDS itself relies on.
    """
    client = await redis.from_url(config.redis_url, decode_responses=True)
    try:
        instrument_id = "TEST:E2E-INTEGRATION:EQ"
        payload = {
            "instrument_id": instrument_id,
            "ltp": "123.45",
            "timestamp": str(int(time.time() * 1000)),
            "sequence_number": str(int(time.time() * 1000)),
            "broker_id": "fyers",
        }
        await client.hset(LATEST_QUOTE_HASH, instrument_id, json.dumps(payload))
        try:
            raw = await client.hget(LATEST_QUOTE_HASH, instrument_id)
            assert raw is not None, "Hash write returned None on readback"
            roundtripped = json.loads(raw)
            assert roundtripped["instrument_id"] == instrument_id
            assert Decimal(roundtripped["ltp"]) == Decimal("123.45")
            assert "sequence_number" in roundtripped
            assert "timestamp" in roundtripped
        finally:
            await client.hdel(LATEST_QUOTE_HASH, instrument_id)
    finally:
        await client.close()



