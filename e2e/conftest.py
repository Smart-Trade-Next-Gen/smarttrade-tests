"""
Base pytest configuration for E2E tests.

Provides comprehensive fixtures for service clients, event collection, assertions,
and lifecycle management. All fixtures are properly scoped and cleaned up.
"""

import asyncio
import hashlib
import logging
import os
from typing import AsyncGenerator
from pathlib import Path
from decimal import Decimal

import pytest

# Load .env file for JWT_SECRET_KEY and other environment variables
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent.parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass  # python-dotenv not available, rely on environment

from e2e.config import TestConfig
from e2e.clients import BASClient, MDSWebSocketClient, MockClient
from e2e.harness import EventCollector, AssertionEngine, ScenarioEngine
from e2e.fixtures.logging import configure_logging
from e2e.fixtures.market_data_stream import MockMarketDataStream
from e2e.fixtures.chaos_engine import ChaosEngine

log = logging.getLogger(__name__)


def pytest_configure(config):
    """Register custom markers and configure logging."""
    config.addinivalue_line("markers", "smoke: quick sanity tests")
    config.addinivalue_line("markers", "injection: deterministic injection mode")
    config.addinivalue_line("markers", "real_execution: real execution mode")
    config.addinivalue_line("markers", "resilience: network failures")
    config.addinivalue_line("markers", "chaos: chaos testing")

    # Configure logging based on environment
    env = os.getenv("E2E_ENV", "dev").lower()
    log_level = "DEBUG" if env == "dev" else "INFO"
    configure_logging(log_level)

    # Ensure reports directory exists
    reports_dir = Path(__file__).parent / "reports"
    reports_dir.mkdir(exist_ok=True)


# ────────────────────────────────────────────────────────────────────────────────
# SESSION-SCOPED FIXTURES
# ────────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def config() -> TestConfig:
    """
    Load E2E test configuration from environment and YAML files.

    Scope: session (loaded once per test run)
    """
    return TestConfig.from_env()


# ────────────────────────────────────────────────────────────────────────────────
# FUNCTION-SCOPED FIXTURES: LOGGING & UTILITIES
# ────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def logger() -> logging.Logger:
    """
    Provide a logger for tests.

    Scope: function
    """
    return logging.getLogger("e2e.test")


@pytest.fixture(autouse=True)
async def setup_trading_account(bas_client, test_account_id):
    """
    Create paper trading accounts (autouse).

    Automatically creates a paper trading account with fyers broker before each test.
    Paper accounts use real broker ID but account_type=PAPER to enable paper trading.

    Scope: function
    """
    broker_id = "fyers"

    try:
        # First delete any existing accounts with this ID (from prior test runs)
        # This ensures we have a clean slate with the correct user_id
        try:
            await bas_client.delete_trading_account(broker_id, test_account_id)
            log.debug(f"Deleted existing trading account: {broker_id}/{test_account_id}")
        except Exception:
            pass  # Account may not exist, that's fine

        # Create PAPER trading account
        await bas_client.create_trading_account(
            broker_id=broker_id,
            account_id=test_account_id,
            initial_funds=Decimal("1000000.00"),
            account_type="PAPER",
        )
        log.debug(f"✅ Paper trading account created: {broker_id}/{test_account_id}")
    except Exception as e:
        log.warning(f"⚠️ Paper account creation failed for {broker_id}/{test_account_id}: {e}")

    # Yield control back to test
    yield

    # Cleanup is optional - accounts can be reused


@pytest.fixture
def test_account_id(request) -> str:
    """
    Generate a unique account ID per test.

    Ensures test isolation by giving each test its own account ID.

    Scope: function
    """
    test_hash = hashlib.md5(request.node.nodeid.encode()).hexdigest()[:8]
    return f"TEST_E2E_{test_hash}"


# ────────────────────────────────────────────────────────────────────────────────
# FUNCTION-SCOPED FIXTURES: AUTHENTICATION
# ────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
async def auth_token(config: TestConfig) -> str:
    """
    Get authentication token for service access.

    Generates a JWT token using the same secret and library as the services.
    Uses test credentials for E2E testing.

    Scope: function (fresh token per test, but with consistent user ID)
    """
    from jose import jwt
    from datetime import datetime, timedelta

    # Secret from environment (must match docker-compose JWT_SECRET_KEY)
    # Falls back to env var or default if not set
    secret = os.getenv("JWT_SECRET_KEY", "jIjETudRTwtHBE_Ez5uU_NeMvi_6zXrst8E3YmdgVxFz7D2Ij6c1rwVF_T9R_HMC")

    now = datetime.utcnow()
    # Use a fixed test user ID so all requests use the same user across the test
    test_user_id = "00000000-0000-0000-0000-000000000001"
    payload = {
        "sub": test_user_id,  # Fixed UUID for consistency across test requests
        "roles": ["user"],
        "type": "access",  # Required by smarttrade-common token validation
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=24)).timestamp()),
        "iss": "auth-service",  # Required by smarttrade-common
        "aud": "smarttrade-services",  # Required by smarttrade-common
    }

    # Use python-jose (same as smarttrade-common) not PyJWT
    token = jwt.encode(payload, secret, algorithm="HS256")
    return token


# ────────────────────────────────────────────────────────────────────────────────
# FUNCTION-SCOPED FIXTURES: SERVICE CLIENTS
# ────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
async def bas_client(config: TestConfig, auth_token: str) -> AsyncGenerator[BASClient, None]:
    """
    Provide BASClient instance with proper setup/teardown.

    Scope: function (fresh client per test)
    """
    async with BASClient(
        base_url=config.bas_url,
        token=auth_token,
        timeout=config.timeout_medium,
    ) as client:
        yield client


@pytest.fixture
async def mock_client(
    config: TestConfig, auth_token: str
) -> AsyncGenerator[MockClient, None]:
    """
    Provide MockClient instance for deterministic fill injection.

    Scope: function (fresh client per test)
    """
    async with MockClient(
        base_url=config.mock_url,
        token=auth_token,
        timeout=config.timeout_fast,
    ) as client:
        yield client


@pytest.fixture
async def market_data_stream(mock_client: MockClient, config: TestConfig) -> MockMarketDataStream:
    """
    Provide MockMarketDataStream for real execution mode tests.

    Allows tests to inject price updates that trigger execution via Mock's PriceExecutionEngine.

    Scope: function (fresh stream per test)
    """
    stream = MockMarketDataStream(mock_client, broker_id=config.broker_id)
    yield stream
    stream.reset()


@pytest.fixture
async def mds_client(
    config: TestConfig, auth_token: str, event_collector: EventCollector, test_account_id: str
) -> AsyncGenerator[MDSWebSocketClient, None]:
    """
    Provide MDSWebSocketClient instance with subscription and event streaming.

    Scope: function (fresh connection per test)
    """
    # Use "ui" consumer type to avoid auto-subscription issues (BAS would need trading accounts)
    ws_url_with_path = f"{config.mds_ws_url}/ws/{config.broker_id}/ui"

    client = MDSWebSocketClient(
        ws_url=ws_url_with_path,
        account_id=test_account_id,
        token=auth_token,
        timeout=config.timeout_slow,
    )
    await client.connect()
    await client.subscribe_account(test_account_id)

    # Start background task to stream events into event_collector
    async def stream_to_collector():
        try:
            async for event in client.stream_events():
                # Extract order_id from event data (check both "data" and "payload" fields)
                event_data = event.get("data") or event.get("payload", {})
                order_id = event_data.get("order_id") or event_data.get("broker_order_id")

                if order_id:
                    # Extract status from event data, or infer from event type
                    status = event_data.get("status") or event_data.get("order_status")
                    event_type = event.get("type")

                    # Infer terminal status from event type
                    if event_type == "order_fill" and not status:
                        status = "FILLED"
                    elif event_type == "trade_exec" and not status:
                        status = "FILLED"

                    # Normalize event_data to have qty/price fields that assertion engine expects
                    # The assertion engine's extract_fills looks for "qty" in event.get("data")
                    normalized_data = dict(event_data)  # Copy event_data

                    # Map broker-specific field names to assertion engine expectations
                    # Multiple event types use different field names for quantity:
                    # - OrderFilledV1: delta_quantity
                    # - TradeExecutedV1: quantity
                    # - Generic: qty, fill_qty
                    if "delta_quantity" in normalized_data and "qty" not in normalized_data:
                        normalized_data["qty"] = normalized_data["delta_quantity"]
                    elif "quantity" in normalized_data and "qty" not in normalized_data:
                        normalized_data["qty"] = normalized_data["quantity"]

                    # Multiple event types use different field names for price:
                    # - OrderFilledV1: average_price
                    # - TradeExecutedV1: price
                    if "average_price" in normalized_data and "price" not in normalized_data:
                        normalized_data["price"] = float(normalized_data["average_price"]) if isinstance(normalized_data["average_price"], str) else normalized_data["average_price"]
                    elif "price" in normalized_data and isinstance(normalized_data["price"], str):
                        # Convert string prices to float for consistency
                        normalized_data["price"] = float(normalized_data["price"])

                    # Create event dict with normalized data
                    event_dict = {
                        "type": event_type,
                        "status": status,
                        "data": normalized_data,  # Contains normalized qty/price for assertion engine
                        "timestamp": event_data.get("timestamp") or event.get("timestamp"),
                    }

                    qty = normalized_data.get("qty")
                    log.debug(f"Collected event: order_id={order_id}, type={event_type}, status={status}, qty={qty}")
                    await event_collector.add_event(order_id, event_dict)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error in stream_to_collector: {e}", exc_info=True)

    stream_task = asyncio.create_task(stream_to_collector())

    yield client

    stream_task.cancel()
    try:
        await stream_task
    except asyncio.CancelledError:
        pass
    await client.disconnect()


# ────────────────────────────────────────────────────────────────────────────────
# FUNCTION-SCOPED FIXTURES: EVENT COLLECTION & HARNESS
# ────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def event_collector() -> EventCollector:
    """
    Provide EventCollector instance for async event collection.

    Scope: function (fresh collector per test)
    """
    collector = EventCollector(maxsize=1000)
    yield collector
    collector.clear()


@pytest.fixture
def assertions() -> AssertionEngine:
    """
    Provide AssertionEngine instance for order/position validation.

    Scope: function
    """
    return AssertionEngine()


@pytest.fixture
def scenario_engine() -> ScenarioEngine:
    """
    Provide ScenarioEngine instance for scenario loading.

    Scope: function
    """
    return ScenarioEngine()


# ────────────────────────────────────────────────────────────────────────────────
# FUNCTION-SCOPED FIXTURES: STATE CAPTURE (PRE/POST)
# ────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
async def pre_state(bas_client: BASClient, test_account_id: str, config: TestConfig) -> dict:
    """
    Capture funds and positions before test execution.

    Scope: function (setup phase)
    """
    try:
        funds = await bas_client.get_funds(config.broker_id, test_account_id)
        positions = await bas_client.get_positions(config.broker_id, test_account_id)
        return {"funds": funds, "positions": positions}
    except Exception as e:
        log.warning(f"Failed to capture pre-state: {e}")
        return {"funds": None, "positions": None}


@pytest.fixture
async def post_state(bas_client: BASClient, test_account_id: str, config: TestConfig):
    """
    Capture funds and positions after test execution.

    Scope: function (teardown phase, yields before test runs)

    Usage: Use in test to get post-test state
    """
    # Store in a dict that can be captured after test
    state = {"funds": None, "positions": None}

    yield state  # Let test run first

    try:
        state["funds"] = await bas_client.get_funds(config.broker_id, test_account_id)
        state["positions"] = await bas_client.get_positions(config.broker_id, test_account_id)
    except Exception as e:
        log.warning(f"Failed to capture post-state: {e}")


# ────────────────────────────────────────────────────────────────────────────────
# AUTOUSE FIXTURES: TEST ISOLATION & CLEANUP
# ────────────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
async def reset_test_account(
    bas_client: BASClient, test_account_id: str, config: TestConfig
) -> None:
    """
    Reset account state before each test for isolation.

    This is an autouse fixture that runs for every test.
    Attempts to cancel all open orders before test execution.

    Scope: function (autouse)
    """
    try:
        # Try to cancel all open orders for this account
        orders = await bas_client.get_orders(config.broker_id, test_account_id)
        for order in orders:
            status = order.status.upper() if hasattr(order, 'status') else order.get('status', '')
            if status not in ["FILLED", "CANCELLED", "REJECTED", "EXPIRED"]:
                try:
                    order_id = order.exchange_order_id if hasattr(order, 'exchange_order_id') else order.get('broker_order_id')
                    if order_id:
                        await bas_client.cancel_order(config.broker_id, test_account_id, order_id)
                except Exception:
                    pass  # Ignore cancellation errors
    except Exception:
        pass  # Account may not exist yet, that's ok

    yield  # Run test


@pytest.fixture
async def cleanup_test_account(
    bas_client: BASClient, test_account_id: str, config: TestConfig
) -> None:
    """
    Clean up account state after test execution.

    Optional aggressive cleanup fixture (not autouse).
    Can be explicitly requested in tests that need it.

    Scope: function
    """
    yield  # Let test run

    try:
        # Exit all open positions
        orders = await bas_client.get_orders(config.broker_id, test_account_id)
        for order in orders:
            status = order.status.upper() if hasattr(order, 'status') else order.get('status', '')
            if status not in ["FILLED", "CANCELLED", "REJECTED", "EXPIRED"]:
                try:
                    order_id = order.exchange_order_id if hasattr(order, 'exchange_order_id') else order.get('broker_order_id')
                    if order_id:
                        await bas_client.cancel_order(config.broker_id, test_account_id, order_id)
                except Exception:
                    pass
    except Exception:
        pass


# ────────────────────────────────────────────────────────────────────────────────
# FUNCTION-SCOPED FIXTURES: CHAOS TESTING
# ────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def chaos_engine() -> ChaosEngine:
    """
    Provide ChaosEngine for resilience and chaos testing.

    Scope: function (fresh engine per test)
    """
    engine = ChaosEngine()
    yield engine
    engine.reset()


# ────────────────────────────────────────────────────────────────────────────────
# HTML REPORT STYLING & ENHANCEMENTS
# ────────────────────────────────────────────────────────────────────────────────


def pytest_html_report_title(report):
    """Set HTML report title."""
    report.title = "SmartTrade E2E Test Report"
