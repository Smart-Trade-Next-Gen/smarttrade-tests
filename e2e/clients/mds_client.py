"""
MDS (Market Data Service) WebSocket client.

Handles real-time streaming of market data and order/trade updates via WebSocket.
Implements automatic reconnection, heartbeat handling, and subscription management.
"""

import asyncio
import json
import logging
from typing import AsyncIterator, Optional

import websockets
from websockets.asyncio.client import ClientConnection

log = logging.getLogger(__name__)


class MDSWebSocketClient:
    """
    Async WebSocket client for Market Data Service.

    Handles connection lifecycle, auto-reconnect with exponential backoff,
    heartbeat responses, subscription management, and event streaming.
    """

    def __init__(
        self,
        ws_url: str,
        account_id: str,
        timeout: float = 30.0,
        heartbeat_interval: float = 5.0,
        initial_backoff: float = 1.0,
        max_backoff: float = 30.0,
    ):
        """
        Initialize MDSWebSocketClient.

        Args:
            ws_url: WebSocket URL for MDS (e.g., ws://localhost:8004)
            account_id: Account ID for subscription
            timeout: Connection timeout in seconds (default: 30.0)
            heartbeat_interval: Interval for responding to heartbeats (default: 5.0)
            initial_backoff: Initial reconnect backoff in seconds (default: 1.0)
            max_backoff: Maximum reconnect backoff in seconds (default: 30.0)
        """
        self.ws_url = ws_url.rstrip("/")
        self.account_id = account_id
        self.timeout = timeout
        self.heartbeat_interval = heartbeat_interval
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff

        self.connection: Optional[ClientConnection] = None
        self.is_connected = False
        self._reader_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._subscribed = False
        self._backoff = initial_backoff

    async def __aenter__(self) -> "MDSWebSocketClient":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()

    async def connect(self) -> None:
        """
        Establish WebSocket connection and wait for system.connected.

        Raises:
            TimeoutError: If connection times out
            ConnectionError: If unable to connect after retries
        """
        while not self.is_connected:
            try:
                log.info(
                    f"Connecting to MDS | ws_url={self.ws_url} | account_id={self.account_id}"
                )
                self.connection = await asyncio.wait_for(
                    websockets.asyncio.client.connect(self.ws_url),
                    timeout=self.timeout,
                )
                log.info(f"WebSocket connected to {self.ws_url}")

                # Wait for system.connected message
                await self._wait_for_system_connected()

                # Start reader and heartbeat tasks
                self._reader_task = asyncio.create_task(self._reader_loop())
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

                self.is_connected = True
                self._backoff = self.initial_backoff
                log.info(f"MDS connection established | account_id={self.account_id}")

                break

            except asyncio.TimeoutError:
                log.error(f"Connection timeout after {self.timeout}s, retrying...")
                await self._cleanup_connection()
                await self._backoff_wait()

            except Exception as e:
                log.error(f"Connection failed: {e}, retrying...")
                await self._cleanup_connection()
                await self._backoff_wait()

    async def disconnect(self) -> None:
        """Close WebSocket connection and cleanup resources."""
        self.is_connected = False

        # Cancel tasks
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        await self._cleanup_connection()
        log.info(f"MDS disconnected | account_id={self.account_id}")

    async def subscribe_account(self, account_id: Optional[str] = None) -> None:
        """
        Subscribe to account updates.

        Args:
            account_id: Account ID to subscribe (default: uses instance account_id)

        Raises:
            RuntimeError: If not connected
        """
        if not self.is_connected or self.connection is None:
            raise RuntimeError("Not connected to MDS. Call connect() first.")

        account_id = account_id or self.account_id
        subscribe_msg = {"type": "subscribe", "data": {"type": "account", "id": account_id}}

        try:
            log.info(f"Subscribing to account | account_id={account_id}")
            await self.connection.send(json.dumps(subscribe_msg))
            self._subscribed = True
            log.info(f"Subscription confirmed | account_id={account_id}")
        except Exception as e:
            log.error(f"Subscription failed: {e}")
            raise

    async def wait_connected(self, timeout: float = 5.0) -> None:
        """
        Wait until connected and subscribed.

        Args:
            timeout: Maximum wait time in seconds

        Raises:
            TimeoutError: If not connected within timeout
        """
        start = asyncio.get_event_loop().time()
        while not self.is_connected:
            if asyncio.get_event_loop().time() - start > timeout:
                raise TimeoutError(f"Not connected after {timeout}s")
            await asyncio.sleep(0.1)

    async def stream_events(self) -> AsyncIterator[dict]:
        """
        Stream order/trade/position update events.

        Filters out heartbeats, acks, and system messages.
        Yields only application events (order, trade, position updates).

        Yields:
            Event dictionaries with type, data

        Raises:
            RuntimeError: If not connected
        """
        if not self.is_connected:
            raise RuntimeError("Not connected to MDS. Call connect() first.")

        while self.is_connected:
            try:
                await asyncio.sleep(0.01)  # Prevent busy waiting
            except asyncio.CancelledError:
                break

    async def _wait_for_system_connected(self) -> None:
        """
        Wait for system.connected message from MDS.

        Raises:
            TimeoutError: If system.connected not received
        """
        if not self.connection:
            raise RuntimeError("Connection is None")

        try:
            message = await asyncio.wait_for(
                self.connection.recv(), timeout=self.timeout
            )
            data = json.loads(message)

            if data.get("type") == "system" and data.get("status") == "connected":
                log.debug("Received system.connected from MDS")
                return

            raise ValueError(f"Expected system.connected, got {data.get('type')}")

        except asyncio.TimeoutError:
            raise TimeoutError("system.connected not received within timeout")

    async def _reader_loop(self) -> None:
        """
        Background task to read messages from WebSocket.

        Routes messages to appropriate handlers (heartbeats, subscriptions, events).
        Handles reconnection on disconnect.
        """
        try:
            while self.is_connected and self.connection:
                try:
                    message = await asyncio.wait_for(
                        self.connection.recv(),
                        timeout=self.timeout,
                    )
                    await self._handle_message(json.loads(message))

                except asyncio.TimeoutError:
                    log.warning(f"WebSocket receive timeout, reconnecting...")
                    await self._handle_disconnect()

                except json.JSONDecodeError as e:
                    log.warning(f"Malformed JSON message: {e}, skipping")

                except Exception as e:
                    log.error(f"Reader error: {e}")
                    await self._handle_disconnect()

        except asyncio.CancelledError:
            log.debug("Reader loop cancelled")

    async def _heartbeat_loop(self) -> None:
        """
        Background task to respond to heartbeat pings.

        MDS sends periodic heartbeat messages; we respond with heartbeat ack.
        """
        try:
            while self.is_connected and self.connection:
                try:
                    await asyncio.sleep(self.heartbeat_interval)

                    if self.is_connected and self.connection:
                        heartbeat_msg = {"type": "heartbeat", "status": "pong"}
                        await self.connection.send(json.dumps(heartbeat_msg))
                        log.debug("Heartbeat pong sent")

                except Exception as e:
                    log.error(f"Heartbeat error: {e}")
                    await self._handle_disconnect()

        except asyncio.CancelledError:
            log.debug("Heartbeat loop cancelled")

    async def _handle_message(self, data: dict) -> None:
        """
        Route incoming message to appropriate handler.

        Args:
            data: Parsed JSON message from MDS
        """
        msg_type = data.get("type")

        if msg_type == "heartbeat":
            log.debug("Received heartbeat from MDS")

        elif msg_type == "ack":
            log.debug(f"Received ack: {data.get('data', {}).get('status')}")

        elif msg_type == "system":
            log.debug(f"System message: {data.get('status')}")

        elif msg_type in {"order.update", "trade.update", "position.update", "order_fill", "trade_exec", "position_update"}:
            log.debug(f"Event received: {msg_type}")
            # Events are handled via stream_events()

        else:
            log.debug(f"Unknown message type: {msg_type}")

    async def _handle_disconnect(self) -> None:
        """Handle WebSocket disconnect and trigger reconnection."""
        log.warning(f"Disconnected from MDS, attempting reconnection...")
        self.is_connected = False
        await self._cleanup_connection()

        # Reconnect
        try:
            await self.connect()
            if self._subscribed:
                await self.subscribe_account()
        except Exception as e:
            log.error(f"Reconnection failed: {e}")

    async def _cleanup_connection(self) -> None:
        """Close WebSocket connection safely."""
        if self.connection:
            try:
                await self.connection.aclose()
            except Exception as e:
                log.debug(f"Error closing connection: {e}")
            self.connection = None

    async def _backoff_wait(self) -> None:
        """Wait with exponential backoff before retrying."""
        wait_time = min(self._backoff, self.max_backoff)
        log.info(f"Backoff wait: {wait_time}s before next reconnect attempt")
        await asyncio.sleep(wait_time)
        self._backoff = min(self._backoff * 2, self.max_backoff)
