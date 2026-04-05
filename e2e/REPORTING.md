# E2E Test Reporting

This document explains how to generate and view beautiful HTML reports for the E2E tests.

## Quick Start

### Generate Test Report
Run the test suite with HTML report generation:

```bash
cd smarttrade-tests

# Run all tests and generate pytest HTML report
python -m pytest e2e/tests/ --html=reports/e2e_report.html --self-contained-html

# Or use the convenience script
./e2e/generate_report.sh

# Run specific test category
./e2e/generate_report.sh smoke           # Smoke tests only
./e2e/generate_report.sh injection       # Injection mode tests
./e2e/generate_report.sh real_execution  # Real execution tests
./e2e/generate_report.sh resilience      # Resilience tests
```

### View Reports

After running tests, two types of reports are available:

#### 1. **Pytest HTML Report** (Detailed)
- **Location**: `reports/e2e_report.html`
- **What it shows**: 
  - Individual test results with full logs
  - Pass/fail status for each test
  - Execution times
  - Error messages and stack traces
- **Use for**: Detailed debugging and understanding failures

```bash
# Open in default browser
open reports/e2e_report.html
# Or manually: file:///path/to/reports/e2e_report.html
```

#### 2. **Custom Dashboard** (User-Friendly)
- **Location**: `reports/e2e_dashboard.html`
- **What it shows**:
  - Summary statistics (passed, failed, skipped)
  - Progress bar showing test distribution
  - Tests organized by category
  - Color-coded results (green=pass, red=fail, orange=skip)
  - Test markers and execution times
  - Known issues and next steps
- **Use for**: Quick overview for non-technical stakeholders

```bash
# Generate the custom dashboard
python e2e/report_generator.py

# Open in default browser
open reports/e2e_dashboard.html
```

## Report Features

### Summary Statistics
At the top of the dashboard:
- **✅ Passed**: Number of tests that passed
- **❌ Failed**: Number of tests that failed
- **⏭️ Skipped**: Number of tests skipped
- **Total**: Total number of tests

### Progress Bar
Visual representation of test results:
- Green segment = percentage passed
- Red segment = percentage failed
- Orange segment = percentage skipped

### Test Groups
Tests organized by category:
- **Smoke Tests**: Critical path validation (2 tests)
- **Injection Mode**: Deterministic execution (18 tests)
- **Real Execution**: Price-driven fills (10 tests)
- **Resilience**: Chaos and recovery (11 tests)

### Test Item Details
Each test shows:
- ✅/❌ Status badge
- Test name
- Category markers (smoke, injection, etc.)
- Execution duration
- Error messages (if failed)

### Status Indicators
- ✅ **PASSED**: Test completed successfully
- ❌ **FAILED**: Test failed (see error details)
- ⏭️ **SKIPPED**: Test was skipped
- ⚠️ **ERROR**: Test encountered an error

## CI/CD Integration

In GitHub Actions, HTML reports are automatically generated and stored as artifacts:

```bash
# Reports are saved with 30-day retention
# Download them from GitHub Actions "Artifacts" section
```

## Example Report Scenarios

### All Tests Pass ✅
```
✅ Passed: 39
❌ Failed: 0
⏭️ Skipped: 0
Total: 39
Progress: [████████████████████] 100% Passed
```

### Some Tests Fail ❌
```
✅ Passed: 3
❌ Failed: 36
⏭️ Skipped: 0
Total: 39
Progress: [████      ] 7% Passed | [████████████] 92% Failed
```

## Commands

### Full Test Suite with Report
```bash
python -m pytest e2e/tests/ \
    -v \
    --html=reports/e2e_report.html \
    --self-contained-html
```

### Smoke Tests Only
```bash
python -m pytest e2e/tests/ \
    -m smoke \
    -v \
    --html=reports/e2e_report_smoke.html \
    --self-contained-html
```

### With Coverage Report
```bash
python -m pytest e2e/tests/ \
    --cov=e2e \
    --cov-report=html \
    --html=reports/e2e_report.html \
    --self-contained-html
```

### Run in Parallel
```bash
python -m pytest e2e/tests/ \
    -n auto \
    --html=reports/e2e_report.html \
    --self-contained-html
```

## Report Files

The `reports/` directory contains:

```
reports/
├── e2e_report.html                 # Main pytest HTML report
├── e2e_dashboard.html              # Custom user-friendly dashboard
├── e2e_report_smoke.html           # Smoke tests only (if generated)
├── e2e_report_injection.html       # Injection tests only (if generated)
├── e2e_report_real_execution.html  # Real execution tests (if generated)
├── e2e_report_resilience.html      # Resilience tests (if generated)
├── e2e_tests_*.log                 # Test execution logs (timestamped)
└── .gitkeep
```

## Troubleshooting

### Report not generated
1. Check that `reports/` directory exists
2. Ensure pytest-html is installed: `pip install pytest-html`
3. Run tests with explicit output: `pytest ... -v`

### Report is empty
1. Verify tests actually ran: check `e2e_tests_*.log`
2. Check for permission issues on `reports/` directory
3. Try generating again: `python e2e/report_generator.py`

### Can't open report in browser
- Use full file path: `file:///home/amit/Work/Smart-Trade/smarttrade-tests/reports/e2e_report.html`
- Or use a local server: `python -m http.server 8000` then visit `http://localhost:8000/reports/`

## Tips for Different Audiences

### For Developers
Use the **pytest HTML report** (`e2e_report.html`):
- Detailed error messages
- Full stack traces
- Log output per test
- Execution timeline

### For QA/Managers
Use the **Custom Dashboard** (`e2e_dashboard.html`):
- Visual summary with color coding
- Progress bar showing completion
- Test categories and organization
- Known issues and next steps
- No technical jargon

### For CI/CD
Both reports are generated automatically:
- HTML reports stored as artifacts
- Download and share with team
- Email summaries for stakeholders
