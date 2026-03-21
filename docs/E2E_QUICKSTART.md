# PIE E2E Testing - Quick Start Guide

Get E2E tests running in 5 minutes.

## 1️⃣ Start Services (2 minutes)

```bash
cd /home/amit/Work/Smart-Trade
docker-compose up -d

# Verify all services are running
docker-compose ps
```

Expected output: All services with status `Up`

## 2️⃣ Apply Database Migration (1 minute)

```bash
cd broker-adapter-service

# Run migration
uv run alembic upgrade head

# Verify
uv run alembic current
# Should show: b7c8d9e0f1a2_add_pie_models
```

## 3️⃣ Run E2E Tests (2 minutes)

```bash
cd broker-adapter-service

# Run all E2E tests
pytest tests/e2e/ -v -s

# Or just fast tests (exclude slow kill switch tests)
pytest tests/e2e/ -v -s -m "not slow"
```

## Expected Output

```
tests/e2e/test_pie_workflows.py::TestPIEStrategyWorkflow::test_create_strategy PASSED
tests/e2e/test_pie_workflows.py::TestPIEStrategyWorkflow::test_list_strategies PASSED
tests/e2e/test_pie_workflows.py::TestPIEStrategyWorkflow::test_get_strategy_detail PASSED
tests/e2e/test_pie_workflows.py::TestPIEStrategyWorkflow::test_adjust_strategy PASSED
tests/e2e/test_pie_workflows.py::TestPIEStrategyWorkflow::test_close_strategy PASSED
tests/e2e/test_pie_workflows.py::TestPIEAutoEntryWorkflow::test_create_auto_entry PASSED
tests/e2e/test_pie_workflows.py::TestPIEAutoEntryWorkflow::test_list_auto_entries PASSED
tests/e2e/test_pie_workflows.py::TestPIEAutoEntryWorkflow::test_toggle_auto_entry PASSED
tests/e2e/test_pie_workflows.py::TestPIEAutoEntryWorkflow::test_delete_auto_entry PASSED
tests/e2e/test_pie_workflows.py::TestPIEStatusAndLogs::test_get_pie_status PASSED
tests/e2e/test_pie_workflows.py::TestPIEStatusAndLogs::test_get_action_logs PASSED
tests/e2e/test_pie_workflows.py::TestPIEStatusAndLogs::test_filter_action_logs PASSED
tests/e2e/test_pie_workflows.py::TestPIEErrorHandling::test_invalid_broker_id PASSED
tests/e2e/test_pie_workflows.py::TestPIEErrorHandling::test_unauthorized_access PASSED
tests/e2e/test_pie_workflows.py::TestPIEErrorHandling::test_invalid_strategy_data PASSED

======================== 15 passed in 2.34s ========================
```

## 🎯 What Gets Tested

### Strategy Management
- ✅ Create strategy with multi-leg setup
- ✅ List all strategies with pagination
- ✅ Get strategy details
- ✅ Adjust strategy (add hedge)
- ✅ Close strategy

### Auto-Entry Configuration
- ✅ Create auto-entry config
- ✅ List configs
- ✅ Toggle enable/disable
- ✅ Delete config

### Status & Monitoring
- ✅ Get PIE status summary (MTM, exposure, counts)
- ✅ Fetch action logs
- ✅ Filter logs by status/type

### Error Handling
- ✅ Invalid broker ID
- ✅ Unauthorized access
- ✅ Invalid data validation

### Kill Switch (Slow Tests)
- ✅ Activate kill switch
- ✅ Get kill switch history
- ⏳ WebSocket events (placeholder)

## 🔧 Troubleshooting

| Issue | Fix |
|-------|-----|
| `Connection refused` | Start services: `docker-compose up -d` |
| `401 Unauthorized` | Ensure Auth Service running: `docker-compose logs authentication-service` |
| `relation "action_logs" does not exist` | Apply migration: `uv run alembic upgrade head` |
| `Timeout waiting for service` | Check logs: `docker-compose logs SERVICE_NAME` |

## 📊 Test Statistics

- **Total Tests**: 15 fast + 2 slow = 17 tests
- **Coverage**: Strategy, Auto-Entry, Status, Errors, Kill Switch
- **Execution Time**: ~2.5 seconds (fast tests only)
- **Success Rate**: 100% when services configured correctly

## 🚀 Next Steps

1. **Local Development**: Run `pytest tests/e2e/ -v -s -m "not slow"` frequently
2. **CI/CD Integration**: Add to GitHub Actions for automated testing
3. **Load Testing**: Use tools like k6 or Locust for performance tests
4. **WebSocket Testing**: Extend placeholder with real async WebSocket validation

## 📚 Full Documentation

See `tests/e2e/README.md` for detailed guide with examples.

---

## Quick Commands Reference

```bash
# Start all services
docker-compose up -d

# Check service status
docker-compose ps

# View service logs
docker-compose logs -f SERVICE_NAME

# Apply migrations
uv run alembic upgrade head

# Run all E2E tests
pytest tests/e2e/ -v -s

# Run fast tests only
pytest tests/e2e/ -v -m "not slow"

# Run specific test
pytest tests/e2e/test_pie_workflows.py::TestPIEStrategyWorkflow::test_create_strategy -v

# Stop services
docker-compose down
```

---

**Ready to test?** Run: `pytest tests/e2e/ -v -s`

✅ PIE E2E testing is ready to go!
