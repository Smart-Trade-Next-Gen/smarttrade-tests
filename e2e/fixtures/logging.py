"""
Logging configuration for E2E tests.

Provides correlation ID support (order_id) for traceability across services.
"""

import logging
import sys
from contextlib import contextmanager
from typing import Optional

# Log format: timestamp | level | service | order_id | message
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(order_id)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class OrderIdFilter(logging.Filter):
    """Add order_id to log records for correlation across services."""

    def __init__(self):
        super().__init__()
        self.order_id = "N/A"

    def filter(self, record: logging.LogRecord) -> bool:
        """Add order_id to log record."""
        record.order_id = self.order_id
        return True


def configure_logging(level: str = "DEBUG") -> None:
    """
    Configure pytest logging with correlation ID support.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
    """
    # Convert string level to logging level
    log_level = getattr(logging, level.upper(), logging.DEBUG)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    # Create formatter with order_id
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    # Add OrderIdFilter to console handler
    order_id_filter = OrderIdFilter()
    console_handler.addFilter(order_id_filter)
    console_handler.setFormatter(formatter)

    # Add handler to root logger
    root_logger.addHandler(console_handler)

    # Store filter reference for later use
    root_logger._order_id_filter = order_id_filter


def get_order_id_logger(order_id: str) -> logging.LoggerAdapter:
    """
    Get a logger that automatically includes order_id in all messages.

    Args:
        order_id: Order ID for correlation

    Returns:
        LoggerAdapter with order_id in extra context
    """
    logger = logging.getLogger("e2e.test")
    return logging.LoggerAdapter(logger, {"order_id": order_id})


@contextmanager
def correlation_context(order_id: str):
    """
    Context manager to set order_id for all logs within a block.

    Args:
        order_id: Order ID for correlation

    Usage:
        with correlation_context("order_123"):
            logger.info("Processing order")  # Will include order_123 in logs
    """
    root_logger = logging.getLogger()
    old_order_id = None
    if hasattr(root_logger, "_order_id_filter"):
        old_order_id = root_logger._order_id_filter.order_id
        root_logger._order_id_filter.order_id = order_id

    try:
        yield
    finally:
        if hasattr(root_logger, "_order_id_filter") and old_order_id is not None:
            root_logger._order_id_filter.order_id = old_order_id
