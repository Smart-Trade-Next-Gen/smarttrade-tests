#!/bin/bash
# Generate HTML report for E2E tests
# Usage: ./generate_report.sh [test_marker]
#   ./generate_report.sh                # All tests
#   ./generate_report.sh smoke          # Smoke tests only
#   ./generate_report.sh injection      # Injection mode tests
#   ./generate_report.sh real_execution # Real execution tests
#   ./generate_report.sh resilience     # Resilience tests

set -e

MARKER=${1:-""}
REPORT_DIR="reports"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Create reports directory
mkdir -p "$REPORT_DIR"

# Run tests with HTML report
if [ -z "$MARKER" ]; then
    echo "🧪 Running ALL E2E tests..."
    python -m pytest e2e/tests/ \
        -v \
        --html="$REPORT_DIR/e2e_report.html" \
        --self-contained-html \
        --tb=short \
        2>&1 | tee "$REPORT_DIR/e2e_tests_$TIMESTAMP.log"
else
    echo "🧪 Running E2E tests with marker: $MARKER"
    python -m pytest e2e/tests/ \
        -m "$MARKER" \
        -v \
        --html="$REPORT_DIR/e2e_report_${MARKER}.html" \
        --self-contained-html \
        --tb=short \
        2>&1 | tee "$REPORT_DIR/e2e_tests_${MARKER}_$TIMESTAMP.log"
fi

REPORT_FILE="$REPORT_DIR/e2e_report${MARKER:+_$MARKER}.html"
echo ""
echo "✅ Report generated: $REPORT_FILE"
echo "📊 Open in browser to view results"
