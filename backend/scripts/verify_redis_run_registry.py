#!/usr/bin/env python3
"""
verify_redis_run_registry.py — RedisAnalysisRunRegistry 集成验证脚本（M40-b）。

测试 10 个场景：
  T1  create_run           → 返回 AnalysisRunRef，Redis Hash 已写入
  T2  get_run_snapshot     → Hash 读回，字段一致
  T3  push_event (dict)    → List 追加，channel pub 已入队
  T4  get_events_after     → after_event_id=None 返回全部；after_event_id=1 返回 eid>1
  T5  push_event (None)    → _close sentinel 发布，List 不新增
  T6  update_status        → status/finished_at 写入 Hash
  T7  request_cancel       → status=cancelled，cancelled 事件入 List，_close pub
  T8  is_cancel_requested  → 返回 True
  T9  subscribe_events     → 实时接收两个事件后收到 None sentinel
  T10 TTL                  → 所有键有 TTL > 0

用法（需要本地 Redis 在 redis://localhost:6379 可达）：
  cd backend
  uv run python scripts/verify_redis_run_registry.py

  # 或指定 Redis URL：
  REDIS_URL=redis://localhost:6379 uv run python scripts/verify_redis_run_registry.py

退出码：
  0 — 全部 PASS
  1 — 至少一个 FAIL
"""

from __future__ import annotations

import asyncio
import os
import sys
import traceback
from datetime import datetime, timezone

# ── 确保 app/ 在 sys.path ─────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from redis.asyncio import from_url

from app.services.redis_run_registry import RedisAnalysisRunRegistry

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

# ── PASS / FAIL helpers ───────────────────────────────────────────────────────

_results: list[tuple[str, bool, str]] = []


def _pass(name: str, detail: str = "") -> None:
    _results.append((name, True, detail))
    print(f"  PASS  {name}" + (f"  — {detail}" if detail else ""))


def _fail(name: str, reason: str) -> None:
    _results.append((name, False, reason))
    print(f"  FAIL  {name}  — {reason}")


# ── Individual tests ──────────────────────────────────────────────────────────

async def t1_create_run(reg: RedisAnalysisRunRegistry) -> str:
    """T1: create_run returns AnalysisRunRef and writes Hash to Redis."""
    ref = await reg.create_run(
        user_id="user-test-001",
        market="CN",
        symbol="000001",
        analysis_scope="comprehensive",
        workflow_engine="custom_coordinator",
        output_language="zh-CN",
    )
    # Verify raw hash exists
    raw = await reg._redis.hgetall(reg._run_key(ref.run_id))
    if not raw:
        _fail("T1_create_run", "Redis Hash is empty after create_run")
    elif raw.get("status") != "queued":
        _fail("T1_create_run", f"Expected status=queued, got {raw.get('status')!r}")
    elif raw.get("user_id") != "user-test-001":
        _fail("T1_create_run", "user_id mismatch in Redis")
    else:
        _pass("T1_create_run", f"run_id={ref.run_id[:8]}")
    return ref.run_id


async def t2_get_run_snapshot(reg: RedisAnalysisRunRegistry, run_id: str) -> None:
    """T2: get_run_snapshot reads back correctly."""
    snap = await reg.get_run_snapshot(run_id)
    if snap is None:
        _fail("T2_get_run_snapshot", "snapshot is None")
    elif snap.status != "queued":
        _fail("T2_get_run_snapshot", f"status={snap.status!r}")
    elif snap.market != "CN":
        _fail("T2_get_run_snapshot", f"market={snap.market!r}")
    elif snap.is_terminal():
        _fail("T2_get_run_snapshot", "is_terminal() returned True for queued run")
    else:
        _pass("T2_get_run_snapshot", f"status={snap.status}, market={snap.market}")


async def t3_push_event(reg: RedisAnalysisRunRegistry, run_id: str) -> None:
    """T3: push_event(dict) appends to List and publishes to channel."""
    # Push 2 events
    await reg.push_event(run_id, {"event": "analysis_started", "progress": 10})
    await reg.push_event(run_id, {"event": "agent_started", "agent": "technical", "progress": 20})

    # Check List length
    length = await reg._redis.llen(reg._events_key(run_id))
    if length != 2:
        _fail("T3_push_event", f"Expected 2 events in List, got {length}")
    else:
        _pass("T3_push_event", f"List has {length} events")


async def t4_get_events_after(reg: RedisAnalysisRunRegistry, run_id: str) -> None:
    """T4: get_events_after returns correct subsets."""
    # All events
    all_events = await reg.get_events_after(run_id, None)
    if len(all_events) != 2:
        _fail("T4_get_events_after(all)", f"Expected 2, got {len(all_events)}")
    else:
        _pass("T4_get_events_after(all)", f"{len(all_events)} events")

    # after event_id=1 → only event with eid=2
    after_1 = await reg.get_events_after(run_id, 1)
    if len(after_1) != 1:
        _fail("T4_get_events_after(after=1)", f"Expected 1, got {len(after_1)}")
    elif after_1[0].get("event_id") != 2:
        _fail("T4_get_events_after(after=1)", f"Expected eid=2, got {after_1[0].get('event_id')}")
    else:
        _pass("T4_get_events_after(after=1)", f"eid={after_1[0].get('event_id')}")

    # after event_id=999 → empty
    after_999 = await reg.get_events_after(run_id, 999)
    if len(after_999) != 0:
        _fail("T4_get_events_after(after=999)", f"Expected 0, got {len(after_999)}")
    else:
        _pass("T4_get_events_after(after=999)", "empty as expected")


async def t5_push_none_sentinel(reg: RedisAnalysisRunRegistry, run_id: str) -> None:
    """T5: push_event(None) publishes _close signal but does NOT append to List."""
    before_len = await reg._redis.llen(reg._events_key(run_id))
    await reg.push_event(run_id, None)
    after_len = await reg._redis.llen(reg._events_key(run_id))

    if after_len != before_len:
        _fail("T5_push_none_sentinel", f"List grew from {before_len} to {after_len} — sentinel should not be stored")
    else:
        _pass("T5_push_none_sentinel", f"List unchanged at {after_len}, close-signal published only")


async def t6_update_status(reg: RedisAnalysisRunRegistry, run_id: str) -> None:
    """T6: update_status writes status and finished_at for terminal states."""
    await reg.update_status(run_id, "running")
    snap = await reg.get_run_snapshot(run_id)
    if snap is None or snap.status != "running":
        _fail("T6_update_status(running)", f"status={snap.status if snap else None!r}")
    else:
        _pass("T6_update_status(running)", "status=running")

    # completed with result
    await reg.update_status(run_id, "completed", result={"report": "ok"})
    snap2 = await reg.get_run_snapshot(run_id)
    if snap2 is None:
        _fail("T6_update_status(completed)", "snapshot None")
    elif snap2.status != "completed":
        _fail("T6_update_status(completed)", f"status={snap2.status!r}")
    elif snap2.finished_at is None:
        _fail("T6_update_status(completed)", "finished_at is None")
    elif snap2.result != {"report": "ok"}:
        _fail("T6_update_status(completed)", f"result={snap2.result!r}")
    else:
        _pass("T6_update_status(completed)", f"status=completed, finished_at set, result OK")


async def t7_request_cancel(reg: RedisAnalysisRunRegistry) -> str:
    """T7: request_cancel sets status=cancelled and publishes events.
    Uses a fresh run so it's not already terminal.
    """
    ref = await reg.create_run(
        user_id="user-test-cancel",
        market="HK",
        symbol="00700",
        analysis_scope="technical_only",
        workflow_engine="custom_coordinator",
        output_language="en-US",
    )
    await reg.request_cancel(ref.run_id)
    snap = await reg.get_run_snapshot(ref.run_id)
    if snap is None:
        _fail("T7_request_cancel", "snapshot None after cancel")
    elif snap.status != "cancelled":
        _fail("T7_request_cancel", f"status={snap.status!r}, expected cancelled")
    elif snap.finished_at is None:
        _fail("T7_request_cancel", "finished_at is None")
    else:
        # Check cancelled event in List
        events = await reg.get_events_after(ref.run_id, None)
        cancel_events = [e for e in events if e.get("event") == "cancelled"]
        if not cancel_events:
            _fail("T7_request_cancel", "No 'cancelled' event in List")
        else:
            _pass("T7_request_cancel", f"status=cancelled, {len(cancel_events)} cancel event(s) in List")

    return ref.run_id


async def t8_is_cancel_requested(reg: RedisAnalysisRunRegistry, cancelled_run_id: str) -> None:
    """T8: is_cancel_requested returns True for cancelled run."""
    result = await reg.is_cancel_requested(cancelled_run_id)
    if not result:
        _fail("T8_is_cancel_requested", f"Expected True, got {result!r}")
    else:
        _pass("T8_is_cancel_requested", "returns True for cancelled run")


async def t9_subscribe_events(reg: RedisAnalysisRunRegistry) -> None:
    """T9: subscribe_events streams live events and then yields None on close."""
    ref = await reg.create_run(
        user_id="user-test-sub",
        market="CN",
        symbol="600519",
        analysis_scope="news_only",
        workflow_engine="custom_coordinator",
        output_language="zh-CN",
    )

    received: list[dict] = []

    async def _producer() -> None:
        # Wait a bit so subscriber is ready, then push events and close
        await asyncio.sleep(0.05)
        await reg.push_event(ref.run_id, {"event": "analysis_started", "progress": 0})
        await asyncio.sleep(0.05)
        await reg.push_event(ref.run_id, {"event": "report_ready", "progress": 100})
        await asyncio.sleep(0.05)
        await reg.push_event(ref.run_id, None)  # close signal

    async def _consumer() -> None:
        async for event in reg.subscribe_events(ref.run_id):
            if event is None:
                received.append({"event": "_sentinel"})
                return
            received.append(event)

    await asyncio.gather(
        asyncio.create_task(_producer()),
        asyncio.create_task(_consumer()),
    )

    sentinels = [e for e in received if e.get("event") == "_sentinel"]
    real_events = [e for e in received if e.get("event") != "_sentinel"]

    if len(real_events) < 2:
        _fail("T9_subscribe_events", f"Expected ≥2 real events, got {len(real_events)}: {real_events}")
    elif not sentinels:
        _fail("T9_subscribe_events", "No None sentinel received — generator did not close cleanly")
    else:
        _pass("T9_subscribe_events", f"{len(real_events)} events + sentinel received")


async def t10_ttl(reg: RedisAnalysisRunRegistry, run_id: str) -> None:
    """T10: all keys for run_id have positive TTL."""
    keys = [
        reg._run_key(run_id),
        reg._events_key(run_id),
        reg._eid_key(run_id),
    ]
    all_ok = True
    for key in keys:
        ttl = await reg._redis.ttl(key)
        if ttl <= 0:
            _fail("T10_ttl", f"Key {key!r} has TTL={ttl} (≤0)")
            all_ok = False
    if all_ok:
        _pass("T10_ttl", f"All {len(keys)} keys have positive TTL (≤{reg._ttl}s)")


# ── Main runner ───────────────────────────────────────────────────────────────

async def main() -> int:
    print(f"\nRedisAnalysisRunRegistry Verification — M40-b")
    print(f"Redis URL: {REDIS_URL}")
    print("=" * 60)

    # Connect to Redis
    try:
        redis = from_url(REDIS_URL, decode_responses=True)
        await redis.ping()
        print(f"Redis connection: OK\n")
    except Exception as exc:
        print(f"FATAL: Cannot connect to Redis at {REDIS_URL!r}: {exc}")
        return 1

    reg = RedisAnalysisRunRegistry(redis=redis, ttl_seconds=3600, event_maxlen=50, env="test")

    try:
        # T1 + T2 — create and read
        run_id = await t1_create_run(reg)
        await t2_get_run_snapshot(reg, run_id)

        # T3 + T4 — push events and replay
        await t3_push_event(reg, run_id)
        await t4_get_events_after(reg, run_id)

        # T5 — close-signal sentinel
        await t5_push_none_sentinel(reg, run_id)

        # T6 — update status
        await t6_update_status(reg, run_id)

        # T7 + T8 — cancel
        cancelled_run_id = await t7_request_cancel(reg)
        await t8_is_cancel_requested(reg, cancelled_run_id)

        # T9 — live subscribe
        await t9_subscribe_events(reg)

        # T10 — TTL (use a fresh run that still has active keys)
        ref2 = await reg.create_run(
            user_id="user-ttl-check", market="CN", symbol="000001",
            analysis_scope="technical_only", workflow_engine="custom_coordinator",
            output_language="zh-CN",
        )
        await reg.push_event(ref2.run_id, {"event": "analysis_started", "progress": 0})
        await t10_ttl(reg, ref2.run_id)

    except Exception as exc:
        print(f"\nUNEXPECTED ERROR: {exc}")
        traceback.print_exc()
        return 1
    finally:
        await redis.aclose()

    # ── Summary ───────────────────────────────────────────────────────────────
    total  = len(_results)
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = total - passed

    print("\n" + "=" * 60)
    print(f"Results: {passed}/{total} PASS  |  {failed} FAIL")
    if failed:
        print("\nFailed tests:")
        for name, ok, detail in _results:
            if not ok:
                print(f"  ✗ {name}: {detail}")
    else:
        print("\nAll tests passed.")
    print()

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
