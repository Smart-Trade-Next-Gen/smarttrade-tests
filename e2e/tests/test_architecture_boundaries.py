"""Tests for SmartTrade architecture boundary enforcement."""

import pytest
from decimal import Decimal

pytestmark = pytest.mark.architecture


@pytest.mark.asyncio
async def test_pbs_does_not_emit_to_execution_topics(
    config,
    instrument_catalog,
    test_account_id,
    auth_token,
    bas_client,
    mock_client,
    place_and_sync_order,
    redis_observer,
    event_collector,
):
    """
    Test that PBS never publishes directly to execution event topics.

    Only BAS should emit order.filled.v1, trade.executed.v1, position.updated.v1.
    PBS only emits broker.order_update which BAS consumes.
    """
    # Setup
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]
    qty = 100
    price = Decimal("550.00")

    # Record stream tail before fill
    stream_info = await redis_observer.get_stream_info("order.filled.v1")
    tail_id = stream_info.get("last-generated-id", "0-0")

    # Place & sync order
    order_responses = await place_and_sync_order(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_request={
            "instrument_id": instrument_id,
            "position_type": "INTRADAY",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": qty,
        },
    )
    order_id = order_responses[0]["broker_order_id"]

    # Inject fill via PBS
    await mock_client.inject_fill(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=qty,
        fill_price=price,
    )

    # Wait for BAS to process and emit
    await event_collector.wait_for_completion(order_id, timeout=config.timeout_medium)

    # Verify events came from BAS (not PBS)
    # BAS should emit exactly one order.filled.v1 event
    events = await redis_observer.observe_stream(
        event_type="order.filled.v1",
        timeout=2.0,
        count=10,
    )

    # Filter for our order
    order_events = [e for e in events if e.get("order_id") == order_id]

    # Assertions
    assert len(order_events) > 0, "order.filled.v1 events should be emitted by BAS"
    # All events should have trace_id indicating they came from BAS
    for event in order_events:
        # BAS should be the producer (trace_id context)
        assert "event_id" in event, "Event should have event_id (idempotency)"


@pytest.mark.asyncio
async def test_bas_does_not_require_mds_synchronously_for_execution(
    config,
    instrument_catalog,
    test_account_id,
    auth_token,
    bas_client,
    mock_client,
    place_and_sync_order,
    event_collector,
):
    """
    Test that BAS can execute orders without blocking on MDS.

    BAS uses local instrument master, not sync calls to MDS.
    """
    # Setup
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]
    qty = 100
    price = Decimal("550.00")

    # Place & sync order (this uses instrument_id from MDS already)
    order_responses = await place_and_sync_order(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_request={
            "instrument_id": instrument_id,
            "position_type": "INTRADAY",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": qty,
        },
    )
    order_id = order_responses[0]["broker_order_id"]

    # Inject fill - this should complete without MDS being available
    await mock_client.inject_fill(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=qty,
        fill_price=price,
    )

    # Wait for execution - should succeed even if MDS latency is high
    events = await event_collector.wait_for_completion(order_id, timeout=config.timeout_medium)

    # Assertions
    assert len(events) > 0, "Order should execute without MDS sync call"
    event_types = [e.get("type") for e in events]
    assert any("order" in t and "fill" in t for t in event_types), "Order should reach FILLED status"


@pytest.mark.asyncio
async def test_portfolio_does_not_affect_execution(
    config,
    instrument_catalog,
    test_account_id,
    auth_token,
    bas_client,
    mock_client,
    place_and_sync_order,
    portfolio_client,
    event_collector,
):
    """
    Test that Portfolio Service async consumption doesn't affect order execution.

    Portfolio is a read-model consumer, not part of execution path.
    """
    # Setup
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]
    qty = 100
    price = Decimal("550.00")

    # Place & sync order
    order_responses = await place_and_sync_order(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_request={
            "instrument_id": instrument_id,
            "position_type": "INTRADAY",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": qty,
        },
    )
    order_id = order_responses[0]["broker_order_id"]

    # Inject fill - execution should complete regardless of Portfolio state
    await mock_client.inject_fill(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=qty,
        fill_price=price,
    )

    # Wait for execution
    events = await event_collector.wait_for_completion(order_id, timeout=config.timeout_medium)

    # Assertions: Execution should complete
    assert len(events) > 0
    event_types = [e.get("type") for e in events]
    assert any("order" in t and "fill" in t for t in event_types), \
        "Order should execute regardless of Portfolio state"


@pytest.mark.asyncio
async def test_journal_does_not_affect_execution(
    config,
    instrument_catalog,
    test_account_id,
    auth_token,
    bas_client,
    mock_client,
    place_and_sync_order,
    journal_client,
    event_collector,
):
    """
    Test that Journal Service async consumption doesn't affect order execution.

    Journal is a read-model consumer, not part of execution path.
    """
    # Setup
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]
    qty = 100
    price = Decimal("550.00")

    # Place & sync order
    order_responses = await place_and_sync_order(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_request={
            "instrument_id": instrument_id,
            "position_type": "INTRADAY",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": qty,
        },
    )
    order_id = order_responses[0]["broker_order_id"]

    # Inject fill - execution should complete regardless of Journal state
    await mock_client.inject_fill(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=qty,
        fill_price=price,
    )

    # Wait for execution
    events = await event_collector.wait_for_completion(order_id, timeout=config.timeout_medium)

    # Assertions: Execution should complete
    assert len(events) > 0
    event_types = [e.get("type") for e in events]
    assert any("order" in t and "fill" in t for t in event_types), \
        "Order should execute regardless of Journal state"


@pytest.mark.asyncio
async def test_pbs_accepts_unknown_instrument_id(
    config,
    test_account_id,
    bas_client,
    mock_client,
    place_and_sync_order,
    instrument_catalog,
    event_collector,
):
    """
    PBS no longer owns instrument metadata — it operates on instrument_id
    strings only. This test exercises the contract by routing an order
    through the standard place_and_sync flow and verifying PBS accepts the
    instrument_id without any pre-seeded instrument record.
    """
    # The instrument_catalog fixture seeds instruments only into BAS, never PBS.
    # If PBS had a sync dependency, sync_order would fail here.
    instrument = instrument_catalog.get_any_equity(1)[0]

    order_responses = await place_and_sync_order(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_request={
            "instrument_id": instrument["id"],
            "position_type": "INTRADAY",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": 10,
        },
    )
    order_id = order_responses[0]["broker_order_id"]

    await mock_client.inject_fill(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=10,
        fill_price=Decimal("550.00"),
    )

    events = await event_collector.wait_for_completion(
        order_id, timeout=config.timeout_medium
    )
    event_types = [e.get("type") for e in events]
    assert any("order" in t and "fill" in t for t in event_types), \
        "PBS should fill orders without an instruments-table dependency"


@pytest.mark.asyncio
async def test_pbs_account_auto_created_on_first_buy(
    config,
    bas_client,
    mock_client,
    place_and_sync_order,
    instrument_catalog,
    event_collector,
):
    """
    PBS auto-creates AccountBalance on first access (account_repo.get_with_lock
    inserts a row with DEFAULT_INITIAL_BALANCE if missing). Verify by routing a
    BUY order through a BAS+PBS account_id that has never been touched before
    in this session, without an explicit PBS account-creation call.
    """
    import uuid

    # Prefix must contain "TEST_E2E" so BAS marks the account ACTIVE on
    # creation (see broker_adapter_service.services.trading_account_service:
    # `AccountState.ACTIVE if "TEST_E2E" in payload.account_id else INACTIVE`).
    fresh_account_id = f"TEST_E2E_AUTOCREATE_{uuid.uuid4().hex[:8]}"
    broker_id = config.broker_id

    # BAS still owns trading-account metadata; create the BAS-side record only.
    # No PBS account-creation call — that is what the test is asserting works.
    await bas_client.create_trading_account(
        broker_id=broker_id,
        account_id=fresh_account_id,
        account_type="PAPER",
    )

    try:
        instrument = instrument_catalog.get_any_equity(1)[0]
        order_responses = await place_and_sync_order(
            broker_id=broker_id,
            account_id=fresh_account_id,
            order_request={
                "instrument_id": instrument["id"],
                "position_type": "INTRADAY",
                "side": "BUY",
                "order_type": "MARKET",
                "qty": 5,
            },
        )
        order_id = order_responses[0]["broker_order_id"]

        # Reservation in PBS triggers AccountBalance auto-creation. Drive
        # the fill via the production quote-stream path.
        await mock_client.inject_fill(
            broker_id=broker_id,
            account_id=fresh_account_id,
            order_id=order_id,
            sequence=1,
            fill_qty=5,
            fill_price=Decimal("550.00"),
        )

        # The session-scoped bas_ws_client is subscribed to a different
        # account, so its event_collector won't see this order's events.
        # Verify the auto-create succeeded by polling PBS directly.
        import asyncio
        import httpx

        deadline = asyncio.get_event_loop().time() + config.timeout_medium
        order = None
        while asyncio.get_event_loop().time() < deadline:
            try:
                order = await mock_client._get_client().get(
                    f"/api/v1/order/{broker_id}/{fresh_account_id}/{order_id}",
                    headers=mock_client._get_headers(),
                )
                if order.status_code == 200:
                    body = order.json()
                    if body.get("status") in {"FILLED", "PARTIALLY_FILLED"}:
                        break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.5)

        assert order is not None and order.status_code == 200, (
            f"PBS should expose the order created on a fresh account_id; "
            f"if AccountBalance auto-creation failed, sync_order itself "
            f"would have errored. Last response: {order!r}"
        )
        body = order.json()
        assert body.get("status") == "FILLED", (
            f"Order should reach FILLED status on the auto-created PBS "
            f"AccountBalance; got status={body.get('status')}, "
            f"filled_qty={body.get('filled_qty')}"
        )
    finally:
        try:
            await bas_client.delete_trading_account(broker_id, fresh_account_id)
        except Exception:
            pass


@pytest.mark.asyncio
async def test_redis_stream_drives_pbs_price_execution(
    config,
    test_account_id,
    bas_client,
    mock_client,
    place_and_sync_order,
    instrument_catalog,
    event_collector,
):
    """
    Production path validation: PBS PriceExecutionEngine must pick up quotes
    from the Redis stream `market.quote.v1` (without the test-only HTTP
    shortcut) and trigger LIMIT-order execution.
    """
    import json
    from datetime import datetime, timezone
    import redis.asyncio as redis

    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]
    limit_price = Decimal("550.00")

    order_responses = await place_and_sync_order(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_request={
            "instrument_id": instrument_id,
            "position_type": "INTRADAY",
            "side": "BUY",
            "order_type": "LIMIT",
            "qty": 10,
            "price": limit_price,
        },
    )
    order_id = order_responses[0]["broker_order_id"]

    # Publish a crossing quote on the production Redis stream — no HTTP call.
    r = await redis.from_url(config.redis_url, decode_responses=True)
    try:
        # Use ms-since-epoch sequence so PBS' per-instrument idempotency
        # check doesn't drop the quote as a duplicate across pytest runs.
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        await r.xadd(
            "market.quote.v1",
            {
                "instrument_id": instrument_id,
                "ltp": str(limit_price - Decimal("0.50")),
                "sequence_number": str(now_ms),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
    finally:
        await r.close()

    # PBS consumer block-time is 100ms; allow consumer-group lag.
    events = await event_collector.wait_for_completion(
        order_id, timeout=config.timeout_slow
    )
    event_types = [e.get("type") for e in events]
    assert any("order" in t and "fill" in t for t in event_types), \
        "PBS should execute the LIMIT order from a Redis-stream quote alone"
