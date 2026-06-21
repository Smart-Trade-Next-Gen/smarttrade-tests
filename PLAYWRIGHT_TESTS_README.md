# Playwright UI Tests for SmartTrade

## Overview

Comprehensive Playwright UI test suite covering core trading and R&D platform (AMIS Control Tower). Legacy AMIS research tools tests are deprecated (ai-service removed).

## Test Files

### Core Trading

#### **core-trading-simple.spec.ts** (ACTIVE)
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

#### **core-trading.spec.ts** (REFERENCE)
Comprehensive test suite (45+ tests) with detailed coverage of all functionality areas.

### R&D Platform (AMIS Control Tower)

#### **rd-smoke.spec.ts**
Login baseline validation and basic R&D page accessibility (4 tests).

#### **rd-navigation.spec.ts**
Smoke tests for all 8 `/rd/*` routes via sidebar navigation (8 tests).

#### **rd-dashboard.spec.ts**
R&D Dashboard structural assertions: Dependency Health, Promotion Queue, Recent Decisions, Open Incidents (2 tests).

#### **rd-programs.spec.ts**
Research programs list and empty state (1 test).

#### **rd-research.spec.ts**
Candidate tabs (Candidates/Experiments/Assets) and tab switching (2 tests).

#### **rd-governance.spec.ts**
Governance tabs (Queue/History/Config), empty promotion queue, and decision history (3 tests).

#### **rd-deployments.spec.ts**
Deployments page structure and empty state (1 test).

#### **rd-lineage.spec.ts**
Lineage Explorer structural elements (1 test).

#### **rd-readiness.spec.ts**
Readiness page navigation (1 test). Note: Readiness API currently returns 500 in dev environment.

#### **rd-workspace.spec.ts**
Workspace wizard UI flow: template selection, form filling, and submission (1 test).

### AMIS Research Tools — MIGRATED

> **Note**: These tests were previously skipped because they routed to the legacy ai-service (port 8014). They have been migrated to their new homes and are now active.

#### **amis-dashboard.spec.ts** (ACTIVE)
Trade Intelligence panel — setup assessment via amis-lab-service (1 test).

#### **amis-replay.spec.ts** (ACTIVE)
Replay Dashboard — candle replay via amis-lab-service (1 test).

#### **amis-training.spec.ts** (ACTIVE)
Training Datasets page — dataset registry via amis-lab-service (1 test).

## Running Tests

### Quick Test Run
```bash
cd /home/amit/Work/Smart-Trade/smarttrade-tests

# Core trading tests
npx playwright test playwright/core-trading-simple.spec.ts

# R&D platform tests
npx playwright test playwright/rd-*.spec.ts

# All tests
npx playwright test
```

### Generate HTML Report
```bash
npx playwright test --reporter=html
npx playwright show-report
```

### Run Specific Test Suite
```bash
npx playwright test playwright/core-trading-simple.spec.ts -g "Authentication"
npx playwright test playwright/rd-dashboard.spec.ts -g "R&D Dashboard"
npx playwright test playwright/rd-workspace.spec.ts --headed
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
- **Base URL**: http://localhost:3000 (Docker) or http://localhost:5173 (local dev)
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
- **AMIS Core Service**: http://localhost:8000
- **AMIS Lab Service**: http://localhost:8016
- **Frontend (Docker)**: http://localhost:3000
- **Frontend (Local dev)**: http://localhost:5173

### Start Services
```bash
cd /home/amit/Work/Smart-Trade/smarttrade-deployment
docker-compose up -d
```

## Known Issues & Limitations

### 1. Readiness API Returns 500
**Problem**: `GET /api/v1/readiness/candidates` returns HTTP 500 in dev environment
**Impact**: Readiness page shows error state instead of candidate readiness data
**Fix**: Fixed `routes_readiness.py` to use `candidate_repo.list()` instead of non-existent `list_all()` method.

### 2. WebSocket Event Detection
**Problem**: Playwright doesn't capture WebSocket connections in all cases
**Impact**: Real-time data tests can't verify WS connections
**Fix**: Add custom WebSocket event logging or use Network tab inspection

### 3. Market Data Price Display
**Problem**: Price pattern `/₹|\\d+\\.\\d{1,2}/` doesn't match displayed prices
**Impact**: Live market data validation fails
**Fix**: Inspect actual price element format in DOM

### 4. Workspace Wizard Requires Valid Instrument IDs
**Problem**: Workspace creation via UI may fail if backend rejects instrument IDs from templates
**Impact**: Full workspace creation end-to-end flow may show error notification
**Fix**: Ensure AMIS Core accepts template instrument IDs or seed valid instruments

### 5. AMIS Lab 403 Forbidden Errors
**Problem**: AMIS Lab operations endpoints (`/api/v1/operations/*`) return 403 for non-admin users
**Impact**: Console shows 403 errors on R&D Dashboard, Programs, and other pages that fetch dependency health / incidents
**Fix**: Tests filter these out as expected dev-environment noise. In production, ensure proper RBAC roles.

## Bug Fixes Applied (This Session)

### Backend
- **AMIS Core readiness endpoint** (`routes_readiness.py`): Changed `candidate_repo.list_all()` to `candidate_repo.list()` because `CandidateArtifactRepository` inherits from `BaseRepository` which provides `list()`, not `list_all()`.

### Frontend
- **`amisCoreClient.ts`**: Added missing import for `amisCoreEndpoints` from `./apiConfig`.
- **`apiConfig.ts`**: Removed duplicate `/amis-core` and `/amis-lab` prefixes from `amisCoreEndpoints` and `amisLabEndpoints`. The axios clients (`amisCoreService`, `amisLabService`) already provide these base URLs, so the endpoints should be relative paths (e.g., `/api/v1/research/candidates` instead of `/amis-core/api/v1/research/candidates`). This was causing all AMIS Core/Lab API calls to return 404 with double-prefixed URLs like `/amis-core/amis-core/api/v1/...`.
- **`ResearchWorkspacePage.tsx`**: Added `data-testid` attributes to VIX min/max inputs (`workspace-vix-min`, `workspace-vix-max`) and governance tab buttons (`governance-tab-queue`, `governance-tab-history`, `governance-tab-config`).

## Recommendations for Improvement

### 1. Add Data Test IDs (PARTIALLY COMPLETE)
R&D and AMIS pages now have `data-testid` attributes on headings, sidebar nav links, shared components (StatusBadge, HealthIndicator, GateStatusIndicator), and workspace wizard elements.

Still needed for core trading UI:
```tsx
<div data-testid="account-equity">{equity}</div>
<button data-testid="buy-button">Buy</button>
<table data-testid="positions-table">
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
