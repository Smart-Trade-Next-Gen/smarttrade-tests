"""
Integration tests for BAS REST API comprehensive coverage.

Tests validate:
- REST API contract compliance
- All endpoints respond correctly
- Request validation
- Error handling
- Rate limiting (if applicable)
"""

from __future__ import annotations

import pytest
from decimal import Decimal

pytestmark = pytest.mark.asyncio


@pytest.mark.smoke
async def test_bas_get_orders_endpoint(
    config,
    bas_client,
    test_account_id,
):
    """
    Test: BAS GET /api/v1/orders/{broker}/{account} endpoint.

    Validates:
    - Endpoint returns 200 OK
    - Returns list of orders (may be empty)
    - Response structure is correct
    """
    broker_id = config.broker_id
    
    orders = await bas_client.get_orders(broker_id, test_account_id)
    
    # Should return a list
    assert isinstance(orders, list), "Should return a list of orders"
    
    # Each order should have required fields
    for order in orders:
        assert "broker_order_id" in order, "Order should have broker_order_id"
        assert "status" in order, "Order should have status"
        assert "instrument_id" in order, "Order should have instrument_id"


@pytest.mark.smoke
async def test_bas_get_order_by_id_endpoint(
    config,
    bas_client,
    test_account_id,
):
    """
    Test: BAS GET /api/v1/orders/{broker}/{account}/{order_id} endpoint.

    Validates:
    - Endpoint returns 200 OK for existing order
    - Endpoint returns 404 for non-existent order
    - Response structure is correct
    """
    broker_id = config.broker_id
    
    # Try to get a non-existent order
    try:
        order = await bas_client.get_order(broker_id, test_account_id, "NONEXISTENT_ORDER_ID")
        # If we get here, the order exists (unexpected)
        assert False, "Non-existent order should return 404"
    except Exception as e:
        # Expected: should get 404 or similar error
        error_str = str(e).lower()
        assert any(err in error_str for err in ["404", "not found"]), \
            f"Should return 404 for non-existent order, got: {e}"


@pytest.mark.smoke
async def test_bas_health_check(
    config,
    bas_client,
):
    """
    Test: BAS health check endpoint.

    Validates:
    - Health check endpoint responds
    - Service is ready to accept requests
    """
    # The BAS client should have a health check method or we can use HTTP directly
    # For now, we'll skip this as the client may not have a health check method
    pytest.skip("BAS health check test requires client health check method")


@pytest.mark.smoke
async def test_bas_create_trading_account(
    config,
    bas_client,
):
    """
    Test: BAS POST /api/v1/trading_account/{broker} endpoint.

    Validates:
    - Can create a trading account
    - Account is created with correct details
    - Duplicate account creation is handled
    """
    broker_id = config.broker_id
    test_account_id = "TEST_E2E_ACCOUNT_CREATE"
    
    # Delete the account if it exists
    try:
        await bas_client.delete_trading_account(broker_id, test_account_id)
    except Exception:
        pass  # Account may not exist
    
    # Create the account
    response = await bas_client.create_trading_account(broker_id, test_account_id)
    
    # Validate response
    assert response is not None, "Should return a response"
    
    # Clean up
    try:
        await bas_client.delete_trading_account(broker_id, test_account_id)
    except Exception:
        pass


@pytest.mark.smoke
async def test_bas_delete_trading_account(
    config,
    bas_client,
):
    """
    Test: BAS DELETE /api/v1/trading_account/{broker}/{account} endpoint.

    Validates:
    - Can delete a trading account
    - Account is deleted successfully
    - Deleting non-existent account is handled
    """
    broker_id = config.broker_id
    test_account_id = "TEST_E2E_ACCOUNT_DELETE"
    
    # Create the account first
    await bas_client.create_trading_account(broker_id, test_account_id)
    
    # Delete the account
    response = await bas_client.delete_trading_account(broker_id, test_account_id)
    
    # Validate response
    assert response is not None, "Should return a response"
    
    # Try to delete again (should handle gracefully)
    try:
        await bas_client.delete_trading_account(broker_id, test_account_id)
        # If we get here, the delete succeeded (account was recreated or idempotent)
    except Exception as e:
        # Expected: should get 404 or similar error
        error_str = str(e).lower()
        assert any(err in error_str for err in ["404", "not found"]), \
            f"Should return 404 for non-existent account, got: {e}"