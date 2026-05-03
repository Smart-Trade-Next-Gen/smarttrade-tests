# Phase 5 Fix Guide: Hard Assertions for Existing Tests

## Overview
This guide shows how to fix position assertions in existing test files to use `portfolio_client.wait_for_position()` instead of the broken `bas_client.get_positions()`.

## Pattern Applied to test_order_lifecycle_injection.py

### Changes Made
1. **Add fixtures to function signature**:
   ```python
   async def test_name(
       config,  # NEW
       instrument_catalog,  # NEW
       ...existing fixtures...,
       portfolio_client,  # NEW
       ...
   ):
   ```

2. **Replace hardcoded instrument IDs**:
   ```python
   # Before
   instrument_id = "INSTR_NSE_SBIN_EQ"
   
   # After
   instrument = instrument_catalog.get_any_equity(1)[0]
   instrument_id = instrument["id"]
   ```

3. **Replace broker_id hardcoding**:
   ```python
   # Before
   broker_id = "fyers"
   
   # After
   broker_id = config.broker_id
   ```

4. **Replace timeouts**:
   ```python
   # Before
   timeout=15.0
   
   # After
   timeout=config.timeout_medium
   ```

5. **Replace position assertion try/except blocks**:
   ```python
   # Before (soft assertion)
   try:
       post_positions = await bas_client.get_positions(broker_id, test_account_id)
       assertions.assert_position_state(
           post_positions,
           "INSTR_NSE_SBIN_EQ",
           expected_qty=100,
           expected_avg_price=Decimal("550.00"),
       )
       logger.info("✓ Position state validated")
   except Exception as e:
       logger.warning(f"Position retrieval not available yet: {e}")
   
   # After (hard assertion)
   position = await portfolio_client.wait_for_position(
       instrument_id=instrument_id,
       expected_qty=100,
       timeout=config.timeout_medium,
   )
   assert position["net_qty"] == 100
   assert Decimal(position["avg_price"]) == Decimal("550.00")
   logger.info("✓ Position state validated via Portfolio Service")
   ```

## Files to Fix (Priority Order)

### Tier 1 (Critical - Multiple Position Assertions)
1. **test_partial_fills_injection.py** — Validates WAP with multiple fills
   - Search for: `try:` + `get_positions`
   - Count: ~3-5 position assertion blocks
   - Complexity: Low (apply same pattern)

2. **test_concurrent_orders_injection.py** — Multiple concurrent orders
   - Search for: `try:` + `get_positions`
   - Count: ~2-3 assertion blocks
   - Complexity: Low

### Tier 2 (Medium - Some Position Assertions)
3. **test_error_paths_injection.py** — Error handling tests
   - May have position assertions
   - Search for: `try:` + `get_positions`

4. **test_cancel_orders_injection.py** — Cancellation scenarios
   - May have position assertions
   - Search for: `try:` + `get_positions`

### Tier 3 (Review Only - No Position Assertions Expected)
5. **test_resilience_*.py** files
   - May have soft assertions
   - Search for: `try:` + `except Exception`

## Step-by-Step Fix Process

### For Each Test File:

1. **Add imports** (if not present):
   ```python
   from e2e.clients import PortfolioClient  # Usually already imported via fixture
   ```

2. **Update function signature**:
   ```python
   async def test_name(
       config,  # ADD THIS
       instrument_catalog,  # ADD THIS
       ...existing fixtures...,
       portfolio_client,  # ADD THIS
   ):
   ```

3. **Find and replace hardcoded values**:
   ```bash
   # Find: "INSTR_NSE_.*_EQ"
   # Replace with: instrument_catalog.get_any_equity(1)[0]["id"]
   
   # Find: broker_id = "fyers"
   # Replace with: broker_id = config.broker_id
   
   # Find: timeout=15.0
   # Replace with: timeout=config.timeout_medium
   ```

4. **Replace position assertion blocks** (the critical part):
   - Look for: `try:` followed by `get_positions`
   - Delete the entire try/except block
   - Replace with hard assertion pattern above

5. **Verify**:
   - Run `pytest tests/test_file.py -v` to verify fixes
   - All tests should pass (not skip position checks)

## Assertion Pattern Templates

### For BUY orders:
```python
position = await portfolio_client.wait_for_position(
    instrument_id=instrument_id,
    expected_qty=qty,
    timeout=config.timeout_medium,
)
assert position["net_qty"] == qty
assert Decimal(position["avg_price"]) == price
logger.info(f"✓ Position validated: BUY {qty} @ {price}")
```

### For SELL orders (negative qty):
```python
position = await portfolio_client.wait_for_position(
    instrument_id=instrument_id,
    expected_qty=-qty,
    timeout=config.timeout_medium,
)
assert position["net_qty"] == -qty
assert Decimal(position["avg_price"]) == price
logger.info(f"✓ Position validated: SELL {qty} @ {price} (short)")
```

### For partial fills (WAP validation):
```python
position = await portfolio_client.wait_for_position(
    instrument_id=instrument_id,
    expected_qty=total_qty,
    timeout=config.timeout_medium,
)
expected_wap = Decimal(expected_wap_value)
actual_wap = Decimal(position["avg_price"])
assert position["net_qty"] == total_qty
assert actual_wap == expected_wap
logger.info(f"✓ Position WAP validated: {actual_wap}")
```

## Testing Your Fixes

```bash
# Test a single file
pytest e2e/tests/test_order_lifecycle_injection.py -v

# Test all injection tests
pytest e2e/tests/ -m injection -v

# Run with detailed logging
pytest e2e/tests/test_order_lifecycle_injection.py -v -s
```

## Expected Results
- All tests should pass (green ✓)
- No "position retrieval not available" warnings
- Position state is now properly validated via Portfolio Service
- Tests fail loudly if position doesn't appear (no silent skips)

## Common Mistakes to Avoid
1. ❌ Forgetting to add `portfolio_client` to function signature
2. ❌ Using `config.timeout_slow` (15-30s too long, use `timeout_medium` = 10s)
3. ❌ Leaving hardcoded `"INSTR_NSE_SBIN_EQ"` values
4. ❌ Not removing the old try/except blocks completely
5. ❌ Using wrong expected_qty (check if BUY=positive, SELL=negative)

## Summary
After fixing all files per this guide:
- Position assertions become hard (fail fast, don't skip)
- Tests use real instruments from MDS (not hardcoded)
- Position truth comes from Portfolio Service (correct source)
- All test files follow consistent pattern
