"""Instrument catalog for E2E tests.

Instruments are pre-seeded into consumer service databases (BAS, PBS)
during test setup, following the event-driven architecture where:
1. Instruments are synced from external sources to MDS
2. MDS emits instrument events to consumers
3. Consumers store instruments in their own databases
4. Tests load instruments from consumer databases, not MDS
"""

import logging
from typing import Optional

log = logging.getLogger(__name__)


class InstrumentCatalog:
    """
    Session-scoped instrument catalog loaded from consumer service databases.

    Provides convenient methods to fetch instruments by symbol, ID, or get arbitrary equities.
    Caches all instruments in memory for fast lookup.

    Note: Instruments are pre-seeded into BAS/PBS databases during fixture setup.
    This simulates the event-driven flow where consumer services receive instrument
    events and store them in their own databases.
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
        Load instruments from pre-seeded data.

        This simulates the event-driven architecture where instruments
        are already in consumer service databases.

        Raises:
            Exception: If no instruments are provided
        """
        if self._loaded:
            log.debug("Instruments already loaded, skipping")
            return

        try:
            self._instruments = self._instruments_data
            log.info(f"Loaded {len(self._instruments)} instruments from test data")

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
