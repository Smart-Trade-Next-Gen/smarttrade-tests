"""AI Service REST client for E2E testing."""

import httpx
from typing import Optional, Dict, Any, List
from datetime import datetime


class AIServiceClient:
    """REST client for AI Market Intelligence Service."""
    
    def __init__(self, base_url: str = "http://localhost:8014", timeout: int = 30):
        """Initialize AI Service client.
        
        Args:
            base_url: Base URL of the AI service
            timeout: Request timeout in seconds
        """
        self.base_url = base_url
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
    
    # Pattern Detection Endpoints
    async def get_patterns(
        self,
        instrument_id: Optional[str] = None,
        timeframe: Optional[str] = None,
        pattern_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        auth_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get patterns with filters."""
        params = {
            "instrument_id": instrument_id,
            "timeframe": timeframe,
            "pattern_type": pattern_type,
            "limit": limit,
            "offset": offset
        }
        headers = self._get_headers(auth_token)
        
        response = await self.client.get(
            f"{self.base_url}/api/v1/patterns",
            params=params,
            headers=headers
        )
        response.raise_for_status()
        return response.json()
    
    async def get_pattern(self, pattern_id: str, auth_token: Optional[str] = None) -> Dict[str, Any]:
        """Get a pattern by ID."""
        headers = self._get_headers(auth_token)
        
        response = await self.client.get(
            f"{self.base_url}/api/v1/patterns/{pattern_id}",
            headers=headers
        )
        response.raise_for_status()
        return response.json()
    
    async def detect_patterns(
        self,
        instrument_id: str,
        timeframe: str,
        timestamp: str,
        open_price: str,
        high_price: str,
        low_price: str,
        close_price: str,
        volume: int,
        auth_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Detect patterns from OHLCV data."""
        payload = {
            "instrument_id": instrument_id,
            "timeframe": timeframe,
            "timestamp": timestamp,
            "open_price": open_price,
            "high_price": high_price,
            "low_price": low_price,
            "close_price": close_price,
            "volume": volume
        }
        headers = self._get_headers(auth_token)
        
        response = await self.client.post(
            f"{self.base_url}/api/v1/patterns/detect",
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        return response.json()
    
    # Setup Intelligence Endpoints
    async def get_setups(
        self,
        instrument_id: Optional[str] = None,
        timeframe: Optional[str] = None,
        setup_type: Optional[str] = None,
        lifecycle_status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        auth_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get setups with filters."""
        params = {
            "instrument_id": instrument_id,
            "timeframe": timeframe,
            "setup_type": setup_type,
            "lifecycle_status": lifecycle_status,
            "limit": limit,
            "offset": offset
        }
        headers = self._get_headers(auth_token)
        
        response = await self.client.get(
            f"{self.base_url}/api/v1/setups",
            params=params,
            headers=headers
        )
        response.raise_for_status()
        return response.json()
    
    async def get_setup(self, setup_id: str, auth_token: Optional[str] = None) -> Dict[str, Any]:
        """Get a setup by ID."""
        headers = self._get_headers(auth_token)
        
        response = await self.client.get(
            f"{self.base_url}/api/v1/setups/{setup_id}",
            headers=headers
        )
        response.raise_for_status()
        return response.json()
    
    async def detect_setups(
        self,
        instrument_id: str,
        timeframe: str,
        timestamp: str,
        open_price: str,
        high_price: str,
        low_price: str,
        close_price: str,
        volume: int,
        auth_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Detect setups from market data."""
        payload = {
            "instrument_id": instrument_id,
            "timeframe": timeframe,
            "timestamp": timestamp,
            "open_price": open_price,
            "high_price": high_price,
            "low_price": low_price,
            "close_price": close_price,
            "volume": volume
        }
        headers = self._get_headers(auth_token)
        
        response = await self.client.post(
            f"{self.base_url}/api/v1/setups/detect",
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        return response.json()
    
    async def update_setup_lifecycle(
        self,
        setup_id: str,
        lifecycle_status: str,
        auth_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update setup lifecycle status."""
        headers = self._get_headers(auth_token)
        
        response = await self.client.patch(
            f"{self.base_url}/api/v1/setups/{setup_id}/lifecycle",
            params={"lifecycle_status": lifecycle_status},
            headers=headers
        )
        response.raise_for_status()
        return response.json()
    
    # Market Regime Endpoints
    async def get_regimes(
        self,
        instrument_id: Optional[str] = None,
        regime_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        auth_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get market regimes with filters."""
        params = {
            "instrument_id": instrument_id,
            "regime_type": regime_type,
            "limit": limit,
            "offset": offset
        }
        headers = self._get_headers(auth_token)
        
        response = await self.client.get(
            f"{self.base_url}/api/v1/regime",
            params=params,
            headers=headers
        )
        response.raise_for_status()
        return response.json()
    
    async def get_latest_regime(
        self,
        instrument_id: str,
        timeframe: Optional[str] = None,
        auth_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get latest regime for an instrument."""
        params = {"timeframe": timeframe} if timeframe else {}
        headers = self._get_headers(auth_token)
        
        response = await self.client.get(
            f"{self.base_url}/api/v1/regime/latest/{instrument_id}",
            params=params,
            headers=headers
        )
        response.raise_for_status()
        return response.json()
    
    async def classify_regime(
        self,
        instrument_id: str,
        timeframe: str,
        timestamp: str,
        close_price: str,
        volume: int,
        auth_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Classify market regime for an instrument."""
        payload = {
            "instrument_id": instrument_id,
            "timeframe": timeframe,
            "timestamp": timestamp,
            "close_price": close_price,
            "volume": volume
        }
        headers = self._get_headers(auth_token)
        
        response = await self.client.post(
            f"{self.base_url}/api/v1/regime/classify",
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        return response.json()
    
    # Watchlist Intelligence Endpoints
    async def get_watchlists(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
        auth_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get watchlists for a user."""
        params = {"user_id": user_id, "limit": limit, "offset": offset}
        headers = self._get_headers(auth_token)
        
        response = await self.client.get(
            f"{self.base_url}/api/v1/watchlists",
            params=params,
            headers=headers
        )
        response.raise_for_status()
        return response.json()
    
    async def create_watchlist(
        self,
        name: str,
        user_id: str,
        description: str,
        watchlist_type: str,
        metadata: Dict[str, Any],
        auth_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new watchlist."""
        payload = {
            "name": name,
            "user_id": user_id,
            "description": description,
            "watchlist_type": watchlist_type,
            "metadata": metadata
        }
        headers = self._get_headers(auth_token)
        
        response = await self.client.post(
            f"{self.base_url}/api/v1/watchlists",
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        return response.json()
    
    # Similarity Search Endpoints
    async def search_similar(
        self,
        query_vector: List[float],
        vector_type: str,
        entity_type: str,
        instrument_id: str,
        timeframe: str,
        k: int = 10,
        similarity_threshold: float = 0.8,
        distance_metric: str = "cosine",
        auth_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search for similar vectors using pgvector."""
        payload = {
            "query_vector": query_vector,
            "vector_type": vector_type,
            "entity_type": entity_type,
            "instrument_id": instrument_id,
            "timeframe": timeframe,
            "k": k,
            "similarity_threshold": similarity_threshold,
            "distance_metric": distance_metric
        }
        headers = self._get_headers(auth_token)
        
        response = await self.client.post(
            f"{self.base_url}/api/v1/similarity/search",
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        return response.json()
    
    # Feature Store Endpoints
    async def list_features(
        self,
        entity_type: str,
        instrument_id: Optional[str] = None,
        timeframe: Optional[str] = None,
        feature_category: Optional[str] = None,
        from_timestamp: Optional[str] = None,
        to_timestamp: Optional[str] = None,
        limit: int = 100,
        auth_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """List features with filters."""
        params = {
            "entity_type": entity_type,
            "instrument_id": instrument_id,
            "timeframe": timeframe,
            "feature_category": feature_category,
            "from_timestamp": from_timestamp,
            "to_timestamp": to_timestamp,
            "limit": limit
        }
        headers = self._get_headers(auth_token)
        
        response = await self.client.get(
            f"{self.base_url}/api/v1/features/",
            params=params,
            headers=headers
        )
        response.raise_for_status()
        return response.json()
    
    async def get_features(
        self,
        entity_type: str,
        entity_id: str,
        timestamp: Optional[str] = None,
        auth_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get features for a specific entity."""
        params = {"timestamp": timestamp} if timestamp else {}
        headers = self._get_headers(auth_token)
        
        response = await self.client.get(
            f"{self.base_url}/api/v1/features/{entity_type}/{entity_id}",
            params=params,
            headers=headers
        )
        response.raise_for_status()
        return response.json()
    
    # Probability Engine Endpoints
    async def calculate_probability(
        self,
        setup_id: Optional[str] = None,
        pattern_id: Optional[str] = None,
        time_horizon: str = "1d",
        confidence_level: float = 0.95,
        force_recalculate: bool = False,
        auth_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Calculate probability for a setup or pattern."""
        payload = {
            "setup_id": setup_id,
            "pattern_id": pattern_id,
            "time_horizon": time_horizon,
            "confidence_level": confidence_level,
            "force_recalculate": force_recalculate
        }
        headers = self._get_headers(auth_token)
        
        response = await self.client.post(
            f"{self.base_url}/api/v1/probabilities/calculate",
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        return response.json()
    
    # Health Check Endpoints
    async def health_check(self) -> Dict[str, Any]:
        """Check service health."""
        response = await self.client.get(f"{self.base_url}/")
        response.raise_for_status()
        return response.json()
    
    async def readiness_check(self) -> Dict[str, Any]:
        """Check service readiness."""
        response = await self.client.get(f"{self.base_url}/ready")
        response.raise_for_status()
        return response.json()
    
    def _get_headers(self, auth_token: Optional[str]) -> Dict[str, str]:
        """Get request headers with optional auth token."""
        headers = {"Content-Type": "application/json"}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        return headers