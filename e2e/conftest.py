"""
Base pytest configuration for E2E tests.

Provides shared fixtures for service clients, event collection, and lifecycle management.
Will be populated with actual fixtures in E2E-023.
"""

import logging
import os

import pytest

from e2e.config import TestConfig
from e2e.clients import BASClient
from e2e.harness import EventCollector
from e2e.fixtures.logging import configure_logging


def pytest_configure(config):
    """Register custom markers and configure logging."""
    config.addinivalue_line(
        "markers", "smoke: quick sanity tests"
    )
    config.addinivalue_line(
        "markers", "injection: deterministic injection mode"
    )
    config.addinivalue_line(
        "markers", "real_execution: real execution mode"
    )
    config.addinivalue_line(
        "markers", "resilience: network failures"
    )
    config.addinivalue_line(
        "markers", "chaos: chaos testing"
    )

    # Configure logging based on environment
    env = os.getenv("E2E_ENV", "dev").lower()
    log_level = "DEBUG" if env == "dev" else "INFO"
    configure_logging(log_level)


@pytest.fixture(scope="session")
def config() -> TestConfig:
    """Load E2E test configuration from environment and YAML files."""
    return TestConfig.from_env()


@pytest.fixture
def logger() -> logging.Logger:
    """Provide a logger for tests."""
    return logging.getLogger("e2e.test")


@pytest.fixture
async def auth_token(config: TestConfig) -> str:
    """
    Get authentication token.

    This is a placeholder that returns a mock token.
    In E2E-013, this will be replaced with actual AuthClient login.
    """
    # TODO: Implement AuthClient login to get real token
    return "placeholder_token_from_auth_service"


@pytest.fixture
async def bas_client(config: TestConfig, auth_token: str) -> BASClient:
    """
    Provide BASClient instance with proper setup/teardown.

    Args:
        config: E2E test configuration
        auth_token: Valid authentication token

    Yields:
        BASClient instance
    """
    async with BASClient(
        base_url=config.bas_url,
        token=auth_token,
        timeout=config.timeout_medium,
    ) as client:
        yield client


@pytest.fixture
def event_collector() -> EventCollector:
    """
    Provide EventCollector instance for event-driven test validation.

    Yields:
        EventCollector instance
    """
    return EventCollector(maxsize=1000)
