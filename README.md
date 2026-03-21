# SmartTrade Tests

Cross-service integration and API test artifacts for the SmartTrade trading platform.

> Service-level unit and route tests live inside each service repo. This repo contains cross-service API tests.

## Structure

```
postman/        — Postman collection and environment files
scripts/        — Test runner scripts
docs/           — E2E test guides and quickstart docs
results/        — Test output (gitignored)
```

## Running Tests

### Prerequisites

```bash
npm install -g newman
```

### Run integration tests

```bash
./scripts/run-integration-tests.sh
# or with a custom environment:
./scripts/run-integration-tests.sh postman/Smartapp Local.postman_environment.json
```

### Import into Postman

1. Open Postman
2. Import → `postman/SmartApp Integration Tests.postman_collection.json`
3. Import → `postman/Smartapp Local.postman_environment.json`
4. Select the environment and run the collection

## Environments

| File | Purpose |
|------|---------|
| `Smartapp Local.postman_environment.json` | Local development (localhost ports) |
