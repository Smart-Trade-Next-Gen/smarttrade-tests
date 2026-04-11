#!/bin/bash
# E2E Test Runner with Optimized Parallelization Strategy

set -e

# Determine run mode
MODE="${1:-full}"
WORKERS="${E2E_PYTEST_WORKERS:-2}"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== SmartTrade E2E Test Runner ===${NC}"
echo "Mode: $MODE"

case $MODE in
  "quick")
    echo -e "${GREEN}Running QUICK mode (smoke tests only)...${NC}"
    python -m pytest e2e/tests/ -m smoke -v --tb=line 2>&1 | tee e2e_tests.log
    ;;

  "smoke")
    echo -e "${GREEN}Running SMOKE mode (critical paths)...${NC}"
    python -m pytest e2e/tests/ -m "smoke or (injection and not concurrent)" -v --tb=line 2>&1 | tee e2e_tests.log
    ;;

  "sequential")
    echo -e "${GREEN}Running SEQUENTIAL mode (problematic tests one-by-one)...${NC}"
    echo "Step 1: Resilience tests (usually work well)..."
    python -m pytest e2e/tests/ -m resilience -v --tb=line 2>&1 | tee -a e2e_tests.log

    echo -e "\nStep 2: Error path tests..."
    python -m pytest e2e/tests/test_error_paths_injection.py -v --tb=line 2>&1 | tee -a e2e_tests.log

    echo -e "\nStep 3: Single concurrent test..."
    python -m pytest e2e/tests/test_concurrent_orders_injection.py::test_two_concurrent_buy_orders -v --tb=line 2>&1 | tee -a e2e_tests.log

    echo -e "\nStep 4: Partial fills..."
    python -m pytest e2e/tests/test_partial_fills_injection.py -v --tb=line 2>&1 | tee -a e2e_tests.log

    echo -e "\nStep 5: Order lifecycle..."
    python -m pytest e2e/tests/test_order_lifecycle_injection.py -v --tb=line 2>&1 | tee -a e2e_tests.log
    ;;

  "parallel")
    echo -e "${GREEN}Running PARALLEL mode (all tests, parallel where possible)...${NC}"
    # Use bounded pytest-xdist parallelization to avoid memory blow-ups.
    if command -v pytest-xdist &> /dev/null; then
      echo "Using $WORKERS worker(s)"
      python -m pytest e2e/tests/ -n "$WORKERS" --dist=loadscope -v --tb=line 2>&1 | tee e2e_tests.log
    else
      echo "pytest-xdist not installed. Running without parallelization..."
      python -m pytest e2e/tests/ -v --tb=line 2>&1 | tee e2e_tests.log
    fi
    ;;

  "full"|*)
    echo -e "${GREEN}Running FULL mode (all tests, sequential for problematic ones)...${NC}"
    # Run tests without parallelization (safest option)
    python -m pytest e2e/tests/ -v --tb=line 2>&1 | tee e2e_tests.log
    ;;
esac

# Summary
echo -e "\n${GREEN}=== Test Run Complete ===${NC}"
PASSED=$(grep -c "PASSED" e2e_tests.log || echo 0)
FAILED=$(grep -c "FAILED" e2e_tests.log || echo 0)
echo "Passed: $PASSED"
echo "Failed: $FAILED"
