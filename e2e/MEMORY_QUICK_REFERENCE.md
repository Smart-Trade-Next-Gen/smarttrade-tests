# Memory Optimization - Quick Reference

## TL;DR

**DO**:
- ✅ Use `asyncio.Semaphore(N)` for >5 concurrent tasks
- ✅ Clear fixtures in teardown: `yield resource; resource.cleanup()`
- ✅ Run tests: `pytest -n 2` (not `-n auto`)
- ✅ Keep tests <30 seconds each
- ✅ Function-scope all fixtures (not session-scope)

**DON'T**:
- ❌ `await asyncio.gather(*tasks)` without a limit
- ❌ Accumulate data in global dicts/lists
- ❌ Use `-n auto` (unbounded parallelism)
- ❌ Session-scope large data structures
- ❌ Leave opened connections/streams unfinished

---

## Common Patterns

### Bounded Concurrency Pattern

```python
# Limit to 10 concurrent operations
semaphore = asyncio.Semaphore(10)

async def bounded_operation(item):
    async with semaphore:
        return await perform_operation(item)

results = await asyncio.gather(*[bounded_operation(item) for item in items])
```

### Fixture Cleanup Pattern

```python
@pytest.fixture
def my_fixture():
    resource = create_resource()
    yield resource
    resource.cleanup()  # Always run this
```

### Async Fixture Pattern

```python
@pytest.fixture
async def my_async_fixture():
    async with Client() as client:  # Auto-cleanup
        yield client
```

---

## Memory Limits in Tests

| Component | Limit | Reason |
|-----------|-------|--------|
| Concurrent orders | 10 | Prevent memory spike |
| Concurrent cancellations | 5 | Limit API load |
| Event buffer | 1000/order | Ring-buffer overflow |
| Test timeout | 30s | Catch hangs early |
| Parallel workers | 2-4 | 2-4GB total |

---

## Running Tests

```bash
# Good: Limited parallelism
pytest -n 2 smarttrade-tests/e2e/tests

# Good: Sequential (smallest memory)
pytest smarttrade-tests/e2e/tests

# Good: With specific markers
pytest -m smoke -n 2

# BAD: Unbounded parallelism (causes OOM)
pytest -n auto smarttrade-tests/e2e/tests
```

---

## Debugging Memory Issues

```bash
# Check peak memory
ps aux | grep pytest | head -5

# Run with verbose logging
pytest -vvs smarttrade-tests/e2e/tests/test_one.py

# Profile memory
python -m memory_profiler test_one.py

# Run single test to isolate issue
pytest smarttrade-tests/e2e/tests/test_one.py::test_market_buy_full_fill -v
```

---

## When to Use Semaphore

| Scenario | Limit | Example |
|----------|-------|---------|
| 1-3 concurrent items | None (small) | Individual order placement |
| 5-50 concurrent items | 5-10 | Batch order placement |
| 100+ concurrent items | 10-20 | Stress test scenarios |
| Unbounded | 10 | Always use semaphore |

---

## Checklist for New Tests

- [ ] Test takes <30 seconds
- [ ] All fixtures are function-scoped
- [ ] No unbounded `asyncio.gather()`
- [ ] Cleanup happens in fixture teardown
- [ ] Test passes with `-n 2`
- [ ] Memory usage <500MB

---

## Files to Read

1. **MEMORY_OPTIMIZATION.md** - Full guide with examples
2. **OPTIMIZATION_CHANGELOG.md** - Detailed change log
3. **pytest.ini** - Configuration and limits
4. **conftest.py** - Fixture implementations

---

## Support

Questions about memory optimization? Check these:

1. Is your operation unbounded? → Add Semaphore
2. Are fixtures leaking? → Check teardown
3. Is memory not freed? → Clear after use
4. Are tests timing out? → Reduce concurrency
5. Still running out of memory? → Profile with memory_profiler

