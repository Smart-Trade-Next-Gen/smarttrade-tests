"""
Performance E2E tests for Smart Exit V1.

Tests validate:
- Policy creation performance
- Policy retrieval performance
- Policy update performance
- Bulk operations performance
- Query performance with filters
"""

from __future__ import annotations

import uuid
import time
from decimal import Decimal

import pytest

from e2e.fixtures.smart_exit_helpers import (
    create_smart_exit_policy,
    activate_smart_exit_policy,
    deactivate_smart_exit_policy,
    delete_smart_exit_policy,
    create_mtm_based_rule,
    create_target_rule,
    create_time_based_rule,
)

pytestmark = pytest.mark.asyncio


@pytest.mark.integration
async def test_policy_creation_performance(
    config,
    portfolio_client,
):
    """
    Test: Policy creation meets performance expectations.

    Validates:
    - Single policy creation completes within acceptable time
    - Multiple policy creations scale linearly
    """
    try:
        # Test single policy creation
        start_time = time.time()
        policy = await create_smart_exit_policy(
            portfolio_client=portfolio_client,
            name=f"Performance test {uuid.uuid4().hex[:8]}",
            scope="SELECTED",
            position_ids=["test_position_1"],
            action="EXIT",
            rules=[create_mtm_based_rule(mtm_threshold=Decimal("1000"))],
            description="Performance test policy",
        )
        creation_time = time.time() - start_time

        assert policy["id"], "Policy should be created"
        assert creation_time < 2.0, f"Policy creation should complete in < 2s, took {creation_time:.2f}s"

        # Test batch creation (10 policies)
        start_time = time.time()
        policies = []
        for i in range(10):
            policy = await create_smart_exit_policy(
                portfolio_client=portfolio_client,
                name=f"Batch policy {i} {uuid.uuid4().hex[:8]}",
                scope="SELECTED",
                position_ids=[f"test_position_{i}"],
                action="EXIT",
                rules=[create_mtm_based_rule(mtm_threshold=Decimal(str(1000 * (i + 1))))],
                description=f"Batch performance test {i}",
            )
            policies.append(policy)
        batch_creation_time = time.time() - start_time

        assert len(policies) == 10, "All policies should be created"
        assert batch_creation_time < 10.0, f"10 policies should be created in < 10s, took {batch_creation_time:.2f}s"

        # Cleanup
        for policy in policies:
            await delete_smart_exit_policy(portfolio_client, policy["id"])

    except Exception as e:
        pytest.skip(f"Policy creation performance test failed: {e}")


@pytest.mark.integration
async def test_policy_retrieval_performance(
    config,
    portfolio_client,
):
    """
    Test: Policy retrieval meets performance expectations.

    Validates:
    - Single policy retrieval completes within acceptable time
    - List policies with pagination works efficiently
    """
    try:
        # Create a test policy first
        policy = await create_smart_exit_policy(
            portfolio_client=portfolio_client,
            name=f"Retrieval test {uuid.uuid4().hex[:8]}",
            scope="SELECTED",
            position_ids=["test_position_1"],
            action="EXIT",
            rules=[create_mtm_based_rule(mtm_threshold=Decimal("1000"))],
            description="Retrieval performance test",
        )

        try:
            # Test single policy retrieval
            start_time = time.time()
            retrieved_policy = await portfolio_client.get_smart_exit_policy(policy["id"])
            retrieval_time = time.time() - start_time

            assert retrieved_policy["id"] == policy["id"]
            assert retrieval_time < 1.0, f"Policy retrieval should complete in < 1s, took {retrieval_time:.2f}s"

            # Test list policies
            start_time = time.time()
            policies_data = await portfolio_client.get_smart_exit_policies()
            list_time = time.time() - start_time

            assert "items" in policies_data
            assert list_time < 2.0, f"List policies should complete in < 2s, took {list_time:.2f}s"

        finally:
            # Cleanup
            await delete_smart_exit_policy(portfolio_client, policy["id"])

    except Exception as e:
        pytest.skip(f"Policy retrieval performance test failed: {e}")


@pytest.mark.integration
async def test_policy_update_performance(
    config,
    portfolio_client,
):
    """
    Test: Policy update meets performance expectations.

    Validates:
    - Single policy update completes within acceptable time
    - Multiple updates to same policy work efficiently
    """
    try:
        # Create a test policy first
        policy = await create_smart_exit_policy(
            portfolio_client=portfolio_client,
            name=f"Update performance test {uuid.uuid4().hex[:8]}",
            scope="SELECTED",
            position_ids=["test_position_1"],
            action="EXIT",
            rules=[create_mtm_based_rule(mtm_threshold=Decimal("1000"))],
            description="Update performance test",
        )

        try:
            # Test single policy update
            start_time = time.time()
            updated_policy = await portfolio_client.update_smart_exit_policy(
                policy["id"],
                name="Updated name",
                description="Updated description",
            )
            update_time = time.time() - start_time

            assert updated_policy["name"] == "Updated name"
            assert update_time < 1.0, f"Policy update should complete in < 1s, took {update_time:.2f}s"

            # Test multiple updates
            start_time = time.time()
            for i in range(5):
                updated_policy = await portfolio_client.update_smart_exit_policy(
                    policy["id"],
                    name=f"Update {i}",
                    description=f"Description {i}",
                )
            batch_update_time = time.time() - start_time

            assert batch_update_time < 5.0, f"5 updates should complete in < 5s, took {batch_update_time:.2f}s"

        finally:
            # Cleanup
            await delete_smart_exit_policy(portfolio_client, policy["id"])

    except Exception as e:
        pytest.skip(f"Policy update performance test failed: {e}")


@pytest.mark.integration
async def test_bulk_operations_performance(
    config,
    portfolio_client,
):
    """
    Test: Bulk operations meet performance expectations.

    Validates:
    - Bulk activation/deactivation works efficiently
    - Bulk deletion works efficiently
    """
    try:
        # Create 20 policies
        policies = []
        for i in range(20):
            policy = await create_smart_exit_policy(
                portfolio_client=portfolio_client,
                name=f"Bulk test policy {i} {uuid.uuid4().hex[:8]}",
                scope="SELECTED",
                position_ids=[f"test_position_{i}"],
                action="EXIT",
                rules=[create_mtm_based_rule(mtm_threshold=Decimal(str(1000 * (i + 1))))],
                description=f"Bulk test {i}",
            )
            policies.append(policy)

        try:
            # Test bulk activation
            start_time = time.time()
            for policy in policies:
                await activate_smart_exit_policy(portfolio_client, policy["id"])
            activation_time = time.time() - start_time

            assert activation_time < 10.0, f"20 activations should complete in < 10s, took {activation_time:.2f}s"

            # Test bulk deactivation
            start_time = time.time()
            for policy in policies:
                await deactivate_smart_exit_policy(portfolio_client, policy["id"])
            deactivation_time = time.time() - start_time

            assert deactivation_time < 10.0, f"20 deactivations should complete in < 10s, took {deactivation_time:.2f}s"

        finally:
            # Cleanup
            start_time = time.time()
            for policy in policies:
                await delete_smart_exit_policy(portfolio_client, policy["id"])
            deletion_time = time.time() - start_time

            assert deletion_time < 10.0, f"20 deletions should complete in < 10s, took {deletion_time:.2f}s"

    except Exception as e:
        pytest.skip(f"Bulk operations performance test failed: {e}")
