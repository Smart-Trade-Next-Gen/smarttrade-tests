"""REST client for Signal Processor Service - Analysis API."""

import logging
from typing import Optional, Dict, Any
from decimal import Decimal

import httpx

log = logging.getLogger(__name__)


class SignalProcessorClient:
    """REST client for Signal Processor Service."""

    def __init__(self, base_url: str, timeout: float = 10.0):
        """
        Initialize Signal Processor Service client.

        Args:
            base_url: Base URL of signal-processor-service (e.g., http://localhost:8012)
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

    def _get_headers(self, token: Optional[str] = None) -> Dict[str, str]:
        """Get request headers with optional authentication."""
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def analyze_candle(
        self,
        instrument_id: str,
        timeframe: str,
        ohlcv: Dict[str, Any],
        token: Optional[str] = None,
        user_id: Optional[str] = None,
        broker_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Analyze a candle using the signal processor service.
        
        Note: This method is deprecated as signal-processor-service is read-only.
        Use get_analysis() instead to retrieve analysis results.

        Args:
            instrument_id: Instrument identifier (e.g., "NIFTY50-INDEX")
            timeframe: Timeframe (e.g., "5m", "15m", "1h")
            ohlcv: OHLCV data dictionary with open, high, low, close, volume, timestamp
            token: Optional JWT token for authentication
            user_id: Optional user ID for multi-tenancy
            broker_id: Optional broker ID for multi-tenancy

        Returns:
            Analysis result dictionary
        """
        # Signal-processor-service is read-only, so this method will fail
        # Kept for backward compatibility but not functional
        raise NotImplementedError(
            "Signal-processor-service is read-only. Use get_analysis() instead."
        )

    async def get_analysis(
        self,
        instrument_id: str,
        timeframe: str,
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get analysis for an instrument and timeframe.

        Args:
            instrument_id: Instrument identifier (e.g., "NIFTY50-INDEX")
            timeframe: Timeframe (e.g., "5m", "15m", "1h")
            token: Optional JWT token for authentication

        Returns:
            Analysis result dictionary
        """
        url = f"{self.base_url}/api/v1/analysis/{instrument_id}/{timeframe}"
        headers = self._get_headers(token)

        response = await self.client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()

    async def get_instruments(
        self,
        token: Optional[str] = None,
    ) -> list[Dict[str, Any]]:
        """
        Get available instruments from signal processor service.
        
        Note: This endpoint may not exist in signal-processor-service.
        Use MDS service for instrument data.

        Args:
            token: Optional JWT token for authentication

        Returns:
            List of instrument dictionaries
        """
        # Signal-processor-service doesn't have instruments endpoint
        # Kept for backward compatibility but not functional
        raise NotImplementedError(
            "Signal-processor-service doesn't have instruments endpoint. "
            "Use MDS service (MDSRestClient) for instrument data."
        )

    async def health_check(self) -> Dict[str, Any]:
        """
        Check signal processor service health.

        Returns:
            Health check result dictionary
        """
        url = f"{self.base_url}/health"
        response = await self.client.get(url)
        response.raise_for_status()
        data = response.json()
        # Handle if response is a tuple (response, status_code)
        if isinstance(data, list) and len(data) == 2:
            return data[0]
        return data

    async def list_signals(
        self,
        token: Optional[str] = None,
        broker_id: Optional[str] = None,
        trading_type: Optional[str] = None,
        signal_type: Optional[str] = None,
        min_confidence: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        List active trading signals for the current user's instruments.

        Args:
            token: Optional JWT token for authentication
            broker_id: Optional broker ID filter
            trading_type: Optional trading type filter (SCALPING, DAY_TRADING, etc.)
            signal_type: Optional signal type filter (BUY, SELL)
            min_confidence: Optional minimum confidence score (0.0-1.0)

        Returns:
            Dictionary with signals list and count
        """
        url = f"{self.base_url}/api/v1/signals"
        headers = self._get_headers(token)
        
        params = {}
        if broker_id:
            params["broker_id"] = broker_id
        if trading_type:
            params["trading_type"] = trading_type
        if signal_type:
            params["signal_type"] = signal_type
        if min_confidence is not None:
            params["min_confidence"] = min_confidence

        response = await self.client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()

    async def get_instrument_signals(
        self,
        instrument_id: str,
        broker_id: str,
        token: Optional[str] = None,
        timeframe: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get signals for a specific instrument.

        Args:
            instrument_id: Instrument ID
            broker_id: Broker ID
            token: Optional JWT token for authentication
            timeframe: Optional timeframe filter

        Returns:
            Dictionary with instrument signals
        """
        url = f"{self.base_url}/api/v1/signals/instruments/{instrument_id}"
        headers = self._get_headers(token)
        
        params = {"broker_id": broker_id}
        if timeframe:
            params["timeframe"] = timeframe

        response = await self.client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()

    async def get_signals_summary(
        self,
        token: Optional[str] = None,
        broker_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get a summary of signals by trading type.

        Args:
            token: Optional JWT token for authentication
            broker_id: Optional broker ID filter

        Returns:
            Dictionary with signal summary grouped by trading type
        """
        url = f"{self.base_url}/api/v1/signals/summary"
        headers = self._get_headers(token)
        
        params = {}
        if broker_id:
            params["broker_id"] = broker_id

        response = await self.client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()

    async def add_instrument(
        self,
        broker_id: str,
        instrument_id: str,
        trading_type: str,
        timeframes: Optional[list[str]] = None,
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Add an instrument to the user's watchlist.

        Args:
            broker_id: Broker ID
            instrument_id: Instrument ID
            trading_type: Trading type (SCALPING, DAY_TRADING, etc.)
            timeframes: Optional list of timeframes (auto-populated from trading_type if not provided)
            token: JWT token for authentication

        Returns:
            Dictionary with instrument details and historical data fetch status
        """
        url = f"{self.base_url}/api/v1/instruments"
        headers = self._get_headers(token)
        
        payload = {
            "broker_id": broker_id,
            "instrument_id": instrument_id,
            "trading_type": trading_type,
        }
        if timeframes:
            payload["timeframes"] = timeframes

        response = await self.client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()

    async def list_instruments(
        self,
        token: Optional[str] = None,
        broker_id: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        List instruments for the current user.

        Args:
            token: Optional JWT token for authentication
            broker_id: Optional broker ID filter
            is_active: Optional active status filter

        Returns:
            Dictionary with instruments list
        """
        url = f"{self.base_url}/api/v1/instruments"
        headers = self._get_headers(token)
        
        params = {}
        if broker_id:
            params["broker_id"] = broker_id
        if is_active is not None:
            params["is_active"] = is_active

        response = await self.client.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
