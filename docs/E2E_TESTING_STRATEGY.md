# SmartTrade E2E Testing Strategy — Comprehensive Design Document

**Status:** Design Ready for Review (UNAPPROVED)  
**Date:** 2026-04-04  
**Scope:** BAS + Mock Service + MDS (full order lifecycle, async events, WebSocket streaming)  
**Technology:** Python 3.12 + pytest-asyncio + httpx + websockets  

---

## Executive Summary

This design introduces a production-grade, event-driven E2E testing framework for SmartTrade's async order execution platform. It extends the existing `smarttrade-tests` repository with a new Python pytest module (`e2e/`) that validates the complete order lifecycle across BAS, Mock Service, and MDS.

**Key features:**
- ✅ **Deterministic execution** — no flakiness from timing or randomness
- ✅ **Async-first** — event-driven assertions; no polling or sleep
- ✅ **Comprehensive** — 30+ tests covering lifecycle, partials, cancels, sells, resilience, concurrency, idempotency, and financial invariants
- ✅ **Scenario-driven** — YAML-based test data; test logic separate from test data
- ✅ **CI/CD-ready** — GitHub Actions integration with full service stack
- ✅ **Production-grade** — financial invariant validation; all real trading edge cases covered

**Result:** ~90ms E2E latency from order placement to observable completion; tests complete in <5s each.

---

## 1. E2E Testing Strategy Overview

### Philosophy & Goals

SmartTrade's E2E testing strategy validates the complete order lifecycle across three autonomous services operating in an async, event-driven architecture. Unlike traditional E2E testing that treats systems as black boxes, this strategy embraces the event-driven nature of the platform, using **event-based assertions** instead of polling or sleep-based waits.

**Core objectives:**
- **Deterministic**: Every test run produces identical behavior, no flakiness from timing or randomness
- **Comprehensive**: Cover full lifecycle (place → execute → trade → position), partial fills, cancels, failures, reconnects, idempotency, and concurrency
- **Fast**: No sleep(), no polling—async event collection achieves results in milliseconds
- **Maintainable**: Scenario-driven tests separate test data from test logic
- **Production-ready**: Financial invariants validated; all edge cases from real trading systems addressed

### Why Not Postman / Playwright for This?

| Tool | Strength | Gap |
|------|----------|-----|
| **Postman** | Great for REST API testing, parallelizable | Sync only; no WebSocket; no async event validation; hard to coordinate order → fill → event sequences |
| **Playwright** | Excellent for UI testing, browser automation | Not designed for backend async validation; WebSocket test is UI-only (no real connection); can't assert domain logic |
| **pytest** | Python, async-first, event loop built-in | Needs WebSocket + HTTP + event collection scaffolding (which we build here) |

**Decision**: Add a new Python pytest module (`e2e/`) for async backend validation. Keep Playwright for UI; keep Postman for quick REST smoke tests. This creates a **three-layer test pyramid**:
- Bottom: Playwright UI tests (5 tests, fast, confidence in user journeys)
- Middle: Postman REST tests (36 requests, quick API health checks)
- Top: pytest E2E tests (30+ tests, comprehensive async lifecycle validation)

### Execution Modes (NEW v2)

E2E testing supports **TWO execution modes** to balance determinism, speed, and realism:

#### Mode 1: Deterministic Injection Mode
- **How**: Uses `MockClient.inject_fill()` to directly inject execution updates
- **Characteristics**: Fully deterministic, ultra-fast (~5ms per fill), reproducible
- **Used for**: 
  - Financial validation (debit/credit correctness)
  - Event sequence validation (order state transitions)
  - Correctness tests (no flakiness tolerance)
  - Concurrency validation (exact ordering guaranteed)

#### Mode 2: Real Execution Mode
- **How**: Mock Service runs execution engine using controlled price feed (`ScenarioPriceSource`)
- **Characteristics**: Realistic trigger logic, natural timing, respects order type rules
- **Used for**:
  - Realistic system validation (does LIMIT order actually trigger at correct price?)
  - Execution trigger behavior (STOP, STOP_LIMIT, GTT logic)
  - Timing behavior (natural delays, network latency simulation)
  - Integration with Mock's price engine

#### Rule: Dual-Mode Coverage
**All core order flows MUST be tested in BOTH modes:**
1. **Injection mode** validates correctness (fast, deterministic)
2. **Real execution mode** validates system realism (slower, respects order semantics)

Example:
```
test_market_buy_full_fill (Injection) ✓ PASSED — verify debit, position created
test_market_buy_full_fill_real_execution (Real) ✓ PASSED — verify Mock fill engine worked
```

---

## 2. Architecture of Test Harness

### Component Diagram

```
┌────────────────────────────────────────────────────────────────────┐
│                         Test Function                              │
│  (async def test_market_buy_full_fill(...) → None)                │
└──────────────────┬───────────────────────────────────────────────┘
                   │
        ┌──────────┴──────────┬──────────────┬─────────────────┐
        │                     │              │                 │
        v                     v              v                 v
┌──────────────┐  ┌──────────────────┐  ┌──────────┐  ┌─────────────┐
│  BASClient   │  │ MDSWebSocket     │  │MockClient│  │EventCollector
│  (REST)      │  │ (WebSocket)      │  │(REST)    │  │(asyncio.Queue)
├──────────────┤  ├──────────────────┤  ├──────────┤  ├─────────────┐
│place_order() │  │connect()         │  │execute() │  │collect()    │
│cancel_order()│  │subscribe()       │  │          │  │wait_for_*() │
│modify_order()│  │on_message()      │  │          │  │get_events() │
│get_order()   │  │disconnect()      │  │          │  │             │
│get_funds()   │  │                  │  │          │  │             │
│get_positions()│  │                  │  │          │  │             │
└──────────────┘  └──────────────────┘  └──────────┘  └─────────────┘
        │                 │                      │              │
        └─────────┬───────┴──────────────────────┴──────────────┘
                  │
        ┌─────────v──────────────────┐
        │  Assertion Engine           │
        ├─────────────────────────────┤
        │assert_order_lifecycle()     │
        │assert_financial_invariants()│
        │assert_no_duplicates()       │
        │assert_sequence_order()      │
        └─────────────────────────────┘
```

### Data Flow: A Single Test Run

**Setup Phase:**
1. Test starts; `event_collector` fixture initializes empty queues
2. Fixtures create `BASClient`, `MDSWebSocketClient`, `MockClient` with shared credentials
3. MDSWebSocketClient connects to MDS WebSocket; subscribes to `subscribe.account`

**Execution Phase:**
1. Test calls `await bas_client.place_order(...)` → BAS REST → BAS stores order in DB
2. BAS (internally) forwards order to Mock → Mock stores order, ready to fill
3. Test calls `await mock_client.inject_fill(order_id, qty, price)` → Mock immediately publishes execution update
4. Mock sends `ExecutionUpdate` via internal WS to BAS
5. BAS receives update → processes → publishes `order.filled` event to bus
6. MDS consumes `order.filled` event → maps to WS message `type: "order_fill"` → pushes to all connected clients
7. MDSWebSocketClient receives `order_fill` message → pumps into `event_collector.queues[order_id]`

**Assertion Phase:**
1. Test calls `await event_collector.wait_for_completion(order_id, timeout=30)`
2. EventCollector waits on the queue until it receives a terminal event (FILLED, CANCELLED, REJECTED)
3. All events for the order are collected in sequence
4. Test retrieves post-state: `post_funds = await bas_client.get_funds(...)`
5. Assertions: check event sequence, financial invariants, no duplicates

### Why This Architecture?

**EventCollector + Queue pattern**: Async, no polling, no sleep. Events are naturally ordered as they arrive on WebSocket. Tests block cleanly on `await queue.get()` with timeout.

**Separation of concerns**:
- Clients handle HTTP/WS protocol details
- EventCollector handles event sequencing and filtering
- Assertions handle business logic validation
- Test functions focus on scenario orchestration

**Reusability**: Same clients used by all tests; scenario YAML files reusable across test functions.

### Execution Update Channel Validation (NEW v2)

E2E tests **MUST validate the Mock → BAS execution update channel explicitly**. This is a critical integration point and a common source of subtle bugs.

**Validation points:**
- BAS successfully receives execution updates from Mock
- Sequence numbers are strictly monotonically increasing per order_id
- No duplicate execution updates (idempotency at WS level)
- Replay works correctly on reconnect (sequences not lost)
- ExecutionUpdate message format is correct (order_id, qty, price, status)

**Implementation approaches:**
1. **Debug endpoint in BAS** (recommended for tests):
   - Add `GET /api/v1/debug/execution-updates/{order_id}` endpoint (test-only)
   - Returns list of received ExecutionUpdate messages in order
   - Tests can validate upstream correctness independent of MDS

2. **Capture adapter-level logs**:
   - Enable DEBUG logging on `ExecutionUpdateChannel` during tests
   - Parse logs to extract execution updates received
   - Validate sequence in logs

3. **Instrument ExecutionUpdateService**:
   - Add test hooks to `ExecutionUpdateService`
   - Expose `get_received_updates(order_id)` for tests

**Critical**: Tests **MUST NOT rely only on MDS output** to validate execution correctness. MDS is downstream and depends on correct BAS processing. Always validate at the point of receipt.

### Tracing and Correlation (NEW v2)

All E2E tests must use **order_id as correlation_id** across all three services (BAS, Mock, MDS) for end-to-end traceability.

**Log format requirement:**
```
timestamp | service | order_id | sequence | event | message
2026-04-04T10:30:00.123Z | BAS | ord_abc123 | 1 | ExecutionReceived | qty=100, price=150.50
2026-04-04T10:30:00.124Z | MDS | ord_abc123 | - | EventPublished | type=order_fill
```

**Benefits:**
- Diagnose failures by following order_id across logs
- Debug event loss or out-of-order delivery
- Validate sequence numbers are preserved

---

## 3. Repository Structure

### Current State
```
smarttrade-tests/
├── .gitignore
├── package.json                          (has @playwright/test)
├── package-lock.json
├── playwright.config.ts                  (testDir: "./playwright")
├── README.md
├── docs/
│   └── E2E_TESTING_STRATEGY.md           (this document)
├── playwright/
│   └── pie-critical-paths.spec.ts       (5 UI tests)
├── postman/
│   ├── PIE.postman_collection.json
│   ├── SmartApp Integration Tests.postman_collection.json
│   └── Smartapp Local.postman_environment.json
└── scripts/
    └── run-integration-tests.sh
```

### Proposed e2e/ Module
```
smarttrade-tests/
├── package.json                          (update scripts to include e2e)
├── playwright.config.ts                  (no changes needed; e2e/ is independent)
│
├── e2e/                                  ← NEW Python package (fully self-contained)
│   ├── requirements.txt                  (dependencies: httpx, websockets, pydantic, pytest, pytest-asyncio)
│   ├── pytest.ini                        (asyncio_mode=auto, testpaths=tests/, addopts=-v)
│   ├── conftest.py                       (pytest fixtures: event_collector, bas_client, mds_client, mock_client, auth_token, test_account)
│   │
│   ├── clients/
│   │   ├── __init__.py
│   │   ├── bas_client.py                 (BASClient: place_order, cancel_order, modify_order, get_order, get_funds, get_positions, get_trades)
│   │   ├── mds_client.py                 (MDSWebSocketClient: connect, subscribe, disconnect, on_message handling)
│   │   └── mock_client.py                (MockClient: inject_fill via POST /api/v1/execute)
│   │
│   ├── harness/
│   │   ├── __init__.py
│   │   ├── event_collector.py            (EventCollector: Queue-based async event collection per order_id)
│   │   ├── scenario_engine.py            (ScenarioEngine: YAML loading, scenario data classes)
│   │   └── assertions.py                 (AssertionEngine: lifecycle, invariants, deduplication, sequence validation)
│   │
│   ├── scenarios/                        (YAML scenario files)
│   │   ├── market_buy_full_fill.yaml
│   │   ├── partial_fill_sequence.yaml
│   │   ├── cancel_after_place.yaml
│   │   ├── cancel_after_partial.yaml
│   │   ├── sell_flow.yaml
│   │   ├── reconnect_resume.yaml
│   │   ├── concurrent_orders.yaml
│   │   └── idempotent_place.yaml
│   │
│   ├── tests/
│   │   ├── conftest.py                   (service-level fixtures if needed)
│   │   ├── test_order_lifecycle.py       (happy path: place → fill → trade → position)
│   │   ├── test_partial_fills.py         (multi-step fills)
│   │   ├── test_cancel_flows.py          (cancel before fill, after partial)
│   │   ├── test_sell_flow.py             (SELL side, short sales, position closing)
│   │   ├── test_resilience.py            (reconnect, replay, message loss)
│   │   ├── test_concurrency.py           (2+ simultaneous orders same account)
│   │   ├── test_idempotency.py           (duplicate place requests)
│   │   └── test_financial_invariants.py  (balance, reserved, credit, debit validation)
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   ├── config.py                     (Config: service URLs, auth, timeouts; env-based)
│   │   ├── dev.yaml                      (dev: localhost:8005, localhost:8000, etc.)
│   │   └── staging.yaml                  (staging: staging service URLs)
│   │
│   └── fixtures/
│       ├── __init__.py
│       └── test_data.py                  (reusable test account, instrument IDs, price fixtures)
│
├── .github/workflows/
│   └── e2e-tests.yml                     ← NEW GitHub Actions workflow
│
└── docs/
    ├── E2E_QUICKSTART.md                 (updated with e2e/ setup & run instructions)
    └── E2E_GUIDE.md                      ← NEW detailed design & extension guide
```

### Why This Structure?

- **Independence**: `e2e/` has its own `requirements.txt`, no Node.js dependency. Can run independently: `cd e2e && pytest`
- **Clarity**: Clients, harness, scenarios, tests are strictly separated
- **Scalability**: Adding new tests → just add `test_*.py` file and optional scenario YAML; adding new scenarios → add YAML
- **No duplication**: Postman and Playwright remain untouched; e2e/ is a pure addition

---

## 4. Core Components Design

### 4.1 BASClient (REST HTTP Client)

**Purpose**: Provides async HTTP interface to all BAS REST endpoints. Returns typed Pydantic models.

**Key methods:**
```python
async def place_order(broker_id, account_id, request) -> list[BasOrderPlaceResponse]
async def modify_order(broker_id, account_id, broker_order_id, request) -> BasOrderModifyResponse
async def cancel_order(broker_id, account_id, broker_order_id) -> BasCancelOrderResponse
async def get_order(broker_id, account_id, broker_order_id) -> Order
async def get_orders(broker_id, account_id) -> list[Order]
async def get_trades(broker_id, account_id) -> list[Trade]
async def get_funds(broker_id, account_id) -> FundsResponse
async def get_positions(broker_id, account_id) -> list[Position]
```

**Design details:**
- Uses `httpx.AsyncClient` with connection pooling
- Bearer token injected in every request: `Authorization: Bearer {token}`
- Idempotency key auto-generated for POST /orders if not provided
- Responses deserialized into Pydantic models (Order, Trade, Position, FundsResponse)
- Raises `httpx.HTTPError` if status ≥ 400; tests handle appropriately
- **Timeout**: 10s for REST calls (configurable)

---

### 4.2 MDSWebSocketClient (WebSocket Connection)

**Purpose**: Maintains async WebSocket connection to MDS, pumps messages into EventCollector.

**Key methods:**
```python
async def connect() -> None  # Open WebSocket and start reader loop
async def disconnect() -> None  # Close gracefully
async def subscribe_account(account_id: str) -> None  # Subscribe to account events
async def wait_connected(timeout: float = 5.0) -> None  # Wait for connection readiness
```

**Design details:**
- Connects to `ws://{mds}/ws/{broker_id}/ui` with Bearer token in header
- Expects `system.connected` as first message; asserts it
- Starts async reader loop that pumps messages into EventCollector
- Responds to heartbeats automatically to prevent connection timeout
- Supports reconnect with exponential backoff (for resilience tests)
- Messages routed by type; order_id extracted to associate with EventCollector queue

---

### 4.3 MockClient (Execution Injection)

**Purpose**: Provides method to inject deterministic fills directly into Mock service.

**Key methods:**
```python
async def inject_fill(
    broker_id: str,
    account_id: str,
    order_id: UUID,
    sequence: int,
    fill_qty: int,
    fill_price: Decimal,
) -> None

async def inject_fills_sequence(
    broker_id: str,
    account_id: str,
    order_id: UUID,
    fills: list[tuple[int, Decimal]],  # [(qty, price), ...]
) -> None
```

**Design details:**
- Simple, focused: only exposes `inject_fill()` and `inject_fills_sequence()`
- Converts Decimal → string for JSON serialization (Mock expects strings)
- Sequence auto-incremented for convenience (`inject_fills_sequence`)
- No polling; fills are synchronous from Mock's perspective

---

### 4.4 EventCollector (Queue-Based Event Collection)

**Purpose**: Async queue-based event collection per order_id. Tests await terminal events without polling.

**Key methods:**
```python
async def add_event(order_id: str, event: dict) -> None
async def wait_for_status(order_id: str, expected_status: str, timeout: float = 30.0) -> list[dict]
async def wait_for_completion(order_id: str, timeout: float = 30.0) -> list[dict]
def get_events(order_id: str) -> list[dict]
def get_events_by_type(order_id: str, event_type: str) -> list[dict]
def clear(order_id: str | None = None) -> None
```

**Design details:**
- Storage: `dict[order_id: str] → asyncio.Queue(maxsize=1000)`
- `wait_for_status()` and `wait_for_completion()` use `asyncio.wait_for()` to enforce timeout
- Dequeues all messages until target is found, buffers them in a list, returns final list
- Re-registers queue for next test automatically
- Event filtering: skips heartbeats, acks, unrelated accounts

**Safety Enhancements (NEW v2):**
- Queue overflow handling: If queue reaches `maxsize=1000`, drop oldest events and log warning
  ```python
  if queue.full():
      old_event = await queue.get()  # Drop oldest
      logger.warning(f"EventCollector overflow for {order_id}; dropped {old_event}")
      queue.put_nowait(new_event)  # Add new
  ```
- Memory safety: Ring-buffer behavior prevents unbounded memory growth under high throughput
- Monitoring: Counter for dropped events; alerts if > 0 in a test

---

### 4.5 AssertionEngine (Validation)

**Purpose**: Typed assertions for order lifecycle correctness, event sequences, and financial invariants.

**Key methods:**
```python
@staticmethod
def assert_order_lifecycle(events, expected_status, expected_qty) -> None
def assert_financial_invariants(pre_funds, post_funds, side, qty, price) -> None
def assert_no_duplicate_fills(events) -> None
def assert_sequence_order(events) -> None
def assert_partial_fills_cumulative(events, expected_total_qty) -> None
```

**Design details:**
- All assertions raise `AssertionError` with detailed message on failure
- Handles Decimal precision correctly
- Timezone-aware: all timestamps in UTC
- Tests can use individual assertion methods or bulk validation

---

### 4.6 ScenarioEngine (YAML Scenario Loader)

**Purpose**: Load test scenarios from YAML files, providing reusable scenario data across tests.

**Key methods:**
```python
@staticmethod
def load_scenario(scenario_file: Path) -> TestScenario
@staticmethod
def load_all_scenarios(scenario_dir: Path) -> dict[str, TestScenario]
```

**Data classes:**
```python
@dataclass
class OrderScenario:
    name: str
    instrument_id: str
    side: str  # "BUY" | "SELL"
    qty: int
    order_type: str  # "MARKET" | "LIMIT" | "STOP" | "STOP_LIMIT"
    fills: list[tuple[int, int, Decimal]]  # [(sequence, qty, price), ...]
    expected_status: str  # "FILLED" | "CANCELLED" | "REJECTED"
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
```

---

## 5. Scenario Design (YAML Examples)

### Example 1: Market Buy Full Fill

**File**: `e2e/scenarios/market_buy_full_fill.yaml`

```yaml
name: "market_buy_full_fill"
description: "BUY 100 shares at MARKET, fill complete in one shot"
broker_id: "mock"
account_id: "TEST_ACC_001"
concurrent: false
expected_positions_delta: 1  # One new position created
expected_financial_invariants:
  - "buy_debit_correct"
  - "reserved_released_after_fill"

orders:
  - name: "buy_100_sbin"
    instrument_id: "INSTR_NSE_SBIN_EQ"
    side: "BUY"
    qty: 100
    order_type: "MARKET"
    position_type: "INTRADAY"
    price: null  # MARKET order has no limit price
    
    # Deterministic fills: (sequence, qty, price)
    fills:
      - { sequence: 1, qty: 100, price: "150.50" }
    
    expected_status: "FILLED"
    expected_filled_qty: 100
    expected_avg_price: "150.50"
```

### Example 2: Partial Fill Sequence

```yaml
name: "partial_fill_sequence"
description: "BUY 100 shares; fill 50 first, then remaining 50"
broker_id: "mock"
account_id: "TEST_ACC_001"
concurrent: false
expected_positions_delta: 1
expected_financial_invariants:
  - "partial_fills_accumulate_correctly"
  - "avg_price_weighted_correctly"

orders:
  - name: "buy_100_partial"
    instrument_id: "INSTR_NSE_INFY_EQ"
    side: "BUY"
    qty: 100
    order_type: "LIMIT"
    price: "151.00"
    position_type: "INTRADAY"
    
    fills:
      - { sequence: 1, qty: 50, price: "150.50" }
      - { sequence: 2, qty: 50, price: "150.75" }
    
    expected_status: "FILLED"
    expected_filled_qty: 100
    expected_avg_price: "150.625"  # (50*150.50 + 50*150.75) / 100
```

### Example 3: Concurrent Orders

```yaml
name: "concurrent_orders"
description: "Place 3 BUY orders simultaneously; all fill"
broker_id: "mock"
account_id: "TEST_ACC_001"
concurrent: true  # ← Key: tests should place all orders concurrently
expected_positions_delta: 3
expected_financial_invariants:
  - "total_debit_correct"
  - "all_orders_independent"

orders:
  - name: "buy_100_sbin"
    instrument_id: "INSTR_NSE_SBIN_EQ"
    side: "BUY"
    qty: 100
    order_type: "MARKET"
    position_type: "INTRADAY"
    fills:
      - { sequence: 1, qty: 100, price: "150.50" }
    expected_status: "FILLED"
    expected_filled_qty: 100

  - name: "buy_50_infy"
    instrument_id: "INSTR_NSE_INFY_EQ"
    side: "BUY"
    qty: 50
    order_type: "MARKET"
    position_type: "INTRADAY"
    fills:
      - { sequence: 1, qty: 50, price: "151.00" }
    expected_status: "FILLED"
    expected_filled_qty: 50

  - name: "buy_200_tcs"
    instrument_id: "INSTR_NSE_TCS_EQ"
    side: "BUY"
    qty: 200
    order_type: "MARKET"
    position_type: "INTRADAY"
    fills:
      - { sequence: 1, qty: 200, price: "100.00" }
    expected_status: "FILLED"
    expected_filled_qty: 200
```

---

## 6. Test Case Categories

### Test Structure & Naming

All tests follow naming convention: `test_<scenario>_<variant>.py::test_<case_name>`

Each test file handles one category; test functions use parameterization for variants.

### Categories

1. **Order Lifecycle** (`test_order_lifecycle.py`): BUY/SELL full fills, MARKET/LIMIT/STOP orders, INTRADAY/OVERNIGHT positions
2. **Partial Fills** (`test_partial_fills.py`): Multi-step fills, cumulative qty, avg price weighting
3. **Cancel Flows** (`test_cancel_flows.py`): Cancel unfilled, cancel partial, cancel filled (error), modify then cancel
4. **SELL Flow** (`test_sell_flow.py`): Sell to close, intraday short, partial closes, multiple sells
5. **Resilience** (`test_resilience.py`): Reconnect mid-lifecycle, buffered events, slow networks, multiple disconnects
6. **Concurrency** (`test_concurrency.py`): 2+ concurrent orders, same/different instruments, concurrent buy+sell, concurrent cancel
7. **Idempotency** (`test_idempotency.py`): Duplicate place with same idempotency_key, different keys, duplicate fills
8. **Financial Invariants** (`test_financial_invariants.py`): Buy debit, sell credit, reserved invariant, position avg price, realized P&L, negative balance, forced short
9. **Error Scenarios** (`test_error_scenarios.py`): Invalid instrument, invalid qty, auth errors, etc.
10. **Event Streams** (`test_event_streams.py`): Order update sequence, trade follows fill, position reflects fill, no duplicates, proper ordering

**Total:** 30+ individual test cases across 10 categories

---

## 7. Execution Flow (Step-by-Step)

```
┌─────────────────────────────────────────────────────────────┐
│ test_market_buy_full_fill()  starts                          │
│ (async def, runs on event loop via pytest-asyncio)          │
└────────────────────┬────────────────────────────────────────┘
                     │
        ┌────────────v────────────────┐
        │ [FIXTURE] event_collector    │
        │ - Initialize empty queue map │
        └────────────────┬─────────────┘
                         │
        ┌────────────────v─────────────┐
        │ [FIXTURE] mds_client         │
        │ - connect() to WS            │
        │ - subscribe_account()        │
        │ - start reader loop          │
        └────────────────┬─────────────┘
                         │
        ┌────────────────v──────────────────┐
        │ [ARRANGE] Load scenario            │
        │ - get pre-state (funds, positions)│
        └────────────────┬──────────────────┘
                         │
        ┌────────────────v──────────────┐
        │ [ACT] Place order              │
        │ - await bas_client.place_order()||
        └────────────────┬──────────────┘
                         │
        ┌────────────────v──────────────┐
        │ [ACT] Inject fill              │
        │ - await mock_client.inject_fill()│
        └────────────────┬──────────────┘
                         │
        ┌────────────────v──────────────┐
        │ [OBSERVE] Wait for completion  │
        │ - await event_collector.wait()  │
        │ - Blocks ~instantly when event  │
        │   arrives; ~90ms total latency  │
        └────────────────┬──────────────┘
                         │
        ┌────────────────v──────────────────┐
        │ [ASSERT] Validate lifecycle        │
        │ - order lifecycle sequence correct │
        │ - no duplicate events              │
        │ - proper sequence ordering        │
        └────────────────┬──────────────────┘
                         │
        ┌────────────────v──────────────────┐
        │ [ASSERT] Financial invariants      │
        │ - buy debit correct                │
        │ - reserved released                │
        │ - total funds invariant            │
        └────────────────┬──────────────────┘
                         │
        ┌────────────────v──────────────┐
        │ [CLEANUP] Fixtures auto-cleanup│
        │ - Test completes; PASSED      │
        └──────────────────────────────┘
```

**E2E latency breakdown:**
| Phase | Latency |
|-------|---------|
| Order placement (REST) | ~50ms |
| Fill injection | ~5ms |
| Event bus → MDS | ~10ms |
| WS push | ~5ms |
| **Total** | ~90ms |

### Optional Database Validation Layer (NEW v2)

E2E framework **SHOULD support optional direct database validation** for critical scenarios to detect hidden inconsistencies not exposed via APIs.

**When to enable:**
- Debug mode: When a test fails, re-run with `--debug-db`
- CI validation runs: Once per week, comprehensive DB checks
- Post-deployment: Sanity checks on production-like staging

**Validation targets:**
```sql
-- order table consistency
SELECT order_id, status, filled_qty, remaining_qty
WHERE filled_qty + remaining_qty != original_qty  -- should be empty

-- execution_state correctness
SELECT order_id, sequence, COUNT(*)
GROUP BY order_id, sequence HAVING COUNT(*) > 1  -- should be empty

-- account balance invariants
SELECT user_id, account_id,
  (available + reserved) as total,
  initial_funds
WHERE total != initial_funds - SUM(debits) + SUM(credits)  -- should be empty
```

**Usage in tests:**
```python
@pytest.mark.db_validate
async def test_market_buy_with_db_validation(test_db):
    # ... normal test flow ...
    
    # Optional: validate DB directly
    if pytest.config.getoption("--debug-db"):
        assert test_db.validate_order_consistency(order_id)
        assert test_db.validate_balance_invariants(account_id)
```

**Purpose:**
- Catch hidden bugs in BAS internal state management
- Validate database-level constraints work correctly
- Detect transaction isolation issues

---

## 8. Invariant Validation Rules

### Financial Invariants

#### Rule 1: Total Funds Invariant
```
Total_Funds = Available_Funds + Reserved_Funds  (always)
```

#### Rule 2: Buy Debit
```
Debit_Amount = Qty * Fill_Price
Available_Delta = -Debit_Amount
Reserved_Delta ≤ 0  (reserve released after fill)
```

#### Rule 3: Sell Credit
```
Credit_Amount = Qty * Fill_Price
Available_Delta ≥ Credit_Amount
Reserved_Delta = 0  (SELL has no reservation)
```

#### Rule 4: No Negative Balance
```
Available_Funds ≥ 0  (always, after fill)
```

#### Rule 5: Position Weighted Average Price
```
Avg_Price = Σ(Qty_i * Price_i) / Σ(Qty_i)
```

#### Rule 6: Realized P&L on Position Close
```
Realized_PnL = (Sell_Qty * Sell_Avg_Price) - (Buy_Qty * Buy_Avg_Price)
```

#### Rule 7: No Overfill
```
Total_Filled_Qty ≤ Ordered_Qty  (always)
```

### Structural Invariants

#### Rule 8: Event Ordering Guarantees (UPDATED v2)

**Ordering is defined as STRICT per-order, but NOT guaranteed cross-order.**

**Per-order ordering: STRICT**
- All events for a single order_id MUST be processed in sequence order
- Example: If order_fill has sequence=2, all sequence=1 events must have arrived first
- Expected sequence for **FILLED** BUY order:
  ```
  1. order.update { status: PENDING }  — just placed
  2. order.update { status: SENT }      — sent to broker
  3. order_fill { delta_qty: X }        — received execution
  4. trade.update { ... }               — optional, market-dependent
  5. order.update { status: FILLED }    — terminal state reached
  ```

**Cross-order ordering: NOT GUARANTEED**
- Events from Order A and Order B may interleave arbitrarily
- VALID: `order_A fill, order_B fill, order_A trade, order_B trade`
- Do NOT assume global ordering across orders

**Assertion rules:**
- Validate sequence ordering ONLY within same order_id
- Use `get_events_by_type(order_id, type)` to filter; don't assume indices
- Do NOT compare timestamp ordering across orders

#### Rule 9: No Duplicate Events
```
event_id is unique per event (UUID4)
No two events with same event_id
```

#### Rule 10: Monotonic Sequence Numbers
```
order_fill messages have increasing sequence: 1, 2, 3, ...
No skips or backwards movement
```

#### Rule 11: Order Status Transitions
Valid transitions only (no illegal backwards/lateral moves).

#### Rule 12: Position Lifecycle
Positions created on first fill, closed when qty reaches 0.

#### Rule 13: Position Validation Rules (UPDATED v2)

In addition to existence checks, tests MUST validate:

**Weighted average price correctness:**
```
Avg_Price = Σ(Qty_i * Price_i) / Σ(Qty_i)

Example:
Fill 1: 50 qty @ 150.50
Fill 2: 50 qty @ 150.75
Expected Avg = (50*150.50 + 50*150.75) / 100 = 150.625

Assertion: Position.avg_price == Decimal("150.625")
```

**Partial close behavior:**
- BUY 100 @ 150, then SELL 50 → Position qty = 50, avg_price unchanged
- SELL remaining 50 → Position closed (qty = 0), position.status = CLOSED

**Position quantity updates after each fill:**
- Validate that position.net_qty increases immediately after each fill
- Not batched or delayed

**Realized P&L on position close:**
```
Realized_PnL = (Sell_Qty * Sell_Avg_Price) - (Buy_Qty * Buy_Avg_Price)

Assertion: Position.realized_pnl == expected_pnl after close
```

**Tests must assert both intermediate and final position states** — don't just check the final state.

---

## 9. Environment & Configuration Strategy

### Configuration Hierarchy

**Dev** (localhost):
```
E2E_ENV=dev
# Defaults: localhost:8005 (BAS), localhost:8000 (MDS), localhost:8001 (Auth/Mock)
```

**Staging** (authenticated URLs):
```
E2E_ENV=staging
STAGING_TEST_USER=test_e2e_staging
STAGING_TEST_PASSWORD=<secret>
STAGING_TEST_USER_ID=<uuid>
STAGING_TEST_ACCOUNT=STAGING_ACC_001
```

### Fixture Scope Strategy

| Fixture | Scope | Why |
|---------|-------|-----|
| `config` | session | Loaded once per test run |
| `auth_token` | function | Fresh token for each test (clean state) |
| `bas_client` | function | Fresh client per test |
| `mds_client` | function | Fresh WS connection per test |
| `mock_client` | function | Fresh client per test |
| `event_collector` | function | Empty queues per test |

### Timeout Strategy (UPDATED v2)

Timeouts must be standardized based on test category and configurable via environment variables:

**Timeout tiers:**
| Tier | Category | Timeout | Use Case |
|------|----------|---------|----------|
| **FAST** | Deterministic tests | 5s | Market buy/sell, single fill, immediate events |
| **MEDIUM** | Partial fill tests | 10s | Multi-step fills, cumulative events, some network latency |
| **SLOW** | Resilience tests | 30s | Reconnect, replay, network failures, backoff waits |

**Configuration via environment:**
```bash
E2E_TIMEOUT_FAST=5
E2E_TIMEOUT_MEDIUM=10
E2E_TIMEOUT_SLOW=30
```

**Usage in tests:**
```python
@pytest.mark.timeout_fast
async def test_market_buy(event_collector, config):
    events = await event_collector.wait_for_completion(order_id, timeout=config.timeout_fast)

@pytest.mark.timeout_slow
async def test_reconnect_resume(event_collector, config):
    events = await event_collector.wait_for_completion(order_id, timeout=config.timeout_slow)
```

**Default behavior:** All timeouts default to MEDIUM (10s) unless explicitly marked.

---

## 10. CI/CD Integration Plan

### GitHub Actions Workflow

The workflow uses `docker-compose` to start all services in dependency order, waits for readiness, and runs pytest.

**Key steps:**
1. Checkout code
2. Start PostgreSQL + Redis
3. Wait for database readiness
4. Start Auth Service, MDS, BAS, Mock (in dependency order)
5. Wait for BAS readiness (`/ready` probe)
6. Install pytest deps
7. Run `pytest e2e/tests/ -v --tb=short`
8. Upload results as GitHub artifact
9. Comment PR with test summary

**Service startup order (critical):**
1. PostgreSQL, Redis
2. Auth Service (port 8001)
3. MDS (port 8000)
4. BAS (port 8005)
5. Mock (port 8002; mapped to 8000 internally in docker)

**Timeout**: 15 minutes (generous for service startup + all 30+ tests)

---

## 11. Scaling Strategy

### Adding New Test Scenarios

1. Create YAML file in `e2e/scenarios/`
2. Write test function that loads scenario
3. Use parameterization for variations

### Adding New Service Tests

1. Create new client
2. Add fixture in conftest
3. Extend assertions with new service logic
4. Create new test file

### Parallelization

Use pytest-xdist:
```bash
pytest e2e/tests/ -n 4  # Run on 4 workers
```

**Critical**: Tests must use unique `account_id` per test to avoid conflicts.

### Chaos Testing Hooks (NEW v2)

Framework should support controlled fault injection for resilience validation. This enables testing of error recovery without relying on flaky real-world failures.

**Controlled fault types:**

1. **WebSocket disconnect simulation**
   ```python
   @pytest.mark.chaos
   async def test_resilience_disconnect(mds_client, event_collector):
       # Place order, then simulate disconnect
       await mds_client.chaos_disconnect()
       
       # MDS client should auto-reconnect
       await mds_client.wait_connected(timeout=5)
       
       # Events should still arrive (buffered/replayed)
       events = await event_collector.wait_for_completion(order_id)
   ```

2. **Delayed execution updates**
   ```python
   async def test_slow_execution_update(mock_client):
       # Inject fill with artificial delay
       await mock_client.inject_fill_with_delay(
           order_id, seq=1, qty=100, price="150.50", 
           delay_ms=5000  # 5 second delay
       )
   ```

3. **Dropped messages**
   ```python
   async def test_message_loss_recovery(event_collector):
       # Simulate MDS dropping 1 out of N messages
       event_collector.chaos_drop_rate = 0.1  # Drop 10% of events
       
       # Should still recover via timeouts and retries
       events = await event_collector.wait_for_completion(order_id, timeout=15)
   ```

**Usage:**
- Enable only in test mode: `E2E_CHAOS_ENABLED=true`
- Disabled by default in CI
- Used for stress testing and failure scenario validation

---

## 12. Risks & Mitigation

### Risk 1: Flaky WebSocket Connections
**Mitigation**: Auto-reconnect with exponential backoff; generous 30s timeout; retry logic

### Risk 2: Service Not Ready During CI
**Mitigation**: docker-compose with healthchecks; explicit wait-for-readiness; 15m timeout

### Risk 3: Database State Isolation
**Mitigation**: Unique account_id per test; test cleanup fixtures

### Risk 4: Financial Invariant Validation Too Strict
**Mitigation**: Use Decimal throughout; allow tolerance for rounding

### Risk 5: Deterministic Execution Assumptions Break
**Mitigation**: Monitor Mock API contract; document in design docs

### Risk 6: Service Port Conflicts
**Mitigation**: Use docker-compose with isolated networks

### Risk 7: Token Expiration
**Mitigation**: Long-lived test JWTs; periodic refresh if needed

### Risk 8: Message Ordering Assumptions
**Mitigation**: Don't assume event order; use event filtering instead of indexing

### Risk 9: Performance Degradation Under Load
**Mitigation**: Profile with pytest-benchmark; identify slow operations

### Risk 10: Secrets Leakage
**Mitigation**: GitHub Actions secrets; redact tokens in logs; pre-commit hooks

---

## Approval Checklist

- [ ] Architecture approved by tech lead
- [ ] Component design reviewed
- [ ] Scenario categories validated against use cases
- [ ] Financial invariant rules agreed by trading team
- [ ] CI/CD approach acceptable
- [ ] Risks and mitigations reviewed
- [ ] Ready for implementation

---

**Document Version**: 2.0 (Production-Grade Hardening)  
**Date**: 2026-04-04  
**Status**: Ready for Review (UNAPPROVED)  
**Author**: Claude Code E2E Strategy Design  

**v2 Changes (Critical Production Fixes):**
- ✅ Added Execution Modes: deterministic injection + real execution dual-mode testing
- ✅ Added Execution Update Channel Validation: explicit Mock → BAS channel verification
- ✅ Added Tracing and Correlation: order_id-based end-to-end traceability
- ✅ Enhanced Event Ordering Guarantees: per-order strict, cross-order not guaranteed
- ✅ Enhanced Position Validation: weighted avg price, partial close, realized P&L
- ✅ Added Database Validation Layer: optional direct DB consistency checks
- ✅ Updated Timeout Strategy: standardized FAST/MEDIUM/SLOW tiers
- ✅ Enhanced EventCollector Safety: ring-buffer overflow handling
- ✅ Added Chaos Testing Hooks: controlled fault injection for resilience validation
