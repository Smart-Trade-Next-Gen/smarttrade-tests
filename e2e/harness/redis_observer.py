"""Direct Redis stream observer for event validation - No consumer heartbeat registration."""

import asyncio
import json
import logging
from typing import Callable, Optional

import redis.asyncio as redis

log = logging.getLogger(__name__)


class RedisStreamObserver:
    """
    Observes Redis Streams directly without registering heartbeats.

    Creates a separate consumer group (`e2e-test-observer`) that does NOT interfere
    with RedisEventBus.publish()'s consumer-readiness checks. This allows passive
    observation of events for test validation without affecting the production
    event flow.
    """

    OBSERVER_GROUP = "e2e-test-observer"

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        """
        Initialize Redis observer.

        Args:
            redis_url: Redis connection URL (e.g., "redis://localhost:6379/0")
        """
        self.redis_url = redis_url
        self.redis = None
        self._created_groups: set[str] = set()

    async def start(self) -> None:
        """Connect to Redis and prepare for stream observation."""
        try:
            self.redis = await redis.from_url(self.redis_url, decode_responses=True)
            await self.redis.ping()
            log.info(f"✅ Connected to Redis: {self.redis_url}")
        except Exception as e:
            log.error(f"Failed to connect to Redis: {e}")
            raise

    async def stop(self) -> None:
        """Cleanup and disconnect from Redis."""
        if self.redis:
            try:
                await self.redis.close()
                log.debug("✅ Redis connection closed")
            except Exception as e:
                log.warning(f"Error closing Redis connection: {e}")

    async def _ensure_consumer_group(self, stream_key: str) -> None:
        """
        Create consumer group for stream if it doesn't exist.

        Uses `XGROUP CREATE ... id=$` to start at current tail (new messages only).

        Args:
            stream_key: Redis stream key
        """
        if stream_key in self._created_groups:
            return

        try:
            await self.redis.xgroup_create(
                name=stream_key,
                groupname=self.OBSERVER_GROUP,
                id="$",  # Start at current tail
                mkstream=True,  # Create the stream if missing so first-test pre-warm
                                # doesn't fail before any producer has published.
            )
            self._created_groups.add(stream_key)
            log.debug(f"Created consumer group {self.OBSERVER_GROUP} for {stream_key}")
        except redis.exceptions.ResponseError as e:
            # Group may already exist
            if "BUSYGROUP" in str(e):
                self._created_groups.add(stream_key)
                log.debug(f"Consumer group {self.OBSERVER_GROUP} already exists for {stream_key}")
            else:
                log.warning(f"Error creating consumer group: {e}")

    async def observe_stream(
        self,
        event_type: str,
        timeout: float = 15.0,
        count: int = 10,
    ) -> list[dict]:
        """
        Read messages from a Redis stream using the observer consumer group.

        Stream key format: `events:{event_type}` (e.g., `events:order.updated.v1`)

        Args:
            event_type: Event type name
            timeout: Timeout for read operation in seconds
            count: Maximum number of messages to read

        Returns:
            List of unwrapped event payload dictionaries

        Raises:
            Exception: If Redis read fails
        """
        stream_key = f"events:{event_type}"

        try:
            await self._ensure_consumer_group(stream_key)

            # Read with XREADGROUP using observer group
            messages = await self.redis.xreadgroup(
                groupname=self.OBSERVER_GROUP,
                consumername=f"observer-{id(self)}",
                streams={stream_key: ">"},  # New messages
                count=count,
                block=int(timeout * 1000),  # Convert to milliseconds
            )

            events = []
            if messages:
                for stream, message_list in messages:
                    for msg_id, msg_data in message_list:
                        try:
                            # Unwrap event envelope
                            event = self._unwrap_envelope(msg_data)
                            events.append(event)
                            log.debug(f"Observed event: {event_type} from {stream}")
                        except Exception as e:
                            log.warning(f"Error unwrapping event: {e}")

            return events
        except Exception as e:
            log.error(f"Error reading stream {stream_key}: {e}")
            raise

    async def wait_for_event(
        self,
        event_type: str,
        predicate: Optional[Callable[[dict], bool]] = None,
        timeout: float = 15.0,
    ) -> dict:
        """
        Poll stream until an event matching predicate is found.

        Args:
            event_type: Event type name
            predicate: Optional filter function (returns True if event matches)
            timeout: Maximum wait time in seconds

        Returns:
            Unwrapped event payload dictionary

        Raises:
            TimeoutError: If no matching event found within timeout
        """
        stream_key = f"events:{event_type}"
        start_time = asyncio.get_event_loop().time()

        await self._ensure_consumer_group(stream_key)

        while True:
            try:
                # Poll with short block time for responsiveness
                messages = await self.redis.xreadgroup(
                    groupname=self.OBSERVER_GROUP,
                    consumername=f"observer-{id(self)}",
                    streams={stream_key: ">"},
                    count=10,
                    block=500,  # 500ms block
                )

                if messages:
                    for stream, message_list in messages:
                        for msg_id, msg_data in message_list:
                            try:
                                event = self._unwrap_envelope(msg_data)
                                if predicate is None or predicate(event):
                                    log.debug(f"✅ Found event: {event_type}")
                                    return event
                            except Exception as e:
                                log.warning(f"Error unwrapping event: {e}")

                # Check timeout
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout:
                    log.error(f"❌ Event not found within {timeout}s: {event_type}")
                    raise TimeoutError(
                        f"Event type {event_type} not found within {timeout}s"
                    )

            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.error(f"Error waiting for event {event_type}: {e}")
                raise

    async def drain(self, event_type: str) -> list[dict]:
        """
        Drain all pending messages from observer consumer group.

        Use for cleanup between tests.

        Args:
            event_type: Event type name

        Returns:
            List of drained event payloads
        """
        stream_key = f"events:{event_type}"

        try:
            await self._ensure_consumer_group(stream_key)

            # Read all pending messages
            events = []
            while True:
                messages = await self.redis.xreadgroup(
                    groupname=self.OBSERVER_GROUP,
                    consumername=f"observer-{id(self)}",
                    streams={stream_key: ">"},
                    count=100,
                    block=0,  # Non-blocking
                )

                if not messages:
                    break

                for stream, message_list in messages:
                    for msg_id, msg_data in message_list:
                        try:
                            event = self._unwrap_envelope(msg_data)
                            events.append(event)
                        except Exception:
                            pass

            log.debug(f"Drained {len(events)} events from {stream_key}")
            return events
        except Exception as e:
            log.warning(f"Error draining stream {stream_key}: {e}")
            return []

    async def delete_consumer_group(self, event_type: str) -> None:
        """
        Delete observer consumer group for cleanup.

        Args:
            event_type: Event type name
        """
        stream_key = f"events:{event_type}"

        try:
            await self.redis.xgroup_destroy(stream_key, self.OBSERVER_GROUP)
            self._created_groups.discard(stream_key)
            log.debug(f"Deleted consumer group for {stream_key}")
        except redis.exceptions.ResponseError:
            # Group doesn't exist, that's fine
            pass
        except Exception as e:
            log.warning(f"Error deleting consumer group: {e}")

    def _unwrap_envelope(self, msg_data: dict) -> dict:
        """
        Unwrap a Redis stream entry into a flat event dict for assertions.

        smarttrade_common.events.event_bus.publish writes entries like::

            xadd("events:<type>", {"event": json.dumps(envelope)})

        where ``envelope`` is::

            {event_id, event_type, timestamp, trace_id, payload: {...}}

        Tests assert against fields like ``order_id``/``side`` that live
        inside ``payload``. Return the payload dict merged with the envelope
        metadata so both shapes are accessible.
        """
        envelope: dict | None = None

        # Modern shape: single "event" field with a JSON-encoded envelope.
        if "event" in msg_data:
            raw = msg_data["event"]
            if isinstance(raw, str):
                try:
                    envelope = json.loads(raw)
                except json.JSONDecodeError:
                    return {"raw": raw}
            elif isinstance(raw, dict):
                envelope = raw

        # Legacy shape: a "payload" key directly on the entry.
        if envelope is None and "payload" in msg_data:
            payload_data = msg_data["payload"]
            if isinstance(payload_data, str):
                try:
                    return json.loads(payload_data)
                except json.JSONDecodeError:
                    return {"raw": payload_data}
            return payload_data if isinstance(payload_data, dict) else {"raw": payload_data}

        if envelope is None:
            return msg_data

        # Merge envelope-level fields with the inner payload so tests can
        # assert on either layer (`event_id`, `event_type`, `timestamp` from
        # the envelope; `order_id`, `side`, … from the payload).
        inner = envelope.get("payload") if isinstance(envelope, dict) else None
        if isinstance(inner, dict):
            merged = dict(inner)
            for k in ("event_id", "event_type", "timestamp", "trace_id", "version"):
                merged.setdefault(k, envelope.get(k))
            return merged
        return envelope

    async def get_stream_info(self, event_type: str) -> dict:
        """
        Get Redis stream info (for debugging).

        Args:
            event_type: Event type name

        Returns:
            Stream info dictionary
        """
        stream_key = f"events:{event_type}"

        try:
            info = await self.redis.xinfo_stream(stream_key)
            return info
        except Exception as e:
            log.warning(f"Error getting stream info for {stream_key}: {e}")
            return {}
