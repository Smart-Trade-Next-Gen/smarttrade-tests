# Hybrid E2E Testing for PIE

Complete end-to-end testing using **Postman + Pytest + Playwright** for comprehensive coverage.

---

## 🎯 Testing Strategy

| Tool | Best For | Speed | Usage |
|------|----------|-------|-------|
| **Postman** | API validation, non-tech users | ⚡ Fast | Quick API smoke tests |
| **Pytest** | Business logic, critical workflows | ⚡ Fast | Automated CI/CD |
| **Playwright** | UI interactions, user flows | 🐢 Slower | User acceptance testing |

---

## Part 1: Postman API Testing

### 📥 Import Collection

1. Open Postman
2. **File** → **Import**
3. Select: `/home/amit/Work/Smart-Trade/PIE.postman_collection.json`

### 🔑 Setup Environment Variables

Before running, configure:

**In Postman:**
1. Click **Environments** (bottom left)
2. Create new environment: `SmartTrade Local`
3. Add variables:

```
auth_base_url    = http://localhost:8001
bas_base_url     = http://localhost:8005
broker_id        = fyers
account_id       = TEST_ACC_001
auth_token       = (auto-populated by Login request)
user_id          = (auto-populated by Login request)
```

### ▶️ Run Collection

**Method 1: Interactive**
1. Click **Authentication** → **Login**
2. Click **Send** (stores auth_token)
3. Run each endpoint individually

**Method 2: Full Collection Run**
1. Right-click collection name
2. **Run Collection**
3. Select environment: `SmartTrade Local`
4. Click **Run PIE**

**Expected Output:**
```
✅ POST Login                          1/1
✅ POST Create Strategy                1/1
✅ GET List Strategies                 1/1
✅ GET Strategy Details                1/1
✅ PUT Adjust Strategy                 1/1
✅ DELETE Close Strategy               1/1
✅ POST Create Auto-Entry Config       1/1
✅ POST Toggle Auto-Entry              1/1
✅ GET PIE Status                      1/1
✅ GET Action Logs                     1/1
✅ POST Activate Kill Switch           1/1
✅ GET Invalid Broker ID (error test)  1/1
✅ GET Missing Auth Token (error test) 1/1

Passed: 13 | Failed: 0 ✅
```

### 📊 Postman Test Reports

**View Results:**
- **Summary Tab** → Shows pass/fail counts
- **Results Tab** → Detailed test execution
- **Console** → Raw request/response logging

**Export Report:**
1. Right-click collection
2. **Export as HTML**
3. Share with stakeholders

---

## Part 2: Pytest Critical Workflows

### 📋 What Gets Tested

- Strategy create/adjust/close
- Auto-entry config CRUD
- Status and log retrieval
- Error handling
- Pagination and filtering

### ▶️ Run Pytest E2E Tests

```bash
cd /home/amit/Work/Smart-Trade/broker-adapter-service

# Run critical workflows only (fast)
pytest tests/e2e/test_pie_workflows.py::TestPIEStrategyWorkflow -v -s
pytest tests/e2e/test_pie_workflows.py::TestPIEAutoEntryWorkflow -v -s
pytest tests/e2e/test_pie_workflows.py::TestPIEStatusAndLogs -v -s

# Run all fast tests (exclude kill switch)
pytest tests/e2e/ -v -s -m "not slow"

# Run with coverage report
pytest tests/e2e/ -v --cov=src/broker_adapter_service
```

### ✅ Pytest Expected Output

```
tests/e2e/test_pie_workflows.py::TestPIEStrategyWorkflow::test_create_strategy PASSED
tests/e2e/test_pie_workflows.py::TestPIEStrategyWorkflow::test_list_strategies PASSED
tests/e2e/test_pie_workflows.py::TestPIEStrategyWorkflow::test_adjust_strategy PASSED
tests/e2e/test_pie_workflows.py::TestPIEAutoEntryWorkflow::test_create_auto_entry PASSED
tests/e2e/test_pie_workflows.py::TestPIEStatusAndLogs::test_get_pie_status PASSED

======================== 15 passed in 2.34s ========================
```

### 🔧 Pytest Benefits

- ✅ Automated in CI/CD
- ✅ Real HTTP client validation
- ✅ Database state verification
- ✅ Error scenario testing
- ✅ Coverage reports

---

## Part 3: Playwright UI Testing

### 📦 Setup

```bash
cd /home/amit/Work/Smart-Trade/smarttrade-frontend

# Install Playwright
npm install -D @playwright/test

# Install browsers
npx playwright install chromium
```

### ⚙️ Configure Playwright

Create `playwright.config.ts`:

```typescript
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'on-first-retry',
  },
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
  },
});
```

### ▶️ Run Playwright Tests

```bash
cd smarttrade-frontend

# Run all UI tests
npx playwright test tests/e2e/pie-critical-paths.spec.ts

# Run in debug mode (interactive)
npx playwright test --debug

# Run specific test
npx playwright test -g "User can create a new strategy"

# Run with headed browser (see what's happening)
npx playwright test --headed

# Generate HTML report
npx playwright test
npx playwright show-report
```

### ✅ Playwright Expected Output

```
✅ 1. User can navigate to PIE page
✅ 2. User can view PIE status dashboard
✅ 3. User can create a new strategy
✅ 4. User can select and view strategy details
✅ 5. User can toggle auto-entry configuration
✅ 6. User can view action monitoring log
✅ 7. WebSocket connection indicator shows connected status
✅ 8. Kill switch button is visible and functional
✅ 9. Real-time MTM updates display (if available)
✅ 10. Responsive layout on mobile viewport

Passed: 10/10 ✅
```

### 📊 Playwright Reports

**HTML Report:**
```bash
npx playwright show-report
```

Opens interactive report with:
- ✅ Test execution timeline
- 📸 Screenshots
- 🎥 Videos of failures
- 📝 Test logs

---

## 🔗 Integrated Workflow

### Daily Development

```bash
# 1. Start services
docker-compose up -d

# 2. Apply migration (once)
cd broker-adapter-service
uv run alembic upgrade head

# 3. Run Pytest (fast - 2.5s)
pytest tests/e2e/ -v -s -m "not slow"

# 4. If Pytest passes, run Playwright (slower - ~30s)
cd ../smarttrade-frontend
npx playwright test tests/e2e/pie-critical-paths.spec.ts --headed
```

### Before Merge (All Tests)

```bash
# Pytest: API/Business Logic
pytest tests/e2e/ -v --cov

# Playwright: UI/UX
npx playwright test

# Postman: Manual smoke test (optional)
# (Run in Postman GUI)
```

### CI/CD Pipeline

```yaml
# .github/workflows/pie-e2e-tests.yml
name: PIE E2E Tests

on: [push, pull_request]

jobs:
  pytest-api:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Start services
        run: docker-compose up -d
      - name: Apply migration
        run: uv run alembic upgrade head
      - name: Run Pytest E2E
        run: pytest tests/e2e/ -v

  playwright-ui:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: 18
      - name: Install dependencies
        run: npm install
      - name: Install browsers
        run: npx playwright install --with-deps
      - name: Run Playwright
        run: npx playwright test

  postman-api:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run Postman CLI
        run: |
          npm install -g postman-cli
          postman run PIE.postman_collection.json --environment env.json
```

---

## 🎯 Test Coverage Matrix

| Workflow | Postman | Pytest | Playwright |
|----------|---------|--------|-----------|
| Create Strategy | ✅ | ✅ | ✅ |
| List Strategies | ✅ | ✅ | ✅ |
| Adjust Strategy | ✅ | ✅ | ✅ |
| Close Strategy | ✅ | ✅ | ✅ |
| Create Auto-Entry | ✅ | ✅ | ✅ |
| Toggle Auto-Entry | ✅ | ✅ | ✅ |
| Get PIE Status | ✅ | ✅ | ✅ |
| View Action Logs | ✅ | ✅ | ✅ |
| Kill Switch | ✅ | ✅ | ✅ (no-op) |
| WebSocket Events | ❌ | ❌ | ✅ |
| UI Responsiveness | ❌ | ❌ | ✅ |
| Form Validation | ❌ | ❌ | ✅ |
| Error Handling | ✅ | ✅ | ✅ |

---

## 📊 Test Execution Times

| Tool | Type | Count | Time |
|------|------|-------|------|
| **Postman** | API smoke | 13 | ~5s |
| **Pytest** | API + Logic | 15 | ~2.5s |
| **Playwright** | UI + UX | 12 | ~30s |
| **Total** | All | 40 | ~40s |

---

## ✅ Troubleshooting

### Postman Issues

| Problem | Solution |
|---------|----------|
| `401 Unauthorized` | Run Login endpoint first, verify token in variables |
| `Connection refused` | Ensure BAS running: `docker-compose logs bas` |
| `No response` | Check services: `docker-compose ps` |

### Pytest Issues

| Problem | Solution |
|---------|----------|
| `Connection refused` | Start services: `docker-compose up -d` |
| `Migration not found` | Run: `uv run alembic upgrade head` |
| `Timeout` | Increase timeout in conftest.py |

### Playwright Issues

| Problem | Solution |
|---------|----------|
| `Browser not found` | Run: `npx playwright install` |
| `Timeout on element` | Increase timeout: `{ timeout: 10000 }` |
| `Auth fails` | Check credentials in pie-critical-paths.spec.ts |

---

## 📚 Documentation Links

| Document | Purpose |
|----------|---------|
| `E2E_QUICKSTART.md` | Quick setup (5 min) |
| `tests/e2e/README.md` | Detailed Pytest guide |
| This file | Hybrid testing strategy |

---

## 🚀 Quick Command Reference

```bash
# Services
docker-compose up -d                    # Start all services
docker-compose ps                       # Check status
docker-compose logs -f SERVICE_NAME     # View logs

# Database
uv run alembic upgrade head              # Apply migrations
uv run alembic current                   # Check current version

# Pytest API Tests
pytest tests/e2e/ -v                     # Run all fast tests
pytest tests/e2e/ -v -s                  # With output
pytest tests/e2e/ -v --cov               # With coverage

# Playwright UI Tests
npx playwright test                      # Run all UI tests
npx playwright test --headed             # With browser visible
npx playwright test --debug              # Interactive debug
npx playwright show-report               # View HTML report

# Postman (Manual)
# Open Postman → Import PIE.postman_collection.json → Run Collection
```

---

## 🎓 Best Practices

### When to Use Each Tool

**Use Postman for:**
- ✅ Quick API validation
- ✅ Demoing APIs to stakeholders
- ✅ Manual testing workflows
- ✅ Non-technical team members

**Use Pytest for:**
- ✅ Automated CI/CD testing
- ✅ Business logic validation
- ✅ Error scenario coverage
- ✅ Coverage reports

**Use Playwright for:**
- ✅ User interaction testing
- ✅ Visual regression testing
- ✅ End-to-end workflows
- ✅ Mobile responsiveness
- ✅ Real user experience

### Execution Order

1. **Start tests with Pytest** (fastest feedback)
2. **Run Playwright on success** (more comprehensive)
3. **Use Postman for manual verification** (spot checks)

---

## 📞 Support

For issues:
1. Check relevant README (E2E_QUICKSTART.md, tests/e2e/README.md)
2. Review service logs: `docker-compose logs -f`
3. Verify database migration: `uv run alembic current`
4. Run individual tests in debug mode

---

**Ready to test?** Start with Pytest:
```bash
pytest tests/e2e/ -v -s -m "not slow"
```

✅ Hybrid E2E testing ready to go!
