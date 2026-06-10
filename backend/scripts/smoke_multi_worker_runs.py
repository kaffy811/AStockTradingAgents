#!/usr/bin/env python3
"""
smoke_multi_worker_runs.py — M43 多 worker 并发分析 SSE 压测脚本

用法:
  python scripts/smoke_multi_worker_runs.py \
    --base-url http://localhost:8000 \
    --token <JWT_TOKEN> \
    --concurrency 4 \
    --runs 8 \
    --engine custom_coordinator

参数:
  --base-url       后端 base URL (default: http://localhost:8000)
  --token          JWT Bearer token（必填）
  --concurrency    并发 worker 数量 (default: 4)
  --runs           总 run 数量 (default: 8)
  --engine         custom_coordinator | langgraph | auto (default: auto，循环使用)
  --scope          analysis_scope (default: technical_only)
  --timeout        单 run SSE 超时秒数 (default: 180)

输出:
  每个 run 的详细指标 + 汇总表
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx


# ── Fixtures ──────────────────────────────────────────────────────────────────

_TEST_CASES = [
    {"market": "CN", "symbol": "000001", "analysis_scope": "technical_only",       "output_language": "zh-CN"},
    {"market": "CN", "symbol": "600519", "analysis_scope": "technical_only",       "output_language": "en-US"},
    {"market": "HK", "symbol": "00700",  "analysis_scope": "news_only",            "output_language": "zh-TW"},
    {"market": "CN", "symbol": "000001", "analysis_scope": "technical_fundamental","output_language": "zh-CN"},
]


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class RunResult:
    run_id:                  str
    engine:                  str
    scope:                   str
    output_language:         str
    status:                  str          = "pending"
    total_duration_ms:       int          = 0
    first_event_latency_ms:  int          = 0
    event_count:             int          = 0
    terminal_event:          str          = ""
    output_language_actual:  str          = ""
    workflow_engine_actual:  str          = ""
    error:                   Optional[str]= None
    event_ids:               list         = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.terminal_event == "report_ready" and self.error is None


# ── SSE parser ────────────────────────────────────────────────────────────────

def _parse_sse_block(block: str):
    block = block.strip()
    if block == ": heartbeat":  return "heartbeat", None
    if block == ": stream-end": return "stream-end", None
    for line in block.splitlines():
        if line.startswith("data:"):
            try:    return "event", json.loads(line[5:].strip())
            except: pass
    return "unknown", None


# ── Single run worker ─────────────────────────────────────────────────────────

async def run_single(
    base: str,
    headers: dict,
    case: dict,
    engine: str,
    timeout_secs: int,
    sem: asyncio.Semaphore,
    idx: int,
) -> RunResult:
    result = RunResult(
        run_id="",
        engine=engine,
        scope=case["analysis_scope"],
        output_language=case["output_language"],
    )
    async with sem:
        t0 = time.monotonic()
        try:
            payload = {**case, "engine": engine}
            async with httpx.AsyncClient(base_url=base, headers=headers, timeout=15) as c:
                r = await c.post("/api/v1/analysis/runs", json=payload)
                if r.status_code not in (200, 201):
                    result.status = "create_failed"
                    result.error  = f"HTTP {r.status_code}: {r.text[:200]}"
                    return result
                data = r.json()
                result.run_id = data["run_id"]

            print(f"  [run-{idx:02d}] created {result.run_id[:8]}… ({engine}/{case['analysis_scope']})")

            buf = ""
            first_event_seen = False
            async with httpx.AsyncClient(headers=headers, timeout=httpx.Timeout(timeout_secs)) as c:
                async with c.stream("GET", f"{base}/api/v1/analysis/runs/{result.run_id}/events") as resp:
                    async for chunk in resp.aiter_text():
                        buf += chunk
                        while "\n\n" in buf:
                            block, buf = buf.split("\n\n", 1)
                            kind, ev_data = _parse_sse_block(block)

                            if kind == "stream-end":
                                result.total_duration_ms = int((time.monotonic() - t0) * 1000)
                                result.status = "streamed"
                                break
                            elif kind == "event" and ev_data:
                                et  = ev_data.get("event", "?")
                                eid = ev_data.get("event_id")
                                result.event_count += 1
                                if eid is not None:
                                    result.event_ids.append(eid)

                                if not first_event_seen:
                                    result.first_event_latency_ms = int(
                                        (time.monotonic() - t0) * 1000
                                    )
                                    first_event_seen = True

                                if et == "report_ready":
                                    res = ev_data.get("result") or {}
                                    meta = res.get("metadata") or {}
                                    result.terminal_event         = "report_ready"
                                    result.output_language_actual = res.get("output_language", "?")
                                    result.workflow_engine_actual = meta.get("workflow_engine", "?")
                                    result.status = "completed"
                                elif et == "analysis_failed":
                                    result.terminal_event = "analysis_failed"
                                    result.error  = ev_data.get("error", "unknown")
                                    result.status = "failed"
                                elif et == "cancelled":
                                    result.terminal_event = "cancelled"
                                    result.status = "cancelled"

        except Exception as exc:
            result.status = "exception"
            result.error  = f"{type(exc).__name__}: {exc}"

        if not result.total_duration_ms:
            result.total_duration_ms = int((time.monotonic() - t0) * 1000)

        # Validate event_id monotonicity (no duplicates)
        if result.event_ids:
            seen = set()
            has_dup = any((eid in seen or seen.add(eid)) for eid in result.event_ids)
            if has_dup:
                result.error = (result.error or "") + " [WARN: duplicate event_ids]"

        icon = "✓" if result.ok else "✗"
        print(f"  [run-{idx:02d}] {icon} {result.terminal_event or result.status} "
              f"{result.total_duration_ms}ms events={result.event_count} "
              f"wfe={result.workflow_engine_actual}")
        return result


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> int:
    parser = argparse.ArgumentParser(description="Multi-worker SSE smoke test")
    parser.add_argument("--base-url",    default="http://localhost:8000")
    parser.add_argument("--token",       required=True)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--runs",        type=int, default=8)
    parser.add_argument("--engine",      default="auto",
                        choices=["auto","custom_coordinator","langgraph"])
    parser.add_argument("--scope",       default=None,
                        help="Override analysis_scope for all runs")
    parser.add_argument("--timeout",     type=int, default=180)
    args = parser.parse_args()

    headers = {"Authorization": f"Bearer {args.token}"}
    sem     = asyncio.Semaphore(args.concurrency)

    print(f"\nSmoke: {args.runs} runs  concurrency={args.concurrency}  "
          f"engine={args.engine}  base={args.base_url}")
    print("─" * 60)

    # Build run list
    tasks = []
    for i in range(args.runs):
        case   = dict(_TEST_CASES[i % len(_TEST_CASES)])
        if args.scope:
            case["analysis_scope"] = args.scope
        engine = (args.engine if args.engine != "auto"
                  else ("langgraph" if i % 2 else "custom_coordinator"))
        tasks.append(asyncio.create_task(
            run_single(args.base_url, headers, case, engine, args.timeout, sem, i)
        ))

    results: list[RunResult] = await asyncio.gather(*tasks)

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print(f"{'#':<4} {'run_id':<10} {'engine':<20} {'scope':<22} {'term':<14} "
          f"{'dur_ms':<8} {'1st_ms':<7} {'evts':<5} {'wfe':<22} {'lang':<7} {'err'}")
    for i, r in enumerate(results):
        short_id = r.run_id[:8] if r.run_id else "n/a"
        err_short = (r.error or "")[:30] if r.error else ""
        print(f"{i:<4} {short_id:<10} {r.engine:<20} {r.scope:<22} "
              f"{r.terminal_event or r.status:<14} {r.total_duration_ms:<8} "
              f"{r.first_event_latency_ms:<7} {r.event_count:<5} "
              f"{r.workflow_engine_actual:<22} {r.output_language_actual:<7} {err_short}")

    ok_count   = sum(1 for r in results if r.ok)
    fail_count = len(results) - ok_count
    avg_dur    = sum(r.total_duration_ms for r in results) / len(results)
    avg_1st    = sum(r.first_event_latency_ms for r in results if r.first_event_latency_ms > 0)
    n_1st      = sum(1 for r in results if r.first_event_latency_ms > 0)
    avg_1st    = avg_1st / n_1st if n_1st else 0

    print(f"\nTotal: {len(results)}  OK: {ok_count}  FAIL: {fail_count}")
    print(f"Avg duration: {avg_dur:.0f}ms  Avg first-event latency: {avg_1st:.0f}ms")
    print(f"First-event latency < 2000ms: "
          f"{'✓' if avg_1st < 2000 else '✗'} ({avg_1st:.0f}ms)")

    if fail_count == 0:
        print("\n✅ ALL PASS")
    else:
        print(f"\n❌ {fail_count} FAILURES")
        for r in results:
            if not r.ok:
                print(f"  run-{results.index(r):02d} {r.run_id[:8]} err={r.error}")

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
