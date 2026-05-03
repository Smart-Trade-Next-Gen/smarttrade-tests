"""Instrument catalog for E2E tests - Fetches real instruments from MDS."""

import logging
from typing import Optional

from e2e.clients.mds_rest_client import MDSRestClient

log = logging.getLogger(__name__)


class InstrumentCatalog:
    """
    Session-scoped instrument catalog that loads instruments from MDS once.

    Provides convenient methods to fetch instruments by symbol, ID, or get arbitrary equities.
    Caches all instruments in memory for fast lookup.
    """

    def __init__(self, mds_rest_client: MDSRestClient):
        """
        Initialize instrument catalog.

        Args:
            mds_rest_client: MDSRestClient instance for fetching instruments
        """
        self.mds_client = mds_rest_client
        self._instruments: list[dict] = []
        self._by_symbol: dict[str, dict] = {}
        self._by_id: dict[str, dict] = {}
        self._loaded = False

    async def load(self) -> None:
        """
        Fetch and cache all instruments from MDS.

        Call once at session startup. Raises error if MDS is unavailable.

        Raises:
            Exception: If instruments cannot be fetched from MDS
        """
        if self._loaded:
            log.debug("Instruments already loaded, skipping")
            return

        try:
            self._instruments = await self.mds_client.get_instruments()
            log.info(f"Loaded {len(self._instruments)} instruments from MDS")

            # Build lookup maps
            for instrument in self._instruments:
                instrument_id = instrument.get("id")
                symbol = instrument.get("symbol")

                if instrument_id:
                    self._by_id[instrument_id] = instrument
                if symbol:
                    self._by_symbol[symbol] = instrument

            self._loaded = True
            log.info(
                f"✅ Instrument catalog ready: {len(self._by_id)} by ID, "
                f"{len(self._by_symbol)} by symbol"
            )
        except Exception as e:
            log.error(f"Failed to load instruments from MDS: {e}")
            raise

    def get_equity(self, symbol: str) -> dict:
        """
        Get instrument by equity symbol.

        Args:
            symbol: Equity symbol (e.g., "SBIN", "INFY", "TCS")

        Returns:
            Instrument dictionary

        Raises:
            KeyError: If symbol not found
        """
        if not self._loaded:
            raise RuntimeError("Instrument catalog not loaded. Call load() first.")

        if symbol not in self._by_symbol:
            raise KeyError(
                f"Equity {symbol} not found in catalog. "
                f"Available symbols: {list(self._by_symbol.keys())[:10]}..."
            )

        return self._by_symbol[symbol]

    def get_by_id(self, instrument_id: str) -> dict:
        """
        Get instrument by ID.

        Args:
            instrument_id: Instrument ID (e.g., "NSE:SBIN:EQ")

        Returns:
            Instrument dictionary

        Raises:
            KeyError: If ID not found
        """
        if not self._loaded:
            raise RuntimeError("Instrument catalog not loaded. Call load() first.")

        if instrument_id not in self._by_id:
            raise KeyError(
                f"Instrument {instrument_id} not found in catalog. "
                f"Available IDs: {list(self._by_id.keys())[:10]}..."
            )

        return self._by_id[instrument_id]

    def get_any_equity(self, n: int = 1) -> list[dict]:
        """
        Get n arbitrary equity instruments.

        Useful for tests that don't care which specific instrument is used.

        Args:
            n: Number of instruments to return

        Returns:
            List of instrument dictionaries

        Raises:
            ValueError: If fewer than n instruments available
        """
        if not self._loaded:
            raise RuntimeError("Instrument catalog not loaded. Call load() first.")

        if len(self._instruments) < n:
            raise ValueError(
                f"Only {len(self._instruments)} instruments available, "
                f"cannot get {n}"
            )

        # Return first n instruments
        return self._instruments[:n]

    def search_by_segment(self, segment: str) -> list[dict]:
        """
        Search instruments by segment.

        Args:
            segment: Segment type (e.g., "EQ", "FUT", "OPT")

        Returns:
            List of matching instruments
        """
        if not self._loaded:
            raise RuntimeError("Instrument catalog not loaded. Call load() first.")

        results = []
        for instrument in self._instruments:
            if instrument.get("segment") == segment:
                results.append(instrument)

        return results

    def list_all(self) -> list[dict]:
        """
        Get all loaded instruments.

        Returns:
            List of all instrument dictionaries
        """
        if not self._loaded:
            raise RuntimeError("Instrument catalog not loaded. Call load() first.")

        return list(self._instruments)

    def count(self) -> int:
        """Get total number of loaded instruments."""
        return len(self._instruments)
