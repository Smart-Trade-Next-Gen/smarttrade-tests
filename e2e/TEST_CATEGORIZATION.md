# E2E Test Categorization & CI/CD Strategy

## Overview

The SmartTrade E2E testing framework spans **Phases 1-8** with **39 comprehensive tests** organized by execution mode and resilience focus.

## Test Categories

### 1. Smoke Tests (2 tests)

**Purpose**: Quick sanity check for critical paths
**Markers**: `@pytest.mark.smoke`
**Timeout**: 2 minutes
**When to run**: Every PR, pre-deployment validation
**Failure policy**: Block merge if failed

Tests:
- `test_market_buy_full_fill` (Phase 5)
- `test_market_sell_full_fill` (Phase 5)

**Run command**:
```bash
pytest -m smoke -v
```

---

### 2. Phase 5: Injection Mode Tests (18 tests)

**Purpose**: Validate order correctness with deterministic fill injection
**Markers**: `@pytest.mark.injection`
**Timeout**: 10 minutes (max 30s per test)
**When to run**: Every PR, daily CI runs
**Failure policy**: Block merge if failed

**Execution model**: Deterministic
- Use `inject_fill()` to trigger fills
- No price-driven execution
- 100% reproducible
- Fast execution

**Test Modules**:
1. **test_order_lifecycle_injection.py** (4 tests)
   - Market BUY/SELL full fill
   - LIMIT BUY/SELL trigger validation
   
2. **test_partial_fills_injection.py** (3 tests)
   - 2-fill scenario (50+50)
   - 3-fill scenario (50+50+50)
   - 10-fill streaming (10 x 10)

3. **test_cancel_orders_injection.py** (3 tests)
   - Cancel unfilled order
   - Cancel partially filled order
   - Fill after cancellation rejection

4. **test_error_paths_injection.py** (5 tests)
   - Invalid inputs (zero qty, negative qty, zero price)
   - Overfill scenarios
   - Sequence violations

5. **test_concurrent_orders_injection.py** (3 tests)
   - Two concurrent BUY orders
   - Concurrent BUY + SELL
   - Three orders on same instrument

**Run command**:
```bash
pytest -m injection -v --tb=short
```

---

### 3. Phase 6: Real Execution Tests (10 tests)

**Purpose**: Test order execution triggered by price movements
**Markers**: `@pytest.mark.real_execution`
**Timeout**: 15 minutes (max 10s per test)
**When to run**: Daily CI, pre-release
**Failure policy**: Warn on failure, don't block merge (non-deterministic)

**Execution model**: Price-driven
- Use `market_data_stream.update_price()` to inject prices
- PriceExecutionEngine triggers fills
- Non-deterministic timing
- Realistic execution scenarios

**Test Modules**:
1. **test_market_buy_real_execution.py** (4 tests)
   - Market order immediate fill
   - LIMIT BUY trigger (price ≤ limit)
   - LIMIT SELL trigger (price ≥ limit)
   - STOP BUY trigger (price ≥ stop)

2. **test_partial_fills_real_execution.py** (3 tests)
   - 2-fill streaming prices
   - LIMIT order with price oscillation
   - Concurrent orders with partial fills

3. **test_execution_stress_scenarios.py** (3 tests)
   - 10 concurrent orders (1000 shares)
   - Rapid price updates (9 in 90ms)
   - Oscillating prices in narrow range

**Run command**:
```bash
pytest -m real_execution -v --tb=short
```

---

### 4. Phase 7: Resilience Tests (11 tests)

**Purpose**: Validate graceful degradation under failures
**Markers**: `@pytest.mark.resilience`
**Timeout**: 30 minutes (max 15s per test)
**When to run**: Weekly, pre-release
**Failure policy**: Warn, investigate, don't block

**Execution model**: Chaos-injected
- Use `ChaosEngine.inject()` for failure scenarios
- Test recovery mechanisms
- Validate invariant preservation
- Non-deterministic

**Test Modules**:
1. **test_resilience_timeouts.py** (4 tests)
   - Order placement under latency
   - Fill injection retries
   - Delayed event collection
   - Position state consistency

2. **test_resilience_event_handling.py** (4 tests)
   - Duplicate fill idempotency
   - Partial fill with missing events
   - Out-of-order event delivery
   - Stream interruption recovery

3. **test_resilience_partial_failures.py** (3 tests)
   - Concurrent orders with partial failures
   - Service degradation and recovery
   - Invariants under partial failures

**Run command**:
```bash
pytest -m resilience -v --tb=short
```

---

## CI/CD Pipeline Stages

### Stage 1: Smoke Tests (2 min)
```
✅ All passed? → Proceed to Stage 2
❌ Failed? → Block merge, report failure
```

**Dependencies**: None (runs first)

### Stage 2: Injection Tests (10 min)
```
✅ All passed? → Proceed to Stage 3
❌ Failed? → Block merge, report failure
⏭️  Skipped? → Proceed anyway
```

**Dependencies**: Smoke tests pass

### Stage 3: Real Execution Tests (15 min)
```
✅ All passed? → Proceed to Stage 4
❌ Failed? → Warn, log, proceed (non-deterministic)
⏭️  Skipped? → Proceed anyway
```

**Dependencies**: Injection tests pass

### Stage 4: Resilience Tests (30 min)
```
✅ All passed? → All tests done
❌ Failed? → Warn, log (optional for merge)
⏭️  Skipped? → All tests done
```

**Dependencies**: Real execution tests pass

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
pytest e2e/tests/ -v

# Run by marker
pytest -m smoke -v
pytest -m injection -v
pytest -m real_execution -v
pytest -m resilience -v

# Run specific test
pytest e2e/tests/test_order_lifecycle_injection.py::test_market_buy_full_fill -v

# Run with coverage
pytest e2e/tests/ --cov=e2e --cov-report=html

# Run in parallel
pytest e2e/tests/ -n auto -v
```

### CI/CD (GitHub Actions)
```yaml
# Trigger: PR to main, push to main, manual dispatch
on: [pull_request, push, workflow_dispatch]

# Stages:
1. Smoke (2 min) → Block if fail
2. Injection (10 min) → Block if fail
3. Real Execution (15 min) → Warn if fail
4. Resilience (30 min) → Warn if fail
5. Summary (5 min) → Aggregate results
```

---

## Test Markers Reference

```python
@pytest.mark.smoke              # Critical path (2 tests)
@pytest.mark.injection          # Deterministic mode (18 tests)
@pytest.mark.real_execution     # Price-driven mode (10 tests)
@pytest.mark.resilience         # Chaos/recovery (11 tests)
```

**Filter by marker**:
```bash
pytest -m smoke
pytest -m "smoke or injection"
pytest -m "not resilience"
```

---

## Service Dependencies

### Services Required

| Service | Port | Purpose | Container |
|---------|------|---------|-----------|
| PostgreSQL | 5432 | Mock order/trade/position data | postgres:16 |
| Redis | 6379 | Event bus for async events | redis:7 |
| Auth Service | 8001 | Token generation | (external) |
| Mock Service | 8002 | Order execution engine | (external) |
| BAS | 8005 | Order placement, positions | (external) |
| MDS | 8004 | WebSocket events | (external) |

### CI/CD Service Setup

```yaml
services:
  postgres:
    image: postgres:16-alpine
    env:
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: smarttrade_mock_service
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
