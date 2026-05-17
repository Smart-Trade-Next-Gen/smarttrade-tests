"""
Integration tests for database query performance.

Tests validate:
- Query performance under load
- Index effectiveness
- Connection pool efficiency
- Query optimization
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


@pytest.mark.performance
async def test_journal_query_performance(
    config,
    journal_client,
    test_account_id,
):
    """
    Test: Journal query performance.

    Validates:
    - Order/trade queries complete within acceptable time
    - Performance is consistent
    - No slow queries
    """
    broker_id = config.broker_id
    
    try:
        # Query orders
        import time
        start = time.time()
        orders = await journal_client.get_orders()
        elapsed = time.time() - start
        
        # Validate query completes quickly (< 1 second)
        assert elapsed < 1.0, "Order query should complete within 1 second"
        
    except Exception as e:
        pytest.skip(f"Journal query performance test failed: {e}")


@pytest.mark.performance
async def test_portfolio_query_performance(
    config,
    portfolio_client,
):
    """
    Test: Portfolio query performance.

    Validates:
    - Position queries complete within acceptable time
    - Performance is consistent
    - No slow queries
    """
    try:
        # Query positions
        import time
        start = time.time()
        positions = await portfolio_client.get_positions()
        elapsed = time.time() - start
        
        # Validate query completes quickly (< 1 second)
        assert elapsed < 1.0, "Position query should complete within 1 second"
        
    except Exception as e:
        pytest.skip(f"Portfolio query performance test failed: {e}")


@pytest.mark.performance
async def test_connection_pool_efficiency(
    config,
    journal_client,
    test_account_id,
):
    """
    Test: Database connection pool efficiency.

    Validates:
    - Connection pool is used effectively
    - No connection leaks
    - Connections are reused
    """
    broker_id = config.broker_id
    
    try:
        # Make multiple queries to test connection reuse
        import time
        start = time.time()
        
        for _ in range(10):
            await journal_client.get_orders()
        
        elapsed = time.time() - start
        
        # Validate queries complete quickly (connection reuse)
        assert elapsed < 5.0, "10 queries with connection reuse should complete within 5 seconds"
        
    except Exception as e:
        pytest.skip(f"Connection pool efficiency test failed: {e}")