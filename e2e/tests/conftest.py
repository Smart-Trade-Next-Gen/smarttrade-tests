"""
Test-level pytest configuration for E2E tests.

Provides test-specific fixtures and setup/teardown logic.
"""

import logging

import pytest

log = logging.getLogger(__name__)


# Additional test-specific fixtures can be added here
# These complement the session and function-scoped fixtures in e2e/conftest.py
