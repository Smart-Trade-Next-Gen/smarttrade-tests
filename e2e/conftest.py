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
    BASWebSocketClient,
    MDSWebSocketClient,
    MockClient,
    MDSRestClient,
    PortfolioClient,
    JournalClient,
)
from e2e.harness import EventCollector, AssertionEngine, ScenarioEngine
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


def pytest_sessionstart(session):
    """Wait for all services to be fully ready before running tests."""
    config = TestConfig.from_env()

    # Wait for Portfolio Service and other services to be ready
    async def wait_services():
        log.info("Waiting for services to be fully initialized...")

        # Create a simple client to check readiness
        async with httpx.AsyncClient() as client:
            # Wait for Portfolio Service
            start = time.time()
            while time.time() - start < 60:
                try:
                    response = await client.get(f"{config.portfolio_url}/ready")
                    if response.status_code == 200:
                        log.info("✅ Portfolio Service is ready")
                        # Verify event listeners are fully subscribed and ready
                        log.info("Waiting for event listeners to initialize (10s)...")
                        await asyncio.sleep(10)

                        # Call the readiness gate to ensure Redis consumer heartbeats are registered
                        await wait_for_portfolio_service_listeners(config.portfolio_url, timeout=30)
                        return
                except Exception as e:
                    log.debug(f"Portfolio Service not ready: {e}")
                    await asyncio.sleep(1)

            raise TimeoutError("Portfolio Service did not become ready in time")

    # Run the async function
    try:
        asyncio.run(wait_services())
    except Exception as e:
        log.error(f"Failed to wait for services: {e}")
        log.warning("Proceeding with tests despite service readiness issues")


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


@pytest.fixture(scope="session")
def mds_rest_client(config: TestConfig) -> MDSRestClient:
    """
    Provide MDSRestClient for fetching instruments from MDS.

    Scope: session (created once per test run)
    Note: Not async-scoped to avoid pytest-asyncio scope mismatch issues
    """
    return MDSRestClient(base_url=config.mds_url)


@pytest.fixture(scope="session")
def instrument_catalog(config: TestConfig) -> InstrumentCatalog:
    """
    Provide session-scoped instrument catalog seeded into BAS and Redis.

    Architecture (current):
    - MDS owns instrument metadata and publishes instrument.created events
      to the Redis stream market.instrument.v1.
    - BAS subscribes to market.instrument.v1 and persists instruments via
      its InstrumentMaster cache.
    - PBS does NOT have an instruments table — it operates on instrument_id
      strings only and never syncs instrument metadata.

    For E2E tests we simulate MDS by:
    - Seeding instruments directly into the BAS database (covers the case
      where the BAS InstrumentMaster cache is loaded from DB on startup).
    - Publishing instrument.created events to market.instrument.v1 (covers
      the live event-driven path).

    PBS receives no instrument seeding by design.

    Scope: session (loaded once per test run)
    Uses asyncio.run() to execute the async load operation.
    """
    import subprocess
    import json
    import redis as redis_sync

    # Get test instruments data
    test_instruments = get_test_instruments()
    log.info(f"Seeding {len(test_instruments)} instruments to consumer service databases and Redis stream")

    # Seed to BAS database
    for instr in test_instruments:
        isin_val = f"'{instr.get('isin')}'" if instr.get('isin') else 'NULL'
        exchange = instr.get("exchange", "NSE")
        symbol = instr.get("symbol", "")
        fyers_trading_symbol = f"{exchange}:{symbol}"

        broker_instruments_json = json.dumps([{
            "broker_id": "fyers",
            "trading_symbol": fyers_trading_symbol,
            "broker_token": symbol,
        }])

        sql = f"""
            INSERT INTO instruments
            (id, symbol, name, exchange, segment, instrument_type, isin, lot_size, tick_size, status, version, instrument_checksum, broker_instruments, created_at, updated_at)
            VALUES
            ('{instr.get("id")}',
             '{instr.get("symbol")}',
             '{instr.get("name", instr.get("symbol", ""))}',
             '{instr.get("exchange", "NSE")}',
             '{instr.get("segment", "CASH")}',
             '{instr.get("type", "EQUITY")}',
             {isin_val},
             {instr.get('lot_size', 1)},
             {instr.get('tick_size', 0.01)},
             'ACTIVE',
             1,
             '',
             '{broker_instruments_json.replace(chr(39), chr(39)+chr(39))}',
             NOW(),
             NOW())
            ON CONFLICT (id) DO UPDATE SET
                symbol = EXCLUDED.symbol,
                broker_instruments = EXCLUDED.broker_instruments,
                updated_at = NOW();
        """

        try:
            proc = subprocess.run(
                ["docker-compose", "-f", "../docker-compose.e2e.yml", "exec", "-T", "postgres",
                 "psql", "-U", "postgres", "-d", "smarttrade_broker_adapter_service", "-c", sql],
                cwd="/home/amit/Work/Smart-Trade/smarttrade-tests/e2e",
                capture_output=True,
                timeout=5,
            )
            if proc.returncode != 0:
                log.warning(f"Could not insert {instr.get('id')} to BAS: {proc.stderr.decode()}")
        except Exception as e:
            log.warning(f"Could not insert {instr.get('id')} to BAS: {e}")

    log.info("✅ Instruments seeded to BAS database")

    # PBS no longer owns instrument metadata — it works with instrument_id only,
    # so there is no PBS-side seeding step.

    # Publish instrument events to Redis stream (market.instrument.v1)
    # This simulates MDS publishing instrument events that consumers subscribe to
    try:
        redis_client = redis_sync.from_url("redis://localhost:6379/0")

        # Delete any existing consumer group for BAS to reset position
        try:
            redis_client.execute_command("XGROUP", "DESTROY", "market.instrument.v1", "bas-instrument-master")
            log.info("Reset BAS instrument master consumer group")
        except:
            # Group doesn't exist yet, which is fine
            pass

        for instr in test_instruments:
            instrument_event = {
                "event_id": f"instr_{instr.get('id')}",
                "event_type": "instrument.created",
                "instrument_id": instr.get("id"),
                "symbol": instr.get("symbol"),
                "name": instr.get("name"),
                "exchange": instr.get("exchange", "NSE"),
                "segment": instr.get("segment", "CASH"),
                "type": instr.get("type", "EQUITY"),
                "isin": instr.get("isin"),
                "lot_size": instr.get("lot_size", 1),
                "tick_size": instr.get("tick_size", 0.01),
                "timestamp": time.time(),
            }
            redis_client.xadd("market.instrument.v1", {"data": json.dumps(instrument_event)})

        log.info(f"✅ Published {len(test_instruments)} instrument events to Redis stream (market.instrument.v1)")

        # Wait for consumers to process events (increased from 5s to 15s)
        log.info("Waiting for instrument consumers to process events (15s)...")
        for i in range(15):
            time.sleep(1)
            # Log progress
            if (i + 1) % 5 == 0:
                log.info(f"  ... {i + 1}/15 seconds elapsed")

        redis_client.close()
    except Exception as e:
        log.warning(f"⚠️ Failed to publish instrument events to Redis: {e}")

    # Create catalog from seeded test data
    catalog = InstrumentCatalog(test_instruments)
    asyncio.run(catalog.load())
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
    bas_client, mock_client, portfolio_client, test_account_id
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

        # Clean up execution state, positions, and PBS' in-memory price
        # cache so the next test starts from a clean slate. Without
        # cleanup_price_cache, OrderService.create_order auto-fills any
        # newly-placed order at whatever LTP a previous test left in the
        # cache, before the current test's own quote can be injected.
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

        try:
            await mock_client.cleanup_price_cache()
            log.debug("✅ PBS price_cache cleared")
        except Exception as e:
            log.warning(f"⚠️ price_cache cleanup failed: {e}")

        try:
            await mock_client.cleanup_account(broker_id, test_account_id)
            log.debug(f"✅ PBS account reset: {broker_id}/{test_account_id}")
        except Exception as e:
            log.warning(f"⚠️ PBS account reset failed: {e}")

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


@pytest.fixture(scope="session")
def test_account_id() -> str:
    """
    Single shared account for all tests in the session.

    Test isolation is preserved via setup_trading_account fixture which deletes
    and recreates the account before each test. All clients and WebSocket
    connections are session-scoped and reuse this single account.

    Scope: session
    """
    return "TEST_E2E_SHARED"


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


# ────────────────────────────────────────────────────────────────────────────────
# FUNCTION-SCOPED FIXTURES: SERVICE CLIENTS
# ────────────────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(scope="session")
async def bas_client(config: TestConfig, auth_token: str) -> AsyncGenerator[BASClient, None]:
    """
    Provide BASClient instance. Reused across all tests in the session.

    Scope: session
    """
    async with BASClient(
        base_url=config.bas_url,
        token=auth_token,
        timeout=config.timeout_medium,
    ) as client:
        yield client


@pytest_asyncio.fixture(scope="session")
async def mock_client(
    config: TestConfig, auth_token: str
) -> AsyncGenerator[MockClient, None]:
    """
    Provide MockClient instance for fill injection.

    inject_fill drives PBS fills by publishing to the Redis stream
    `market.quote.v1` (production path) — there is no longer an HTTP
    /execute shortcut, so we pass the redis URL here.

    Scope: session
    """
    async with MockClient(
        base_url=config.mock_url,
        token=auth_token,
        timeout=config.timeout_fast,
        redis_url=config.redis_url,
    ) as client:
        yield client


@pytest_asyncio.fixture(scope="session")
async def portfolio_client(config: TestConfig, auth_token: str) -> AsyncGenerator[PortfolioClient, None]:
    """
    Provide PortfolioClient for testing Portfolio Service async aggregation.

    Scope: session
    """
    async with PortfolioClient(
        base_url=config.portfolio_url,
        token=auth_token,
        timeout=config.timeout_medium,
    ) as client:
        yield client


@pytest_asyncio.fixture(scope="session")
async def journal_client(config: TestConfig, auth_token: str) -> AsyncGenerator[JournalClient, None]:
    """
    Provide JournalClient for testing Journal Service audit trail.

    Scope: session
    """
    async with JournalClient(
        base_url=config.journal_url,
        token=auth_token,
        timeout=config.timeout_medium,
    ) as client:
        yield client


@pytest_asyncio.fixture
async def market_data_stream(mock_client: MockClient, config: TestConfig) -> MockMarketDataStream:
    """
    Provide MockMarketDataStream for real execution mode tests.

    Publishes price updates on the production Redis stream `market.quote.v1`
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
    for event_type in ["order.filled.v1", "trade.executed.v1", "position.updated.v1"]:
        await observer._ensure_consumer_group(f"events:{event_type}")
    yield observer
    # Cleanup: delete observer consumer groups
    for event_type in ["order.filled.v1", "trade.executed.v1", "position.updated.v1"]:
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


@pytest_asyncio.fixture(scope="session")
async def mds_client(
    config: TestConfig, auth_token: str, test_account_id: str, test_user_id: str
) -> AsyncGenerator[MDSWebSocketClient, None]:
    """
    Provide MDSWebSocketClient bound to the MDS UI WebSocket channel.

    Scope: session — one connection for the entire test run, never closed
    between tests.

    The MDS UI channel is exclusively a UI-facing market data feed (quotes,
    depth, candles, instrument subscription requests). BAS and PBS no longer
    consume MDS via WebSocket — they read market data from the Redis stream
    market.quote.v1. Tests must therefore not use mds_client as a stand-in
    for the BAS/PBS data path.

    Account/execution events stay on the BAS WebSocket (bas_ws_client).
    """
    ws_url_with_path = f"{config.mds_ws_url}/ws/{config.broker_id}/ui"

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

    # Session teardown: disconnect once at the very end of the session
    try:
        await client.disconnect()
    except Exception as e:
        log.warning(f"Error disconnecting MDS client: {e}")


@pytest_asyncio.fixture(scope="session")
async def bas_ws_client(
    config: TestConfig, auth_token: str, test_account_id: str
) -> AsyncGenerator[BASWebSocketClient, None]:
    """
    Provide BASWebSocketClient instance for trading account events.

    Scope: session — one connection for the entire test run, never closed between tests

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
                    "order.cancelled.v1": "order_cancelled",
                    "order.rejected.v1": "order_rejected",
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

    # Session teardown: cancel stream and disconnect once at the very end of the session
    stream_task.cancel()
    try:
        await asyncio.wait_for(stream_task, timeout=5.0)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass
    finally:
        client._event_collector = None

    try:
        await client.disconnect()
    except Exception as e:
        log.warning(f"Error disconnecting BAS client: {e}")


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
def event_collector(bas_ws_client) -> EventCollector:
    """
    Provide EventCollector instance for async event collection.

    Scope: function (fresh collector per test)

    Wires itself to bas_ws_client so BAS events are streamed into this collector.
    Memory is cleared after test completes.
    """
    # Reduced maxsize from 1000 to 100 to limit memory per test
    collector = EventCollector(maxsize=100)
    # Wire the collector to the bas_ws_client so it can stream events
    bas_ws_client._event_collector = collector
    yield collector
    # Aggressive cleanup: drain all queues, clear all events, and reset state
    try:
        collector.clear()  # Drains queues and clears events
    except Exception as e:
        log.warning(f"Error clearing event collector: {e}")
    # Remove reference
    collector = None


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
async def place_and_sync_order(bas_client: BASClient, mock_client: MockClient, config: TestConfig, instrument_catalog: InstrumentCatalog):
    """
    Provide a helper function to place an order in BAS and sync it to paper broker service.

    This ensures orders exist in paper broker service with correct instrument_id (from MDS)
    before fill injection is attempted.

    Supports both dict (simplified) and BasOrderPlaceRequest formats for order_request.

    Usage in tests:
        # Dict format (automatically converted to BasOrderPlaceRequest)
        [order_resp] = await place_and_sync_order(
            broker_id, account_id,
            order_request={"instrument_id": "...", "side": "BUY", "qty": 100, ...}
        )

        # Or Pydantic model format (passed directly)
        [order_resp] = await place_and_sync_order(broker_id, account_id, order_request=BasOrderPlaceRequest(...))

    Args (passed to helper):
        broker_id: Broker identifier
        account_id: Account identifier
        order_request: dict or BasOrderPlaceRequest

    Returns:
        List of order responses from BAS (same as place_order)

    Scope: function
    """
    async def helper(broker_id: str, account_id: str, order_request):
        # Convert dict to BasOrderPlaceRequest if needed
        if isinstance(order_request, dict):
            order_request = _dict_to_order_request(order_request, instrument_catalog)

        # Step 1: Place order in BAS (returns order with instrument_id from MDS)
        order_responses = await bas_client.place_order(broker_id, account_id, order_request)

        # Step 2: Convert responses to dicts for consistency (tests expect dicts)
        order_response_dicts = [
            resp.model_dump() if hasattr(resp, 'model_dump') else resp
            for resp in order_responses
        ]

        # Step 3: Sync each order to paper broker service using instrument_id (not broker symbol)
        for order_resp_dict in order_response_dicts:
            try:
                await mock_client.sync_order(broker_id, account_id, order_resp_dict)
                log.debug(f"Order synced: {order_resp_dict.get('broker_order_id')}")
            except Exception as e:
                log.warning(f"Failed to sync order to paper broker service (non-critical): {e}")
                # Sync to paper broker is optional - tests can proceed without it

        return order_response_dicts

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


# ────────────────────────────────────────────────────────────────────────────────
# HTML REPORT STYLING & ENHANCEMENTS
# ────────────────────────────────────────────────────────────────────────────────


def pytest_html_report_title(report):
    """Set HTML report title."""
    report.title = "SmartTrade E2E Test Report"
