"""
E2E Test Configuration System

Supports dev/staging/prod environments with environment variable and YAML file overrides.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class TestConfig:
    """E2E test configuration for SmartTrade services."""

    env: str
    bas_url: str
    mds_ws_url: str
    mock_url: str
    auth_url: str
    test_user: str
    test_password: str
    broker_id: str
    account_id: str
    timeout_fast: float = 5.0
    timeout_medium: float = 10.0
    timeout_slow: float = 30.0

    @staticmethod
    def from_env() -> "TestConfig":
        """
        Load configuration from environment variables and YAML files.

        Priority:
        1. Environment variables (E2E_* prefix)
        2. YAML file (dev.yaml, staging.yaml, etc.)
        3. Hardcoded defaults for localhost
        """
        env = os.getenv("E2E_ENV", "dev").lower()

        # Try to load YAML config file
        config_path = Path(__file__).parent / f"{env}.yaml"
        yaml_config = {}
        if config_path.exists():
            with open(config_path) as f:
                yaml_config = yaml.safe_load(f) or {}

        # Build config with priority: env vars > YAML > defaults
        def get_setting(key: str, yaml_key: Optional[str] = None) -> str:
            env_var = f"E2E_{key.upper()}"
            yaml_fallback_key = yaml_key or key.lower()
            return (
                os.getenv(env_var)
                or yaml_config.get(yaml_fallback_key)
                or _get_default(key, env)
            )

        def get_float_setting(key: str, yaml_key: Optional[str] = None) -> float:
            env_var = f"E2E_{key.upper()}"
            yaml_fallback_key = yaml_key or key.lower()
            env_value = os.getenv(env_var)
            if env_value:
                try:
                    return float(env_value)
                except ValueError:
                    raise ValueError(
                        f"Invalid {env_var}: must be a float, got '{env_value}'"
                    )
            yaml_value = yaml_config.get(yaml_fallback_key)
            if yaml_value is not None:
                return float(yaml_value)
            return float(_get_default(key, env))

        return TestConfig(
            env=env,
            bas_url=get_setting("BAS_URL", "bas_url"),
            mds_ws_url=get_setting("MDS_WS_URL", "mds_ws_url"),
            mock_url=get_setting("MOCK_URL", "mock_url"),
            auth_url=get_setting("AUTH_URL", "auth_url"),
            test_user=get_setting("TEST_USER", "test_user"),
            test_password=get_setting("TEST_PASSWORD", "test_password"),
            broker_id=get_setting("BROKER_ID", "broker_id"),
            account_id=get_setting("ACCOUNT_ID", "account_id"),
            timeout_fast=get_float_setting("TIMEOUT_FAST", "timeout_fast"),
            timeout_medium=get_float_setting("TIMEOUT_MEDIUM", "timeout_medium"),
            timeout_slow=get_float_setting("TIMEOUT_SLOW", "timeout_slow"),
        )

    def asdict(self) -> dict:
        """Return config as dictionary (useful for logging/debugging)."""
        return {
            "env": self.env,
            "bas_url": self.bas_url,
            "mds_ws_url": self.mds_ws_url,
            "mock_url": self.mock_url,
            "auth_url": self.auth_url,
            "test_user": self.test_user,
            "broker_id": self.broker_id,
            "account_id": self.account_id,
            "timeout_fast": self.timeout_fast,
            "timeout_medium": self.timeout_medium,
            "timeout_slow": self.timeout_slow,
        }


def _get_default(key: str, env: str) -> str:
    """Get default configuration based on environment."""
    defaults = {
        "dev": {
            "BAS_URL": "http://localhost:8005",
            "MDS_WS_URL": "ws://localhost:8004",
            "MOCK_URL": "http://localhost:8002",  # Paper Broker Service
            "AUTH_URL": "http://localhost:8001",
            "TEST_USER": "testuser@example.com",
            "TEST_PASSWORD": "testpassword123",
            "BROKER_ID": "fyers",
            "ACCOUNT_ID": "TEST123456",
            "TIMEOUT_FAST": "5.0",
            "TIMEOUT_MEDIUM": "10.0",
            "TIMEOUT_SLOW": "30.0",
        },
        "staging": {
            "BAS_URL": "https://staging-bas.smarttrade.asia",
            "MDS_WS_URL": "wss://staging-mds.smarttrade.asia",
            "MOCK_URL": "https://staging-mock.smarttrade.asia",  # Paper Broker Service
            "AUTH_URL": "https://staging-auth.smarttrade.asia",
            "TEST_USER": "staging-testuser@example.com",
            "TEST_PASSWORD": "staging-testpassword123",
            "BROKER_ID": "fyers",
            "ACCOUNT_ID": "STAGING123456",
            "TIMEOUT_FAST": "5.0",
            "TIMEOUT_MEDIUM": "15.0",
            "TIMEOUT_SLOW": "60.0",
        },
        "prod": {
            "BAS_URL": "https://api.smarttrade.asia/bas",
            "MDS_WS_URL": "wss://api.smarttrade.asia/mds",
            "MOCK_URL": "https://api.smarttrade.asia/mock",  # Paper Broker Service
            "AUTH_URL": "https://api.smarttrade.asia/auth",
            "TEST_USER": "prod-testuser@example.com",
            "TEST_PASSWORD": "prod-testpassword123",
            "BROKER_ID": "fyers",
            "ACCOUNT_ID": "PROD123456",
            "TIMEOUT_FAST": "10.0",
            "TIMEOUT_MEDIUM": "20.0",
            "TIMEOUT_SLOW": "60.0",
        },
    }

    if env not in defaults:
        env = "dev"

    return defaults[env].get(key.upper(), "")
