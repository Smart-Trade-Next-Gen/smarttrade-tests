"""Pytest fixtures for E2E testing (clients, harness setup, cleanup)."""

from e2e.fixtures.helpers import (
    unique_account_id,
    unique_order_id,
    truncate_token,
    format_price,
    format_quantity,
    parse_iso_timestamp,
    elapsed_ms,
)
from e2e.fixtures.logging import (
    configure_logging,
    get_order_id_logger,
    correlation_context,
)
from e2e.fixtures.test_data import (
    INSTRUMENTS,
    PRICES,
    QUANTITIES,
    PRICE_LEVELS,
    ORDER_TYPES,
    ORDER_SIDES,
    TIME_IN_FORCE,
    MARGIN_MULTIPLIER,
    get_instrument_id,
    get_price,
    get_quantity,
    calculate_price_level,
)

__all__ = [
    # Helpers
    "unique_account_id",
    "unique_order_id",
    "truncate_token",
    "format_price",
    "format_quantity",
    "parse_iso_timestamp",
    "elapsed_ms",
    # Logging
    "configure_logging",
    "get_order_id_logger",
    "correlation_context",
    # Test data
    "INSTRUMENTS",
    "PRICES",
    "QUANTITIES",
    "PRICE_LEVELS",
    "ORDER_TYPES",
    "ORDER_SIDES",
    "TIME_IN_FORCE",
    "MARGIN_MULTIPLIER",
    "get_instrument_id",
    "get_price",
    "get_quantity",
    "calculate_price_level",
]
