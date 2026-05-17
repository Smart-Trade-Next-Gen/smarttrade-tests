# E2E Test Runner - Quick Start Guide

This guide helps you run the SmartTrade E2E tests smoothly on your local machine.

## 🚀 One-Time Setup

Run this once to install dependencies:

```bash
cd /path/to/smarttrade-tests
bash setup_e2e.sh
```

This will:
- ✓ Check Python installation
- ✓ Install all test dependencies
- ✓ Verify packages
- ✓ Create necessary directories

## 📋 Prerequisites

Before running tests, ensure services are running:

### Option 1: Docker (Recommended)

```bash
docker compose -f docker-compose.e2e.yml up -d
```

This starts:
- PostgreSQL (port 5432)
- Redis (port 6379)
- All services (Auth, BAS, MDS, Mock, etc.)

### Option 2: Manual Service Setup

If running services locally, ensure these are running:
- PostgreSQL on localhost:5432
- Redis on localhost:6379
- All SmartTrade services

> ℹ️ Services must be running before tests start. Tests will fail with connection errors if services aren't available.

## 🏃 Running Tests

### Quick Start (2 minutes)

Test basic smoke tests to verify setup:

```bash
./run_e2e_tests.sh quick
```

### Common Commands

```bash
# Run smoke tests only
./run_e2e_tests.sh quick

# Run all tests sequentially (safe)
./run_e2e_tests.sh full

# Run injection tests (deterministic)
./run_e2e_tests.sh injection

# Run real execution tests (price-driven)
./run_e2e_tests.sh real

# Run resilience tests (chaos)
./run_e2e_tests.sh resilience

# Run in parallel with 4 workers
E2E_PYTEST_WORKERS=4 ./run_e2e_tests.sh parallel
```

### Test Modes

| Mode | Tests | Time | Best For |
|------|-------|------|----------|
| `quick` | 2 smoke | ~2 min | Quick verification |
| `injection` | 18 tests | ~10 min | Deterministic checks |
| `real` | 10 tests | ~15 min | Price-driven scenarios |
| `resilience` | 11 tests | ~30 min | Chaos/failure paths |
| `sequential` | All (39) | ~45 min | Safe staged execution |
| `parallel` | All (39) | ~20 min | Fast parallel run |
| `full` | All (39) | ~30 min | Complete suite |

## 📊 Test Results

Results are saved to `test-results/` with timestamps:

```
test-results/
├── e2e_tests_20260504_143022.log  # Latest run
├── e2e_tests_20260504_142015.log  # Previous run
└── ...
```

View results:

```bash
# View latest results
cat test-results/e2e_tests_*.log | tail -50

# Check for failures
grep "FAILED\|ERROR" test-results/e2e_tests_*.log

# Count passed/failed
grep -E "passed|failed" test-results/e2e_tests_*.log | tail -1
```

## 🔧 Advanced Options

```bash
# Run with help
./run_e2e_tests.sh --help

# Skip dependency checks
./run_e2e_tests.sh quick --skip-deps

# Skip environment checks
./run_e2e_tests.sh full --skip-env

# Run without saving logs
./run_e2e_tests.sh injection --no-log

# Open log file after completion (Linux/Mac)
./run_e2e_tests.sh quick --open
```

## 🐛 Troubleshooting

### Problem: "pytest: command not found"

**Solution**: Install dependencies
```bash
bash setup_e2e.sh
```

### Problem: Tests timeout or fail immediately

**Likely cause**: Services not running

**Solution**:
```bash
# Verify Docker is running
docker ps

# Start services
docker compose -f docker-compose.e2e.yml up -d

# In another terminal, run tests
./run_e2e_tests.sh quick
```

### Problem: Connection refused on localhost:5432 or 6379

**Solution**:
```bash
# Check if PostgreSQL is running
docker ps | grep postgres

# Check if Redis is running
docker ps | grep redis

# Start services if needed
docker compose -f docker-compose.e2e.yml up -d
```

### Problem: Tests pass in quick mode but fail in full mode

**Likely cause**: Service state pollution between tests

**Solution**: 
- Use `sequential` mode instead of `parallel`
- Check if services have memory leaks or dangling connections
- Review test logs for cleanup issues

### Problem: "PYTHONPATH" related import errors

**Solution**: Set PYTHONPATH manually
```bash
export PYTHONPATH="$PWD/e2e:$PYTHONPATH"
./run_e2e_tests.sh quick
```

## 📈 Performance Tips

### For faster runs:

1. **Use parallel mode** (needs pytest-xdist):
   ```bash
   pip install pytest-xdist
   E2E_PYTEST_WORKERS=4 ./run_e2e_tests.sh parallel
   ```

2. **Run only specific phase**:
   ```bash
   ./run_e2e_tests.sh injection    # 18 tests, ~10 min
   ./run_e2e_tests.sh real         # 10 tests, ~15 min
   ```

3. **Run specific test**:
   ```bash
   export PYTHONPATH="$PWD/e2e:$PYTHONPATH"
   cd e2e
   pytest tests/test_order_lifecycle_injection.py::test_place_market_buy_order -v
   ```

## 📚 Test Phases Overview

### Phase 5: Injection Mode (18 tests)
- **Type**: Deterministic (mock fills)
- **Time**: ~10 min
- **Use**: Core order flow validation
- **Command**: `./run_e2e_tests.sh injection`

### Phase 6: Real Execution (10 tests)
- **Type**: Price-driven (real fills)
- **Time**: ~15 min
- **Use**: Realistic trading scenarios
- **Command**: `./run_e2e_tests.sh real`

### Phase 7: Resilience (11 tests)
- **Type**: Chaos testing (failure injection)
- **Time**: ~30 min
- **Use**: Error handling and recovery
- **Command**: `./run_e2e_tests.sh resilience`

## 🔗 Related Documentation

- [E2E Framework README](e2e/README.md) — Detailed architecture and fixtures
- [Test Categorization](e2e/TEST_CATEGORIZATION.md) — Test strategy and CI/CD
- [GitHub Workflow](.github/workflows/e2e-tests.yml) — CI/CD pipeline

## ❓ Getting Help

1. **Check logs**: `test-results/e2e_tests_*.log`
2. **Run with verbose output**: `./run_e2e_tests.sh quick --no-log`
3. **See test structure**: `ls -la e2e/tests/`
4. **Review pytest config**: `cat e2e/pytest.ini`

## ✅ Checklist for First Run

- [ ] Python 3 installed
- [ ] Ran `bash setup_e2e.sh`
- [ ] Services running (`docker compose -f docker-compose.e2e.yml up -d`)
- [ ] Redis and PostgreSQL accessible
- [ ] Ran `./run_e2e_tests.sh quick` successfully
- [ ] Review test results in `test-results/`

---

**Quick Command Reference**:
```bash
bash setup_e2e.sh              # One-time setup
./run_e2e_tests.sh quick       # Verify setup (2 min)
./run_e2e_tests.sh full        # Run all tests (30 min)
./run_e2e_tests.sh --help      # See all options
```
