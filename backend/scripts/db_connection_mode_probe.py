"""Probe PostgreSQL connection strategies without printing secrets.

Usage:
  python backend/scripts/db_connection_mode_probe.py --output backend/docs/artifacts/db_connection_mode_probe.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import statistics
import time
from datetime import datetime, timezone
from typing import Any

BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    index = min(len(values) - 1, max(0, int(round((pct / 100) * (len(values) - 1)))))
    return round(values[index], 2)


def _summary(latencies: list[float], timeouts: int) -> dict[str, Any]:
    return {
        "count": len(latencies),
        "timeout_count": timeouts,
        "p50_ms": _percentile(latencies, 50),
        "p95_ms": _percentile(latencies, 95),
        "p99_ms": _percentile(latencies, 99),
        "avg_ms": round(statistics.mean(latencies), 2) if latencies else None,
    }


def _phase_summary(samples: list[dict[str, float]], timeouts: int) -> dict[str, Any]:
    return {
        "total_ms": _summary([s["total_ms"] for s in samples], timeouts),
        "checkout_connect_ms": _summary([s["checkout_connect_ms"] for s in samples], timeouts),
        "query_ms": _summary([s["query_ms"] for s in samples], timeouts),
        "dns_tcp_ssl_supavisor_note": (
            "asyncpg/SQLAlchemy expose DNS/TCP/SSL/Supavisor as one connection phase; "
            "checkout_connect_ms is pool checkout plus connection establishment."
        ),
    }


async def _select_one(engine, timeout: float) -> dict[str, float]:
    started = time.perf_counter()
    async with asyncio.timeout(timeout):
        connect_started = time.perf_counter()
        async with engine.connect() as conn:
            connected_at = time.perf_counter()
            await conn.execute(text("SELECT 1"))
            finished_at = time.perf_counter()
    return {
        "total_ms": (finished_at - started) * 1000,
        "checkout_connect_ms": (connected_at - connect_started) * 1000,
        "query_ms": (finished_at - connected_at) * 1000,
    }


async def _run_group_inner(name: str, database_url: str, *, poolclass, pool_size: int | None = None, max_overflow: int | None = None) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "poolclass": poolclass,
        "connect_args": {"statement_cache_size": 0, "command_timeout": 5, "timeout": 5},
        "pool_pre_ping": True,
    }
    if poolclass is AsyncAdaptedQueuePool:
        kwargs.update({"pool_size": pool_size or 2, "max_overflow": max_overflow or 2, "pool_timeout": 5, "pool_recycle": 300})
    engine = create_async_engine(database_url, **kwargs)
    result: dict[str, Any] = {"name": name, "pool_class": poolclass.__name__}
    try:
        serial: list[dict[str, float]] = []
        serial_timeouts = 0
        for _ in range(20):
            try:
                serial.append(await _select_one(engine, 2))
            except Exception:
                serial_timeouts += 1
        result["serial_select_1"] = _phase_summary(serial, serial_timeouts)

        concurrent_results = await asyncio.gather(
            *[_select_one(engine, 2) for _ in range(20)],
            return_exceptions=True,
        )
        result["concurrent_select_1"] = _phase_summary(
            [item for item in concurrent_results if isinstance(item, dict)],
            sum(1 for item in concurrent_results if isinstance(item, TimeoutError)),
        )

        tx: list[dict[str, float]] = []
        tx_timeouts = 0
        for _ in range(100):
            try:
                tx.append(await _select_one(engine, 2))
            except Exception:
                tx_timeouts += 1
        result["short_transactions_100"] = _phase_summary(tx, tx_timeouts)

        task = asyncio.create_task(_select_one(engine, 8))
        await asyncio.sleep(0.001)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            result["simulated_cancellation"] = "cancelled_cleanly"
        result["pool_checked_out_baseline"] = getattr(engine.sync_engine.pool, "checkedout", lambda: None)()
        result["pool_overflow_baseline"] = getattr(engine.sync_engine.pool, "overflow", lambda: None)()
    finally:
        await engine.dispose()
    return result


async def _run_group(name: str, database_url: str, *, poolclass, pool_size: int | None = None, max_overflow: int | None = None) -> dict[str, Any]:
    try:
        return await asyncio.wait_for(
            _run_group_inner(name, database_url, poolclass=poolclass, pool_size=pool_size, max_overflow=max_overflow),
            timeout=60,
        )
    except asyncio.TimeoutError:
        return {
            "name": name,
            "pool_class": poolclass.__name__,
            "status": "incomplete_timeout",
            "group_timeout_seconds": 60,
        }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        from app.core.config import settings
        database_url = settings.database_url
    if not database_url:
        raise SystemExit("DATABASE_URL is required")
    url = make_url(database_url)
    groups = [
        ("transaction_pooler_current_queue", AsyncAdaptedQueuePool, 5, 10),
        ("transaction_pooler_null_pool", NullPool, None, None),
        ("transaction_pooler_small_queue", AsyncAdaptedQueuePool, 2, 2),
    ]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target": {
            "host_class": "supabase_pooler" if "pooler.supabase.com" in (url.host or "") else "database_host",
            "port": url.port,
            "driver": url.drivername,
        },
        "groups": [],
    }
    for name, poolclass, pool_size, max_overflow in groups:
        payload["groups"].append(await _run_group(name, database_url, poolclass=poolclass, pool_size=pool_size, max_overflow=max_overflow))
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)


if __name__ == "__main__":
    asyncio.run(main())
