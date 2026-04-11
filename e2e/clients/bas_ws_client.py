"""
BAS (Broker Adapter Service) WebSocket client for account events.

Handles real-time streaming of trading events (orders, trades, positions) via WebSocket.
Implements automatic reconnection, heartbeat handling, and subscription management.
"""

import asyncio
import json
import logging
from typing import AsyncIterator, Optional

import websockets
from websockets.asyncio.client import ClientConnection
from websockets.exceptions import ConnectionClosed

log = logging.getLogger(__name__)


class BASWebSocketClient:
    """
    Async WebSocket client for Broker Adapter Service account events.

    Handles connection lifecycle, auto-reconnect with exponential backoff,
    heartbeat responses, subscription management, and event streaming.
    Specializes in trading events (orders, trades, positions), not market data.
    """

    def __init__(
        self,
        ws_url: str,
        account_id: str,
        token: str,
        timeout: float = 30.0,
        heartbeat_interval: float = 5.0,
        initial_backoff: float = 1.0,
        max_backoff: float = 30.0,
    ):
        """
        Initialize BASWebSocketClient.

        Args:
            ws_url: WebSocket URL for BAS (e.g., ws://localhost:8005/api/v1/ws)
            account_id: Account ID for subscription
            token: JWT token for authentication
            timeout: Connection timeout in seconds (default: 30.0)
            heartbeat_interval: Interval for responding to heartbeats (default: 5.0)
            initial_backoff: Initial reconnect backoff in seconds (default: 1.0)
            max_backoff: Maximum reconnect backoff in seconds (default: 30.0)
        """
        self.ws_url = ws_url.rstrip("/")
        self.account_id = account_id
        self.token = token
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
        self._event_queue: Optional[asyncio.Queue] = None
        self._system_connected_event: Optional[asyncio.Event] = None

    async def __aenter__(self) -> "BASWebSocketClient":
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
                    f"Connecting to BAS WebSocket | ws_url={self.ws_url} | account_id={self.account_id}"
                )
                # Add token and account_id as query parameters for authentication and routing
                ws_url_with_params = f"{self.ws_url}?token={self.token}&account_id={self.account_id}"
                self.connection = await asyncio.wait_for(
                    websockets.asyncio.client.connect(ws_url_with_params),
                    timeout=self.timeout,
                )
                log.info(f"BAS WebSocket connected to {self.ws_url}")

                # Initialize lazy resources (bound to current event loop)
                if self._event_queue is None:
                    self._event_queue = asyncio.Queue(maxsize=1000)
                if self._system_connected_event is None:
                    self._system_connected_event = asyncio.Event()

                # Reset system connected event for new connection
                self._system_connected_event.clear()

                # Start reader and heartbeat tasks FIRST (reader will handle system.connected)
                self._reader_task = asyncio.create_task(self._reader_loop())
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

                # Wait for system.connected to be signaled by reader loop
                await asyncio.wait_for(
                    self._system_connected_event.wait(),
                    timeout=self.timeout
                )

                self.is_connected = True
                self._backoff = self.initial_backoff
                log.info(f"BAS WebSocket connection established | account_id={self.account_id}")

                break

            except asyncio.TimeoutError:
                log.error(f"Connection timeout after {self.timeout}s, retrying...")
                await self._cleanup_resources()
                await self._backoff_wait()

            except Exception as e:
                log.error(f"Connection failed: {e}, retrying...")
                await self._cleanup_resources()
                await self._backoff_wait()

    async def disconnect(self) -> None:
        """Close WebSocket connection and cleanup resources."""
        self.is_connected = False
        await self._cleanup_resources()
        log.info(f"BAS WebSocket disconnected | account_id={self.account_id}")

    async def subscribe_account(self, account_id: Optional[str] = None) -> None:
        """
        Mark account as subscribed (for compatibility).

        Note: BAS WebSocket broadcasts events to all connected clients automatically.
        No explicit subscription message is required.

        Args:
            account_id: Account ID (stored for reference, not sent to server)

        Raises:
            RuntimeError: If not connected
        """
        if not self.is_connected or self.connection is None:
            raise RuntimeError("Not connected to BAS WebSocket. Call connect() first.")

        account_id = account_id or self.account_id

        # No subscription message needed - BAS broadcasts to all connected clients
        # Server automatically sends events after system.connected
        self._subscribed = True
        log.info(f"BAS account marked as subscribed | account_id={account_id}")

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
        Stream trading account events (orders, trades, positions).

        Filters out heartbeats, acks, and system messages.
        Yields only application events (order.filled, trade.executed, position.updated).

        Yields:
            Event dictionaries with type, data

        Raises:
            RuntimeError: If not connected
        """
        if not self.is_connected or self._event_queue is None:
            raise RuntimeError("Not connected to BAS WebSocket. Call connect() first.")

        while self.is_connected:
            try:
                event = await asyncio.wait_for(
                    self._event_queue.get(),
                    timeout=1.0
                )
                yield event
            except asyncio.TimeoutError:
                # No event received, continue waiting
                continue
            except asyncio.CancelledError:
                break

    async def _reader_loop(self) -> None:
        """
        Background task to read messages from WebSocket.

        Routes messages to appropriate handlers (heartbeats, subscriptions, events).
        Handles reconnection on disconnect.
        """
        log.debug("BAS reader loop started")
        try:
            while self.connection:
                log.debug(f"BAS reader loop iteration - connection={self.connection is not None}")
                try:
                    message = await asyncio.wait_for(
                        self.connection.recv(),
                        timeout=self.timeout,
                    )
                    data = json.loads(message)
                    log.debug(f"BAS reader loop received message type: {data.get('type')}")
                    await self._handle_message(data)

                except asyncio.TimeoutError:
                    log.warning(f"BAS WebSocket receive timeout, reconnecting...")
                    await self._handle_disconnect()

                except json.JSONDecodeError as e:
                    log.warning(f"BAS: Malformed JSON message: {e}, skipping")

                except ConnectionClosed as e:
                    # Check if this is a "Replaced by new connection" close
                    if e.rcvd and "Replaced by new connection" in str(e.rcvd.reason):
                        log.info(f"BAS connection replaced (normal idempotency handling), stopping gracefully")
                        self.is_connected = False
                        break
                    else:
                        log.error(f"BAS reader error: Connection closed: {e}")
                        await self._handle_disconnect()

                except Exception as e:
                    log.error(f"BAS reader error: {e}")
                    await self._handle_disconnect()

        except asyncio.CancelledError:
            log.debug("BAS reader loop cancelled")

    async def _heartbeat_loop(self) -> None:
        """
        Background task to respond to heartbeat pings.

        BAS sends periodic heartbeat messages; we respond with heartbeat ack.
        """
        try:
            while self.is_connected and self.connection:
                try:
                    await asyncio.sleep(self.heartbeat_interval)

                    if self.is_connected and self.connection:
                        heartbeat_msg = {"type": "heartbeat", "status": "pong"}
                        await self.connection.send(json.dumps(heartbeat_msg))
                        log.debug("BAS heartbeat pong sent")

                except Exception as e:
                    log.error(f"BAS heartbeat error: {e}")
                    await self._handle_disconnect()

        except asyncio.CancelledError:
            log.debug("BAS heartbeat loop cancelled")

    async def _handle_message(self, data: dict) -> None:
        """
        Route incoming message to appropriate handler.

        Args:
            data: Parsed JSON message from BAS
        """
        msg_type = data.get("type")

        if msg_type == "connection_ack":
            log.debug("Received connection_ack from BAS WebSocket")
            if self._system_connected_event:
                self._system_connected_event.set()

        elif msg_type == "system.connected":
            log.debug("Received system.connected from BAS WebSocket")
            if self._system_connected_event:
                self._system_connected_event.set()

        elif msg_type == "heartbeat":
            log.debug("Received heartbeat from BAS WebSocket")

        elif msg_type == "system.heartbeat":
            # System heartbeat with explicit prefix
            log.debug("Received system.heartbeat from BAS WebSocket")

        elif msg_type == "ack":
            log.debug(f"Received ack from BAS: {data.get('data', {}).get('status')}")

        elif msg_type == "system":
            log.debug(f"BAS system message: {data.get('status')}")

        elif msg_type == "notification":
            # System notification - extract inner event if present
            notification_data = data.get("data", {})
            log.debug(f"BAS NOTIFICATION: {json.dumps(data, default=str)[:500]}")

            # Check if notification wraps an actual event (e.g., order fill, trade exec)
            if "event_type" in notification_data:
                inner_event_type = notification_data.get("event_type")
                log.debug(f"Extracting event from BAS notification: event_type={inner_event_type}")

                # Map event_type to WebSocket message type
                event_type_map = {
                    "order_filled": "order.filled.v1",
                    "order_fill": "order.filled.v1",
                    "order_cancelled": "order.cancelled.v1",
                    "order_cancel": "order.cancelled.v1",
                    "trade_executed": "trade.executed.v1",
                    "trade_exec": "trade.executed.v1",
                    "position_updated": "position.updated.v1",
                    "position_update": "position.updated.v1",
                }

                mapped_type = event_type_map.get(inner_event_type, inner_event_type)

                # Create event message with mapped type
                inner_event = {
                    "type": mapped_type,
                    "data": notification_data,
                    "timestamp": notification_data.get("timestamp") or data.get("timestamp"),
                }

                # Add to queue if it's a recognized event type
                if mapped_type in {"order.filled.v1", "trade.executed.v1", "position.updated.v1", "order.cancelled.v1", "order.placed.v1"}:
                    log.debug(f"Adding extracted BAS event to queue: type={mapped_type}")
                    if self._event_queue:
                        try:
                            self._event_queue.put_nowait(inner_event)
                        except asyncio.QueueFull:
                            log.warning(f"BAS event queue full, dropping oldest event")
                            try:
                                self._event_queue.get_nowait()
                                self._event_queue.put_nowait(inner_event)
                            except Exception as e:
                                log.error(f"Failed to handle BAS event queue: {e}")

        elif msg_type == "event":
            # Handle event message: {"type": "event", "event_name": "...", "data": {...}, "sequence": N, "timestamp": "..."}
            event_name = data.get("event_name")
            if event_name and event_name in {"order.filled.v1", "trade.executed.v1", "position.updated.v1", "order.cancelled.v1", "order.placed.v1"}:
                log.debug(f"BAS event received: {event_name}")
                # Convert to flat message structure for compatibility with client code
                event_message = {
                    "type": event_name,
                    "data": data.get("data", {}),
                    "sequence": data.get("sequence"),
                    "timestamp": data.get("timestamp"),
                }
                if self._event_queue:
                    try:
                        self._event_queue.put_nowait(event_message)
                    except asyncio.QueueFull:
                        log.warning(f"BAS event queue full, dropping oldest event")
                        try:
                            self._event_queue.get_nowait()
                            self._event_queue.put_nowait(event_message)
                        except Exception as e:
                            log.error(f"Failed to handle BAS event queue: {e}")
            else:
                log.debug(f"BAS event type not recognized: {event_name}")

        elif msg_type in {"order.filled.v1", "trade.executed.v1", "position.updated.v1", "order.cancelled.v1", "order.placed.v1"}:
            log.debug(f"BAS event received: {msg_type}")
            # Add event to queue for stream_events() to yield
            if self._event_queue:
                try:
                    self._event_queue.put_nowait(data)
                except asyncio.QueueFull:
                    log.warning(f"BAS event queue full, dropping oldest event")
                    try:
                        self._event_queue.get_nowait()
                        self._event_queue.put_nowait(data)
                    except Exception as e:
                        log.error(f"Failed to handle BAS event queue: {e}")

        else:
            log.debug(f"BAS unknown message type: {msg_type} | Full message: {json.dumps(data, indent=2) if len(str(data)) < 1000 else str(data)[:1000]}")

    async def _handle_disconnect(self) -> None:
        """Handle WebSocket disconnect and trigger reconnection."""
        log.warning(f"Disconnected from BAS WebSocket, attempting reconnection...")
        self.is_connected = False
        await self._cleanup_connection()

        # Reconnect
        try:
            await self.connect()
            if self._subscribed:
                await self.subscribe_account()
        except Exception as e:
            log.error(f"BAS reconnection failed: {e}")

    async def _cleanup_connection(self) -> None:
        """Close WebSocket connection safely."""
        if self.connection:
            try:
                self.connection.close()
                try:
                    await asyncio.wait_for(self.connection.wait_closed(), timeout=2.0)
                except asyncio.TimeoutError:
                    log.warning("BAS: Timeout waiting for WebSocket to close")
            except Exception as e:
                log.debug(f"BAS: Error closing connection: {e}")
            self.connection = None

    async def _cleanup_resources(self) -> None:
        """Cancel all background tasks and close connection."""
        # Close connection first to interrupt any pending recv()
        await self._cleanup_connection()

        # Cancel reader task
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await asyncio.wait_for(self._reader_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            self._reader_task = None

        # Cancel heartbeat task
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await asyncio.wait_for(self._heartbeat_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            self._heartbeat_task = None

        # Drain event queue to prevent memory leak (items accumulate in asyncio.Queue)
        if self._event_queue is not None:
            try:
                while True:
                    self._event_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            self._event_queue = None

    async def _backoff_wait(self) -> None:
        """Wait with exponential backoff before retrying."""
        wait_time = min(self._backoff, self.max_backoff)
        log.info(f"BAS backoff wait: {wait_time}s before next reconnect attempt")
        await asyncio.sleep(wait_time)
        self._backoff = min(self._backoff * 2, self.max_backoff)
