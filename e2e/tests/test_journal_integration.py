"""Tests for Journal Service trade audit trail."""

import pytest
from decimal import Decimal

pytestmark = pytest.mark.injection


@pytest.mark.asyncio
async def test_journal_trade_recorded_after_fill(
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
    """Test that Journal Service records trade after fill is executed."""
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

    # Wait for execution
    await event_collector.wait_for_completion(order_id, timeout=config.timeout_medium)

    # Poll Journal Service for trade (hard timeout)
    trade = await journal_client.wait_for_trade(
        order_id=order_id,
        timeout=config.timeout_medium,
    )

    # Assertions
    assert trade["order_id"] == order_id
    assert int(trade["quantity"]) == qty
    assert Decimal(trade["price"]) == price


@pytest.mark.asyncio
async def test_journal_entry_created_after_fill(
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
    """Test that Journal Service creates journal entry for traded instrument."""
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

    # Wait for execution
    await event_collector.wait_for_completion(order_id, timeout=config.timeout_medium)

    # Poll Journal Service for entry
    entry = await journal_client.wait_for_journal_entry(
        instrument_id=instrument_id,
        lifecycle_status="OPEN",
        timeout=config.timeout_medium,
    )

    # Assertions
    assert entry["instrument_id"] == instrument_id
    assert entry["lifecycle_status"] == "OPEN"


@pytest.mark.asyncio
async def test_journal_records_correct_side_and_qty(
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
    """Test that Journal records correct side, quantity, and price."""
    # Setup
    instrument = instrument_catalog.get_any_equity(1)[0]
    instrument_id = instrument["id"]
    qty = 100
    price = Decimal("550.00")

    # BUY order
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

    # Get trade from journal
    trade = await journal_client.wait_for_trade(
        order_id=order_id,
        timeout=config.timeout_medium,
    )

    # Assertions
    assert trade["side"] == "BUY"
    assert int(trade["quantity"]) == qty
    assert Decimal(trade["price"]) == price
    assert trade["instrument_id"] == instrument_id
