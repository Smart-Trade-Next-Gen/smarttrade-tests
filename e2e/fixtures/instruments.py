"""Instrument catalog for E2E tests.

Instruments are fetched from MDS, which contains the real Fyers instrument master.
The flow:
1. MDS DB is populated with real instruments from Fyers broker sync (deployment environment)
2. Tests query MDS /api/v1/instruments to discover available instruments
3. Tests trigger MDS restream to ensure BAS has the full catalog
4. BAS consumes instruments from market.instrument Redis stream
5. Tests use real canonical instrument IDs when placing orders
"""

import logging
from typing import Optional

log = logging.getLogger(__name__)


class InstrumentCatalog:
    """
    Session-scoped instrument catalog loaded from MDS.

    Provides convenient methods to fetch instruments by symbol, ID, or get arbitrary equities.
    Caches all instruments in memory for fast lookup.

    Instruments come from the deployment environment's MDS DB (populated by Fyers broker sync).
    Uses canonical instrument IDs in the format: {exchange}:{segment}:{instrument_type}:{symbol}
    Example: NSE:CM:EQUITY:SBIN
    """

    def __init__(self, instruments_data: list[dict]):
        """
        Initialize instrument catalog with pre-seeded instruments.

        Args:
            instruments_data: List of instrument dictionaries to load
        """
        self._instruments: list[dict] = []
        self._by_symbol: dict[str, dict] = {}
        self._by_id: dict[str, dict] = {}
        self._loaded = False
        self._instruments_data = instruments_data

    async def load(self) -> None:
        """
        Load instruments from MDS data.

        Assumes instruments_data was fetched from MDS /api/v1/instruments endpoint.
        Builds lookup maps by ID (canonical) and by symbol for convenience.

        Raises:
            Exception: If no instruments are provided
        """
        if self._loaded:
            log.debug("Instruments already loaded, skipping")
            return

        try:
            self._instruments = self._instruments_data
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
            log.error(f"Failed to load instruments: {e}")
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
        Get n arbitrary pure equity (cash stock) instruments.

        Filters out derivatives (options, futures) to return only plain equities.
        Useful for tests that need any tradable cash equity, not a derivative contract.

        Args:
            n: Number of instruments to return

        Returns:
            List of pure equity instrument dictionaries

        Raises:
            ValueError: If fewer than n pure equities available
            RuntimeError: If catalog not loaded
        """
        if not self._loaded:
            raise RuntimeError("Instrument catalog not loaded. Call load() first.")

        pure_equities = [
            i for i in self._instruments
            if i.get("instrument_type") == "EQUITY" and not i.get("derivative_type")
        ]

        if len(pure_equities) < n:
            raise ValueError(
                f"Only {len(pure_equities)} pure equities available, "
                f"cannot get {n}"
            )

        return pure_equities[:n]

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
