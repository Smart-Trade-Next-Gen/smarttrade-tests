# SmartTrade E2E Testing Framework — Implementation Task Breakdown

**Date:** 2026-04-04  
**Status:** Ready for Team Execution  
**Total Effort:** ~120-140 engineering hours across 9 phases  
**Target Timeline:** 6-8 weeks (with parallel execution)  

---

## CRITICAL POLICY: Mock Behaves as Real Broker

### NEW (v3): Execution Mode Policy

**Foundational Constraint**: Mock Service MUST behave like a real broker in all E2E tests.

This ensures tests validate realistic execution behavior, not artificial shortcuts.

**Two Execution Modes:**

1. **REAL Mode (Default, Mandatory for E2E)**
   - Execution driven **ONLY** by market conditions (price feed)
   - Mock execution engine evaluates order type rules (LIMIT, STOP, MARKET)
   - Mock triggers fills when conditions are met
   - Tests **MUST NOT** manually trigger execution
   - Tests validate full chain: Mock → BAS → MDS → Client
   - Used in CI and primary E2E suite

2. **INJECTION Mode (Restricted, Debug-Only)**
   - Direct execution injection via `inject_fill()`
   - Used **ONLY** for isolated unit testing or debugging
   - **FORBIDDEN in E2E tests**
   - **EXCLUDED from CI**

### Strict Rules

- ❌ `inject_fill()` is **FORBIDDEN** in REAL mode
- ✅ Tests **MUST** define market conditions (price sequences) instead of execution events
- ✅ Tests **MUST** validate price-triggered execution correctness
- ✅ Mock **MUST** be treated as external broker, not test helper
- ✅ BAS is the only execution authority for orders

### Developer Guardrails

Runtime checks:
```python
# In MockClient
if execution_mode == 'REAL':
    if inject_fill_called:
        raise RuntimeError("inject_fill() forbidden in REAL mode")
```

Code checks:
- Lint rule to flag `inject_fill()` usage in E2E test files
- CI check to ensure REAL mode tests only

---

## 1. Phase-wise Task Breakdown

| Phase | Tasks | Duration | Priority | Blocking |
|-------|-------|----------|----------|----------|
| Foundation Setup | E2E-001, E2E-002, E2E-003 | 1-2 days | P0 | All downstream |
| Client Layer | E2E-010, E2E-011, E2E-012, E2E-013 | 3-4 days | P0 | Harness, Tests |
| Core Test Harness | E2E-020, E2E-021, E2E-022, E2E-023 | 3-4 days | P0 | Tests |
| Scenario Engine | E2E-030, E2E-031 | 2-3 days | P0 | All tests |
| Injection Mode Tests | E2E-040, E2E-041, E2E-042 | 4-5 days | P1 | Injection validation |
| Real Execution Mode | E2E-050, E2E-051 | 3-4 days | P1 | Real execution validation |
| Resilience & Chaos | E2E-060, E2E-061, E2E-062 | 3-4 days | P1 | Chaos validation |
| Observability | E2E-070, E2E-071, E2E-072 | 2-3 days | P2 | Debugging, CI reporting |
| CI/CD Integration | E2E-080, E2E-081, E2E-082 | 2-3 days | P0 | Production readiness |

---

## 2. Detailed Task List

### PHASE 1: FOUNDATION SETUP

#### E2E-001: Create e2e/ Directory Structure & Python Package

**Phase:** Foundation Setup  
**Priority:** P0 — Blocks all downstream work  
**Dependencies:** None  
**Estimated Effort:** 1.5 hours  

**Description:**
Initialize the e2e/ module as a self-contained Python package within smarttrade-tests. Set up directory hierarchy, `__init__.py` files, and basic configuration.

**Implementation Steps:**
1. Create directories:
   - `e2e/clients/`
   - `e2e/harness/`
   - `e2e/scenarios/`
   - `e2e/tests/`
   - `e2e/config/`
   - `e2e/fixtures/`
2. Create `__init__.py` in each package
3. Create base `conftest.py` (will be filled in E2E-023)
4. Create `pytest.ini` with:
   ```ini
   [pytest]
   asyncio_mode = auto
   testpaths = tests
   python_files = test_*.py
   markers =
       smoke: quick sanity tests
       injection: deterministic injection mode
       real_execution: real execution mode
       resilience: network failures
       chaos: chaos testing
   ```

**Acceptance Criteria:**
- ✅ Directory structure matches design doc
- ✅ All `__init__.py` files present
- ✅ pytest.ini correctly configured
- ✅ `pytest --collect-only` discovers no tests yet (expected)
- ✅ Can import from `e2e.clients`, `e2e.harness` in Python

**Edge Cases:**
- Windows path separators (use `pathlib.Path`)
- Python import path issues (verify `PYTHONPATH` includes e2e/)

**Files/Modules Impacted:**
```
smarttrade-tests/
└── e2e/
    ├── __init__.py
    ├── pytest.ini
    ├── conftest.py (base)
    ├── clients/ (__init__.py)
    ├── harness/ (__init__.py)
    ├── scenarios/ (__init__.py)
    ├── tests/ (__init__.py, conftest.py)
    ├── config/ (__init__.py)
    └── fixtures/ (__init__.py)
```

---

#### E2E-002: Implement Config System (Environment-Based)

**Phase:** Foundation Setup  
**Priority:** P0 — Blocks all clients and tests  
**Dependencies:** E2E-001  
**Estimated Effort:** 2 hours  

**Description:**
Build configuration system that supports dev/staging/prod environments. Config must be loaded from environment variables and/or YAML files. Must support both localhost (dev) and remote URLs (staging).

**Implementation Steps:**
1. Create `e2e/config/config.py`:
   ```python
   @dataclass
   class TestConfig:
       env: str
       bas_url: str
       mds_ws_url: str
       mock_url: str
       auth_url: str
       test_user: str
       test_password: str
       broker_id: str
       account_id: str
       timeout_fast: float = 5.0
       timeout_medium: float = 10.0
       timeout_slow: float = 30.0
       
       @staticmethod
       def from_env() -> TestConfig:
           # Load from environment
   ```
2. Create `e2e/config/dev.yaml` with localhost URLs
3. Create `e2e/config/staging.yaml` with placeholder staging URLs
4. Support override via environment variables:
   - `E2E_ENV` (dev|staging|prod)
   - `E2E_BAS_URL`, `E2E_MDS_URL`, etc.
   - `E2E_TIMEOUT_FAST`, `E2E_TIMEOUT_MEDIUM`, `E2E_TIMEOUT_SLOW`
5. Create `conftest.py` fixture:
   ```python
   @pytest.fixture(scope="session")
   def config() -> TestConfig:
       return TestConfig.from_env()
   ```

**Acceptance Criteria:**
- ✅ Config loads from env vars
- ✅ Config falls back to YAML files
- ✅ All required URLs and timeouts present
- ✅ Dev config points to localhost
- ✅ Can override individual settings via env
- ✅ pytest fixture `config` available in all tests

**Edge Cases:**
- Missing environment variables (provide sensible defaults)
- YAML file not found (fall back to hardcoded defaults)
- Invalid timeout values (validate and raise clear error)

**Files/Modules Impacted:**
```
e2e/config/
├── __init__.py
├── config.py
├── dev.yaml
└── staging.yaml

e2e/conftest.py (fixture: config)
```

---

#### E2E-003: Create Base Test Utilities & Logging

**Phase:** Foundation Setup  
**Priority:** P0 — Required for debugging and CI  
**Dependencies:** E2E-002  
**Estimated Effort:** 1.5 hours  

**Description:**
Set up logging infrastructure, test utilities, and helper functions. Ensure all logs include correlation IDs (order_id) for traceability.

**Implementation Steps:**
1. Create `e2e/fixtures/logging.py`:
   - Configure pytest logging with correlation ID support
   - Log format: `timestamp | service | order_id | event | message`
   - Set log levels: DEBUG in dev, INFO in staging
2. Create `e2e/fixtures/helpers.py`:
   - `unique_account_id(test_id: str) -> str` — generates unique per-test account
   - `correlation_id_logger(order_id: str) -> Logger` — logger with order_id context
3. Create `e2e/fixtures/test_data.py`:
   - Instrument IDs: `INSTRUMENTS = {"SBIN": "INSTR_NSE_SBIN_EQ", ...}`
   - Standard prices: `PRICES = {"SBIN": Decimal("150.50"), ...}`
   - Standard quantities: `QUANTITIES = {"small": 50, "medium": 100, ...}`
4. Update `conftest.py` with logging configuration

**Acceptance Criteria:**
- ✅ Logs include order_id in every message
- ✅ Can filter logs by order_id
- ✅ Test data available via imports
- ✅ Unique account IDs generated per test
- ✅ No hardcoded values in test files

**Edge Cases:**
- Concurrent tests writing logs (ensure thread-safe logging)
- Log rotation (handle large test runs)
- Missing order_id (use placeholder "N/A")

**Files/Modules Impacted:**
```
e2e/fixtures/
├── logging.py
├── helpers.py
└── test_data.py

e2e/conftest.py (logging setup)
```

---

### PHASE 2: CLIENT LAYER

#### E2E-010: Implement BASClient (REST HTTP Client)

**Phase:** Client Layer  
**Priority:** P0 — Core dependency  
**Dependencies:** E2E-002  
**Estimated Effort:** 4 hours  

**Description:**
Build async REST client for BAS endpoints. Must support order placement, modification, cancellation, and portfolio queries. All responses must be typed (Pydantic models from smarttrade-common).

**Implementation Steps:**
1. Create `e2e/clients/bas_client.py`:
   ```python
   class BASClient:
       def __init__(self, base_url: str, token: str, timeout: float = 10.0)
       
       async def place_order(broker_id, account_id, request) -> list[BasOrderPlaceResponse]
       async def modify_order(broker_id, account_id, broker_order_id, request) -> BasOrderModifyResponse
       async def cancel_order(broker_id, account_id, broker_order_id) -> BasCancelOrderResponse
       async def get_order(broker_id, account_id, broker_order_id) -> Order
       async def get_orders(broker_id, account_id) -> list[Order]
       async def get_trades(broker_id, account_id) -> list[Trade]
       async def get_funds(broker_id, account_id) -> FundsResponse
       async def get_positions(broker_id, account_id) -> list[Position]
   ```
2. Use `httpx.AsyncClient` with connection pooling
3. Auto-inject Bearer token in all requests
4. Auto-generate idempotency key for POST /orders
5. Return Pydantic models (imported from smarttrade-common)
6. Raise `httpx.HTTPError` on non-2xx status

**Acceptance Criteria:**
- ✅ All methods async
- ✅ Bearer token auto-injected
- ✅ Idempotency key auto-generated
- ✅ Responses are Pydantic models
- ✅ Can be used as context manager (`async with BASClient(...) as client`)
- ✅ Timeout defaults to 10s, configurable
- ✅ Connection pooling enabled

**Edge Cases:**
- Network timeout (propagate as exception)
- Invalid response body (Pydantic parsing fails; raise ValidationError)
- 4xx errors (raise HTTPError with details)
- Missing token (raise ValueError)

**Files/Modules Impacted:**
```
e2e/clients/
├── __init__.py (export BASClient)
└── bas_client.py
```

---

#### E2E-011: Implement MDSWebSocketClient (WebSocket Streaming)

**Phase:** Client Layer  
**Priority:** P0 — Core dependency  
**Dependencies:** E2E-002  
**Estimated Effort:** 5 hours  

**Description:**
Build async WebSocket client for MDS. Must handle connection lifecycle, auto-reconnect, heartbeats, subscriptions, and message streaming. Critical for event-driven architecture.

**Implementation Steps:**
1. Create `e2e/clients/mds_client.py`:
   ```python
   class MDSWebSocketClient:
       async def connect() -> None
       async def disconnect() -> None
       async def subscribe_account(account_id: str) -> None
       async def wait_connected(timeout: float = 5.0) -> None
       async def stream_events() -> AsyncIterator[dict]
   ```
2. Use `websockets.asyncio.client.connect()` with 30s timeout
3. Send heartbeat responses every 5s (MDS sends first)
4. Auto-reconnect with exponential backoff (1s, 2s, 4s, 8s, max 30s)
5. Reader loop: pump messages into EventCollector (via injected dependency)
6. Message routing:
   - Filter heartbeats, acks, system messages
   - Route order/trade/position updates to EventCollector by order_id
7. Exception handling: wrap connection errors, log and reconnect

**Acceptance Criteria:**
- ✅ Connects to MDS WebSocket
- ✅ Receives and validates `system.connected` message
- ✅ Auto-responds to heartbeats
- ✅ Auto-reconnects on disconnect
- ✅ Can subscribe to account
- ✅ Streams events correctly
- ✅ Can be used with `async with` or explicit disconnect
- ✅ Concurrent connections handled (oldest closed on new connection from same user)

**Edge Cases:**
- Network timeout (auto-reconnect)
- Malformed JSON (skip message, log warning)
- Out-of-order subscriptions (validate state)
- Rapid reconnects (respect backoff)
- Event loss on reconnect (rely on EventCollector replay logic)

**Files/Modules Impacted:**
```
e2e/clients/
├── __init__.py (export MDSWebSocketClient)
└── mds_client.py
```

---

#### E2E-012: Implement MockClient (Deterministic Fill Injection)

**Phase:** Client Layer  
**Priority:** P0 — Core dependency for injection mode  
**Dependencies:** E2E-002  
**Estimated Effort:** 3 hours  

**Description:**
Build REST client for Mock service's execution injection endpoint. Enable deterministic fill injection for testing without relying on price-triggered execution.

**Implementation Steps:**
1. Create `e2e/clients/mock_client.py`:
   ```python
   class MockClient:
       async def inject_fill(
           broker_id, account_id, order_id, sequence, fill_qty, fill_price
       ) -> ExecutionResult
       
       async def inject_fills_sequence(
           broker_id, account_id, order_id, fills: list[tuple[int, Decimal]]
       ) -> None
   ```
2. Single endpoint: `POST /api/v1/execute/{broker_id}/{account_id}`
3. Request body: `{"order_id": str, "sequence": int, "fill_qty": int, "fill_price": str}`
4. Response: `ExecutionResult` with order_id, status, filled_qty, remaining_qty, timestamp
5. Validate sequence monotonicity (enforce sequence >= 1, increasing per order_id)
6. Auto-convert Decimal to string for JSON serialization

**Acceptance Criteria:**
- ✅ Inject single fill
- ✅ Inject sequence of fills (auto-incrementing sequence)
- ✅ Validate sequence monotonicity
- ✅ Parse ExecutionResult response
- ✅ Timeout defaults to 5s
- ✅ Can be used as context manager

**Edge Cases:**
- Invalid order_id (Mock returns error; propagate)
- Sequence not increasing (raise AssertionError)
- Fill qty exceeds remaining (Mock returns error; propagate)
- Decimal precision (ensure string conversion preserves precision)

**NEW (v3): MockClient Responsibilities & Constraints**

MockClient is responsible ONLY for:
- Configuring execution scenarios (price sequences in INJECTION mode)
- Supporting INJECTION mode for debugging

MockClient MUST NOT:
- Trigger execution in REAL mode
- Modify order state directly
- Act as execution authority

**Guard against misuse:**
```python
class MockClient:
    def __init__(self, ..., execution_mode: str = "INJECTION"):
        self.execution_mode = execution_mode
    
    async def inject_fill(self, ...):
        if self.execution_mode == "REAL":
            raise RuntimeError(
                "inject_fill() is FORBIDDEN in REAL mode. "
                "Use price_source to configure market conditions instead."
            )
```

This prevents developers from accidentally bypassing execution engine in REAL mode tests.

**Files/Modules Impacted:**
```
e2e/clients/
├── __init__.py (export MockClient)
└── mock_client.py
```

---

#### E2E-013: Implement AuthClient (Optional, for Token Refresh)

**Phase:** Client Layer  
**Priority:** P1 — Can be added later if needed  
**Dependencies:** E2E-002  
**Estimated Effort:** 2 hours  

**Description:**
Build minimal Auth client for login and token refresh. Required if test tokens expire during long test runs.

**Implementation Steps:**
1. Create `e2e/clients/auth_client.py`:
   ```python
   class AuthClient:
       async def login(username: str, password: str) -> str  # returns token
       async def refresh(token: str) -> str  # returns new token
   ```
2. POST `/api/v1/login` endpoint
3. Handle token expiration (refresh if < 5 min remaining)
4. Cache token per test session

**Acceptance Criteria:**
- ✅ Login returns valid JWT
- ✅ Can refresh expired token
- ✅ Token cache works

**Edge Cases:**
- Invalid credentials (raise AuthError)
- Network timeout (retry logic)

**Files/Modules Impacted:**
```
e2e/clients/
├── __init__.py (export AuthClient)
└── auth_client.py
```

---

### PHASE 3: CORE TEST HARNESS

#### E2E-020: Implement EventCollector (Async Queue-Based Event Collection)

**Phase:** Core Test Harness  
**Priority:** P0 — Core dependency for all tests  
**Dependencies:** E2E-001, E2E-003  
**Estimated Effort:** 4 hours  

**Description:**
Build async event collector using per-order asyncio.Queue. Events must be collected in sequence, support filtering, and provide async wait operations. Implement ring-buffer overflow handling.

**Implementation Steps:**
1. Create `e2e/harness/event_collector.py`:
   ```python
   class EventCollector:
       def __init__(self, maxsize: int = 1000)
       
       async def add_event(order_id: str, event: dict) -> None
       async def wait_for_status(order_id, status, timeout) -> list[dict]
       async def wait_for_completion(order_id, timeout) -> list[dict]
       def get_events(order_id) -> list[dict]
       def get_events_by_type(order_id, event_type) -> list[dict]
       def clear(order_id) -> None
   ```
2. Storage:
   - `queues: dict[order_id] → asyncio.Queue(maxsize=1000)`
   - `events: dict[order_id] → list[dict]` (chronological log)
3. add_event logic:
   - Append to `events[order_id]`
   - Put into `queues[order_id]`
   - Ring-buffer: if queue full, log warning and drop oldest
4. wait_for_completion logic:
   - Poll queue with timeout until terminal status (FILLED, CANCELLED, REJECTED, EXPIRED)
   - Return accumulated events
5. Event filtering: skip heartbeats, system acks, unrelated accounts

**Acceptance Criteria:**
- ✅ Events collected in chronological order
- ✅ Support multiple concurrent orders (separate queues)
- ✅ wait_for_completion blocks until terminal state or timeout
- ✅ Ring-buffer overflow handled (drop oldest, log warning)
- ✅ Can retrieve events by type
- ✅ No event loss (except on ring-buffer overflow)
- ✅ Timeout works correctly

**Edge Cases:**
- Out-of-order events (collect as-is, assertions validate ordering)
- High-frequency events (ring-buffer overflow; log and continue)
- Concurrent wait calls on same order (all wait on same queue; undefined which returns)
- Missing order_id (create queue on demand)
- Long-running tests (clear events after test to free memory)

**NEW (v2): Event Storage Model**

Define clear source of truth:
- `events[order_id]` is the **PRIMARY source of truth** — stores complete event history
- `asyncio.Queue` is used **ONLY for signaling/waiting** — may drop events on overflow

Critical rule: Queue may drop oldest events due to `maxsize=1000`, but `events[]` dict must retain FULL chronological history. This ensures assertions always have complete data, even if queue overflows.

**NEW (v2): Backpressure & Drop Monitoring**

Add tracking:
- Counter: `dropped_events_count` per `order_id`
- Log warning on every drop: `"EventCollector overflow for {order_id}; dropped event {event_id}"`
- Update counter: `self.dropped_events_counts[order_id] += 1`

In tests, add assertion:
```python
assert event_collector.dropped_events_counts.get(order_id, 0) == 0
```

This fails tests if unexpected event loss occurs. Allow override for chaos tests via:
```python
@pytest.mark.chaos_allow_drops
async def test_with_event_drops(...):
    # May have drops
```

**Files/Modules Impacted:**
```
e2e/harness/
├── __init__.py (export EventCollector)
└── event_collector.py
```

---

#### E2E-021: Implement AssertionEngine (Lifecycle, Invariants, Sequence Validation)

**Phase:** Core Test Harness  
**Priority:** P0 — Core dependency for all tests  
**Dependencies:** E2E-020  
**Estimated Effort:** 5 hours  

**Description:**
Build comprehensive assertion library for validating order lifecycles, financial invariants, event sequences, and position states. All assertions must be typed and provide detailed failure messages.

**Implementation Steps:**
1. Create `e2e/harness/assertions.py`:
   ```python
   class AssertionError(Exception):
       pass
   
   class AssertionEngine:
       # Order lifecycle
       @staticmethod
       def assert_order_lifecycle(events, expected_status, expected_qty=None) -> None
       
       # Financial invariants
       @staticmethod
       def assert_financial_invariants(pre_funds, post_funds, side, qty, price) -> None
       
       # Event quality
       @staticmethod
       def assert_no_duplicate_events(events) -> None
       @staticmethod
       def assert_sequence_order(events) -> None  # per-order strict
       @staticmethod
       def assert_partial_fills_cumulative(events, expected_total_qty) -> None
       
       # Position validation
       @staticmethod
       def assert_position_state(positions, instrument_id, expected_qty, expected_avg_price) -> None
       @staticmethod
       def assert_position_weighted_avg_price(events, expected_avg) -> None
       @staticmethod
       def assert_position_realized_pnl(positions, expected_pnl) -> None
       
       # Helpers
       @staticmethod
       def extract_final_status(events) -> str
       @staticmethod
       def extract_fills(events) -> list[dict]
       @staticmethod
       def calculate_weighted_avg_price(fills) -> Decimal
   ```
2. Assertion implementations:
   - **assert_order_lifecycle**: Validate status transitions, presence of fills for FILLED orders
   - **assert_financial_invariants**: Validate total = available + reserved, buy debit, sell credit
   - **assert_no_duplicate_events**: Check event_id uniqueness (each event_id appears once)
   - **assert_sequence_order**: Validate order_fill sequences are 1, 2, 3, ... (per order_id)
   - **assert_position_weighted_avg_price**: Calculate Σ(qty*price)/Σ(qty) and compare
   - **assert_position_realized_pnl**: (sell_qty * sell_avg) - (buy_qty * buy_avg)
3. Use Decimal for all financial math (no float)
4. Provide detailed error messages: expected vs actual, full context

**Acceptance Criteria:**
- ✅ All assertions use Decimal for financial math
- ✅ Assertions provide detailed failure messages
- ✅ Per-order sequence validation (not global)
- ✅ Support partial fills
- ✅ Support position closes
- ✅ Support concurrent orders
- ✅ All assertions typed with Pydantic models
- ✅ Can assert intermediate states (not just final)

**Edge Cases:**
- Partial fills (validate accumulation)
- Position closes (qty=0, status=CLOSED)
- Missing events (timeout detected by EventCollector, not here)
- Rounding errors (use tolerance for Decimal comparisons)
- Negative positions (intraday short; validate carefully)

**NEW (v2): Execution Trigger Validation**

Add method to validate order execution occurred at correct price conditions:

```python
@staticmethod
def assert_execution_trigger(events, order_type, limit_price=None, 
                            stop_price=None, execution_price=None) -> None:
    """
    Validate execution happened at correct trigger condition.
    
    Rules:
    - LIMIT BUY: execution_price ≤ limit_price
    - LIMIT SELL: execution_price ≥ limit_price
    - STOP BUY: execution_price ≥ stop_price (triggers when price rises)
    - STOP SELL: execution_price ≤ stop_price (triggers when price falls)
    - MARKET: any price (no constraint)
    """
```

Critical for **REAL execution mode** to validate Mock's execution engine respects order type semantics.

Validation rules:
- Extract execution_price from order_fill events
- Match against limit_price / stop_price
- Raise AssertionError if trigger condition violated

**NEW (v3): Real Execution Validation Rules**

Tests MUST validate execution correctness under real market conditions:

Rules:
- **Execution occurs ONLY when price condition is satisfied**
- **No execution before trigger condition is met**
- **Execution timing aligns with price sequence**

Example validation:
```python
@staticmethod
def assert_real_execution_correctness(
    events: list[dict],
    order_type: str,
    limit_price: Decimal | None,
    stop_price: Decimal | None,
    price_sequence: list[Decimal]
):
    """
    Validate execution behavior matches Mock's execution engine
    for given order type and price sequence.
    
    Example:
    LIMIT BUY @ 150
    Price sequence: 151, 152, 149
    
    Expected:
    - Execution at price 149 (first time ≤ 150)
    - NOT at 151 or 152
    """
```

This ensures Mock behaves like a real broker, not an artificial execution authority.

**Files/Modules Impacted:**
```
e2e/harness/
├── __init__.py (export AssertionEngine)
└── assertions.py
```

---

#### E2E-022: Implement ScenarioEngine (YAML-Driven Test Scenarios)

**Phase:** Core Test Harness  
**Priority:** P0 — Required for all scenario-driven tests  
**Dependencies:** E2E-001  
**Estimated Effort:** 3 hours  

**Description:**
Build scenario loader and data classes for YAML-based test scenarios. Scenarios define order parameters, fill sequences, expected outcomes, and financial checks.

**Implementation Steps:**
1. Create `e2e/harness/scenario_engine.py`:
   ```python
   @dataclass
   class OrderScenario:
       name: str
       instrument_id: str
       side: str  # BUY | SELL
       qty: int
       order_type: str  # MARKET | LIMIT | STOP | STOP_LIMIT
       price: Decimal | None
       stop_price: Decimal | None
       position_type: str  # INTRADAY | OVERNIGHT
       fills: list[tuple[int, int, Decimal]]  # (sequence, qty, price)
       expected_status: str  # FILLED | CANCELLED | REJECTED
       expected_filled_qty: int
       expected_avg_price: Decimal | None
   
   @dataclass
   class TestScenario:
       name: str
       description: str
       broker_id: str
       account_id: str
       orders: list[OrderScenario]
       concurrent: bool
       expected_positions_delta: int
       expected_financial_invariant_checks: list[str]
   
   class ScenarioEngine:
       @staticmethod
       def load_scenario(scenario_file: Path) -> TestScenario
       @staticmethod
       def load_all_scenarios(scenario_dir: Path) -> dict[str, TestScenario]
   ```
2. YAML schema:
   ```yaml
   name: "scenario_name"
   description: "..."
   broker_id: "mock"
   account_id: "TEST_ACC"
   concurrent: false
   expected_positions_delta: 1
   expected_financial_invariants:
     - "buy_debit_correct"
     - "reserved_released"
   
   orders:
     - name: "buy_100"
       instrument_id: "INSTR_NSE_SBIN_EQ"
       side: "BUY"
       qty: 100
       order_type: "MARKET"
       position_type: "INTRADAY"
       fills:
         - { sequence: 1, qty: 100, price: "150.50" }
       expected_status: "FILLED"
       expected_filled_qty: 100
       expected_avg_price: "150.50"
   ```
3. Parsing with pyyaml
4. Validation (required fields, types, ranges)

**Acceptance Criteria:**
- ✅ Load YAML scenarios
- ✅ Parse into typed dataclasses
- ✅ Validate required fields
- ✅ Support multiple orders per scenario
- ✅ Can load all scenarios from directory
- ✅ Raise clear errors on invalid YAML

**Edge Cases:**
- Missing fields (raise ValidationError)
- Invalid types (Decimal parsing, int validation)
- File not found (raise FileNotFoundError)
- Circular dependencies (none expected)

**Files/Modules Impacted:**
```
e2e/harness/
├── __init__.py (export ScenarioEngine)
└── scenario_engine.py

e2e/scenarios/
└── (empty, will be filled by E2E-040+)
```

---

#### E2E-023: Integrate Fixtures & Bootstrap Full Conftest

**Phase:** Core Test Harness  
**Priority:** P0 — Required for test execution  
**Dependencies:** E2E-010, E2E-011, E2E-012, E2E-020, E2E-021, E2E-022, E2E-002, E2E-003  
**Estimated Effort:** 3 hours  

**Description:**
Complete the `conftest.py` files with all fixtures: auth tokens, service clients, event collectors, assertions, scenarios. Ensure proper scoping and cleanup.

**Implementation Steps:**
1. Create `e2e/conftest.py` (session-level fixtures):
   ```python
   @pytest.fixture(scope="session")
   def config(request) -> TestConfig:
       return TestConfig.from_env()
   
   @pytest.fixture(scope="function")
   async def auth_token(config) -> str:
       async with AuthClient(config.auth_url) as auth:
           return await auth.login(config.test_user, config.test_password)
   
   @pytest.fixture(scope="function")
   async def bas_client(config, auth_token) -> AsyncGenerator[BASClient, None]:
       async with BASClient(config.bas_url, auth_token) as client:
           yield client
   
   @pytest.fixture(scope="function")
   async def mds_client(config, auth_token, event_collector) -> AsyncGenerator[MDSWebSocketClient, None]:
       client = MDSWebSocketClient(config.mds_ws_url, auth_token, event_collector)
       await client.connect()
       await client.subscribe_account(config.account_id)
       yield client
       await client.disconnect()
   
   @pytest.fixture(scope="function")
   async def mock_client(config, auth_token) -> AsyncGenerator[MockClient, None]:
       async with MockClient(config.mock_url, auth_token) as client:
           yield client
   
   @pytest.fixture(scope="function")
   def event_collector() -> EventCollector:
       collector = EventCollector()
       # Start reader loop to pump MDS events
       yield collector
       collector.clear()
   
   @pytest.fixture(scope="function")
   def assertions() -> AssertionEngine:
       return AssertionEngine()
   
   @pytest.fixture(scope="function")
   def scenario_engine() -> ScenarioEngine:
       return ScenarioEngine()
   ```
2. Create `e2e/tests/conftest.py` (test-level fixtures):
   ```python
   @pytest.fixture
   def test_account_id(request) -> str:
       """Generate unique account ID per test"""
       import hashlib
       hash_val = hashlib.md5(request.node.nodeid.encode()).hexdigest()[:8]
       return f"TEST_E2E_{hash_val}"
   
   @pytest.fixture
   async def pre_state(bas_client, test_account_id, config):
       """Capture funds and positions before test"""
       return {
           "funds": await bas_client.get_funds(config.broker_id, test_account_id),
           "positions": await bas_client.get_positions(config.broker_id, test_account_id),
       }
   
   @pytest.fixture
   async def post_state(bas_client, test_account_id, config):
       """Capture funds and positions after test"""
       yield  # Let test run
       return {
           "funds": await bas_client.get_funds(config.broker_id, test_account_id),
           "positions": await bas_client.get_positions(config.broker_id, test_account_id),
       }
   ```
3. Wire EventCollector reader loop:
   ```python
   @pytest.fixture(scope="function")
   async def event_collector(mds_client) -> EventCollector:
       collector = EventCollector()
       
       # Start async task to pump MDS events into collector
       async def pump_events():
           async for event in mds_client.stream_events():
               order_id = extract_order_id(event)
               if order_id:
                   await collector.add_event(order_id, event)
       
       reader_task = asyncio.create_task(pump_events())
       yield collector
       
       # Cleanup
       reader_task.cancel()
       collector.clear()
   ```

**Acceptance Criteria:**
- ✅ All fixtures available in tests
- ✅ Proper scoping (session, function)
- ✅ Cleanup happens automatically
- ✅ Clients are fresh per test
- ✅ Auth tokens valid for entire test
- ✅ EventCollector pumped by MDS reader loop
- ✅ Can run `pytest tests/ -v` and see all fixtures resolve

**Edge Cases:**
- Token expiration (refresh during test)
- WebSocket disconnect during test setup (retry in fixture)
- Concurrent fixture initialization (ensure thread-safe)

**NEW (v2): Test Isolation Guarantee**

Ensure each test operates in isolated environment:

Options (implement at least one):
1. **Unique account_id per test** (already implemented via hashlib)
2. **AND reset account state before test**

Add pre-test setup hook:
```python
@pytest.fixture(autouse=True)
async def reset_test_account(bas_client, test_account_id, config):
    """Reset account state before each test"""
    # Attempt to cancel all open orders
    try:
        orders = await bas_client.get_orders(config.broker_id, test_account_id)
        for order in orders:
            if order.status not in ["FILLED", "CANCELLED", "REJECTED"]:
                await bas_client.cancel_order(config.broker_id, test_account_id, order.exchange_order_id)
    except Exception:
        pass  # Account may not exist yet
    
    yield  # Run test
```

Optional post-test cleanup (for aggressive isolation):
```python
@pytest.fixture(autouse=True)
async def cleanup_test_account(bas_client, test_account_id, config):
    yield  # Run test
    
    # After test: clear positions/balances if needed
    try:
        exit_req = BasExitPositionRequest(exit_all=True, cancel_pending_orders=True)
        await bas_client.exit_position(config.broker_id, test_account_id, exit_req)
    except Exception:
        pass
```

This ensures no state leakage across tests.

**Files/Modules Impacted:**
```
e2e/conftest.py (full)
e2e/tests/conftest.py (full)
```

---

### PHASE 4: SCENARIO ENGINE

#### E2E-030: Create YAML Scenario Files (Core Happy Paths)

**Phase:** Scenario Engine  
**Priority:** P0 — Required for first tests  
**Dependencies:** E2E-022  
**Estimated Effort:** 2 hours  

**Description:**
Write 8-10 YAML scenario files defining market conditions and order specifications. Scenarios serve as data-driven specifications; execution is driven by Mock's execution engine reacting to market conditions.

**UPDATED (v3): Scenario-Driven Execution Model**

Scenarios define market conditions, NOT execution events:

```yaml
name: "limit_buy_triggers_at_price"
order:
  side: BUY
  qty: 100
  order_type: LIMIT
  limit_price: 150.00
  
price_sequence:
  - timestamp: 0.0, price: 151.00  # Above limit, no fill
  - timestamp: 0.5, price: 150.50  # Still above, no fill
  - timestamp: 1.0, price: 149.00  # Below limit, FILLS HERE
  - timestamp: 1.5, price: 148.00  # Further down
```

Mock's execution engine evaluates:
- LIMIT BUY @ 150: fills when price ≤ 150
- LIMIT SELL @ 150: fills when price ≥ 150
- STOP BUY: fills when price ≥ stop
- MARKET: fills immediately

Tests validate Mock's behavior matches order type rules.

**Implementation Steps:**
1. Create `e2e/scenarios/` directory
2. Create YAML files (one per scenario):
   - `market_buy_full_fill.yaml` — MARKET BUY, fills immediately
   - `limit_buy_triggers_at_price.yaml` — LIMIT BUY, fills when price condition met
   - `stop_buy_triggers.yaml` — STOP BUY, triggers at stop price
   - `cancel_unfilled.yaml` — Place order, cancel before trigger
   - `partial_fills.yaml` — Multiple fills as price moves through levels
   - `intraday_short.yaml` — SELL without prior BUY (short)
   - `position_close.yaml` — BUY then SELL to close
   - `concurrent_orders.yaml` — Multiple orders with different triggers
3. Validate YAML syntax and required fields

**Acceptance Criteria:**
- ✅ 8-10 scenarios created
- ✅ Each scenario has valid YAML
- ✅ All required fields present
- ✅ Covers happy paths + edge cases
- ✅ Can load all scenarios with ScenarioEngine

**Edge Cases:**
- Instrument ID typos (validate against known list)
- Invalid order types (validate enum)
- Price precision (ensure Decimal compatible)

**Files/Modules Impacted:**
```
e2e/scenarios/
├── market_buy_full_fill.yaml
├── market_sell_full_fill.yaml
├── limit_buy_partial_fill_3x.yaml
├── cancel_after_place.yaml
├── cancel_after_partial.yaml
├── intraday_short.yaml
├── position_close.yaml
└── concurrent_orders_3x.yaml
```

---

#### E2E-031: Implement Scenario Execution Framework

**Phase:** Scenario Engine  
**Priority:** P0 — Required for test execution  
**Dependencies:** E2E-022, E2E-023  
**Estimated Effort:** 2 hours  

**Description:**
Build framework to execute scenarios end-to-end: place orders (concurrent if needed), inject fills, collect events, and return results for assertions.

**Implementation Steps:**
1. Create `e2e/harness/scenario_executor.py`:
   ```python
   class ScenarioExecutor:
       async def execute_scenario(
           scenario: TestScenario,
           bas_client: BASClient,
           mock_client: MockClient,
           event_collector: EventCollector,
           execution_mode: str = "INJECTION"  # INJECTION | REAL
       ) -> ScenarioResult
   
   @dataclass
   class ScenarioResult:
       orders_placed: list[BasOrderPlaceResponse]
       events_collected: dict[str, list[dict]]  # order_id → events
       post_state: dict  # funds, positions, trades
       execution_time: float
       status: str  # NEW (v2): See status values below
       failure_reason: str | None  # NEW (v2): Detailed failure info
   ```

**UPDATED (v2): ScenarioResult Status Granularity**

Replace generic SUCCESS/FAILURE with:
- `SUCCESS` — All orders executed, all assertions passed
- `ASSERTION_FAILURE` — Execution OK, but assertion failed (e.g., financial invariant)
- `TIMEOUT` — Event not received within timeout (e.g., order didn't fill)
- `EXECUTION_FAILURE` — Order placement failed (e.g., invalid instrument)
- `INFRA_FAILURE` — Service unavailable, network error, etc.

Include `failure_reason` field with details for debugging:
```python
ScenarioResult(
    ...,
    status="ASSERTION_FAILURE",
    failure_reason="Financial invariant failed: available should be 5000, got 4950"
)
```

This enables precise failure classification in reports and CI.

2. **UPDATED (v2): Dual Execution Mode Flow**

Explicitly define execution paths to prevent mixing modes:

```python
async def execute_scenario(...):
    # ... setup phase ...
    
    IF execution_mode == 'INJECTION':
        # Deterministic injection path
        for order in scenario.orders:
            [order_resp] = await bas_client.place_order(...)
            order_id = order_resp.broker_order_id
            
            # Inject deterministic fills
            for seq, fill_qty, fill_price in order.fills:
                await mock_client.inject_fill(
                    ..., order_id=order_id, sequence=seq,
                    fill_qty=fill_qty, fill_price=fill_price
                )
            # Collect events
            events = await event_collector.wait_for_completion(order_id)
    
    ELIF execution_mode == 'REAL':
        # Real execution path (NO inject_fill calls)
        # Configure price source
        await scenario_price_source.inject_price_sequence(
            instrument_id,
            prices=scenario.price_feed[instrument_id]
        )
        
        for order in scenario.orders:
            [order_resp] = await bas_client.place_order(...)
            order_id = order_resp.broker_order_id
            # DO NOT call inject_fill()
            # Wait for natural execution
            events = await event_collector.wait_for_completion(order_id, timeout=10)
```

This ensures real execution mode is not accidentally bypassed by inject_fill.

3. **NEW (v3): Real Execution Flow (Mandatory for E2E)**

REAL mode execution flow is mandatory:

```python
async def execute_scenario(
    scenario: TestScenario,
    execution_mode: str = "REAL",  # Default MUST be REAL
    ...
):
    # Validate execution mode
    if execution_mode == "REAL":
        # Configure price source FIRST
        await scenario_price_source.inject_price_sequence(
            instrument_id,
            prices=scenario.price_sequence,
            intervals=scenario.intervals  # Timing between prices
        )
    
    for order in scenario.orders:
        # Place order
        [order_resp] = await bas_client.place_order(...)
        order_id = order_resp.broker_order_id
        
        # For REAL mode: Mock evaluates execution internally
        # For INJECTION mode: inject_fill called (debugging only)
        if execution_mode == "INJECTION":
            await mock_client.inject_fill(...)  # For debugging
        
        # Wait for execution (driven by Mock's execution engine)
        events = await event_collector.wait_for_completion(
            order_id, 
            timeout=config.timeout_real_execution
        )
```

Key constraints:
- Default execution_mode = "REAL" (not INJECTION)
- INJECTION mode blocked from E2E suite
- Tests validate full chain: Mock → BAS → MDS → Client

**Acceptance Criteria:**
- ✅ Execute scenarios end-to-end
- ✅ Support concurrent order placement
- ✅ Collect all events for each order
- ✅ Return structured result
- ✅ Support both INJECTION (debugging) and REAL (E2E) modes
- ✅ Measure execution time
- ✅ **REAL mode is default and mandatory for E2E tests**
- ✅ MockClient.inject_fill() raises error if called in REAL mode

**Edge Cases:**
- Order placement fails (capture error, continue)
- Timeout on event collection (return partial result)
- Real mode: Mock doesn't fill within timeout (return as timeout)
- Attempt to use inject_fill in REAL mode (raise RuntimeError)

**Files/Modules Impacted:**
```
e2e/harness/
├── __init__.py (export ScenarioExecutor)
└── scenario_executor.py
```

---

### PHASE 5: INJECTION MODE TESTS

#### E2E-040: Write Happy Path E2E Tests (Injection Mode)

**Phase:** Injection Mode Tests  
**Priority:** P1 — Core functionality validation  
**Dependencies:** E2E-023, E2E-030, E2E-031  
**Estimated Effort:** 4 hours  

**Description:**
Write comprehensive E2E tests using deterministic injection mode. Tests validate order lifecycles, event sequences, and financial invariants without relying on price-triggered execution.

**Implementation Steps:**
1. Create `e2e/tests/test_order_lifecycle_injection.py`:
   ```python
   @pytest.mark.smoke
   @pytest.mark.injection
   async def test_market_buy_full_fill(
       scenario_engine, bas_client, mock_client, event_collector, assertions
   ):
       scenario = scenario_engine.load_scenario("market_buy_full_fill.yaml")
       
       # Arrange
       pre_funds = await bas_client.get_funds("mock", "TEST_ACC_001")
       
       # Act: Place order
       [order_resp] = await bas_client.place_order("mock", "TEST_ACC_001", 
                                                    scenario.orders[0].to_request())
       order_id = order_resp.broker_order_id
       
       # Act: Inject fill
       await mock_client.inject_fill("mock", "TEST_ACC_001", order_id, 
                                     sequence=1, fill_qty=100, 
                                     fill_price=Decimal("150.50"))
       
       # Observe: Wait for completion
       events = await event_collector.wait_for_completion(order_id, timeout=5)
       
       # Assert
       assertions.assert_order_lifecycle(events, "FILLED", 100)
       assertions.assert_no_duplicate_events(events)
       assertions.assert_sequence_order(events)
       
       post_funds = await bas_client.get_funds("mock", "TEST_ACC_001")
       assertions.assert_financial_invariants(pre_funds, post_funds, 
                                             side=OrderSide.BUY, qty=100, 
                                             price=Decimal("150.50"))
       
       post_positions = await bas_client.get_positions("mock", "TEST_ACC_001")
       assertions.assert_position_state(post_positions, "INSTR_NSE_SBIN_EQ",
                                       expected_qty=100, 
                                       expected_avg_price=Decimal("150.50"))
   ```
2. Create test for SELL:
   ```python
   @pytest.mark.smoke
   @pytest.mark.injection
   async def test_market_sell_full_fill(...)
   ```
3. Use pytest.mark decorators:
   - `@pytest.mark.smoke` — fast sanity test
   - `@pytest.mark.injection` — uses injection mode
4. All tests should complete in < 5 seconds

**Acceptance Criteria:**
- ✅ Tests cover: market buy, market sell, limit buy, limit sell
- ✅ All tests pass with deterministic fills
- ✅ Events collected correctly
- ✅ Financial invariants validated
- ✅ Positions validated
- ✅ Tests complete in < 5s
- ✅ Markers enable filtering: `pytest -m injection`

**Edge Cases:**
- Order placement fails (test should validate error response)
- Fill sequence numbers wrong (MockClient should reject)
- Event loss (EventCollector should timeout)

**Files/Modules Impacted:**
```
e2e/tests/
├── __init__.py
└── test_order_lifecycle_injection.py
```

---

#### E2E-041: Write Partial Fill E2E Tests (Injection Mode)

**Phase:** Injection Mode Tests  
**Priority:** P1 — Edge case validation  
**Dependencies:** E2E-023, E2E-030, E2E-031  
**Estimated Effort:** 3 hours  

**Description:**
Write tests for partial fills: multi-step fills, weighted average price calculation, and fill accumulation.

**Implementation Steps:**
1. Create `e2e/tests/test_partial_fills_injection.py`:
   ```python
   @pytest.mark.injection
   async def test_partial_fill_2x(scenario_engine, ...):
       # BUY 100: fill 50 @ 150.50, fill 50 @ 150.75
       # Verify avg price = (50*150.50 + 50*150.75) / 100 = 150.625
       scenario = scenario_engine.load_scenario("limit_buy_partial_fill_3x.yaml")
       
       [order_resp] = await bas_client.place_order(...)
       order_id = order_resp.broker_order_id
       
       # Inject 2 fills
       await mock_client.inject_fill(..., sequence=1, fill_qty=50, 
                                     fill_price=Decimal("150.50"))
       await mock_client.inject_fill(..., sequence=2, fill_qty=50, 
                                     fill_price=Decimal("150.75"))
       
       events = await event_collector.wait_for_completion(order_id)
       
       assertions.assert_order_lifecycle(events, "FILLED", 100)
       assertions.assert_partial_fills_cumulative(events, 100)
       assertions.assert_position_weighted_avg_price(..., 
                                                    expected_avg=Decimal("150.625"))
   ```
2. Test variants:
   - 2-fill: 50+50
   - 3-fill: 33+33+34
   - Many-fill: 10x fills of 10 qty each

**Acceptance Criteria:**
- ✅ Partial fills accumulate correctly
- ✅ Weighted average price calculated correctly
- ✅ No overfill
- ✅ All intermediate events collected

**Edge Cases:**
- Fills out of sequence (EventCollector should reject or EventCollector should log)
- Overfill (qty filled > ordered)
- Rounding in weighted average (use Decimal tolerance)

**Files/Modules Impacted:**
```
e2e/tests/
└── test_partial_fills_injection.py
```

---

#### E2E-042: Write Cancel & Modify E2E Tests (Injection Mode)

**Phase:** Injection Mode Tests  
**Priority:** P1 — Edge case validation  
**Dependencies:** E2E-023, E2E-030, E2E-031  
**Estimated Effort:** 3 hours  

**Description:**
Write tests for order cancellation (before fill, after partial fill) and modification.

**Implementation Steps:**
1. Create `e2e/tests/test_cancel_injection.py`:
   ```python
   @pytest.mark.injection
   async def test_cancel_unfilled_order(...):
       # Place order, cancel immediately (no fills)
       [order_resp] = await bas_client.place_order(...)
       order_id = order_resp.broker_order_id
       
       cancel_resp = await bas_client.cancel_order(..., order_id)
       assert cancel_resp.status == "CANCELLED"
       
       events = await event_collector.wait_for_completion(order_id)
       assertions.assert_order_lifecycle(events, "CANCELLED")
   
   @pytest.mark.injection
   async def test_cancel_after_partial_fill(...):
       # Place, partial fill, cancel
       [order_resp] = await bas_client.place_order(...)
       order_id = order_resp.broker_order_id
       
       await mock_client.inject_fill(..., sequence=1, fill_qty=50, ...)
       events = await event_collector.wait_for_status(order_id, "PARTIALLY_FILLED")
       
       cancel_resp = await bas_client.cancel_order(...)
       assert cancel_resp.status == "CANCELLED"
       
       events = await event_collector.wait_for_completion(order_id)
       assertions.assert_order_lifecycle(events, "CANCELLED")
       assertions.assert_partial_fills_cumulative(events, 50)  # Only 50 filled
   ```
2. Test variants:
   - Cancel unfilled
   - Cancel partial
   - Cancel already filled (should fail with error)
   - Modify then cancel

**Acceptance Criteria:**
- ✅ Cancel unfilled works
- ✅ Cancel partial works
- ✅ Cancel filled fails (returns error)
- ✅ Events correct for each scenario
- ✅ Reserved funds released on cancel

**Edge Cases:**
- Cancel non-existent order (BAS returns error)
- Double-cancel (BAS returns error)
- Modify price outside valid range (BAS returns error)

**Files/Modules Impacted:**
```
e2e/tests/
└── test_cancel_injection.py
```

---

### PHASE 6: REAL EXECUTION MODE TESTS

#### E2E-050: Write Happy Path Tests (Real Execution Mode)

**Phase:** Real Execution Mode  
**Priority:** P1 — Realistic system validation  
**Dependencies:** E2E-023, E2E-030, E2E-031  
**Estimated Effort:** 3 hours  

**Description:**
Write same tests as E2E-040 but using real execution mode (price-triggered fills). Mock Service's execution engine decides when to fill based on price conditions.

**Implementation Steps:**
1. Create `e2e/tests/test_order_lifecycle_real_execution.py`:
   ```python
   @pytest.mark.timeout_medium
   @pytest.mark.real_execution
   async def test_market_buy_full_fill_real_execution(
       scenario_engine, bas_client, mds_client, event_collector, assertions
   ):
       # Load scenario with price sequence
       scenario = ScenarioEngine.load_scenario_with_price_source(
           "market_buy_full_fill.yaml",
           price_source="controlled_feed"  # Use scenario-defined prices
       )
       
       pre_funds = await bas_client.get_funds(...)
       
       # Place order
       [order_resp] = await bas_client.place_order(..., 
                                                    execution_intent="SINGLE",
                                                    order_type="MARKET")
       order_id = order_resp.broker_order_id
       
       # Wait for natural execution (no inject_fill)
       # Mock's execution engine watches price feed and fills when conditions met
       events = await event_collector.wait_for_completion(order_id, timeout=10)
       
       # Assertions (same as injection mode)
       assertions.assert_order_lifecycle(events, "FILLED", 100)
       assertions.assert_financial_invariants(pre_funds, post_funds, ...)
   ```
2. Key difference from injection mode:
   - Do NOT call `mock_client.inject_fill()`
   - Mock's execution engine watches price feed
   - Scenario defines price sequence via ScenarioPriceSource
3. Extended timeout (10s instead of 5s) to account for execution latency

**Acceptance Criteria:**
- ✅ Tests validate real order type semantics
- ✅ MARKET orders fill immediately
- ✅ LIMIT orders fill only when price conditions met
- ✅ STOP orders trigger at stop price
- ✅ Financial invariants still validated
- ✅ Timeout 10s (configurable)

**Edge Cases:**
- Price never reaches trigger (timeout)
- Price oscillates around trigger (mock handles as specified in order type logic)
- Gap fills (price jumps past limit; mock handles)

**Files/Modules Impacted:**
```
e2e/tests/
└── test_order_lifecycle_real_execution.py
```

---

#### E2E-051: Implement ScenarioPriceSource (Mock Price Feed Controller)

**Phase:** Real Execution Mode  
**Priority:** P1 — Required for real execution mode  
**Dependencies:** E2E-022, E2E-031  
**Estimated Effort:** 3 hours  

**Description:**
Build price feed controller to inject controlled price sequences into Mock Service. Enables deterministic real execution mode testing.

**Implementation Steps:**
1. Create `e2e/harness/scenario_price_source.py`:
   ```python
   class ScenarioPriceSource:
       async def inject_price_sequence(
           instrument_id: str,
           prices: list[Decimal],
           intervals: list[float] = None  # delays between prices, default 0.5s
       ) -> None
   
   class PriceFeed:
       def __init__(self, mock_client: MockClient)
       async def push_prices(self, instrument_id, prices, intervals)
   ```
2. Extend scenario YAML to include price sequences:
   ```yaml
   name: "market_buy_with_price_feed"
   price_feed:
     INSTR_NSE_SBIN_EQ:
       prices: ["150.00", "150.25", "150.50", "150.75"]
       intervals: [0.1, 0.1, 0.1]  # seconds between prices
   ```
3. Mock Service receives price updates via REST endpoint (or subscribed WebSocket)
4. Price updates trigger Mock's execution engine

**Acceptance Criteria:**
- ✅ Can inject price sequence
- ✅ Prices delivered with correct timing
- ✅ Mock fills orders based on prices
- ✅ Deterministic and repeatable

**Edge Cases:**
- Price updates race with order placement (handle timing)
- Gaps in price sequence (mock handles gracefully)
- Multiple instruments (independent feeds)

**Files/Modules Impacted:**
```
e2e/harness/
├── __init__.py (export ScenarioPriceSource)
└── scenario_price_source.py
```

---

### PHASE 7: RESILIENCE & CHAOS

#### E2E-060: Implement Reconnect & Replay Tests

**Phase:** Resilience & Chaos  
**Priority:** P1 — Critical for production stability  
**Dependencies:** E2E-023, E2E-030, E2E-031  
**Estimated Effort:** 3 hours  

**Description:**
Write tests validating WebSocket reconnection, event replay, and recovery from network failures.

**Implementation Steps:**
1. Create `e2e/tests/test_resilience_reconnect.py`:
   ```python
   @pytest.mark.timeout_slow
   @pytest.mark.resilience
   async def test_mds_reconnect_mid_lifecycle(
       scenario_engine, bas_client, mock_client, mds_client, event_collector
   ):
       # Place order
       [order_resp] = await bas_client.place_order(...)
       order_id = order_resp.broker_order_id
       
       # Simulate disconnect (force close WebSocket)
       await mds_client.disconnect()
       
       # Inject fill while disconnected
       await mock_client.inject_fill(..., sequence=1, ...)
       
       # Reconnect
       await mds_client.connect()
       await mds_client.subscribe_account(...)
       
       # Should receive buffered/replayed events
       events = await event_collector.wait_for_completion(order_id, timeout=30)
       
       # Events should be present despite disconnect
       assert len(events) > 0
       assertions.assert_order_lifecycle(events, "FILLED")
   ```
2. Test variants:
   - Disconnect during order placement
   - Disconnect during fill
   - Disconnect during event streaming
   - Multiple reconnects (3x disconnect/reconnect cycle)

**Acceptance Criteria:**
- ✅ Auto-reconnect works
- ✅ Events not lost on disconnect
- ✅ Order lifecycle completes despite network hiccup
- ✅ Timeout extended to 30s for reconnect scenarios

**Edge Cases:**
- Reconnect fails (multiple retries with backoff)
- Events lost due to replay buffer (timeout and fail)
- Order placed during disconnect (confirm on reconnect)

**NEW (v2): Replay Window Configuration**

Add configurable replay window to validate event replay behavior:

```python
# In config.py
mds_replay_window_seconds: float = 300  # 5 minutes; events buffered for 5m

# In test
@pytest.fixture
def replay_config(config):
    return {
        "replay_window_seconds": config.mds_replay_window_seconds,
        "max_events_buffered": 10000,
    }

# In test
async def test_reconnect_within_replay_window(mds_client, event_collector, replay_config):
    # Disconnect, wait < replay_window, reconnect
    await mds_client.disconnect()
    
    # Wait 2 seconds (< 300 second replay window)
    await asyncio.sleep(2)
    
    await mds_client.connect()
    await mds_client.subscribe_account(...)
    
    # Events should be replayed from buffer
    events = await event_collector.wait_for_completion(order_id, timeout=10)
    assert len(events) > 0

async def test_reconnect_outside_replay_window(mds_client, event_collector, replay_config):
    # Disconnect, wait > replay_window, reconnect
    await mds_client.disconnect()
    
    # Wait longer than replay window (simulated by test)
    # Events are not guaranteed to be replayed
    
    await mds_client.connect()
    # Expect timeout or partial events
```

Used in resilience tests to validate event replay boundaries.

**Files/Modules Impacted:**
```
e2e/tests/
└── test_resilience_reconnect.py

e2e/config/config.py (add mds_replay_window_seconds)
```

---

#### E2E-061: Implement Idempotency & Duplicate Detection Tests

**Phase:** Resilience & Chaos  
**Priority:** P1 — Production safety  
**Dependencies:** E2E-023, E2E-030, E2E-031  
**Estimated Effort:** 2 hours  

**Description:**
Write tests for idempotency: duplicate order placement, duplicate fill injection, duplicate event delivery.

**Implementation Steps:**
1. Create `e2e/tests/test_idempotency.py`:
   ```python
   @pytest.mark.resilience
   async def test_duplicate_place_same_idempotency_key(
       bas_client, ...
   ):
       # Place order twice with same idempotency key
       request = BasOrderPlaceRequest(..., idempotency_key="idem_123")
       
       [resp1] = await bas_client.place_order(..., request)
       [resp2] = await bas_client.place_order(..., request)
       
       # Should return same order_id
       assert resp1.broker_order_id == resp2.broker_order_id
   
   @pytest.mark.resilience
   async def test_duplicate_fill_no_double_debit(
       bas_client, mock_client, event_collector, assertions, ...
   ):
       # Place order, inject fill twice
       [order_resp] = await bas_client.place_order(...)
       order_id = order_resp.broker_order_id
       
       pre_funds = await bas_client.get_funds(...)
       
       # Inject same fill twice
       await mock_client.inject_fill(..., sequence=1, fill_qty=100, 
                                     fill_price=Decimal("150.50"))
       await mock_client.inject_fill(..., sequence=1, fill_qty=100,
                                     fill_price=Decimal("150.50"))  # Duplicate
       
       events = await event_collector.wait_for_completion(order_id, timeout=10)
       
       # Only one fill should be recorded
       fills = assertions.extract_fills(events)
       assert len(fills) == 1  # Not 2
       
       post_funds = await bas_client.get_funds(...)
       post_funds.available should equal (pre_funds.available - 100*150.50)  # Not double debit
   ```

**Acceptance Criteria:**
- ✅ Duplicate order placement idempotent (same order_id)
- ✅ Duplicate fills not double-counted
- ✅ Duplicate events deduplicated (by event_id)
- ✅ Financial invariants still correct

**Edge Cases:**
- Different idempotency keys (create new orders)
- Duplicate with slight price variation (treated as different fill)
- Timing: duplicate arrives during processing (handled correctly)

**Files/Modules Impacted:**
```
e2e/tests/
└── test_idempotency.py
```

---

#### E2E-062: Implement Chaos Testing Hooks

**Phase:** Resilience & Chaos  
**Priority:** P2 — Enhanced resilience validation  
**Dependencies:** E2E-011, E2E-020  
**Estimated Effort:** 2 hours  

**Description:**
Implement controlled fault injection: WebSocket disconnects, delayed messages, dropped events. Enable resilience testing without relying on flaky network.

**Implementation Steps:**
1. Extend `MDSWebSocketClient` with chaos methods:
   ```python
   class MDSWebSocketClient:
       async def chaos_disconnect(self, duration: float = 2.0) -> None
       async def chaos_delay_message(self, delay: float = 1.0) -> None
       async def chaos_drop_message_rate(self, drop_rate: float = 0.1) -> None
   ```
2. Extend `EventCollector` with chaos:
   ```python
   class EventCollector:
       async def chaos_drop_events(self, drop_rate: float = 0.1) -> None
   ```
3. Write tests:
   ```python
   @pytest.mark.chaos
   @pytest.mark.timeout_slow
   async def test_chaos_disconnect_and_recover(mds_client, event_collector, ...):
       scenario = load_scenario("market_buy_full_fill.yaml")
       
       # Enable chaos
       await mds_client.chaos_disconnect(duration=3.0)
       
       [order_resp] = await bas_client.place_order(...)
       order_id = order_resp.broker_order_id
       
       await mock_client.inject_fill(...)
       
       # Should recover despite disconnect
       events = await event_collector.wait_for_completion(order_id, timeout=30)
       assert len(events) > 0
   ```

**Acceptance Criteria:**
- ✅ Chaos hooks work
- ✅ System recovers from induced faults
- ✅ Timeouts adjusted for chaos scenarios
- ✅ Can enable/disable via env var

**Edge Cases:**
- Cascade failures (disconnect + dropped messages)
- Rapid disconnect/reconnect cycles
- Chaos during critical event (fill)

**Files/Modules Impacted:**
```
e2e/clients/mds_client.py (add chaos methods)
e2e/harness/event_collector.py (add chaos methods)
e2e/tests/test_chaos.py (new)
```

---

### PHASE 8: OBSERVABILITY & REPORTING

#### E2E-070: Implement HTML Reporting & Test Artifacts

**Phase:** Observability & Reporting  
**Priority:** P2 — CI/CD visualization  
**Dependencies:** E2E-023  
**Estimated Effort:** 3 hours  

**Description:**
Build rich HTML test reports with event timelines, order state transitions, financial invariant validations, and artifact collection.

**Implementation Steps:**
1. Install pytest-html and create custom plugin:
   ```bash
   pip install pytest-html
   ```
2. Create `e2e/conftest.py` extension:
   ```python
   def pytest_configure(config):
       config.addinivalue_line(
           "markers", "html_report: mark test for HTML report"
       )
   ```
3. Create custom reporter `e2e/fixtures/html_reporter.py`:
   ```python
   class HTMLReporter:
       def generate_test_report(self, test_name, scenario, result, events, 
                              pre_state, post_state) -> dict:
           return {
               "test_name": test_name,
               "execution_mode": result.execution_mode,
               "status": "PASSED" | "FAILED",
               "order_payload": scenario.orders[0],
               "event_timeline": [
                   {"timestamp": e["timestamp"], "type": e["type"], 
                    "sequence": e.get("sequence"), "data": e.get("data")}
                   for e in events
               ],
               "final_state": {
                   "order_status": result.order_status,
                   "filled_qty": result.filled_qty,
                   "avg_price": result.avg_price,
                   "funds": post_state["funds"],
                   "positions": post_state["positions"],
               },
               "assertions_passed": result.assertions_passed,
               "execution_time_ms": result.execution_time_ms,
           }
   ```
4. Attach reports to pytest:
   ```python
   @pytest.fixture
   def html_reporter(request):
       reporter = HTMLReporter()
       yield reporter
       # After test, generate and attach report
   ```
5. Generate JSON artifacts per test:
   ```
   test-artifacts/
   ├── test_market_buy_full_fill.json
   ├── test_partial_fill_3x.json
   └── ...
   ```

**Acceptance Criteria:**
- ✅ HTML report generated for each test
- ✅ Event timeline with sequence numbers
- ✅ Order payload and final state visible
- ✅ Execution mode displayed (INJECTION/REAL)
- ✅ All assertions results shown
- ✅ JSON artifacts attached to report

**Edge Cases:**
- Large event lists (paginate or collapse)
- Missing timestamps (use default)
- Decimal precision in JSON (serialize as string)

**NEW (v2): Test Metrics Collection**

Capture per-test metrics for observability:

```python
class TestMetrics:
    total_orders_executed: int
    total_events_processed: int
    avg_execution_latency_ms: float
    dropped_events_count: int
    assertion_count: int
    assertion_failures: int
```

Collect metrics:
```python
metrics = {
    "total_orders_executed": len(scenario.orders),
    "total_events_processed": sum(len(e) for e in events.values()),
    "avg_execution_latency_ms": execution_time_ms / len(scenario.orders),
    "dropped_events_count": event_collector.dropped_events_counts.get(order_id, 0),
}
```

Include metrics in:
- HTML report (display as summary stats)
- JSON artifacts (for aggregation)
- Logs (per-test metrics line)

This enables performance tracking across test runs.

**Files/Modules Impacted:**
```
e2e/fixtures/html_reporter.py
e2e/conftest.py (integrate reporter)
e2e/fixtures/test_metrics.py (NEW)
test-artifacts/ (generated)
```

---

#### E2E-071: Implement Structured Logging & Correlation IDs

**Phase:** Observability & Reporting  
**Priority:** P2 — Debugging  
**Dependencies:** E2E-003  
**Estimated Effort:** 2 hours  

**Description:**
Enhance logging with structured format: order_id, sequence, timestamp. Enable log filtering and end-to-end tracing.

**Implementation Steps:**
1. Create `e2e/fixtures/structured_logger.py`:
   ```python
   class StructuredLogger:
       def __init__(self, order_id: str):
           self.order_id = order_id
       
       def info(self, event: str, message: str, **kwargs):
           log_entry = {
               "timestamp": datetime.utcnow().isoformat(),
               "order_id": self.order_id,
               "sequence": kwargs.get("sequence"),
               "event": event,
               "message": message,
               "extra": kwargs
           }
           logging.info(json.dumps(log_entry))
   ```
2. Update conftest to inject logger:
   ```python
   @pytest.fixture
   def logger(request):
       # Extract order_id from test context
       order_id = getattr(request, "order_id", "N/A")
       return StructuredLogger(order_id)
   ```
3. Update tests to use structured logger:
   ```python
   logger.info("order_placed", "Order placed successfully", 
              broker_order_id=order_id)
   ```

**Acceptance Criteria:**
- ✅ All logs include order_id
- ✅ Logs are structured JSON
- ✅ Can grep logs by order_id
- ✅ Timestamp present in every log

**Edge Cases:**
- Missing order_id (use "N/A")
- Concurrent tests (ensure each order_id unique)

**Files/Modules Impacted:**
```
e2e/fixtures/structured_logger.py
e2e/conftest.py
e2e/tests/*.py (use logger)
```

---

#### E2E-072: Add Optional DB Validation Layer

**Phase:** Observability & Reporting  
**Priority:** P2 — Advanced debugging  
**Dependencies:** E2E-002  
**Estimated Effort:** 2 hours  

**Description:**
Implement optional direct database validation for detecting hidden inconsistencies. Disabled by default; enabled via `--debug-db` flag.

**Implementation Steps:**
1. Create `e2e/fixtures/db_validator.py`:
   ```python
   class DBValidator:
       def __init__(self, db_connection_string: str):
           self.conn = psycopg.connect(db_connection_string)
       
       async def validate_order_consistency(self, order_id: str) -> bool
       async def validate_balance_invariants(self, account_id: str) -> bool
       async def validate_no_duplicate_fills(self, order_id: str) -> bool
   ```
2. Add pytest flag:
   ```python
   def pytest_addoption(parser):
       parser.addoption("--debug-db", action="store_true", 
                       help="Enable database validation")
   ```
3. Use in tests:
   ```python
   @pytest.mark.db_validate
   async def test_with_db_check(request, db_validator, ...):
       # Normal test flow
       
       # Optional: validate DB
       if request.config.getoption("--debug-db"):
           assert await db_validator.validate_order_consistency(order_id)
   ```

**Acceptance Criteria:**
- ✅ DB validation available
- ✅ Can enable via flag
- ✅ Detects order inconsistencies
- ✅ Validates financial invariants
- ✅ Doesn't slow down normal tests

**Edge Cases:**
- DB connection fails (skip validation)
- Order not found in DB (report error)
- Transaction isolation issues (report anomalies)

**Files/Modules Impacted:**
```
e2e/fixtures/db_validator.py
e2e/conftest.py (add pytest option)
e2e/tests/*.py (optional marker)
```

---

### PHASE 9: CI/CD INTEGRATION

#### E2E-080: Create docker-compose.test.yml

**Phase:** CI/CD Integration  
**Priority:** P0 — Production readiness  
**Dependencies:** None  
**Estimated Effort:** 2 hours  

**Description:**
Build docker-compose configuration for spinning up all services in correct dependency order. Used by GitHub Actions workflow.

**Implementation Steps:**
1. Create `docker-compose.test.yml` in smarttrade-tests root:
   ```yaml
   version: '3.8'
   
   services:
     postgres:
       image: postgres:15
       environment:
         POSTGRES_USER: smarttrade
         POSTGRES_PASSWORD: smarttrade
         POSTGRES_DB: smarttrade_test
       healthcheck:
         test: ["CMD", "pg_isready"]
         interval: 5s
         timeout: 3s
         retries: 5
     
     redis:
       image: redis:7
       healthcheck:
         test: ["CMD", "redis-cli", "ping"]
         interval: 5s
       retries: 5
     
     auth:
       build:
         context: ..
         dockerfile: authentication-service/Dockerfile.test
       ports:
         - "8001:8000"
       environment:
         DATABASE_URL: postgresql://smarttrade:smarttrade@postgres:5432/smarttrade_test
         JWT_SECRET_KEY: test-secret
       depends_on:
         postgres:
           condition: service_healthy
     
     mds:
       build:
         context: ..
         dockerfile: market-data-service/Dockerfile.test
       ports:
         - "8000:8000"
       environment:
         DATABASE_URL: postgresql://smarttrade:smarttrade@postgres:5432/smarttrade_test
         EVENT_BUS_URL: redis://redis:6379/0
       depends_on:
         - postgres
         - redis
     
     bas:
       build:
         context: ..
         dockerfile: broker-adapter-service/Dockerfile.test
       ports:
         - "8005:8000"
       environment:
         DATABASE_URL: postgresql://smarttrade:smarttrade@postgres:5432/smarttrade_test
         EVENT_BUS_URL: redis://redis:6379/0
       depends_on:
         - postgres
         - redis
         - auth
         - mds
     
     mock:
       build:
         context: ..
         dockerfile: paper-broker-service/Dockerfile.test
       ports:
         - "8002:8000"
       environment:
         DATABASE_URL: postgresql://smarttrade:smarttrade@postgres:5432/smarttrade_test
         EVENT_BUS_URL: redis://redis:6379/0
       depends_on:
         - postgres
         - redis
   
   volumes:
     pgdata:
   ```

**Acceptance Criteria:**
- ✅ All services start in correct order
- ✅ Healthchecks pass
- ✅ Services reachable on configured ports
- ✅ Can run: `docker-compose -f docker-compose.test.yml up`

**Edge Cases:**
- Ports already in use (use different port mappings)
- Image build failures (check Dockerfile.test in each service)
- Volume persistence (optional; use named volumes for state)

**Files/Modules Impacted:**
```
smarttrade-tests/
└── docker-compose.test.yml
```

---

#### E2E-081: Create GitHub Actions Workflow

**Phase:** CI/CD Integration  
**Priority:** P0 — Production readiness  
**Dependencies:** E2E-080  
**Estimated Effort:** 2 hours  

**Description:**
Build GitHub Actions workflow to automatically run E2E tests on PR and commit to main. Integrates service startup, pytest execution, artifact upload, and PR comments.

**Implementation Steps:**
1. Create `.github/workflows/e2e-tests.yml`:
   ```yaml
   name: E2E Tests
   
   on:
     push:
       branches: [main]
     pull_request:
       branches: [main]
   
   jobs:
     e2e-tests:
       runs-on: ubuntu-latest
       timeout-minutes: 15
       
       steps:
         - uses: actions/checkout@v4
         
         - name: Set up Python
           uses: actions/setup-python@v4
           with:
             python-version: '3.12'
         
         - name: Start services
           run: docker-compose -f smarttrade-tests/docker-compose.test.yml up -d
         
         - name: Wait for services
           run: |
             for i in {1..60}; do
               if curl -f http://localhost:8005/ready 2>/dev/null; then
                 echo "Services ready"
                 exit 0
               fi
               sleep 1
             done
             echo "Services failed to start"
             exit 1
         
         - name: Install E2E dependencies
           working-directory: smarttrade-tests/e2e
           run: pip install -r requirements.txt
         
         - name: Run E2E tests
           working-directory: smarttrade-tests/e2e
           run: |
             pytest tests/ -v --tb=short \
               --html=test-report.html --self-contained-html \
               --junit-xml=test-results.xml \
               -m "not chaos"  # Skip chaos tests in CI
           env:
             E2E_ENV: dev
         
         - name: Upload test report
           if: always()
           uses: actions/upload-artifact@v3
           with:
             name: e2e-test-report
             path: smarttrade-tests/e2e/test-report.html
         
         - name: Publish test results
           if: always()
           uses: EnricoMi/publish-unit-test-result-action@v2
           with:
             files: smarttrade-tests/e2e/test-results.xml
         
         - name: Comment PR
           if: github.event_name == 'pull_request'
           uses: actions/github-script@v7
           with:
             script: |
               const fs = require('fs');
               const xml = fs.readFileSync('smarttrade-tests/e2e/test-results.xml', 'utf8');
               const match = xml.match(/tests="(\d+)".*failures="(\d+)"/);
               const [, total, failures] = match || ['', '0', '0'];
               
               github.rest.issues.createComment({
                 issue_number: context.issue.number,
                 owner: context.repo.owner,
                 repo: context.repo.repo,
                 body: `✅ E2E Tests: ${total} passed, ${failures} failed\n\n[View Report](https://github.com/${{ github.repository }}/actions/runs/${{ github.run_id }})`
               });
   ```

**Acceptance Criteria:**
- ✅ Workflow runs on PR and commit to main
- ✅ Tests run successfully
- ✅ Report uploaded as artifact
- ✅ PR commented with results
- ✅ Timeout 15 minutes (allows all tests to run)

**Edge Cases:**
- Service startup timeout (increase retry count)
- Flaky tests (use retry logic)
- Artifact upload fails (don't fail workflow)

**NEW (v2): Test Execution Matrix**

**UPDATED (v3): CI Execution Policy (Real Mode Only)**

Define test execution strategy based on environment:

```yaml
execution_matrix:
  ci:
    name: "Pull Request & Commit to main — REAL EXECUTION ONLY"
    markers: "-m 'real_execution and not chaos'"  # UPDATED: Must include real_execution
    requirement: "Tests MUST validate realistic broker behavior"
    max_duration: 10 minutes
  
  nightly:
    name: "Full Suite (scheduled 11 PM)"
    markers: "-m 'not chaos'"  # Include all real_execution tests
    timeouts:
      - real_execution (10s timeout)
      - resilience (30s timeout)
    max_duration: 15 minutes
  
  manual:
    name: "Debug & Chaos Testing (user-triggered)"
    markers: "-m 'chaos or injection'"  # Only for debugging
    note: "For developer troubleshooting only, not in CI"
    max_duration: 30 minutes
```

**CI Command (from GitHub Actions):**
```bash
pytest tests/ \
  -m 'real_execution and not chaos' \
  -v --tb=short \
  --html=test-report.html
```

**Key enforcement:**
- ✅ CI runs ONLY `@pytest.mark.real_execution` tests
- ✅ INJECTION tests (`@pytest.mark.injection`) excluded from CI
- ✅ All CI tests validate realistic execution behavior
- ✅ No artificial execution shortcuts in CI

**Rationale:**
Ensures CI validates full realistic chain (Mock → BAS → MDS), not isolated unit behavior.

**Files/Modules Impacted:**
```
smarttrade-tests/
└── .github/workflows/e2e-tests.yml
```

---

#### E2E-082: Create requirements.txt & Local Setup Documentation

**Phase:** CI/CD Integration  
**Priority:** P0 — Local development  
**Dependencies:** E2E-010 through E2E-072  
**Estimated Effort:** 1.5 hours  

**Description:**
Create requirements.txt for Python dependencies and README for local setup.

**Implementation Steps:**
1. Create `e2e/requirements.txt`:
   ```
   pytest==7.4.4
   pytest-asyncio==0.23.2
   pytest-html==4.1.1
   httpx[http2]==0.26.0
   websockets==12.0
   pydantic==2.6.0
   pyyaml==6.0.1
   python-dotenv==1.0.0
   psycopg==3.1.0  # Optional, for DB validation
   ```
2. Create `e2e/README.md`:
   ```markdown
   # SmartTrade E2E Testing Framework
   
   ## Setup
   
   ### Local Development
   
   1. Install dependencies:
      ```bash
      cd e2e
      pip install -r requirements.txt
      ```
   
   2. Start services:
      ```bash
      docker-compose -f ../docker-compose.test.yml up
      ```
   
   3. Run tests:
      ```bash
      pytest tests/ -v
      ```
   
   ### Modes
   
   - **Injection Mode** (default): `pytest -m injection`
   - **Real Execution Mode**: `pytest -m real_execution`
   - **Resilience**: `pytest -m resilience`
   - **Smoke**: `pytest -m smoke`
   
   ### Configuration
   
   Set environment before running:
   ```bash
   export E2E_ENV=dev
   export E2E_TIMEOUT_FAST=5
   export E2E_TIMEOUT_MEDIUM=10
   export E2E_TIMEOUT_SLOW=30
   ```
   
   ### Debug
   
   ```bash
   # Verbose output
   pytest tests/ -vv
   
   # Show logs
   pytest tests/ -v --capture=no
   
   # DB validation
   pytest tests/ --debug-db
   
   # Chaos testing
   pytest -m chaos
   ```
   ```

**Acceptance Criteria:**
- ✅ requirements.txt includes all dependencies
- ✅ README has setup instructions
- ✅ README has mode descriptions
- ✅ Local developers can follow README and run tests

**Edge Cases:**
- Python version mismatch (specify 3.12+)
- Missing system dependencies (psycopg needs libpq)

**Files/Modules Impacted:**
```
e2e/
├── requirements.txt
└── README.md
```

---

## 3. Critical Path (Blocking Tasks)

Tasks that must be completed before others can start:

```
E2E-001 (Directory Setup)
    ↓
E2E-002 (Config System)
    ↓
E2E-003 (Logging & Test Data)
    ├─→ E2E-010 (BASClient)
    ├─→ E2E-011 (MDSWebSocketClient)
    ├─→ E2E-012 (MockClient)
    │
    └─→ E2E-020 (EventCollector)
        ↓
    E2E-021 (AssertionEngine)
        ↓
    E2E-022 (ScenarioEngine)
        ↓
    E2E-023 (Fixtures Integration)
        ↓
    E2E-030 (YAML Scenarios)
        ↓
    E2E-031 (Scenario Executor)
        ├─→ E2E-040 (Happy Path Injection Tests)
        ├─→ E2E-041 (Partial Fill Tests)
        ├─→ E2E-042 (Cancel Tests)
        │
        └─→ E2E-050 (Real Execution Tests)
            ↓
        E2E-051 (Price Source)
        │
        └─→ E2E-060 (Reconnect Tests)
        └─→ E2E-061 (Idempotency Tests)
        └─→ E2E-062 (Chaos Hooks)
    │
    └─→ E2E-070 (HTML Reporting)
    └─→ E2E-071 (Structured Logging)
    └─→ E2E-072 (DB Validation)
    │
    └─→ E2E-080 (docker-compose.test.yml)
        ↓
    E2E-081 (GitHub Actions)
        ↓
    E2E-082 (requirements.txt & README)
```

**Minimum Viable Product (MVP) Path:**
- E2E-001 → E2E-002 → E2E-003 → E2E-010/011/012 → E2E-020/021/022 → E2E-023 → E2E-030/031 → E2E-040

This gives you working happy path injection tests in ~3-4 weeks.

---

## 4. Parallelization Plan (Team Execution)

### Team Structure (Estimated)
- **Backend Engineer (1-2)**: Clients (E2E-010/011/012), Harness (E2E-020/021)
- **QA Engineer (1)**: Scenarios (E2E-030/031), Tests (E2E-040/041/042)
- **Platform Engineer (1)**: CI/CD (E2E-080/081/082), Observability (E2E-070/071)

### Parallelization (Weeks 1-8)

**Week 1: Foundation** (all parallel)
- E2E-001: Directory setup (1 person, 1.5h)
- E2E-002: Config system (1 person, 2h)
- E2E-003: Logging & test data (1 person, 1.5h)
- **Exit criteria**: All setup complete

**Week 2: Client Layer** (all parallel)
- E2E-010: BASClient (1 person, 4h) + review (2h)
- E2E-011: MDSWebSocketClient (1 person, 5h) + review (2h)
- E2E-012: MockClient (1 person, 3h) + review (1h)
- E2E-013: AuthClient (1 person, 2h) optional
- **Exit criteria**: All clients tested independently

**Week 3: Core Harness** (all parallel, dependent on Week 2)
- E2E-020: EventCollector (1 person, 4h) + review (2h)
- E2E-021: AssertionEngine (1 person, 5h) + review (2h)
- E2E-022: ScenarioEngine (1 person, 3h) + review (1h)
- E2E-023: Fixtures (1 person, 3h) + review (1h)
- **Exit criteria**: Full harness ready

**Week 4: Scenario Setup** (dependent on Week 3)
- E2E-030: YAML Scenarios (1 person, 2h)
- E2E-031: Scenario Executor (1 person, 2h) + review (1h)
- **Exit criteria**: Scenarios ready to use

**Week 5: Injection Mode Tests** (dependent on Week 4, all parallel)
- E2E-040: Happy Paths (1 person, 4h) + review (1h)
- E2E-041: Partial Fills (1 person, 3h) + review (1h)
- E2E-042: Cancel Flows (1 person, 3h) + review (1h)
- **Exit criteria**: 10+ injection mode tests passing

**Week 6: Real Execution & Observability** (parallel)
- E2E-050: Real Execution Happy Paths (1 person, 3h) + review (1h)
- E2E-051: Price Source (1 person, 3h) + review (1h)
- E2E-070: HTML Reporting (1 person, 3h) + review (1h)
- E2E-071: Structured Logging (1 person, 2h) + review (0.5h)
- **Exit criteria**: Real execution tests working, reporting ready

**Week 7: Resilience & Chaos** (dependent on Week 5, all parallel)
- E2E-060: Reconnect Tests (1 person, 3h) + review (1h)
- E2E-061: Idempotency Tests (1 person, 2h) + review (0.5h)
- E2E-062: Chaos Hooks (1 person, 2h) + review (0.5h)
- E2E-072: DB Validation (1 person, 2h) + review (0.5h)
- **Exit criteria**: All resilience scenarios covered

**Week 8: CI/CD & Release** (dependent on earlier phases)
- E2E-080: docker-compose.test.yml (1 person, 2h) + review (0.5h)
- E2E-081: GitHub Actions (1 person, 2h) + review (0.5h)
- E2E-082: requirements.txt & README (1 person, 1.5h) + review (0.5h)
- **Integration testing**: Full pipeline
- **Exit criteria**: E2E framework production-ready

---

## 5. Milestones (What Should Work)

### After Phase 1 (Foundation Setup)
✅ Directory structure created  
✅ Config system loads from env  
✅ Logging with order_id correlation  
✅ Test data fixtures available  

### After Phase 2 (Client Layer)
✅ BASClient places orders via REST  
✅ MDSWebSocketClient connects to MDS, receives events  
✅ MockClient injects deterministic fills  
✅ Can login and get auth token  

### After Phase 3 (Core Harness)
✅ EventCollector collects events in sequence  
✅ AssertionEngine validates order lifecycles  
✅ ScenarioEngine loads YAML scenarios  
✅ All fixtures integrated and available to tests  

### After Phase 4 (Scenario Engine)
✅ YAML scenarios load correctly  
✅ Scenario executor places orders and injects fills  
✅ Can run single scenario end-to-end  

### After Phase 5 (Injection Mode Tests)
✅ 3 happy path injection tests passing  
✅ 2 partial fill tests passing  
✅ 2 cancel tests passing  
✅ **8+ tests in injection mode working**  

### After Phase 6 (Real Execution Mode)
✅ Same scenarios work with real execution (price-triggered)  
✅ Price source framework working  
✅ Real execution mode tests passing  
✅ HTML reports generated for all tests  

### After Phase 7 (Resilience & Chaos)
✅ Reconnect tests passing  
✅ Idempotency validated  
✅ Chaos hooks implemented  
✅ DB validation optional feature working  

### After Phase 8 (Observability)
✅ Rich HTML reports with event timelines  
✅ Structured logging with order_id correlation  
✅ JSON artifacts for each test  
✅ Debugging tools ready  

### After Phase 9 (CI/CD Integration)
✅ docker-compose.test.yml starts all services  
✅ GitHub Actions workflow runs tests on PR/commit  
✅ Test results published to artifacts  
✅ **E2E framework production-ready**  

---

## 6. Risks & Mitigation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| **EventCollector event loss under high throughput** | Medium | High | Implement ring-buffer overflow handling; monitor dropped events |
| **WebSocket reconnect timing race conditions** | Medium | High | Test reconnect scenarios thoroughly; add exponential backoff |
| **Decimal precision issues in financial math** | Low | High | Use Decimal type everywhere; add tolerance in comparisons |
| **Service not ready in CI** | Medium | Medium | Add explicit wait-for-readiness; increase timeout |
| **Flaky tests from network timing** | Medium | Medium | Use event-driven waits, not sleep; add retry logic |
| **Test data conflicts (concurrent tests)** | Medium | Low | Generate unique account_id per test |
| **Docker image build failures** | Low | Medium | Version lock base images; test locally before CI |
| **Token expiration during long test runs** | Low | Low | Implement token refresh; use long-lived test tokens |

---

## 7. Architecture Enforcement Rules

### NEW (v3): Mock Behaves as Real Broker Enforcement

SmartTrade E2E testing MUST enforce the constraint: **"Mock Service behaves as an external broker"**.

**Architectural Principle:**
- BAS is the execution authority for orders
- Mock simulates external broker behavior
- Tests validate full chain: Mock → BAS → MDS → Client
- Tests MUST NOT bypass the execution engine

**Execution Architecture:**
```
Test Framework
    ↓
BAS (order authority)
    ↓
Mock (simulates broker, evaluates execution internally)
    ↓
BAS (processes execution, publishes events)
    ↓
MDS (streams events)
    ↓
Test client observes
```

**Forbidden Shortcuts:**
- ❌ `inject_fill()` in REAL mode (bypasses execution engine)
- ❌ Direct order state modification (bypasses BAS)
- ❌ Artificial execution outcomes (not price-triggered)
- ❌ Isolation of Mock behavior from full chain

**Enforcement:**
1. **Runtime Guard** (in MockClient):
   ```python
   if execution_mode == "REAL":
       raise RuntimeError("inject_fill() forbidden in REAL mode")
   ```

2. **Static Analysis** (CI check):
   ```bash
   # Prevent inject_fill() usage in E2E test files
   grep -r "inject_fill" e2e/tests/ && exit 1
   ```

3. **Test Markers** (filtering):
   ```bash
   # CI only runs REAL execution tests
   pytest -m "real_execution and not chaos"
   ```

4. **Code Review Policy**:
   - REAL mode default (no INJECTION shortcuts)
   - INJECTION marked as debug-only
   - Architecture reviewers verify no execution bypass

---

### NEW (v3): Developer Guardrails

Prevent common mistakes that violate architecture:

**Lint Rules:**
```yaml
# Add to .pre-commit-config.yaml
e2e-no-inject-fill:
  entry: "grep -r 'inject_fill' e2e/tests/"
  language: "system"
  pass_filenames: false
  always_run: true
  fail_fast: true
  stages: ["commit"]
```

**Test Marker Enforcement:**
```python
# Pytest plugin in conftest.py
def pytest_configure(config):
    # All tests in e2e/tests/ MUST have real_execution marker
    # OR be marked injection (excluded from CI)
    pass
```

**Documentation (README.md):**
```markdown
## Execution Modes

### REAL Mode (E2E, Default)
- Used in CI
- Validates realistic broker behavior
- Mock execution engine drives fills

### INJECTION Mode (Debug Only)
- Used for unit testing, isolated validation
- NOT in CI
- Forbidden in E2E test suite
```

---

## 7. Definition of Done (E2E Framework Ready)

The E2E framework is **production-ready** when:

### Code Quality
- ✅ All components have unit tests
- ✅ All clients tested with mock services
- ✅ Code review approval (2+ reviewers)
- ✅ No critical SonarQube violations
- ✅ Type hints on all functions

### Test Coverage
- ✅ 30+ E2E tests written
- ✅ 50%+ code coverage in e2e/ module
- ✅ All major workflows covered (buy, sell, cancel, partial fills)
- ✅ Both injection and real execution modes tested
- ✅ Resilience tests passing

### Documentation
- ✅ README.md with setup instructions
- ✅ Inline code comments for complex logic
- ✅ Test scenario descriptions in YAML
- ✅ API reference for all clients
- ✅ Debugging guide (how to run with chaos, logs, etc.)

### CI/CD
- ✅ GitHub Actions workflow green on main
- ✅ Tests run in < 10 minutes (excluding docker startup)
- ✅ HTML reports generated and archived
- ✅ Test results published to PR
- ✅ All services start cleanly in docker-compose

### Performance
- ✅ Injection mode tests complete in < 5s each
- ✅ Real execution mode tests complete in < 10s each
- ✅ Resilience tests complete in < 30s each
- ✅ Full test suite runs in < 10 minutes

### Reliability
- ✅ Tests pass 100% consistently (no flakiness)
- ✅ No event loss in production scenarios
- ✅ Financial invariants always validated
- ✅ Reconnect scenarios work correctly
- ✅ Error messages clear and actionable

### Extensibility
- ✅ Can add new scenarios by adding YAML files
- ✅ Can add new service clients without modifying existing code
- ✅ Can add new assertions to AssertionEngine
- ✅ New team members can run tests following README

---

## Summary

**Total Effort:** ~120-140 engineering hours  
**Timeline:** 6-8 weeks with parallel execution  
**Team:** 3 engineers (1-2 backend, 1 QA, 1 platform)  

**Deliverables:**
1. ✅ Full e2e/ Python module with clients, harness, scenarios
2. ✅ 30+ comprehensive E2E tests (injection + real execution modes)
3. ✅ Resilience & chaos testing framework
4. ✅ Rich HTML reporting with event timelines
5. ✅ GitHub Actions CI/CD integration
6. ✅ Production-ready, extensible test framework

**MVP (Minimum Viable):** 3-4 weeks → 8-10 injection mode tests passing  
**Full System:** 6-8 weeks → complete framework with resilience, observability, CI/CD
