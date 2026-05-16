"""REST client for Portfolio Service - Async aggregation of positions and trades."""

import asyncio
import logging
from typing import Optional

import httpx

log = logging.getLogger(__name__)


class PortfolioClient:
    """REST client for Portfolio Service with polling support for eventual consistency."""

    def __init__(
        self,
        base_url: str,
        token: str,
        broker_id: str,
        account_id: str,
        timeout: float = 10.0,
    ):
        """
        Initialize Portfolio Service client.

        Args:
            base_url: Base URL of Portfolio Service (e.g., http://localhost:8008)
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

    async def get_positions(
        self,
        instrument_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """
        Fetch aggregated positions from Portfolio Service.

        Args:
            instrument_id: Optional filter by instrument ID
            limit: Number of positions to return
            offset: Pagination offset

        Returns:
            List of position dictionaries (AggregatedPositionResponse)

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        if not self.client:
            self.client = httpx.AsyncClient(
                timeout=self.timeout,
                headers=self._headers,
            )

        url = f"{self.base_url}/api/v1/positions/{self.broker_id}/{self.account_id}"
        params = {"limit": limit, "offset": offset}
        if instrument_id:
            params["instrument_id"] = instrument_id

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            positions = data.get("items", [])
            log.debug(f"Fetched {len(positions)} positions from Portfolio Service")
            return positions
        except httpx.HTTPStatusError as e:
            log.error(f"Failed to fetch positions: {e.response.status_code}")
            raise

    async def cleanup_positions(self) -> dict:
        """
        Delete every aggregated position for the current user.

        Testing-only. Portfolio aggregates accumulate across e2e tests
        because each fill mutates per-instrument totals; without this
        reset, tests sharing an instrument see growing net_qty across runs.
        """
        if not self.client:
            self.client = httpx.AsyncClient(
                timeout=self.timeout,
                headers=self._headers,
            )

        url = f"{self.base_url}/api/v1/positions/cleanup"
        try:
            response = await self.client.delete(url)
            response.raise_for_status()
            payload = response.json()
            log.debug(
                f"Portfolio positions cleared: {payload.get('positions_cleared', '?')}"
            )
            return payload
        except httpx.HTTPError as e:
            log.warning(f"Portfolio positions cleanup failed (non-critical): {e}")
            return {"status": "error", "message": str(e)}

    async def get_portfolio(self) -> dict:
        """
        Fetch portfolio summary (total exposure, cash, etc.).

        Returns:
            Portfolio summary dictionary (PortfolioSummaryResponse)

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        if not self.client:
            self.client = httpx.AsyncClient(
                timeout=self.timeout,
                headers=self._headers,
            )

        url = f"{self.base_url}/api/v1/portfolio/{self.broker_id}/{self.account_id}"

        try:
            response = await self.client.get(url)
            response.raise_for_status()
            portfolio = response.json()
            log.debug("Fetched portfolio summary")
            return portfolio
        except httpx.HTTPStatusError as e:
            log.error(f"Failed to fetch portfolio: {e.response.status_code}")
            raise

    async def wait_for_position(
        self,
        instrument_id: str,
        expected_qty: int,
        timeout: float = 15.0,
        poll_interval: float = 0.5,
    ) -> dict:
        """
        Poll positions until instrument reaches expected quantity.

        Implements hard timeout and polling for eventual consistency.
        Raises TimeoutError if position not found within timeout.

        Args:
            instrument_id: Instrument ID to wait for
            expected_qty: Expected net quantity
            timeout: Maximum wait time in seconds
            poll_interval: Time between polls in seconds

        Returns:
            Position dictionary when found

        Raises:
            TimeoutError: If position not found or qty doesn't match within timeout
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            try:
                positions = await self.get_positions(instrument_id=instrument_id)

                # Find position with matching instrument_id and qty
                for position in positions:
                    if position.get("instrument_id") == instrument_id:
                        net_qty = int(position.get("net_qty", 0))
                        if net_qty == expected_qty:
                            log.info(
                                f"✅ Position found: {instrument_id} qty={net_qty} "
                                f"avg_price={position.get('avg_price')}"
                            )
                            return position

                # Check timeout
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout:
                    log.error(
                        f"❌ Position not found within {timeout}s: "
                        f"{instrument_id} qty={expected_qty}"
                    )
                    raise TimeoutError(
                        f"Position {instrument_id} with qty={expected_qty} not found "
                        f"within {timeout}s. "
                        f"Found positions: {positions}"
                    )

                # Wait before next poll
                await asyncio.sleep(poll_interval)

            except httpx.HTTPStatusError as e:
                # Don't fail on transient errors, retry
                log.warning(f"Error fetching positions: {e.response.status_code}, retrying...")
                await asyncio.sleep(poll_interval)
                continue

    # Orders and trades belong to Journal Service after the read split.
    # Use JournalClient.get_orders / JournalClient.get_trades instead.
