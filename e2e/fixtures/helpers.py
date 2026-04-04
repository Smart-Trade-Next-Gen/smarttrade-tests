"""
Test helper utilities for E2E testing.

Provides unique ID generation, correlation ID support, and other test utilities.
"""

import uuid
from datetime import datetime


def unique_account_id(test_id: str) -> str:
    """
    Generate a unique account ID for each test run.

    This prevents conflicts when running parallel tests and provides
    clear traceability to the original test.

    Args:
        test_id: Base test identifier (e.g., test function name)

    Returns:
        Unique account ID in format: <test_id>_<timestamp>_<uuid_short>
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_suffix = str(uuid.uuid4())[:8]
    return f"{test_id}_{timestamp}_{unique_suffix}"


def unique_order_id(test_id: str = "order") -> str:
    """
    Generate a unique order ID for each test.

    Args:
        test_id: Base test identifier (default: "order")

    Returns:
        Unique order ID in format: <test_id>_<timestamp>_<uuid_short>
    """
    return unique_account_id(test_id)


def truncate_token(token: str, length: int = 20) -> str:
    """
    Safely truncate a token for logging without exposing secrets.

    Args:
        token: Token to truncate
        length: Number of characters to show

    Returns:
        Truncated token with ellipsis
    """
    if len(token) <= length:
        return token
    return f"{token[:length]}..."


def format_price(price) -> str:
    """
    Format price for display in logs.

    Args:
        price: Price value (int, float, or string)

    Returns:
        Formatted price string
    """
    if isinstance(price, str):
        return f"₹{price}"
    return f"₹{float(price):.2f}"


def format_quantity(quantity) -> str:
    """
    Format quantity for display in logs.

    Args:
        quantity: Quantity value

    Returns:
        Formatted quantity string with units
    """
    return f"{int(quantity)} shares"


def parse_iso_timestamp(timestamp_str: str) -> datetime:
    """
    Parse ISO 8601 timestamp string.

    Args:
        timestamp_str: ISO timestamp string

    Returns:
        datetime object

    Raises:
        ValueError: If timestamp format is invalid
    """
    try:
        return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError(f"Invalid ISO timestamp: {timestamp_str}") from e


def elapsed_ms(start_time: datetime, end_time: datetime) -> int:
    """
    Calculate elapsed time in milliseconds.

    Args:
        start_time: Start datetime
        end_time: End datetime

    Returns:
        Elapsed milliseconds
    """
    delta = end_time - start_time
    return int(delta.total_seconds() * 1000)
