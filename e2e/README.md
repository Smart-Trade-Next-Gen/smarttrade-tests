# SmartTrade E2E Test Framework

Production-grade end-to-end testing for the SmartTrade trading platform.

**Updated for v4.0 Stateless Architecture** - Broker is source of truth, BAS is stateless

**Total coverage**: 50+ comprehensive tests across 4 test phases

## Quick Start

### Installation

```bash
cd e2e
pip install -r requirements.txt
```

### Run All Tests

```bash
pytest integration/ -v
```

### Run by Test Phase

```bash
# Phase 1: Cross-cutting concerns (architecture boundaries, order lifecycle, financial invariants, RBAC)
pytest -m smoke -v

# Phase 2: Service-specific coverage (BAS, PBS, MDS, Journal, Portfolio, Notification, Strategy)
pytest -m integration -v

# Phase 3: Resilience & chaos (Redis failure, PostgreSQL failure, service restart, network partition)
pytest -m resilience -v

# Phase 4: Performance & stress (order load, quote processing, database performance, Redis stream performance)
pytest -m performance -v
```

## Project Structure

```
e2e/
├── README.md                          # This file
├── requirements.txt                   # Python dependencies
├── pytest.ini                         # pytest configuration
├── conftest.py                        # Global pytest fixtures
├── clients/
│   ├── __init__.py
│   ├── bas_client.py                 # Broker Adapter Service REST client
│   ├── broker_state_client.py        # Broker state client (source of truth)
│   ├── mds_client.py                 # Market Data Service WebSocket client
│   ├── mds_rest_client.py            # MDS REST client (instruments)
│   ├── portfolio_client.py          # Portfolio Service client
│   ├── journal_client.py            # Journal Service client
│   ├── notification_client.py       # Notification Service client
│   ├── strategy_client.py           # Strategy Service client
│   └── redis_client.py              # Redis client (for stream validation)
└── integration/
    ├── conftest.py                   # Integration test fixtures
    ├── cross_cutting/
    │   ├── test_architecture_boundaries.py      # Architecture validation
    │   └── test_rbac_enforcement.py            # RBAC enforcement
    ├── order_lifecycle/
    │   ├── test_order_lifecycle_e2e.py          # Order lifecycle end-to-end
    │   └── test_financial_invariants.py         # Financial invariants validation
    ├── bas/
    │   ├── test_bas_rest_api_comprehensive.py   # BAS REST API comprehensive tests
    │   └── test_bas_redis_trade_events.py      # BAS Redis trade events consumption
    ├── pbs/
    │   ├── test_pbs_execution_logic.py         # PBS execution logic tests
    │   └── test_pbs_concurrency_safety.py      # PBS concurrency safety
    ├── mds/
    │   └── test_mds_quote_production.py         # MDS quote production tests
    ├── journal/
    │   ├── test_journal_redis_consumer.py      # Journal Redis event consumption
    │   └── test_journal_rest_api.py            # Journal REST API tests
    ├── portfolio/
    │   ├── test_portfolio_redis_position_consumer.py  # Portfolio Redis position consumption
    │   └── test_portfolio_rest_api.py          # Portfolio REST API tests
    ├── notification/
    │   ├── test_notification_redis_consumer.py  # Notification Redis event consumption
    │   └── test_notification_rest_api.py       # Notification REST API tests
    ├── strategy/
    │   └── test_strategy_rest_api.py           # Strategy REST API tests
    ├── resilience/
    │   ├── test_redis_failure.py               # Redis failure scenarios
    │   ├── test_postgresql_failure.py          # PostgreSQL failure scenarios
    │   ├── test_service_restart.py             # Service restart scenarios
    │   ├── test_network_partition.py          # Network partition scenarios
    │   └── test_message_ordering.py            # Message ordering guarantees
    └── performance/
        ├── test_order_load.py                  # Order placement load testing
        ├── test_quote_processing.py            # High-frequency quote processing
        ├── test_database_performance.py        # Database query performance
        └── test_redis_stream_performance.py    # Redis stream performance
```

## Quick Links

- **Test Categorization & CI/CD Strategy**: [TEST_CATEGORIZATION.md](TEST_CATEGORIZATION.md)
- **GitHub Actions Workflow**: [.github/workflows/e2e-tests.yml](../.github/workflows/e2e-tests.yml)
- **Configuration**: [pytest.ini](pytest.ini)
- **Fixtures**: [conftest.py](conftest.py)

## Test Phases Overview

| Phase | Type | Count | Timeout | Purpose |
|-------|------|-------|---------|---------|
| 1.1 | Cross-cutting | 3 | 30s | Architecture boundaries validation |
| 1.2 | Order Lifecycle | 7 | 30s | Order lifecycle end-to-end |
| 1.3 | Financial Invariants | 5 | 30s | Financial invariants validation |
| 1.5 | RBAC Enforcement | 4 | 30s | RBAC enforcement tests |
| 2 | Service-Specific | 14 | 30s | Service-specific coverage |
| 3 | Resilience & Chaos | 5 | 60s | Resilience & chaos testing |
| 4 | Performance & Stress | 4 | 60s | Performance & stress testing |
| Smoke | Critical | 5 | 2min | Quick sanity check |

## Running Tests

```bash
# Local: All tests
pytest integration/ -v

# By phase
pytest -m smoke -v          # Critical path tests
pytest -m integration -v    # Service-specific tests
pytest -m resilience -v     # Resilience & chaos tests
pytest -m performance -v    # Performance & stress tests

# By service
pytest integration/bas/ -v          # BAS tests
pytest integration/pbs/ -v          # PBS tests
pytest integration/mds/ -v          # MDS tests
pytest integration/journal/ -v       # Journal tests
pytest integration/portfolio/ -v    # Portfolio tests
pytest integration/notification/ -v # Notification tests
pytest integration/strategy/ -v     # Strategy tests

# With coverage
pytest integration/ --cov=e2e --cov-report=html

# Parallel execution
pytest integration/ -n auto -v
```

## CI/CD Pipeline

GitHub Actions workflow with 4 stages:

1. **Smoke** (2 min) → Block if fail
2. **Service-Specific** (15 min) → Block if fail
3. **Resilience** (10 min) → Warn if fail
4. **Performance** (10 min) → Warn if fail

Total: **37 minutes** for full suite

See [TEST_CATEGORIZATION.md](TEST_CATEGORIZATION.md) for strategy.

## Event Architecture

E2E tests use **Redis Streams** aligned with the v4.0 stateless architecture:

| Stream | Purpose | Events |
|--------|---------|--------|
| **Redis Streams** | Event-driven event collection | `order.updated`, `trade.executed`, `position.updated` |

### Event Flow

1. Test places order via `bas_client.place_order()`
2. Broker processes order and publishes events to Redis Streams
3. Test observes events via Redis stream consumers or service clients
4. Broker state verified via `broker_state_client` (source of truth)

## Key Fixtures

- `bas_client`: BAS REST client (order placement, portfolio queries)
- `pbs_client`: PBS REST client (execution logic, order management)
- `mds_client`: MDS REST client (instruments, quotes)
- `journal_client`: Journal Service client (trades, orders, actions)
- `portfolio_client`: Portfolio Service client (positions, account summary)
- `notification_client`: Notification Service client (alerts, notifications)
- `strategy_client`: Strategy Service client (strategies, decisions)
- `broker_state_client`: Broker state client (source of truth)
- `redis_client`: Redis client (for stream validation)
- `test_account_id`: Unique test account per test

## Test Markers

```python
@pytest.mark.smoke              # Critical path tests
@pytest.mark.integration        # Service-specific tests
@pytest.mark.resilience         # Resilience & chaos tests
@pytest.mark.performance        # Performance & stress tests
```

## Performance

- **50+ total tests**
- **37 min full suite** (parallel-friendly, estimated)
- **2 min smoke only** (estimated)
- **Individual test max**: 60 seconds

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

**Status**: Production-ready | **Coverage**: 50+ E2E tests | **Phases**: 1-4
