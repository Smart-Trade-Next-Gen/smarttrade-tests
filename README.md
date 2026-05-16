# SmartTrade Tests

Cross-service integration, E2E, and API test artifacts for the SmartTrade trading platform.

> Service-level unit and route tests live inside each service repo. This repo contains cross-service API and E2E tests.

## 🚀 Quick Start

**New to E2E testing?** Read the quick start guide:

```bash
# One-time setup
bash setup_e2e.sh

# Run tests
./run_e2e_tests.sh quick        # Verify setup (2 min)
./run_e2e_tests.sh full         # Run all tests (30 min)
./run_e2e_tests.sh --help       # See all options
```

👉 **[E2E Quick Start Guide](E2E_QUICKSTART.md)** — Setup, running tests, troubleshooting

## Structure

```
e2e/                — E2E test framework (39 tests across 4 phases)
  ├── tests/        — Test suites (injection, real execution, resilience)
  ├── conftest.py   — Global pytest fixtures and configuration
  ├── requirements.txt
  └── README.md     — Framework details

postman/            — Postman collection and environment files
scripts/            — Test runner scripts
docs/               — Additional test guides and documentation
test-results/       — Test output and logs (gitignored)
```

## 📋 Running E2E Tests

### One-Time Setup

```bash
bash setup_e2e.sh
```

This checks Python, installs pytest + dependencies, and verifies the environment.

### Run Tests

```bash
# Quick sanity check (2 tests, ~2 min)
./run_e2e_tests.sh quick

# All tests sequentially (39 tests, ~30 min)
./run_e2e_tests.sh full

# By test phase
./run_e2e_tests.sh injection      # 18 deterministic tests
./run_e2e_tests.sh real           # 10 price-driven tests
./run_e2e_tests.sh resilience     # 11 chaos tests

# Parallel execution (faster, ~20 min)
E2E_PYTEST_WORKERS=4 ./run_e2e_tests.sh parallel

# See all options
./run_e2e_tests.sh --help
```

### Prerequisites

Services must be running before tests:

```bash
docker compose -f docker-compose.e2e.yml up -d
```

This starts PostgreSQL, Redis, and all services (Auth, BAS, MDS, Mock, Frontend).

### Results

Test results are saved to `test-results/` with timestamps:

```bash
# View latest results
cat test-results/e2e_tests_*.log | tail -50

# Check for failures
grep "FAILED\|ERROR" test-results/e2e_tests_*.log
```

### Verify Setup

Before running tests, verify your environment:

```bash
bash check_e2e_setup.sh
```

---

## 📚 Documentation

| Document | Purpose |
|----------|---------|
| [E2E Quick Start](E2E_QUICKSTART.md) | Setup, commands, troubleshooting |
| [E2E Framework README](e2e/README.md) | Architecture, fixtures, test phases |
| [Test Categorization](e2e/TEST_CATEGORIZATION.md) | Test strategy and CI/CD pipeline |
| [Troubleshooting Guide](TROUBLESHOOTING.md) | Common issues and solutions |

---

## 🧪 Test Phases

| Phase | Type | Count | Time | Marker |
|-------|------|-------|------|--------|
| Smoke | Quick sanity | 2 | 2 min | `@pytest.mark.smoke` |
| Phase 5 | Injection | 18 | 10 min | `@pytest.mark.injection` |
| Phase 6 | Real Execution | 10 | 15 min | `@pytest.mark.real_execution` |
| Phase 7 | Resilience | 11 | 30 min | `@pytest.mark.resilience` |

**Total**: 39 tests | **Full suite**: ~57 minutes

---

## 🔧 Scripts

| Script | Purpose |
|--------|---------|
| `run_e2e_tests.sh` | Main test runner (modes: quick, full, injection, etc.) |
| `setup_e2e.sh` | One-time environment setup |
| `check_e2e_setup.sh` | Verify setup is correct |

---

## Legacy: Postman Tests

### Prerequisites

```bash
npm install -g newman
```

### Run integration tests

```bash
./scripts/run-integration-tests.sh
# or with a custom environment:
./scripts/run-integration-tests.sh postman/Smartapp Local.postman_environment.json
```

### Import into Postman

1. Open Postman
2. Import → `postman/SmartApp Integration Tests.postman_collection.json`
3. Import → `postman/Smartapp Local.postman_environment.json`
4. Select the environment and run the collection

| File | Purpose |
|------|---------|
| `Smartapp Local.postman_environment.json` | Local development (localhost ports) |
