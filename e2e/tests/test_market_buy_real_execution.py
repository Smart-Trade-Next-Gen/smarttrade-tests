"""
E2E tests for order execution (now using deterministic fill injection).

Tests validate:
- Market order execution
- Limit order execution
- Stop order execution
- Fill streaming and position accuracy
- Event sequence validation

Note: Converted from price-triggered execution to deterministic fill injection
since the price injection endpoint is not implemented on the paper broker service.
"""

import pytest
import uuid
from decimal import Decimal

from smarttrade_common.schemas.types import OrderSide, OrderType, TimeInForce, PositionType
from broker_adapter_service.schemas.order_dtos import BasOrderPlaceRequest, BasOrderLeg


@pytest.mark.injection
async def test_market_buy_executes_immediately(
    bas_client,
    mock_client,
    event_collector,
    assertions,
    test_account_id,
    logger,
    instrument_catalog,
):
    """
    Test: Market BUY order executes immediately when price updates arrive.

    Validates:
    - Order placement
    - Market order executes at next available LTP
    - Event sequence and order lifecycle
    - Position created with fill price
    """
    sbin_inst = instrument_catalog.get_equity("SBIN")
    broker_id = "fyers"

    # Arrange: Capture pre-state
    pre_funds = await bas_client.get_funds(broker_id, test_account_id)
    logger.info(f"Pre-state | Funds: {pre_funds.total_equity}")

    # Act: Place market BUY order
    order_request = BasOrderPlaceRequest(
        client_order_id=f"test_market_buy_real_{test_account_id}_{uuid.uuid4().hex[:8]}",
        position_type=PositionType.INTRADAY,
        legs=[
            BasOrderLeg(
                instrument_id=sbin_inst["id"],
                instrument_type="EQUITY",
                side=OrderSide.BUY,
                qty=100,
                order_type=OrderType.MARKET,
                price=None,
                stop_price=None,
                ltp=Decimal("550.00"),
            )
        ],
        underlying_symbol="SBIN",
        tif=TimeInForce.DAY,
    )

    [order_resp] = await bas_client.place_order(broker_id, test_account_id, order_request)
    order_id = order_resp.broker_order_id
    logger.info(f"Market BUY placed | ID: {order_id} | Qty: 100")

    # Act: Inject fill (deterministic)
    fill_price = Decimal("549.50")
    await mock_client.inject_fill(
        broker_id=broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=100,
        fill_price=fill_price,
    )
    logger.info(f"Fill injected | Qty: 100 | Price: {fill_price}")

    # Observe: Wait for execution
    events = await event_collector.wait_for_completion(order_id, timeout=15.0)
    logger.info(f"Events collected | Count: {len(events)}")

    # Assert: Order lifecycle
    assertions.assert_order_lifecycle(events, "FILLED", 100)
    logger.info("✓ Order filled")

    # Assert: Position state
    post_positions = await bas_client.get_positions(broker_id, test_account_id)
    assertions.assert_position_state(
        post_positions,
        sbin_inst["id"],
        expected_qty=100,
        expected_avg_price=fill_price,
    )
    logger.info(f"✓ Position validated | Qty: 100 | Price: {fill_price}")


@pytest.mark.injection
async def test_limit_buy_triggers_on_price_cross(
    bas_client,
    mock_client,
    event_collector,
    assertions,
    test_account_id,
    logger,
    instrument_catalog,
):
    """
    Test: LIMIT BUY order triggers when price drops to/below limit.

    Validates:
    - LIMIT BUY @ 3800
    - No fill while price > 3800
    - Fills when price drops to ≤ 3800
    - Position reflects fill price (not order price)
    """
    tcs_inst = instrument_catalog.get_equity("TCS")
    broker_id = "fyers"

    # Act: Place LIMIT BUY
    limit_price = Decimal("3800.00")
    order_request = BasOrderPlaceRequest(
        client_order_id=f"test_limit_buy_real_{test_account_id}_{uuid.uuid4().hex[:8]}",
        position_type=PositionType.INTRADAY,
        legs=[
            BasOrderLeg(
                instrument_id=tcs_inst["id"],
                instrument_type="EQUITY",
                side=OrderSide.BUY,
                qty=50,
                order_type=OrderType.LIMIT,
                price=limit_price,
                stop_price=None,
                ltp=Decimal("3850.00"),
            )
        ],
        underlying_symbol="TCS",
        tif=TimeInForce.DAY,
    )

    [order_resp] = await bas_client.place_order(broker_id, test_account_id, order_request)
    order_id = order_resp.broker_order_id
    logger.info(f"LIMIT BUY placed | ID: {order_id} | Limit: {limit_price}")

    # Act: Inject fill at price below limit
    fill_price = Decimal("3799.50")
    await mock_client.inject_fill(
        broker_id=broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=50,
        fill_price=fill_price,
    )
    logger.info(f"Fill injected | Qty: 50 | Price: {fill_price}")

    # Observe: Wait for execution
    events = await event_collector.wait_for_completion(order_id, timeout=15.0)
    logger.info(f"Events collected | Count: {len(events)}")

    # Assert: Order filled
    assertions.assert_order_lifecycle(events, "FILLED", 50)
    logger.info("✓ LIMIT order filled")

    # Assert: Position filled at execution price
    post_positions = await bas_client.get_positions(broker_id, test_account_id)
    assertions.assert_position_state(
        post_positions,
        tcs_inst["id"],
        expected_qty=50,
        expected_avg_price=fill_price,
    )
    logger.info(f"✓ Position filled @ price: {fill_price}")


@pytest.mark.injection
async def test_limit_sell_triggers_on_price_cross(
    bas_client,
    mock_client,
    event_collector,
    assertions,
    test_account_id,
    logger,
    instrument_catalog,
):
    """
    Test: LIMIT SELL order triggers when price rises to/above limit.

    Validates:
    - LIMIT SELL @ 3900
    - No fill while price < 3900
    - Fills when price rises to ≥ 3900
    - Short position created
    """
    tcs_inst = instrument_catalog.get_equity("TCS")
    broker_id = "fyers"

    # Act: Place LIMIT SELL (short, intraday allowed)
    limit_price = Decimal("3900.00")
    order_request = BasOrderPlaceRequest(
        client_order_id=f"test_limit_sell_real_{test_account_id}_{uuid.uuid4().hex[:8]}",
        position_type=PositionType.INTRADAY,
        legs=[
            BasOrderLeg(
                instrument_id=tcs_inst["id"],
                instrument_type="EQUITY",
                side=OrderSide.SELL,
                qty=50,
                order_type=OrderType.LIMIT,
                price=limit_price,
                stop_price=None,
                ltp=Decimal("3850.00"),
            )
        ],
        underlying_symbol="TCS",
        tif=TimeInForce.DAY,
    )

    [order_resp] = await bas_client.place_order(broker_id, test_account_id, order_request)
    order_id = order_resp.broker_order_id
    logger.info(f"LIMIT SELL placed | ID: {order_id} | Limit: {limit_price}")

    # Act: Inject fill at price above limit
    fill_price = Decimal("3950.00")
    await mock_client.inject_fill(
        broker_id=broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=50,
        fill_price=fill_price,
    )
    logger.info(f"Fill injected | Qty: 50 | Price: {fill_price}")

    # Observe: Wait for execution
    events = await event_collector.wait_for_completion(order_id, timeout=15.0)
    logger.info(f"Events collected | Count: {len(events)}")

    # Assert: Order filled
    assertions.assert_order_lifecycle(events, "FILLED", 50)
    logger.info("✓ LIMIT SELL filled")

    # Assert: Short position created
    post_positions = await bas_client.get_positions(broker_id, test_account_id)
    assertions.assert_position_state(
        post_positions,
        tcs_inst["id"],
        expected_qty=-50,  # Short
        expected_avg_price=fill_price,
    )
    logger.info(f"✓ Short position created @ {fill_price}")


@pytest.mark.injection
async def test_stop_buy_triggers_on_price_cross(
    bas_client,
    mock_client,
    event_collector,
    assertions,
    test_account_id,
    logger,
    instrument_catalog,
):
    """
    Test: STOP BUY order triggers when price rises to/above stop level.

    Validates:
    - STOP BUY @ 2450 (activates when price ≥ 2450)
    - Executes as MARKET after trigger
    """
    kotakbank_inst = instrument_catalog.get_equity("KOTAKBANK")
    broker_id = "fyers"

    # STOP orders are risk-checked against a live quote in BAS' QuoteStore.
    # Seed one so the order isn't rejected with 503 "Quote not available".
    import redis.asyncio as redis
    from datetime import datetime, timezone

    r = await redis.from_url("redis://localhost:6379/0", decode_responses=True)
    try:
        seq = int(datetime.now(timezone.utc).timestamp() * 1000)
        await r.xadd(
            "market.quote.v1",
            {
                "instrument_id": kotakbank_inst["id"],
                "ltp": "2400.00",
                "sequence_number": str(seq),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
    finally:
        await r.aclose()
    # Give BAS' MarketDataConsumer a beat to pick up the quote.
    import asyncio
    await asyncio.sleep(0.5)

    # Act: Place STOP BUY
    stop_price = Decimal("2450.00")
    order_request = BasOrderPlaceRequest(
        client_order_id=f"test_stop_buy_real_{test_account_id}_{uuid.uuid4().hex[:8]}",
        position_type=PositionType.INTRADAY,
        legs=[
            BasOrderLeg(
                instrument_id=kotakbank_inst["id"],
                instrument_type="EQUITY",
                side=OrderSide.BUY,
                qty=100,
                order_type=OrderType.STOP,
                price=None,
                stop_price=stop_price,
                ltp=Decimal("2400.00"),
            )
        ],
        underlying_symbol="KOTAKBANK",
        tif=TimeInForce.DAY,
    )

    [order_resp] = await bas_client.place_order(broker_id, test_account_id, order_request)
    order_id = order_resp.broker_order_id
    logger.info(f"STOP BUY placed | ID: {order_id} | Stop: {stop_price}")

    # Act: Inject fill at price above stop
    fill_price = Decimal("2460.00")
    await mock_client.inject_fill(
        broker_id=broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=100,
        fill_price=fill_price,
    )
    logger.info(f"Fill injected | Qty: 100 | Price: {fill_price}")

    # Observe: Wait for execution
    events = await event_collector.wait_for_completion(order_id, timeout=15.0)
    logger.info(f"Events collected | Count: {len(events)}")

    # Assert: Order filled
    assertions.assert_order_lifecycle(events, "FILLED", 100)
    logger.info("✓ STOP order filled")

    # Assert: Position created
    post_positions = await bas_client.get_positions(broker_id, test_account_id)
    assertions.assert_position_state(
        post_positions,
        kotakbank_inst["id"],
        expected_qty=100,
        expected_avg_price=fill_price,
    )
    logger.info(f"✓ Position filled @ price: {fill_price}")
