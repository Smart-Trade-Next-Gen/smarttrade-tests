"""REST client for Market Data Service (MDS) - Instrument API."""

import logging
from typing import Optional

import httpx

log = logging.getLogger(__name__)


class MDSRestClient:
    """REST client for fetching instruments from Market Data Service."""

    def __init__(self, base_url: str, timeout: float = 10.0):
        """
        Initialize MDS REST client.

        Args:
            base_url: Base URL of MDS service (e.g., http://localhost:8004)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client = None

    async def __aenter__(self):
        """Context manager entry."""
        self.client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self.client:
            await self.client.aclose()

    async def get_instruments(
        self,
        exchange: Optional[str] = None,
        instrument_type: Optional[str] = None,
    ) -> list[dict]:
        """
        Fetch all instruments from MDS (public endpoint, no auth required).

        Args:
            exchange: Optional filter by exchange (e.g., "NSE", "BSE")
            instrument_type: Optional filter by instrument type (e.g., "EQ", "FUT")

        Returns:
            List of instrument dictionaries

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        if not self.client:
            self.client = httpx.AsyncClient(timeout=self.timeout)

        url = f"{self.base_url}/api/v1/instruments"
        params = {}
        if exchange:
            params["exchange"] = exchange
        if instrument_type:
            params["type"] = instrument_type

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            instruments = data.get("instruments", [])
            log.debug(f"Fetched {len(instruments)} instruments from MDS")
            return instruments
        except httpx.HTTPStatusError as e:
            log.error(f"Failed to fetch instruments from MDS: {e.response.status_code}")
            raise

    async def get_instrument(self, instrument_id: str) -> dict:
        """
        Fetch a single instrument by ID (public endpoint, no auth required).

        Args:
            instrument_id: Instrument ID (e.g., "NSE:SBIN:EQ")

        Returns:
            Instrument dictionary

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        if not self.client:
            self.client = httpx.AsyncClient(timeout=self.timeout)

        url = f"{self.base_url}/api/v1/instruments/id/{instrument_id}"

        try:
            response = await self.client.get(url)
            response.raise_for_status()
            instrument = response.json()
            log.debug(f"Fetched instrument: {instrument_id}")
            return instrument
        except httpx.HTTPStatusError as e:
            log.error(f"Failed to fetch instrument {instrument_id}: {e.response.status_code}")
            raise

    async def get_instruments_by_ids(self, instrument_ids: list[str]) -> list[dict]:
        """
        Fetch multiple instruments by IDs (public endpoint, no auth required).

        Args:
            instrument_ids: List of instrument IDs

        Returns:
            List of instrument dictionaries

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        if not self.client:
            self.client = httpx.AsyncClient(timeout=self.timeout)

        url = f"{self.base_url}/api/v1/instruments/ids"

        try:
            response = await self.client.post(url, json=instrument_ids)
            response.raise_for_status()
            instruments = response.json().get("instruments", [])
            log.debug(f"Fetched {len(instruments)} instruments from MDS")
            return instruments
        except httpx.HTTPStatusError as e:
            log.error(f"Failed to fetch instruments from MDS: {e.response.status_code}")
            raise
