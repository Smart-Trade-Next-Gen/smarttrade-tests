"""
E2E tests for order lifecycle validation using injection mode.

Tests validate:
- Order placement and status transitions
- Deterministic fill injection
- Event sequence correctness (via Redis Streams)
- Financial invariant validation
- Broker state verification (source of truth)
- Position state tracking via Portfolio Service

All tests use INJECTION mode for deterministic execution.
Updated for v4.0 stateless architecture.
"""

import pytest
import uuid
from decimal import Decimal

from smarttrade_common.schemas.types import OrderSide, OrderType, TimeInForce, PositionType
from broker_adapter_service.schemas.order_dtos import BasOrderPlaceRequest, BasOrderLeg


@pytest.mark.smoke
@pytest.mark.injection
@pytest.mark.asyncio
async def test_market_buy_full_fill(
    config,
    instrument_catalog,
    bas_client,
    mock_client,
    redis_event_collector,
    broker_state_client,
    assertions,
    portfolio_client,
    test_account_id,
    logger,
):
    """
    Test: Market BUY order - full fill in single execution.

    Validates:
    - Order placement
    - Deterministic fill injection
    - Event collection via Redis Streams
    - Order lifecycle (PLACED → FILLED)
    - Financial invariants (debit correct)
    - Broker state verification (source of truth)
    - Position creation via Portfolio Service
    """
    broker_id = config.broker_id
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]
    qty = 100
    price = Decimal("550.00")

    # Arrange: Capture pre-state
    pre_funds = await bas_client.get_funds(broker_id, test_account_id)
    logger.info(f"Pre-state captured | Funds: {pre_funds.total_equity}")

    # Act: Create and place order
    order_request = BasOrderPlaceRequest(
        client_order_id=f"test_market_buy_{test_account_id}_{uuid.uuid4().hex[:8]}",
        position_type=PositionType.INTRADAY,
        legs=[
            BasOrderLeg(
                instrument_id=instrument_id,
                instrument_type="EQUITY",
                side=OrderSide.BUY,
                qty=qty,
                order_type=OrderType.MARKET,
                price=None,
                stop_price=None,
                ltp=price,
            )
        ],
        underlying_symbol=instrument["symbol"],
        tif=TimeInForce.DAY,
    )

    [order_resp] = await bas_client.place_order(broker_id, test_account_id, order_request)
    order_id = order_resp.broker_order_id
    logger.info(f"Order placed | ID: {order_id} | Status: {order_resp.status}")

    # Act: Inject deterministic fill
    await mock_client.inject_fill(
        broker_id=broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=qty,
        fill_price=price,
    )
    logger.info(f"Fill injected | Qty: {qty} | Price: {price}")

    # Observe: Wait for completion via Redis Streams
    events = await redis_event_collector.wait_for_completion(order_id, timeout=config.timeout_medium)
    logger.info(f"Events collected | Count: {len(events)}")

    # Assert: Order lifecycle with consolidated event schema
    assertions.assert_order_lifecycle(events, "FILLED", qty)
    logger.info("✓ Order lifecycle validated")

    # Assert: Status transitions correct
    assertions.assert_status_transition_correct(events, ["PLACED", "FILLED"])
    logger.info("✓ Status transitions validated")

    # Assert: Event sequence
    assertions.assert_no_duplicate_events(events)
    logger.info("✓ No duplicate events validated")

    # Assert: Broker state matches events (source of truth)
    broker_order = await broker_state_client.get_order_state(broker_id, test_account_id, order_id)
    assertions.assert_broker_state_matches_events(broker_order, events)
    logger.info("✓ Broker state matches events")

    # Assert: Financial invariants
    post_funds = await bas_client.get_funds(broker_id, test_account_id)
    assertions.assert_financial_invariants(
        pre_funds,
        post_funds,
        side="BUY",
        qty=qty,
        price=price,
    )
    logger.info("✓ Financial invariants validated")

    # Assert: Position state via Portfolio Service
    position = await portfolio_client.wait_for_position(
        instrument_id=instrument_id,
        expected_qty=qty,
        timeout=config.timeout_medium,
    )
    assert position["net_qty"] == qty
    assert Decimal(position["avg_price"]) == price
    logger.info("✓ Position state validated via Portfolio Service")


@pytest.mark.smoke
@pytest.mark.injection
@pytest.mark.asyncio
async def test_market_sell_full_fill(
    config,
    instrument_catalog,
    bas_client,
    mock_client,
    redis_event_collector,
    broker_state_client,
    assertions,
    portfolio_client,
    test_account_id,
    logger,
):
    """
    Test: Market SELL order - full fill in single execution.

    Validates:
    - SELL order flow (opposite of BUY)
    - Short position (intraday allowed)
    - Broker state verification
    - Position state for SHORT via Portfolio Service
    """
    broker_id = config.broker_id
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]
    qty = 100
    price = Decimal("550.00")

    # Arrange: Capture pre-state
    pre_funds = await bas_client.get_funds(broker_id, test_account_id)
    logger.info(f"Pre-state captured | Funds: {pre_funds.total_equity}")

    # Act: Create and place order
    order_request = BasOrderPlaceRequest(
        client_order_id=f"test_market_sell_{test_account_id}_{uuid.uuid4().hex[:8]}",
        position_type=PositionType.INTRADAY,
        legs=[
            BasOrderLeg(
                instrument_id=instrument_id,
                instrument_type="EQUITY",
                side=OrderSide.SELL,
                qty=qty,
                order_type=OrderType.MARKET,
                price=None,
                stop_price=None,
                ltp=price,
            )
        ],
        underlying_symbol=instrument["symbol"],
        tif=TimeInForce.DAY,
    )

    [order_resp] = await bas_client.place_order(broker_id, test_account_id, order_request)
    order_id = order_resp.broker_order_id
    logger.info(f"Order placed | ID: {order_id} | Status: {order_resp.status}")

    # Act: Inject deterministic fill
    await mock_client.inject_fill(
        broker_id=broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=qty,
        fill_price=price,
    )
    logger.info(f"Fill injected | Qty: {qty} | Price: {price}")

    # Observe: Wait for completion via Redis Streams
    events = await redis_event_collector.wait_for_completion(order_id, timeout=config.timeout_medium)
    logger.info(f"Events collected | Count: {len(events)}")

    # Assert: Order lifecycle
    assertions.assert_order_lifecycle(events, "FILLED", qty)
    logger.info("✓ Order lifecycle validated")

    # Assert: Status transitions correct
    assertions.assert_status_transition_correct(events, ["PLACED", "FILLED"])
    logger.info("✓ Status transitions validated")

    # Assert: Event sequence
    assertions.assert_no_duplicate_events(events)
    logger.info("✓ No duplicate events validated")

    # Assert: Broker state matches events
    broker_order = await broker_state_client.get_order_state(broker_id, test_account_id, order_id)
    assertions.assert_broker_state_matches_events(broker_order, events)
    logger.info("✓ Broker state matches events")

    # Assert: Financial invariants
    post_funds = await bas_client.get_funds(broker_id, test_account_id)
    assertions.assert_financial_invariants(
        pre_funds,
        post_funds,
        side="SELL",
        qty=qty,
        price=price,
    )
    logger.info("✓ Financial invariants validated")

    # Assert: Position state (negative for SHORT) via Portfolio Service
    position = await portfolio_client.wait_for_position(
        instrument_id=instrument_id,
        expected_qty=-qty,
        timeout=config.timeout_medium,
    )
    assert position["net_qty"] == -qty
    assert Decimal(position["avg_price"]) == price
    logger.info("✓ Position state validated (short position) via Portfolio Service")


@pytest.mark.injection
@pytest.mark.asyncio
async def test_limit_buy_triggers_at_price(
    config,
    instrument_catalog,
    bas_client,
    mock_client,
    redis_event_collector,
    broker_state_client,
    assertions,
    portfolio_client,
    test_account_id,
    logger,
):
    """
    Test: LIMIT BUY order - validates execution at price.

    Validates:
    - LIMIT order placement
    - Fill occurs at limit price (not above)
    - Limit order semantics (BUY ≤ limit_price)
    - Broker state verification
    - Position state via Portfolio Service
    """
    broker_id = config.broker_id
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]
    qty = 50

    # Arrange: Capture pre-state
    pre_funds = await bas_client.get_funds(broker_id, test_account_id)
    logger.info(f"Pre-state captured | Funds: {pre_funds.total_equity}")

    # Act: Create and place order
    limit_price = Decimal("550.00")
    order_request = BasOrderPlaceRequest(
        client_order_id=f"test_limit_buy_{test_account_id}_{uuid.uuid4().hex[:8]}",
        position_type=PositionType.INTRADAY,
        legs=[
            BasOrderLeg(
                instrument_id=instrument_id,
                instrument_type="EQUITY",
                side=OrderSide.BUY,
                qty=qty,
                order_type=OrderType.LIMIT,
                price=limit_price,
                stop_price=None,
                ltp=limit_price,
            )
        ],
        underlying_symbol=instrument["symbol"],
        tif=TimeInForce.DAY,
    )

    [order_resp] = await bas_client.place_order(broker_id, test_account_id, order_request)
    order_id = order_resp.broker_order_id
    logger.info(f"Order placed | ID: {order_id} | Status: {order_resp.status}")

    # Act: Inject fill at limit price
    await mock_client.inject_fill(
        broker_id=broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=qty,
        fill_price=limit_price,
    )
    logger.info(f"Fill injected | Qty: {qty} | Price: {limit_price}")

    # Observe: Wait for completion via Redis Streams
    events = await redis_event_collector.wait_for_completion(order_id, timeout=config.timeout_medium)
    logger.info(f"Events collected | Count: {len(events)}")

    # Assert: Order lifecycle
    assertions.assert_order_lifecycle(events, "FILLED", qty)
    logger.info("✓ Order lifecycle validated")

    # Assert: Status transitions correct
    assertions.assert_status_transition_correct(events, ["PLACED", "FILLED"])
    logger.info("✓ Status transitions validated")

    # Assert: Broker state matches events
    broker_order = await broker_state_client.get_order_state(broker_id, test_account_id, order_id)
    assertions.assert_broker_state_matches_events(broker_order, events)
    logger.info("✓ Broker state matches events")

    # Assert: Fill price matches limit price
    fill_price = Decimal(str(broker_order.get("price", "0")))
    assert fill_price == limit_price, f"Fill price {fill_price} != limit price {limit_price}"
    logger.info(f"✓ Fill price matches limit price: {fill_price}")

    # Assert: Position state via Portfolio Service
    position = await portfolio_client.wait_for_position(
        instrument_id=instrument_id,
        expected_qty=qty,
        timeout=config.timeout_medium,
    )
    assert position["net_qty"] == qty
    assert Decimal(position["avg_price"]) == limit_price
    logger.info("✓ Position state validated via Portfolio Service")


@pytest.mark.injection
@pytest.mark.asyncio
async def test_limit_sell_triggers_at_price(
    config,
    instrument_catalog,
    bas_client,
    mock_client,
    redis_event_collector,
    broker_state_client,
    assertions,
    portfolio_client,
    test_account_id,
    logger,
):
    """
    Test: LIMIT SELL order - validates execution at price.

    Validates:
    - LIMIT SELL placement
    - Fill occurs at limit price (not below)
    - Limit order semantics (SELL ≥ limit_price)
    - Broker state verification
    - Position state via Portfolio Service
    """
    broker_id = config.broker_id
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]
    qty = 50

    # Arrange: Capture pre-state
    pre_funds = await bas_client.get_funds(broker_id, test_account_id)
    logger.info(f"Pre-state captured | Funds: {pre_funds.total_equity}")

    # Act: Create and place order
    limit_price = Decimal("560.00")
    order_request = BasOrderPlaceRequest(
        client_order_id=f"test_limit_sell_{test_account_id}_{uuid.uuid4().hex[:8]}",
        position_type=PositionType.INTRADAY,
        legs=[
            BasOrderLeg(
                instrument_id=instrument_id,
                instrument_type="EQUITY",
                side=OrderSide.SELL,
                qty=qty,
                order_type=OrderType.LIMIT,
                price=limit_price,
                stop_price=None,
                ltp=limit_price,
            )
        ],
        underlying_symbol=instrument["symbol"],
        tif=TimeInForce.DAY,
    )

    [order_resp] = await bas_client.place_order(broker_id, test_account_id, order_request)
    order_id = order_resp.broker_order_id
    logger.info(f"Order placed | ID: {order_id} | Status: {order_resp.status}")

    # Act: Inject fill at limit price
    await mock_client.inject_fill(
        broker_id=broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=qty,
        fill_price=limit_price,
    )
    logger.info(f"Fill injected | Qty: {qty} | Price: {limit_price}")

    # Observe: Wait for completion via Redis Streams
    events = await redis_event_collector.wait_for_completion(order_id, timeout=config.timeout_medium)
    logger.info(f"Events collected | Count: {len(events)}")

    # Assert: Order lifecycle
    assertions.assert_order_lifecycle(events, "FILLED", qty)
    logger.info("✓ Order lifecycle validated")

    # Assert: Status transitions correct
    assertions.assert_status_transition_correct(events, ["PLACED", "FILLED"])
    logger.info("✓ Status transitions validated")

    # Assert: Broker state matches events
    broker_order = await broker_state_client.get_order_state(broker_id, test_account_id, order_id)
    assertions.assert_broker_state_matches_events(broker_order, events)
    logger.info("✓ Broker state matches events")

    # Assert: Fill price matches limit price
    fill_price = Decimal(str(broker_order.get("price", "0")))
    assert fill_price == limit_price, f"Fill price {fill_price} != limit price {limit_price}"
    logger.info(f"✓ Fill price matches limit price: {fill_price}")

    # Assert: Position state via Portfolio Service
    position = await portfolio_client.wait_for_position(
        instrument_id=instrument_id,
        expected_qty=-qty,
        timeout=config.timeout_medium,
    )
    assert position["net_qty"] == -qty
    assert Decimal(position["avg_price"]) == limit_price
    logger.info("✓ Position state validated via Portfolio Service")
