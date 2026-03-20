#!/bin/bash
# Run SmartTrade integration tests via Newman (Postman CLI)
# Usage: ./scripts/run-integration-tests.sh [environment]
# Requires: npm install -g newman

set -e

COLLECTION="postman/SmartApp Integration Tests.postman_collection.json"
ENV="${1:-postman/Smartapp Local.postman_environment.json}"

echo "Running integration tests..."
echo "Collection: $COLLECTION"
echo "Environment: $ENV"

newman run "$COLLECTION" \
  --environment "$ENV" \
  --reporters cli,junit \
  --reporter-junit-export results/integration-test-results.xml

echo "Done. Results in results/integration-test-results.xml"
