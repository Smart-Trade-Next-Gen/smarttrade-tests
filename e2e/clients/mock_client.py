"""
Mock Service REST API client.

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
    from mock_service.schemas import ExecutionCommand, ExecutionResult
else:
    ExecutionCommand = None
    ExecutionResult = None

log = logging.getLogger(__name__)


class MockClient:
    """
    Async REST client for Mock Service (execution injection).

    Enables deterministic fill injection for E2E testing.
    Validates sequence monotonicity to prevent duplicate or out-of-order executions.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: float = 5.0,
    ):
        """
        Initialize MockClient.

        Args:
            base_url: Base URL for Mock service (e.g., http://localhost:8002)
            token: Bearer token for authentication
            timeout: Request timeout in seconds (default: 5.0)

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
        mock-service to be in the Python path at import time.

        Returns:
            Tuple of (ExecutionCommand, ExecutionResult) classes
        """
        try:
            from mock_service.schemas import ExecutionCommand, ExecutionResult
            return ExecutionCommand, ExecutionResult
        except ImportError:
            # Try adding mock-service to path
            mock_service_path = Path(__file__).parent.parent.parent.parent / "mock-service" / "src"
            if mock_service_path.exists() and str(mock_service_path) not in sys.path:
                sys.path.insert(0, str(mock_service_path))

            from mock_service.schemas import ExecutionCommand, ExecutionResult
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
        Inject a single fill execution.

        Args:
            broker_id: Broker ID (e.g., "fyers")
            account_id: Account ID
            order_id: Order ID to fill
            sequence: Execution sequence number (must be monotonic: 1, 2, 3, ...)
            fill_qty: Quantity to fill
            fill_price: Execution price

        Returns:
            ExecutionResult with execution details

        Raises:
            httpx.HTTPError: On HTTP error
            ValueError: On sequence validation error
        """
        ExecutionCommand, ExecutionResult = self._ensure_imports()

        # Validate sequence monotonicity
        last_sequence = self._sequence_tracker.get(order_id, 0)
        if sequence <= last_sequence:
            raise ValueError(
                f"Sequence must be monotonically increasing. "
                f"Last: {last_sequence}, Got: {sequence}"
            )
        self._sequence_tracker[order_id] = sequence

        client = self._get_client()
        headers = self._get_headers()

        # Convert order_id to UUID if it's a string
        try:
            order_uuid = UUID(order_id) if isinstance(order_id, str) else order_id
        except (ValueError, AttributeError):
            raise ValueError(f"Invalid order_id format: {order_id}")

        execution_cmd = ExecutionCommand(
            order_id=order_uuid,
            sequence=sequence,
            fill_qty=fill_qty,
            fill_price=fill_price,
        )

        url = f"/api/v1/execute/{broker_id}/{account_id}"
        log.debug(
            f"Injecting fill | broker_id={broker_id} | account_id={account_id} | "
            f"order_id={order_id} | sequence={sequence} | qty={fill_qty} | price={fill_price}"
        )

        response = await client.post(
            url,
            json=execution_cmd.model_dump(mode="json"),
            headers=headers,
        )
        response.raise_for_status()

        return ExecutionResult.model_validate(response.json())

    async def inject_fills_sequence(
        self,
        broker_id: str,
        account_id: str,
        order_id: str,
        fills: list[tuple[Decimal, int]],
    ) -> None:
        """
        Inject a sequence of fills with auto-incrementing sequence numbers.

        Args:
            broker_id: Broker ID
            account_id: Account ID
            order_id: Order ID to fill
            fills: List of (price, qty) tuples to fill in order

        Raises:
            httpx.HTTPError: On HTTP error
        """
        for price, qty in fills:
            sequence = self._get_next_sequence(order_id)
            await self.inject_fill(
                broker_id=broker_id,
                account_id=account_id,
                order_id=order_id,
                sequence=sequence,
                fill_qty=qty,
                fill_price=price,
            )

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
