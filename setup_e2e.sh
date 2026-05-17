#!/bin/bash
# E2E Test Environment Setup Helper
# Run this once to prepare for E2E testing

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

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

# ============================================================================
# MAIN
# ============================================================================

print_header "SmartTrade E2E Test Setup"

# Check Python
print_info "Checking Python installation..."
if ! command -v python3 &> /dev/null; then
  print_error "Python 3 is required but not installed"
  exit 1
fi
PYTHON_VERSION=$(python3 --version | awk '{print $2}')
print_success "Python $PYTHON_VERSION found"

# Check if requirements.txt exists
if [[ ! -f "e2e/requirements.txt" ]]; then
  print_error "e2e/requirements.txt not found"
  exit 1
fi

# Install dependencies
print_info "Installing test dependencies..."
print_info "This may take a minute..."
echo ""

if python3 -m pip install -r e2e/requirements.txt -q; then
  print_success "Dependencies installed"
else
  print_error "Failed to install dependencies"
  exit 1
fi

echo ""

# Verify key packages
print_info "Verifying installation..."
echo ""

PACKAGES=("pytest" "pytest-asyncio" "pytest-timeout" "aiohttp" "pydantic")
FAILED=0

for pkg in "${PACKAGES[@]}"; do
  if python3 -c "import ${pkg//-/_}" 2>/dev/null; then
    print_success "$pkg installed"
  else
    print_error "$pkg not found"
    FAILED=$((FAILED + 1))
  fi
done

echo ""

if [[ $FAILED -gt 0 ]]; then
  print_error "$FAILED package(s) failed to install"
  print_info "Try again with: pip install -r e2e/requirements.txt"
  exit 1
fi

# Create directories
print_info "Creating directories..."
mkdir -p test-results
print_success "test-results/ directory created"

echo ""

# Print next steps
print_header "Setup Complete!"

echo "Next steps:"
echo ""
echo "1. Start services:"
echo "   ${YELLOW}docker compose -f docker-compose.e2e.yml up -d${NC}"
echo ""
echo "2. Run tests:"
echo "   ${YELLOW}./run_e2e_tests.sh quick${NC}     (smoke tests, ~2 min)"
echo "   ${YELLOW}./run_e2e_tests.sh full${NC}      (all tests, ~30 min)"
echo ""
echo "3. View help:"
echo "   ${YELLOW}./run_e2e_tests.sh --help${NC}"
echo ""

print_success "Ready to run E2E tests!"
