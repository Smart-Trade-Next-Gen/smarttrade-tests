"""
Async event collector for E2E testing.

Collects events from services (MDS WebSocket, order/trade/position updates) using per-order
asyncio.Queue for signaling. Provides async wait operations with timeout support and
event filtering capabilities. Implements ring-buffer overflow handling.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

log = logging.getLogger(__name__)

# Terminal order statuses
TERMINAL_STATUSES = {"FILLED", "CANCELLED", "REJECTED", "EXPIRED", "COMPLETED"}


class EventCollector:
    """
    Async event collector using per-order asyncio.Queue.

    Collects events in chronological order, supports filtering, and provides
    async wait operations with timeout. Implements ring-buffer overflow handling
    to prevent memory issues in long-running tests.
    """

    def __init__(self, maxsize: int = 1000):
        """
        Initialize EventCollector.

        Args:
            maxsize: Maximum queue size per order (default: 1000)
        """
        self.maxsize = maxsize
        self.queues: dict[str, asyncio.Queue] = {}
        self.events: dict[str, list[dict]] = {}
        self.dropped_events_counts: dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def add_event(self, order_id: str, event: dict) -> None:
        """
        Add an event for an order.

        Events are stored in chronological order and put into a queue for
        async waiting. If queue is full, oldest events are dropped and
        a warning is logged.

        Args:
            order_id: Order ID
            event: Event dictionary with type, timestamp, data, etc.
        """
        async with self._lock:
            # Initialize queue and events list if needed
            if order_id not in self.queues:
                self.queues[order_id] = asyncio.Queue(maxsize=self.maxsize)
                self.events[order_id] = []
                self.dropped_events_counts[order_id] = 0

            # Append to chronological event log (primary source of truth)
            self.events[order_id].append(event)

            # Try to put event in queue for waiting
            try:
                self.queues[order_id].put_nowait(event)
            except asyncio.QueueFull:
                # Ring-buffer overflow: drop oldest event from queue
                try:
                    dropped = self.queues[order_id].get_nowait()
                    self.dropped_events_counts[order_id] += 1
                    log.warning(
                        f"EventCollector overflow for order_id={order_id}; "
                        f"dropped event {dropped.get('type', 'unknown')} | "
                        f"total dropped: {self.dropped_events_counts[order_id]}"
                    )
                except asyncio.QueueEmpty:
                    pass

                # Retry put
                try:
                    self.queues[order_id].put_nowait(event)
                except asyncio.QueueFull:
                    log.error(
                        f"EventCollector: Failed to add event for order_id={order_id} "
                        f"even after dropping"
                    )

    async def wait_for_status(
        self,
        order_id: str,
        status: str,
        timeout: float = 30.0,
    ) -> list[dict]:
        """
        Wait for order to reach a specific status.

        Args:
            order_id: Order ID
            status: Status to wait for
            timeout: Maximum wait time in seconds

        Returns:
            List of events collected up to and including the status change

        Raises:
            TimeoutError: If status not reached within timeout
            ValueError: If order_id not found
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            # Check current events
            events = self.get_events(order_id)
            for event in reversed(events):
                if event.get("status") == status or event.get("data", {}).get("status") == status:
                    return events

            # Check timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                raise TimeoutError(
                    f"Status {status} not reached for order_id={order_id} within {timeout}s"
                )

            # Wait for next event
            try:
                if order_id not in self.queues:
                    await asyncio.sleep(0.1)
                    continue

                remaining_timeout = timeout - elapsed
                await asyncio.wait_for(
                    self.queues[order_id].get(),
                    timeout=remaining_timeout,
                )
            except asyncio.TimeoutError:
                raise TimeoutError(
                    f"Status {status} not reached for order_id={order_id} within {timeout}s"
                )

    async def wait_for_completion(
        self,
        order_id: str,
        timeout: float = 30.0,
    ) -> list[dict]:
        """
        Wait for order to reach terminal status.

        Terminal statuses: FILLED, CANCELLED, REJECTED, EXPIRED, COMPLETED

        Args:
            order_id: Order ID
            timeout: Maximum wait time in seconds

        Returns:
            List of all events for the order

        Raises:
            TimeoutError: If terminal status not reached within timeout
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            # Check current events
            events = self.get_events(order_id)
            for event in reversed(events):
                event_status = (
                    event.get("status")
                    or event.get("data", {}).get("status")
                    or event.get("order_status")
                )
                if event_status in TERMINAL_STATUSES:
                    log.debug(
                        f"Order reached terminal status | order_id={order_id} | "
                        f"status={event_status} | events={len(events)}"
                    )
                    return events

            # Check timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                raise TimeoutError(
                    f"Terminal status not reached for order_id={order_id} within {timeout}s. "
                    f"Last status: {events[-1].get('status', 'unknown') if events else 'N/A'}"
                )

            # Wait for next event
            try:
                if order_id not in self.queues:
                    await asyncio.sleep(0.1)
                    continue

                remaining_timeout = timeout - elapsed
                await asyncio.wait_for(
                    self.queues[order_id].get(),
                    timeout=remaining_timeout,
                )
            except asyncio.TimeoutError:
                raise TimeoutError(
                    f"Terminal status not reached for order_id={order_id} within {timeout}s"
                )

    def get_events(self, order_id: str) -> list[dict]:
        """
        Get all events for an order.

        Returns the complete chronological event history (primary source of truth).

        Args:
            order_id: Order ID

        Returns:
            List of events in chronological order
        """
        return self.events.get(order_id, [])

    def get_events_by_type(self, order_id: str, event_type: str) -> list[dict]:
        """
        Filter events by type.

        Args:
            order_id: Order ID
            event_type: Event type to filter (e.g., "order.placed", "order.filled")

        Returns:
            List of events matching the type
        """
        events = self.get_events(order_id)
        return [e for e in events if e.get("type") == event_type]

    def get_event_count(self, order_id: str) -> int:
        """
        Get count of events for an order.

        Args:
            order_id: Order ID

        Returns:
            Number of events
        """
        return len(self.get_events(order_id))

    def get_dropped_count(self, order_id: str) -> int:
        """
        Get count of dropped events due to overflow.

        Args:
            order_id: Order ID

        Returns:
            Number of dropped events
        """
        return self.dropped_events_counts.get(order_id, 0)

    async def clear_completed_orders(self, terminal_orders: list[str]) -> None:
        """
        Clear events for orders that have reached terminal status.

        This is called after test completes to free memory from completed orders.
        Use this to prevent memory accumulation across multiple orders in a single test.

        Args:
            terminal_orders: List of order IDs that have completed
        """
        async with self._lock:
            for order_id in terminal_orders:
                if order_id in self.events:
                    size_before = len(self.events[order_id])
                    self.events.pop(order_id, None)
                    self.dropped_events_counts.pop(order_id, None)
                    # Don't clear queue to avoid race conditions with waiting tasks
                    log.debug(f"Cleared {size_before} events for completed order_id={order_id}")

    def clear(self, order_id: Optional[str] = None) -> None:
        """
        Clear events for an order or all orders (blocking version).

        Args:
            order_id: Order ID to clear (if None, clears all)
        """
        if order_id:
            self.events.pop(order_id, None)
            self.dropped_events_counts.pop(order_id, None)
            # Note: Don't clear queue as it may have waiting tasks
            log.debug(f"Cleared events for order_id={order_id}")
        else:
            self.events.clear()
            self.dropped_events_counts.clear()
            log.debug("Cleared all events")

    def get_summary(self, order_id: str) -> dict:
        """
        Get summary of events for an order.

        Args:
            order_id: Order ID

        Returns:
            Dictionary with counts and final status
        """
        events = self.get_events(order_id)
        if not events:
            return {
                "order_id": order_id,
                "event_count": 0,
                "dropped_count": 0,
                "final_status": None,
                "first_event_time": None,
                "last_event_time": None,
            }

        final_event = events[-1]
        final_status = (
            final_event.get("status")
            or final_event.get("data", {}).get("status")
            or final_event.get("order_status")
        )

        return {
            "order_id": order_id,
            "event_count": len(events),
            "dropped_count": self.get_dropped_count(order_id),
            "final_status": final_status,
            "first_event_time": events[0].get("timestamp"),
            "last_event_time": events[-1].get("timestamp"),
            "event_types": list(set(e.get("type") for e in events if e.get("type"))),
        }

    async def wait_for_event_type(
        self,
        order_id: str,
        event_type: str,
        timeout: float = 30.0,
    ) -> dict:
        """
        Wait for a specific event type.

        Args:
            order_id: Order ID
            event_type: Event type to wait for
            timeout: Maximum wait time in seconds

        Returns:
            The first event of the specified type

        Raises:
            TimeoutError: If event type not received within timeout
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            # Check current events
            matching = self.get_events_by_type(order_id, event_type)
            if matching:
                return matching[0]

            # Check timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                raise TimeoutError(
                    f"Event type {event_type} not received for order_id={order_id} "
                    f"within {timeout}s"
                )

            # Wait for next event
            try:
                if order_id not in self.queues:
                    await asyncio.sleep(0.1)
                    continue

                remaining_timeout = timeout - elapsed
                await asyncio.wait_for(
                    self.queues[order_id].get(),
                    timeout=remaining_timeout,
                )
            except asyncio.TimeoutError:
                raise TimeoutError(
                    f"Event type {event_type} not received for order_id={order_id} "
                    f"within {timeout}s"
                )
