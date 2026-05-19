"""
paper broker service REST API client.

Provides deterministic fill injection for testing without relying on price-triggered execution.
Used to create reproducible, controlled test scenarios.
"""

import logging
import sys
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Optional
from uuid import UUID

import httpx

if TYPE_CHECKING:
    from paper_broker_service.schemas import ExecutionCommand, ExecutionResult
else:
    ExecutionCommand = None
    ExecutionResult = None

log = logging.getLogger(__name__)


class MockClient:
    """
    Async REST client for paper broker service (execution injection).

    Enables deterministic fill injection for E2E testing.
    Validates sequence monotonicity to prevent duplicate or out-of-order executions.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: float = 5.0,
        redis_url: str = "redis://localhost:6379/0",
    ):
        """
        Initialize MockClient.

        Args:
            base_url: Base URL for paper broker service (e.g., http://localhost:8002)
            token: Bearer token for authentication
            timeout: Request timeout in seconds (default: 5.0)
            redis_url: Redis URL for publishing quotes that drive PBS fills.

        Raises:
            ValueError: If token is empty
        """
        if not token:
            raise ValueError("Bearer token cannot be empty")

        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.client: Optional[httpx.AsyncClient] = None
        self._sequence_tracker: dict[str, int] = {}  # Track sequence per order_id
        # Redis quote-publish state for inject_fill (production fill path).
        self._redis_url = redis_url
        self._redis = None
        self._quote_sequence: dict[str, int] = {}

    async def __aenter__(self) -> "MockClient":
        """Async context manager entry."""
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.client:
            await self.client.aclose()
            self.client = None
        if self._redis is not None:
            try:
                await self._redis.close()
            except Exception:
                pass
            self._redis = None

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self.client is None:
            raise RuntimeError(
                "MockClient not connected. Use 'async with MockClient(...)' or call connect() first."
            )
        return self.client

    async def connect(self) -> None:
        """Establish HTTP client connection."""
        if self.client is None:
            self.client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                limits=httpx.Limits(
                    max_connections=100, max_keepalive_connections=20
                ),
            )

    async def disconnect(self) -> None:
        """Close HTTP client connection."""
        if self.client:
            await self.client.aclose()
            self.client = None

    def _get_headers(self) -> dict:
        """Build request headers with Bearer token."""
        return {"Authorization": f"Bearer {self.token}"}

    def _ensure_imports(self) -> tuple:
        """
        Dynamically import ExecutionCommand and ExecutionResult.

        This is done at runtime to allow tests to discover without requiring
        paper-broker-service to be in the Python path at import time.

        Returns:
            Tuple of (ExecutionCommand, ExecutionResult) classes
        """
        try:
            from paper_broker_service.schemas import ExecutionCommand, ExecutionResult
            return ExecutionCommand, ExecutionResult
        except ImportError:
            # Try adding paper-broker-service to path
            paper_broker_service_path = Path(__file__).parent.parent.parent.parent / "paper-broker-service" / "src"
            if paper_broker_service_path.exists() and str(paper_broker_service_path) not in sys.path:
                sys.path.insert(0, str(paper_broker_service_path))

            from paper_broker_service.schemas import ExecutionCommand, ExecutionResult
            return ExecutionCommand, ExecutionResult

    def _get_next_sequence(self, order_id: str) -> int:
        """
        Get the next sequence number for an order.

        Tracks sequence numbers per order_id to enforce monotonicity.

        Args:
            order_id: Order ID

        Returns:
            Next sequence number (1-indexed)
        """
        if order_id not in self._sequence_tracker:
            self._sequence_tracker[order_id] = 0
        self._sequence_tracker[order_id] += 1
        return self._sequence_tracker[order_id]

    async def inject_fill(
        self,
        broker_id: str,
        account_id: str,
        order_id: str,
        sequence: int,
        fill_qty: int,
        fill_price: Decimal,
    ):
        """
        Drive an order fill by publishing a quote on the production Redis stream.

        PBS no longer exposes an HTTP /execute endpoint. Fills are produced by
        the price-driven path: a quote on `market.quote` is consumed by
        PBSMarketDataConsumer, which enqueues an ExecutionWorker fill at the
        quote's LTP for the **full remaining qty** of every open order on that
        instrument. The worker emits ORDER_UPDATE / TRADE_UPDATE /
        POSITION_UPDATE on PBS' internal WS post-commit.

        The legacy ``sequence`` and ``fill_qty`` parameters are kept for
        signature compatibility but are no longer honored — partial fills are
        not supported in PBS today (skip those tests). ``fill_qty`` is treated
        as a sanity check: if it is less than the order's remaining qty a
        ValueError is raised so partial-fill tests fail loudly instead of
        producing a misleading full fill.

        Args:
            broker_id: Broker ID (used to look up the order)
            account_id: Account ID (used to look up the order)
            order_id: PBS order UUID
            sequence: Ignored. Kept for backward compatibility.
            fill_qty: Sanity-checked against the order's remaining qty.
            fill_price: Quote LTP that the worker will use as the fill price.
        """
        # Discover the order's instrument_id and remaining qty so we can
        # publish a quote that targets exactly this order.
        client = self._get_client()
        headers = self._get_headers()
        url = f"/api/v1/order/{broker_id}/{account_id}/{order_id}"
        order_response = await client.get(url, headers=headers)
        order_response.raise_for_status()
        order = order_response.json()

        instrument_id = order.get("instrument_id")
        remaining_qty = int(order.get("remaining_qty", 0))
        if not instrument_id:
            raise ValueError(
                f"PBS returned no instrument_id for order_id={order_id}; "
                f"cannot publish a quote to drive the fill."
            )
        if fill_qty != remaining_qty:
            raise ValueError(
                f"Partial fills are not supported in PBS. "
                f"order_id={order_id}: requested fill_qty={fill_qty}, "
                f"remaining_qty={remaining_qty}. Either pass the full "
                f"remaining qty or skip the test."
            )

        # Track sequence for back-compat callers that read it.
        self._sequence_tracker[order_id] = sequence

        # Publish quote on the production Redis stream. PBSMarketDataConsumer
        # has a per-instrument idempotency check (`_last_seq[instrument_id]`)
        # that survives across pytest invocations because PBS is long-lived.
        # A millisecond timestamp keeps the sequence_number monotonic across
        # processes so a new test session is never silently dropped as a
        # duplicate.
        import redis.asyncio as redis
        from datetime import datetime, timezone

        if self._redis is None:
            self._redis = await redis.from_url(self._redis_url, decode_responses=True)

        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        # Track within the session in case caller wants to read it back.
        self._quote_sequence[instrument_id] = now_ms

        await self._redis.xadd(
            "market.quote",
            {
                "instrument_id": instrument_id,
                "ltp": str(fill_price),
                "sequence_number": str(now_ms),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        log.debug(
            f"Published quote for fill | broker_id={broker_id} | "
            f"account_id={account_id} | order_id={order_id} | "
            f"instrument_id={instrument_id} | qty={fill_qty} | "
            f"price={fill_price}"
        )

    async def inject_fills_sequence(
        self,
        broker_id: str,
        account_id: str,
        order_id: str,
        fills: list[tuple[Decimal, int]],
    ) -> None:
        """
        DEPRECATED: partial fills are not supported in PBS today.

        Raises ValueError unconditionally so any caller that still depends on
        partial-fill semantics fails loudly. Tests exercising partial fills
        should be skipped with a clear reason.
        """
        raise ValueError(
            "inject_fills_sequence is deprecated: PBS does not support "
            "partial fills. Skip these tests until partial-fill simulation "
            "is added back."
        )

    async def inject_price_update(
        self,
        broker_id: str,
        instrument_id: str,
        ltp: Decimal,
        bid: Optional[Decimal] = None,
        ask: Optional[Decimal] = None,
    ) -> dict:
        """
        Test-only HTTP shortcut to synchronously trigger PBS PriceExecutionEngine.

        Production data flow is via the Redis stream `market.quote` consumed
        by PBSMarketDataConsumer. This endpoint bypasses that path and is used
        by E2E tests to keep LIMIT/STOP trigger assertions deterministic when
        consumer-group lag would otherwise race the test.

        Sends a price update to the paper broker service, which triggers the
        PriceExecutionEngine to evaluate all open orders and execute any that
        match the trigger conditions.

        Args:
            broker_id: Broker ID (e.g., "mock")
            instrument_id: Instrument ID to update price for
            ltp: Last traded price
            bid: Bid price (optional)
            ask: Ask price (optional)

        Returns:
            Response dict with status and updated orders

        Raises:
            httpx.HTTPError: On HTTP error
        """
        client = self._get_client()
        headers = self._get_headers()

        payload = {
            "instrument_id": instrument_id,
            "ltp": str(ltp),
        }
        if bid is not None:
            payload["bid"] = str(bid)
        if ask is not None:
            payload["ask"] = str(ask)

        url = f"/api/v1/price/{broker_id}"
        log.debug(
            f"Injecting price update | broker_id={broker_id} | "
            f"instrument_id={instrument_id} | ltp={ltp}"
        )

        try:
            response = await client.post(
                url,
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            # Price endpoint may not exist yet - log warning but don't fail
            log.warning(
                f"Price injection endpoint not available: {e}. "
                f"Use inject_fill() for deterministic testing instead."
            )
            return {"status": "not_implemented", "message": "Price injection not available"}

    async def cancel_order(
        self,
        broker_id: str,
        account_id: str,
        order_id: str,
    ) -> dict:
        """
        Cancel an order via paper broker service.

        Args:
            broker_id: Broker identifier (e.g., "fyers")
            account_id: Account identifier
            order_id: Order ID to cancel

        Returns:
            Response from paper broker service

        Raises:
            httpx.HTTPError: If request fails
        """
        url = f"{self.base_url}/api/v1/order/{broker_id}/{account_id}/{order_id}"
        headers = self._get_headers()

        try:
            response = await self.client.delete(
                url,
                headers=headers,
            )
            response.raise_for_status()
            log.debug(f"Cancel order request sent | broker_id={broker_id} | account_id={account_id} | order_id={order_id}")
            return response.json()
        except httpx.HTTPError as e:
            log.error(f"Cancel order failed: {e}")
            raise

    def reset_sequence(self, order_id: Optional[str] = None) -> None:
        """
        Reset sequence tracking for an order or all orders.

        Args:
            order_id: Order ID to reset (if None, resets all)
        """
        if order_id:
            self._sequence_tracker.pop(order_id, None)
            log.debug(f"Reset sequence for order_id={order_id}")
        else:
            self._sequence_tracker.clear()
            log.debug("Reset all sequence trackers")

    async def cleanup_account(self, broker_id: str, account_id: str) -> dict:
        """
        Reset the PBS AccountBalance for (user, broker, account) to defaults.

        Each filled BUY debits the AccountBalance row, so without a reset
        the balance depletes across the test session until reserved exceeds
        balance and the financial invariant violation aborts further fills.
        """
        client = self._get_client()
        headers = self._get_headers()
        try:
            response = await client.delete(
                f"/api/v1/cleanup/account/{broker_id}/{account_id}", headers=headers
            )
            response.raise_for_status()
            log.debug(f"PBS account reset: {broker_id}/{account_id}")
            return response.json()
        except httpx.HTTPError as e:
            log.warning(f"PBS account reset failed (non-critical): {e}")
            return {"status": "error", "message": str(e)}

    async def cleanup_price_cache(self) -> dict:
        """
        Drop PBS' in-memory LTP cache.

        PBS' OrderService.create_order auto-fills any new order whose
        instrument has a cached price. Tests share instruments across the
        session, so the cache must be dropped between tests; otherwise an
        order placed for SBIN gets filled at whatever LTP a previous test
        last published, before the current test's own quote arrives.

        Returns:
            Response with status="cleared"
        """
        client = self._get_client()
        headers = self._get_headers()
        try:
            response = await client.delete("/api/v1/cleanup/price_cache", headers=headers)
            response.raise_for_status()
            log.debug("PBS price_cache cleared")
            return response.json()
        except httpx.HTTPError as e:
            log.warning(f"PBS price_cache cleanup failed (non-critical): {e}")
            return {"status": "error", "message": str(e)}

    async def cleanup_execution_state(
        self,
        broker_id: str,
        account_id: str,
    ) -> dict:
        """
        Clear execution state for all orders in an account.

        Resets sequence tracking in paper broker service database.
        Used during test setup to ensure fresh fills start with sequence 1.

        Args:
            broker_id: Broker identifier
            account_id: Account identifier

        Returns:
            Response with count of cleared execution state records

        Raises:
            httpx.HTTPError: If request fails
        """
        client = self._get_client()
        headers = self._get_headers()
        url = f"/api/v1/cleanup/execution_state/{broker_id}/{account_id}"

        try:
            response = await client.delete(url, headers=headers)
            response.raise_for_status()
            log.debug(f"Execution state cleared | broker_id={broker_id} | account_id={account_id}")
            return response.json()
        except httpx.HTTPError as e:
            log.error(f"Execution state cleanup failed: {e}")
            raise

    async def cleanup_positions(
        self,
        broker_id: str,
        account_id: str,
    ) -> dict:
        """
        Clear all positions for an account.

        Deletes all Position records for the account.
        Used during test setup to ensure fresh position state for each test.

        Args:
            broker_id: Broker identifier
            account_id: Account identifier

        Returns:
            Response with count of cleared position records

        Raises:
            httpx.HTTPError: If request fails
        """
        client = self._get_client()
        headers = self._get_headers()
        url = f"/api/v1/cleanup/positions/{broker_id}/{account_id}"

        try:
            response = await client.delete(url, headers=headers)
            response.raise_for_status()
            log.debug(f"Positions cleared | broker_id={broker_id} | account_id={account_id}")
            return response.json()
        except httpx.HTTPError as e:
            log.error(f"Positions cleanup failed: {e}")
            raise
