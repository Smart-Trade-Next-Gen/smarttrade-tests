# E2E Test Categorization & CI/CD Strategy

## Architecture: Redis Streams Event Bus

Tests use the production event-driven architecture with **Redis Streams**:

| Stream | Purpose | Events |
|--------|---------|--------|
| **Redis Streams** | Event-driven event collection | `order.updated`, `trade.executed`, `position.updated` |

**Event Collection Flow**:
1. Services publish events to Redis Streams
2. Tests consume events via Redis clients or service clients
3. Tests validate state via broker state clients (source of truth)

**Rationale**: This ensures event-driven testing that matches the production architecture with broker as source of truth.

## Overview

The SmartTrade E2E testing framework spans **Phases 1-4** with **50+ comprehensive tests** organized by cross-cutting concerns, service-specific coverage, resilience, and performance.

## Test Categories

### 1. Phase 1: Cross-Cutting Concerns (19 tests)

**Purpose**: Validate architecture boundaries, order lifecycle, financial invariants, and RBAC
**Markers**: `@pytest.mark.smoke`
**Timeout**: 10 minutes (max 30s per test)
**When to run**: Every PR, pre-deployment validation
**Failure policy**: Block merge if failed

**Test Modules**:
1. **cross_cutting/test_architecture_boundaries.py** (3 tests)
   - Service boundary validation
   - Event bus validation
   - WebSocket separation

2. **cross_cutting/test_rbac_enforcement.py** (4 tests)
   - Unauthorized access prevention
   - Role-based access control
   - Permission validation

3. **order_lifecycle/test_order_lifecycle_e2e.py** (7 tests)
   - Market BUY/SELL full fill
   - LIMIT BUY/SELL trigger validation
   - Order cancellation
   - Order rejection
   - Partial fills

4. **order_lifecycle/test_financial_invariants.py** (5 tests)
   - Buy order decreases cash
   - Sell order increases cash
   - Position quantity matches trades
   - PnL calculation accuracy
   - No negative cash or positions

**Run command**:
```bash
pytest -m smoke -v
```

---

### 2. Phase 2: Service-Specific Coverage (14 tests)

**Purpose**: Validate each service's REST API and event consumption
**Markers**: `@pytest.mark.integration`
**Timeout**: 15 minutes (max 30s per test)
**When to run**: Every PR, daily CI runs
**Failure policy**: Block merge if failed

**Test Modules**:
1. **bas/test_bas_rest_api_comprehensive.py** (4 tests)
   - Order placement endpoint
   - Order cancellation endpoint
   - Portfolio query endpoint
   - WebSocket routing

2. **bas/test_bas_redis_trade_events.py** (3 tests)
   - Trade event consumption
   - Order event consumption
   - Position event consumption

3. **pbs/test_pbs_execution_logic.py** (4 tests)
   - Order execution validation
   - Fill injection validation
   - Position calculation
   - Order state transitions

4. **pbs/test_pbs_concurrency_safety.py** (3 tests)
   - Concurrent order placement
   - Concurrent fill injection
   - Position consistency

5. **mds/test_mds_quote_production.py** (4 tests)
   - Quote production validation
   - Quote format compliance
   - Instrument master publishing
   - Subscription request processing

6. **journal/test_journal_redis_consumer.py** (3 tests)
   - Trade event consumption
   - Order event consumption
   - Action event consumption

7. **journal/test_journal_rest_api.py** (4 tests)
   - Orders retrieval endpoint
   - Trades retrieval endpoint
   - Actions retrieval endpoint
   - Order by ID endpoint

8. **portfolio/test_portfolio_redis_position_consumer.py** (3 tests)
   - Position event consumption
   - Portfolio update validation
   - Account summary validation

9. **portfolio/test_portfolio_rest_api.py** (3 tests)
   - Positions retrieval endpoint
   - Position by instrument endpoint
   - Account summary endpoint

10. **notification/test_notification_redis_consumer.py** (3 tests)
    - Alert event consumption
    - Notification delivery validation
    - Settings update validation

11. **notification/test_notification_rest_api.py** (3 tests)
    - Alerts retrieval endpoint
    - Alert creation endpoint
    - History endpoint

12. **strategy/test_strategy_rest_api.py** (4 tests)
    - Strategies retrieval endpoint
    - Strategy by ID endpoint
    - Strategy execution endpoint
    - Decisions retrieval endpoint

**Run command**:
```bash
pytest -m integration -v
```

---

### 3. Phase 3: Resilience & Chaos (5 tests)

**Purpose**: Validate graceful degradation under failures
**Markers**: `@pytest.mark.resilience`
**Timeout**: 10 minutes (max 60s per test)
**When to run**: Weekly, pre-release
**Failure policy**: Warn, investigate, don't block

**Test Modules**:
1. **resilience/test_redis_failure.py** (3 tests)
   - Redis unavailable during order placement
   - Redis reconnection after failure
   - Redis stream consumer recovery

2. **resilience/test_postgresql_failure.py** (3 tests)
   - PostgreSQL unavailable during query
   - Connection pool recovery
   - Transaction rollback

3. **resilience/test_service_restart.py** (3 tests)
   - Service startup sequence
   - Service restart state persistence
   - Event replay after restart

4. **resilience/test_network_partition.py** (3 tests)
   - Network partition between services
   - Circuit breaker activation
   - Timeout handling

5. **resilience/test_message_ordering.py** (3 tests)
   - Redis stream message ordering
   - Consumer group ordering guarantees
   - Idempotent processing

**Run command**:
```bash
pytest -m resilience -v
```

---

### 4. Phase 4: Performance & Stress (4 tests)

**Purpose**: Validate system performance under load
**Markers**: `@pytest.mark.performance`
**Timeout**: 10 minutes (max 60s per test)
**When to run**: Weekly, pre-release
**Failure policy**: Warn, investigate, don't block

**Test Modules**:
1. **performance/test_order_load.py** (3 tests)
   - Concurrent order placement
   - Order placement throughput
   - Order placement latency

2. **performance/test_quote_processing.py** (3 tests)
   - High-frequency quote processing
   - Quote delivery latency
   - Consumer group scaling

3. **performance/test_database_performance.py** (3 tests)
   - Journal query performance
   - Portfolio query performance
   - Connection pool efficiency

4. **performance/test_redis_stream_performance.py** (3 tests)
   - Redis stream write throughput
   - Redis stream read throughput
   - Consumer group performance

**Run command**:
```bash
pytest -m performance -v
```

---

## CI/CD Pipeline Stages

### Stage 1: Smoke Tests (2 min)
```
✅ All passed? → Proceed to Stage 2
❌ Failed? → Block merge, report failure
```

**Dependencies**: None (runs first)

### Stage 2: Service-Specific Tests (15 min)
```
✅ All passed? → Proceed to Stage 3
❌ Failed? → Block merge, report failure
⏭️  Skipped? → Proceed anyway
```

**Dependencies**: Smoke tests pass

### Stage 3: Resilience Tests (10 min)
```
✅ All passed? → Proceed to Stage 4
❌ Failed? → Warn, log, proceed (non-deterministic)
⏭️  Skipped? → Proceed anyway
```

**Dependencies**: Service-specific tests pass

### Stage 4: Performance Tests (10 min)
```
✅ All passed? → All tests done
❌ Failed? → Warn, log (optional for merge)
⏭️  Skipped? → All tests done
```

**Dependencies**: Resilience tests pass

### Stage 5: Test Summary & Reporting
```
→ Generate HTML reports
→ Upload artifacts
→ Comment on PR with results
→ Set final status
```

---

## Execution Modes

### Local Development
```bash
# Run all tests
pytest integration/ -v

# Run by marker
pytest -m smoke -v
pytest -m integration -v
pytest -m resilience -v
pytest -m performance -v

# Run by service
pytest integration/bas/ -v
pytest integration/pbs/ -v
pytest integration/mds/ -v
pytest integration/journal/ -v
pytest integration/portfolio/ -v
pytest integration/notification/ -v
pytest integration/strategy/ -v

# Run specific test
pytest integration/order_lifecycle/test_order_lifecycle_e2e.py::test_market_buy_full_fill -v

# Run with coverage
pytest integration/ --cov=e2e --cov-report=html

# Run in parallel
pytest integration/ -n auto -v
```

### CI/CD (GitHub Actions)
```yaml
# Trigger: PR to main, push to main, manual dispatch
on: [pull_request, push, workflow_dispatch]

# Stages:
1. Smoke (2 min) → Block if fail
2. Service-Specific (15 min) → Block if fail
3. Resilience (10 min) → Warn if fail
4. Performance (10 min) → Warn if fail
5. Summary (5 min) → Aggregate results
```

---

## Test Markers Reference

```python
@pytest.mark.smoke              # Critical path (19 tests)
@pytest.mark.integration        # Service-specific (14 tests)
@pytest.mark.resilience         # Resilience & chaos (5 tests)
@pytest.mark.performance        # Performance & stress (4 tests)
```

**Filter by marker**:
```bash
pytest -m smoke
pytest -m "smoke or integration"
pytest -m "not resilience"
```

---

## Service Dependencies

### Services Required

| Service | Port | Purpose | Container |
|---------|------|---------|-----------|
| PostgreSQL | 5432 | Service databases | postgres:16 |
| Redis | 6379 | Event bus for async events | redis:7 |
| Auth Service | 8001 | Token generation | (external) |
| PBS | 8002 | Paper broker execution | (external) |
| MDS | 8004 | Market data service | (external) |
| BAS | 8005 | Broker adapter service | (external) |
| Strategy Service | 8006 | Strategy service | (external) |
| Journal Service | 8007 | Journal service | (external) |
| Portfolio Service | 8008 | Portfolio service | (external) |
| Notification Service | 8011 | Notification service | (external) |

### CI/CD Service Setup

```yaml
services:
  postgres:
    image: postgres:16-alpine
    env:
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: smarttrade_paper_broker_service
    health-check: pg_isready

  redis:
    image: redis:7-alpine
    health-check: redis-cli ping
```

**Health check script**:
```bash
#!/bin/bash
# Wait for PostgreSQL
until psql -h localhost -U postgres -c '\q' 2>/dev/null; do
  sleep 2
done

# Wait for Redis
until redis-cli -h localhost ping 2>/dev/null | grep PONG; do
  sleep 2
done

echo "All services ready"
```

---

## Timeout Configuration

| Test Type | Timeout | Rationale |
|-----------|---------|-----------|
| Smoke | 2 min | Quick sanity check |
| Injection | 30s/test | Deterministic, fast |
| Real Execution | 10s/test | Price-driven, slower |
| Resilience | 15s/test | Chaos injection overhead |
| Full Suite | 90 min | Total CI pipeline |

---

## Artifact Collection

### Generated During Tests

1. **Test Reports**
   - `smoke-report.html`
   - `injection-report.html`
   - `real-exec-report.html`
   - `resilience-report.html`

2. **Coverage Reports**
   - `coverage.xml` (Cobertura format)
   - `htmlcov/` (HTML coverage report)

3. **JUnit XML**
   - `smoke-junit.xml`
   - `injection-junit.xml`
   - `real-exec-junit.xml`
   - `resilience-junit.xml`

### Uploaded Artifacts

```yaml
- smoke-test-report (30 days)
- injection-test-report (30 days)
- real-execution-test-report (30 days)
- resilience-test-report (30 days)
- coverage-report (30 days)
- all-test-reports (30 days)
```

---

## Retry Logic

### Transient Failures

Some failures are expected to be transient (timeouts, network hiccups):

**Phase 5 (Injection)**: No retry (deterministic)
**Phase 6 (Real Execution)**: Manual retry (non-deterministic)
**Phase 7 (Resilience)**: No retry (testing failure handling itself)

**Manual retry command**:
```bash
pytest e2e/tests/test_partial_fills_real_execution.py -v --last-failed
```

---

## Failure Classification

| Category | Impact | Action |
|----------|--------|--------|
| **Smoke failure** | CRITICAL | Block merge, fix immediately |
| **Injection failure** | HIGH | Block merge, fix within 24h |
| **Real Execution failure** | MEDIUM | Warn, investigate, may proceed |
| **Resilience failure** | LOW | Log, investigate, proceed |

---

## Performance Baseline

### Target Execution Times

```
Smoke tests:      2 min  (quick PR validation)
Injection tests:  10 min (deterministic correctness)
Real Exec tests:  15 min (execution engine testing)
Resilience tests: 30 min (chaos engineering)
─────────────────────────
Total:            57 min (full CI pipeline)
```

**Optimization strategies**:
- Parallel test execution (`pytest -n auto`)
- Shared database fixtures
- Service reuse across stages
- Artifact caching

---

## Common CI Scenarios

### Scenario 1: Feature PR
```
Trigger: Pull request to main
Stages: Smoke → Injection → Real Exec → Resilience
Result: Summary comment on PR
Status: Block if smoke/injection fail, warn if real_exec/resilience fail
```

### Scenario 2: Hotfix
```
Trigger: Push to main
Stages: Smoke (2 min) → Rest optional
Result: Quick validation
Status: Block if smoke fails
```

### Scenario 3: Manual Full Run
```
Trigger: workflow_dispatch
Input: Select stage (all, smoke, injection, real_execution, resilience)
Result: Run selected stage(s) only
Status: Full reporting
```

---

## Debugging Failed Tests

### Get test output
```bash
cd e2e
pytest tests/test_name.py -v -s
```

### Run with logging
```bash
pytest tests/ -v -s --log-cli-level=DEBUG
```

### Check artifacts
1. Download HTML report from GitHub Actions
2. Check JUnit XML for structured results
3. Review coverage report for code paths

### Common failures and fixes

**Timeout errors**:
- Increase `wait_for_completion()` timeout
- Check service health
- Review event collector logs

**Assertion failures**:
- Review event sequence in test report
- Check position state vs expected
- Validate WAP calculation

**Resource errors**:
- Check PostgreSQL/Redis connectivity
- Verify event bus connectivity
- Check memory/CPU limits

---

## Maintenance

### Weekly Tasks
- Review failed resilience tests
- Check test execution times
- Update timeout thresholds

### Monthly Tasks
- Analyze test trends
- Review flaky tests
- Update test documentation

### Quarterly Tasks
- Refactor slow tests
- Add new test scenarios
- Review Phase 8 effectiveness

---

## Next Steps

For Phase 8 complete implementation:

1. ✅ GitHub Actions workflow (`.github/workflows/e2e-tests.yml`)
2. ✅ Test categorization (this document)
3. ⏳ Service health checks (startup scripts)
4. ⏳ Artifact reporting (HTML/XML generation)
5. ⏳ PR commenting (test result notifications)
6. ⏳ Performance monitoring (execution time trends)
