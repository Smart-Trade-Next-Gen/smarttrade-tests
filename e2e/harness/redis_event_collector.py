"""
Redis stream event collector for E2E testing.

Collects events directly from Redis Streams (bypassing service WebSockets).
Uses consumer groups for reliable event consumption with idempotency.
"""

import asyncio
import json
import logging
from typing import Optional, List
import redis.asyncio as redis

log = logging.getLogger(__name__)


class RedisEventCollector:
    """
    Async event collector using Redis Streams.

    Each instance owns a unique consumer group (one per test). On subscribe,
    the group is created with id="0" so any events published just before the
    reader starts blocking are still delivered. The reader uses a single
    XREADGROUP call across all streams, so there is no per-stream polling gap.
    """

    def __init__(
        self,
        redis_url: str,
        consumer_group: str,
        consumer_name: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.redis_url = redis_url
        self.consumer_group = consumer_group
        self.consumer_name = consumer_name or f"consumer-{id(self):x}"
        self.timeout = timeout

        self.redis_client: Optional[redis.Redis] = None
        self.queues: dict[str, asyncio.Queue] = {}
        self.events: dict[str, List[dict]] = {}
        # Mirror every consumed event under its stream name as well so tests
        # can find events that don't carry an order_id (notably
        # position.updated, which is keyed on instrument_id).
        self.events_by_stream: dict[str, List[dict]] = {}
        self._subscribed_streams: set[str] = set()
        self._running = False
        self._reader_task: Optional[asyncio.Task] = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()

    async def connect(self) -> None:
        """Connect to Redis."""
        self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
        await self.redis_client.ping()
        log.info(f"Connected to Redis at {self.redis_url}")

    async def disconnect(self) -> None:
        """Stop the reader, close Redis."""
        self._running = False

        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None

        log.info("Disconnected from Redis")

    async def subscribe_to_streams(
        self, stream_patterns: List[str], replay_from_start: bool = False
    ) -> None:
        """
        Subscribe to Redis Streams via a per-collector consumer group.

        The group is created with mkstream=True so streams are auto-created.
        - replay_from_start=False (default): id="$" — only events added after
          subscribe are delivered. Correct for E2E tests, since the test body
          (which triggers the producer) runs strictly after this returns.
        - replay_from_start=True: id="0" — every existing event in the stream
          is delivered before new ones. Use only when the test explicitly
          relies on pre-existing state.
        """
        if not self.redis_client:
            raise RuntimeError("Not connected. Call connect() first.")

        start_id = "0" if replay_from_start else "$"
        for stream in stream_patterns:
            try:
                await self.redis_client.xgroup_create(
                    stream, self.consumer_group, id=start_id, mkstream=True
                )
                log.info(
                    f"Created consumer group {self.consumer_group} on {stream}"
                )
            except redis.ResponseError as e:
                if "BUSYGROUP" in str(e):
                    log.debug(
                        f"Consumer group {self.consumer_group} already exists on {stream}"
                    )
                else:
                    raise
            self._subscribed_streams.add(stream)

        self._running = True
        self._reader_task = asyncio.create_task(self._reader_loop())
        log.info(
            f"Subscribed to streams: {sorted(self._subscribed_streams)} "
            f"as group={self.consumer_group} consumer={self.consumer_name}"
        )

    async def _reader_loop(self) -> None:
        """
        Background task: single XREADGROUP across all subscribed streams.

        Using ">" returns only messages not yet delivered to this group's
        consumer. We block up to 500ms per call so cancellation stays
        responsive. All streams are read in one call, so there is no
        per-stream gap.
        """
        while self._running:
            try:
                if not self._subscribed_streams:
                    await asyncio.sleep(0.1)
                    continue

                streams_arg = {s: ">" for s in self._subscribed_streams}
                try:
                    messages = await self.redis_client.xreadgroup(
                        self.consumer_group,
                        self.consumer_name,
                        streams=streams_arg,
                        count=100,
                        block=500,
                    )
                except redis.ResponseError as e:
                    log.error(f"xreadgroup failed: {e}")
                    await asyncio.sleep(0.5)
                    continue

                if not messages:
                    continue

                for stream_name, stream_messages in messages:
                    for message_id, fields in stream_messages:
                        await self._process_message(stream_name, message_id, fields)

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.exception(f"Unexpected error in reader loop: {e}")
                await asyncio.sleep(0.5)

    async def _process_message(self, stream: str, message_id: str, fields: dict) -> None:
        """Parse one message and enqueue it under its order_id."""
        try:
            raw = fields.get("event", "{}")
            event_data = json.loads(raw)

            payload = event_data.get("payload") or {}
            event_type = (
                event_data.get("event_name")
                or event_data.get("event_type")
                or event_data.get("type")
                or stream
            )

            # BAS publishes order.updated with `payload.order_id` set to the
            # client_order_id for PLACED/ACCEPTED (before the broker call) and
            # to the broker_order_id for FILLED/CANCELLED (which originate from
            # the broker WS). Index the event under every id we can find so
            # tests can wait on whichever id the API handed them.
            ids: set[str] = set()
            for key in ("order_id", "broker_order_id", "client_order_id"):
                value = payload.get(key) or event_data.get(key)
                if value:
                    ids.add(str(value))

            event = {
                "stream": stream,
                "message_id": message_id,
                "type": event_type,
                "data": event_data,
                "payload": payload,
                "timestamp": fields.get("timestamp") or event_data.get("timestamp"),
            }

            # Always mirror the event under its stream so tests can locate
            # events that don't carry an order_id (e.g. position.updated
            # is keyed on instrument_id).
            self.events_by_stream.setdefault(stream, []).append(event)

            if not ids:
                log.debug(
                    f"Event without order_id stored under stream only | "
                    f"stream={stream} id={message_id}"
                )
                await self._safe_ack(stream, message_id)
                return

            for oid in ids:
                self.events.setdefault(oid, []).append(event)
                self.queues.setdefault(oid, asyncio.Queue()).put_nowait(event)

            log.debug(
                f"Processed event | stream={stream} | order_ids={sorted(ids)} "
                f"| type={event_type} | id={message_id}"
            )
        except Exception as e:
            log.exception(
                f"Error processing message | stream={stream} id={message_id}: {e}"
            )
        finally:
            await self._safe_ack(stream, message_id)

    async def _safe_ack(self, stream: str, message_id: str) -> None:
        try:
            await self.redis_client.xack(stream, self.consumer_group, message_id)
        except Exception as e:
            log.warning(
                f"xack failed | stream={stream} group={self.consumer_group} id={message_id}: {e}"
            )

    async def wait_for_event(
        self,
        order_id: str,
        event_type: str,
        timeout: Optional[float] = None,
    ) -> dict:
        """Wait for a specific event type for an order."""
        timeout = timeout or self.timeout
        deadline = asyncio.get_event_loop().time() + timeout

        for event in self.events.get(order_id, []):
            if event.get("type") == event_type:
                return event

        queue = self.queues.setdefault(order_id, asyncio.Queue())
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise TimeoutError(
                    f"Event {event_type} not found for order_id={order_id}"
                )
            try:
                event = await asyncio.wait_for(queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                raise TimeoutError(
                    f"Event {event_type} not found for order_id={order_id}"
                )
            if event.get("type") == event_type:
                return event

    async def wait_for_completion(
        self,
        order_id: str,
        timeout: Optional[float] = None,
    ) -> List[dict]:
        """Wait for order to reach a terminal status (FILLED/CANCELLED/REJECTED/EXPIRED)."""
        timeout = timeout or self.timeout
        deadline = asyncio.get_event_loop().time() + timeout
        terminal_statuses = {"FILLED", "CANCELLED", "REJECTED", "EXPIRED"}

        def _has_terminal() -> bool:
            for ev in self.events.get(order_id, []):
                status = (ev.get("payload") or {}).get("status")
                if status in terminal_statuses:
                    log.info(
                        f"Order reached terminal status | order_id={order_id} | status={status}"
                    )
                    return True
            return False

        if _has_terminal():
            return self.events[order_id]

        queue = self.queues.setdefault(order_id, asyncio.Queue())
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise TimeoutError(
                    f"Terminal status not reached for order_id={order_id} within {timeout}s"
                )
            try:
                await asyncio.wait_for(queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                raise TimeoutError(
                    f"Terminal status not reached for order_id={order_id} within {timeout}s"
                )
            if _has_terminal():
                return self.events[order_id]

    def get_events(self, order_id: str) -> List[dict]:
        """Get all events for an order in arrival order."""
        return list(self.events.get(order_id, []))

    def get_events_on_stream(self, stream: str) -> List[dict]:
        """Get every event seen on a stream in arrival order, regardless of
        whether the event was keyed to an order_id."""
        return list(self.events_by_stream.get(stream, []))

    async def cleanup(self) -> None:
        """Destroy this collector's consumer group on every subscribed stream.

        Stops the reader first so an in-flight XREADGROUP cannot race the
        group destroy and log a spurious NOGROUP error.
        """
        if not self.redis_client:
            return

        self._running = False
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        for stream in list(self._subscribed_streams):
            try:
                await self.redis_client.xgroup_destroy(stream, self.consumer_group)
                log.info(
                    f"Destroyed consumer group {self.consumer_group} on {stream}"
                )
            except Exception as e:
                log.warning(
                    f"Failed to destroy consumer group {self.consumer_group} on {stream}: {e}"
                )
