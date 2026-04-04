"""E2E test harness components (async event collection, assertions, lifecycle)."""

from e2e.harness.event_collector import EventCollector, TERMINAL_STATUSES
from e2e.harness.assertions import AssertionEngine, AssertionError
from e2e.harness.scenario_engine import (
    ScenarioEngine,
    TestScenario,
    OrderScenario,
    FillSpec,
)
from e2e.harness.scenario_executor import ScenarioExecutor, ScenarioResult

__all__ = [
    "EventCollector",
    "TERMINAL_STATUSES",
    "AssertionEngine",
    "AssertionError",
    "ScenarioEngine",
    "TestScenario",
    "OrderScenario",
    "FillSpec",
    "ScenarioExecutor",
    "ScenarioResult",
]
