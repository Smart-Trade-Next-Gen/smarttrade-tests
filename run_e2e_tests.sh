#!/bin/bash
# SmartTrade E2E Test Runner
# Run with: ./run_e2e_tests.sh [mode] [options]

set -e

# Determine script directory and project root
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Test run config
MODE="${1:-full}"
WORKERS="${E2E_PYTEST_WORKERS:-2}"
PYTHON_PATH="${PYTHONPATH}:$PROJECT_ROOT/e2e"
LOG_DIR="$PROJECT_ROOT/test-results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/e2e_tests_${TIMESTAMP}.log"

# ============================================================================
# FUNCTIONS
# ============================================================================

print_header() {
  echo -e "\n${BLUE}========================================${NC}"
  echo -e "${BLUE}$1${NC}"
  echo -e "${BLUE}========================================${NC}\n"
}

print_success() {
  echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
  echo -e "${RED}✗ $1${NC}"
}

print_info() {
  echo -e "${YELLOW}ℹ $1${NC}"
}

show_help() {
  cat << EOF
${BLUE}SmartTrade E2E Test Runner${NC}

Usage: ./run_e2e_tests.sh [MODE] [OPTIONS]

${BLUE}Modes:${NC}
  quick      Run QUICK mode (smoke tests only, ~2 min)
  smoke      Run SMOKE mode (critical paths, ~5 min)
  injection  Run INJECTION tests (deterministic, ~10 min)
  real       Run REAL EXECUTION tests (price-driven, ~15 min)
  resilience Run RESILIENCE tests (chaos, ~30 min)
  sequential Run SEQUENTIAL mode (safe order, ~30 min)
  parallel   Run PARALLEL mode (all tests with -n workers)
  full       Run FULL mode (all tests, sequential) [default]

${BLUE}Options:${NC}
  --help      Show this help message
  --skip-deps Don't verify dependencies
  --skip-env  Don't check environment
  --no-log    Don't write to log file
  --open      Open HTML report after completion

${BLUE}Environment Variables:${NC}
  E2E_PYTEST_WORKERS  Number of parallel workers (default: 2)
  PYTHONPATH          Python path (auto-set)

${BLUE}Examples:${NC}
  ./run_e2e_tests.sh quick
  ./run_e2e_tests.sh injection --open
  E2E_PYTEST_WORKERS=4 ./run_e2e_tests.sh parallel

EOF
}

check_dependencies() {
  print_info "Checking dependencies..."

  # Check Python
  if ! command -v python3 &> /dev/null; then
    print_error "Python 3 not found"
    return 1
  fi
  print_success "Python 3 found: $(python3 --version)"

  # Check pytest
  if ! python3 -m pytest --version &> /dev/null; then
    print_error "pytest not installed"
    echo "Install with: pip install -r e2e/requirements.txt"
    return 1
  fi
  print_success "pytest found: $(python3 -m pytest --version | head -1)"

  # Check pytest-asyncio
  if ! python3 -c "import pytest_asyncio" 2>/dev/null; then
    print_error "pytest-asyncio not installed"
    echo "Install with: pip install -r e2e/requirements.txt"
    return 1
  fi
  print_success "pytest-asyncio found"

  return 0
}

check_environment() {
  print_info "Checking environment..."

  # Check if conftest exists
  if [[ ! -f "$PROJECT_ROOT/e2e/conftest.py" ]]; then
    print_error "conftest.py not found in e2e/"
    return 1
  fi
  print_success "Test configuration found"

  # Check if tests directory exists
  if [[ ! -d "$PROJECT_ROOT/e2e/tests" ]]; then
    print_error "tests/ directory not found in e2e/"
    return 1
  fi
  print_success "Test files found"

  # Create log directory
  mkdir -p "$LOG_DIR"
  print_success "Log directory ready: $LOG_DIR"

  return 0
}

run_tests() {
  local mode="$1"
  local cmd_args="$2"

  export PYTHONPATH="$PYTHON_PATH"

  if [[ "$NO_LOG" == "true" ]]; then
    cd "$PROJECT_ROOT"
    python3 -m pytest $cmd_args
  else
    cd "$PROJECT_ROOT"
    echo "Saving results to: $LOG_FILE"
    python3 -m pytest $cmd_args 2>&1 | tee "$LOG_FILE"
  fi
}

parse_results() {
  if [[ "$NO_LOG" == "true" ]]; then
    return 0
  fi

  if [[ ! -f "$LOG_FILE" ]]; then
    return 0
  fi

  echo -e "\n${BLUE}========================================${NC}"
  echo -e "${BLUE}Test Results Summary${NC}"
  echo -e "${BLUE}========================================${NC}\n"

  # Parse pytest output more robustly
  if grep -q "passed" "$LOG_FILE"; then
    local passed=$(grep -oP '\d+(?= passed)' "$LOG_FILE" | tail -1)
    print_success "$passed tests passed"
  fi

  if grep -q "failed" "$LOG_FILE"; then
    local failed=$(grep -oP '\d+(?= failed)' "$LOG_FILE" | tail -1)
    print_error "$failed tests failed"
  fi

  if grep -q "error" "$LOG_FILE"; then
    local errors=$(grep -oP '\d+(?= error)' "$LOG_FILE" | tail -1)
    print_error "$errors tests had errors"
  fi

  # Show test summary line
  echo ""
  grep -E "passed|failed|error" "$LOG_FILE" | tail -1 || true
  echo ""
}

# ============================================================================
# MAIN
# ============================================================================

print_header "SmartTrade E2E Test Runner"
echo "Mode: ${YELLOW}$MODE${NC}"
echo "Timestamp: ${YELLOW}$TIMESTAMP${NC}"
echo ""

# Parse options
SKIP_DEPS=false
SKIP_ENV=false
NO_LOG=false
OPEN_REPORT=false

shift # Remove mode from arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --help)
      show_help
      exit 0
      ;;
    --skip-deps)
      SKIP_DEPS=true
      shift
      ;;
    --skip-env)
      SKIP_ENV=true
      shift
      ;;
    --no-log)
      NO_LOG=true
      shift
      ;;
    --open)
      OPEN_REPORT=true
      shift
      ;;
    *)
      print_error "Unknown option: $1"
      show_help
      exit 1
      ;;
  esac
done

# Verify setup
if [[ "$SKIP_DEPS" != "true" ]]; then
  if ! check_dependencies; then
    echo ""
    print_error "Setup failed. Install dependencies and try again:"
    echo "  pip install -r e2e/requirements.txt"
    exit 1
  fi
  echo ""
fi

if [[ "$SKIP_ENV" != "true" ]]; then
  if ! check_environment; then
    echo ""
    print_error "Environment check failed"
    exit 1
  fi
  echo ""
fi

# Run tests based on mode
case $MODE in
  "quick")
    print_header "QUICK Mode (Smoke Tests)"
    run_tests "quick" "e2e/tests/ -m smoke -v --tb=short"
    ;;

  "smoke")
    print_header "SMOKE Mode (Critical Paths)"
    run_tests "smoke" "e2e/tests/ -m smoke -v --tb=short"
    ;;

  "injection")
    print_header "INJECTION Mode (Deterministic Tests)"
    run_tests "injection" "e2e/tests/ -m injection -v --tb=short"
    ;;

  "real")
    print_header "REAL EXECUTION Mode"
    run_tests "real" "e2e/tests/ -m real_execution -v --tb=short"
    ;;

  "resilience")
    print_header "RESILIENCE Mode (Chaos Tests)"
    run_tests "resilience" "e2e/tests/ -m resilience -v --tb=short"
    ;;

  "sequential")
    print_header "SEQUENTIAL Mode (Staged Test Execution)"

    print_info "Stage 1: Resilience tests..."
    run_tests "sequential_1" "e2e/tests/ -m resilience -v --tb=short"

    print_info "Stage 2: Error path tests..."
    run_tests "sequential_2" "e2e/tests/test_error_paths_injection.py -v --tb=short"

    print_info "Stage 3: Partial fills..."
    run_tests "sequential_3" "e2e/tests/test_partial_fills_injection.py -v --tb=short"

    print_info "Stage 4: Order lifecycle..."
    run_tests "sequential_4" "e2e/tests/test_order_lifecycle_injection.py -v --tb=short"

    print_info "Stage 5: Concurrent orders..."
    run_tests "sequential_5" "e2e/tests/test_concurrent_orders_injection.py -v --tb=short"
    ;;

  "parallel")
    print_header "PARALLEL Mode"
    if command -v pytest &> /dev/null && python3 -m pytest --version 2>&1 | grep -q xdist; then
      print_info "Using $WORKERS worker(s)"
      run_tests "parallel" "e2e/tests/ -n $WORKERS --dist=loadscope -v --tb=short"
    else
      print_error "pytest-xdist not available. Install with: pip install pytest-xdist"
      print_info "Running without parallelization instead..."
      run_tests "parallel" "e2e/tests/ -v --tb=short"
    fi
    ;;

  "full"|*)
    print_header "FULL Mode (All Tests)"
    run_tests "full" "e2e/tests/ -v --tb=short"
    ;;
esac

EXIT_CODE=$?

# Parse and display results
parse_results

# Open report if requested
if [[ "$OPEN_REPORT" == "true" ]] && [[ -f "$LOG_FILE" ]]; then
  if command -v xdg-open &> /dev/null; then
    xdg-open "$LOG_FILE" || true
  elif command -v open &> /dev/null; then
    open "$LOG_FILE" || true
  fi
fi

# Final status
if [[ $EXIT_CODE -eq 0 ]]; then
  echo ""
  print_success "All tests completed successfully!"
else
  echo ""
  print_error "Tests completed with failures. See log: $LOG_FILE"
fi

echo ""

exit $EXIT_CODE
