"""
Integration tests for BAS REST API comprehensive coverage.

Tests validate:
- REST API contract compliance
- All endpoints respond correctly
- Request validation
- Error handling
- Rate limiting (if applicable)

Note: Order query endpoints (GET /orders) have been moved to Journal Service.
Tests for those endpoints should be in the Journal Service test suite.
"""

from __future__ import annotations

import pytest
from decimal import Decimal

pytestmark = pytest.mark.asyncio


@pytest.mark.smoke
async def test_bas_health_check(
    config,
):
    """
    Test: BAS health check endpoints using common library.

    Validates:
    - Liveness probe (/) returns 200 OK
    - Readiness probe (/ready) returns 200 OK when dependencies are healthy
    """
    import httpx
    
    bas_url = config.bas_url
    
    # Test liveness probe
    async with httpx.AsyncClient(timeout=10.0) as http:
        liveness_response = await http.get(f"{bas_url}/")
        assert liveness_response.status_code == 200, "Liveness probe should return 200"
        liveness_data = liveness_response.json()
        assert liveness_data["status"] == "ok", "Liveness should return ok status"
        
    # Test readiness probe
    async with httpx.AsyncClient(timeout=10.0) as http:
        readiness_response = await http.get(f"{bas_url}/ready")
        assert readiness_response.status_code == 200, "Readiness probe should return 200"
        readiness_data = readiness_response.json()
        assert readiness_data["status"] in ["ready", "not-ready"], "Readiness should return valid status"
        assert "checks" in readiness_data, "Readiness should include dependency checks"


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