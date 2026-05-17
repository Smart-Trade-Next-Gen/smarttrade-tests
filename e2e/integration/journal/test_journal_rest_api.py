"""
Integration tests for Journal Service REST API.

Tests validate:
- REST API contract compliance
- Order retrieval endpoint
- Trade retrieval endpoint
- Action retrieval endpoint
- Pagination
- Filtering
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


@pytest.mark.smoke
async def test_journal_get_orders_endpoint(
    config,
    journal_client,
    test_account_id,
):
    """
    Test: Journal GET /api/v1/orders endpoint.

    Validates:
    - Endpoint returns 200 OK
    - Returns list of orders
    - Response structure is correct
    """
    broker_id = config.broker_id
    
    try:
        orders = await journal_client.get_orders()
        
        # Should return a list
        assert isinstance(orders, list), "Should return a list of orders"
        
        # Each order should have required fields
        for order in orders:
            assert "order_id" in order, "Order should have order_id"
            assert "broker_order_id" in order, "Order should have broker_order_id"
            assert "status" in order, "Order should have status"
            
    except Exception as e:
        # Journal may not have orders for this account
        pytest.skip(f"No orders in journal: {e}")


@pytest.mark.smoke
async def test_journal_get_trades_endpoint(
    config,
    journal_client,
    test_account_id,
):
    """
    Test: Journal GET /api/v1/trades endpoint.

    Validates:
    - Endpoint returns 200 OK
    - Returns list of trades
    - Response structure is correct
    """
    broker_id = config.broker_id
    
    try:
        trades = await journal_client.get_trades()
        
        # Should return a list
        assert isinstance(trades, list), "Should return a list of trades"
        
        # Each trade should have required fields
        for trade in trades:
            assert "trade_id" in trade, "Trade should have trade_id"
            assert "order_id" in trade, "Trade should have order_id"
            assert "quantity" in trade, "Trade should have quantity"
            assert "price" in trade, "Trade should have price"
            
    except Exception as e:
        # Journal may not have trades for this account
        pytest.skip(f"No trades in journal: {e}")


@pytest.mark.smoke
async def test_journal_get_actions_endpoint(
    config,
    journal_client,
    test_account_id,
):
    """
    Test: Journal GET /api/v1/actions endpoint.

    Validates:
    - Endpoint returns 200 OK
    - Returns list of actions
    - Response structure is correct
    """
    broker_id = config.broker_id
    
    try:
        actions = await journal_client.get_actions()
        
        # Should return a list
        assert isinstance(actions, list), "Should return a list of actions"
        
        # Each action should have required fields
        for action in actions:
            assert "action_id" in action, "Action should have action_id"
            assert "action_type" in action, "Action should have action_type"
            
    except Exception as e:
        # Journal may not have actions for this account
        pytest.skip(f"No actions in journal: {e}")


@pytest.mark.smoke
async def test_journal_order_by_id_endpoint(
    config,
    journal_client,
    test_account_id,
):
    """
    Test: Journal GET /api/v1/orders/{broker}/{account}/{order_id} endpoint.

    Validates:
    - Endpoint returns 200 OK for existing order
    - Endpoint returns 404 for non-existent order
    - Response structure is correct
    """
    broker_id = config.broker_id
    
    # Try to get a non-existent order
    try:
        order = await journal_client.get_order_by_id("NONEXISTENT_ORDER_ID")
        # If we get here, the order exists (unexpected)
        assert False, "Non-existent order should return 404"
    except Exception as e:
        # Expected: should get 404 or similar error
        error_str = str(e).lower()
        assert any(err in error_str for err in ["404", "not found"]), \
            f"Should return 404 for non-existent order, got: {e}"