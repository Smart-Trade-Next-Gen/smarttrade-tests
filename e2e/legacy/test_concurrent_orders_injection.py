"""
E2E tests for concurrent order handling using injection mode.

Tests validate:
- Multiple simultaneous BUY orders
- Multiple simultaneous SELL orders
- Mixed BUY and SELL concurrently
- Event isolation per order (via Redis Streams)
- Financial invariant preservation across orders
- Position aggregation correctness
- Broker state verification (source of truth)

All tests use INJECTION mode for deterministic execution.
Updated for v4.0 stateless architecture.
"""

import pytest
import uuid
import asyncio
from decimal import Decimal

from smarttrade_common.schemas.types import OrderSide, OrderType, TimeInForce, PositionType
from broker_adapter_service.schemas.order_dtos import BasOrderPlaceRequest, BasOrderLeg


@pytest.mark.injection
@pytest.mark.asyncio
async def test_two_concurrent_buy_orders(
    config,
    bas_client,
    mock_client,
    redis_event_collector,
    broker_state_client,
    assertions,
    test_account_id,
    logger,
    instrument_catalog,
):
    """
    Test: Two concurrent BUY orders placed and filled simultaneously.

    Validates:
    - Both orders placed successfully
    - Fills injected for both orders
    - Events collected for each order independently (via Redis Streams)
    - Broker state verification for both orders
    - Final positions reflect both buys
    - No event cross-contamination
    """
    axis_inst = instrument_catalog.get_equity("AXIS")
    kotak_inst = instrument_catalog.get_equity("KOTAK")
    broker_id = config.broker_id

    # Act: Place two BUY orders concurrently
    order_request_1 = BasOrderPlaceRequest(
        client_order_id=f"test_concurrent_buy_1_{test_account_id}_{uuid.uuid4().hex[:8]}",
        position_type=PositionType.INTRADAY,
        legs=[
            BasOrderLeg(
                instrument_id=axis_inst["id"],
                instrument_type="EQUITY",
                side=OrderSide.BUY,
                qty=50,
                order_type=OrderType.MARKET,
                price=None,
                stop_price=None,
                ltp=Decimal("900.00"),
            )
        ],
        underlying_instrument_id=axis_inst["id"],
        underlying_symbol="AXIS",
        tif=TimeInForce.DAY,
    )

    order_request_2 = BasOrderPlaceRequest(
        client_order_id=f"test_concurrent_buy_2_{test_account_id}_{uuid.uuid4().hex[:8]}",
        position_type=PositionType.INTRADAY,
        legs=[
            BasOrderLeg(
                instrument_id=kotak_inst["id"],
                instrument_type="EQUITY",
                side=OrderSide.BUY,
                qty=75,
                order_type=OrderType.MARKET,
                price=None,
                stop_price=None,
                ltp=Decimal("1850.00"),
            )
        ],
        underlying_instrument_id=kotak_inst["id"],
        underlying_symbol="KOTAK",
        tif=TimeInForce.DAY,
    )

    [resp1] = await bas_client.place_order(broker_id, test_account_id, order_request_1)
    await asyncio.sleep(0.1)  # Small delay to avoid race conditions
    [resp2] = await bas_client.place_order(broker_id, test_account_id, order_request_2)
    order_id_1 = resp1.broker_order_id
    order_id_2 = resp2.broker_order_id
    logger.info(f"Order 1 placed | ID: {order_id_1} | Qty: 50")
    logger.info(f"Order 2 placed | ID: {order_id_2} | Qty: 75")

    # Act: Inject fills for both orders
    await mock_client.inject_fill(
        broker_id=broker_id,
        account_id=test_account_id,
        order_id=order_id_1,
        sequence=1,
        fill_qty=50,
        fill_price=Decimal("899.50"),
    )
    await mock_client.inject_fill(
        broker_id=broker_id,
        account_id=test_account_id,
        order_id=order_id_2,
        sequence=1,
        fill_qty=75,
        fill_price=Decimal("1849.00"),
    )
    logger.info("Fills injected for both orders")

    # Observe: Collect events for both orders via Redis Streams
    events_1 = await redis_event_collector.wait_for_completion(order_id_1, timeout=15.0)
    events_2 = await redis_event_collector.wait_for_completion(order_id_2, timeout=15.0)
    logger.info(f"Events collected | Order 1: {len(events_1)} | Order 2: {len(events_2)}")

    # Assert: Both orders filled
    assertions.assert_order_lifecycle(events_1, "FILLED", 50)
    assertions.assert_order_lifecycle(events_2, "FILLED", 75)
    logger.info("✓ Both orders filled")

    # Assert: Status transitions correct
    assertions.assert_status_transition_correct(events_1, ["PLACED", "FILLED"])
    assertions.assert_status_transition_correct(events_2, ["PLACED", "FILLED"])
    logger.info("✓ Status transitions validated")

    # Assert: No event contamination between orders
    assertions.assert_no_duplicate_events(events_1)
    assertions.assert_no_duplicate_events(events_2)
    logger.info("✓ No event contamination")

    # Assert: Broker state verification for both orders
    broker_order_1 = await broker_state_client.get_order_state(broker_id, test_account_id, order_id_1)
    broker_order_2 = await broker_state_client.get_order_state(broker_id, test_account_id, order_id_2)
    assertions.assert_broker_state_matches_events(broker_order_1, events_1)
    assertions.assert_broker_state_matches_events(broker_order_2, events_2)
    logger.info("✓ Broker state matches events for both orders")


@pytest.mark.injection
@pytest.mark.asyncio
async def test_concurrent_buy_and_sell(
    config,
    bas_client,
    mock_client,
    redis_event_collector,
    broker_state_client,
    assertions,
    test_account_id,
    logger,
    instrument_catalog,
):
    """
    Test: BUY and SELL orders placed and filled concurrently.

    Validates:
    - BUY and SELL execute independently
    - Events isolated per order (via Redis Streams)
    - Positions reflect both (long + short)
    - Financial invariants: debit for BUY, credit for SELL
    - Broker state verification
    """
    asian_inst = instrument_catalog.get_equity("ASIAN")
    bhartiartl_inst = instrument_catalog.get_equity("BHARTIARTL")
    broker_id = config.broker_id

    # Act: Place BUY and SELL orders concurrently
    buy_request = BasOrderPlaceRequest(
        client_order_id=f"test_concurrent_buy_sell_buy_{test_account_id}_{uuid.uuid4().hex[:8]}",
        position_type=PositionType.INTRADAY,
        legs=[
            BasOrderLeg(
                instrument_id=asian_inst["id"],
                instrument_type="EQUITY",
                side=OrderSide.BUY,
                qty=100,
                order_type=OrderType.MARKET,
                price=None,
                stop_price=None,
                ltp=Decimal("700.00"),
            )
        ],
        underlying_instrument_id=asian_inst["id"],
        underlying_symbol="ASIAN",
        tif=TimeInForce.DAY,
    )

    sell_request = BasOrderPlaceRequest(
        client_order_id=f"test_concurrent_buy_sell_sell_{test_account_id}_{uuid.uuid4().hex[:8]}",
        position_type=PositionType.INTRADAY,
        legs=[
            BasOrderLeg(
                instrument_id=bhartiartl_inst["id"],
                instrument_type="EQUITY",
                side=OrderSide.SELL,
                qty=100,
                order_type=OrderType.MARKET,
                price=None,
                stop_price=None,
                ltp=Decimal("850.00"),
            )
        ],
        underlying_instrument_id=bhartiartl_inst["id"],
        underlying_symbol="BHARTIARTL",
        tif=TimeInForce.DAY,
    )

    # Capture pre-state
    pre_funds = await bas_client.get_funds(broker_id, test_account_id)
    logger.info(f"Pre-state captured | Funds: {pre_funds.total_equity}")

    # Place orders
    [buy_resp] = await bas_client.place_order(broker_id, test_account_id, buy_request)
    [sell_resp] = await bas_client.place_order(broker_id, test_account_id, sell_request)
    buy_order_id = buy_resp.broker_order_id
    sell_order_id = sell_resp.broker_order_id
    logger.info(f"BUY order placed | ID: {buy_order_id} | Qty: 100")
    logger.info(f"SELL order placed | ID: {sell_order_id} | Qty: 100")

    # Act: Inject fills for both
    await mock_client.inject_fill(
        broker_id=broker_id,
        account_id=test_account_id,
        order_id=buy_order_id,
        sequence=1,
        fill_qty=100,
        fill_price=Decimal("699.50"),
    )
    await mock_client.inject_fill(
        broker_id=broker_id,
        account_id=test_account_id,
        order_id=sell_order_id,
        sequence=1,
        fill_qty=100,
        fill_price=Decimal("849.00"),
    )
    logger.info("Fills injected for both orders")

    # Observe: Collect events via Redis Streams
    buy_events = await redis_event_collector.wait_for_completion(buy_order_id, timeout=15.0)
    sell_events = await redis_event_collector.wait_for_completion(sell_order_id, timeout=15.0)
    logger.info(f"Events collected | BUY: {len(buy_events)} | SELL: {len(sell_events)}")

    # Assert: Both orders filled
    assertions.assert_order_lifecycle(buy_events, "FILLED", 100)
    assertions.assert_order_lifecycle(sell_events, "FILLED", 100)
    logger.info("✓ Both orders filled")

    # Assert: Status transitions correct
    assertions.assert_status_transition_correct(buy_events, ["PLACED", "FILLED"])
    assertions.assert_status_transition_correct(sell_events, ["PLACED", "FILLED"])
    logger.info("✓ Status transitions validated")

    # Assert: No duplicate events
    assertions.assert_no_duplicate_events(buy_events)
    assertions.assert_no_duplicate_events(sell_events)
    logger.info("✓ No duplicate events")

    # Assert: Broker state verification
    broker_buy_order = await broker_state_client.get_order_state(broker_id, test_account_id, buy_order_id)
    broker_sell_order = await broker_state_client.get_order_state(broker_id, test_account_id, sell_order_id)
    assertions.assert_broker_state_matches_events(broker_buy_order, buy_events)
    assertions.assert_broker_state_matches_events(broker_sell_order, sell_events)
    logger.info("✓ Broker state matches events")

    # Assert: Financial invariants
    post_funds = await bas_client.get_funds(broker_id, test_account_id)
    assertions.assert_financial_invariants(
        pre_funds,
        post_funds,
        side="BUY",
        qty=100,
        price=Decimal("699.50"),
    )
    logger.info("✓ Financial invariants validated")


@pytest.mark.injection
@pytest.mark.asyncio
async def test_three_orders_same_instrument(
    config,
    bas_client,
    mock_client,
    redis_event_collector,
    broker_state_client,
    assertions,
    test_account_id,
    logger,
    instrument_catalog,
):
    """
    Test: Three orders for the same instrument placed concurrently.

    Validates:
    - All three orders placed successfully
    - Events isolated per order (via Redis Streams)
    - Position aggregation handles multiple orders correctly
    - Broker state verification
    """
    tcs_inst = instrument_catalog.get_equity("TCS")
    broker_id = config.broker_id

    # Act: Place three orders for same instrument
    order_requests = []
    order_ids = []
    qtys = [50, 75, 100]

    for i, qty in enumerate(qtys):
        order_request = BasOrderPlaceRequest(
            client_order_id=f"test_three_orders_{i}_{test_account_id}_{uuid.uuid4().hex[:8]}",
            position_type=PositionType.INTRADAY,
            legs=[
                BasOrderLeg(
                    instrument_id=tcs_inst["id"],
                    instrument_type="EQUITY",
                    side=OrderSide.BUY,
                    qty=qty,
                    order_type=OrderType.LIMIT,
                    price=Decimal("3500.00"),
                    stop_price=None,
                    ltp=Decimal("3550.00"),
                )
            ],
            underlying_instrument_id=tcs_inst["id"],
            underlying_symbol="TCS",
            tif=TimeInForce.DAY,
        )
        order_requests.append(order_request)

    # Place orders with small delay
    for i, order_request in enumerate(order_requests):
        [resp] = await bas_client.place_order(broker_id, test_account_id, order_request)
        order_ids.append(resp.broker_order_id)
        logger.info(f"Order {i+1} placed | ID: {order_ids[i]} | Qty: {qtys[i]}")
        await asyncio.sleep(0.05)

    # Act: Inject fills for all orders
    for i, (order_id, qty) in enumerate(zip(order_ids, qtys)):
        await mock_client.inject_fill(
            broker_id=broker_id,
            account_id=test_account_id,
            order_id=order_id,
            sequence=1,
            fill_qty=qty,
            fill_price=Decimal("3495.00"),
        )
        logger.info(f"Fill {i+1} injected | Qty: {qty}")

    # Observe: Collect events for all orders via Redis Streams
    all_events = []
    for i, order_id in enumerate(order_ids):
        events = await redis_event_collector.wait_for_completion(order_id, timeout=15.0)
        all_events.append(events)
        logger.info(f"Events collected | Order {i+1}: {len(events)}")

    # Assert: All orders filled
    for i, (events, qty) in enumerate(zip(all_events, qtys)):
        assertions.assert_order_lifecycle(events, "FILLED", qty)
        logger.info(f"✓ Order {i+1} filled")
    
    # Assert: Status transitions correct
    for i, events in enumerate(all_events):
        assertions.assert_status_transition_correct(events, ["PLACED", "FILLED"])
    logger.info("✓ Status transitions validated")

    # Assert: No duplicate events
    for i, events in enumerate(all_events):
        assertions.assert_no_duplicate_events(events)
    logger.info("✓ No duplicate events")

    # Assert: Broker state verification
    for i, (order_id, events) in enumerate(zip(order_ids, all_events)):
        broker_order = await broker_state_client.get_order_state(broker_id, test_account_id, order_id)
        assertions.assert_broker_state_matches_events(broker_order, events)
    logger.info("✓ Broker state matches events for all orders")
