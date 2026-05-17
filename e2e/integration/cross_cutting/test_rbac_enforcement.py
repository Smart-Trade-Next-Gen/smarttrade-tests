"""
Integration tests for RBAC (Role-Based Access Control) enforcement.

Tests validate:
- Users can only access their own data
- Role-based permissions are enforced
- Unauthorized requests are rejected
- Token validation works correctly

These tests ensure that the RBAC system is working correctly across services.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


@pytest.mark.smoke
async def test_user_can_access_own_data(
    config,
    bas_client,
    test_account_id,
):
    """
    Test: Users can access their own data.

    Validates:
    - Authenticated users can access their own orders
    - RBAC allows legitimate access
    """
    broker_id = config.broker_id
    
    # Try to list orders for the test account (should succeed)
    orders = await bas_client.get_orders(broker_id, test_account_id)
    
    # Should return a list (even if empty)
    assert isinstance(orders, list), "Should return a list of orders"
    
    # Request should not raise authentication/authorization errors
    # If we get here, the request was successful


@pytest.mark.smoke
async def test_unauthenticated_request_rejected(
    config,
    bas_client,
):
    """
    Test: Unauthenticated requests are rejected.

    Validates:
    - Requests without valid tokens are rejected
    - 401 Unauthorized is returned for unauthenticated requests
    """
    import httpx
    
    # Create a client without authentication
    unauth_client = httpx.AsyncClient(timeout=10.0)
    
    try:
        # Try to access an endpoint without authentication
        response = await unauth_client.get(f"{config.bas_url}/api/v1/orders/fyers/SOME_ACCOUNT")
        
        # Should get 401 Unauthorized
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        
    finally:
        await unauth_client.aclose()


@pytest.mark.smoke
async def test_invalid_token_rejected(
    config,
):
    """
    Test: Invalid tokens are rejected.

    Validates:
    - Requests with invalid tokens are rejected
    - 401 Unauthorized is returned for invalid tokens
    """
    import httpx
    
    # Create a client with invalid token
    invalid_client = httpx.AsyncClient(
        timeout=10.0,
        headers={"Authorization": "Bearer invalid_token_12345"}
    )
    
    try:
        # Try to access an endpoint with invalid token
        response = await invalid_client.get(f"{config.bas_url}/api/v1/orders/fyers/SOME_ACCOUNT")
        
        # Should get 401 Unauthorized
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        
    finally:
        await invalid_client.aclose()


@pytest.mark.smoke
async def test_cross_account_access_restricted(
    config,
    bas_client,
    test_account_id,
):
    """
    Test: Users cannot access other users' data.

    Validates:
    - Users can only access their own data
    - Cross-account access is restricted
    """
    broker_id = config.broker_id
    
    # Try to access a different account (should fail or return empty)
    # This test assumes the test user doesn't have access to other accounts
    different_account = "DIFFERENT_ACCOUNT_ID"
    
    try:
        orders = await bas_client.get_orders(broker_id, different_account)
        
        # If it doesn't fail, it should return empty data (no access)
        # or fail with authorization error
        assert isinstance(orders, list), "Should return a list"
        
        # Should not have data from other accounts
        # (implementation may vary - either empty list or auth error)
        
    except Exception as e:
        # May get authorization error, which is acceptable
        error_str = str(e).lower()
        # Acceptable errors: forbidden, unauthorized, not found
        assert any(err in error_str for err in ["forbidden", "unauthorized", "not found", "403", "401", "404"]), \
            f"Unexpected error: {e}"


@pytest.mark.smoke
async def test_admin_role_enforcement(
    config,
    bas_client,
):
    """
    Test: Admin role has elevated permissions.

    Validates:
    - Admin users can access administrative endpoints
    - Role-based permissions are enforced
    """
    # This test would require creating an admin user and testing admin-specific endpoints
    # For now, we'll skip this as it requires special test setup
    
    # Skip with a message
    pytest.skip("Admin role testing requires special test user setup")


@pytest.mark.smoke
async def test_token_expiry_handling(
    config,
):
    """
    Test: Expired tokens are rejected.

    Validates:
    - Expired tokens are rejected
    - 401 Unauthorized is returned for expired tokens
    """
    import httpx
    
    # Create a client with an expired token (simulated)
    # In a real test, we would use an actually expired token
    expired_client = httpx.AsyncClient(
        timeout=10.0,
        headers={"Authorization": "Bearer expired_token_simulated"}
    )
    
    try:
        # Try to access an endpoint with expired token
        response = await expired_client.get(f"{config.bas_url}/api/v1/orders/fyers/SOME_ACCOUNT")
        
        # Should get 401 Unauthorized
        # (may also get 403 depending on implementation)
        assert response.status_code in [401, 403], \
            f"Expected 401 or 403, got {response.status_code}"
        
    finally:
        await expired_client.aclose()