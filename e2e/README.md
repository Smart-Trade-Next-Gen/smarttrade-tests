# SmartTrade E2E Test Framework

Production-grade end-to-end testing for the SmartTrade trading platform.

**Total coverage**: 39 comprehensive tests across 4 test phases

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
# Phase 5: Injection Mode (deterministic, 18 tests)
pytest -m injection -v

# Phase 6: Real Execution (price-driven, 10 tests)
pytest -m real_execution -v

# Phase 7: Resilience (chaos testing, 11 tests)
pytest -m resilience -v

# Quick sanity check (2 tests)
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
│   └── config.py                     # Test configuration (URLs, timeouts)
├── clients/
│   ├── __init__.py
│   ├── bas_client.py                 # Broker Adapter Service REST client
│   ├── mock_client.py                # Mock Service client (fill injection)
│   └── mds_websocket_client.py      # Market Data Service WebSocket client
├── harness/
│   ├── __init__.py
│   ├── event_collector.py            # Async event collection per order_id
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
│   ├── partial_fill_3x.yaml
│   ├── concurrent_orders_2x.yaml
│   └── ...
└── tests/
    ├── __init__.py
    ├── conftest.py                   # Test-level fixtures
    ├── test_order_lifecycle_injection.py        # Phase 5: 4 tests
    ├── test_partial_fills_injection.py          # Phase 5: 3 tests
    ├── test_cancel_orders_injection.py          # Phase 5: 3 tests
    ├── test_error_paths_injection.py            # Phase 5: 5 tests
    ├── test_concurrent_orders_injection.py      # Phase 5: 3 tests
    ├── test_market_buy_real_execution.py        # Phase 6: 4 tests
    ├── test_partial_fills_real_execution.py     # Phase 6: 3 tests
    ├── test_execution_stress_scenarios.py       # Phase 6: 3 tests
    ├── test_resilience_timeouts.py              # Phase 7: 4 tests
    ├── test_resilience_event_handling.py        # Phase 7: 4 tests
    └── test_resilience_partial_failures.py      # Phase 7: 3 tests
```

## Quick Links

- **Test Categorization & CI/CD Strategy**: [TEST_CATEGORIZATION.md](TEST_CATEGORIZATION.md)
- **GitHub Actions Workflow**: [.github/workflows/e2e-tests.yml](../.github/workflows/e2e-tests.yml)
- **Configuration**: [pytest.ini](pytest.ini)
- **Fixtures**: [conftest.py](conftest.py)

## Test Phases Overview

| Phase | Type | Count | Timeout | Purpose |
|-------|------|-------|---------|---------|
| 5 | Injection | 18 | 30s | Deterministic correctness |
| 6 | Real Execution | 10 | 10s | Price-driven execution |
| 7 | Resilience | 11 | 15s | Chaos & recovery |
| Smoke | Critical | 2 | 2min | Quick sanity check |

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

## Key Fixtures

- `bas_client`: BAS REST client
- `mock_client`: Mock fill injection
- `mds_client`: WebSocket events
- `event_collector`: Async event collection
- `assertions`: Order/position validation
- `test_account_id`: Unique test account
- `chaos_engine`: Failure injection (Phase 7)

## Test Markers

```python
@pytest.mark.smoke              # 2 tests
@pytest.mark.injection          # 18 tests
@pytest.mark.real_execution     # 10 tests
@pytest.mark.resilience         # 11 tests
```

## Performance

- **39 total tests**
- **57 min full suite** (parallel-friendly)
- **2 min smoke only**
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
