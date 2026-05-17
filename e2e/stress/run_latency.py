"""
Latency profile harness — measures the *quiet-system* round-trip time
for a single MARKET BUY through the full pipeline.

Unlike run_stress.py, this script issues orders one at a time with a
generous sleep between them, so PBS' per-instrument execution worker
never has more than a single order to drain. The measurements
therefore reflect the inherent latency of the pipeline (not queue
depth).

Usage:
    python -m e2e.stress.run_latency --samples 50 --pause-ms 250

Output: per-sample latency in ms plus aggregate p50/p95/p99.
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
from datetime import datetime, timezone
from pathlib import Path

import httpx
import redis.asyncio as redis

# Re-use the shared bits from run_stress
from e2e.stress.run_stress import (
    INSTRUMENTS,
    StressConfig,
    mint_jwt,
    reset_account,
    percentile,
)


log = logging.getLogger("latency")


async def measure_one(
    http: httpx.AsyncClient,
    redis_client: redis.Redis,
    bas_url: str,
    broker_id: str,
    account_id: str,
    token: str,
    instrument_id: str,
    group_name: str,
) -> float | None:
    """Submit one MARKET BUY, trigger fill via quote, time it to FILLED."""
    client_order_id = f"latency_{uuid.uuid4().hex[:12]}"
    body = {
        "client_order_id": client_order_id,
        "position_type": "INTRADAY",
        "legs": [
            {
                "instrument_id": instrument_id,
                "instrument_type": "EQUITY",
                "side": "BUY",
                "qty": 1,
                "order_type": "MARKET",
                "ltp": "100.00",
            }
        ],
        "underlying_symbol": instrument_id.split(":")[1],
        "tif": "DAY",
    }

    t_start = time.monotonic_ns()
    resp = await http.post(
        f"{bas_url}/api/v1/orders/{broker_id}/{account_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Idempotency-Key": client_order_id,
        },
        json=body,
    )
    if resp.status_code != 200:
        log.warning("Submit failed: HTTP %d %s", resp.status_code, resp.text[:120])
        return None
    data = resp.json()
    first = data[0] if isinstance(data, list) and data else data
    broker_order_id = first.get("broker_order_id") or first.get("order_id")
    if not broker_order_id:
        return None

    # Trigger fill on the same instrument.
    await redis_client.xadd(
        "market.quote.v1",
        {
            "instrument_id": instrument_id,
            "ltp": "100.00",
            "sequence_number": str(int(time.time() * 1000)),
            "timestamp": str(int(time.time() * 1000)),
        },
    )

    # Wait for the FILLED event on events:order.updated.v1.
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        msgs = await redis_client.xreadgroup(
            group_name,
            "latency-consumer",
            {"events:order.updated.v1": ">"},
            count=50,
            block=200,
        )
        if not msgs:
            continue
        for _stream, entries in msgs:
            for msg_id, fields in entries:
                try:
                    env = json.loads(fields.get("event", "{}"))
                except json.JSONDecodeError:
                    await redis_client.xack(
                        "events:order.updated.v1", group_name, msg_id
                    )
                    continue
                payload = env.get("payload") or {}
                bid = payload.get("broker_order_id") or payload.get("order_id")
                status = payload.get("status")
                await redis_client.xack(
                    "events:order.updated.v1", group_name, msg_id
                )
                if bid == broker_order_id and status == "FILLED":
                    return (time.monotonic_ns() - t_start) / 1e6
    log.warning("Timed out waiting for FILLED on %s", broker_order_id)
    return None


async def run(args) -> int:
    logging.basicConfig(
        level=os.getenv("STRESS_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    cfg = StressConfig(
        bas_url=args.bas_url,
        pbs_url=args.pbs_url,
        redis_url=args.redis_url,
        account_id=args.account_id,
        user_id=args.user_id,
    )
    token = mint_jwt(cfg.user_id)
    log.info("Resetting account state")
    await reset_account(cfg, token)

    redis_client = await redis.from_url(cfg.redis_url, decode_responses=True)
    group_name = f"latency-{uuid.uuid4().hex[:8]}"
    try:
        await redis_client.xgroup_create(
            "events:order.updated.v1", group_name, id="$", mkstream=True
        )
    except redis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise

    latencies: list[float] = []
    try:
        async with httpx.AsyncClient(timeout=30.0) as http:
            for i in range(args.samples):
                instrument = INSTRUMENTS[i % len(INSTRUMENTS)]
                lat = await measure_one(
                    http,
                    redis_client,
                    cfg.bas_url,
                    cfg.broker_id,
                    cfg.account_id,
                    token,
                    instrument,
                    group_name,
                )
                if lat is not None:
                    latencies.append(lat)
                    log.info(
                        "[%d/%d] %s: %.1f ms",
                        i + 1,
                        args.samples,
                        instrument,
                        lat,
                    )
                await asyncio.sleep(args.pause_ms / 1000)
    finally:
        try:
            await redis_client.xgroup_destroy(
                "events:order.updated.v1", group_name
            )
        except Exception:
            pass
        await redis_client.close()

    if not latencies:
        log.error("No latency samples captured.")
        return 2

    summary = {
        "samples": len(latencies),
        "mean_ms": round(statistics.mean(latencies), 1),
        "p50_ms": round(percentile(latencies, 50), 1),
        "p95_ms": round(percentile(latencies, 95), 1),
        "p99_ms": round(percentile(latencies, 99), 1),
        "max_ms": round(max(latencies), 1),
        "min_ms": round(min(latencies), 1),
    }

    report = f"""# SmartTrade Latency Profile (quiet system)

**Run at:** {datetime.now(timezone.utc).isoformat()}
**Samples:** {summary["samples"]}
**Pause between samples:** {args.pause_ms}ms

End-to-end latency (POST /orders → FILLED event on events:order.updated.v1).

| metric | ms |
|---|---|
| min   | {summary["min_ms"]} |
| mean  | {summary["mean_ms"]} |
| p50   | {summary["p50_ms"]} |
| p95   | {summary["p95_ms"]} |
| p99   | {summary["p99_ms"]} |
| max   | {summary["max_ms"]} |
"""
    if args.report:
        Path(args.report).write_text(report)
        log.info("Report written to %s", args.report)
    print(report)
    return 0


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--samples", type=int, default=30)
    p.add_argument("--pause-ms", type=int, default=250)
    p.add_argument("--report", type=str, default=None)
    p.add_argument("--bas-url", default=os.getenv("BAS_URL", "http://localhost:8005"))
    p.add_argument("--pbs-url", default=os.getenv("PBS_URL", "http://localhost:8002"))
    p.add_argument("--redis-url", default=os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    p.add_argument("--account-id", default=os.getenv("ACCOUNT_ID", "TEST_E2E_LATENCY"))
    p.add_argument("--user-id", default=os.getenv("USER_ID", "00000000-0000-0000-0000-000000000001"))
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(asyncio.run(run(parse_args())))
