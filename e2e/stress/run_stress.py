"""
Stress + volume harness for the BAS → PBS → Redis event chain.

NOT a pytest. Pytest's per-test fixture setup adds setup overhead that
would dominate any measurement of the production path. This script is
deliberately a single asyncio program that:

  1. Starts with a clean account (one-shot cleanup against PBS/BAS).
  2. Subscribes to Redis Streams (events:order.updated.v1) before
     issuing any orders, so no FILLED event can be missed.
  3. Drives a burst of MARKET BUYs at the target concurrency, then
     pushes a single quote per instrument to trigger the fills.
  4. Captures end-to-end latency (HTTP submit → FILLED on Redis) for
     every order and reports p50/p95/p99 + throughput + error counts.

Usage:
    python -m e2e.stress.run_stress --orders 200 --concurrency 20
    python -m e2e.stress.run_stress --orders 1000 --concurrency 50 --report /tmp/stress.md

The script exits non-zero if the success rate < 95% or any order fails
to reach FILLED within --order-timeout seconds. This makes it suitable
for both interactive debugging and CI gating.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import statistics
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

import httpx
import redis.asyncio as redis
from jose import jwt as jose_jwt


log = logging.getLogger("stress")


# ──────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────


@dataclass
class StressConfig:
    bas_url: str = "http://localhost:8005"
    pbs_url: str = "http://localhost:8002"
    redis_url: str = "redis://localhost:6379/0"
    broker_id: str = "fyers"
    # Account id MUST contain the literal substring "TEST_E2E" so BAS'
    # trading_account_service auto-activates it (see line 67 of that
    # service). Without auto-activation the account is created inactive
    # and every order placement returns 409.
    account_id: str = "TEST_E2E_STRESS"
    user_id: str = "00000000-0000-0000-0000-000000000001"
    orders: int = 100
    concurrency: int = 10
    qty_per_order: int = 1
    order_timeout: float = 20.0
    overall_timeout: float = 300.0
    report_path: Optional[str] = None
    success_threshold_pct: float = 95.0


# ──────────────────────────────────────────────────────────────────────────
# Auth
# ──────────────────────────────────────────────────────────────────────────


def mint_jwt(user_id: str) -> str:
    """Mint a JWT that matches the smarttrade-common verifier.

    Mirrors the e2e/conftest auth_token fixture so the stress run uses
    exactly the same credential shape as the integration tests.
    """
    secret = os.getenv("JWT_SECRET_KEY")
    if not secret:
        raise RuntimeError(
            "JWT_SECRET_KEY env var required. Set it to the same value "
            "as in docker-compose.e2e.yml (default: 247ede858cd1b034a2c"
            "8594452088c660b5a63b8cc89944ad3fe802ac7f2ae30 for local)."
        )
    # datetime.utcnow() returns a NAIVE datetime; calling .timestamp() on
    # a naive datetime interprets it as local time. On a host in IST
    # (+5:30) that flips iat 5.5h into the past and a 1h-expiry token is
    # then 4.5h in the past relative to real wall clock — the validator
    # correctly rejects it. The conftest's session-scope auth_token
    # fixture papers over this by using a 24h expiry; here we use UTC-
    # aware datetimes so short-lived tokens work correctly too.
    now_unix = int(time.time())
    payload = {
        "sub": user_id,
        "roles": ["user"],
        "type": "access",
        "iat": now_unix,
        "exp": now_unix + 3600,
        "iss": "auth-service",
        "aud": "smarttrade-services",
    }
    return jose_jwt.encode(payload, secret, algorithm="HS256")


# ──────────────────────────────────────────────────────────────────────────
# Account + instrument setup
# ──────────────────────────────────────────────────────────────────────────


# A small basket of equities matching e2e/fixtures/test_instruments_data.
# We round-robin orders across this list to spread the load across PBS'
# per-instrument execution worker queues; otherwise every order on one
# instrument serializes through a single worker and we measure that, not
# the system.
INSTRUMENTS = [
    "NSE:SBIN:EQ",
    "NSE:INFY:EQ",
    "NSE:HDFC:EQ",
    "NSE:ICICIBANK:EQ",
    "NSE:TCS:EQ",
    "NSE:RELIANCE:EQ",
    "NSE:WIPRO:EQ",
    "NSE:LT:EQ",
    "NSE:AXIS:EQ",
    "NSE:KOTAK:EQ",
]


async def reset_account(cfg: StressConfig, token: str) -> None:
    """One-shot cleanup of the stress account state before the run."""
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=15.0) as http:
        # Delete any prior trading account in BAS (idempotent — 404 is fine).
        try:
            await http.delete(
                f"{cfg.bas_url}/api/v1/trading_account/{cfg.broker_id}/{cfg.account_id}",
                headers=headers,
            )
        except Exception:
            pass

        # Re-create as a PAPER account so PBS routes the orders. The
        # BAS endpoint requires account_name + base_currency in addition
        # to id/type; missing fields fail Pydantic validation silently
        # (the account never gets created and downstream order POSTs 404).
        resp = await http.post(
            f"{cfg.bas_url}/api/v1/trading_account/{cfg.broker_id}",
            headers=headers,
            json={
                "account_id": cfg.account_id,
                "account_name": cfg.account_id,
                "account_type": "PAPER",
                "base_currency": "INR",
            },
        )
        if resp.status_code not in (200, 201, 409):
            raise RuntimeError(
                f"Failed to create trading account: HTTP {resp.status_code} {resp.text[:200]}"
            )

        # Clear PBS execution state, positions, price cache, account
        # balance reserve. Best-effort — 404s are fine.
        for path in (
            f"/api/v1/cleanup/execution_state/{cfg.broker_id}/{cfg.account_id}",
            f"/api/v1/cleanup/positions/{cfg.broker_id}/{cfg.account_id}",
            "/api/v1/cleanup/price_cache",
            f"/api/v1/cleanup/account/{cfg.broker_id}/{cfg.account_id}",
        ):
            try:
                await http.delete(f"{cfg.pbs_url}{path}", headers=headers)
            except Exception:
                pass
    log.info("Account reset complete")


# ──────────────────────────────────────────────────────────────────────────
# Redis event collection
# ──────────────────────────────────────────────────────────────────────────


@dataclass
class OrderRecord:
    """One slot per submitted order."""

    request_idx: int
    instrument_id: str
    submit_started_at_ns: int = 0
    submit_completed_at_ns: int = 0
    broker_order_id: Optional[str] = None
    accepted_at_ns: Optional[int] = None
    filled_at_ns: Optional[int] = None
    submit_error: Optional[str] = None

    @property
    def submit_latency_ms(self) -> Optional[float]:
        if self.submit_started_at_ns and self.submit_completed_at_ns:
            return (self.submit_completed_at_ns - self.submit_started_at_ns) / 1e6
        return None

    @property
    def total_latency_ms(self) -> Optional[float]:
        if self.submit_started_at_ns and self.filled_at_ns:
            return (self.filled_at_ns - self.submit_started_at_ns) / 1e6
        return None


class FillCollector:
    """Tail events:order.updated.v1 and stamp the fill time on each order."""

    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.client: Optional[redis.Redis] = None
        self.group_name = f"stress-{uuid.uuid4().hex[:8]}"
        self.consumer_name = "consumer-1"
        self.streams = ["events:order.updated.v1"]
        self._stop = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        # broker_order_id → OrderRecord
        self.records: dict[str, OrderRecord] = {}

    async def start(self) -> None:
        self.client = await redis.from_url(self.redis_url, decode_responses=True)
        for stream in self.streams:
            try:
                # id="$" → only events that arrive AFTER subscription. Old
                # events from previous test runs must not leak in.
                await self.client.xgroup_create(
                    stream, self.group_name, id="$", mkstream=True
                )
            except redis.ResponseError as e:
                if "BUSYGROUP" not in str(e):
                    raise
        self._task = asyncio.create_task(self._reader())

    async def _reader(self) -> None:
        try:
            while not self._stop.is_set():
                msgs = await self.client.xreadgroup(
                    self.group_name,
                    self.consumer_name,
                    {s: ">" for s in self.streams},
                    count=200,
                    block=200,
                )
                if not msgs:
                    continue
                now_ns = time.monotonic_ns()
                for stream, entries in msgs:
                    for msg_id, fields in entries:
                        try:
                            envelope = json.loads(fields.get("event", "{}"))
                        except json.JSONDecodeError:
                            await self.client.xack(stream, self.group_name, msg_id)
                            continue
                        payload = envelope.get("payload") or {}
                        bid = payload.get("broker_order_id") or payload.get("order_id")
                        status = payload.get("status")
                        if bid and bid in self.records:
                            rec = self.records[bid]
                            if status == "ACCEPTED" and rec.accepted_at_ns is None:
                                rec.accepted_at_ns = now_ns
                            elif status == "FILLED" and rec.filled_at_ns is None:
                                rec.filled_at_ns = now_ns
                        await self.client.xack(stream, self.group_name, msg_id)
        except asyncio.CancelledError:
            return

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        if self.client:
            for stream in self.streams:
                try:
                    await self.client.xgroup_destroy(stream, self.group_name)
                except Exception:
                    pass
            await self.client.close()


# ──────────────────────────────────────────────────────────────────────────
# Order driver
# ──────────────────────────────────────────────────────────────────────────


async def submit_order(
    http: httpx.AsyncClient,
    cfg: StressConfig,
    token: str,
    rec: OrderRecord,
) -> None:
    """POST a single MARKET BUY and capture submit timing + broker_order_id."""
    body = {
        "client_order_id": f"stress_{rec.request_idx}_{uuid.uuid4().hex[:8]}",
        "position_type": "INTRADAY",
        "legs": [
            {
                "instrument_id": rec.instrument_id,
                "instrument_type": "EQUITY",
                "side": "BUY",
                "qty": cfg.qty_per_order,
                "order_type": "MARKET",
                "ltp": "100.00",
            }
        ],
        "underlying_symbol": rec.instrument_id.split(":")[1],
        "tif": "DAY",
    }
    rec.submit_started_at_ns = time.monotonic_ns()
    try:
        resp = await http.post(
            f"{cfg.bas_url}/api/v1/orders/{cfg.broker_id}/{cfg.account_id}",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Idempotency-Key": body["client_order_id"],
            },
            json=body,
        )
        rec.submit_completed_at_ns = time.monotonic_ns()
        if resp.status_code != 200:
            rec.submit_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            return
        data = resp.json()
        # Response is a list of leg responses; use the first one.
        first = data[0] if isinstance(data, list) and data else data
        rec.broker_order_id = first.get("broker_order_id") or first.get("order_id")
    except Exception as e:
        rec.submit_completed_at_ns = time.monotonic_ns()
        rec.submit_error = repr(e)


async def trigger_fills(cfg: StressConfig, instruments_used: set[str]) -> None:
    """Publish one quote per instrument so PBS' on_price_update enqueues
    a fill for every open MARKET order. One quote per instrument is
    enough because PBS' worker fills ALL open orders on that instrument
    in a single sweep.
    """
    client = await redis.from_url(cfg.redis_url, decode_responses=True)
    try:
        base_seq = int(time.time() * 1000)
        for i, instrument in enumerate(sorted(instruments_used)):
            await client.xadd(
                "market.quote.v1",
                {
                    "instrument_id": instrument,
                    "ltp": "100.00",
                    "sequence_number": str(base_seq + i),
                    "timestamp": str(int(time.time() * 1000)),
                },
            )
    finally:
        await client.close()


# ──────────────────────────────────────────────────────────────────────────
# Reporting
# ──────────────────────────────────────────────────────────────────────────


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    k = (len(sorted_values) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


def summarize(cfg: StressConfig, records: list[OrderRecord], wall_seconds: float) -> dict:
    total = len(records)
    submit_errors = [r for r in records if r.submit_error]
    submitted_ok = [r for r in records if not r.submit_error and r.broker_order_id]
    filled = [r for r in submitted_ok if r.filled_at_ns is not None]

    submit_latencies = [r.submit_latency_ms for r in submitted_ok if r.submit_latency_ms is not None]
    total_latencies = [r.total_latency_ms for r in filled if r.total_latency_ms is not None]

    return {
        "config": {
            "orders": cfg.orders,
            "concurrency": cfg.concurrency,
            "qty_per_order": cfg.qty_per_order,
        },
        "totals": {
            "submitted": total,
            "submit_errors": len(submit_errors),
            "submit_ok": len(submitted_ok),
            "filled": len(filled),
            "fill_success_pct": (100.0 * len(filled) / total) if total else 0.0,
            "wall_seconds": round(wall_seconds, 3),
            "throughput_orders_per_sec": round(len(filled) / wall_seconds, 2) if wall_seconds > 0 else 0.0,
        },
        "submit_latency_ms": {
            "n": len(submit_latencies),
            "p50": round(percentile(submit_latencies, 50), 1),
            "p95": round(percentile(submit_latencies, 95), 1),
            "p99": round(percentile(submit_latencies, 99), 1),
            "max": round(max(submit_latencies), 1) if submit_latencies else 0.0,
            "mean": round(statistics.mean(submit_latencies), 1) if submit_latencies else 0.0,
        },
        "submit_to_filled_latency_ms": {
            "n": len(total_latencies),
            "p50": round(percentile(total_latencies, 50), 1),
            "p95": round(percentile(total_latencies, 95), 1),
            "p99": round(percentile(total_latencies, 99), 1),
            "max": round(max(total_latencies), 1) if total_latencies else 0.0,
            "mean": round(statistics.mean(total_latencies), 1) if total_latencies else 0.0,
        },
        "error_samples": [r.submit_error for r in submit_errors[:5]],
        "missing_fill_count": len(submitted_ok) - len(filled),
    }


def render_markdown(summary: dict) -> str:
    cfg = summary["config"]
    tot = summary["totals"]
    sl = summary["submit_latency_ms"]
    el = summary["submit_to_filled_latency_ms"]
    return f"""# SmartTrade Stress / Volume Report

**Run at:** {datetime.now(timezone.utc).isoformat()}

## Configuration
- Orders attempted: **{cfg["orders"]}**
- Concurrency: **{cfg["concurrency"]}**
- Qty per order: **{cfg["qty_per_order"]}**

## Outcome
- Submitted: **{tot["submitted"]}**
- Submit errors: **{tot["submit_errors"]}**
- Submit OK: **{tot["submit_ok"]}**
- Reached FILLED: **{tot["filled"]}**
- Fill success rate: **{tot["fill_success_pct"]:.1f}%**
- Wall time: **{tot["wall_seconds"]}s**
- Throughput: **{tot["throughput_orders_per_sec"]} orders/sec** (filled / wall)
- Orders submitted OK but never filled: **{summary["missing_fill_count"]}**

## Latency (submit-only, BAS POST round-trip, ms)
| metric | value |
|---|---|
| n     | {sl["n"]} |
| mean  | {sl["mean"]} |
| p50   | {sl["p50"]} |
| p95   | {sl["p95"]} |
| p99   | {sl["p99"]} |
| max   | {sl["max"]} |

## Latency (submit → FILLED on Redis, ms)
End-to-end through BAS → PBS → execution worker → BAS WS handler → outbox → poller → Redis Streams.

| metric | value |
|---|---|
| n     | {el["n"]} |
| mean  | {el["mean"]} |
| p50   | {el["p50"]} |
| p95   | {el["p95"]} |
| p99   | {el["p99"]} |
| max   | {el["max"]} |

## Error samples (first 5)
{chr(10).join(f"- {e}" for e in summary["error_samples"]) if summary["error_samples"] else "_None_"}
"""


# ──────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────


async def run(cfg: StressConfig) -> int:
    logging.basicConfig(
        level=os.getenv("STRESS_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    token = mint_jwt(cfg.user_id)
    log.info("Resetting account state")
    await reset_account(cfg, token)

    collector = FillCollector(cfg.redis_url)
    log.info("Starting Redis fill collector (consumer group %s)", collector.group_name)
    await collector.start()

    # Pre-allocate records keyed by request index. We don't know the
    # broker_order_id yet (assigned by PBS), so we map by index now and
    # re-key by broker_order_id after submit returns.
    records = [
        OrderRecord(
            request_idx=i,
            instrument_id=INSTRUMENTS[i % len(INSTRUMENTS)],
        )
        for i in range(cfg.orders)
    ]
    instruments_used = {r.instrument_id for r in records}

    # Concurrent submission, bounded by --concurrency.
    semaphore = asyncio.Semaphore(cfg.concurrency)
    wall_start = time.monotonic()
    async with httpx.AsyncClient(timeout=15.0) as http:
        async def _submit(r: OrderRecord) -> None:
            async with semaphore:
                await submit_order(http, cfg, token, r)
                if r.broker_order_id:
                    collector.records[r.broker_order_id] = r

        log.info("Submitting %d orders @ concurrency=%d", cfg.orders, cfg.concurrency)
        await asyncio.gather(*(_submit(r) for r in records), return_exceptions=True)

    log.info(
        "Submit phase complete in %.2fs (%d submit errors)",
        time.monotonic() - wall_start,
        sum(1 for r in records if r.submit_error),
    )

    # Trigger fills now that every order is in PBS' open-order pool.
    log.info("Publishing trigger quotes on %d instruments", len(instruments_used))
    await trigger_fills(cfg, instruments_used)

    # Wait until every submitted-OK order reaches FILLED or the timeout
    # expires. We poll the collector's records dict every 100ms.
    deadline = time.monotonic() + cfg.overall_timeout
    while time.monotonic() < deadline:
        outstanding = [
            r for r in records
            if not r.submit_error and r.broker_order_id and r.filled_at_ns is None
        ]
        if not outstanding:
            break
        await asyncio.sleep(0.1)

    wall_seconds = time.monotonic() - wall_start

    await collector.stop()

    summary = summarize(cfg, records, wall_seconds)
    log.info(
        "Done: %d filled / %d submitted in %.2fs (%.1f%% success)",
        summary["totals"]["filled"],
        summary["totals"]["submitted"],
        wall_seconds,
        summary["totals"]["fill_success_pct"],
    )

    report_md = render_markdown(summary)
    if cfg.report_path:
        Path(cfg.report_path).write_text(report_md)
        log.info("Report written to %s", cfg.report_path)
    print(report_md)

    return (
        0
        if summary["totals"]["fill_success_pct"] >= cfg.success_threshold_pct
        else 2
    )


def parse_args() -> StressConfig:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--orders", type=int, default=100)
    p.add_argument("--concurrency", type=int, default=10)
    p.add_argument("--qty", type=int, default=1)
    p.add_argument("--order-timeout", type=float, default=20.0)
    p.add_argument("--overall-timeout", type=float, default=300.0)
    p.add_argument("--report", type=str, default=None,
                   help="Write markdown report to this path")
    p.add_argument("--success-threshold-pct", type=float, default=95.0)
    p.add_argument("--bas-url", default=os.getenv("BAS_URL", "http://localhost:8005"))
    p.add_argument("--pbs-url", default=os.getenv("PBS_URL", "http://localhost:8002"))
    p.add_argument("--redis-url", default=os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    p.add_argument("--account-id", default=os.getenv("ACCOUNT_ID", "TEST_E2E_STRESS"))
    p.add_argument("--user-id", default=os.getenv("USER_ID", "00000000-0000-0000-0000-000000000001"))
    args = p.parse_args()
    return StressConfig(
        bas_url=args.bas_url,
        pbs_url=args.pbs_url,
        redis_url=args.redis_url,
        account_id=args.account_id,
        user_id=args.user_id,
        orders=args.orders,
        concurrency=args.concurrency,
        qty_per_order=args.qty,
        order_timeout=args.order_timeout,
        overall_timeout=args.overall_timeout,
        report_path=args.report,
        success_threshold_pct=args.success_threshold_pct,
    )


if __name__ == "__main__":
    cfg = parse_args()
    sys.exit(asyncio.run(run(cfg)))
