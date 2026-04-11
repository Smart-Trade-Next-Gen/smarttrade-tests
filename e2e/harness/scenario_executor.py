"""
Scenario execution framework for end-to-end E2E testing.

Executes scenarios end-to-end: place orders, inject fills (INJECTION mode),
collect events, and return structured results for assertions.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from e2e.clients import BASClient, MockClient
from e2e.harness.event_collector import EventCollector
from e2e.harness.scenario_engine import TestScenario, OrderScenario

log = logging.getLogger(__name__)


@dataclass
class ScenarioResult:
    """Result of scenario execution."""

    # Execution data
    orders_placed: list = field(default_factory=list)
    events_collected: dict[str, list[dict]] = field(default_factory=dict)
    post_state: dict = field(default_factory=dict)
    execution_time: float = 0.0

    # Status tracking
    status: str = "SUCCESS"  # SUCCESS, ASSERTION_FAILURE, TIMEOUT, EXECUTION_FAILURE, INFRA_FAILURE
    failure_reason: Optional[str] = None

    def is_success(self) -> bool:
        """Check if scenario executed successfully."""
        return self.status == "SUCCESS"

    def __str__(self) -> str:
        """Human-readable result summary."""
        summary = f"ScenarioResult(status={self.status}, orders={len(self.orders_placed)}, "
        summary += f"events={sum(len(e) for e in self.events_collected.values())}, time={self.execution_time:.2f}s)"
        if self.failure_reason:
            summary += f"\n  Reason: {self.failure_reason}"
        return summary


class ScenarioExecutor:
    """
    Execute scenarios end-to-end with support for both INJECTION and REAL modes.

    INJECTION mode: Deterministic fill injection for testing without price-triggered execution.
    REAL mode: Mock's execution engine drives fills based on market conditions.
    """

    @staticmethod
    async def execute_scenario(
        scenario: TestScenario,
        bas_client: BASClient,
        mock_client: MockClient,
        event_collector: EventCollector,
        execution_mode: str = "INJECTION",
        timeout: float = 30.0,
    ) -> ScenarioResult:
        """
        Execute a scenario end-to-end.

        Args:
            scenario: TestScenario to execute
            bas_client: BASClient for order placement
            mock_client: MockClient for fill injection
            event_collector: EventCollector for event collection
            execution_mode: "INJECTION" (deterministic) or "REAL" (price-driven)
            timeout: Timeout for event collection per order

        Returns:
            ScenarioResult with execution details and status
        """
        result = ScenarioResult()
        start_time = time.time()

        try:
            # Phase 1: Place orders
            order_id_mapping = {}  # order_name -> broker_order_id

            if scenario.concurrent:
                # Concurrent placement (bounded by semaphore to limit memory)
                log.info(
                    f"Executing scenario '{scenario.name}' (CONCURRENT, mode={execution_mode})"
                )

                # Limit concurrent orders to 10 to avoid unbounded memory growth
                semaphore = asyncio.Semaphore(10)

                async def bounded_place_order(order):
                    async with semaphore:
                        return await ScenarioExecutor._place_order(
                            bas_client,
                            scenario.broker_id,
                            scenario.account_id,
                            order,
                        )

                tasks = [bounded_place_order(order) for order in scenario.orders]
                responses = await asyncio.gather(*tasks, return_exceptions=True)

                for i, order in enumerate(scenario.orders):
                    resp = responses[i]
                    if isinstance(resp, Exception):
                        log.error(f"Order placement failed: {order.name} - {resp}")
                        result.status = "EXECUTION_FAILURE"
                        result.failure_reason = f"Order placement failed: {order.name}"
                        result.execution_time = time.time() - start_time
                        return result

                    if resp:
                        order_id_mapping[order.name] = resp.broker_order_id
                        result.orders_placed.append(resp)
            else:
                # Sequential placement
                log.info(
                    f"Executing scenario '{scenario.name}' (SEQUENTIAL, mode={execution_mode})"
                )
                for order in scenario.orders:
                    try:
                        resp = await ScenarioExecutor._place_order(
                            bas_client,
                            scenario.broker_id,
                            scenario.account_id,
                            order,
                        )
                        if resp:
                            order_id_mapping[order.name] = resp.broker_order_id
                            result.orders_placed.append(resp)
                    except Exception as e:
                        log.error(f"Order placement failed: {order.name} - {e}")
                        result.status = "EXECUTION_FAILURE"
                        result.failure_reason = f"Order placement failed: {order.name}: {str(e)}"
                        result.execution_time = time.time() - start_time
                        return result

            # Phase 2: Execute fills (INJECTION mode only)
            if execution_mode.upper() == "INJECTION":
                for order in scenario.orders:
                    order_id = order_id_mapping.get(order.name)
                    if not order_id:
                        continue

                    try:
                        for fill in order.fills:
                            await mock_client.inject_fill(
                                scenario.broker_id,
                                scenario.account_id,
                                order_id,
                                sequence=fill.sequence,
                                fill_qty=fill.qty,
                                fill_price=fill.price,
                            )
                            log.debug(
                                f"Injected fill for {order.name}: seq={fill.sequence}, "
                                f"qty={fill.qty}, price={fill.price}"
                            )
                    except Exception as e:
                        log.error(f"Fill injection failed: {order.name} - {e}")
                        result.status = "EXECUTION_FAILURE"
                        result.failure_reason = f"Fill injection failed: {order.name}: {str(e)}"
                        result.execution_time = time.time() - start_time
                        return result

            # Phase 3: Collect events
            for order in scenario.orders:
                order_id = order_id_mapping.get(order.name)
                if not order_id:
                    continue

                try:
                    events = await event_collector.wait_for_completion(
                        order_id, timeout=timeout
                    )
                    result.events_collected[order.name] = events
                    log.debug(
                        f"Collected {len(events)} events for {order.name} ({order_id})"
                    )
                except asyncio.TimeoutError:
                    log.warning(f"Timeout waiting for completion: {order.name}")
                    result.status = "TIMEOUT"
                    result.failure_reason = (
                        f"Event collection timeout for {order.name} after {timeout}s"
                    )
                    result.execution_time = time.time() - start_time
                    return result
                except Exception as e:
                    log.error(f"Event collection failed: {order.name} - {e}")
                    result.status = "INFRA_FAILURE"
                    result.failure_reason = (
                        f"Event collection failed: {order.name}: {str(e)}"
                    )
                    result.execution_time = time.time() - start_time
                    return result

            # Phase 4: Capture post-state
            try:
                funds = await bas_client.get_funds(scenario.broker_id, scenario.account_id)
                positions = await bas_client.get_positions(
                    scenario.broker_id, scenario.account_id
                )
                trades = await bas_client.get_trades(scenario.broker_id, scenario.account_id)
                result.post_state = {
                    "funds": funds,
                    "positions": positions,
                    "trades": trades,
                }
            except Exception as e:
                log.warning(f"Failed to capture post-state: {e}")
                result.post_state = {}

            # Success!
            result.status = "SUCCESS"
            result.execution_time = time.time() - start_time
            log.info(
                f"Scenario executed successfully: {scenario.name} "
                f"({result.execution_time:.2f}s, {len(result.orders_placed)} orders)"
            )
            return result

        except Exception as e:
            log.error(f"Scenario execution failed: {str(e)}")
            result.status = "INFRA_FAILURE"
            result.failure_reason = f"Unexpected error: {str(e)}"
            result.execution_time = time.time() - start_time
            return result

    @staticmethod
    async def _place_order(
        bas_client: BASClient,
        broker_id: str,
        account_id: str,
        order: OrderScenario,
    ):
        """
        Place a single order via BAS client.

        Args:
            bas_client: BASClient instance
            broker_id: Broker ID
            account_id: Account ID
            order: OrderScenario to place

        Returns:
            BasOrderPlaceResponse or None

        Raises:
            Exception on placement failure
        """
        # Convert OrderScenario to BasOrderPlaceRequest
        from broker_adapter_service.schemas.order_dtos import (
            BasOrderPlaceRequest,
            BasOrderLeg,
        )
        from smarttrade_common.schemas.types import (
            OrderSide,
            OrderType,
            TimeInForce,
            PositionType,
            ExecutionIntent,
            ProtectionType,
            TriggerType,
        )

        # Build leg
        leg = BasOrderLeg(
            instrument_id=order.instrument_id,
            instrument_type="EQ",  # Equity
            side=OrderSide(order.side),
            qty=order.qty,
            order_type=OrderType(order.order_type),
            price=order.price,
            stop_price=order.stop_price,
            ltp=Decimal(
                "100.00"
            ),  # Dummy LTP, not used in Mock
        )

        # Build request
        request = BasOrderPlaceRequest(
            client_order_id=f"{order.name}_{int(time.time()*1000)}",
            position_type=PositionType(order.position_type),
            legs=[leg],
            underlying_instrument_id=order.instrument_id,
            tif=TimeInForce.DAY,
        )

        log.debug(f"Placing order: {order.name} ({request.client_order_id})")
        responses = await bas_client.place_order(broker_id, account_id, request)

        if not responses:
            raise ValueError(f"No response from BAS for order: {order.name}")

        # BAS returns list of responses, we take first one
        resp = responses[0]
        log.info(
            f"Order placed: {order.name} -> {resp.broker_order_id} (status={resp.status})"
        )
        return resp
