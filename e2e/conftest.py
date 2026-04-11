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
import pytest_asyncio

# Load .env file for JWT_SECRET_KEY and other environment variables
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent.parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass  # python-dotenv not available, rely on environment

from e2e.config import TestConfig
from e2e.clients import BASClient, BASWebSocketClient, MDSWebSocketClient, MockClient
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
    config.addinivalue_line("markers", "sequential: tests that must run sequentially")
    config.addinivalue_line("markers", "slow: tests that need extended timeout")

    # Configure logging based on environment
    env = os.getenv("E2E_ENV", "dev").lower()
    log_level = "DEBUG" if env == "dev" else "INFO"
    configure_logging(log_level)

    # Ensure reports directory exists
    reports_dir = Path(__file__).parent / "reports"
    reports_dir.mkdir(exist_ok=True)


def pytest_collection_modifyitems(config, items):
    """Mark problematic tests as sequential to avoid WebSocket connection contention."""
    # Test classes/modules that have concurrent connection issues
    problematic_patterns = [
        "test_concurrent_orders_injection",
        "test_partial_fills_injection",
        "test_order_lifecycle_injection",
        "test_market_buy_real_execution",
        "test_partial_fills_real_execution",
    ]

    for item in items:
        # Mark tests as sequential if they match problematic patterns
        for pattern in problematic_patterns:
            if pattern in item.nodeid:
                item.add_marker(pytest.mark.sequential)
                break

        # Mark real execution tests as slow (they need more time)
        if "real_execution" in item.nodeid:
            item.add_marker(pytest.mark.slow)


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
def _configure_test_timeout(request):
    """
    Dynamically adjust test timeout based on test type.

    - Smoke tests: 30 seconds
    - Injection tests: 20 seconds
    - Real execution: 30 seconds (slower)
    - Resilience: 30 seconds
    - Sequential: 25 seconds
    """
    if request.node.get_closest_marker("smoke"):
        request.node.timeout = 30
    elif request.node.get_closest_marker("slow"):
        request.node.timeout = 35
    elif request.node.get_closest_marker("sequential"):
        request.node.timeout = 25
    # Default 60s from pytest.ini handles the rest


@pytest_asyncio.fixture(autouse=True)
async def setup_trading_account(bas_client, mock_client, test_account_id):
    """
    Create paper trading accounts (autouse).

    Automatically creates a paper trading account with fyers broker before each test.
    Paper accounts use real broker ID but account_type=PAPER to enable paper trading.

    Scope: function
    """
    broker_id = "fyers"  # Only setup primary broker (tests use fyers)

    try:
        # Delete any existing accounts (ensures clean slate)
        try:
            await bas_client.delete_trading_account(broker_id, test_account_id)
        except Exception:
            pass  # Account may not exist

        # Create PAPER trading account
        await bas_client.create_trading_account(
            broker_id=broker_id,
            account_id=test_account_id,
            initial_funds=Decimal("1000000.00"),
            account_type="PAPER",
        )
        log.debug(f"✅ Paper trading account created: {broker_id}/{test_account_id}")

        # Clean up execution state and positions (batch these for efficiency)
        try:
            await mock_client.cleanup_execution_state(broker_id, test_account_id)
            log.debug(f"✅ Execution state cleared: {broker_id}/{test_account_id}")
        except Exception as e:
            log.warning(f"⚠️ Execution state cleanup failed: {e}")

        try:
            await mock_client.cleanup_positions(broker_id, test_account_id)
            log.debug(f"✅ Positions cleared: {broker_id}/{test_account_id}")
        except Exception as e:
            log.warning(f"⚠️ Positions cleanup failed: {e}")

    except Exception as e:
        log.warning(f"⚠️ Paper account creation failed: {e}")

    # Yield control back to test
    yield

    # Cleanup is optional - accounts can be reused


@pytest_asyncio.fixture(autouse=True)
async def setup_broker_credentials(bas_client):
    """
    Seed broker credentials for MDS to use (autouse).

    Creates broker connections with test credentials before each test.
    MDS needs these credentials to validate trading accounts and initialize plugins.

    Scope: function
    """
    # Only setup fyers (primary broker)
    broker_id = "fyers"

    try:
        # Upsert broker connection with test credentials
        await bas_client.upsert_broker_connection(
            broker_id=broker_id,
            auth_type="api_key",
            credentials={
                "app_id": f"test_{broker_id}_app_id",
                "app_secret": f"test_{broker_id}_app_secret",
            }
        )
        log.debug(f"✅ Broker credentials seeded: {broker_id}")
    except Exception as e:
        log.warning(f"⚠️ Broker credential seeding failed: {e}")

    # Yield control back to test
    yield

    # Cleanup is optional - credentials can be reused


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
def auth_token(config: TestConfig) -> str:
    """
    Get authentication token for service access.

    Generates a JWT token using the same secret and library as the services.
    Uses test credentials for E2E testing.

    Scope: function (fresh token per test, but with consistent user ID)
    """
    from jose import jwt
    from datetime import datetime, timedelta

    # Load .env file again to ensure JWT_SECRET_KEY is available
    try:
        from dotenv import load_dotenv
        env_file = Path(__file__).parent.parent.parent / ".env"
        if env_file.exists():
            load_dotenv(env_file, override=True)  # Force reload
    except ImportError:
        pass

    # Secret from environment (must match docker-compose JWT_SECRET_KEY)
    secret = os.getenv("JWT_SECRET_KEY")
    if not secret:
        log.error("JWT_SECRET_KEY not found in environment. Check .env file or container environment.")
        raise ValueError("JWT_SECRET_KEY required for test authentication")

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


@pytest_asyncio.fixture
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


@pytest_asyncio.fixture
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


@pytest_asyncio.fixture
async def market_data_stream(mock_client: MockClient, config: TestConfig) -> MockMarketDataStream:
    """
    Provide MockMarketDataStream for real execution mode tests.

    Allows tests to inject price updates that trigger execution via Mock's PriceExecutionEngine.

    Scope: function (fresh stream per test)
    """
    stream = MockMarketDataStream(mock_client, broker_id=config.broker_id)
    yield stream
    stream.reset()


@pytest_asyncio.fixture
async def mds_client(
    config: TestConfig, auth_token: str, test_account_id: str
) -> AsyncGenerator[MDSWebSocketClient, None]:
    """
    Provide MDSWebSocketClient instance for market data only.

    Scope: function (fresh connection per test)

    Note: MDS WebSocket is now used for market data only (quotes, depth, candles).
    Account events (orders, trades, positions) are handled by BAS WebSocket.
    """
    ws_url_with_path = f"{config.mds_ws_url}/ws/{config.broker_id}/ui"

    client = MDSWebSocketClient(
        ws_url=ws_url_with_path,
        account_id=test_account_id,
        token=auth_token,
        timeout=config.timeout_slow,
    )
    await client.connect()
    await client.subscribe_account(test_account_id)

    yield client

    # Aggressive cleanup
    try:
        await client.disconnect()
    except Exception as e:
        log.warning(f"Error disconnecting MDS client: {e}")

    # Force close underlying WebSocket
    if hasattr(client, 'ws') and client.ws is not None:
        try:
            await client.ws.close()
        except Exception:
            pass


@pytest_asyncio.fixture
async def bas_ws_client(
    config: TestConfig, auth_token: str, test_account_id: str, request
) -> AsyncGenerator[BASWebSocketClient, None]:
    """
    Provide BASWebSocketClient instance for trading account events.

    Scope: function (fresh connection per test)

    Handles order fills, trades, and position updates.
    Automatically streams events into the event_collector for test assertions.
    """
    client = BASWebSocketClient(
        ws_url=config.bas_ws_url,
        account_id=test_account_id,
        token=auth_token,
        timeout=config.timeout_slow,
    )
    await client.connect()
    await client.subscribe_account(test_account_id)

    # Get the event_collector fixture if it exists (it will be created after us)
    # We store it on client so event_collector fixture can wire it up
    client._event_collector = None

    # Start background task to stream account events
    async def stream_account_events():
        try:
            async for event in client.stream_events():
                # Skip if collector not initialized (wait for next event)
                if client._event_collector is None:
                    continue

                # Extract order_id early to avoid processing irrelevant events
                event_data = event.get("data") or {}
                order_id = event_data.get("order_id") or event_data.get("broker_order_id")

                if not order_id:
                    log.debug(f"No order_id in BAS event type={event.get('type')}, skipping")
                    continue

                # Extract status from event data
                status = event_data.get("status") or event_data.get("order_status")
                event_type = event.get("type")

                # Map BAS event types to internal format
                event_type_map = {
                    "order.filled.v1": "order_fill",
                    "trade.executed.v1": "trade_exec",
                    "position.updated.v1": "position_update",
                }
                normalized_event_type = event_type_map.get(event_type, event_type)

                # Infer terminal status from event type
                if normalized_event_type == "order_fill" and not status:
                    try:
                        filled_pct = float(event_data.get("filled_percentage", 0))
                    except (TypeError, ValueError):
                        filled_pct = 0.0
                    status = "FILLED" if filled_pct >= 100.0 else "PARTIALLY_FILLED"
                elif normalized_event_type == "order_cancelled" and not status:
                    status = "CANCELLED"

                # Normalize event_data to have qty/price fields that assertion engine expects
                normalized_data = dict(event_data)

                # Map broker-specific field names to assertion engine expectations
                if "delta_quantity" in normalized_data and "qty" not in normalized_data:
                    normalized_data["qty"] = normalized_data["delta_quantity"]
                    normalized_data["fill_qty"] = normalized_data["delta_quantity"]
                elif "quantity" in normalized_data and "qty" not in normalized_data:
                    normalized_data["qty"] = normalized_data["quantity"]
                    normalized_data["fill_qty"] = normalized_data["quantity"]

                # Map price fields
                if "average_price" in normalized_data and "price" not in normalized_data:
                    try:
                        normalized_data["price"] = float(normalized_data["average_price"])
                    except (TypeError, ValueError):
                        normalized_data["price"] = normalized_data["average_price"]
                elif "price" in normalized_data and isinstance(normalized_data["price"], str):
                    try:
                        normalized_data["price"] = float(normalized_data["price"])
                    except (TypeError, ValueError):
                        pass

                # Create event dict with normalized data
                event_dict = {
                    "type": normalized_event_type,
                    "status": status,
                    "data": normalized_data,
                    "timestamp": event_data.get("timestamp") or event.get("timestamp"),
                }

                qty = normalized_data.get("qty")
                log.debug(f"Collected BAS event: order_id={order_id}, type={normalized_event_type}, status={status}, qty={qty}")
                await client._event_collector.add_event(order_id, event_dict)
        except asyncio.CancelledError:
            log.debug("BAS event streaming cancelled")
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error in stream_account_events: {e}", exc_info=True)

    stream_task = asyncio.create_task(stream_account_events())

    yield client

    # Aggressive cleanup to ensure WebSocket is fully closed
    stream_task.cancel()
    try:
        await stream_task
    except asyncio.CancelledError:
        pass

    # Ensure WebSocket is fully disconnected
    try:
        await client.disconnect()
    except Exception as e:
        log.warning(f"Error disconnecting BAS client: {e}")

    # Force close the underlying WebSocket connection
    if hasattr(client, 'ws') and client.ws is not None:
        try:
            await client.ws.close()
        except Exception:
            pass


# ────────────────────────────────────────────────────────────────────────────────
# FUNCTION-SCOPED FIXTURES: EVENT COLLECTION & HARNESS
# ────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def event_collector(bas_ws_client) -> EventCollector:
    """
    Provide EventCollector instance for async event collection.

    Scope: function (fresh collector per test)

    Wires itself to bas_ws_client so BAS events are streamed into this collector.
    Memory is cleared after test completes.
    """
    collector = EventCollector(maxsize=1000)
    # Wire the collector to the bas_ws_client so it can stream events
    bas_ws_client._event_collector = collector
    yield collector
    # Aggressive cleanup: clear all events after test (not just queues)
    collector.clear()


@pytest_asyncio.fixture(autouse=True)
async def cleanup_event_memory(event_collector):
    """
    Autouse fixture to ensure event_collector memory is fully cleared after test.

    Scope: function (runs after every test that uses event_collector)
    """
    yield
    # After test, ensure event_collector is cleaned up
    event_collector.clear()


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


@pytest_asyncio.fixture
async def place_and_sync_order(bas_client: BASClient, mock_client: MockClient, config: TestConfig):
    """
    Provide a helper function to place an order in BAS and sync it to paper broker service.

    This ensures orders exist in paper broker service with correct instrument_id (from MDS)
    before fill injection is attempted.

    Usage in tests:
        [order_resp] = await place_and_sync_order(broker_id, account_id, order_request)

    Args (passed to helper):
        broker_id: Broker identifier
        account_id: Account identifier
        order_request: BasOrderPlaceRequest

    Returns:
        List of order responses from BAS (same as place_order)

    Scope: function
    """
    async def helper(broker_id: str, account_id: str, order_request):
        # Step 1: Place order in BAS (returns order with instrument_id from MDS)
        order_responses = await bas_client.place_order(broker_id, account_id, order_request)

        # Step 2: Sync each order to paper broker service using instrument_id (not broker symbol)
        for order_resp in order_responses:
            await mock_client.sync_order(broker_id, account_id, order_resp.model_dump() if hasattr(order_resp, 'model_dump') else order_resp)
            log.debug(f"Order synced: {order_resp.get('broker_order_id') if isinstance(order_resp, dict) else order_resp.broker_order_id}")

        return order_responses

    return helper


# ────────────────────────────────────────────────────────────────────────────────
# FUNCTION-SCOPED FIXTURES: STATE CAPTURE (PRE/POST)
# ────────────────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
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


@pytest_asyncio.fixture
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


@pytest_asyncio.fixture(autouse=True)
async def reset_test_account(
    bas_client: BASClient, test_account_id: str, config: TestConfig
) -> None:
    """
    Reset account state before each test for isolation.

    Attempts to cancel all open orders before test execution (with timeout).

    Scope: function (autouse)
    """
    try:
        # Timeout get_orders to avoid hanging on slow connections
        orders = await asyncio.wait_for(
            bas_client.get_orders(config.broker_id, test_account_id),
            timeout=5.0,
        )
        # Cancel open orders in parallel (bounded by 5 concurrent cancellations)
        cancel_semaphore = asyncio.Semaphore(5)

        async def cancel_if_open(order):
            status = order.status.upper() if hasattr(order, 'status') else order.get('status', '')
            if status not in ["FILLED", "CANCELLED", "REJECTED", "EXPIRED"]:
                try:
                    order_id = order.exchange_order_id if hasattr(order, 'exchange_order_id') else order.get('broker_order_id')
                    if order_id:
                        async with cancel_semaphore:
                            await bas_client.cancel_order(config.broker_id, test_account_id, order_id)
                except Exception:
                    pass  # Ignore cancellation errors

        if orders:
            await asyncio.gather(*[cancel_if_open(order) for order in orders], return_exceptions=True)
    except asyncio.TimeoutError:
        log.debug(f"Timeout resetting account {test_account_id}, skipping order cancellations")
    except Exception:
        pass  # Account may not exist yet, that's ok

    yield  # Run test


@pytest_asyncio.fixture
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
