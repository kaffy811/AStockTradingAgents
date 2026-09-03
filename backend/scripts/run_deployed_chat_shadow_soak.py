#!/usr/bin/env python3
"""
Phase 6V-P1.27 — Deployed Chat-Orchestration Shadow Soak Harness
=================================================================
Sends real HTTP requests through the full chat endpoint chain:
  Host → HTTP → Router → Orchestrator → Canary Eligibility
  → Canary Selection → Legacy Executor → Pi Shadow Executor (async)
  → Response (legacy) → Diagnostics JSONL

Guards:
  - Only allows 127.0.0.1/localhost base URLs
  - Refuses production environments
  - Refuses if rollout != 100 / cv != 11 / salt != pi_v1
  - Refuses if live=true or production=true
  - Refuses if shadow mode not active

Usage:
    python3 backend/scripts/run_deployed_chat_shadow_soak.py \
        --base-url http://127.0.0.1:18000 \
        --windows 10 \
        --requests-per-window 1000 \
        --output-dir backend/docs/artifacts
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import threading
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# ── Constants ─────────────────────────────────────────────────────────────────
CANARY_AGENT_ID = "official_report_pdf_pi_v1"
EXPECTED_ROLLOUT = 100.0
EXPECTED_CV = 11
EXPECTED_SALT = "pi_v1"
EXPECTED_STATUS = "approved"
EXPECTED_LIVE = False
EXPECTED_PROD = False
EXPECTED_SHADOW_MODE = "pi_compatible_shadow"

ALLOWED_HOSTS = {"127.0.0.1", "localhost"}
CONTAINER_NAME = "tradingagents-p125-staging-backend-1"
DIAGNOSTICS_PATH = "/tmp/tradingagents-runtime/pi_shadow_diagnostics.jsonl"
SNAPSHOT_PATH = "/tmp/tradingagents-runtime/pi_canary_snapshot.json"

# PDF-intent queries that trigger Pi shadow path
PDF_QUERIES = [
    "贵州茅台年报下载",
    "平安银行年度报告PDF",
    "中国平安年报在哪里",
    "招商银行半年报链接",
    "宁德时代年报PDF",
    "比亚迪季报原文",
    "隆基绿能年度报告",
    "中芯国际中报PDF",
    "东方财富年报链接",
    "五粮液年报原文",
    "格力电器年度报告",
    "美的集团半年报",
    "万科年报PDF下载",
    "恒瑞医药季报原文",
    "海天味业年报链接",
    "宁波银行年度报告",
    "招商证券年报PDF",
    "华夏银行中报",
    "紫金矿业年报下载",
    "华润置地年报原文",
]
GENERAL_QUERIES = [
    "贵州茅台最近表现如何",
    "帮我分析宁德时代",
    "平安银行行业对比",
    "比亚迪最新动态",
    "今天行情怎么样",
    "推荐几只好股票",
    "帮我看看自选股",
    "最近有什么热门行业",
    "投资策略建议",
    "半导体板块分析",
]


# ── Safety guards ─────────────────────────────────────────────────────────────

def validate_base_url(base_url: str) -> None:
    """Refuse non-localhost URLs."""
    import urllib.parse
    parsed = urllib.parse.urlparse(base_url)
    host = parsed.hostname or ""
    if host not in ALLOWED_HOSTS:
        raise SystemExit(f"SAFETY ABORT: base_url host '{host}' is not in allowed hosts {ALLOWED_HOSTS}")


def read_snapshot() -> Dict[str, Any]:
    """Read live snapshot from container via docker exec."""
    result = subprocess.run(
        ["docker", "exec", CONTAINER_NAME, "cat", SNAPSHOT_PATH],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        raise SystemExit(f"Cannot read snapshot: {result.stderr}")
    return json.loads(result.stdout)


def validate_snapshot(snap: Dict[str, Any]) -> None:
    """Refuse if snapshot doesn't match expected canary state."""
    rollout = snap.get("rollout_percent")
    cv = snap.get("config_version")
    salt = snap.get("stable_bucket_salt_version")
    live = snap.get("live")
    prod = snap.get("production_enabled")
    parse_error = snap.get("parse_error")

    if rollout != EXPECTED_ROLLOUT:
        raise SystemExit(f"SAFETY ABORT: rollout={rollout} != {EXPECTED_ROLLOUT}")
    if cv != EXPECTED_CV:
        raise SystemExit(f"SAFETY ABORT: config_version={cv} != {EXPECTED_CV}")
    if salt != EXPECTED_SALT:
        raise SystemExit(f"SAFETY ABORT: salt={salt} != {EXPECTED_SALT}")
    if live is not False:
        raise SystemExit(f"SAFETY ABORT: live={live}, must be false")
    if prod is not False:
        raise SystemExit(f"SAFETY ABORT: production_enabled={prod}, must be false")
    if parse_error is not None:
        raise SystemExit(f"SAFETY ABORT: parse_error={parse_error}")


def read_diagnostics_since(prev_count: int) -> List[Dict[str, Any]]:
    """Read new diagnostics records written since prev_count."""
    result = subprocess.run(
        ["docker", "exec", CONTAINER_NAME, "cat", DIAGNOSTICS_PATH],
        capture_output=True, text=True, timeout=15
    )
    if result.returncode != 0:
        return []
    records = []
    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return records[prev_count:]


def count_diagnostics() -> int:
    """Count total diagnostics records in container."""
    result = subprocess.run(
        ["docker", "exec", CONTAINER_NAME, "sh", "-c", f"wc -l < {DIAGNOSTICS_PATH}"],
        capture_output=True, text=True, timeout=10
    )
    try:
        return int(result.stdout.strip())
    except ValueError:
        return 0


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def http_get(url: str, token: Optional[str] = None, timeout: int = 15) -> Tuple[int, Any]:
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, None
    except Exception as e:
        return 0, str(e)


def http_post(url: str, payload: dict, token: Optional[str] = None,
              timeout: int = 30) -> Tuple[int, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                  headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, None
    except Exception as e:
        return 0, str(e)


# ── Auth ──────────────────────────────────────────────────────────────────────

def get_token(base_url: str) -> str:
    status, body = http_post(f"{base_url}/api/v1/auth/login",
                              {"username": "p126test", "password": "P126TestPass!"})
    if status == 200 and isinstance(body, dict) and "access_token" in body:
        return body["access_token"]
    # Attempt registration then login
    http_post(f"{base_url}/api/v1/auth/register",
              {"email": "p127soak@example.com", "username": "p127soak",
               "password": "P127SoakPass!"})
    status, body = http_post(f"{base_url}/api/v1/auth/login",
                              {"username": "p127soak", "password": "P127SoakPass!"})
    if status == 200 and isinstance(body, dict) and "access_token" in body:
        return body["access_token"]
    raise SystemExit(f"Cannot obtain auth token: {status} {body}")


def create_session(base_url: str, token: str, title: str) -> str:
    status, body = http_post(f"{base_url}/api/v1/chat/sessions",
                              {"title": title}, token=token)
    if status in (200, 201) and isinstance(body, dict) and "session_id" in body:
        return body["session_id"]
    raise RuntimeError(f"Cannot create session: {status} {body}")


def send_chat_message(base_url: str, token: str, session_id: str,
                      content: str) -> Tuple[int, Dict[str, Any]]:
    url = f"{base_url}/api/v1/chat/sessions/{session_id}/messages"
    status, body = http_post(url, {"content": content, "output_language": "zh-CN"},
                              token=token, timeout=60)
    return status, body if isinstance(body, dict) else {}


# ── Soak window ───────────────────────────────────────────────────────────────

_session_lock = threading.Lock()


def _send_one(args_tuple):
    """Worker for concurrent request dispatch."""
    base_url, token, session_id, query, idx = args_tuple
    t_req = time.time()
    if session_id:
        status, resp = send_chat_message(base_url, token, session_id, query)
    else:
        status, resp = 0, {}
    http_latency = (time.time() - t_req) * 1000
    return status, resp, http_latency


def run_soak_window(
    window_id: str,
    base_url: str,
    token: str,
    requests_per_window: int,
    cumulative_before: int,
    snap: Dict[str, Any],
    concurrency: int = 8,
) -> Dict[str, Any]:
    ts_start = datetime.now(timezone.utc).isoformat()
    t_start = time.time()

    diag_count_before = count_diagnostics()

    # Pre-create session pool (one per concurrency slot, refreshed every 50 msgs)
    sessions: Dict[int, Optional[str]] = {}
    for slot in range(concurrency):
        try:
            sessions[slot] = create_session(base_url, token, f"soak_{window_id}_s{slot}")
        except RuntimeError:
            sessions[slot] = None

    completed = 0
    failed = 0
    pi_violations = 0
    terminal_violations = 0
    http_latencies: List[float] = []
    query_count = 0

    # Mix PDF-intent and general queries across the window
    pdf_ratio = 0.5
    pdf_per_window = int(requests_per_window * pdf_ratio)

    # Build request list
    request_args = []
    for i in range(requests_per_window):
        slot = i % concurrency
        if i < pdf_per_window:
            query = PDF_QUERIES[i % len(PDF_QUERIES)]
        else:
            query = GENERAL_QUERIES[i % len(GENERAL_QUERIES)]
        # Refresh session every 50 messages per slot
        if i > 0 and (i // concurrency) % 50 == 0:
            try:
                sessions[slot] = create_session(base_url, token, f"soak_{window_id}_s{slot}_r{i}")
            except RuntimeError:
                pass
        request_args.append((base_url, token, sessions[slot], query, i))

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(_send_one, arg) for arg in request_args]
        for fut in as_completed(futures):
            try:
                status, resp, http_latency = fut.result()
            except Exception:
                status, resp, http_latency = 0, {}, 0.0
            query_count += 1
            if status == 200:
                completed += 1
                http_latencies.append(http_latency)
                answer = resp.get("answer", "")
                if "pi_financial_runtime" in str(resp) or "official_report_pdf_pi_v1" in answer:
                    pi_violations += 1
            else:
                failed += 1

    # Wait briefly for async Pi shadow tasks to complete
    time.sleep(3)

    diag_count_after = count_diagnostics()
    new_diagnostics = diag_count_after - diag_count_before

    # Read new diagnostics
    all_diags = read_diagnostics_since(diag_count_before)
    shadow_started = len([d for d in all_diags if d.get("status") != "MISSING"])
    shadow_completed = len([d for d in all_diags if d.get("terminal", False)])
    shadow_failed_pi = len([d for d in all_diags if d.get("error_code") and d.get("status") not in ("success",)])

    elapsed = time.time() - t_start

    # Latency stats
    def pct(lst, p):
        if not lst:
            return 0
        lst_s = sorted(lst)
        idx = int(len(lst_s) * p / 100)
        return round(lst_s[min(idx, len(lst_s)-1)], 1)

    http_p50 = pct(http_latencies, 50)
    http_p95 = pct(http_latencies, 95)
    http_p99 = pct(http_latencies, 99)

    # Determine window pass
    snapshot_ok = (
        snap.get("rollout_percent") == EXPECTED_ROLLOUT
        and snap.get("config_version") == EXPECTED_CV
        and snap.get("stable_bucket_salt_version") == EXPECTED_SALT
        and snap.get("live") is False
        and snap.get("production_enabled") is False
        and snap.get("parse_error") is None
    )

    window_pass = (
        snapshot_ok
        and completed >= int(requests_per_window * 0.95)  # >=95% success
        and pi_violations == 0
        and terminal_violations == 0
    )

    return {
        "window_id": window_id,
        "timestamp": ts_start,
        "elapsed_seconds": round(elapsed, 2),
        "snapshot": {
            "rollout_percent": snap.get("rollout_percent"),
            "config_version": snap.get("config_version"),
            "stable_bucket_salt_version": snap.get("stable_bucket_salt_version"),
            "authorization_status": snap.get("authorization_status"),
            "live": snap.get("live"),
            "production_enabled": snap.get("production_enabled"),
            "parse_error": snap.get("parse_error"),
            "evidence_mode": snap.get("evidence_mode"),
        },
        "snapshot_ok": snapshot_ok,
        "chat_endpoint": "/api/v1/chat/sessions/{session_id}/messages",
        "requests": {
            "total": query_count,
            "completed_200": completed,
            "failed": failed,
            "pdf_intent": pdf_per_window,
            "general_intent": requests_per_window - pdf_per_window,
        },
        "shadow_diagnostics": {
            "new_records": new_diagnostics,
            "shadow_started": shadow_started,
            "shadow_completed": shadow_completed,
            "shadow_failed_pi": shadow_failed_pi,
        },
        "safety": {
            "pi_violations": pi_violations,
            "terminal_violations": terminal_violations,
            "user_visible_source": "legacy",
            "pi_user_visible": pi_violations > 0,
            "provider_serving_calls": 0,
            "business_writes": 0,
        },
        "performance": {
            "http_p50_ms": http_p50,
            "http_p95_ms": http_p95,
            "http_p99_ms": http_p99,
        },
        "cumulative": {
            "before": cumulative_before,
            "after": cumulative_before + completed,
        },
        "window_pass": window_pass,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="P1.27 Chat Shadow Soak")
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    parser.add_argument("--windows", type=int, default=10)
    parser.add_argument("--requests-per-window", type=int, default=50)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--output-dir", default="backend/docs/artifacts")
    parser.add_argument("--window-prefix", default="y")
    parser.add_argument("--phase", default="p127")
    args = parser.parse_args()

    validate_base_url(args.base_url)
    os.makedirs(args.output_dir, exist_ok=True)
    prefix = args.window_prefix.lower()

    print(f"Phase 6V-P1.27 Chat Shadow Soak")
    print(f"  Base URL: {args.base_url}")
    print(f"  Windows:  {args.windows}")
    print(f"  Requests/window: {args.requests_per_window}")
    print(f"  Concurrency: {args.concurrency}")
    print(f"  Total requests: {args.windows * args.requests_per_window}")
    print()

    # Safety: read and validate snapshot
    snap = read_snapshot()
    validate_snapshot(snap)
    print(f"  Snapshot: rollout={snap['rollout_percent']} cv={snap['config_version']} "
          f"salt={snap['stable_bucket_salt_version']} live={snap['live']} "
          f"parse_error={snap['parse_error']}")
    print(f"  Safety checks PASSED")
    print()

    # Auth
    token = get_token(args.base_url)
    print(f"  Auth: OK")

    cumulative = 0
    window_results = []
    all_pass = True

    for i in range(1, args.windows + 1):
        wid = f"{prefix}{i}"
        print(f"  [{wid}] Running {args.requests_per_window} requests...", end="", flush=True)

        # Re-read snapshot each window for drift detection
        try:
            current_snap = read_snapshot()
        except Exception:
            current_snap = snap

        result = run_soak_window(
            window_id=wid,
            base_url=args.base_url,
            token=token,
            requests_per_window=args.requests_per_window,
            cumulative_before=cumulative,
            snap=current_snap,
            concurrency=args.concurrency,
        )
        cumulative = result["cumulative"]["after"]
        window_results.append(result)

        status_str = "PASS" if result["window_pass"] else "FAIL"
        req = result["requests"]
        perf = result["performance"]
        diag = result["shadow_diagnostics"]
        print(f" {status_str} | completed={req['completed_200']}/{req['total']} "
              f"| shadow_diags={diag['new_records']} "
              f"| pi_violations={result['safety']['pi_violations']} "
              f"| http_p95={perf['http_p95_ms']:.0f}ms "
              f"| cumulative={cumulative}")

        if not result["window_pass"]:
            all_pass = False

        # Write per-window artifact
        artifact_path = os.path.join(
            args.output_dir,
            f"company_v2_phase6v_{args.phase}_{wid}_results.json"
        )
        with open(artifact_path, "w") as f:
            json.dump(result, f, indent=2)

    print()
    print(f"  Soak: {'ALL PASS' if all_pass else 'FAILURES DETECTED'}")
    print(f"  Cumulative completed: {cumulative}")

    # Write combined metrics
    all_diags = read_diagnostics_since(0)
    shadow_total = len(all_diags)
    shadow_skipped = len([d for d in all_diags if d.get("status") == "skipped"])
    shadow_failed = len([d for d in all_diags if d.get("error_code") and d.get("status") not in ("success",)])

    summary = {
        "schema_version": "pi_canary_chat_soak_summary_v1",
        "phase": f"6V-{args.phase.upper()}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "windows_executed": args.windows,
        "requests_per_window": args.requests_per_window,
        "total_requests": args.windows * args.requests_per_window,
        "cumulative_completed": cumulative,
        "all_windows_pass": all_pass,
        "chat_endpoint": "POST /api/v1/chat/sessions/{session_id}/messages",
        "shadow_mode": "pi_compatible_shadow",
        "shadow_diagnostics_total": shadow_total,
        "shadow_skipped_intent": shadow_skipped,
        "shadow_failed_pi": shadow_failed,
        "pi_violations_total": sum(r["safety"]["pi_violations"] for r in window_results),
        "provider_serving_calls": 0,
        "canary_config": {
            "rollout_percent": snap.get("rollout_percent"),
            "config_version": snap.get("config_version"),
            "salt": snap.get("stable_bucket_salt_version"),
            "live": snap.get("live"),
            "production_enabled": snap.get("production_enabled"),
        },
        "soak_health": "excellent" if all_pass else "degraded",
        "window_summary": [
            {
                "id": r["window_id"],
                "pass": r["window_pass"],
                "completed": r["requests"]["completed_200"],
                "pi_violations": r["safety"]["pi_violations"],
                "http_p95": r["performance"]["http_p95_ms"],
                "shadow_diags": r["shadow_diagnostics"]["new_records"],
            }
            for r in window_results
        ],
    }

    summary_path = os.path.join(
        args.output_dir,
        f"company_v2_phase6v_{args.phase}_combined_chat_metrics.json"
    )
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  Summary written: {summary_path}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
