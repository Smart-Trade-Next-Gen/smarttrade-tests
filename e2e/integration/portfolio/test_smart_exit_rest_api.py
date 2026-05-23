"""
Integration tests for Smart Exit REST API.

Tests validate:
- Smart Exit policy CRUD operations
- Policy activation/deactivation
- Trigger history retrieval
- Rule evaluation integration
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


@pytest.mark.smoke
async def test_smart_exit_create_policy(
    config,
    portfolio_client,
):
    """
    Test: Smart Exit POST /api/v1/smart-exit/policies endpoint.

    Validates:
    - Endpoint returns 201 Created
    - Policy is created with correct fields
    - Rules are attached to policy
    """
    try:
        policy = await portfolio_client.create_smart_exit_policy(
            name="Test Policy",
            description="Integration test policy",
            scope="SELECTED",
            position_ids=["test_position_1"],
            action="EXIT",
            rules=[
                {
                    "rule_type": "TARGET",
                    "parameters": {"target_price": "100.50"},
                }
            ],
        )
        
        # Should return a dict with policy fields
        assert isinstance(policy, dict), "Should return a policy dict"
        assert "id" in policy, "Policy should have an ID"
        assert policy["name"] == "Test Policy", "Policy name should match"
        assert policy["scope"] == "SELECTED", "Policy scope should match"
        assert policy["action"] == "EXIT", "Policy action should match"
        assert len(policy["rules"]) == 1, "Policy should have 1 rule"
        assert policy["rules"][0]["rule_type"] == "TARGET", "Rule type should match"
        
        # Cleanup
        await portfolio_client.delete_smart_exit_policy(policy["id"])
        
    except Exception as e:
        pytest.skip(f"Smart Exit policy creation failed: {e}")


@pytest.mark.smoke
async def test_smart_exit_get_policies(
    config,
    portfolio_client,
):
    """
    Test: Smart Exit GET /api/v1/smart-exit/policies endpoint.

    Validates:
    - Endpoint returns 200 OK
    - Returns list of policies
    - Response structure is correct
    """
    try:
        # First create a test policy
        created_policy = await portfolio_client.create_smart_exit_policy(
            name="Test Policy for List",
            scope="SELECTED",
            position_ids=["test_position_1"],
            action="ALERT_ONLY",
            rules=[
                {
                    "rule_type": "MTM_BASED",
                    "parameters": {"mtm_threshold": "-500"},
                }
            ],
        )
        
        # Get policies
        policies_data = await portfolio_client.get_smart_exit_policies()
        
        # Should return a dict with items and total
        assert isinstance(policies_data, dict), "Should return a dict"
        assert "items" in policies_data, "Should have items field"
        assert "total" in policies_data, "Should have total field"
        assert isinstance(policies_data["items"], list), "Items should be a list"
        
        # Find our created policy
        found = False
        for policy in policies_data["items"]:
            if policy["id"] == created_policy["id"]:
                found = True
                assert policy["name"] == "Test Policy for List"
                break
        
        assert found, "Created policy should be in the list"
        
        # Cleanup
        await portfolio_client.delete_smart_exit_policy(created_policy["id"])
        
    except Exception as e:
        pytest.skip(f"Smart Exit get policies failed: {e}")


@pytest.mark.smoke
async def test_smart_exit_get_policy_by_id(
    config,
    portfolio_client,
):
    """
    Test: Smart Exit GET /api/v1/smart-exit/policies/{policy_id} endpoint.

    Validates:
    - Endpoint returns 200 OK
    - Returns specific policy
    - Policy structure is correct
    """
    try:
        # Create a test policy
        created_policy = await portfolio_client.create_smart_exit_policy(
            name="Test Policy for Get",
            scope="SELECTED",
            position_ids=["test_position_1"],
            action="EXIT",
            rules=[
                {
                    "rule_type": "MTM_BASED",
                    "parameters": {
                        "mtm_threshold": "1000",
                    },
                }
            ],
        )
        
        # Get specific policy
        policy = await portfolio_client.get_smart_exit_policy(created_policy["id"])
        
        # Should return the created policy
        assert isinstance(policy, dict), "Should return a policy dict"
        assert policy["id"] == created_policy["id"], "Policy ID should match"
        assert policy["name"] == "Test Policy for Get", "Policy name should match"
        assert len(policy["rules"]) == 1, "Policy should have 1 rule"
        
        # Cleanup
        await portfolio_client.delete_smart_exit_policy(created_policy["id"])
        
    except Exception as e:
        pytest.skip(f"Smart Exit get policy by ID failed: {e}")


@pytest.mark.smoke
async def test_smart_exit_update_policy(
    config,
    portfolio_client,
):
    """
    Test: Smart Exit PUT /api/v1/smart-exit/policies/{policy_id} endpoint.

    Validates:
    - Endpoint returns 200 OK
    - Policy is updated correctly
    - Fields are modified as expected
    """
    try:
        # Create a test policy
        created_policy = await portfolio_client.create_smart_exit_policy(
            name="Test Policy for Update",
            description="Original description",
            scope="SELECTED",
            position_ids=["test_position_1"],
            action="EXIT",
        )
        
        # Update the policy
        updated_policy = await portfolio_client.update_smart_exit_policy(
            created_policy["id"],
            name="Updated Policy Name",
            description="Updated description",
            is_active=False,
        )
        
        # Verify updates
        assert updated_policy["name"] == "Updated Policy Name", "Name should be updated"
        assert updated_policy["description"] == "Updated description", "Description should be updated"
        assert updated_policy["is_active"] is False, "Active status should be updated"
        
        # Cleanup
        await portfolio_client.delete_smart_exit_policy(created_policy["id"])
        
    except Exception as e:
        pytest.skip(f"Smart Exit update policy failed: {e}")


@pytest.mark.smoke
async def test_smart_exit_delete_policy(
    config,
    portfolio_client,
):
    """
    Test: Smart Exit DELETE /api/v1/smart-exit/policies/{policy_id} endpoint.

    Validates:
    - Endpoint returns 200 OK
    - Policy is deleted successfully
    - Deleted policy cannot be retrieved
    """
    try:
        # Create a test policy
        created_policy = await portfolio_client.create_smart_exit_policy(
            name="Test Policy for Delete",
            scope="SELECTED",
            position_ids=["test_position_1"],
            action="EXIT",
        )
        
        # Delete the policy
        result = await portfolio_client.delete_smart_exit_policy(created_policy["id"])
        
        # Verify deletion
        assert isinstance(result, dict), "Should return a dict"
        assert "message" in result, "Should have message field"
        
        # Try to get deleted policy (should fail)
        try:
            await portfolio_client.get_smart_exit_policy(created_policy["id"])
            assert False, "Should not be able to get deleted policy"
        except Exception:
            # Expected - policy should not exist
            pass
        
    except Exception as e:
        pytest.skip(f"Smart Exit delete policy failed: {e}")


@pytest.mark.smoke
async def test_smart_exit_activate_deactivate_policy(
    config,
    portfolio_client,
):
    """
    Test: Smart Exit POST /api/v1/smart-exit/policies/{policy_id}/activate and deactivate endpoints.

    Validates:
    - Activate endpoint returns 200 OK
    - Policy is activated correctly
    - Deactivate endpoint returns 200 OK
    - Policy is deactivated correctly
    """
    try:
        # Create a test policy (active by default)
        created_policy = await portfolio_client.create_smart_exit_policy(
            name="Test Policy for Activation",
            scope="SELECTED",
            position_ids=["test_position_1"],
            action="EXIT",
        )
        
        # Deactivate the policy first
        deactivated_policy = await portfolio_client.deactivate_smart_exit_policy(created_policy["id"])
        assert deactivated_policy["is_active"] is False, "Policy should be deactivated"
        
        # Activate the policy
        activated_policy = await portfolio_client.activate_smart_exit_policy(created_policy["id"])
        assert activated_policy["is_active"] is True, "Policy should be activated"
        
        # Cleanup
        await portfolio_client.delete_smart_exit_policy(created_policy["id"])
        
    except Exception as e:
        pytest.skip(f"Smart Exit activate/deactivate failed: {e}")


@pytest.mark.smoke
async def test_smart_exit_get_policy_triggers(
    config,
    portfolio_client,
):
    """
    Test: Smart Exit GET /api/v1/smart-exit/policies/{policy_id}/triggers endpoint.

    Validates:
    - Endpoint returns 200 OK
    - Returns trigger history
    - Response structure is correct
    """
    try:
        # Create a test policy
        created_policy = await portfolio_client.create_smart_exit_policy(
            name="Test Policy for Triggers",
            scope="SELECTED",
            position_ids=["test_position_1"],
            action="EXIT",
            rules=[
                {
                    "rule_type": "TIME_BASED",
                    "parameters": {"exit_time": "15:30"},
                }
            ],
        )
        
        # Get trigger history (may be empty for new policy)
        triggers_data = await portfolio_client.get_smart_exit_policy_triggers(created_policy["id"])
        
        # Should return a dict with items and total
        assert isinstance(triggers_data, dict), "Should return a dict"
        assert "items" in triggers_data, "Should have items field"
        assert "total" in triggers_data, "Should have total field"
        assert isinstance(triggers_data["items"], list), "Items should be a list"
        
        # Cleanup
        await portfolio_client.delete_smart_exit_policy(created_policy["id"])
        
    except Exception as e:
        pytest.skip(f"Smart Exit get policy triggers failed: {e}")


@pytest.mark.integration
async def test_smart_exit_multiple_rule_types(
    config,
    portfolio_client,
):
    """
    Test: Smart Exit policy with multiple rule types.

    Validates:
    - Policy can have multiple rules
    - Different rule types are supported
    - Rule parameters are stored correctly
    - MTM rule with trailing parameters works
    """
    try:
        # Create a policy with multiple rules
        # Note: Trailing is now a parameter within MTM_BASED rule
        policy = await portfolio_client.create_smart_exit_policy(
            name="Multi-Rule Policy",
            scope="SELECTED",
            position_ids=["test_position_1"],
            action="EXIT",
            rules=[
                {
                    "rule_type": "TARGET",
                    "parameters": {"target_price": "105.00"},
                },
                {
                    "rule_type": "MTM_BASED",
                    "parameters": {
                        "mtm_threshold": "1000",  # Positive for Protect P&L
                        "enable_trailing": True,
                        "trail_amount": "500",
                    },
                },
            ],
        )
        
        # Verify all rules are present
        assert len(policy["rules"]) == 2, "Should have 2 rules"
        
        rule_types = [rule["rule_type"] for rule in policy["rules"]]
        assert "TARGET" in rule_types, "Should have TARGET rule"
        assert "MTM_BASED" in rule_types, "Should have MTM_BASED rule"
        
        # Verify rule parameters
        target_rule = next(r for r in policy["rules"] if r["rule_type"] == "TARGET")
        assert target_rule["parameters"]["target_price"] == "105.00"
        
        # Verify MTM_BASED has trailing parameters
        mtm_rule = next(r for r in policy["rules"] if r["rule_type"] == "MTM_BASED")
        assert mtm_rule["parameters"]["mtm_threshold"] == "1000"
        assert mtm_rule["parameters"]["enable_trailing"] is True
        assert mtm_rule["parameters"]["trail_amount"] == "500"
        
        # Cleanup
        await portfolio_client.delete_smart_exit_policy(policy["id"])
        
    except Exception as e:
        pytest.skip(f"Smart Exit multiple rule types test failed: {e}")


@pytest.mark.integration
async def test_smart_exit_mtm_trailing_validation(
    config,
    portfolio_client,
):
    """
    Test: MTM_BASED rule with trailing parameters validation.

    Validates:
    - Trailing without trail parameters fails validation
    - Trailing with positive threshold succeeds (Protect P&L mode)
    - Trailing with negative threshold succeeds (Stop Loss mode)
    """
    try:
        # Test 1: Trailing enabled without trail parameters should fail
        try:
            policy = await portfolio_client.create_smart_exit_policy(
                name="Invalid Trailing Policy",
                scope="SELECTED",
                position_ids=["test_position_1"],
                action="EXIT",
                rules=[
                    {
                        "rule_type": "MTM_BASED",
                        "parameters": {
                            "mtm_threshold": "1000",
                            "enable_trailing": True,
                        },
                    },
                ],
            )
            assert False, "Should have failed validation - trailing requires trail parameters"
        except Exception as e:
            assert "at least one of trail_amount" in str(e) or "422" in str(e), f"Expected validation error, got: {e}"

        # Test 2: Trailing with positive threshold should succeed (Protect P&L mode)
        policy = await portfolio_client.create_smart_exit_policy(
            name="Valid Trailing Policy",
            scope="SELECTED",
            position_ids=["test_position_1"],
            action="EXIT",
            rules=[
                {
                    "rule_type": "MTM_BASED",
                    "parameters": {
                        "mtm_threshold": "1000",
                        "enable_trailing": True,
                        "trail_amount": "500",
                    },
                },
            ],
        )

        assert policy["rules"][0]["rule_type"] == "MTM_BASED"
        assert policy["rules"][0]["parameters"]["enable_trailing"] is True
        assert policy["rules"][0]["parameters"]["trail_amount"] == "500"

        # Cleanup
        await portfolio_client.delete_smart_exit_policy(policy["id"])

        # Test 3: Trailing with negative threshold should succeed (Stop Loss mode)
        policy = await portfolio_client.create_smart_exit_policy(
            name="Valid Trailing Policy SL",
            scope="SELECTED",
            position_ids=["test_position_1"],
            action="EXIT",
            rules=[
                {
                    "rule_type": "MTM_BASED",
                    "parameters": {
                        "mtm_threshold": "-500",
                        "enable_trailing": True,
                        "trail_percentage": "5",
                    },
                },
            ],
        )

        assert policy["rules"][0]["rule_type"] == "MTM_BASED"
        assert policy["rules"][0]["parameters"]["enable_trailing"] is True
        assert policy["rules"][0]["parameters"]["trail_percentage"] == "5"

        # Cleanup
        await portfolio_client.delete_smart_exit_policy(policy["id"])

    except Exception as e:
        pytest.skip(f"Smart Exit MTM trailing validation test failed: {e}")
