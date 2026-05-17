"""
Broker state client for direct broker queries.

Supports multiple broker types (Fyers, PBS) with unified interface.
Broker is the single source of truth for order/position/trade state.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional
import httpx

log = logging.getLogger(__name__)


class BrokerStateClient(ABC):
    """Abstract base class for broker state clients."""
    
    @abstractmethod
    async def get_order_state(self, broker_id: str, account_id: str, order_id: str) -> dict:
        """Get order state from broker."""
        pass
    
    @abstractmethod
    async def get_position_state(self, broker_id: str, account_id: str, instrument_id: str) -> dict:
        """Get position state from broker."""
        pass
    
    @abstractmethod
    async def get_positions(self, broker_id: str, account_id: str) -> list:
        """Get all positions for an account from broker."""
        pass
    
    @abstractmethod
    async def get_trade_state(self, broker_id: str, account_id: str, order_id: str) -> dict:
        """Get trade state from broker."""
        pass
    
    @abstractmethod
    async def get_account_state(self, broker_id: str, account_id: str) -> dict:
        """Get account state from broker."""
        pass


class FyersStateClient(BrokerStateClient):
    """Fyers broker state client."""
    
    def __init__(self, api_url: str, token: str, timeout: float = 10.0):
        self.api_url = api_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=self.timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()
    
    async def get_order_state(self, broker_id: str, account_id: str, order_id: str) -> dict:
        """Query Fyers API for order state."""
        if not self.client:
            raise RuntimeError("Client not connected. Use async context manager.")
        
        # Implementation depends on Fyers API specifics
        # This is a placeholder - actual API calls need to be implemented
        url = f"{self.api_url}/orders/{order_id}"
        headers = {"Authorization": f"Bearer {self.token}"}
        
        response = await self.client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    
    async def get_position_state(self, broker_id: str, account_id: str, instrument_id: str) -> dict:
        """Query Fyers API for position state."""
        if not self.client:
            raise RuntimeError("Client not connected. Use async context manager.")
        
        url = f"{self.api_url}/positions"
        params = {"instrument_id": instrument_id}
        headers = {"Authorization": f"Bearer {self.token}"}
        
        response = await self.client.get(url, params=params, headers=headers)
        response.raise_for_status()
        
        positions = response.json()
        # Find matching position
        for pos in positions:
            if pos.get("instrument_id") == instrument_id:
                return pos
        return {}
    
    async def get_positions(self, broker_id: str, account_id: str) -> list:
        """Query Fyers API for all positions."""
        if not self.client:
            raise RuntimeError("Client not connected. Use async context manager.")
        
        url = f"{self.api_url}/positions"
        params = {"account_id": account_id}
        headers = {"Authorization": f"Bearer {self.token}"}
        
        response = await self.client.get(url, params=params, headers=headers)
        response.raise_for_status()
        
        return response.json()
    
    async def get_trade_state(self, broker_id: str, account_id: str, order_id: str) -> dict:
        """Query Fyers API for trade state."""
        if not self.client:
            raise RuntimeError("Client not connected. Use async context manager.")
        
        url = f"{self.api_url}/trades"
        params = {"order_id": order_id}
        headers = {"Authorization": f"Bearer {self.token}"}
        
        response = await self.client.get(url, params=params, headers=headers)
        response.raise_for_status()
        
        trades = response.json()
        for trade in trades:
            if trade.get("order_id") == order_id:
                return trade
        return {}
    
    async def get_account_state(self, broker_id: str, account_id: str) -> dict:
        """Query Fyers API for account state."""
        if not self.client:
            raise RuntimeError("Client not connected. Use async context manager.")
        
        url = f"{self.api_url}/account"
        headers = {"Authorization": f"Bearer {self.token}"}
        
        response = await self.client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()


class PBSStateClient(BrokerStateClient):
    """Paper Broker Service state client.
    
    Security Note: The caller must ensure that the provided token belongs to the user
    who is authorized to access the requested broker_id/account_id combination. This client
    does not perform user_id validation - it relies on the service's RBAC to enforce access control.
    """
    
    def __init__(self, base_url: str, token: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
        self.client = httpx.AsyncClient(timeout=self.timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()
    
    async def get_order_state(self, broker_id: str, account_id: str, order_id: str) -> dict:
        """Query PBS internal API for order state."""
        if not self.client:
            raise RuntimeError("Client not connected. Use async context manager.")
        
        url = f"{self.base_url}/api/v1/order/{broker_id}/{account_id}/{order_id}"
        headers = {"Authorization": f"Bearer {self.token}"}
        
        response = await self.client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    
    async def get_position_state(self, broker_id: str, account_id: str, instrument_id: str) -> dict:
        """Query PBS internal API for position state."""
        if not self.client:
            raise RuntimeError("Client not connected. Use async context manager.")
        
        url = f"{self.base_url}/api/v1/position/{broker_id}"
        params = {"account_id": account_id, "instrument_id": instrument_id}
        headers = {"Authorization": f"Bearer {self.token}"}
        
        response = await self.client.get(url, params=params, headers=headers)
        response.raise_for_status()
        
        positions = response.json()
        for pos in positions:
            if pos.get("instrument_id") == instrument_id:
                return pos
        return {}
    
    async def get_positions(self, broker_id: str, account_id: str) -> list:
        """Query PBS internal API for all positions."""
        if not self.client:
            raise RuntimeError("Client not connected. Use async context manager.")
        
        url = f"{self.base_url}/api/v1/position/{broker_id}"
        params = {"account_id": account_id}
        headers = {"Authorization": f"Bearer {self.token}"}
        
        response = await self.client.get(url, params=params, headers=headers)
        response.raise_for_status()
        
        return response.json()
    
    async def get_trade_state(self, broker_id: str, account_id: str, order_id: str) -> dict:
        """Query PBS internal API for trade state."""
        if not self.client:
            raise RuntimeError("Client not connected. Use async context manager.")
        
        url = f"{self.base_url}/api/v1/trade/{broker_id}"
        params = {"account_id": account_id, "order_id": order_id}
        headers = {"Authorization": f"Bearer {self.token}"}
        
        response = await self.client.get(url, params=params, headers=headers)
        response.raise_for_status()
        
        trades = response.json()
        for trade in trades:
            if trade.get("order_id") == order_id:
                return trade
        return {}
    
    async def get_account_state(self, broker_id: str, account_id: str) -> dict:
        """Query PBS internal API for account state.
        
        Args:
            broker_id: Broker identifier
            account_id: Account identifier
            
        Returns:
            Dictionary with cash_balance, balance, reserved, currency
            
        Raises:
            httpx.HTTPStatusError: If account doesn't exist (404) or other HTTP error
            RuntimeError: If client not connected
        """
        if not self.client:
            raise RuntimeError("Client not connected. Use async context manager.")
        
        url = f"{self.base_url}/api/v1/account/{broker_id}/{account_id}/balance"
        headers = {"Authorization": f"Bearer {self.token}"}
        
        try:
            response = await self.client.get(url, headers=headers)
            response.raise_for_status()
            
            balance_data = response.json()
            # Map to expected format
            return {
                "cash_balance": balance_data.get("available", 0),
                "balance": balance_data.get("balance", 0),
                "reserved": balance_data.get("reserved", 0),
                "currency": balance_data.get("currency", "INR"),
            }
        except httpx.HTTPStatusError as e:
            # Provide clearer error message for account not found
            if e.response.status_code == 404:
                raise httpx.HTTPStatusError(
                    f"Account not found: broker_id={broker_id}, account_id={account_id}",
                    request=e.request,
                    response=e.response
                )
            raise


def create_broker_state_client(broker_type: str, base_url: str, token: str, timeout: float = 10.0) -> BrokerStateClient:
    """
    Factory function to create broker-specific state client.
    
    Args:
        broker_type: Type of broker ("fyers" or "pbs")
        base_url: Base URL for broker API
        token: Authentication token
        timeout: Request timeout in seconds
    
    Returns:
        BrokerStateClient instance
    
    Raises:
        ValueError: If broker_type is not supported
    """
    broker_type = broker_type.lower()
    
    if broker_type == "fyers":
        return FyersStateClient(base_url, token, timeout)
    elif broker_type == "pbs":
        return PBSStateClient(base_url, token, timeout)
    else:
        raise ValueError(f"Unsupported broker type: {broker_type}")
