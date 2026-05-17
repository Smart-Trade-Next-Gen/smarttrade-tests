#!/bin/bash
# E2E Test Setup Verification
# Run this to verify your test environment is ready

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

FAILED=0
PASSED=0

print_header() {
  echo -e "\n${BLUE}========================================${NC}"
  echo -e "${BLUE}$1${NC}"
  echo -e "${BLUE}========================================${NC}\n"
}

check_pass() {
  echo -e "${GREEN}✓ $1${NC}"
  PASSED=$((PASSED + 1))
}

check_fail() {
  echo -e "${RED}✗ $1${NC}"
  FAILED=$((FAILED + 1))
}

check_warn() {
  echo -e "${YELLOW}⚠ $1${NC}"
}

# ============================================================================
# MAIN
# ============================================================================

print_header "SmartTrade E2E Setup Verification"

# Python
echo -n "Checking Python... "
if command -v python3 &> /dev/null; then
  PYVER=$(python3 --version 2>&1 | awk '{print $2}')
  check_pass "Python $PYVER"
else
  check_fail "Python 3 not found"
fi

# pytest
echo -n "Checking pytest... "
if python3 -m pytest --version &> /dev/null; then
  check_pass "pytest installed"
else
  check_fail "pytest not installed (run: bash setup_e2e.sh)"
fi

# pytest-asyncio
echo -n "Checking pytest-asyncio... "
if python3 -c "import pytest_asyncio" 2>/dev/null; then
  check_pass "pytest-asyncio installed"
else
  check_fail "pytest-asyncio not installed (run: bash setup_e2e.sh)"
fi

# Test files
echo -n "Checking test files... "
if [[ -d "e2e/tests" ]]; then
  TESTCOUNT=$(find e2e/tests -name "test_*.py" 2>/dev/null | wc -l)
  if [[ $TESTCOUNT -gt 0 ]]; then
    check_pass "$TESTCOUNT test files found"
  else
    check_fail "No test files found in e2e/tests/"
  fi
else
  check_fail "e2e/tests/ directory not found"
fi

# Test config
echo -n "Checking pytest config... "
if [[ -f "e2e/pytest.ini" ]]; then
  check_pass "pytest.ini found"
else
  check_fail "pytest.ini not found"
fi

# Conftest
echo -n "Checking test fixtures... "
if [[ -f "e2e/conftest.py" ]]; then
  check_pass "conftest.py found"
else
  check_fail "conftest.py not found"
fi

echo ""

# Service connectivity
print_header "Checking Service Connectivity"

# PostgreSQL
echo -n "Checking PostgreSQL (localhost:5432)... "
if python3 -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('localhost', 5432)); s.close()" 2>/dev/null; then
  check_pass "PostgreSQL accessible"
else
  check_warn "PostgreSQL not accessible on localhost:5432 (may be expected if not running)"
fi

# Redis
echo -n "Checking Redis (localhost:6379)... "
if python3 -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('localhost', 6379)); s.close()" 2>/dev/null; then
  check_pass "Redis accessible"
else
  check_warn "Redis not accessible on localhost:6379 (may be expected if not running)"
fi

# MDS Service
echo -n "Checking MDS Service (localhost:8004)... "
if python3 -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('localhost', 8004)); s.close()" 2>/dev/null; then
  check_pass "MDS Service accessible"
else
  check_warn "MDS Service not accessible on localhost:8004 (may be expected if not running)"
fi

# BAS Service
echo -n "Checking BAS Service (localhost:8005)... "
if python3 -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('localhost', 8005)); s.close()" 2>/dev/null; then
  check_pass "BAS Service accessible"
else
  check_warn "BAS Service not accessible on localhost:8005 (may be expected if not running)"
fi

echo ""

# Directories
print_header "Checking Directories"

echo -n "Checking test-results directory... "
if mkdir -p test-results 2>/dev/null; then
  check_pass "test-results/ ready"
else
  check_fail "Cannot create test-results/"
fi

# Summary
echo ""
print_header "Summary"

if [[ $FAILED -eq 0 ]]; then
  echo -e "${GREEN}All critical checks passed!${NC}"
  echo ""
  echo "Next steps:"
  echo "  1. Start services: ${YELLOW}docker compose -f docker-compose.e2e.yml up -d${NC}"
  echo "  2. Run tests:     ${YELLOW}./run_e2e_tests.sh quick${NC}"
  echo ""
  exit 0
else
  echo -e "${RED}$FAILED critical check(s) failed${NC}"
  echo -e "${GREEN}$PASSED check(s) passed${NC}"
  echo ""
  echo "Fix failures and try again:"
  echo "  ${YELLOW}bash setup_e2e.sh${NC}"
  echo ""
  exit 1
fi
