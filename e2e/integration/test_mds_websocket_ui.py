"""
Integration test — MDS UI WebSocket protocol contract.

Pair under test: UI client ←→ market-data-service (`/ws/{broker_id}/ui`).

Contract:
    1. The UI WebSocket accepts a JWT via either Authorization header or
       `?token=` query param. The handshake is rejected (close code 4401)
       without a valid token.
    2. On accept, MDS sends two control frames in order:
          a. `system.connected` carrying conn_id, user_id, broker_id
          b. `system.subscription_set.v1` listing currently-active
             instrument_ids for the broker (firehose model — UI joins the
             broker-wide set, no explicit account subscription needed)
    3. A `subscribe.market` request with `quote=[instrument_id, ...]` is
       acknowledged by:
          a. `system.ack` (request_id echoed) — must arrive FIRST
          b. `system.subscribed_market` (depth/quote lists echoed)
    4. The matching `unsubscribe.market` is acknowledged symmetrically by
       `system.ack` followed by `system.unsubscribed_market`.
    5. MDS sends `system.heartbeat` frames periodically (~every 5s). The
       channel survives idle periods without disconnecting the client.

This test does NOT validate the full quote-fanout path (a quote on
`market.quote.v1` ultimately reaching the UI WS), because driving that
end-to-end requires a broker mock pushing onPriceChange. The full
fanout is covered by the broker-plugin tests inside MDS. Here we verify
only the UI-facing WS contract.

Past regression to guard against:
    - The ack/subscribe-confirm send order matters for frontend state
      machines: the React store treats `system.ack` as "request committed"
      and only then applies the optimistic subscription. If MDS sent
      `system.subscribed_market` before `system.ack`, the store wedged.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Optional

import pytest
import websockets


pytestmark = pytest.mark.asyncio


async def _recv_until(
    ws,
    type_predicate,
    *,
    timeout: float = 5.0,
    max_messages: int = 50,
) -> dict:
    """Receive messages until one matches `type_predicate(type)`.

    Heartbeats and unrelated control frames are drained. Useful for
    asserting "eventually we see message X" without coupling to the
    intervening housekeeping frames.
    """
    deadline = asyncio.get_event_loop().time() + timeout
    seen_types: list[str] = []
    for _ in range(max_messages):
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            break
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        except asyncio.TimeoutError:
            break
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        seen_types.append(data.get("type", "?"))
        if type_predicate(data.get("type")):
            return data
    raise AssertionError(
        f"Did not receive matching message within {timeout}s. "
        f"Types seen: {seen_types}"
    )


async def _connect_ui_ws(
    config,
    auth_token: str,
    test_user_id: str,
    *,
    open_timeout: float = 5.0,
):
    """Open a UI WebSocket against MDS. Returns the open connection."""
    ws_url = (
        f"{config.mds_ws_url}/ws/{config.broker_id}/ui"
        f"?token={auth_token}&user_id={test_user_id}"
    )
    return await websockets.connect(ws_url, open_timeout=open_timeout)


async def test_ui_ws_handshake_sends_system_connected_and_subscription_set(
    config,
    auth_token,
    test_user_id,
):
    """On UI WS connect, MDS must send `system.connected` then
    `system.subscription_set.v1` in that order.

    Order matters: the frontend uses `system.connected` to flip its
    `wsReady` state, and `system.subscription_set.v1` to seed the
    initially-active instrument set so the UI can render the live
    quote list without making a separate REST call.
    """
    ws = await _connect_ui_ws(config, auth_token, test_user_id)
    try:
        # First message MUST be system.connected
        raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
        first = json.loads(raw)
        assert first.get("type") == "system.connected", (
            f"First MDS UI WS frame must be system.connected; got "
            f"type={first.get('type')!r}, full={first}"
        )
        assert first.get("conn_id"), "system.connected missing conn_id"
        assert first.get("broker_id") == config.broker_id, (
            f"system.connected has wrong broker_id: got "
            f"{first.get('broker_id')!r} expected {config.broker_id!r}"
        )
        assert first.get("consumer_type") == "ui", (
            f"system.connected.consumer_type should be 'ui' on the UI route; "
            f"got {first.get('consumer_type')!r}"
        )

        # Second message MUST be system.subscription_set.v1
        subscription_set = await _recv_until(
            ws,
            lambda t: t == "system.subscription_set.v1",
            timeout=5.0,
        )
        assert "active_instrument_ids" in subscription_set, (
            f"system.subscription_set.v1 missing active_instrument_ids: "
            f"{subscription_set}"
        )
        assert isinstance(subscription_set["active_instrument_ids"], list), (
            f"system.subscription_set.v1.active_instrument_ids must be a "
            f"list; got {type(subscription_set['active_instrument_ids'])}"
        )
        assert subscription_set.get("broker_id") == config.broker_id
    finally:
        await ws.close()


async def test_ui_ws_subscribe_market_ack_arrives_before_confirm(
    config,
    auth_token,
    test_user_id,
    instrument_catalog,
):
    """`subscribe.market` request triggers `system.ack` (first) then
    `system.subscribed_market` (second) with the echoed quote list.

    A naive implementation might emit the confirm before the ack — the
    frontend store would then apply the subscription before knowing
    the request was committed, defeating the optimistic-update
    rollback path. Order must be ack→confirm.
    """
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]
    request_id = f"e2e-{uuid.uuid4().hex[:12]}"

    ws = await _connect_ui_ws(config, auth_token, test_user_id)
    try:
        # Drain handshake frames.
        await _recv_until(
            ws, lambda t: t == "system.subscription_set.v1", timeout=5.0
        )

        # Send subscribe.
        await ws.send(json.dumps({
            "action": "subscribe.market",
            "request_id": request_id,
            "quote": [instrument_id],
            "depth": [],
        }))

        # 1. system.ack must arrive first.
        ack = await _recv_until(
            ws,
            lambda t: t in ("system.ack", "system.subscribed_market", "error.event"),
            timeout=5.0,
        )
        if ack.get("type") == "error.event":
            pytest.fail(
                f"subscribe.market produced error.event: code="
                f"{ack.get('error_code')!r}, message={ack.get('message')!r}"
            )
        assert ack.get("type") == "system.ack", (
            f"Expected `system.ack` to arrive before `system.subscribed_market`. "
            f"Got type={ack.get('type')!r}. Frontend stores rely on this order."
        )
        assert ack.get("status") == "ok"
        assert ack.get("request_id") == request_id, (
            f"system.ack.request_id must echo the client's request_id. "
            f"Sent {request_id!r}, got {ack.get('request_id')!r}."
        )

        # 2. system.subscribed_market follows with echoed lists.
        confirm = await _recv_until(
            ws, lambda t: t == "system.subscribed_market", timeout=5.0
        )
        assert confirm.get("request_id") == request_id
        assert instrument_id in confirm.get("quote", []), (
            f"system.subscribed_market.quote should echo subscribed "
            f"instrument {instrument_id}; got {confirm.get('quote')}"
        )
    finally:
        await ws.close()


async def test_ui_ws_unsubscribe_market_acked_symmetrically(
    config,
    auth_token,
    test_user_id,
    instrument_catalog,
):
    """`unsubscribe.market` is acknowledged by `system.ack` + `system.unsubscribed_market`.

    Symmetric to subscribe — the same ack-before-confirm ordering must
    hold. Otherwise the frontend can leak optimistic subscriptions.
    """
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]

    ws = await _connect_ui_ws(config, auth_token, test_user_id)
    try:
        await _recv_until(
            ws, lambda t: t == "system.subscription_set.v1", timeout=5.0
        )

        # Subscribe first so we have something to unsubscribe.
        sub_req = f"sub-{uuid.uuid4().hex[:8]}"
        await ws.send(json.dumps({
            "action": "subscribe.market",
            "request_id": sub_req,
            "quote": [instrument_id],
        }))
        await _recv_until(
            ws, lambda t: t == "system.subscribed_market", timeout=5.0
        )

        # Now unsubscribe.
        unsub_req = f"unsub-{uuid.uuid4().hex[:8]}"
        await ws.send(json.dumps({
            "action": "unsubscribe.market",
            "request_id": unsub_req,
            "quote": [instrument_id],
        }))

        ack = await _recv_until(
            ws,
            lambda t: t in ("system.ack", "system.unsubscribed_market", "error.event"),
            timeout=5.0,
        )
        assert ack.get("type") == "system.ack", (
            f"Expected `system.ack` before `system.unsubscribed_market`. "
            f"Got type={ack.get('type')!r}."
        )
        assert ack.get("request_id") == unsub_req
        assert ack.get("status") == "ok"

        confirm = await _recv_until(
            ws, lambda t: t == "system.unsubscribed_market", timeout=5.0
        )
        assert confirm.get("request_id") == unsub_req
        assert instrument_id in confirm.get("quote", [])
    finally:
        await ws.close()


async def test_ui_ws_handshake_rejected_without_token(
    config,
):
    """Connecting without a JWT token must be rejected at handshake.

    MDS closes the WebSocket with code 4401 (custom auth-failed code,
    see authenticate_websocket()). The `websockets` client surfaces
    this as a ConnectionClosedError / InvalidStatus during connect.
    """
    ws_url = f"{config.mds_ws_url}/ws/{config.broker_id}/ui"

    raised = False
    try:
        async with websockets.connect(ws_url, open_timeout=5.0) as ws:
            # If the server accepts the handshake (it shouldn't), try to
            # read — the close frame will arrive immediately.
            try:
                await asyncio.wait_for(ws.recv(), timeout=2.0)
            except Exception:
                raised = True
    except websockets.exceptions.InvalidStatus:
        raised = True
    except websockets.exceptions.ConnectionClosed:
        raised = True
    except Exception:
        raised = True

    assert raised, (
        "MDS UI WS accepted a connection with no JWT token. The "
        "handshake must reject unauthenticated clients with close "
        "code 4401."
    )


async def test_ui_ws_receives_periodic_heartbeat(
    config,
    auth_token,
    test_user_id,
):
    """MDS sends `system.heartbeat` frames at ~5s intervals.

    The frontend uses heartbeat absence as its dead-connection signal.
    If MDS stops sending heartbeats, the UI re-establishes the WS.
    """
    ws = await _connect_ui_ws(config, auth_token, test_user_id)
    try:
        # Drain initial handshake.
        await _recv_until(
            ws, lambda t: t == "system.subscription_set.v1", timeout=5.0
        )

        # Wait up to ~7s for a heartbeat (interval is 5s, give 2s slack).
        # Heartbeats are unrelated to subscribed market data, so we
        # accept the first one we see.
        hb = await _recv_until(
            ws, lambda t: t == "system.heartbeat", timeout=7.0
        )
        assert hb.get("type") == "system.heartbeat"
    finally:
        await ws.close()
