# E2E Test Run — Failure Report
Run: 2026-05-05 07:41 → 07:46  •  pytest in `/home/amit/Work/Smart-Trade/smarttrade-tests`

## Summary

| Metric | Count |
|---|---|
| Tests collected | 58 |
| **PASSED** | 9 |
| **FAILED** | 46 |
| **Did not complete** | 3 (final websocket-separation tests; pytest timed out at 120s) |

The run is heavily skewed toward failure (~80%). Most failures share a small set of root causes in the BAS → PBS → portfolio/journal pipeline.

## Tests that PASSED (9)
- `test_architecture_boundaries`: 3 of 4
- `test_error_paths_injection`: 3 of 5 (the 3 reject-on-input cases)
- `test_journal_integration::test_journal_trade_recorded_after_fill`
- `test_websocket_client_routing`: 2 of 2

## Tests that FAILED (46)
All other tests failed. Failures cluster across:
- order_lifecycle_injection (4)
- partial_fills_injection (3) + partial_fills_real (3)
- cancel_orders_injection (3)
- concurrent_orders_injection (3)
- error_paths_injection (2)
- event_bus_validation (4)
- execution_stress (3)
- market_buy_real_execution (4)
- portfolio_integration (3)
- journal_integration (2)
- resilience_event_handling (4) + resilience_partial_failures (3) + resilience_timeouts (4)
- architecture_boundaries (1: `test_pbs_does_not_emit_to_execution_topics`)

## Root Causes

The 46 failures are explained by 5 product bugs and 2 test-infrastructure issues. Listed in order of blast radius.

### RC-1 — BAS Paper plugin **overwrites canonical instrument_id with broker symbol** when calling PBS
**File:** `broker-adapter-service/src/broker_adapter_service/plugins/paper/dto_to_paper_mapper.py:41` (and `:84` for multi-leg).

```python
trading_symbol = await master.get_broker_symbol(leg.instrument_id, self.broker_id)  # → "NSE:SBIN"
return {
    ...
    "instrument_id": trading_symbol,   # ← broker symbol stored under instrument_id
    ...
}
```

Effect:
- Test places order with canonical `instrument_id=NSE:SBIN:EQ`.
- BAS rewrites the field to broker symbol `NSE:SBIN`, sends to PBS.
- PBS stores `instrument_id=NSE:SBIN`. Every downstream event (`broker.order_update`, `order.filled`, `trade.executed`) carries `NSE:SBIN`.
- Tests/portfolio query for `NSE:SBIN:EQ` → never matches.

Confirmed in BAS log: `order.placed` outbox payload has `instrument_id: 'NSE:SBIN:EQ'`, but `order.filled` payload has `instrument_id: 'NSE:SBIN'`.

**Fix:** keep `instrument_id` canonical end-to-end; introduce a separate `broker_symbol` field for broker-facing wire format, OR have PBS look up the canonical id and round-trip it.

**Blocks:** every test that asserts on positions, fills, or events keyed by instrument id (~30 tests).

---

### RC-2 — `position.updated` is **never published** to the bus
**Files:** `broker-adapter-service/src/broker_adapter_service/services/order_fill_consumer.py:374-424` (only emits `order.filled` and `trade.executed`); `paper-broker-service/src/paper_broker_service/services/execution_engine.py:267` (comment: "PBS is external broker - doesn't publish trading events").

The flow described in the BAS comments — *PBS emits `position.updated` → BAS consumes → BAS publishes `position.updated`* — does not exist:
- PBS never publishes `position.updated` (grep confirms only `broker.order_update`).
- BAS `position_sync_consumer` (`@subscribe("position.updated")`) therefore never fires.
- Portfolio service `position_consumer.handle_position_updated` never receives an event.

In the captured run, `grep -E "position\.updated" /tmp/e2e_run/*.log` returns zero hits.

**Fix:** either have PBS publish `position.updated` after `execution_engine` updates the position, or have BAS emit `position.updated` directly inside `_process_execution` alongside `order.filled`/`trade.executed`.

**Blocks:** all `test_portfolio_integration.*` and any test that depends on portfolio position state (~10+ tests).

---

### RC-3 — Race: `order.placed` (outbox) vs `order.filled` (direct publish)
**Files:**
- BAS publishes `order.placed` via outbox poller — `broker_adapter_service/services/order_handler.py:316` (`Saved order.placed event to OUTBOX`).
- BAS publishes `order.filled` directly to Redis — `order_fill_consumer.py:507` (`Published order.filled event via EventBus`).
- Portfolio's `handle_order_filled` requires the snapshot to already exist — `portfolio-service/src/portfolio_service/events/order_consumer.py:124` (`update_order` raises `ValueError` if missing).

Captured timeline (portfolio.log, order `2bf0b157`):

```
02:12:15  order.filled received → ERROR Order ... not found (attempt 1)
02:12:16  order.filled retry  → ERROR (attempt 2)
02:12:18  order.filled retry  → ERROR (attempt 3) → DLQ
02:12:18  order.placed processed (too late)
```

Three retries, then the fill is sent to the Redis DLQ and never re-applied → snapshot stays in PENDING with filled_quantity=0, position never aggregated.

**Fix:** either route `order.placed` through the same direct-publish path so ordering is preserved, OR teach the portfolio fill consumer to upsert (create-then-update) when the snapshot is missing, OR have it block/retry with backoff long enough to absorb the outbox cycle.

**Blocks:** all injection tests, partial-fill tests, and any portfolio-dependent assertion on FAST fills (~25 tests).

---

### RC-4 — Journal/Portfolio `process_order_placed` writes `price=None` for MARKET orders → DB `NotNullViolationError`
**Files:**
- `journal-service/src/journal_service/services/order_service.py:61`
- `portfolio-service/src/portfolio_service/services/order_service.py:61`

Both have:
```python
"price": str(price) if price is not None else None,
```
The `OrderSnapshot.price` column is `nullable=False` (journal models.py:86; portfolio likely the same). MARKET orders have `price=None`.

Captured journal log: 102 `Error processing event_name=order.placed` errors all reading `null value in column "price" of relation "order_snapshots" violates not-null constraint`.

**Fix:** default to `"0"` instead of `None` when price is absent, or make the column nullable in the schema.

**Blocks:** journal integration tests; also pollutes portfolio order_snapshots → contributes to RC-3 retries failing.

---

### RC-5 — Portfolio `process_order_filled` reads wrong field names from the event payload
**File:** `portfolio-service/src/portfolio_service/services/order_service.py:95`

```python
filled_quantity = event_payload.get("filled_quantity", 0)
```
The `order.filled` payload BAS actually publishes (per `OrderFilledV1` in `order_events.py`) uses `delta_quantity` and `total_filled_quantity` — there is no `filled_quantity`. So portfolio writes `filled_quantity=0` to every snapshot, and the order never visibly transitions to FILLED.

Confirmed in log:
```
"Processed order.filled event: order_id=2bf0b157-..., filled_qty=0, avg_price=550.0, status=FILLED"
```

**Fix:** read `total_filled_quantity` (and use `delta_quantity` for incremental aggregation if needed).

**Blocks:** event_bus_validation schema tests, any test that reads filled qty from portfolio.

---

### RC-6 — BAS Paper plugin's WS reader publishes a duplicate `broker.order_update` with empty `instrument_id`
**File:** `broker-adapter-service/src/broker_adapter_service/plugins/paper/plugin.py:230-240`

The paper plugin opens its own WS to PBS and re-publishes received messages as `broker.order_update`, but uses `data.get("instrument_id", "")` — the WS payload doesn't carry one.

Counts in this run: PBS emitted 20 `broker.order_update` events; BAS received 40 (each event arriving twice). Half are rejected with the warning:
```
[FillConsumer] Missing required fields in broker.order_update event  (instrument_id="")
```

Not directly fatal — the redundant Redis publish still wins — but creates noise, doubles processing cost, and would be the actual root cause if the redundant Redis path were ever skipped (e.g. in a partial outage).

**Fix:** stop double-publishing in the paper plugin, OR include `instrument_id` in the WS message and propagate it.

---

### RC-7 (test infra) — `mock_client.sync_order` rejects every BAS response
**File:** `e2e/clients/mock_client.py:441-442`

`sync_order` requires `order_response['instrument_id']`, but the BAS Paper plugin builds `BasOrderPlaceResponse` without setting that field (`broker_adapter_service/plugins/paper/plugin.py:68`), so with `model_config = ConfigDict(exclude_none=True)` the dict has no `instrument_id`. Every test using the `place_and_sync_order` fixture logs:
```
Invalid order response format for sync: order_response must have instrument_id
```
The fixture catches and warns, so it does not directly fail tests, but it indicates the sync step never runs (and points to RC-1 from a different angle — BAS is dropping instrument_id at order placement too).

**Fix (cheap):** populate `instrument_id` on `BasOrderPlaceResponse` from the request leg in `paper/plugin.py:_place_order`. **Real fix:** RC-1.

---

### RC-8 (test infra) — `test_websocket_separation_live` hangs on un-timed `__anext__`
**File:** `e2e/tests/test_websocket_separation_live.py:62`
```python
mds_events = await mds_client.stream_events().__anext__() if hasattr(...) else []
```
With no event arriving, `__anext__()` blocks indefinitely. pytest's 120s `timeout = thread` killed it; that interrupt is what truncated the run before the last 3 tests reported.

**Fix:** wrap with `asyncio.wait_for(..., timeout=2.0)` and treat timeout as "no execution events" (which is what the test is actually trying to assert).

---

## Suggested fix order (prioritized)

1. **RC-1** (instrument_id round-trip) — unblocks ~30 tests immediately. Smallest blast radius is the single mapper file; biggest payoff.
2. **RC-3** (order.placed/order.filled ordering) — unblocks the injection test family.
3. **RC-4** (`price=None` NOT NULL violation) — quick win, two-line fix per service.
4. **RC-5** (`filled_quantity` field name) — quick win.
5. **RC-2** (publish `position.updated`) — needed for portfolio_integration.
6. **RC-7** (`BasOrderPlaceResponse.instrument_id`) — fixed implicitly by RC-1 if you also set it on the response.
7. **RC-6** (duplicate publish from WS reader) — cleanup, not a hard blocker.
8. **RC-8** (test hang) — fix to keep CI runs from being truncated.

## Where to look (ready-to-edit pointers)

- `broker-adapter-service/src/broker_adapter_service/plugins/paper/dto_to_paper_mapper.py:41,84`
- `broker-adapter-service/src/broker_adapter_service/plugins/paper/plugin.py:68-73`
- `broker-adapter-service/src/broker_adapter_service/plugins/paper/plugin.py:230-240`
- `broker-adapter-service/src/broker_adapter_service/services/order_fill_consumer.py:374-424` (add position.updated emission)
- `broker-adapter-service/src/broker_adapter_service/services/order_handler.py:316` (decide: outbox vs direct for placed)
- `journal-service/src/journal_service/services/order_service.py:61`
- `portfolio-service/src/portfolio_service/services/order_service.py:61` and `:95`
- `portfolio-service/src/portfolio_service/events/order_consumer.py:124`
- `e2e/tests/test_websocket_separation_live.py:62`

## Artifacts on disk

- pytest log: `/tmp/e2e_run/pytest.log`
- per-service logs: `/tmp/e2e_run/{bas,paper,mds,portfolio,journal}.log`
- per-test results: `/tmp/e2e_run/results.txt`
