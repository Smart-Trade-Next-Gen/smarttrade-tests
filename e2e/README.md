# SmartTrade E2E Test Framework

Production-grade end-to-end testing for the SmartTrade trading platform.

**Updated for v4.0 Stateless Architecture** - Broker is source of truth, BAS is stateless

**Total coverage**: 34 comprehensive tests across 4 test phases (updated from 39)

## Quick Start

### Installation

```bash
cd e2e
pip install -r requirements.txt
```

### Run All Tests

```bash
pytest tests/ -v
```

### Run by Test Phase

```bash
# Phase 5: Injection Mode (deterministic, 13 tests)
pytest -m injection -v

# Phase 6: Real Execution (price-driven, 10 tests) - TODO
pytest -m real_execution -v

# Phase 7: Resilience (chaos testing, 11 tests) - TODO
pytest -m resilience -v

# Quick sanity check (2 tests) - TODO
pytest -m smoke -v
```

## Project Structure

```
e2e/
├── README.md                          # This file
├── requirements.txt                   # Python dependencies
├── pytest.ini                         # pytest configuration
├── TEST_CATEGORIZATION.md            # Test organization and CI/CD strategy
├── conftest.py                        # Global pytest fixtures
├── config/
│   ├── __init__.py
│   └── config.py                     # Test configuration (URLs, timeouts, broker config)
├── clients/
│   ├── __init__.py
│   ├── bas_client.py                 # Broker Adapter Service REST client
│   ├── broker_state_client.py        # Broker state client (NEW - source of truth)
│   ├── mds_client.py                 # Market Data Service WebSocket client
│   ├── mds_rest_client.py            # MDS REST client (instruments)
│   ├── mock_client.py                # Mock Service client (fill injection)
│   ├── portfolio_client.py          # Portfolio Service client
│   └── journal_client.py            # Journal Service client
├── harness/
│   ├── __init__.py
│   ├── event_collector.py            # Async event collection per order_id
│   ├── redis_event_collector.py      # Redis Stream event collector (NEW)
│   ├── assertions.py                 # Order/position/invariant assertions
│   ├── scenario_engine.py            # YAML scenario loading
│   └── scenario_executor.py          # Scenario execution orchestration
├── fixtures/
│   ├── __init__.py
│   ├── logging.py                    # Test logging configuration
│   ├── market_data_stream.py         # Price update injection (Phase 6)
│   └── chaos_engine.py               # Failure injection (Phase 7)
├── scenarios/                         # YAML scenario files
│   ├── market_buy_full_fill.yaml
│   ├── concurrent_orders_2x.yaml
│   └── ...
└── tests/
    ├── __init__.py
    ├── conftest.py                   # Test-level fixtures
    ├── test_order_lifecycle_injection.py        # Phase 5: 4 tests (UPDATED)
    ├── test_cancel_orders_injection.py          # Phase 5: 2 tests (UPDATED)
    ├── test_error_paths_injection.py            # Phase 5: 4 tests (UPDATED)
    ├── test_concurrent_orders_injection.py      # Phase 5: 3 tests (UPDATED)
    ├── test_market_buy_real_execution.py        # Phase 6: 4 tests (TODO)
    ├── test_execution_stress_scenarios.py       # Phase 6: 3 tests (TODO)
    ├── test_resilience_timeouts.py              # Phase 7: 4 tests (TODO)
    ├── test_resilience_event_handling.py        # Phase 7: 4 tests (TODO)
    ├── test_resilience_partial_failures.py      # Phase 7: 3 tests (TODO)
    ├── test_journal_integration.py            # 3 tests (TODO)
    ├── test_portfolio_integration.py          # 3 tests (TODO)
    ├── test_architecture_boundaries.py        # Architecture validation (TODO)
    ├── test_websocket_client_routing.py        # WebSocket separation (TODO)
    ├── test_websocket_separation_live.py      # Live WebSocket tests (TODO)
    └── test_event_bus_validation.py           # Event bus validation (TODO)
```

## Quick Links

- **Test Categorization & CI/CD Strategy**: [TEST_CATEGORIZATION.md](TEST_CATEGORIZATION.md)
- **GitHub Actions Workflow**: [.github/workflows/e2e-tests.yml](../.github/workflows/e2e-tests.yml)
- **Configuration**: [pytest.ini](pytest.ini)
- **Fixtures**: [conftest.py](conftest.py)

## Test Phases Overview

| Phase | Type | Count | Timeout | Purpose |
|-------|------|-------|---------|---------|
| 5 | Injection | 13 | 30s | Deterministic correctness (UPDATED) |
| 6 | Real Execution | 10 | 10s | Price-driven execution (TODO) |
| 7 | Resilience | 11 | 15s | Chaos & recovery (TODO) |
| Smoke | Critical | 2 | 2min | Quick sanity check (TODO) |

## Running Tests

```bash
# Local: All tests
pytest tests/ -v

# By phase
pytest -m smoke -v          # 2 critical tests
pytest -m injection -v      # 18 deterministic tests
pytest -m real_execution -v # 10 price-driven tests
pytest -m resilience -v     # 11 chaos tests

# With coverage
pytest tests/ --cov=e2e --cov-report=html

# Parallel execution
pytest tests/ -n auto -v
```

## CI/CD Pipeline

GitHub Actions workflow with 4 stages:

1. **Smoke** (2 min) → Block if fail
2. **Injection** (10 min) → Block if fail
3. **Real Execution** (15 min) → Warn if fail
4. **Resilience** (30 min) → Warn if fail

Total: **57 minutes** for full suite

See [TEST_CATEGORIZATION.md](TEST_CATEGORIZATION.md) for strategy.

## WebSocket Architecture

E2E tests use **Redis Streams** aligned with the v4.0 stateless architecture:

| Stream | Purpose | Events |
|--------|---------|--------|
| **Redis Streams** | Event-driven event collection | `order.updated.v1`, `trade.executed.v1`, `position.updated.v1` |

### Event Flow

1. Test places order via `bas_client.place_order()`
2. Mock service injects fill via `mock_client.inject_fill()`
3. Broker publishes `order.updated.v1` event to Redis Streams
4. `redis_event_collector` streams event from Redis Streams
5. Test observes via `redis_event_collector.wait_for_completion(order_id)`
6. Broker state verified via `broker_state_client` (source of truth)

## Key Fixtures

- `bas_client`: BAS REST client (order placement, portfolio queries)
- `broker_state_client`: Broker state client (source of truth) - NEW
- `redis_event_collector`: Redis Stream event collector (NEW)
- `mds_client`: MDS WebSocket client (market data stream)
- `mock_client`: Mock service for deterministic fill injection
- `event_collector`: Async event collection (legacy, kept for compatibility)
- `assertions`: Order/position validation (updated with broker state assertions)
- `test_account_id`: Unique test account per test
- `chaos_engine`: Failure injection (Phase 7)

## Test Markers

```python
@pytest.mark.smoke              # 2 tests
@pytest.mark.injection          # 18 tests
@pytest.mark.real_execution     # 10 tests
@pytest.mark.resilience         # 11 tests
```

## Performance

- **34 total tests** (updated from 39)
- **57 min full suite** (parallel-friendly, estimated)
- **2 min smoke only** (estimated)
- **Individual test max**: 15 seconds

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Import error | `export PYTHONPATH=$PWD/e2e:$PYTHONPATH` |
| Timeout | Increase `--timeout=60`, check service connectivity |
| Event loss | Verify Redis/WebSocket, check event collector logs |
| Assertion fail | Review event sequence, check position state |

## Contributing

New tests should:
- Use marker `@pytest.mark.<phase>`
- Follow Arrange → Act → Observe → Assert pattern
- Include docstring with validation goals
- Use existing fixtures
- Execute in < 15 seconds
- Handle async/await properly

---

**Status**: Production-ready | **Coverage**: 39 E2E tests | **Phases**: 5-7
