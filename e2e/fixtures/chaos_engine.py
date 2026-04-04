"""
Chaos testing fixture for injecting failures and observing recovery.

Enables resilience testing by simulating:
- Network failures (timeouts, connection drops)
- Service degradation (slow responses, partial failures)
- Data inconsistencies (duplicate/missing events)
- Resource exhaustion (memory pressure, thread pool saturation)

Uses context managers to scope failure injection and automatic cleanup.
"""

import asyncio
import logging
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional, Callable, Any, List

log = logging.getLogger(__name__)


class FailureMode(Enum):
    """Types of failures that can be injected."""
    TIMEOUT = "timeout"  # Request times out
    CONNECTION_REFUSED = "connection_refused"  # Cannot connect
    SERVICE_UNAVAILABLE = "service_unavailable"  # 503 Service Unavailable
    PARTIAL_FAILURE = "partial_failure"  # Only some requests fail
    SLOW_RESPONSE = "slow_response"  # Artificially slow responses
    DUPLICATE_EVENT = "duplicate_event"  # Event delivered twice
    MISSING_EVENT = "missing_event"  # Event not delivered
    OUT_OF_ORDER = "out_of_order"  # Events in wrong sequence
    RESOURCE_EXHAUSTION = "resource_exhaustion"  # Memory/CPU pressure


@dataclass
class ChaosConfig:
    """Configuration for chaos injection."""
    mode: FailureMode
    duration_ms: int = 1000  # How long to inject the failure
    affected_service: str = "mock"  # Which service to target (mock, bas, mds)
    failure_rate: float = 1.0  # 0-1: what % of requests fail
    delay_ms: int = 0  # Additional delay to add
    recovery_time_ms: int = 500  # Time to attempt recovery after failure


class ChaosEngine:
    """
    Orchestrates chaos injection and recovery monitoring.

    Usage:
        async with chaos_engine.inject(
            ChaosConfig(
                mode=FailureMode.TIMEOUT,
                duration_ms=2000,
                affected_service="mock",
            )
        ):
            # Within this block, mock service requests timeout
            # Test resilience and recovery
            ...
        # After exiting, failure is auto-cleaned up
    """

    def __init__(self):
        """Initialize chaos engine."""
        self._active_failures: List[ChaosConfig] = []
        self._failure_counts = {}  # Track how many times each failure was triggered
        self._recovery_attempts = {}  # Track recovery attempts

    async def inject(self, config: ChaosConfig):
        """
        Context manager for scoped failure injection.

        Args:
            config: ChaosConfig specifying the failure mode

        Yields:
            Self (for introspection during failure)
        """
        self._active_failures.append(config)
        self._failure_counts[config.mode.value] = 0
        self._recovery_attempts[config.mode.value] = 0

        log.info(
            f"🔴 Chaos injected | Mode: {config.mode.value} | "
            f"Service: {config.affected_service} | Duration: {config.duration_ms}ms"
        )

        try:
            yield self

            # Auto-cleanup: wait for failure duration then remove
            await asyncio.sleep(config.duration_ms / 1000.0)

        finally:
            self._active_failures.remove(config)
            log.info(
                f"🟢 Chaos cleared | Mode: {config.mode.value} | "
                f"Failures triggered: {self._failure_counts.get(config.mode.value, 0)} | "
                f"Recovery attempts: {self._recovery_attempts.get(config.mode.value, 0)}"
            )

    async def simulate_timeout(self, service: str, delay_ms: int = 6000) -> None:
        """
        Simulate service timeout (request hangs longer than timeout).

        Args:
            service: Service name (mock, bas, mds)
            delay_ms: How long to hang the request
        """
        config = ChaosConfig(
            mode=FailureMode.TIMEOUT,
            duration_ms=delay_ms,
            affected_service=service,
        )
        async with self.inject(config):
            yield

    async def simulate_service_unavailable(self, service: str, duration_ms: int = 3000) -> None:
        """
        Simulate service returning 503 Service Unavailable.

        Args:
            service: Service name
            duration_ms: How long service is down
        """
        config = ChaosConfig(
            mode=FailureMode.SERVICE_UNAVAILABLE,
            duration_ms=duration_ms,
            affected_service=service,
        )
        async with self.inject(config):
            yield

    async def simulate_partial_failure(
        self,
        service: str,
        failure_rate: float = 0.5,
        duration_ms: int = 2000,
    ) -> None:
        """
        Simulate partial failure (random requests fail).

        Args:
            service: Service name
            failure_rate: Fraction of requests that fail (0-1)
            duration_ms: How long to inject failures
        """
        config = ChaosConfig(
            mode=FailureMode.PARTIAL_FAILURE,
            affected_service=service,
            failure_rate=failure_rate,
            duration_ms=duration_ms,
        )
        async with self.inject(config):
            yield

    async def simulate_slow_response(
        self,
        service: str,
        added_delay_ms: int = 3000,
        duration_ms: int = 5000,
    ) -> None:
        """
        Simulate degraded performance (all responses slow).

        Args:
            service: Service name
            added_delay_ms: Additional delay to add to all requests
            duration_ms: How long to degrade performance
        """
        config = ChaosConfig(
            mode=FailureMode.SLOW_RESPONSE,
            affected_service=service,
            delay_ms=added_delay_ms,
            duration_ms=duration_ms,
        )
        async with self.inject(config):
            yield

    async def simulate_duplicate_event(
        self,
        order_id: str,
        event_type: str = "order_fill",
        duplicate_count: int = 1,
    ) -> None:
        """
        Simulate duplicate event delivery.

        Args:
            order_id: Order ID to duplicate events for
            event_type: Type of event to duplicate
            duplicate_count: How many duplicates to inject
        """
        config = ChaosConfig(
            mode=FailureMode.DUPLICATE_EVENT,
            duration_ms=100,  # Brief injection
        )
        async with self.inject(config):
            log.warning(
                f"Injecting {duplicate_count} duplicate events | "
                f"Order: {order_id} | Type: {event_type}"
            )
            yield

    async def simulate_missing_event(
        self,
        order_id: str,
        event_type: str = "position_updated",
        drop_count: int = 1,
    ) -> None:
        """
        Simulate missing/dropped events.

        Args:
            order_id: Order ID to drop events for
            event_type: Type of event to drop
            drop_count: How many events to drop
        """
        config = ChaosConfig(
            mode=FailureMode.MISSING_EVENT,
            duration_ms=100,
        )
        async with self.inject(config):
            log.warning(
                f"Injecting {drop_count} missing events | "
                f"Order: {order_id} | Type: {event_type}"
            )
            yield

    async def simulate_out_of_order_events(
        self,
        order_id: str,
        event_count: int = 2,
    ) -> None:
        """
        Simulate out-of-order event delivery.

        Args:
            order_id: Order ID to disorder events for
            event_count: How many events to reorder
        """
        config = ChaosConfig(
            mode=FailureMode.OUT_OF_ORDER,
            duration_ms=200,
        )
        async with self.inject(config):
            log.warning(
                f"Injecting out-of-order events | "
                f"Order: {order_id} | Affected events: {event_count}"
            )
            yield

    async def simulate_resource_exhaustion(
        self,
        resource_type: str = "memory",  # memory, threads, connections
        duration_ms: int = 3000,
    ) -> None:
        """
        Simulate resource exhaustion.

        Args:
            resource_type: Type of resource (memory, threads, connections)
            duration_ms: How long to exhaust resource
        """
        config = ChaosConfig(
            mode=FailureMode.RESOURCE_EXHAUSTION,
            duration_ms=duration_ms,
        )
        async with self.inject(config):
            log.warning(f"Exhausting {resource_type} resources for {duration_ms}ms")
            yield

    def record_failure(self, failure_mode: FailureMode) -> None:
        """Record that a failure was triggered."""
        self._failure_counts[failure_mode.value] = self._failure_counts.get(failure_mode.value, 0) + 1

    def record_recovery_attempt(self, failure_mode: FailureMode) -> None:
        """Record that recovery was attempted."""
        self._recovery_attempts[failure_mode.value] = self._recovery_attempts.get(failure_mode.value, 0) + 1

    def get_failure_stats(self) -> dict:
        """Get statistics about injected failures."""
        return {
            "active_failures": len(self._active_failures),
            "failure_counts": self._failure_counts.copy(),
            "recovery_attempts": self._recovery_attempts.copy(),
            "active_modes": [f.mode.value for f in self._active_failures],
        }

    def reset(self) -> None:
        """Reset all chaos state (use between tests)."""
        self._active_failures.clear()
        self._failure_counts.clear()
        self._recovery_attempts.clear()
        log.debug("Chaos engine reset")
