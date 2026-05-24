"""
Smart Exit helper functions for E2E testing.

Provides utilities for creating Smart Exit policies and rule configurations.
"""

import logging
from decimal import Decimal
from typing import Optional, Dict, Any, List

log = logging.getLogger(__name__)


async def create_smart_exit_policy(
    portfolio_client,
    name: str,
    scope: str = "SELECTED",
    position_ids: Optional[List[str]] = None,
    action: str = "EXIT",
    rules: Optional[List[Dict[str, Any]]] = None,
    description: Optional[str] = None,
    rule_logic: str = "ANY",
) -> Dict[str, Any]:
    """
    Create a Smart Exit policy via Portfolio Service.

    Args:
        portfolio_client: PortfolioClient instance
        name: Policy name
        scope: Policy scope (SELECTED or ALL_INTRADAY)
        position_ids: List of position IDs (required for SELECTED scope)
        action: Action type (EXIT or ALERT_ONLY)
        rules: List of rule configurations
        description: Policy description
        rule_logic: Rule combination logic (ANY or ALL)

    Returns:
        Created policy dictionary
    """
    if position_ids is None:
        position_ids = []

    if rules is None:
        rules = []

    policy = await portfolio_client.create_smart_exit_policy(
        name=name,
        scope=scope,
        position_ids=position_ids,
        action=action,
        rules=rules,
        description=description,
        rule_logic=rule_logic,
    )
    log.info(f"✅ Created Smart Exit policy: {policy['id']} name={name}")
    return policy


async def activate_smart_exit_policy(
    portfolio_client,
    policy_id: str,
) -> Dict[str, Any]:
    """
    Activate a Smart Exit policy.

    Args:
        portfolio_client: PortfolioClient instance
        policy_id: Policy ID to activate

    Returns:
        Updated policy dictionary
    """
    policy = await portfolio_client.activate_smart_exit_policy(policy_id)
    log.info(f"✅ Activated Smart Exit policy: {policy_id}")
    return policy


async def deactivate_smart_exit_policy(
    portfolio_client,
    policy_id: str,
) -> Dict[str, Any]:
    """
    Deactivate a Smart Exit policy.

    Args:
        portfolio_client: PortfolioClient instance
        policy_id: Policy ID to deactivate

    Returns:
        Updated policy dictionary
    """
    policy = await portfolio_client.deactivate_smart_exit_policy(policy_id)
    log.info(f"✅ Deactivated Smart Exit policy: {policy_id}")
    return policy


async def delete_smart_exit_policy(
    portfolio_client,
    policy_id: str,
) -> Dict[str, Any]:
    """
    Delete a Smart Exit policy.

    Args:
        portfolio_client: PortfolioClient instance
        policy_id: Policy ID to delete

    Returns:
        Deletion response dictionary
    """
    result = await portfolio_client.delete_smart_exit_policy(policy_id)
    log.info(f"✅ Deleted Smart Exit policy: {policy_id}")
    return result


def create_time_based_rule(
    exit_time: str,
    exit_date: Optional[str] = None,
    timezone: str = "Asia/Kolkata",
) -> Dict[str, Any]:
    """
    Create a time-based rule configuration.

    Args:
        exit_time: Exit time in HH:MM format
        exit_date: Exit date in YYYY-MM-DD format (optional)
        timezone: Timezone for exit time

    Returns:
        Rule configuration dictionary
    """
    return {
        "rule_type": "TIME_BASED",
        "parameters": {
            "exit_time": exit_time,
            "exit_date": exit_date,
            "timezone": timezone,
        },
    }


def create_mtm_based_rule(
    mtm_threshold: Decimal,
    mtm_percentage: Optional[Decimal] = None,
    enable_trailing: bool = False,
    trail_amount: Optional[Decimal] = None,
    trail_percentage: Optional[Decimal] = None,
) -> Dict[str, Any]:
    """
    Create an MTM-based rule configuration.

    Args:
        mtm_threshold: MTM threshold amount (positive for lock profit, negative for cap loss)
        mtm_percentage: MTM threshold as percentage (optional)
        enable_trailing: Enable trailing stop-loss
        trail_amount: Trailing amount in absolute value
        trail_percentage: Trailing amount as percentage

    Returns:
        Rule configuration dictionary
    """
    parameters = {
        "mtm_threshold": str(mtm_threshold),
    }

    if mtm_percentage is not None:
        parameters["mtm_percentage"] = str(mtm_percentage)

    if enable_trailing:
        parameters["enable_trailing"] = True
        if trail_amount is not None:
            parameters["trail_amount"] = str(trail_amount)
        if trail_percentage is not None:
            parameters["trail_percentage"] = str(trail_percentage)

    return {
        "rule_type": "MTM_BASED",
        "parameters": parameters,
    }


def create_target_rule(
    target_price: Decimal,
    target_percentage: Optional[Decimal] = None,
) -> Dict[str, Any]:
    """
    Create a target-based rule configuration.

    Args:
        target_price: Target price for exit
        target_percentage: Target as percentage (optional)

    Returns:
        Rule configuration dictionary
    """
    parameters = {
        "target_price": str(target_price),
    }

    if target_percentage is not None:
        parameters["target_percentage"] = str(target_percentage)

    return {
        "rule_type": "TARGET",
        "parameters": parameters,
    }


def create_trailing_sl_rule(
    trail_amount: Decimal,
    trail_percentage: Optional[Decimal] = None,
) -> Dict[str, Any]:
    """
    Create a trailing stop-loss rule configuration.

    Note: TRAILING_SL is typically used as a parameter within MTM_BASED rules,
    not as a standalone rule type. This function is provided for completeness.

    Args:
        trail_amount: Trailing amount in absolute value
        trail_percentage: Trailing amount as percentage

    Returns:
        Rule configuration dictionary
    """
    parameters = {
        "trail_amount": str(trail_amount),
    }

    if trail_percentage is not None:
        parameters["trail_percentage"] = str(trail_percentage)

    return {
        "rule_type": "TRAILING_SL",
        "parameters": parameters,
    }
