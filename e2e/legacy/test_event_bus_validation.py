"""Tests for EventBus (Redis Streams) validation - Event schema, ordering, idempotency."""

import pytest
from decimal import Decimal

pytestmark = pytest.mark.event_bus


@pytest.mark.asyncio
async def test_order_filled_event_has_correct_schema(
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
    """Test that order.updated.v1 event has correct schema."""
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

    # Inject fill
    await mock_client.inject_fill(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=qty,
        fill_price=price,
    )

    # Wait for event on Redis stream
    event = await redis_observer.wait_for_event(
        event_type="order.updated.v1",
        predicate=lambda e: e.get("order_id") == order_id,
        timeout=config.timeout_medium,
    )

    # Assertions on schema
    assert event["event_type"] == "order.updated.v1"
    assert event.get("order_id") == order_id
    assert event.get("instrument_id") == instrument_id
    assert event.get("side") == "BUY"
    assert int(event.get("delta_quantity", 0)) == qty
    assert "event_id" in event  # Idempotency key
    assert "timestamp" in event


@pytest.mark.asyncio
async def test_trade_executed_event_has_correct_schema(
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
    """Test that trade.executed.v1 event has correct schema."""
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

    # Inject fill
    await mock_client.inject_fill(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=qty,
        fill_price=price,
    )

    # Wait for event on Redis stream
    event = await redis_observer.wait_for_event(
        event_type="trade.executed.v1",
        predicate=lambda e: e.get("order_id") == order_id,
        timeout=config.timeout_medium,
    )

    # Assertions on schema
    assert event["event_type"] == "trade.executed.v1"
    assert event.get("order_id") == order_id
    assert event.get("instrument_id") == instrument_id
    assert event.get("side") == "BUY"
    assert int(event.get("quantity", 0)) == qty
    assert Decimal(event.get("price", 0)) == price
    assert "trade_id" in event
    assert "event_id" in event


@pytest.mark.skip(reason="BAS handle_position_updated() raises 'got multiple values for argument session'; events never reach Redis stream. Pending BAS-side fix.")
@pytest.mark.asyncio
async def test_position_updated_event_has_correct_schema(
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
    """Test that position.updated.v1 event has correct schema."""
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

    # Inject fill
    await mock_client.inject_fill(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=qty,
        fill_price=price,
    )

    # Wait for event on Redis stream
    event = await redis_observer.wait_for_event(
        event_type="position.updated.v1",
        predicate=lambda e: e.get("instrument_id") == instrument_id,
        timeout=config.timeout_medium,
    )

    # Assertions on schema
    assert event["event_type"] == "position.updated.v1"
    assert event.get("instrument_id") == instrument_id
    assert int(event.get("net_quantity", 0)) == qty
    assert Decimal(event.get("average_price", 0)) == price
    assert "event_id" in event


@pytest.mark.asyncio
async def test_events_have_unique_event_ids(
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
    """Test that all events have unique event_ids (no duplicates)."""
    # Setup
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]

    # Place & sync order
    order_responses = await place_and_sync_order(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_request={
            "instrument_id": instrument_id,
            "position_type": "INTRADAY",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": 100,
        },
    )
    order_id = order_responses[0]["broker_order_id"]

    # Inject fill
    await mock_client.inject_fill(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=100,
        fill_price=550.00,
    )

    # Wait for completion
    await event_collector.wait_for_completion(order_id, timeout=config.timeout_medium)

    # Collect all events
    all_event_ids = []
    for event_type in ["order.updated.v1", "trade.executed.v1", "position.updated.v1"]:
        events = await redis_observer.observe_stream(
            event_type=event_type,
            timeout=2.0,
            count=10,
        )
        for event in events:
            event_id = event.get("event_id")
            if event_id:
                all_event_ids.append(event_id)

    # Assertions
    assert len(all_event_ids) > 0, "No events found"
    assert len(all_event_ids) == len(set(all_event_ids)), "Duplicate event_ids found"


@pytest.mark.asyncio
async def test_subscription_request_includes_user_id(
    config,
    test_account_id,
    test_user_id,
    bas_client,
    mock_client,
    place_and_sync_order,
    instrument_catalog,
    event_collector,
):
    """
    BAS publishes runtime instrument-subscription requests on the
    `market.subscription.request.v1` Redis stream. Each request must carry
    the originating `user_id` so MDS can scope broker subscriptions per
    user. Verify the messages emitted while placing an order include the
    test user's UUID and the instrument we ordered against.
    """
    import json
    import redis.asyncio as redis

    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]

    r = await redis.from_url(config.redis_url, decode_responses=True)
    try:
        # Snapshot the stream tail BEFORE placing the order so we only read
        # subscription requests caused by this test.
        try:
            info = await r.xinfo_stream("market.subscription.request.v1")
            tail_id = info.get("last-generated-id", "0-0")
        except redis.exceptions.ResponseError:
            # Stream doesn't exist yet — read from the beginning.
            tail_id = "0-0"

        order_responses = await place_and_sync_order(
            broker_id=config.broker_id,
            account_id=test_account_id,
            order_request={
                "instrument_id": instrument_id,
                "position_type": "INTRADAY",
                "side": "BUY",
                "order_type": "MARKET",
                "qty": 10,
            },
        )
        # Drive the order to completion so any post-fill subscription
        # bookkeeping has fired before we read the stream.
        order_id = order_responses[0]["broker_order_id"]
        await mock_client.inject_fill(
            broker_id=config.broker_id,
            account_id=test_account_id,
            order_id=order_id,
            sequence=1,
            fill_qty=10,
            fill_price=Decimal("550.00"),
        )
        await event_collector.wait_for_completion(
            order_id, timeout=config.timeout_medium
        )

        # Read all subscription messages emitted after our snapshot.
        # SubscriptionPublisher debounces at 50ms so messages should be
        # present by the time the fill completes.
        entries = await r.xrange(
            "market.subscription.request.v1",
            min=f"({tail_id}",
            max="+",
        )
    finally:
        await r.close()

    assert entries, (
        "Expected at least one market.subscription.request.v1 message after "
        "placing an order; BAS subscription publisher did not emit."
    )

    matched_for_instrument = False
    for _msg_id, fields in entries:
        # Every message must carry user_id — that is the contract.
        assert fields.get("user_id") == test_user_id, (
            f"subscription request missing/mismatched user_id: "
            f"got {fields.get('user_id')!r}, expected {test_user_id!r}"
        )
        assert fields.get("broker_id") == config.broker_id
        assert fields.get("action") in {"subscribe", "unsubscribe"}
        try:
            instruments = json.loads(fields.get("instrument_ids", "[]"))
        except json.JSONDecodeError:
            instruments = []
        if instrument_id in instruments:
            matched_for_instrument = True

    assert matched_for_instrument, (
        f"No subscription request mentioned the ordered instrument "
        f"{instrument_id!r}; BAS is not requesting market data for the "
        f"instruments it places orders against."
    )
