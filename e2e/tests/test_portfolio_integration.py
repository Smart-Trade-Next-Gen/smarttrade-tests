"""Tests for Portfolio Service async aggregation after trades."""

import pytest
from decimal import Decimal

pytestmark = pytest.mark.injection  # Use deterministic fill injection


@pytest.mark.asyncio
async def test_portfolio_position_after_market_buy(
    config,
    instrument_catalog,
    test_account_id,
    auth_token,
    bas_client,
    mock_client,
    place_and_sync_order,
    portfolio_client,
    event_collector,
    assertions,
):
    """Test that Portfolio Service reflects position after market BUY fill."""
    # Setup
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]
    qty = 100
    price = Decimal("550.00")

    # Place order
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

    # Wait for execution
    await event_collector.wait_for_completion(order_id, timeout=config.timeout_medium)

    # Poll Portfolio Service for position (hard timeout, no silent failures)
    position = await portfolio_client.wait_for_position(
        instrument_id=instrument_id,
        expected_qty=qty,
        timeout=config.timeout_medium,
    )

    # Assertions (hard)
    assert position["net_qty"] == qty
    assert Decimal(position["avg_price"]) == price
    assert position["instrument_id"] == instrument_id


@pytest.mark.asyncio
async def test_portfolio_position_after_partial_fills(
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
    """Test that Portfolio Service aggregates WAP correctly after partial fills."""
    # Setup
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]
    total_qty = 100

    # Place order for 100 shares
    order_responses = await place_and_sync_order(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_request={
            "instrument_id": instrument_id,
            "position_type": "INTRADAY",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": total_qty,
        },
    )
    order_id = order_responses[0]["broker_order_id"]

    # Inject 2 partial fills: 50@550, 50@560
    fill1_qty, fill1_price = 50, Decimal("550.00")
    fill2_qty, fill2_price = 50, Decimal("560.00")

    await mock_client.inject_fill(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=1,
        fill_qty=fill1_qty,
        fill_price=fill1_price,
    )

    await mock_client.inject_fill(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_id=order_id,
        sequence=2,
        fill_qty=fill2_qty,
        fill_price=fill2_price,
    )

    # Wait for completion
    await event_collector.wait_for_completion(order_id, timeout=config.timeout_medium)

    # Poll Portfolio Service
    position = await portfolio_client.wait_for_position(
        instrument_id=instrument_id,
        expected_qty=total_qty,
        timeout=config.timeout_medium,
    )

    # Verify WAP: (50*550 + 50*560) / 100 = 555
    expected_wap = Decimal("555.00")
    actual_wap = Decimal(position["avg_price"])

    assert position["net_qty"] == total_qty
    assert actual_wap == expected_wap


@pytest.mark.asyncio
async def test_portfolio_position_closes_after_opposing_trade(
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
    """Test that Portfolio position closes (qty=0) after opposing trade."""
    # Setup
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]
    qty = 100
    buy_price = Decimal("550.00")
    sell_price = Decimal("560.00")

    # BUY 100
    buy_responses = await place_and_sync_order(
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
    buy_order_id = buy_responses[0]["broker_order_id"]

    # Fill BUY
    await mock_client.inject_fill(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_id=buy_order_id,
        sequence=1,
        fill_qty=qty,
        fill_price=buy_price,
    )

    await event_collector.wait_for_completion(buy_order_id, timeout=config.timeout_medium)

    # Verify position exists
    position = await portfolio_client.wait_for_position(
        instrument_id=instrument_id,
        expected_qty=qty,
        timeout=config.timeout_medium,
    )
    assert position["net_qty"] == qty

    # SELL 100 (opposite)
    sell_responses = await place_and_sync_order(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_request={
            "instrument_id": instrument_id,
            "position_type": "INTRADAY",
            "side": "SELL",
            "order_type": "MARKET",
            "qty": qty,
        },
    )
    sell_order_id = sell_responses[0]["broker_order_id"]

    # Fill SELL
    await mock_client.inject_fill(
        broker_id=config.broker_id,
        account_id=test_account_id,
        order_id=sell_order_id,
        sequence=1,
        fill_qty=qty,
        fill_price=sell_price,
    )

    await event_collector.wait_for_completion(sell_order_id, timeout=config.timeout_medium)

    # Verify position is closed or very small (qty=0 or near-zero due to rounding)
    positions = await portfolio_client.get_positions(instrument_id=instrument_id)
    # Position may be gone or have qty=0
    if positions:
        for pos in positions:
            if pos["instrument_id"] == instrument_id:
                assert int(pos["net_qty"]) == 0
