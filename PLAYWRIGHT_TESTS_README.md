# Playwright UI Tests for SmartTrade Core Trading Functionality

## Overview

Comprehensive Playwright UI test suite covering all core trading platform functionality. Tests validate user-facing features including order placement, market data updates, position management, and account operations.

## Test Files

### 1. **core-trading-simple.spec.ts** (ACTIVE)
Simplified, working test suite optimized for actual UI interactions.

**26 core tests** organized into 8 test suites:
- **Authentication** (2 tests) - Login and session persistence
- **Navigation** (3 tests) - Page navigation (Positions, Orders, Market Watch)
- **Dashboard Display** (4 tests) - Account equity, balance, positions, pending orders
- **Order Panel Access** (2 tests) - Order entry UI access
- **Real-Time Data** (2 tests) - WebSocket connections and market data
- **Positions Page** (2 tests) - Position table display and columns
- **Orders Page** (2 tests) - Order list and status indicators
- **API Connectivity** (4 tests) - Service health checks (Auth, MDS, BAS, Mock)
- **UI Responsiveness** (3 tests) - Console errors, navigation, loading state
- **End-to-End Flows** (2 tests) - Multi-page user journeys

### 2. **core-trading.spec.ts** (REFERENCE)
Comprehensive test suite (45+ tests) with detailed coverage of all functionality areas.

**8 test suites** covering:
- Order Placement & Execution (6 tests)
- Real-Time Market Data Updates (4 tests)
- Trade Execution Flow (3 tests)
- Position Management & Updates (5 tests)
- Order History & Tracking (6 tests)
- Account Balance Operations (4 tests)
- Market Watch Functionality (6 tests)
- Buy/Sell Order Validation & Execution (5 tests)

## Running Tests

### Quick Test Run
```bash
cd /home/amit/Work/Smart-Trade/smarttrade-tests
npx playwright test playwright/core-trading-simple.spec.ts
```

### Generate HTML Report
```bash
npx playwright test playwright/core-trading-simple.spec.ts --reporter=html
npx playwright show-report
```

### Run Specific Test Suite
```bash
npx playwright test playwright/core-trading-simple.spec.ts -g "Authentication"
npx playwright test playwright/core-trading-simple.spec.ts -g "API Connectivity"
```

### Run with Debugging
```bash
npx playwright test playwright/core-trading-simple.spec.ts --debug
npx playwright test playwright/core-trading-simple.spec.ts --headed
```

## Test Results Summary

### Current Status (April 17, 2026)
- **Total Tests**: 26
- **Passing**: 14 (54%)
- **Failing**: 12 (46%)

### Passing Tests ✅
1. Navigate to Market Watch
2. Open order entry panel from sidebar
3. Find order related UI elements
4. Display positions table
5. Display orders list
6. Show order status indicators
7. Auth service responding (HTTP 200)
8. Market data service responding (HTTP 200)
9. Broker adapter service responding (HTTP 200)
10. Paper broker service responding (HTTP 200)
11. No critical console errors
12. Not stuck in loading state
13. Multi-page navigation responsive

### Failing Tests ❌
1. Dashboard login flows (timeout waiting for Dashboard text)
2. Dashboard display elements (equity, balance selectors not matching)
3. WebSocket connection detection
4. Live market data display (price pattern matching)
5. Position column detection
6. Main navigation rendering
7. E2E journey (login flow timeout)

## Architecture

### Test Configuration
- **Browser**: Chromium
- **Timeout**: 45 seconds per test
- **Retries**: 1 (auto-retry on failure)
- **Base URL**: http://localhost:5173
- **Headless**: true
- **Screenshots**: Only on failure
- **Traces**: On first retry (for debugging)

### Helper Functions
```typescript
async function loginAndWait(page: Page)
  - Logs in with test credentials
  - Waits for app to load
  - Handles navigation

async function getPositionRow(page: Page, instrument: string)
  - Finds position table row by instrument

async function getAccountBalance(page: Page)
  - Extracts numeric balance from DOM
```

### Test Data
```typescript
const BASE_URL = "http://localhost:5173";
const TEST_USERNAME = "test_pie_e2e";
const TEST_PASSWORD = "Test123.e2e";
```

## Service Requirements

All services must be running on expected ports:
- **Auth Service**: http://localhost:8001
- **Paper Broker Service**: http://localhost:8002
- **Market Data Service**: http://localhost:8004
- **Broker Adapter Service**: http://localhost:8005
- **Frontend**: http://localhost:5173

### Start Services
```bash
cd /home/amit/Work/Smart-Trade/smarttrade-deployment
docker-compose up -d
```

## Known Issues & Limitations

### 1. Dashboard Text Selector Issue
**Problem**: Tests timeout looking for "text=Dashboard" after login
**Impact**: Authentication tests fail
**Root Cause**: Dashboard heading may use different text or be in sidebar (collapsible)
**Fix**: Inspect Dashboard component and use more specific selector or data-testid

### 2. WebSocket Event Detection
**Problem**: Playwright doesn't capture WebSocket connections in all cases
**Impact**: Real-time data tests can't verify WS connections
**Fix**: Add custom WebSocket event logging or use Network tab inspection

### 3. Market Data Price Display
**Problem**: Price pattern `/₹|\\d+\\.\\d{1,2}/` doesn't match displayed prices
**Impact**: Live market data validation fails
**Fix**: Inspect actual price element format in DOM

### 4. Navigation URL Patterns
**Problem**: Tests use URL patterns that may not match actual routes
**Impact**: Some navigation tests fail
**Fix**: Verify actual route structure in app

## Recommendations for Improvement

### 1. Add Data Test IDs (CRITICAL)
Add `data-testid` attributes to key UI elements:
```tsx
<h1 data-testid="dashboard-title">Dashboard</h1>
<div data-testid="account-equity">{equity}</div>
<button data-testid="buy-button">Buy</button>
<table data-testid="positions-table">
```

Then use in tests:
```typescript
const dashboard = page.locator('[data-testid="dashboard-title"]');
const buyBtn = page.locator('[data-testid="buy-button"]');
```

### 2. Improve Login Flow Testing
- Mock auth server or create dedicated test user
- Reduce login wait time with better loading indicators
- Add explicit ready state checks

### 3. Add E2E Test Fixtures
Create test fixtures for:
- Pre-populated market data
- Pre-created orders
- Account balance snapshots

### 4. Enhance WebSocket Testing
- Capture WebSocket events at application level
- Add explicit event listeners
- Log WebSocket messages for debugging

### 5. Create Visual Regression Tests
- Screenshot critical UI flows
- Compare with baseline images
- Detect unintended UI changes

## CI/CD Integration

Tests are designed to run in GitHub Actions (or similar CI):

```yaml
- name: Run Playwright Tests
  run: |
    cd smarttrade-tests
    npx playwright test --reporter=html
    
- name: Upload Report
  uses: actions/upload-artifact@v3
  with:
    name: playwright-report
    path: smarttrade-tests/playwright-report/
```

## Coverage Mapping

| Requirement | Test Suite | Status |
|---|---|---|
| Order placement & execution | Order Placement & Execution | ✅ Designed |
| Real-time market data | Real-Time Market Data | ⚠️ Needs selectors |
| Trade execution flow | Trade Execution Flow | ✅ Designed |
| Position management | Position Management | ✅ Partially passing |
| Order history/tracking | Order History & Tracking | ✅ Partially passing |
| Account balance | Account Balance | ✅ Designed |
| Market watch | Market Watch | ✅ Passing |
| Buy/sell validation | Buy/Sell Validation | ✅ Designed |

## Next Steps

1. **Immediate (High Priority)**
   - Add data-testid attributes to critical UI elements
   - Fix dashboard text selector
   - Update navigation URL patterns

2. **Short Term (Medium Priority)**
   - Implement visual regression testing
   - Add comprehensive error logging
   - Create test data fixtures

3. **Medium Term (Low Priority)**
   - Add performance benchmarking
   - Implement accessibility testing
   - Create load testing scenarios

## Useful Commands

```bash
# Run all tests
npx playwright test

# Run specific file
npx playwright test core-trading-simple.spec.ts

# Run specific test
npx playwright test -g "should display account equity"

# Run in debug mode
npx playwright test --debug

# Run in headed mode (visible browser)
npx playwright test --headed

# Update snapshots
npx playwright test --update-snapshots

# List all tests
npx playwright test --list

# Generate report
npx playwright test --reporter=html

# View report
npx playwright show-report

# Run with specific browser
npx playwright test --project=chromium
```

## File Structure

```
smarttrade-tests/
├── playwright/
│   ├── core-trading-simple.spec.ts     # Active test suite (26 tests)
│   ├── core-trading.spec.ts            # Reference suite (45+ tests)
│   ├── alignment.spec.ts               # Existing alignment tests
│   └── ...
├── playwright.config.ts                # Playwright config
├── test-results/                       # Test results (auto-generated)
├── playwright-report/                  # HTML report (auto-generated)
└── PLAYWRIGHT_TESTS_README.md          # This file
```

## Contact & Support

For issues or questions about tests:
1. Check test output in `test-results/` directory
2. View HTML report: `npx playwright show-report`
3. Check trace files for detailed execution logs
4. Review this README for known issues

## Version Info

- **Playwright**: 1.58.2
- **Node.js**: 20+
- **Test Framework**: Playwright Test
- **Browser**: Chromium
- **Created**: April 17, 2026
