"""REST client for Journal Service - Trade audit trail and journaling."""

import asyncio
import logging
from typing import Optional
from uuid import UUID

import httpx

log = logging.getLogger(__name__)


def _validate_uuid(id_str: str) -> str:
    """Validate UUID format."""
    try:
        UUID(id_str)
        return id_str
    except ValueError as e:
        raise ValueError(f"Invalid UUID format: {id_str}") from e


class JournalClient:
    """REST client for Journal Service with polling support for eventual consistency."""

    def __init__(
        self,
        base_url: str,
        token: str,
        broker_id: str,
        account_id: str,
        timeout: float = 10.0,
    ):
        """
        Initialize Journal Service client.

        Args:
            base_url: Base URL of Journal Service (e.g., http://localhost:8007)
            token: JWT authentication token
            broker_id: Broker scope for all queries (required path segment after split)
            account_id: Account scope for all queries (required path segment after split)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.broker_id = broker_id
        self.account_id = account_id
        self.timeout = timeout
        self.client = None
        self._headers = {"Authorization": f"Bearer {token}"}

    async def __aenter__(self):
        """Context manager entry."""
        self.client = httpx.AsyncClient(
            timeout=self.timeout,
            headers=self._headers,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self.client:
            await self.client.aclose()

    async def get_journal_entries(
        self,
        instrument_id: Optional[str] = None,
        lifecycle_status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """
        Fetch journal entries (audit trail for trades).

        Args:
            instrument_id: Optional filter by instrument ID
            lifecycle_status: Optional filter by lifecycle status (e.g., "OPEN", "CLOSED")
            limit: Number of entries to return
            offset: Pagination offset

        Returns:
            List of journal entry dictionaries (JournalEntryResponse)

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        if not self.client:
            self.client = httpx.AsyncClient(
                timeout=self.timeout,
                headers=self._headers,
            )

        url = f"{self.base_url}/api/v1/journal/{self.broker_id}/{self.account_id}"
        params = {"limit": limit, "offset": offset}
        if instrument_id:
            params["instrument_id"] = instrument_id
        if lifecycle_status:
            params["lifecycle_status"] = lifecycle_status

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            entries = data.get("items", [])
            log.debug(f"Fetched {len(entries)} journal entries")
            return entries
        except httpx.HTTPStatusError as e:
            log.error(f"Failed to fetch journal entries: {e.response.status_code}")
            raise

    async def get_trades(
        self,
        instrument_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """
        Fetch trades from journal (executed trades with full details).

        Args:
            instrument_id: Optional filter by instrument ID
            limit: Number of trades to return
            offset: Pagination offset

        Returns:
            List of trade dictionaries (TradeResponse)

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        if not self.client:
            self.client = httpx.AsyncClient(
                timeout=self.timeout,
                headers=self._headers,
            )

        url = f"{self.base_url}/api/v1/trades/{self.broker_id}/{self.account_id}"
        params = {"limit": limit, "offset": offset}
        if instrument_id:
            params["instrument_id"] = instrument_id

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            trades = data.get("items", [])
            log.debug(f"Fetched {len(trades)} trades from journal")
            return trades
        except httpx.HTTPStatusError as e:
            log.error(f"Failed to fetch trades: {e.response.status_code}")
            raise

    async def wait_for_trade(
        self,
        order_id: str,
        timeout: float = 15.0,
        poll_interval: float = 0.5,
    ) -> dict:
        """
        Poll trades until one matching the order_id is found.

        Implements hard timeout and polling for eventual consistency.
        Raises TimeoutError if trade not found within timeout.

        Args:
            order_id: Order ID to wait for
            timeout: Maximum wait time in seconds
            poll_interval: Time between polls in seconds

        Returns:
            Trade dictionary when found

        Raises:
            TimeoutError: If trade not found within timeout
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            try:
                trades = await self.get_trades(limit=100)

                # Find trade with matching order_id
                for trade in trades:
                    if trade.get("order_id") == order_id:
                        log.info(
                            f"✅ Trade found: order_id={order_id} "
                            f"qty={trade.get('quantity')} price={trade.get('price')}"
                        )
                        return trade

                # Check timeout
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout:
                    log.error(f"❌ Trade not found within {timeout}s: order_id={order_id}")
                    raise TimeoutError(
                        f"Trade with order_id={order_id} not found within {timeout}s. "
                        f"Available trades: {[t.get('order_id') for t in trades]}"
                    )

                # Wait before next poll
                await asyncio.sleep(poll_interval)

            except httpx.HTTPStatusError as e:
                # Don't fail on transient errors, retry
                log.warning(f"Error fetching trades: {e.response.status_code}, retrying...")
                await asyncio.sleep(poll_interval)
                continue

    async def wait_for_journal_entry(
        self,
        instrument_id: str,
        lifecycle_status: str = "OPEN",
        timeout: float = 15.0,
        poll_interval: float = 0.5,
    ) -> dict:
        """
        Poll journal entries until one matching instrument and status is found.

        Implements hard timeout and polling for eventual consistency.

        Args:
            instrument_id: Instrument ID to wait for
            lifecycle_status: Lifecycle status to match (e.g., "OPEN", "CLOSED")
            timeout: Maximum wait time in seconds
            poll_interval: Time between polls in seconds

        Returns:
            Journal entry dictionary when found

        Raises:
            TimeoutError: If entry not found within timeout
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            try:
                entries = await self.get_journal_entries(
                    instrument_id=instrument_id,
                    lifecycle_status=lifecycle_status,
                    limit=100,
                )

                # If we got entries, return the first one
                if entries:
                    entry = entries[0]
                    log.info(
                        f"✅ Journal entry found: {instrument_id} "
                        f"status={entry.get('lifecycle_status')}"
                    )
                    return entry

                # Check timeout
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout:
                    log.error(
                        f"❌ Journal entry not found within {timeout}s: "
                        f"{instrument_id} {lifecycle_status}"
                    )
                    raise TimeoutError(
                        f"Journal entry for {instrument_id} with status={lifecycle_status} "
                        f"not found within {timeout}s"
                    )

                # Wait before next poll
                await asyncio.sleep(poll_interval)

            except httpx.HTTPStatusError as e:
                # Don't fail on transient errors, retry
                log.warning(f"Error fetching journal entries: {e.response.status_code}, retrying...")
                await asyncio.sleep(poll_interval)
                continue

    async def get_orders(
        self,
        instrument_id: Optional[str] = None,
        status: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> list[dict]:
        """
        Fetch orders from journal with filters.

        Args:
            instrument_id: Optional filter by instrument ID
            status: Optional filter by status (PENDING, FILLED, PARTIAL, CANCELLED, REJECTED)
            from_date: Optional filter orders placed after this datetime
            to_date: Optional filter orders placed before this datetime
            page: Page number (default: 1)
            page_size: Items per page (default: 50, max: 200)

        Returns:
            List of order dictionaries
        """
        if page < 1:
            raise ValueError("page must be >= 1")
        if page_size < 1 or page_size > 200:
            raise ValueError("page_size must be between 1 and 200")

        if not self.client:
            self.client = httpx.AsyncClient(
                timeout=self.timeout,
                headers=self._headers,
            )

        url = f"{self.base_url}/api/v1/orders/{self.broker_id}/{self.account_id}"
        params = {"page": page, "page_size": page_size}
        if instrument_id:
            params["instrument_id"] = instrument_id
        if status:
            params["status"] = status
        if from_date:
            params["from_date"] = from_date
        if to_date:
            params["to_date"] = to_date

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            orders = data.get("orders", [])
            log.debug(f"Fetched {len(orders)} orders from journal")
            return orders
        except httpx.HTTPStatusError as e:
            log.error(f"Failed to fetch orders: {e.response.status_code}")
            raise

    async def get_order_by_id(
        self,
        order_id: str,
    ) -> dict:
        """
        Fetch a specific order by ID (broker_order_id).

        Args:
            order_id: Order ID (broker_order_id)

        Returns:
            Order dictionary

        Raises:
            httpx.HTTPStatusError: If request fails or order not found
        """
        if not self.client:
            self.client = httpx.AsyncClient(
                timeout=self.timeout,
                headers=self._headers,
            )

        url = f"{self.base_url}/api/v1/orders/{self.broker_id}/{self.account_id}/{order_id}"

        try:
            response = await self.client.get(url)
            response.raise_for_status()
            order = response.json()
            log.debug(f"Fetched order {order_id}")
            return order
        except httpx.HTTPStatusError as e:
            log.error(f"Failed to fetch order {order_id}: {e.response.status_code}")
            raise

    async def get_trade_by_id(
        self,
        trade_id: str,
    ) -> dict:
        """
        Fetch a specific trade by ID.

        Args:
            trade_id: Trade ID (UUID)

        Returns:
            Trade dictionary

        Raises:
            httpx.HTTPStatusError: If request fails or trade not found
            ValueError: If trade_id is not a valid UUID
        """
        trade_id = _validate_uuid(trade_id)

        if not self.client:
            self.client = httpx.AsyncClient(
                timeout=self.timeout,
                headers=self._headers,
            )

        url = f"{self.base_url}/api/v1/trades/{self.broker_id}/{self.account_id}/{trade_id}"

        try:
            response = await self.client.get(url)
            response.raise_for_status()
            trade = response.json()
            log.debug(f"Fetched trade {trade_id}")
            return trade
        except httpx.HTTPStatusError as e:
            log.error(f"Failed to fetch trade {trade_id}: {e.response.status_code}")
            raise

    async def get_actions(
        self,
        instrument_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """
        Fetch actions from journal.

        Args:
            instrument_id: Optional filter by instrument ID
            limit: Number of actions to return
            offset: Pagination offset

        Returns:
            List of action dictionaries
        """
        if limit < 1 or limit > 200:
            raise ValueError("limit must be between 1 and 200")
        if offset < 0:
            raise ValueError("offset must be >= 0")

        if not self.client:
            self.client = httpx.AsyncClient(
                timeout=self.timeout,
                headers=self._headers,
            )

        url = f"{self.base_url}/api/v1/actions/{self.broker_id}/{self.account_id}"
        params = {"limit": limit, "offset": offset}
        if instrument_id:
            params["instrument_id"] = instrument_id

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            actions = data.get("items", [])
            log.debug(f"Fetched {len(actions)} actions from journal")
            return actions
        except httpx.HTTPStatusError as e:
            log.error(f"Failed to fetch actions: {e.response.status_code}")
            raise

    async def get_action_by_id(
        self,
        action_id: str,
    ) -> dict:
        """
        Fetch a specific action by ID.

        Args:
            action_id: Action ID (UUID)

        Returns:
            Action dictionary

        Raises:
            httpx.HTTPStatusError: If request fails or action not found
            ValueError: If action_id is not a valid UUID
        """
        action_id = _validate_uuid(action_id)

        if not self.client:
            self.client = httpx.AsyncClient(
                timeout=self.timeout,
                headers=self._headers,
            )

        url = f"{self.base_url}/api/v1/actions/{self.broker_id}/{self.account_id}/{action_id}"

        try:
            response = await self.client.get(url)
            response.raise_for_status()
            action = response.json()
            log.debug(f"Fetched action {action_id}")
            return action
        except httpx.HTTPStatusError as e:
            log.error(f"Failed to fetch action {action_id}: {e.response.status_code}")
            raise

    async def get_journal_entry_by_id(
        self,
        journal_id: str,
    ) -> dict:
        """
        Fetch a specific journal entry by ID.

        Args:
            journal_id: Journal entry ID (UUID)

        Returns:
            Journal entry dictionary

        Raises:
            httpx.HTTPStatusError: If request fails or entry not found
            ValueError: If journal_id is not a valid UUID
        """
        journal_id = _validate_uuid(journal_id)

        if not self.client:
            self.client = httpx.AsyncClient(
                timeout=self.timeout,
                headers=self._headers,
            )

        url = f"{self.base_url}/api/v1/journal/{self.broker_id}/{self.account_id}/{journal_id}"

        try:
            response = await self.client.get(url)
            response.raise_for_status()
            entry = response.json()
            log.debug(f"Fetched journal entry {journal_id}")
            return entry
        except httpx.HTTPStatusError as e:
            log.error(f"Failed to fetch journal entry {journal_id}: {e.response.status_code}")
            raise
