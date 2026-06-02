"""
Base pytest configuration for E2E tests.

Provides comprehensive fixtures for service clients, event collection, assertions,
and lifecycle management. All fixtures are properly scoped and cleaned up.
"""

import asyncio
import hashlib
import logging
import os
import time
import uuid
from typing import AsyncGenerator
from pathlib import Path
from decimal import Decimal
from datetime import datetime

import pytest
import pytest_asyncio
import httpx

# Load .env file for JWT_SECRET_KEY and other environment variables
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent.parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass  # python-dotenv not available, rely on environment

from broker_adapter_service.schemas.order_dtos import BasOrderPlaceRequest, BasOrderLeg
from smarttrade_common.schemas.types import OrderSide, OrderType, TimeInForce, PositionType, InstrumentType

from e2e.config import TestConfig
from e2e.clients import (
    BASClient,
    MDSWebSocketClient,
    MockClient,
    PortfolioClient,
    JournalClient,
    BrokerStateClient,
    create_broker_state_client,
)
from e2e.harness import EventCollector, AssertionEngine, ScenarioEngine, RedisEventCollector
from e2e.harness.redis_observer import RedisStreamObserver
from e2e.fixtures.logging import configure_logging
from e2e.fixtures.market_data_stream import MockMarketDataStream
from e2e.fixtures.chaos_engine import ChaosEngine
from e2e.fixtures.instruments import InstrumentCatalog
from e2e.fixtures.test_instruments_data import get_test_instruments
from e2e.fixtures.quote_injection import QuoteInjector


log = logging.getLogger(__name__)


async def wait_for_portfolio_service_listeners(portfolio_url: str, timeout: int = 30) -> None:
    """
    Wait for Portfolio Service event listeners to be fully subscribed.

    Polls the Portfolio Service health endpoint to ensure event consumers are ready.
    This prevents the race condition where tests publish events before listeners are subscribed.

    Args:
        portfolio_url: Portfolio Service base URL (e.g., "http://localhost:8008")
        timeout: Maximum wait time in seconds

    Raises:
        TimeoutError: If listeners are not ready within timeout
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            # Make a simple request to trigger service startup completion
            # Once we get a 200 response, the service is ready
            async with httpx.AsyncClient(base_url=portfolio_url, timeout=5.0) as client:
                await client.get("/ready")
            log.info("✅ Portfolio Service listeners ready")
            # Give an extra 2 seconds to ensure Redis connections are fully established
            await asyncio.sleep(2)
            return
        except Exception as e:
            log.debug(f"Portfolio Service not ready yet: {e}")
            await asyncio.sleep(1)

    raise TimeoutError(f"Portfolio Service listeners not ready after {timeout}s")


def pytest_configure(config):
    """Register custom markers and configure logging."""
    config.addinivalue_line("markers", "smoke: quick sanity tests")
    config.addinivalue_line("markers", "injection: deterministic injection mode")
    config.addinivalue_line("markers", "real_execution: real execution mode")
    config.addinivalue_line("markers", "resilience: network failures")
    config.addinivalue_line("markers", "chaos: chaos testing")
    config.addinivalue_line("markers", "sequential: tests that must run sequentially")
    config.addinivalue_line("markers", "slow: tests that need extended timeout")
    config.addinivalue_line("markers", "live_ws: live WebSocket separation tests")
    config.addinivalue_line("markers", "event_bus: direct Redis stream observation tests")
    config.addinivalue_line("markers", "architecture: architecture boundary tests")

    # Configure logging based on environment
    log_level = os.getenv("E2E_LOG_LEVEL", "INFO").upper()
    configure_logging(log_level)

    # Ensure reports directory exists
    reports_dir = Path(__file__).parent / "reports"
    reports_dir.mkdir(exist_ok=True)


async def trigger_mds_instrument_restream(client: httpx.AsyncClient, config: TestConfig) -> None:
    """
    Trigger MDS to restream all instruments to Redis.

    This calls the MDS /api/v1/instruments/restream endpoint which publishes
    all instruments from the MDS database to the Redis stream market.instrument.
    BAS will consume these events and populate its instruments table.

    This is a safety net to ensure BAS has the full instrument catalog even if
    it missed events at startup.
    """
    try:
        response = await client.post(f"{config.mds_url}/api/v1/instruments/restream", timeout=30.0)
        if response.status_code == 200:
            result = response.json()
            count = result.get("count", 0)
            log.info(f"✅ MDS restreamed {count} instruments to Redis market.instrument")
            if count == 0:
                log.warning("⚠️ MDS has 0 instruments — run Fyers instrument sync before E2E tests")
        else:
            log.warning(f"⚠️ MDS restream returned status {response.status_code}: {response.text}")
    except Exception as e:
        log.error(f"❌ Failed to trigger MDS instrument restream: {e}")
        raise


def pytest_sessionstart(session):
    """Wait for all services to be fully ready before running tests.

    Instrument sync is performed ONCE at session start as a fire-and-forget
    operation. Subsequent failures or timeouts do not retry — multiple
    concurrent restreams overwhelm MDS (132k+ instruments in 500-batch chunks).
    """
    config = TestConfig.from_env()

    async def wait_for_portfolio_ready():
        """Wait for Portfolio Service readiness (separate from instrument sync)."""
        async with httpx.AsyncClient() as client:
            start = time.time()
            while time.time() - start < 60:
                try:
                    response = await client.get(f"{config.portfolio_url}/ready")
                    if response.status_code == 200:
                        log.info("✅ Portfolio Service is ready")
                        log.info("Waiting for event listeners to initialize (10s)...")
                        await asyncio.sleep(10)
                        await wait_for_portfolio_service_listeners(config.portfolio_url, timeout=30)
                        return True
                except Exception as e:
                    log.debug(f"Portfolio Service not ready: {e}")
                await asyncio.sleep(1)
            return False

    async def trigger_instrument_sync_once():
        """Trigger MDS instrument restream — exactly once. Fire-and-forget on timeout."""
        log.info("Skipping MDS instrument restream (disabled for E2E testing due to performance issues)")
        # DISABLED FOR E2E TESTING - MDS instrument restream takes too long
        # log.info("Triggering MDS instrument restream to Redis (one-time at session start)...")
        # async with httpx.AsyncClient() as client:
        #     try:
        #         await trigger_mds_instrument_restream(client, config)
        #     except Exception as e:
        #         log.warning(
        #             f"⚠️ MDS instrument restream call did not complete: {e}. "
        #             "Continuing — BAS likely has instruments from prior MDS startup sync."
        #         )

    async def session_init():
        log.info("Waiting for services to be fully initialized...")
        ready = await wait_for_portfolio_ready()
        if not ready:
            log.warning("Portfolio Service did not become ready in time — proceeding anyway")
        # Trigger instrument sync ONCE — independent of readiness loop
        # await trigger_instrument_sync_once()
        # log.info("Waiting for BAS to consume instruments (5s)...")
        # await asyncio.sleep(5)
        log.info("✅ E2E test environment initialized")

    try:
        asyncio.run(session_init())
    except Exception as e:
        log.error(f"Failed to initialize E2E test session: {e}")
        log.warning("Proceeding with tests despite initialization issues")


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
# SESSION-SCOPED FIXTURES: INSTRUMENT CATALOG & CLIENTS
# ────────────────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(scope="session")
async def instrument_catalog(config: TestConfig) -> InstrumentCatalog:
    """
    Provide session-scoped instrument catalog by fetching real instruments from MDS.

    The deployment docker-compose has MDS DB populated with real Fyers instruments.
    Tests fetch the instrument list from MDS and use those real IDs for order placement.

    Architecture notes:
    - MDS is the source of truth for instrument metadata
    - Tests query MDS /api/v1/instruments to discover available instruments
    - Tests use real canonical instrument IDs (e.g., NSE:CM:EQUITY:SBIN)
    - BAS has consumed these same instruments via market.instrument Redis stream

    Scope: session (loaded once per test run)
    """
    log.info("Loading real instruments from MDS for E2E tests")

    # Fetch real instruments from MDS
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{config.mds_url}/api/v1/instruments", timeout=15.0)
            response.raise_for_status()
            data = response.json()
            instruments_data = data.get("instruments", [])
        except Exception as e:
            log.error(f"Failed to fetch instruments from MDS: {e}")
            raise

    if not instruments_data:
        raise RuntimeError(
            "MDS has 0 instruments. Run Fyers instrument sync in the deployment environment before E2E tests."
        )

    log.info(f"✅ Loaded {len(instruments_data)} real instruments from MDS")

    # Create catalog from real instruments
    catalog = InstrumentCatalog(instruments_data)
    await catalog.load()
    log.info(f"✅ Instrument catalog ready: {catalog.count()} instruments")

    return catalog


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
async def setup_trading_account(
    bas_client, mock_client, portfolio_client, test_account_id, instrument_catalog
):
    """
    Create the BAS trading-account record (autouse).

    BAS owns trading-account metadata and is the only service we explicitly
    create the account in. The matching PBS AccountBalance row is created
    lazily on first access (PBS account_repo.get_with_lock auto-inserts with
    DEFAULT_INITIAL_BALANCE = 1_000_000), so no PBS account-creation call is
    needed.

    Scope: function
    """
    broker_id = "fyers"  # Only setup primary broker (tests use fyers)

    try:
        # Delete any existing accounts (ensures clean slate)
        try:
            await bas_client.delete_trading_account(broker_id, test_account_id)
        except Exception:
            pass  # Account may not exist

        # Create PAPER trading account in BAS. PBS AccountBalance is auto-
        # created on first order placement with DEFAULT_INITIAL_BALANCE.
        await bas_client.create_trading_account(
            broker_id=broker_id,
            account_id=test_account_id,
            account_type="PAPER",
        )
        log.debug(f"✅ Paper trading account created: {broker_id}/{test_account_id}")

        # Start the account session with guaranteed WebSocket connection
        # This ensures BAS is ready to receive execution updates before orders are placed
        try:
            session_status = await bas_client.start_account_session(
                broker_id=broker_id,
                account_id=test_account_id,
            )
            log.debug(
                f"✅ Account session started: {broker_id}/{test_account_id} | "
                f"status={session_status.get('status')} | "
                f"bootstrapped={session_status.get('bootstrapped')} | "
                f"ws_connected={session_status.get('ws_connected')}"
            )
        except Exception as e:
            log.warning(f"⚠️ Account session start failed (will use lazy bootstrap): {e}")

        # PBS account is now created synchronously by BAS when PAPER account is created
        # No need for manual PBS account cleanup - BAS handles it on account deletion
        # Only clear price cache to prevent LTP leakage between tests
        try:
            await mock_client.cleanup_price_cache()
            log.debug("✅ PBS price_cache cleared")
        except Exception as e:
            log.warning(f"⚠️ price_cache cleanup failed: {e}")

        # Inject prices for common instruments to prevent VAL_001 errors
        # MARKET orders require LTP for fund reservation with slippage buffer
        try:
            from decimal import Decimal
            # Get first 20 instruments from catalog to cover most test scenarios
            instruments = instrument_catalog.list_all()[:20]
            for instrument in instruments:
                instrument_id = instrument.get("id")
                if instrument_id:
                    try:
                        await mock_client.inject_price_update(
                            broker_id=broker_id,
                            instrument_id=instrument_id,
                            ltp=Decimal("100.00"),
                        )
                    except Exception as price_error:
                        # Log but don't fail - individual price injection failures shouldn't block tests
                        log.debug(f"Failed to inject price for {instrument_id}: {price_error}")
            log.debug(f"✅ Injected prices for {len(instruments)} instruments")
        except Exception as e:
            log.warning(f"⚠️ Price injection failed: {e}")

        # Clean up portfolio positions
        try:
            await portfolio_client.cleanup_positions()
            log.debug("✅ Portfolio aggregated positions cleared")
        except Exception as e:
            log.warning(f"⚠️ Portfolio positions cleanup failed: {e}")

    except Exception as e:
        log.warning(f"⚠️ Paper account creation failed: {e}")

    # Yield control back to test
    yield

    # Cleanup is optional - accounts can be reused


@pytest_asyncio.fixture
async def setup_broker_credentials(bas_client):
    """
    Seed broker credentials for MDS to use (NOT autouse).

    Creates broker connections with test credentials before each test.
    MDS needs these credentials to validate trading accounts and initialize plugins.

    Scope: function
    Note: Removed autouse=True in v4.0 because broker connection updates
    invalidate user sessions, breaking injection tests. Use explicitly for
    tests that require MDS integration.
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


@pytest.fixture(scope="session")
def test_account_id() -> str:
    """
    Single shared account for all tests in the session.

    Test isolation is preserved via setup_trading_account fixture which deletes
    and recreates the account before each test. Clients are now function-scoped
    to avoid session-scoped HTTP connection issues.

    Scope: session
    """
    return "TEST_E2E_SHARED"


@pytest_asyncio.fixture
async def isolated_test_account(
    bas_client,
    mock_client,
    portfolio_client,
):
    """
    Create a unique isolated trading account per test.

    Generates a unique account ID per test to avoid conflicts in concurrent
    testing scenarios. Performs full cleanup including BAS account deletion,
    PBS state cleanup, and Portfolio position cleanup.

    Scope: function (unique per test)
    """
    broker_id = "fyers"
    unique_account_id = f"TEST_ISO_{uuid.uuid4().hex[:12]}"

    try:
        # Create PAPER trading account in BAS
        await bas_client.create_trading_account(
            broker_id=broker_id,
            account_id=unique_account_id,
            account_type="PAPER",
        )
        log.debug(f"✅ Isolated paper trading account created: {broker_id}/{unique_account_id}")

        yield unique_account_id

    except Exception as e:
        log.warning(f"⚠️ Isolated account creation failed: {e}")
        raise

    finally:
        # Cleanup: delete account and all associated state
        # PBS account and state are cleaned up automatically by BAS when account is deleted
        try:
            await bas_client.delete_trading_account(broker_id, unique_account_id)
            log.debug(f"✅ BAS trading account deleted (PBS cleanup handled synchronously): {broker_id}/{unique_account_id}")
        except Exception as e:
            log.warning(f"⚠️ BAS account deletion failed: {e}")

        # Clean up portfolio positions
        try:
            await portfolio_client.cleanup_positions()
            log.debug("✅ Portfolio aggregated positions cleared")
        except Exception as e:
            log.warning(f"⚠️ Portfolio positions cleanup failed: {e}")


@pytest.fixture(scope="session")
def test_user_id() -> str:
    """
    Single shared user UUID for all tests in the session.

    Must match the `sub` claim in auth_token; many components (BAS/PBS
    subscription publisher, MDS UI WS routing, RBAC) key state on user_id
    so tests need a single canonical value.

    Scope: session
    """
    return "00000000-0000-0000-0000-000000000001"


# ────────────────────────────────────────────────────────────────────────────────
# FUNCTION-SCOPED FIXTURES: AUTHENTICATION
# ────────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def auth_token(config: TestConfig, test_user_id: str) -> str:
    """
    Get authentication token for service access.

    JWT is valid for 1440 minutes — far longer than any test session.
    Created once and reused by all session-scoped clients.

    Scope: session
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


@pytest.fixture(scope="session")
def admin_token(config: TestConfig) -> str:
    """
    Get admin authentication token for testing admin functionality.

    Uses the default admin credentials that are seeded by the auth service.
    JWT is valid for 1440 minutes — far longer than any test session.

    Scope: session
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

    # Use a fixed admin user ID for testing
    admin_user_id = "00000000-0000-0000-0000-000000000002"

    now = datetime.utcnow()
    payload = {
        "sub": admin_user_id,  # Admin user ID
        "roles": ["admin"],  # Admin role
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
    Provide BASClient instance. Created per test to avoid session-scoped issues.

    Scope: function
    """
    async with BASClient(
        base_url=config.bas_url,
        token=auth_token,
        timeout=config.timeout_medium,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def admin_bas_client(config: TestConfig, admin_token: str) -> AsyncGenerator[BASClient, None]:
    """
    Provide BASClient instance with admin token for testing admin functionality.

    Scope: function
    """
    async with BASClient(
        base_url=config.bas_url,
        token=admin_token,
        timeout=config.timeout_medium,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def mock_client(
    config: TestConfig, auth_token: str, admin_token: str
) -> AsyncGenerator[MockClient, None]:
    """
    Provide MockClient instance for fill injection.

    inject_fill drives PBS fills by publishing to the Redis stream
    `market.quote` (production path) — there is no longer an HTTP
    /execute shortcut, so we pass the redis URL here.

    Scope: function
    """
    async with MockClient(
        base_url=config.mock_url,
        token=auth_token,
        timeout=config.timeout_fast,
        redis_url=config.redis_url,
        admin_token=admin_token,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def portfolio_client(
    config: TestConfig, auth_token: str, test_account_id: str
) -> AsyncGenerator[PortfolioClient, None]:
    """
    Provide PortfolioClient for testing Portfolio Service async aggregation.

    Scope: function
    """
    async with PortfolioClient(
        base_url=config.portfolio_url,
        token=auth_token,
        broker_id="fyers",
        account_id=test_account_id,
        timeout=config.timeout_medium,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def journal_client(
    config: TestConfig, auth_token: str, test_account_id: str
) -> AsyncGenerator[JournalClient, None]:
    """
    Provide JournalClient for testing Journal Service audit trail.

    Scope: function
    """
    async with JournalClient(
        base_url=config.journal_url,
        token=auth_token,
        broker_id="fyers",
        account_id=test_account_id,
        timeout=config.timeout_medium,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def admin_journal_client(
    config: TestConfig, admin_token: str
) -> AsyncGenerator[JournalClient, None]:
    """
    Provide JournalClient instance with admin token for testing admin functionality.

    Scope: function
    """
    async with JournalClient(
        base_url=config.journal_url,
        token=admin_token,
        broker_id="fyers",
        account_id="TEST_ACCOUNT",
        timeout=config.timeout_medium,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def market_data_stream(mock_client: MockClient, config: TestConfig) -> MockMarketDataStream:
    """
    Provide MockMarketDataStream for real execution mode tests.

    Publishes price updates on the production Redis stream `market.quote`
    (read by BAS QuoteStore and PBS PriceExecutionEngine) and also calls the
    PBS HTTP shortcut for deterministic LIMIT/STOP triggering.

    Scope: function (fresh stream per test)
    """
    stream = MockMarketDataStream(
        mock_client,
        broker_id=config.broker_id,
        redis_url=config.redis_url,
    )
    yield stream
    stream.reset()
    await stream.close()


@pytest_asyncio.fixture
async def redis_observer(config: TestConfig) -> AsyncGenerator[RedisStreamObserver, None]:
    """
    Provide RedisStreamObserver for direct Redis stream observation.

    Allows tests to validate events by reading directly from Redis streams.
    Uses separate consumer group to avoid interfering with production event flow.

    Scope: function (fresh observer per test)
    """
    observer = RedisStreamObserver(redis_url=config.redis_url)
    await observer.start()
    # Pre-warm consumer groups at the current stream tail so events emitted
    # during the test are captured. Without this, the consumer group is
    # created lazily inside observe_stream() — by which point any events the
    # test produced before its first observe_stream() call are already past
    # the group's $ position and invisible.
    for event_type in ["order.updated", "trade.executed", "position.updated"]:
        await observer._ensure_consumer_group(f"events:{event_type}")
    yield observer
    # Cleanup: delete observer consumer groups
    for event_type in ["order.updated", "trade.executed", "position.updated"]:
        await observer.delete_consumer_group(event_type)
    await observer.stop()


@pytest_asyncio.fixture
async def quote_injector(config: TestConfig, mock_client: MockClient) -> AsyncGenerator[QuoteInjector, None]:
    """
    Provide QuoteInjector for two-level quote injection.

    Injects quotes at both:
    1. Redis stream (BAS QuoteStore)
    2. PBS price endpoint (price-driven execution)

    Scope: function (fresh injector per test)
    """
    injector = QuoteInjector(redis_url=config.redis_url, mock_client=mock_client)
    yield injector
    await injector.close()


@pytest_asyncio.fixture
async def mds_client(
    config: TestConfig, auth_token: str, test_account_id: str, test_user_id: str
) -> AsyncGenerator[MDSWebSocketClient, None]:
    """
    Provide MDSWebSocketClient bound to the MDS UI WebSocket channel.

    Scope: function — created per test to avoid session-scoped issues.

    The MDS UI channel is exclusively a UI-facing market data feed (quotes,
    depth, candles, instrument subscription requests). BAS and PBS no longer
    consume MDS via WebSocket — they read market data from the Redis stream
    market.quote. Tests must therefore not use mds_client as a stand-in
    for the BAS/PBS data path.

    Account/execution events are collected via Redis Streams using redis_event_collector.
    """
    ws_url_with_path = f"{config.mds_ws_url}/ws/{config.broker_id}/{test_account_id}/ui"

    client = MDSWebSocketClient(
        ws_url=ws_url_with_path,
        account_id=test_account_id,
        user_id=test_user_id,
        token=auth_token,
        timeout=config.timeout_slow,
    )
    await client.connect()
    await client.subscribe_account(test_account_id)

    yield client

    # Function teardown: disconnect after each test
    try:
        await client.disconnect()
    except Exception as e:
        log.warning(f"Error disconnecting MDS client: {e}")


# ────────────────────────────────────────────────────────────────────────────────
# FUNCTION-SCOPED FIXTURES: EVENT COLLECTION & HARNESS
# ────────────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def gc_cleanup():
    """
    Force garbage collection after each test to prevent memory accumulation.

    Scope: function (runs after every test)
    """
    yield
    # Force garbage collection after test cleanup
    import gc
    gc.collect()


@pytest.fixture
def event_collector() -> EventCollector:
    """
    Provide EventCollector instance for async event collection.

    Scope: function (fresh collector per test)

    NOTE: Updated for stateless architecture - no longer depends on bas_ws_client.
    Events are now collected via Redis streams using redis_event_collector fixture.
    Memory is cleared after test completes.
    """
    # Reduced maxsize from 1000 to 100 to limit memory per test
    collector = EventCollector(maxsize=100)
    yield collector
    # Aggressive cleanup: drain all queues, clear all events, and reset state
    try:
        collector.clear()  # Drains queues and clears events
    except Exception as e:
        log.warning(f"Error clearing event collector: {e}")
    # Remove reference
    collector = None


@pytest_asyncio.fixture
async def broker_state_client(config: TestConfig, auth_token: str) -> BrokerStateClient:
    """
    Provide broker state client for direct broker queries.

    Scope: function (created per test)

    Broker is the single source of truth for order/position/trade state in the
    stateless architecture. This client queries the broker directly.
    """
    client = create_broker_state_client(
        broker_type=config.broker_type,
        base_url=config.broker_api_url,
        token=auth_token,
    )
    async with client:
        yield client


@pytest_asyncio.fixture
async def redis_event_collector(config: TestConfig) -> RedisEventCollector:
    """
    Provide Redis event collector for stream-based event collection.

    Scope: function (created per test)

    Collects events directly from Redis Streams (bypassing service WebSockets).
    Uses consumer groups for reliable event consumption with idempotency.
    """
    import uuid
    
    collector = RedisEventCollector(
        redis_url=config.redis_url,
        consumer_group=f"{config.redis_stream_consumer_group}-{uuid.uuid4().hex[:8]}",
    )
    await collector.connect()
    await collector.subscribe_to_streams([
        "events:order.updated",
        "events:trade.executed",
        "events:position.updated",
    ])
    
    yield collector
    
    await collector.cleanup()
    await collector.disconnect()


@pytest_asyncio.fixture
async def redis_client(config: TestConfig):
    """
    Provide direct Redis client for Redis stream operations.

    Scope: function (created per test)

    Provides direct access to Redis for stream operations in tests that
    need to manually interact with Redis Streams (e.g., resilience tests,
    performance tests, MDS quote production tests).
    """
    import redis.asyncio as redis
    
    client = await redis.from_url(config.redis_url, encoding="utf-8", decode_responses=True)
    yield client
    await client.close()


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
async def place_and_sync_order(bas_client: BASClient, config: TestConfig, instrument_catalog: InstrumentCatalog):
    """
    Place an order via BAS — and only via BAS.

    BAS' paper plugin internally forwards the order to PBS' create_order
    endpoint, so PBS receives the order through the production path. Tests
    must NOT POST to PBS' /api/v1/order/... directly: that bypasses risk
    validation, idempotency caching, the BAS↔PBS WebSocket session setup,
    and the order-state machine in BAS.

    Supports both dict (simplified) and BasOrderPlaceRequest formats for
    order_request.

    Usage in tests:
        # Dict format (automatically converted to BasOrderPlaceRequest)
        [order_resp] = await place_and_sync_order(
            broker_id, account_id,
            order_request={"instrument_id": "...", "side": "BUY", "qty": 100, ...}
        )

        # Or Pydantic model format (passed directly)
        [order_resp] = await place_and_sync_order(broker_id, account_id, order_request=BasOrderPlaceRequest(...))

    Returns: List of order response dicts from BAS.

    Scope: function
    """
    async def helper(broker_id: str, account_id: str, order_request):
        # Convert dict to BasOrderPlaceRequest if needed
        if isinstance(order_request, dict):
            order_request = _dict_to_order_request(order_request, instrument_catalog)

        # Place order via BAS only. BAS' paper plugin auto-forwards to PBS.
        order_responses = await bas_client.place_order(broker_id, account_id, order_request)
        return [
            resp.model_dump() if hasattr(resp, 'model_dump') else resp
            for resp in order_responses
        ]

    return helper


def _dict_to_order_request(order_dict: dict, instrument_catalog: InstrumentCatalog) -> BasOrderPlaceRequest:
    """
    Convert simplified dict order format to BasOrderPlaceRequest.

    Dict format:
        {
            "instrument_id": "NSE:SBIN:EQ",
            "position_type": "INTRADAY",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": 100,
            "ltp": Decimal("550.00"),  # optional, defaults to 100.00
            "price": Decimal("550.00"),  # optional, for LIMIT orders
            "stop_price": Decimal("545.00"),  # optional, for STOP orders
        }
    """
    instrument_id = order_dict["instrument_id"]
    instrument = instrument_catalog.get_by_id(instrument_id)

    if not instrument:
        raise ValueError(f"Instrument not found: {instrument_id}")

    # Build the leg
    leg = BasOrderLeg(
        instrument_id=instrument_id,
        instrument_type=InstrumentType(order_dict.get("instrument_type", "EQUITY")),
        side=OrderSide(order_dict["side"].upper()),
        qty=int(order_dict["qty"]),
        order_type=OrderType(order_dict["order_type"].upper()),
        ltp=Decimal(str(order_dict.get("ltp", "100.00"))),
        price=Decimal(str(order_dict["price"])) if "price" in order_dict else None,
        stop_price=Decimal(str(order_dict["stop_price"])) if "stop_price" in order_dict else None,
    )

    # Build the request
    return BasOrderPlaceRequest(
        client_order_id=f"e2e_{uuid.uuid4().hex[:12]}",
        position_type=PositionType(order_dict.get("position_type", "INTRADAY").upper()),
        legs=[leg],
        underlying_symbol=instrument.get("symbol", instrument_id),
        tif=TimeInForce(order_dict.get("tif", "DAY").upper()),
    )


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


@pytest_asyncio.fixture
async def setup_test_data(
    bas_client: BASClient,
    mock_client: MockClient,
    config: TestConfig,
    test_account_id: str,
    instrument_catalog: InstrumentCatalog,
    place_and_sync_order,
):
    """
    Setup test data (orders, positions, portfolio) for integration tests.

    Creates sample orders and executes them to populate Journal and Portfolio
    services with test data. This fixture should be used by integration tests
    that require existing orders/trades/positions.

    Scope: function (creates fresh data per test)
    """
    broker_id = config.broker_id
    
    # Get a test instrument
    instruments = instrument_catalog.get_any_equity(1)
    if not instruments:
        raise RuntimeError("No instruments available in catalog")
    instrument = instruments[0]
    
    instrument_id = instrument["id"]
    price = Decimal(str(instrument.get("ltp", "100.00")))
    
    try:
        # Ensure trading account exists
        try:
            await bas_client.get_funds(broker_id, test_account_id)
        except Exception:
            # Account doesn't exist, create it
            await bas_client.create_trading_account(
                broker_id=broker_id,
                account_id=test_account_id,
                account_type="PAPER",
            )
            log.info(f"✅ Created trading account: {broker_id}/{test_account_id}")
        
        # Inject price quote for market order execution
        await mock_client.inject_price_update(
            broker_id=broker_id,
            instrument_id=instrument_id,
            ltp=price,
        )
        
        # Place a BUY order
        buy_order = {
            "instrument_id": instrument_id,
            "position_type": "INTRADAY",
            "side": "BUY",
            "order_type": "MARKET",
            "qty": 10,
            "ltp": price,
        }
        
        buy_responses = await place_and_sync_order(broker_id, test_account_id, buy_order)
        buy_order_id = buy_responses[0]["broker_order_id"]
        log.info(f"✅ Placed BUY order: {buy_order_id}")
        
        # Inject fill to execute the order
        await mock_client.inject_fill(
            broker_id=broker_id,
            account_id=test_account_id,
            order_id=buy_order_id,
            sequence=1,
            fill_qty=10,
            fill_price=price,
        )
        log.info(f"✅ Injected fill for BUY order: {buy_order_id}")
        
        # Wait for events to propagate to Journal and Portfolio services
        await asyncio.sleep(3)
        
        yield {
            "instrument_id": instrument_id,
            "buy_order_id": buy_order_id,
            "price": price,
        }
        
    except Exception as e:
        log.error(f"❌ Failed to setup test data: {e}")
        raise


# ────────────────────────────────────────────────────────────────────────────────
# HTML REPORT STYLING & ENHANCEMENTS
# ────────────────────────────────────────────────────────────────────────────────


def pytest_html_report_title(report):
    """Set HTML report title."""
    report.title = "SmartTrade E2E Test Report"
