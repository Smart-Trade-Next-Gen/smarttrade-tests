# E2E Test Runner - Troubleshooting Guide

This guide covers common issues and solutions for running E2E tests.

## Diagnostic Commands

Before troubleshooting, run these to understand your setup:

```bash
# Verify entire setup
bash check_e2e_setup.sh

# List available tests
ls -la e2e/tests/test_*.py

# Check pytest version and plugins
python3 -m pytest --version

# View pytest configuration
cat e2e/pytest.ini

# Check environment
env | grep -E "PYTHONPATH|PATH|VIRTUAL"
```

---

## ❌ Common Issues & Solutions

### 1. "pytest: command not found"

**Error Message**:
```
./run_e2e_tests.sh: line X: pytest: command not found
```

**Root Cause**: pytest is not installed

**Solution**:
```bash
# Install dependencies
bash setup_e2e.sh

# Or manually
pip install -r e2e/requirements.txt
```

**Verify**:
```bash
python3 -m pytest --version
```

---

### 2. "ModuleNotFoundError: No module named 'e2e'"

**Error Message**:
```
ModuleNotFoundError: No module named 'e2e'
ERROR collecting e2e/tests/...
```

**Root Cause**: PYTHONPATH not set correctly

**Solution**:
```bash
# Option 1: Let the script handle it
./run_e2e_tests.sh quick

# Option 2: Set manually
export PYTHONPATH="$PWD/e2e:$PYTHONPATH"
python3 -m pytest e2e/tests/ -v
```

**Verify**:
```bash
echo $PYTHONPATH
python3 -c "import e2e; print(e2e.__file__)"
```

---

### 3. Tests fail with connection refused (5432 or 6379)

**Error Message**:
```
ConnectionRefusedError: [Errno 111] Connection refused
asyncpg.exceptions.CannotConnectNowError
redis.exceptions.ConnectionError
```

**Root Cause**: PostgreSQL or Redis not running

**Solution**:
```bash
# Check Docker is running
docker ps

# Start services
docker compose -f docker-compose.e2e.yml up -d

# Verify services
docker ps | grep -E "postgres|redis"
```

**Check Connectivity**:
```bash
# PostgreSQL
psql -h localhost -U postgres -d smarttrade_paper_broker_service -c "SELECT 1"

# Redis
redis-cli ping
```

---

### 4. "Address already in use" for port 8004, 8005, etc.

**Error Message**:
```
OSError: [Errno 98] Address already in use
ERROR: for mds Cannot start service mds: bind: address already in use
```

**Root Cause**: Service port already in use from previous run

**Solution**:
```bash
# Kill lingering processes
pkill -f "uvicorn"
pkill -f "pytest"

# Stop Docker services
docker compose -f docker-compose.e2e.yml down

# Wait 5 seconds
sleep 5

# Restart
docker compose -f docker-compose.e2e.yml up -d

# Or kill specific port (example: 8004)
lsof -ti:8004 | xargs kill -9
```

---

### 5. Tests timeout or hang indefinitely

**Error Message**:
```
Timeout >30.0s
FAILED - Timeout
Test hang (no output for >5 min)
```

**Root Cause**: 
- Services are slow/unresponsive
- Network connectivity issues
- Deadlock in async code

**Solution**:
```bash
# Check service health
curl -s http://localhost:8005/health | python3 -m json.tool

# Check logs from Docker
docker logs mds
docker logs bas
docker logs postgres

# Try quick smoke test
./run_e2e_tests.sh quick --no-log

# Increase timeout temporarily
export PYTEST_TIMEOUT=60
./run_e2e_tests.sh quick

# Kill and restart services
docker compose -f docker-compose.e2e.yml restart
```

---

### 6. Tests fail randomly, pass sometimes

**Error Message**:
```
FAILED test_order_lifecycle_injection.py::test_place_market_buy_order
ERROR: Test passed on retry
Flaky test
```

**Root Cause**:
- Insufficient cleanup between tests
- Race conditions in async code
- Weak service isolation

**Solution**:
```bash
# Run specific test multiple times
export PYTHONPATH="$PWD/e2e:$PYTHONPATH"
cd e2e
pytest tests/test_order_lifecycle_injection.py::test_place_market_buy_order -v --count=5

# Run in sequential mode
../run_e2e_tests.sh sequential

# Check service logs
docker logs bas | tail -100
docker logs mds | tail -100

# Restart all services
docker compose -f docker-compose.e2e.yml down && docker compose -f docker-compose.e2e.yml up -d
```

---

### 7. "No module named 'pytest_asyncio'"

**Error Message**:
```
ModuleNotFoundError: No module named 'pytest_asyncio'
ERROR: could not load plugin 'pytest_asyncio'
```

**Root Cause**: pytest-asyncio not installed

**Solution**:
```bash
# Reinstall dependencies
bash setup_e2e.sh

# Or manually
pip install pytest-asyncio

# Verify
python3 -c "import pytest_asyncio; print(pytest_asyncio.__version__)"
```

---

### 8. Docker services stuck or unresponsive

**Symptoms**:
```
docker-compose up hangs
Service logs show repeated errors
Cannot connect to services
```

**Root Cause**: 
- Docker daemon issues
- Corrupted volumes
- Previous incomplete shutdown

**Solution**:
```bash
# Full cleanup (⚠️ WARNING: Removes all data)
docker compose -f docker-compose.e2e.yml down -v
docker system prune -f

# Restart
docker compose -f docker-compose.e2e.yml up -d

# Check Docker health
docker system info
docker ps -a
```

**Alternative - Restart Docker**:
```bash
# macOS
sudo killall Docker

# Linux
sudo systemctl restart docker
```

---

### 9. Permission denied when running scripts

**Error Message**:
```
permission denied: ./run_e2e_tests.sh
cannot execute binary file
```

**Root Cause**: Scripts not executable

**Solution**:
```bash
# Make scripts executable
chmod +x run_e2e_tests.sh setup_e2e.sh check_e2e_setup.sh

# Verify
ls -la *.sh
```

---

### 10. "PYTHONPATH" still unset after script

**Error Message**:
```
(no pytest output, but tests don't run)
Log shows: "ModuleNotFoundError"
```

**Root Cause**: Parent shell not inheriting PYTHONPATH

**Solution**:
```bash
# Set in current shell
export PYTHONPATH="$PWD/e2e:$PYTHONPATH"

# Verify
echo $PYTHONPATH

# Now run
./run_e2e_tests.sh quick
```

---

## 🔍 Debugging Tips

### View Test Output in Real-Time

```bash
# Run without log file (output to terminal)
./run_e2e_tests.sh quick --no-log

# Verbose pytest output
export PYTHONPATH="$PWD/e2e:$PYTHONPATH"
cd e2e
pytest tests/ -v --tb=long -s
```

### Check Service Logs

```bash
# View all service logs
docker compose -f docker-compose.e2e.yml logs

# Follow specific service
docker compose -f docker-compose.e2e.yml logs -f mds
docker compose -f docker-compose.e2e.yml logs -f bas

# View recent logs with timestamp
docker compose -f docker-compose.e2e.yml logs --tail=50 --timestamps
```

### Manual Test Execution

```bash
# Set environment
export PYTHONPATH="$PWD/e2e:$PYTHONPATH"
cd e2e

# Run single test with full output
pytest tests/test_order_lifecycle_injection.py::test_place_market_buy_order -v -s

# Run with debugging
pytest tests/test_order_lifecycle_injection.py -v --pdb

# Run with print statements
pytest tests/ -v -s
```

### Check Database State

```bash
# Connect to PostgreSQL
psql -h localhost -U postgres -d smarttrade_paper_broker_service

# View tables
\dt

# Check order data
SELECT * FROM "order" LIMIT 5;

# Check positions
SELECT * FROM position LIMIT 5;
```

### Monitor Network Connectivity

```bash
# Test port connectivity
nc -zv localhost 5432      # PostgreSQL
nc -zv localhost 6379      # Redis
nc -zv localhost 8004      # MDS
nc -zv localhost 8005      # BAS

# Or using Python
python3 -c "
import socket
ports = {'PostgreSQL': 5432, 'Redis': 6379, 'MDS': 8004, 'BAS': 8005}
for name, port in ports.items():
    s = socket.socket()
    try:
        s.connect(('localhost', port))
        print(f'✓ {name} accessible')
    except:
        print(f'✗ {name} not accessible')
    finally:
        s.close()
"
```

---

## 📋 Verification Checklist

Run these checks in order:

- [ ] `bash check_e2e_setup.sh` passes
- [ ] `python3 -m pytest --version` works
- [ ] `docker ps` shows services running
- [ ] `curl http://localhost:8005/health` returns 200
- [ ] `./run_e2e_tests.sh quick --no-log` passes
- [ ] `./run_e2e_tests.sh injection` passes 18+ tests
- [ ] `cat test-results/e2e_tests_*.log | tail -5` shows passed count

---

## 🆘 Advanced Debugging

### Enable Verbose Test Logging

Create `e2e/conftest_debug.py`:
```python
import logging

logging.basicConfig(level=logging.DEBUG)
logging.getLogger("asyncio").setLevel(logging.DEBUG)
```

Run with:
```bash
pytest -v -s --log-cli-level=DEBUG
```

### Profile Test Execution

```bash
# Time each test
pytest --durations=10 e2e/tests/

# Profile with py-spy
pip install py-spy
py-spy record -o profile.svg -- pytest e2e/tests/
```

### Generate Test Report

```bash
# HTML report
pytest e2e/tests/ --html=report.html --self-contained-html

# JUnit XML
pytest e2e/tests/ --junit-xml=report.xml

# Coverage report
pytest e2e/tests/ --cov=e2e --cov-report=html
```

---

## 📞 Getting Help

If you still can't resolve the issue:

1. **Collect diagnostics**:
   ```bash
   bash check_e2e_setup.sh > diag.txt 2>&1
   cat test-results/e2e_tests_*.log >> diag.txt
   docker compose -f docker-compose.e2e.yml logs >> diag.txt
   ```

2. **Review logs**:
   ```bash
   cat diag.txt
   ```

3. **Check recent commits**:
   ```bash
   git log --oneline -20
   git log --oneline e2e/
   ```

4. **Ask for help with full context**:
   - Share `diag.txt`
   - Share test output
   - Share `docker ps` output
   - Describe steps to reproduce

---

## ✅ Success Indicators

Tests are working correctly when:

- ✓ `./run_e2e_tests.sh quick` completes in ~2 minutes
- ✓ 2 smoke tests pass
- ✓ No timeout errors
- ✓ No connection refused errors
- ✓ Test results logged to `test-results/`
- ✓ Log shows: "X passed in Y seconds"

---

**Last Updated**: May 2026
**Version**: 1.0
