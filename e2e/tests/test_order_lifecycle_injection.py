"""
E2E tests for order lifecycle validation using injection mode.

Tests validate:
- Order placement and status transitions
- Deterministic fill injection
- Event sequence correctness
- Financial invariant validation
- Position state tracking via Portfolio Service

All tests use INJECTION mode for deterministic execution.
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
    event_collector,
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
    - Event collection
    - Order lifecycle (PENDING → FILLED)
    - Financial invariants (debit correct)
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

    # Observe: Wait for completion
    events = await event_collector.wait_for_completion(order_id, timeout=config.timeout_medium)
    logger.info(f"Events collected | Count: {len(events)}")

    # Assert: Order lifecycle
    assertions.assert_order_lifecycle(events, "FILLED", qty)
    logger.info("✓ Order lifecycle validated")

    # Assert: Event sequence
    assertions.assert_no_duplicate_events(events)
    assertions.assert_sequence_order(events)
    logger.info("✓ Event sequence validated")

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

    # Assert: Position state via Portfolio Service (correct source of truth)
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
    event_collector,
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

    # Observe: Wait for completion
    events = await event_collector.wait_for_completion(order_id, timeout=config.timeout_medium)
    logger.info(f"Events collected | Count: {len(events)}")

    # Assert: Order lifecycle
    assertions.assert_order_lifecycle(events, "FILLED", qty)
    logger.info("✓ Order lifecycle validated")

    # Assert: Event sequence
    assertions.assert_no_duplicate_events(events)
    assertions.assert_sequence_order(events)
    logger.info("✓ Event sequence validated")

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
    event_collector,
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
                ltp=Decimal("551.00"),
            )
        ],
        underlying_symbol=instrument["symbol"],
        tif=TimeInForce.DAY,
    )

    [order_resp] = await bas_client.place_order(broker_id, test_account_id, order_request)
    order_id = order_resp.broker_order_id
    logger.info(f"Order placed | ID: {order_id} | Limit: {limit_price}")

    # Act: Inject fill at price below limit (valid trigger)
    fill_price = Decimal("549.50")
    await mock_client.inject_fill(
        broker_id=broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=qty,
        fill_price=fill_price,
    )
    logger.info(f"Fill injected | Qty: {qty} | Price: {fill_price} (≤ limit {limit_price})")

    # Observe: Wait for completion
    events = await event_collector.wait_for_completion(order_id, timeout=config.timeout_medium)
    logger.info(f"Events collected | Count: {len(events)}")

    # Assert: Order lifecycle
    assertions.assert_order_lifecycle(events, "FILLED", qty)
    logger.info("✓ Order lifecycle validated")

    # Assert: Execution trigger (BUY fill at price ≤ limit)
    assertions.assert_execution_trigger(
        events,
        order_type="LIMIT",
        limit_price=limit_price,
        execution_price=fill_price,
    )
    logger.info("✓ Execution trigger validated (fill ≤ limit)")

    # Assert: Position state via Portfolio Service
    position = await portfolio_client.wait_for_position(
        instrument_id=instrument_id,
        expected_qty=qty,
        timeout=config.timeout_medium,
    )
    assert position["net_qty"] == qty
    assert Decimal(position["avg_price"]) == fill_price
    logger.info("✓ Position state validated via Portfolio Service")


@pytest.mark.injection
@pytest.mark.asyncio
async def test_limit_sell_triggers_at_price(
    config,
    instrument_catalog,
    bas_client,
    mock_client,
    event_collector,
    assertions,
    portfolio_client,
    test_account_id,
    logger,
):
    """
    Test: LIMIT SELL order - validates execution at price.

    Validates:
    - LIMIT SELL order placement
    - Fill occurs at limit price (not below)
    - Limit order semantics (SELL ≥ limit_price)
    - Position state via Portfolio Service
    """
    broker_id = config.broker_id
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]
    qty = 50

    # Arrange: Capture pre-state
    pre_funds = await bas_client.get_funds(broker_id, test_account_id)

    # Act: Create and place order
    limit_price = Decimal("550.00")
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
                ltp=Decimal("549.00"),
            )
        ],
        underlying_symbol=instrument["symbol"],
        tif=TimeInForce.DAY,
    )

    [order_resp] = await bas_client.place_order(broker_id, test_account_id, order_request)
    order_id = order_resp.broker_order_id
    logger.info(f"Order placed | ID: {order_id} | Limit: {limit_price}")

    # Act: Inject fill at price above limit (valid trigger)
    fill_price = Decimal("551.00")
    await mock_client.inject_fill(
        broker_id=broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=qty,
        fill_price=fill_price,
    )
    logger.info(f"Fill injected | Qty: {qty} | Price: {fill_price} (≥ limit {limit_price})")

    # Observe: Wait for completion
    events = await event_collector.wait_for_completion(order_id, timeout=config.timeout_medium)

    # Assert: Order lifecycle
    assertions.assert_order_lifecycle(events, "FILLED", qty)
    logger.info("✓ Order lifecycle validated")

    # Assert: Execution trigger (SELL fill at price ≥ limit)
    assertions.assert_execution_trigger(
        events,
        order_type="LIMIT",
        limit_price=limit_price,
        execution_price=fill_price,
    )
    logger.info("✓ Execution trigger validated (fill ≥ limit)")

    # Assert: Position state via Portfolio Service
    position = await portfolio_client.wait_for_position(
        instrument_id=instrument_id,
        expected_qty=-qty,
        timeout=config.timeout_medium,
    )
    assert position["net_qty"] == -qty
    assert Decimal(position["avg_price"]) == fill_price
    logger.info("✓ Position state validated (short) via Portfolio Service")
