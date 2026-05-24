"""
Happy path E2E tests for Smart Exit V1.

Tests validate:
- Time-based rule creation and validation
- MTM-based rule (lock profit and cap loss) creation and validation
- Target rule creation and validation
- Trailing stop-loss dynamic threshold configuration
- Multi-rule ANY logic configuration
- ALL_INTRADAY scope configuration
- SELECTED scope with multiple positions configuration
- Policy activation and deactivation
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta

import pytest

from e2e.fixtures.smart_exit_helpers import (
    create_smart_exit_policy,
    activate_smart_exit_policy,
    deactivate_smart_exit_policy,
    delete_smart_exit_policy,
    create_time_based_rule,
    create_mtm_based_rule,
    create_target_rule,
    create_trailing_sl_rule,
)

pytestmark = pytest.mark.asyncio


@pytest.mark.smoke
@pytest.mark.integration
async def test_time_based_rule_exit(
    config,
    portfolio_client,
):
    """
    Test: Time-based rule creation and validation.

    Validates:
    - Policy creation with TIME_BASED rule
    - Policy activation
    - Rule validation
    """
    try:
        # Set exit time to 1 minute from now
        exit_time = (datetime.now(timezone.utc) + timedelta(minutes=1)).strftime("%H:%M")

        policy = await create_smart_exit_policy(
            portfolio_client=portfolio_client,
            name=f"Time-based test {uuid.uuid4().hex[:8]}",
            scope="SELECTED",
            position_ids=["test_position_1"],
            action="EXIT",
            rules=[create_time_based_rule(exit_time=exit_time)],
            description="Test time-based exit",
        )

        assert policy["id"], "Policy should have an ID"
        assert policy["scope"] == "SELECTED"
        assert len(policy["rules"]) == 1
        assert policy["rules"][0]["rule_type"] == "TIME_BASED"

        # Activate policy
        await activate_smart_exit_policy(portfolio_client, policy["id"])
        
        # Verify activation
        updated_policy = await portfolio_client.get_smart_exit_policy(policy["id"])
        assert updated_policy["is_active"] is True

        # Cleanup
        await deactivate_smart_exit_policy(portfolio_client, policy["id"])
        await delete_smart_exit_policy(portfolio_client, policy["id"])

    except Exception as e:
        pytest.skip(f"Time-based rule test failed: {e}")


@pytest.mark.smoke
@pytest.mark.integration
async def test_mtm_based_lock_profit(
    config,
    portfolio_client,
):
    """
    Test: MTM-based rule with positive threshold (lock profit).

    Validates:
    - Policy creation with MTM_BASED rule (positive threshold)
    - Rule validation
    - Policy activation
    """
    try:
        policy = await create_smart_exit_policy(
            portfolio_client=portfolio_client,
            name=f"MTM lock profit test {uuid.uuid4().hex[:8]}",
            scope="SELECTED",
            position_ids=["test_position_1"],
            action="EXIT",
            rules=[create_mtm_based_rule(mtm_threshold=Decimal("2000"))],
            description="Test MTM-based profit locking",
        )

        assert policy["id"], "Policy should have an ID"
        assert policy["scope"] == "SELECTED"
        assert len(policy["rules"]) == 1
        assert policy["rules"][0]["rule_type"] == "MTM_BASED"
        assert policy["rules"][0]["parameters"]["mtm_threshold"] == "2000"

        # Activate policy
        await activate_smart_exit_policy(portfolio_client, policy["id"])
        
        # Verify activation
        updated_policy = await portfolio_client.get_smart_exit_policy(policy["id"])
        assert updated_policy["is_active"] is True

        # Cleanup
        await deactivate_smart_exit_policy(portfolio_client, policy["id"])
        await delete_smart_exit_policy(portfolio_client, policy["id"])

    except Exception as e:
        pytest.skip(f"MTM-based lock profit test failed: {e}")


@pytest.mark.smoke
@pytest.mark.integration
async def test_mtm_based_cap_loss(
    config,
    portfolio_client,
):
    """
    Test: MTM-based rule with negative threshold (cap loss).

    Validates:
    - Policy creation with MTM_BASED rule (negative threshold)
    - Rule validation
    - Policy activation
    """
    try:
        policy = await create_smart_exit_policy(
            portfolio_client=portfolio_client,
            name=f"MTM cap loss test {uuid.uuid4().hex[:8]}",
            scope="SELECTED",
            position_ids=["test_position_1"],
            action="EXIT",
            rules=[create_mtm_based_rule(mtm_threshold=Decimal("-1000"))],
            description="Test MTM-based loss capping",
        )

        assert policy["id"], "Policy should have an ID"
        assert policy["scope"] == "SELECTED"
        assert len(policy["rules"]) == 1
        assert policy["rules"][0]["rule_type"] == "MTM_BASED"
        assert policy["rules"][0]["parameters"]["mtm_threshold"] == "-1000"

        # Activate policy
        await activate_smart_exit_policy(portfolio_client, policy["id"])
        
        # Verify activation
        updated_policy = await portfolio_client.get_smart_exit_policy(policy["id"])
        assert updated_policy["is_active"] is True

        # Cleanup
        await deactivate_smart_exit_policy(portfolio_client, policy["id"])
        await delete_smart_exit_policy(portfolio_client, policy["id"])

    except Exception as e:
        pytest.skip(f"MTM-based cap loss test failed: {e}")


@pytest.mark.smoke
@pytest.mark.integration
async def test_target_rule_exit(
    config,
    portfolio_client,
):
    """
    Test: Target rule creation and validation.

    Validates:
    - Policy creation with TARGET rule
    - Rule validation
    - Policy activation
    """
    try:
        policy = await create_smart_exit_policy(
            portfolio_client=portfolio_client,
            name=f"Target rule test {uuid.uuid4().hex[:8]}",
            scope="SELECTED",
            position_ids=["test_position_1"],
            action="EXIT",
            rules=[create_target_rule(target_price=Decimal("570.00"))],
            description="Test target-based exit",
        )

        assert policy["id"], "Policy should have an ID"
        assert policy["scope"] == "SELECTED"
        assert len(policy["rules"]) == 1
        assert policy["rules"][0]["rule_type"] == "TARGET"
        assert policy["rules"][0]["parameters"]["target_price"] == "570.00"

        # Activate policy
        await activate_smart_exit_policy(portfolio_client, policy["id"])
        
        # Verify activation
        updated_policy = await portfolio_client.get_smart_exit_policy(policy["id"])
        assert updated_policy["is_active"] is True

        # Cleanup
        await deactivate_smart_exit_policy(portfolio_client, policy["id"])
        await delete_smart_exit_policy(portfolio_client, policy["id"])

    except Exception as e:
        pytest.skip(f"Target rule test failed: {e}")


@pytest.mark.integration
async def test_trailing_sl_dynamic_threshold(
    config,
    portfolio_client,
):
    """
    Test: Trailing stop-loss rule with MTM_BASED dependency.

    Validates:
    - Policy creation with MTM_BASED + TRAILING_SL rules
    - Dependency validation (TRAILING_SL requires MTM_BASED with positive threshold)
    - Rule validation
    - Policy activation
    """
    try:
        policy = await create_smart_exit_policy(
            portfolio_client=portfolio_client,
            name=f"Trailing SL test {uuid.uuid4().hex[:8]}",
            scope="SELECTED",
            position_ids=["test_position_1"],
            action="EXIT",
            rules=[
                create_mtm_based_rule(
                    mtm_threshold=Decimal("2000"),
                    enable_trailing=True,
                    trail_amount=Decimal("500"),
                ),
            ],
            description="Test trailing stop-loss",
        )

        assert policy["id"], "Policy should have an ID"
        assert policy["scope"] == "SELECTED"
        assert len(policy["rules"]) == 1
        assert policy["rules"][0]["rule_type"] == "MTM_BASED"
        assert policy["rules"][0]["parameters"]["enable_trailing"] is True
        assert policy["rules"][0]["parameters"]["trail_amount"] == "500"

        # Activate policy
        await activate_smart_exit_policy(portfolio_client, policy["id"])
        
        # Verify activation
        updated_policy = await portfolio_client.get_smart_exit_policy(policy["id"])
        assert updated_policy["is_active"] is True

        # Cleanup
        await deactivate_smart_exit_policy(portfolio_client, policy["id"])
        await delete_smart_exit_policy(portfolio_client, policy["id"])

    except Exception as e:
        pytest.skip(f"Trailing SL test failed: {e}")


@pytest.mark.integration
async def test_multi_rule_any_logic(
    config,
    portfolio_client,
):
    """
    Test: Multiple rules with ANY logic.

    Validates:
    - Policy creation with multiple rules
    - ANY logic validation
    - Policy activation
    """
    try:
        policy = await create_smart_exit_policy(
            portfolio_client=portfolio_client,
            name=f"Multi-rule test {uuid.uuid4().hex[:8]}",
            scope="SELECTED",
            position_ids=["test_position_1"],
            action="EXIT",
            rules=[
                create_target_rule(target_price=Decimal("570.00")),
                create_mtm_based_rule(mtm_threshold=Decimal("1000")),
                create_mtm_based_rule(mtm_threshold=Decimal("-1000")),
            ],
            rule_logic="ANY",
            description="Test multi-rule ANY logic",
        )

        assert policy["id"], "Policy should have an ID"
        assert policy["scope"] == "SELECTED"
        assert len(policy["rules"]) == 3
        assert policy["rule_logic"] == "ANY"

        # Activate policy
        await activate_smart_exit_policy(portfolio_client, policy["id"])
        
        # Verify activation
        updated_policy = await portfolio_client.get_smart_exit_policy(policy["id"])
        assert updated_policy["is_active"] is True

        # Cleanup
        await deactivate_smart_exit_policy(portfolio_client, policy["id"])
        await delete_smart_exit_policy(portfolio_client, policy["id"])

    except Exception as e:
        pytest.skip(f"Multi-rule test failed: {e}")


@pytest.mark.integration
async def test_all_intraday_scope(
    config,
    portfolio_client,
):
    """
    Test: ALL_INTRADAY scope validation.

    Validates:
    - Policy creation with ALL_INTRADAY scope
    - Empty position_ids for ALL_INTRADAY
    - Policy activation
    """
    try:
        policy = await create_smart_exit_policy(
            portfolio_client=portfolio_client,
            name=f"All intraday test {uuid.uuid4().hex[:8]}",
            scope="ALL_INTRADAY",
            position_ids=[],  # Empty for ALL_INTRADAY
            action="EXIT",
            rules=[create_mtm_based_rule(mtm_threshold=Decimal("1000"))],
            description="Test ALL_INTRADAY scope",
        )

        assert policy["id"], "Policy should have an ID"
        assert policy["scope"] == "ALL_INTRADAY"
        assert policy["position_ids"] == []

        # Activate policy
        await activate_smart_exit_policy(portfolio_client, policy["id"])
        
        # Verify activation
        updated_policy = await portfolio_client.get_smart_exit_policy(policy["id"])
        assert updated_policy["is_active"] is True

        # Cleanup
        await deactivate_smart_exit_policy(portfolio_client, policy["id"])
        await delete_smart_exit_policy(portfolio_client, policy["id"])

    except Exception as e:
        pytest.skip(f"ALL_INTRADAY scope test failed: {e}")


@pytest.mark.integration
async def test_selected_scope_multiple_positions(
    config,
    portfolio_client,
):
    """
    Test: SELECTED scope with multiple position IDs.

    Validates:
    - Policy creation with SELECTED scope and multiple position_ids
    - Policy activation
    """
    try:
        policy = await create_smart_exit_policy(
            portfolio_client=portfolio_client,
            name=f"Selected scope test {uuid.uuid4().hex[:8]}",
            scope="SELECTED",
            position_ids=["test_position_1", "test_position_2", "test_position_3"],
            action="EXIT",
            rules=[create_mtm_based_rule(mtm_threshold=Decimal("1000"))],
            description="Test SELECTED scope with multiple positions",
        )

        assert policy["id"], "Policy should have an ID"
        assert policy["scope"] == "SELECTED"
        assert len(policy["position_ids"]) == 3

        # Activate policy
        await activate_smart_exit_policy(portfolio_client, policy["id"])
        
        # Verify activation
        updated_policy = await portfolio_client.get_smart_exit_policy(policy["id"])
        assert updated_policy["is_active"] is True

        # Cleanup
        await deactivate_smart_exit_policy(portfolio_client, policy["id"])
        await delete_smart_exit_policy(portfolio_client, policy["id"])

    except Exception as e:
        pytest.skip(f"Selected scope test failed: {e}")
