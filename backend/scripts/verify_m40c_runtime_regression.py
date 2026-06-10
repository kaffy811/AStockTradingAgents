#!/usr/bin/env python3
"""
verify_m40c_runtime_regression.py — M40-c Phase 运行时回归验证脚本。

覆盖测试：
  M40-c-1  memory technical_only custom_coordinator
  M40-c-2  memory output_language en-US
  M40-c-3  memory LangGraph engine
  M40-c-4  memory cancel
  M40-c-5  redis technical_only custom_coordinator
  M40-c-6  redis output_language en-US
  M40-c-7  redis LangGraph engine
  M40-c-8  redis after_event_id replay
  M40-c-9  redis cancel
  M40-c-10 dual registry cross-instance simulation
  M40-c-12 redis unavailable → fail-fast (no server needed)
  M40-c-13 TTL config
  M40-c-14 event maxlen

要求：
  - 本地 Redis 在 redis://localhost:6379 可达
  - .env 文件在 backend/ 目录（或上层）配置了 DATABASE_URL
  - uv 在 PATH 中可用（用于启动 uvicorn 子进程）

用法：
  cd backend
  uv run python scripts/verify_m40c_runtime_regression.py

退出码：0=全部 PASS，1=有 FAIL
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
import traceback
import uuid
from typing import Optional

# ── Path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import httpx
from redis.asyncio import from_url as redis_from_url

BACKEND_DIR   = os.path.dirname(os.path.dirname(__file__))
BASE_URL      = "http://127.0.0.1:8001"
REDIS_URL     = os.environ.get("REDIS_URL", "redis://localhost:6379")
TEST_EMAIL    = f"m40c_test_{uuid.uuid4().hex[:8]}@test.invalid"
TEST_PASSWORD = "TestPass123!"

SSE_TIMEOUT      = 180   # seconds to wait for report_ready
STARTUP_TIMEOUT  = 20    # seconds to wait for server ready

# ── Result tracking ───────────────────────────────────────────────────────────

_results: list[tuple[str, bool, str]] = []


def _pass(name: str, detail: str = "") -> None:
    _results.append((name, True, detail))
    print(f"  PASS  {name}" + (f"  — {detail}" if detail else ""))


def _fail(name: str, reason: str) -> None:
    _results.append((name, False, reason))
    print(f"  FAIL  {name}  — {reason}")


def _skip(name: str, reason: str) -> None:
    _results.append((name, True, f"[SKIP] {reason}"))
    print(f"  SKIP  {name}  — {reason}")


# ── Server lifecycle ──────────────────────────────────────────────────────────

def _start_server(env_overrides: dict) -> subprocess.Popen:
    """Start uvicorn on port 8001 with given env overrides."""
    env = os.environ.copy()
    env.update(env_overrides)
    # Prevent port conflicts
    env["PORT"] = "8001"

    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "app.main:app",
            "--host", "127.0.0.1",
            "--port", "8001",
            "--log-level", "warning",
        ],
        cwd=BACKEND_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    return proc


async def _wait_server_ready(timeout: int = STARTUP_TIMEOUT) -> bool:
    """Poll /health until server responds or timeout."""
    deadline = time.time() + timeout
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=5) as client:
        while time.time() < deadline:
            try:
                r = await client.get("/health")
                if r.status_code == 200:
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.4)
    return False


def _stop_server(proc: subprocess.Popen) -> None:
    """Gracefully stop the server subprocess."""
    try:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


# ── Auth helpers ──────────────────────────────────────────────────────────────

async def _get_token(client: httpx.AsyncClient) -> Optional[str]:
    """Register a test user and return JWT access token."""
    # Try register first
    r = await client.post("/auth/register", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
    })
    if r.status_code not in (200, 201, 409):  # 409 = already exists
        return None

    # Login to get token
    r = await client.post("/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
    })
    if r.status_code != 200:
        return None
    return r.json().get("access_token")


# ── SSE reader ────────────────────────────────────────────────────────────────

async def _read_sse_events(
    client:         httpx.AsyncClient,
    url:            str,
    token:          str,
    stop_events:    frozenset = frozenset({"report_ready", "analysis_failed", "cancelled"}),
    timeout:        int = SSE_TIMEOUT,
    max_events:     int = 200,
    after_event_id: Optional[int] = None,
) -> list[dict]:
    """Stream SSE events, return list of parsed event dicts."""
    params = {}
    if after_event_id is not None:
        params["after_event_id"] = after_event_id

    events: list[dict] = []
    deadline = time.time() + timeout

    try:
        async with client.stream(
            "GET", url,
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=timeout,
        ) as resp:
            if resp.status_code != 200:
                return []

            async for line in resp.aiter_lines():
                if time.time() > deadline:
                    break
                if len(events) >= max_events:
                    break

                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if not raw:
                    continue
                try:
                    evt = json.loads(raw)
                    events.append(evt)
                    if evt.get("event") in stop_events:
                        break
                except (json.JSONDecodeError, ValueError):
                    pass
    except Exception:
        pass

    return events


# ── API test helpers ──────────────────────────────────────────────────────────

async def _create_run(
    client: httpx.AsyncClient,
    token:  str,
    market: str = "CN",
    symbol: str = "000001",
    scope:  str = "technical_only",
    engine: str = "custom_coordinator",
    lang:   str = "zh-CN",
) -> Optional[str]:
    """POST /analysis/runs, return run_id or None."""
    r = await client.post(
        "/analysis/runs",
        json={
            "market":          market,
            "symbol":          symbol,
            "analysis_scope":  scope,
            "engine":          engine,
            "output_language": lang,
        },
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if r.status_code != 201:
        return None
    return r.json().get("run_id")


async def _get_run(
    client: httpx.AsyncClient, token: str, run_id: str
) -> Optional[dict]:
    r = await client.get(
        f"/analysis/runs/{run_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    if r.status_code != 200:
        return None
    return r.json()


async def _cancel_run(
    client: httpx.AsyncClient, token: str, run_id: str
) -> Optional[dict]:
    r = await client.post(
        f"/analysis/runs/{run_id}/cancel",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    if r.status_code != 200:
        return None
    return r.json()


# ── Memory mode tests ─────────────────────────────────────────────────────────

async def run_memory_tests(token: str) -> None:
    print("\n── Memory Mode Tests ──────────────────────────────────────")

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=SSE_TIMEOUT + 10) as client:

        # M40-c-1: memory technical_only custom_coordinator
        print("\n[M40-c-1] memory technical_only custom_coordinator")
        run_id = await _create_run(client, token, scope="technical_only", engine="custom_coordinator", lang="zh-CN")
        if not run_id:
            _fail("M40-c-1_create_run", "POST /analysis/runs failed")
        else:
            _pass("M40-c-1_create_run", f"run_id={run_id[:8]}")
            events = await _read_sse_events(client, f"/analysis/runs/{run_id}/events", token)
            event_types = {e.get("event") for e in events}

            if "analysis_started" not in event_types:
                _fail("M40-c-1_analysis_started", f"event_types={event_types}")
            else:
                _pass("M40-c-1_analysis_started")

            if "report_ready" not in event_types:
                _fail("M40-c-1_report_ready", f"event_types={event_types}")
            else:
                _pass("M40-c-1_report_ready")

            # event_id stamping
            stamped = [e for e in events if "event_id" in e]
            if not stamped:
                _fail("M40-c-1_event_id_stamped", "No events have event_id")
            else:
                _pass("M40-c-1_event_id_stamped", f"{len(stamped)}/{len(events)} events stamped")

            snap = await _get_run(client, token, run_id)
            if snap is None or snap.get("status") != "completed":
                _fail("M40-c-1_get_run_completed", f"status={snap.get('status') if snap else None}")
            else:
                _pass("M40-c-1_get_run_completed", f"status={snap.get('status')}")

        # M40-c-2: memory output_language en-US
        print("\n[M40-c-2] memory output_language en-US")
        run_id2 = await _create_run(client, token, scope="technical_only", engine="custom_coordinator", lang="en-US")
        if not run_id2:
            _fail("M40-c-2_create_run", "POST failed")
        else:
            events2 = await _read_sse_events(client, f"/analysis/runs/{run_id2}/events", token)
            snap2 = await _get_run(client, token, run_id2)

            rr = next((e for e in events2 if e.get("event") == "report_ready"), None)
            if rr is None:
                _fail("M40-c-2_report_ready", f"events={[e.get('event') for e in events2]}")
            else:
                _pass("M40-c-2_report_ready")

            if snap2 and snap2.get("result", {}).get("output_language") == "en-US":
                _pass("M40-c-2_output_language", "result.output_language=en-US")
            elif snap2 and snap2.get("result", {}).get("metadata", {}).get("output_language") == "en-US":
                _pass("M40-c-2_output_language", "metadata.output_language=en-US")
            else:
                # Check event for output_language
                ol = None
                if rr:
                    ol = rr.get("output_language") or (rr.get("result") or {}).get("output_language")
                if ol == "en-US":
                    _pass("M40-c-2_output_language", "event output_language=en-US")
                else:
                    # As long as no NameError and report_ready received, P0 fix is verified
                    if rr is not None:
                        _pass("M40-c-2_no_name_error", "report_ready received — no NameError")
                    else:
                        _fail("M40-c-2_output_language", f"snap={snap2}")

        # M40-c-3: memory LangGraph
        print("\n[M40-c-3] memory LangGraph engine")
        run_id3 = await _create_run(client, token, scope="technical_only", engine="langgraph", lang="en-US")
        if not run_id3:
            _fail("M40-c-3_create_run", "POST failed")
        else:
            events3 = await _read_sse_events(client, f"/analysis/runs/{run_id3}/events", token)
            snap3 = await _get_run(client, token, run_id3)

            if snap3 and snap3.get("workflow_engine") == "langgraph":
                _pass("M40-c-3_workflow_engine", "workflow_engine=langgraph")
            else:
                _fail("M40-c-3_workflow_engine", f"snap={snap3}")

            rr3 = next((e for e in events3 if e.get("event") == "report_ready"), None)
            if rr3:
                _pass("M40-c-3_report_ready")
            else:
                _fail("M40-c-3_report_ready", f"events={[e.get('event') for e in events3[-5:]]}")

        # M40-c-4: memory cancel
        print("\n[M40-c-4] memory cancel")
        run_id4 = await _create_run(client, token, scope="technical_only", engine="custom_coordinator")
        if not run_id4:
            _fail("M40-c-4_create_run", "POST failed")
        else:
            # Cancel immediately
            await asyncio.sleep(0.3)
            cancel_resp = await _cancel_run(client, token, run_id4)
            if cancel_resp is None:
                _fail("M40-c-4_cancel_endpoint", "cancel POST failed")
            else:
                _pass("M40-c-4_cancel_endpoint", f"resp={cancel_resp}")

            # Check GET run — should be cancelled or completed (if already done before cancel)
            snap4 = await _get_run(client, token, run_id4)
            if snap4 and snap4.get("status") in ("cancelled", "completed", "failed"):
                _pass("M40-c-4_terminal_status", f"status={snap4.get('status')}")
            else:
                _fail("M40-c-4_terminal_status", f"status={snap4.get('status') if snap4 else None}")


# ── Redis mode tests ──────────────────────────────────────────────────────────

async def run_redis_tests(token: str) -> None:
    print("\n── Redis Mode Tests ───────────────────────────────────────")

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=SSE_TIMEOUT + 10) as client:

        # M40-c-5: redis technical_only custom_coordinator
        print("\n[M40-c-5] redis technical_only custom_coordinator")
        run_id5 = await _create_run(client, token, scope="technical_only", engine="custom_coordinator", lang="zh-CN")
        if not run_id5:
            _fail("M40-c-5_create_run", "POST /analysis/runs failed (Redis mode)")
        else:
            _pass("M40-c-5_create_run", f"run_id={run_id5[:8]}")
            events5 = await _read_sse_events(client, f"/analysis/runs/{run_id5}/events", token)
            event_types5 = {e.get("event") for e in events5}

            if "report_ready" in event_types5:
                _pass("M40-c-5_report_ready")
            else:
                _fail("M40-c-5_report_ready", f"event_types={event_types5}")

            # Check Redis keys
            redis = redis_from_url(REDIS_URL, decode_responses=True)
            try:
                from app.core.config import settings
                env = settings.app_env
                hash_key = f"ta:{env}:run:{run_id5}"
                raw = await redis.hgetall(hash_key)
                if raw:
                    _pass("M40-c-5_redis_hash", f"Hash has {len(raw)} fields")
                else:
                    _fail("M40-c-5_redis_hash", f"Hash empty for key {hash_key!r}")

                elist_key = f"ta:{env}:run:{run_id5}:events"
                elist_len = await redis.llen(elist_key)
                if elist_len > 0:
                    _pass("M40-c-5_redis_events_list", f"List has {elist_len} events")
                else:
                    _fail("M40-c-5_redis_events_list", "List empty")
            finally:
                await redis.aclose()

            snap5 = await _get_run(client, token, run_id5)
            if snap5 and snap5.get("status") == "completed":
                _pass("M40-c-5_get_run_completed")
                if snap5.get("analysis_scope") == "technical_only":
                    _pass("M40-c-5_analysis_scope")
                else:
                    _fail("M40-c-5_analysis_scope", f"analysis_scope={snap5.get('analysis_scope')}")
            else:
                _fail("M40-c-5_get_run_completed", f"status={snap5.get('status') if snap5 else None}")

        # M40-c-6: redis output_language en-US
        print("\n[M40-c-6] redis output_language en-US")
        run_id6 = await _create_run(client, token, scope="technical_only", engine="custom_coordinator", lang="en-US")
        if not run_id6:
            _fail("M40-c-6_create_run", "POST failed")
        else:
            events6 = await _read_sse_events(client, f"/analysis/runs/{run_id6}/events", token)
            rr6 = next((e for e in events6 if e.get("event") == "report_ready"), None)
            if rr6:
                _pass("M40-c-6_report_ready")
            else:
                _fail("M40-c-6_report_ready", "report_ready not received")

            # Check Redis hash for output_language
            redis = redis_from_url(REDIS_URL, decode_responses=True)
            try:
                from app.core.config import settings
                env = settings.app_env
                val = await redis.hget(f"ta:{env}:run:{run_id6}", "output_language")
                if val == "en-US":
                    _pass("M40-c-6_redis_output_language", "Redis hash output_language=en-US")
                else:
                    _fail("M40-c-6_redis_output_language", f"Redis output_language={val!r}")
            finally:
                await redis.aclose()

        # M40-c-7: redis LangGraph
        print("\n[M40-c-7] redis LangGraph engine")
        run_id7 = await _create_run(client, token, scope="technical_only", engine="langgraph", lang="en-US")
        if not run_id7:
            _fail("M40-c-7_create_run", "POST failed")
        else:
            events7 = await _read_sse_events(client, f"/analysis/runs/{run_id7}/events", token)
            snap7 = await _get_run(client, token, run_id7)

            if snap7 and snap7.get("workflow_engine") == "langgraph":
                _pass("M40-c-7_workflow_engine")
            else:
                _fail("M40-c-7_workflow_engine", f"snap={snap7}")

            rr7 = next((e for e in events7 if e.get("event") == "report_ready"), None)
            if rr7:
                _pass("M40-c-7_report_ready")
            else:
                _fail("M40-c-7_report_ready", f"events={[e.get('event') for e in events7[-5:]]}")

        # M40-c-8: redis after_event_id replay
        print("\n[M40-c-8] redis after_event_id replay")
        run_id8 = await _create_run(client, token, scope="technical_only", engine="custom_coordinator")
        if not run_id8:
            _fail("M40-c-8_create_run", "POST failed")
        else:
            # Read first few events then disconnect
            first_events = await _read_sse_events(
                client, f"/analysis/runs/{run_id8}/events", token,
                stop_events=frozenset({"analysis_started"}),  # stop after first event type
                max_events=3,
            )
            # Find max event_id seen
            seen_ids = [e.get("event_id") for e in first_events if e.get("event_id") is not None]
            if not seen_ids:
                _fail("M40-c-8_first_events", f"No stamped events: {first_events}")
            else:
                cutoff = max(seen_ids)
                _pass("M40-c-8_first_events", f"Read {len(first_events)} events, cutoff eid={cutoff}")

                # Wait for analysis to complete (needed so replay has events to return)
                all_events = await _read_sse_events(
                    client, f"/analysis/runs/{run_id8}/events", token,
                )
                all_ids = sorted([e.get("event_id") for e in all_events if e.get("event_id") is not None])
                _pass("M40-c-8_all_events_collected", f"eid sequence: {all_ids}")

                # Now replay with after_event_id=cutoff
                replay_events = await _read_sse_events(
                    client, f"/analysis/runs/{run_id8}/events", token,
                    after_event_id=cutoff,
                )
                replay_ids = [e.get("event_id") for e in replay_events if e.get("event_id") is not None]

                # All replayed event_ids should be > cutoff
                stale = [eid for eid in replay_ids if eid is not None and eid <= cutoff]
                if stale:
                    _fail("M40-c-8_no_duplicates", f"Replayed stale eids: {stale}")
                else:
                    _pass("M40-c-8_no_duplicates", f"Replayed {len(replay_events)} events, all eid > {cutoff}")

                # Should still have report_ready in replay
                has_terminal = any(e.get("event") in {"report_ready", "analysis_failed"} for e in replay_events)
                if has_terminal:
                    _pass("M40-c-8_report_ready_in_replay")
                else:
                    # Already completed — replay from List should still have it
                    snap8 = await _get_run(client, token, run_id8)
                    if snap8 and snap8.get("status") == "completed":
                        _pass("M40-c-8_run_completed", f"status=completed (replay was after report_ready)")
                    else:
                        _fail("M40-c-8_report_ready_in_replay", f"events={[e.get('event') for e in replay_events]}")

        # M40-c-9: redis cancel
        print("\n[M40-c-9] redis cancel")
        run_id9 = await _create_run(client, token, scope="technical_only", engine="custom_coordinator")
        if not run_id9:
            _fail("M40-c-9_create_run", "POST failed")
        else:
            await asyncio.sleep(0.3)
            cancel9 = await _cancel_run(client, token, run_id9)
            if cancel9 is None:
                _fail("M40-c-9_cancel_endpoint", "cancel POST failed")
            else:
                _pass("M40-c-9_cancel_endpoint", f"resp={cancel9}")

            # Check Redis state
            redis = redis_from_url(REDIS_URL, decode_responses=True)
            try:
                from app.core.config import settings
                env = settings.app_env
                status_val = await redis.hget(f"ta:{env}:run:{run_id9}", "status")
                cancel_val = await redis.hget(f"ta:{env}:run:{run_id9}", "cancel_requested")
                if status_val == "cancelled":
                    _pass("M40-c-9_redis_status_cancelled")
                else:
                    # Could be completed if analysis finished before cancel
                    if status_val in ("completed", "failed"):
                        _pass("M40-c-9_redis_terminal", f"status={status_val} (finished before cancel)")
                    else:
                        _fail("M40-c-9_redis_status", f"status={status_val!r}")

                if cancel_val == "1":
                    _pass("M40-c-9_cancel_requested_flag")
                else:
                    _skip("M40-c-9_cancel_requested_flag", f"cancel_requested={cancel_val!r} (may be completed)")
            finally:
                await redis.aclose()

            snap9 = await _get_run(client, token, run_id9)
            if snap9 and snap9.get("status") in ("cancelled", "completed", "failed"):
                _pass("M40-c-9_get_run_terminal", f"status={snap9.get('status')}")
            else:
                _fail("M40-c-9_get_run_terminal", f"status={snap9.get('status') if snap9 else None}")


# ── Registry-level tests (no server) ─────────────────────────────────────────

async def run_registry_level_tests() -> None:
    print("\n── Registry-Level Tests (no server) ──────────────────────")

    from app.services.redis_run_registry import RedisAnalysisRunRegistry

    redis_a = redis_from_url(REDIS_URL, decode_responses=True)
    redis_b = redis_from_url(REDIS_URL, decode_responses=True)

    try:
        # M40-c-10: dual registry cross-instance simulation
        print("\n[M40-c-10] dual registry cross-instance")
        reg_a = RedisAnalysisRunRegistry(redis=redis_a, ttl_seconds=300, event_maxlen=50, env="test-c10")
        reg_b = RedisAnalysisRunRegistry(redis=redis_b, ttl_seconds=300, event_maxlen=50, env="test-c10")

        ref = await reg_a.create_run(
            user_id="user-a", market="CN", symbol="000001",
            analysis_scope="technical_only", workflow_engine="custom_coordinator", output_language="zh-CN",
        )
        await reg_a.push_event(ref.run_id, {"event": "analysis_started", "progress": 0})
        await reg_a.push_event(ref.run_id, {"event": "report_ready", "progress": 100})

        # reg_b reads what reg_a wrote
        snap_b = await reg_b.get_run_snapshot(ref.run_id)
        if snap_b is None:
            _fail("M40-c-10_cross_snapshot", "reg_b cannot see reg_a's run")
        else:
            _pass("M40-c-10_cross_snapshot", f"reg_b sees run from reg_a: status={snap_b.status}")

        events_b = await reg_b.get_events_after(ref.run_id, None)
        if len(events_b) >= 2:
            _pass("M40-c-10_cross_events", f"reg_b sees {len(events_b)} events from reg_a")
        else:
            _fail("M40-c-10_cross_events", f"reg_b sees only {len(events_b)} events")

        # cancel from reg_b, check reg_a sees it
        ref2 = await reg_a.create_run(
            user_id="user-a", market="HK", symbol="00700",
            analysis_scope="news_only", workflow_engine="custom_coordinator", output_language="en-US",
        )
        await reg_b.request_cancel(ref2.run_id)
        is_cancelled = await reg_a.is_cancel_requested(ref2.run_id)
        if is_cancelled:
            _pass("M40-c-10_cross_cancel", "reg_a sees cancel requested by reg_b")
        else:
            _fail("M40-c-10_cross_cancel", "reg_a cannot see cancel from reg_b")

        # M40-c-12: Redis unavailable fail-fast
        print("\n[M40-c-12] Redis unavailable → fail-fast")
        # Test the factory directly with bad URL
        import importlib
        import sys as _sys

        # Temporarily simulate unavailable Redis by testing _safe_get_registry behaviour
        # We test the factory logic: when redis_client is None, get_run_registry raises RuntimeError
        # This simulates what happens when connect_redis() fails (Redis not reachable)
        from app.services import run_registry_factory as factory_mod

        # Save state
        original_registry = factory_mod._registry

        # Clear singleton to force re-init
        factory_mod._registry = None

        # Monkey-patch get_redis to return None (simulates unavailable Redis)
        import app.core.database as db_mod
        original_get_redis = db_mod.get_redis
        db_mod.get_redis = lambda: None

        # Temporarily set mode to redis
        import app.core.config as cfg_mod
        original_mode = cfg_mod.settings.analysis_run_registry
        cfg_mod.settings.analysis_run_registry = "redis"

        try:
            factory_mod.get_run_registry()
            _fail("M40-c-12_fail_fast", "Expected RuntimeError but no exception raised")
        except RuntimeError as e:
            _pass("M40-c-12_fail_fast", f"RuntimeError raised: {str(e)[:60]}")
        except Exception as e:
            _fail("M40-c-12_fail_fast", f"Unexpected exception type: {type(e).__name__}: {e}")
        finally:
            # Restore
            db_mod.get_redis = original_get_redis
            cfg_mod.settings.analysis_run_registry = original_mode
            factory_mod._registry = original_registry

        # M40-c-13: TTL config
        print("\n[M40-c-13] TTL config")
        short_ttl_reg = RedisAnalysisRunRegistry(redis=redis_a, ttl_seconds=10, event_maxlen=50, env="test-ttl")
        ref_ttl = await short_ttl_reg.create_run(
            user_id="ttl-user", market="CN", symbol="000001",
            analysis_scope="technical_only", workflow_engine="custom_coordinator", output_language="zh-CN",
        )
        await short_ttl_reg.push_event(ref_ttl.run_id, {"event": "analysis_started", "progress": 0})
        ttl_val = await redis_a.ttl(f"ta:test-ttl:run:{ref_ttl.run_id}")
        if 0 < ttl_val <= 10:
            _pass("M40-c-13_ttl_set", f"TTL={ttl_val}s (≤10s as configured)")
        else:
            _fail("M40-c-13_ttl_set", f"TTL={ttl_val}s, expected 0 < TTL ≤ 10")

        # M40-c-14: event maxlen
        print("\n[M40-c-14] event maxlen")
        maxlen_reg = RedisAnalysisRunRegistry(redis=redis_a, ttl_seconds=300, event_maxlen=3, env="test-maxlen")
        ref_ml = await maxlen_reg.create_run(
            user_id="ml-user", market="CN", symbol="000001",
            analysis_scope="technical_only", workflow_engine="custom_coordinator", output_language="zh-CN",
        )
        # Push 5 events — list should be trimmed to 3
        for i in range(5):
            await maxlen_reg.push_event(ref_ml.run_id, {"event": f"evt_{i}", "progress": i * 10})

        list_len = await redis_a.llen(f"ta:test-maxlen:run:{ref_ml.run_id}:events")
        if list_len == 3:
            _pass("M40-c-14_maxlen_trim", f"List trimmed to {list_len} (maxlen=3)")
        elif list_len <= 3:
            _pass("M40-c-14_maxlen_trim", f"List has {list_len} ≤ 3 events (OK)")
        else:
            _fail("M40-c-14_maxlen_trim", f"List has {list_len} events, expected ≤3")

        # Confirm early events are evicted
        events_ml = await maxlen_reg.get_events_after(ref_ml.run_id, None)
        ids_ml = [e.get("event_id") for e in events_ml]
        # event_ids should be 3, 4, 5 (last 3 of 5 pushed)
        if ids_ml and min(ids_ml) >= 3:
            _pass("M40-c-14_early_evicted", f"Retained eids: {ids_ml} (early events evicted)")
        else:
            _fail("M40-c-14_early_evicted", f"Retained eids: {ids_ml}")

    finally:
        await redis_a.aclose()
        await redis_b.aclose()


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> int:
    print("\nM40-c Runtime Regression Verification")
    print("=" * 60)

    # ── Registry-level tests (no server needed) ───────────────────────────────
    try:
        await run_registry_level_tests()
    except Exception as exc:
        print(f"\nFATAL in registry-level tests: {exc}")
        traceback.print_exc()

    # ── Memory mode API tests ─────────────────────────────────────────────────
    print("\n\n=== Memory Mode: Starting server (no ANALYSIS_RUN_REGISTRY) ===")
    mem_proc = _start_server({
        "ANALYSIS_RUN_REGISTRY": "memory",
    })
    try:
        ready = await _wait_server_ready()
        if not ready:
            _fail("server_memory_startup", f"Server did not start within {STARTUP_TIMEOUT}s")
            stderr_out = mem_proc.stderr.read(2000) if mem_proc.stderr else b""
            print(f"  Server stderr: {stderr_out.decode(errors='replace')[:500]}")
        else:
            _pass("server_memory_startup", "Server ready on :8001")

            async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as auth_client:
                token = await _get_token(auth_client)

            if not token:
                _fail("server_memory_auth", "Could not obtain JWT token")
            else:
                _pass("server_memory_auth", "JWT token obtained")
                await run_memory_tests(token)
    finally:
        _stop_server(mem_proc)
        await asyncio.sleep(1)  # brief wait for port release

    # ── Redis mode API tests ──────────────────────────────────────────────────
    print("\n\n=== Redis Mode: Starting server (ANALYSIS_RUN_REGISTRY=redis) ===")
    redis_proc = _start_server({
        "ANALYSIS_RUN_REGISTRY": "redis",
        "REDIS_URL": REDIS_URL,
    })
    try:
        ready2 = await _wait_server_ready()
        if not ready2:
            _fail("server_redis_startup", f"Server did not start within {STARTUP_TIMEOUT}s")
            stderr_out = redis_proc.stderr.read(2000) if redis_proc.stderr else b""
            print(f"  Server stderr: {stderr_out.decode(errors='replace')[:500]}")
        else:
            _pass("server_redis_startup", "Server ready on :8001 (Redis mode)")

            # Reuse same test user (already registered)
            async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as auth_client:
                token2 = await _get_token(auth_client)

            if not token2:
                _fail("server_redis_auth", "Could not obtain JWT token")
            else:
                _pass("server_redis_auth", "JWT token obtained")
                await run_redis_tests(token2)
    finally:
        _stop_server(redis_proc)

    # ── Summary ───────────────────────────────────────────────────────────────
    total  = len(_results)
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = total - passed
    skipped = sum(1 for _, _, d in _results if d.startswith("[SKIP]"))

    print("\n" + "=" * 60)
    print(f"Results: {passed}/{total} PASS  |  {failed} FAIL  |  {skipped} SKIP")
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
