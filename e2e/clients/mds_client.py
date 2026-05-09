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
from websockets.exceptions import ConnectionClosed

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
        token: str,
        user_id: Optional[str] = None,
        timeout: float = 30.0,
        heartbeat_interval: float = 5.0,
        initial_backoff: float = 1.0,
        max_backoff: float = 30.0,
        max_reconnect_attempts: int = 5,
        auto_reconnect: bool = False,
    ):
        """
        Initialize MDSWebSocketClient.

        Args:
            ws_url: WebSocket URL for MDS UI route (e.g., ws://localhost:8004/ws/fyers/ui)
            account_id: Account ID used in subscribe.account UI messages
            token: JWT token for authentication
            user_id: User UUID — included as a ?user_id= query param so the MDS
                UI route is consistently keyed by user (matches the inter-service
                subscription model on market.subscription.request.v1). MDS
                authoritatively reads user_id from the JWT; this query param is
                cosmetic/observability for now.
            timeout: Connection timeout in seconds (default: 30.0)
            heartbeat_interval: Interval for responding to heartbeats (default: 5.0)
            initial_backoff: Initial reconnect backoff in seconds (default: 1.0)
            max_backoff: Maximum reconnect backoff in seconds (default: 30.0)
            max_reconnect_attempts: Maximum connect attempts before raising
                ConnectionError. Bounded to prevent unbounded connection growth
                that crashes the service. (default: 5)
            auto_reconnect: When True, the client transparently reconnects on
                disconnect via a supervisor task. When False (default for tests),
                the client surfaces disconnects loudly so test failures are
                visible instead of hidden behind silent reconnect storms.
        """
        self.ws_url = ws_url.rstrip("/")
        self.account_id = account_id
        self.user_id = user_id
        self.token = token
        self.timeout = timeout
        self.heartbeat_interval = heartbeat_interval
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.max_reconnect_attempts = max_reconnect_attempts
        self.auto_reconnect = auto_reconnect

        self.connection: Optional[ClientConnection] = None
        self.is_connected = False
        self._reader_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._subscribed = False
        self._backoff = initial_backoff
        self._event_queue: Optional[asyncio.Queue] = None
        self._system_connected_event: Optional[asyncio.Event] = None
        # Serializes connect()/disconnect() so concurrent disconnects from the
        # reader and heartbeat loops cannot fire parallel connect() retries.
        # Lazy-init in connect() so the lock binds to the active event loop.
        self._connect_lock: Optional[asyncio.Lock] = None
        self._reconnecting = False

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

        Bounded by ``max_reconnect_attempts``: if all attempts fail this raises
        ``ConnectionError`` instead of looping forever, preventing the
        connection storm that previously exhausted resources.

        Concurrent calls are serialized by ``_connect_lock`` and become
        no-ops once the first call succeeds.

        Raises:
            ConnectionError: If unable to connect after ``max_reconnect_attempts``
        """
        if self._connect_lock is None:
            self._connect_lock = asyncio.Lock()

        async with self._connect_lock:
            if self.is_connected and self.connection is not None:
                log.debug("MDS WebSocket already connected, skipping connect()")
                return

            self._backoff = self.initial_backoff
            last_error: Optional[BaseException] = None

            for attempt in range(1, self.max_reconnect_attempts + 1):
                # Always close any leaked connection/tasks from a previous
                # iteration before opening a new one. This is the invariant
                # that prevents the connection leak.
                await self._cleanup_resources()

                try:
                    log.info(
                        f"Connecting to MDS "
                        f"(attempt {attempt}/{self.max_reconnect_attempts}) | "
                        f"ws_url={self.ws_url} | user_id={self.user_id} | "
                        f"account_id={self.account_id}"
                    )
                    # Token authenticates; user_id query param matches the
                    # user-scoped subscription model used elsewhere in MDS.
                    ws_url_with_params = (
                        f"{self.ws_url}?token={self.token}&user_id={self.user_id}"
                    )
                    self.connection = await asyncio.wait_for(
                        websockets.asyncio.client.connect(ws_url_with_params),
                        timeout=self.timeout,
                    )
                    log.info(f"MDS WebSocket connected to {self.ws_url}")

                    # Initialize lazy resources (bound to current event loop)
                    if self._event_queue is None:
                        self._event_queue = asyncio.Queue(maxsize=1000)
                    if self._system_connected_event is None:
                        self._system_connected_event = asyncio.Event()
                    self._system_connected_event.clear()

                    # Start reader and heartbeat tasks FIRST (reader will handle system.connected)
                    self._reader_task = asyncio.create_task(self._reader_loop())
                    self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

                    # Wait for system.connected to be signaled by reader loop
                    await asyncio.wait_for(
                        self._system_connected_event.wait(),
                        timeout=self.timeout,
                    )

                    self.is_connected = True
                    self._backoff = self.initial_backoff
                    log.info(
                        f"MDS WebSocket connection established | "
                        f"account_id={self.account_id}"
                    )
                    return

                except asyncio.CancelledError:
                    # Don't swallow cancellation — propagate after cleanup.
                    await self._cleanup_resources()
                    raise

                except asyncio.TimeoutError as e:
                    last_error = e
                    log.error(
                        f"MDS connect attempt {attempt}/{self.max_reconnect_attempts} "
                        f"timed out after {self.timeout}s"
                    )

                except Exception as e:
                    last_error = e
                    log.error(
                        f"MDS connect attempt {attempt}/{self.max_reconnect_attempts} "
                        f"failed: {e}"
                    )

                if attempt < self.max_reconnect_attempts:
                    await self._backoff_wait()

            # Exhausted retries — clean up and surface a hard error so callers
            # see the failure instead of silently leaking connections.
            await self._cleanup_resources()
            raise ConnectionError(
                f"MDS WebSocket failed to connect after "
                f"{self.max_reconnect_attempts} attempts | "
                f"ws_url={self.ws_url} | last_error={last_error!r}"
            )

    async def disconnect(self) -> None:
        """Close WebSocket connection and cleanup resources.

        Cancels any in-flight reconnect supervisor first so it cannot race
        the disconnect and resurrect a connection after we tore it down.
        """
        self.is_connected = False
        # Suppress reconnects during teardown.
        self.auto_reconnect = False

        if self._reconnect_task is not None and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await asyncio.wait_for(self._reconnect_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            self._reconnect_task = None

        await self._cleanup_resources()
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
        subscribe_msg = {
            "action": "subscribe.account",
            "accounts": [{"account_id": account_id}]
        }

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
        if not self.is_connected or self._event_queue is None:
            raise RuntimeError("Not connected to MDS. Call connect() first.")

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
        On disconnect, schedules reconnect via supervisor task and exits — never
        runs reconnect inline (which would cancel this task mid-execution and
        corrupt the connection state).
        """
        log.debug("MDS reader loop started")
        try:
            while self.connection:
                try:
                    message = await asyncio.wait_for(
                        self.connection.recv(),
                        timeout=self.timeout,
                    )
                    data = json.loads(message)
                    log.debug(f"MDS reader loop received message type: {data.get('type')}")
                    await self._handle_message(data)

                except asyncio.TimeoutError:
                    log.warning("MDS WebSocket receive timeout")
                    self._schedule_reconnect()
                    return

                except json.JSONDecodeError as e:
                    log.warning(f"MDS: Malformed JSON message: {e}, skipping")

                except ConnectionClosed as e:
                    # "Replaced by new connection" is a graceful close from the
                    # server's idempotency handling — don't trigger reconnect.
                    if e.rcvd and "Replaced by new connection" in str(e.rcvd.reason):
                        log.info("MDS connection replaced (server idempotency), stopping gracefully")
                        self.is_connected = False
                        return
                    log.error(f"MDS reader error: Connection closed: {e}")
                    self._schedule_reconnect()
                    return

                except Exception as e:
                    log.error(f"MDS reader error: {e}")
                    self._schedule_reconnect()
                    return

        except asyncio.CancelledError:
            log.debug("MDS reader loop cancelled")

    async def _heartbeat_loop(self) -> None:
        """
        Background task to respond to heartbeat pings.

        On send failure, schedules reconnect and exits cleanly. Does not run
        reconnect inline (avoids self-cancellation when reconnect closes tasks).
        """
        try:
            while self.is_connected and self.connection:
                try:
                    await asyncio.sleep(self.heartbeat_interval)

                    if self.is_connected and self.connection:
                        heartbeat_msg = {"type": "heartbeat", "status": "pong"}
                        await self.connection.send(json.dumps(heartbeat_msg))
                        log.debug("MDS heartbeat pong sent")

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    log.error(f"MDS heartbeat error: {e}")
                    self._schedule_reconnect()
                    return

        except asyncio.CancelledError:
            log.debug("MDS heartbeat loop cancelled")

    async def _handle_message(self, data: dict) -> None:
        """
        Route incoming message to appropriate handler.

        Args:
            data: Parsed JSON message from MDS
        """
        msg_type = data.get("type")

        if msg_type == "system.connected":
            log.debug("Received system.connected from MDS")
            if self._system_connected_event:
                self._system_connected_event.set()

        elif msg_type == "heartbeat":
            log.debug("Received heartbeat from MDS")

        elif msg_type == "system.heartbeat":
            # System heartbeat with explicit prefix
            log.debug("Received system.heartbeat from MDS")

        elif msg_type == "ack":
            log.debug(f"Received ack: {data.get('data', {}).get('status')}")

        elif msg_type == "system":
            log.debug(f"System message: {data.get('status')}")

        elif msg_type == "notification":
            # System notification - extract inner event if present
            notification_data = data.get("data", {})
            log.debug(f"NOTIFICATION: {json.dumps(data, default=str)[:500]}")

            # Check if notification wraps an actual event (e.g., order fill, trade exec)
            if "event_type" in notification_data:
                inner_event_type = notification_data.get("event_type")
                log.debug(f"Extracting event from notification: event_type={inner_event_type}")

                # Map event_type to WebSocket message type
                event_type_map = {
                    "order_filled": "order_fill",
                    "order_fill": "order_fill",
                    "trade_executed": "trade_exec",
                    "trade_exec": "trade_exec",
                    "order_cancelled": "order_cancelled",
                    "position_updated": "position_update",
                    "position_update": "position_update",
                }

                mapped_type = event_type_map.get(inner_event_type, inner_event_type)

                # Create event message with mapped type
                inner_event = {
                    "type": mapped_type,
                    "data": notification_data,
                    "timestamp": notification_data.get("timestamp") or data.get("timestamp"),
                }

                # Add to queue if it's a recognized event type
                if mapped_type in {"order_fill", "trade_exec", "position_update", "order_cancelled", "order.update", "trade.update", "position.update"}:
                    log.debug(f"Adding extracted event to queue: type={mapped_type}")
                    if self._event_queue:
                        try:
                            self._event_queue.put_nowait(inner_event)
                        except asyncio.QueueFull:
                            log.warning(f"Event queue full, dropping oldest event")
                            try:
                                self._event_queue.get_nowait()
                                self._event_queue.put_nowait(inner_event)
                            except Exception as e:
                                log.error(f"Failed to handle event queue: {e}")
                else:
                    log.debug(f"Unknown inner event type in notification: {mapped_type}")
            else:
                log.debug(f"System notification without event_type")

        elif msg_type in {"order.update", "trade.update", "position.update", "order_fill", "trade_exec", "position_update", "order_cancelled"}:
            log.debug(f"Event received: {msg_type}")
            # Add event to queue for stream_events() to yield
            if self._event_queue:
                try:
                    self._event_queue.put_nowait(data)
                except asyncio.QueueFull:
                    log.warning(f"Event queue full, dropping oldest event")
                    try:
                        self._event_queue.get_nowait()
                        self._event_queue.put_nowait(data)
                    except Exception as e:
                        log.error(f"Failed to handle event queue: {e}")

        else:
            log.warning(f"Unknown message type: {msg_type} | Full message: {json.dumps(data, indent=2) if len(str(data)) < 1000 else str(data)[:1000]}")

    def _schedule_reconnect(self) -> None:
        """
        Mark the connection as dead and (optionally) schedule a reconnect.

        The reconnect runs in a *separate* supervisor task so the calling
        reader/heartbeat task can exit cleanly. Running ``connect()`` inline
        from those tasks would cancel the very task that is awaiting it.

        When ``auto_reconnect`` is False (default), the client just records
        the disconnect — the next ``connect()`` call (or test failure)
        surfaces the issue. This is the safe default for tests, where a
        silent reconnect storm previously crashed the service.
        """
        self.is_connected = False

        if not self.auto_reconnect:
            log.info(
                "MDS auto_reconnect disabled — marking client disconnected; "
                "call connect() explicitly to reconnect"
            )
            return

        if self._reconnecting:
            log.debug("MDS reconnect already scheduled, skipping duplicate trigger")
            return

        if self._reconnect_task is not None and not self._reconnect_task.done():
            log.debug("MDS reconnect task already running, skipping duplicate trigger")
            return

        self._reconnect_task = asyncio.create_task(self._reconnect_supervisor())

    async def _reconnect_supervisor(self) -> None:
        """Run a single bounded reconnect attempt off the reader/heartbeat tasks."""
        if self._reconnecting:
            return
        self._reconnecting = True
        try:
            await self.connect()
            if self._subscribed:
                await self.subscribe_account()
        except Exception as e:
            log.error(f"MDS reconnection failed: {e}")
        finally:
            self._reconnecting = False

    async def _cleanup_connection(self) -> None:
        """Close WebSocket connection safely."""
        if self.connection:
            try:
                self.connection.close()
                try:
                    await asyncio.wait_for(self.connection.wait_closed(), timeout=2.0)
                except asyncio.TimeoutError:
                    log.warning("Timeout waiting for WebSocket to close")
            except Exception as e:
                log.debug(f"Error closing connection: {e}")
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
        log.info(f"Backoff wait: {wait_time}s before next reconnect attempt")
        await asyncio.sleep(wait_time)
        self._backoff = min(self._backoff * 2, self.max_backoff)
