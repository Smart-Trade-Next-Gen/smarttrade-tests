"""
Scenario engine for YAML-driven E2E test scenarios.

Provides dataclasses for test scenarios and YAML loading capability.
Scenarios define order specifications, fill sequences, and expected outcomes.
"""

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Optional

import yaml

log = logging.getLogger(__name__)


@dataclass
class FillSpec:
    """Specification for a single fill in an order."""

    sequence: int  # Execution sequence number (1, 2, 3, ...)
    qty: int  # Fill quantity
    price: Decimal  # Fill price


@dataclass
class OrderScenario:
    """Specification for a single order in a scenario."""

    name: str
    instrument_id: str
    side: str  # BUY | SELL
    qty: int
    order_type: str  # MARKET | LIMIT | STOP | STOP_LIMIT
    position_type: str  # INTRADAY | OVERNIGHT
    fills: list[FillSpec]
    expected_status: str  # FILLED | CANCELLED | REJECTED
    expected_filled_qty: int
    underlying_symbol: str
    expected_avg_price: Optional[Decimal] = None
    price: Optional[Decimal] = None  # LIMIT price
    stop_price: Optional[Decimal] = None  # STOP price


@dataclass
class TestScenario:
    """Complete test scenario with multiple orders."""

    name: str
    description: str
    broker_id: str
    account_id: str
    orders: list[OrderScenario]
    concurrent: bool = False
    expected_positions_delta: int = 0
    expected_financial_invariant_checks: list[str] = field(default_factory=list)


class ScenarioEngine:
    """
    Scenario engine for loading and managing YAML-based test scenarios.
    """

    @staticmethod
    def load_scenario(scenario_file: Path) -> TestScenario:
        """
        Load a single scenario from YAML file.

        Args:
            scenario_file: Path to YAML scenario file

        Returns:
            TestScenario dataclass instance

        Raises:
            FileNotFoundError: If file not found
            ValueError: If YAML is invalid or required fields missing
        """
        scenario_file = Path(scenario_file)
        if not scenario_file.exists():
            raise FileNotFoundError(f"Scenario file not found: {scenario_file}")

        try:
            with open(scenario_file) as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {scenario_file}: {e}")

        if not data:
            raise ValueError(f"Empty scenario file: {scenario_file}")

        return ScenarioEngine._parse_scenario(data, scenario_file)

    @staticmethod
    def load_all_scenarios(scenario_dir: Path) -> dict[str, TestScenario]:
        """
        Load all scenarios from a directory.

        Args:
            scenario_dir: Path to directory containing YAML files

        Returns:
            Dictionary of scenario_name -> TestScenario
        """
        scenario_dir = Path(scenario_dir)
        if not scenario_dir.is_dir():
            raise ValueError(f"Scenario directory not found: {scenario_dir}")

        scenarios = {}
        for yaml_file in sorted(scenario_dir.glob("*.yaml")):
            if yaml_file.name.startswith("_"):
                continue  # Skip template files

            try:
                scenario = ScenarioEngine.load_scenario(yaml_file)
                scenarios[scenario.name] = scenario
                log.debug(f"Loaded scenario: {scenario.name} from {yaml_file.name}")
            except Exception as e:
                log.warning(f"Failed to load {yaml_file.name}: {e}")

        log.info(f"Loaded {len(scenarios)} scenarios from {scenario_dir}")
        return scenarios

    @staticmethod
    def _parse_scenario(data: dict, source: Optional[Path] = None) -> TestScenario:
        """
        Parse raw YAML data into TestScenario.

        Args:
            data: Parsed YAML data
            source: Source file (for error messages)

        Returns:
            TestScenario instance

        Raises:
            ValueError: If required fields missing or invalid
        """
        source_str = f" ({source})" if source else ""

        # Validate required fields
        required_fields = ["name", "description", "broker_id", "account_id", "orders"]
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Missing required field: {field}{source_str}")

        # Parse orders
        orders = []
        for order_data in data.get("orders", []):
            orders.append(ScenarioEngine._parse_order(order_data, source_str))

        # Create TestScenario
        scenario = TestScenario(
            name=data["name"],
            description=data["description"],
            broker_id=data["broker_id"],
            account_id=data["account_id"],
            orders=orders,
            concurrent=data.get("concurrent", False),
            expected_positions_delta=int(data.get("expected_positions_delta", 0)),
            expected_financial_invariant_checks=data.get(
                "expected_financial_invariants", []
            ),
        )

        log.debug(
            f"Parsed scenario: {scenario.name} with {len(orders)} orders{source_str}"
        )
        return scenario

    @staticmethod
    def _parse_order(data: dict, source_str: str = "") -> OrderScenario:
        """
        Parse order specification from YAML.

        Args:
            data: Order data dict
            source_str: Source for error messages

        Returns:
            OrderScenario instance

        Raises:
            ValueError: If required fields missing or invalid
        """
        # Validate required fields
        required_fields = [
            "name",
            "instrument_id",
            "side",
            "qty",
            "order_type",
            "position_type",
            "fills",
            "expected_status",
            "expected_filled_qty",
        ]
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Order missing required field: {field}{source_str}")

        # Parse fills
        fills = []
        for fill_data in data.get("fills", []):
            fill = FillSpec(
                sequence=int(fill_data["sequence"]),
                qty=int(fill_data["qty"]),
                price=Decimal(str(fill_data["price"])),
            )
            fills.append(fill)

        # Parse prices
        price = None
        if data.get("price"):
            price = Decimal(str(data["price"]))

        stop_price = None
        if data.get("stop_price"):
            stop_price = Decimal(str(data["stop_price"]))

        # Parse expected_avg_price
        expected_avg = None
        if data.get("expected_avg_price"):
            expected_avg = Decimal(str(data["expected_avg_price"]))

        order = OrderScenario(
            name=data["name"],
            instrument_id=data["instrument_id"],
            side=data["side"].upper(),
            qty=int(data["qty"]),
            order_type=data["order_type"].upper(),
            position_type=data["position_type"].upper(),
            fills=fills,
            expected_status=data["expected_status"].upper(),
            expected_filled_qty=int(data["expected_filled_qty"]),
            expected_avg_price=expected_avg,
            price=price,
            stop_price=stop_price,
        )

        log.debug(f"Parsed order: {order.name} | Type: {order.order_type}")
        return order

    @staticmethod
    def scenario_to_dict(scenario: TestScenario) -> dict:
        """
        Convert TestScenario back to dict (for serialization).

        Args:
            scenario: TestScenario instance

        Returns:
            Dictionary representation
        """
        return {
            "name": scenario.name,
            "description": scenario.description,
            "broker_id": scenario.broker_id,
            "account_id": scenario.account_id,
            "concurrent": scenario.concurrent,
            "expected_positions_delta": scenario.expected_positions_delta,
            "expected_financial_invariants": scenario.expected_financial_invariant_checks,
            "orders": [
                {
                    "name": order.name,
                    "instrument_id": order.instrument_id,
                    "side": order.side,
                    "qty": order.qty,
                    "order_type": order.order_type,
                    "position_type": order.position_type,
                    "price": str(order.price) if order.price else None,
                    "stop_price": str(order.stop_price) if order.stop_price else None,
                    "fills": [
                        {
                            "sequence": f.sequence,
                            "qty": f.qty,
                            "price": str(f.price),
                        }
                        for f in order.fills
                    ],
                    "expected_status": order.expected_status,
                    "expected_filled_qty": order.expected_filled_qty,
                    "expected_avg_price": str(order.expected_avg_price)
                    if order.expected_avg_price
                    else None,
                }
                for order in scenario.orders
            ],
        }
