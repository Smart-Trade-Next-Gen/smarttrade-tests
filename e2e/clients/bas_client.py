"""
BAS (Broker Adapter Service) REST API client.

Provides async operations for order management, portfolio queries, and position management.
Uses httpx for HTTP operations and automatically injects Bearer token and idempotency keys.
"""

import logging
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

import httpx

# Import response models from BAS
from broker_adapter_service.schemas.order_dtos import (
    BasCancelOrderResponse,
    BasOrderModifyRequest,
    BasOrderModifyResponse,
    BasOrderPlaceRequest,
    BasOrderPlaceResponse,
)

# Import domain DTOs (no longer used - removed deprecated endpoints)
# from smarttrade_common.schemas.services.trading.order_dtos import (
#     Order,
#     Position,
#     Trade,
# )

# Import funds DTO
from broker_adapter_service.schemas.funds_dtos import FundsResponse

log = logging.getLogger(__name__)


class BASClient:
    """
    Async REST client for Broker Adapter Service.

    Handles order placement, modification, cancellation, and portfolio queries.
    Automatically injects Bearer token and manages idempotency.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: float = 10.0,
    ):
        """
        Initialize BASClient.

        Args:
            base_url: Base URL for BAS service (e.g., http://localhost:8005)
            token: Bearer token for authentication
            timeout: Request timeout in seconds (default: 10.0)

        Raises:
            ValueError: If token is empty
        """
        if not token:
            raise ValueError("Bearer token cannot be empty")

        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "BASClient":
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
                "BASClient not connected. Use 'async with BASClient(...)' or call connect() first."
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

    def _get_headers(self, idempotency_key: Optional[str] = None) -> dict:
        """Build request headers with Bearer token and optional idempotency key."""
        headers = {"Authorization": f"Bearer {self.token}"}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    def _generate_idempotency_key(self) -> str:
        """Generate a unique idempotency key."""
        return str(uuid.uuid4())

    async def place_order(
        self,
        broker_id: str,
        account_id: str,
        request: BasOrderPlaceRequest,
    ) -> list[BasOrderPlaceResponse]:
        """
        Place a new order.

        Args:
            broker_id: Broker ID (e.g., "fyers")
            account_id: Account ID
            request: Order placement request

        Returns:
            List of order placement responses

        Raises:
            httpx.HTTPError: On HTTP error
        """
        client = self._get_client()
        idempotency_key = self._generate_idempotency_key()
        headers = self._get_headers(idempotency_key)

        url = f"/api/v1/orders/{broker_id}/{account_id}"
        log.debug(
            f"Placing order | broker_id={broker_id} | account_id={account_id} | "
            f"idempotency_key={idempotency_key}"
        )

        response = await client.post(
            url,
            json=request.model_dump(mode='json', exclude_none=True),
            headers=headers,
        )

        if response.status_code != 200:
            log.error(f"❌ Order placement failed | Status: {response.status_code} | Body: {response.text}")

        response.raise_for_status()

        return [
            BasOrderPlaceResponse.model_validate(item) for item in response.json()
        ]

    async def modify_order(
        self,
        broker_id: str,
        account_id: str,
        broker_order_id: str,
        request: BasOrderModifyRequest,
    ) -> BasOrderModifyResponse:
        """
        Modify an existing order.

        Args:
            broker_id: Broker ID
            account_id: Account ID
            broker_order_id: Broker order ID
            request: Order modification request

        Returns:
            Order modification response

        Raises:
            httpx.HTTPError: On HTTP error
        """
        client = self._get_client()
        headers = self._get_headers()

        url = f"/api/v1/orders/{broker_id}/{account_id}/{broker_order_id}"
        log.debug(
            f"Modifying order | broker_id={broker_id} | account_id={account_id} | "
            f"broker_order_id={broker_order_id}"
        )

        response = await client.put(
            url,
            json=request.model_dump(mode='json', exclude_none=True),
            headers=headers,
        )
        response.raise_for_status()

        return BasOrderModifyResponse.model_validate(response.json())

    async def cancel_order(
        self,
        broker_id: str,
        account_id: str,
        broker_order_id: str,
    ) -> BasCancelOrderResponse:
        """
        Cancel an existing order.

        Args:
            broker_id: Broker ID
            account_id: Account ID
            broker_order_id: Broker order ID

        Returns:
            Order cancellation response

        Raises:
            httpx.HTTPError: On HTTP error
        """
        client = self._get_client()
        headers = self._get_headers()

        url = f"/api/v1/orders/{broker_id}/{account_id}/{broker_order_id}"
        log.debug(
            f"Cancelling order | broker_id={broker_id} | account_id={account_id} | "
            f"broker_order_id={broker_order_id}"
        )

        response = await client.delete(
            url,
            headers=headers,
        )
        response.raise_for_status()

        return BasCancelOrderResponse.model_validate(response.json())


    async def get_funds(
        self,
        broker_id: str,
        account_id: str,
    ) -> FundsResponse:
        """
        Get funds and portfolio information.

        Args:
            broker_id: Broker ID
            account_id: Account ID

        Returns:
            FundsResponse with portfolio details

        Raises:
            httpx.HTTPError: On HTTP error
        """
        client = self._get_client()
        headers = self._get_headers()

        url = f"/api/v1/funds/{broker_id}/{account_id}"
        log.debug(
            f"Getting funds | broker_id={broker_id} | account_id={account_id}"
        )

        response = await client.get(url, headers=headers)

        # For test accounts that don't exist yet, return default funds
        if response.status_code == 404 and "TEST_E2E" in account_id:
            log.info(f"Account {account_id} not found, returning default funds for testing")
            return FundsResponse(
                currency="INR",
                total_equity=Decimal("1000000.00"),
                cash_balance=Decimal("1000000.00"),
                timestamp=datetime.utcnow(),
            )

        response.raise_for_status()

        return FundsResponse.model_validate(response.json())


    async def create_trading_account(
        self,
        broker_id: str,
        account_id: str,
        account_name: str = None,
        account_type: str = "TRADING",
    ) -> dict:
        """
        Create a trading account for testing.

        Args:
            broker_id: Broker ID (e.g., "fyers")
            account_id: Account ID to create
            account_name: Name of the account (defaults to account_id)
            account_type: Account type ("TRADING" for live, "PAPER" for paper trading)

        Note:
            Initial funds are owned by PBS for paper accounts. PBS auto-creates
            an AccountBalance row with DEFAULT_INITIAL_BALANCE (1,000,000) on
            first access, so this call only creates the BAS-side trading-account
            metadata.

        Returns:
            Response dict from the API

        Raises:
            httpx.HTTPError: On HTTP error
        """
        client = self._get_client()
        headers = self._get_headers()

        url = f"/api/v1/trading_account/{broker_id}"
        payload = {
            "account_id": account_id,
            "account_name": account_name or account_id,
            "account_type": account_type,
            "base_currency": "INR",
        }

        log.debug(
            f"Creating trading account | broker_id={broker_id} | account_id={account_id} "
        )

        response = await client.post(url, json=payload, headers=headers)

        # Account creation may return 200, 201, or 409 (if already exists)
        if response.status_code == 409:
            log.debug(f"Trading account already exists: {account_id}")
            return {"account_id": account_id}

        response.raise_for_status()
        return response.json()

    async def delete_trading_account(
        self,
        broker_id: str,
        account_id: str,
    ) -> dict:
        """
        Delete a trading account.

        Args:
            broker_id: Broker ID
            account_id: Account ID to delete

        Returns:
            Response dict from the API

        Raises:
            httpx.HTTPError: On HTTP error
        """
        client = self._get_client()
        headers = self._get_headers()

        url = f"/api/v1/trading_account/{broker_id}/{account_id}"

        log.debug(f"Deleting trading account | broker_id={broker_id} | account_id={account_id}")

        response = await client.delete(url, headers=headers)

        # Account deletion may return 404 if not found (which is fine)
        if response.status_code == 404:
            log.debug(f"Trading account not found: {account_id}")
            return {"account_id": account_id}

        response.raise_for_status()
        return response.json()

    async def start_account_session(
        self,
        broker_id: str,
        account_id: str,
    ) -> dict:
        """
        Start an account session with guaranteed WebSocket connection.

        This endpoint performs synchronous bootstrapping including:
        - Fetching positions from broker
        - Establishing WebSocket connection for execution updates
        - Publishing snapshots to downstream services

        Args:
            broker_id: Broker ID (e.g., "fyers")
            account_id: Account ID

        Returns:
            Session status dict with:
            - status: "ready" or "degraded"
            - bootstrapped: bool
            - ws_connected: bool
            - broker_id: str
            - account_id: str

        Raises:
            httpx.HTTPError: On HTTP error
        """
        client = self._get_client()
        headers = self._get_headers()

        url = f"/api/v1/session/{broker_id}/{account_id}"

        log.debug(
            f"Starting account session | broker_id={broker_id} | account_id={account_id}"
        )

        response = await client.post(url, headers=headers)
        response.raise_for_status()

        return response.json()

    async def get_account_session_health(
        self,
        broker_id: str,
        account_id: str,
    ) -> dict:
        """
        Get health status of an account session.

        Args:
            broker_id: Broker ID
            account_id: Account ID

        Returns:
            Session health dict with:
            - status: "healthy", "degraded", or "not_bootstrapped"
            - bootstrapped: bool
            - bootstrapped_at: timestamp or None
            - ws_connected: bool
            - ws_reconnect_attempts: int
            - uptime_seconds: float

        Raises:
            httpx.HTTPError: On HTTP error
        """
        client = self._get_client()
        headers = self._get_headers()

        url = f"/api/v1/session/{broker_id}/{account_id}/health"

        log.debug(
            f"Getting account session health | broker_id={broker_id} | account_id={account_id}"
        )

        response = await client.get(url, headers=headers)
        response.raise_for_status()

        return response.json()

    async def upsert_broker_connection(
        self,
        broker_id: str,
        auth_type: str = "api_key",
        credentials: dict = None,
    ) -> dict:
        """
        Upsert broker connection with credentials for testing.

        Args:
            broker_id: Broker ID (e.g., "fyers")
            auth_type: Authentication type (default: "api_key")
            credentials: Dict with app_id, app_secret, etc.

        Returns:
            Response dict from the API

        Raises:
            httpx.HTTPError: On HTTP error
        """
        if credentials is None:
            credentials = {
                "app_id": "test_app_id",
                "app_secret": "test_app_secret",
            }

        client = self._get_client()
        headers = self._get_headers()

        url = f"/api/v1/broker_connection/{broker_id}"
        payload = {
            "auth_type": auth_type,
            "credentials": credentials,
        }

        log.debug(
            f"Upserting broker connection | broker_id={broker_id} | auth_type={auth_type}"
        )

        response = await client.put(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()

    async def cleanup_quote_store(self) -> dict:
        """
        Drop every cached quote in BAS' in-memory QuoteStore.

        Test-only. BAS validates quote freshness for risk-checked order
        types (LIMIT/STOP); without this hook a stale quote left behind
        by an earlier test can flip risk decisions for the current test.
        """
        client = self._get_client()
        headers = self._get_headers()
        try:
            response = await client.delete(
                "/api/v1/_test/cleanup/quote_store", headers=headers
            )
            response.raise_for_status()
            log.debug("BAS quote_store cleared")
            return response.json()
        except httpx.HTTPError as e:
            log.warning(f"BAS quote_store cleanup failed (non-critical): {e}")
            return {"status": "error", "message": str(e)}
