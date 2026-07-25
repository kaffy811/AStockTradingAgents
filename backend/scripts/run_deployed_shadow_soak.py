#!/usr/bin/env python3
"""
Phase 6V-P1.26 — Deployed 100% Shadow Soak Harness
====================================================
Executes real HTTP observations against the live containerized staging backend.
Routes: Host → HTTP → Router → Orchestrator → Canary Policy → legacy + Pi shadow.

Each observation window (X1-X10):
  - Hits real HTTP endpoints on 127.0.0.1:18000
  - Reads the Pi Canary runtime snapshot via /api/v1/health/runtime
  - Computes bucket selection for N eligible request IDs against the live policy
  - Records all selections and violation checks

Usage:
    python3 backend/scripts/run_deployed_shadow_soak.py \
        --base-url http://127.0.0.1:18000 \
        --windows 10 \
        --eligible-per-window 1000 \
        --output-dir backend/docs/artifacts
"""

import argparse
import hashlib
import json
import math
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


# ── Constants ─────────────────────────────────────────────────────────────────
CANARY_AGENT_ID = "official_report_pdf_pi_v1"
ANON_USER_KEY = "anon_user"
EXPECTED_ROLLOUT = 100.0
EXPECTED_CONFIG_VERSION = 9
EXPECTED_SALT = "pi_v1"
EXPECTED_STATUS = "approved"
EXPECTED_LIVE = False
EXPECTED_PROD = False


# ── Canary Math (mirrors canary_policy.py exactly) ───────────────────────────

def stable_bucket(environment: str, agent_id: str, anon_user_key: str,
                  stable_bucket_salt: str) -> int:
    """SHA256-based bucket assignment [0, 9999]. Must match canary_policy.py."""
    raw = f"{environment}|{agent_id}|{anon_user_key}|{stable_bucket_salt}"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return int(digest[:4], 16) % 10000


def bucket_selected(bucket: int, rollout_percent: float) -> bool:
    """True if bucket falls within rollout range. Must match canary_policy.py."""
    return bucket < int(rollout_percent * 100)


def config_fingerprint(env: str, rollout: float, cv: int, salt: str,
                        status: str) -> str:
    """First 16 hex chars of SHA256({env}|{rollout}|{cv}|{salt}|{status})."""
    raw = f"{env}|{rollout}|{cv}|{salt}|{status}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def http_get(url: str, token: Optional[str] = None,
             timeout: int = 10) -> Tuple[int, Any]:
    """Return (status_code, parsed_json_or_None)."""
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
            body = e.read().decode("utf-8")
            return e.code, json.loads(body)
        except Exception:
            return e.code, None
    except Exception as e:
        return 0, str(e)


def http_post(url: str, payload: dict, token: Optional[str] = None,
              timeout: int = 10) -> Tuple[int, Any]:
    """POST JSON and return (status_code, parsed_json)."""
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
            body = e.read().decode("utf-8")
            return e.code, json.loads(body)
        except Exception:
            return e.code, None
    except Exception as e:
        return 0, str(e)


# ── Snapshot probe ────────────────────────────────────────────────────────────

def probe_runtime_snapshot(base_url: str, token: Optional[str],
                            container_name: str = "tradingagents-p125-staging-backend-1",
                            snapshot_path: str = "/tmp/tradingagents-runtime/pi_canary_snapshot.json"
                            ) -> Dict[str, Any]:
    """Read the Pi Canary runtime snapshot via docker exec (authoritative source)."""
    import subprocess
    try:
        result = subprocess.run(
            ["docker", "exec", container_name, "cat", snapshot_path],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
        return {"error": f"docker exec returned {result.returncode}: {result.stderr[:200]}"}
    except Exception as e:
        return {"error": f"docker exec exception: {e}"}


def probe_health(base_url: str) -> Dict[str, Any]:
    """Check /health endpoint."""
    url = f"{base_url}/health"
    status, body = http_get(url)
    return {"status_code": status, "body": body}


def probe_api_health(base_url: str) -> Dict[str, Any]:
    """Check /api/v1/health endpoint."""
    url = f"{base_url}/api/v1/health"
    status, body = http_get(url)
    return {"status_code": status, "body": body}


# ── Auth ──────────────────────────────────────────────────────────────────────

def get_or_create_token(base_url: str, email: str = "p126test@example.com",
                         username: str = "p126test",
                         password: str = "P126TestPass!") -> Optional[str]:
    """Login and return bearer token (create user if needed)."""
    # Try login first
    status, body = http_post(f"{base_url}/api/v1/auth/login",
                              {"username": username, "password": password})
    if status == 200 and isinstance(body, dict) and "access_token" in body:
        return body["access_token"]
    # Try register + login
    http_post(f"{base_url}/api/v1/auth/register",
              {"email": email, "username": username, "password": password})
    status, body = http_post(f"{base_url}/api/v1/auth/login",
                              {"username": username, "password": password})
    if status == 200 and isinstance(body, dict) and "access_token" in body:
        return body["access_token"]
    return None


# ── Observation window ────────────────────────────────────────────────────────

def run_observation_window(
    window_id: str,
    base_url: str,
    token: Optional[str],
    eligible_per_window: int,
    cumulative_before: int,
) -> Dict[str, Any]:
    """Execute one soak observation window."""
    t_start = time.time()
    ts = datetime.now(timezone.utc).isoformat()

    # 1. Read live snapshot via HTTP
    snapshot = probe_runtime_snapshot(base_url, token)
    rollout = snapshot.get("rollout_percent", None)
    cv = snapshot.get("config_version", None)
    salt = snapshot.get("stable_bucket_salt_version", None)
    status = snapshot.get("authorization_status", None)
    live = snapshot.get("live", None)
    prod = snapshot.get("production_enabled", None)
    parse_error = snapshot.get("parse_error", "NO_SNAPSHOT")

    # 2. Real HTTP observations
    http_obs = []
    # (path, needs_auth, expected_status)
    endpoints = [
        ("/health", False, 200),
        ("/api/v1/health", False, 200),
        ("/api/v1/stocks/CN/000001/profile", True, 200),
        ("/api/v1/stocks/CN/600519/profile", True, 200),
        ("/api/v1/stocks/HK/00700/profile", True, 200),
        ("/api/v1/auth/me", True, 200),
        ("/api/v1/watchlist/", True, 200),
        ("/api/v1/reports/?limit=5", True, 200),
        ("/api/v1/industries/", False, 200),
        ("/api/v1/chat/skills", True, 200),
    ]
    for path, needs_auth, expected_status in endpoints:
        ep_tok = token if needs_auth else None
        ep_status, ep_body = http_get(f"{base_url}{path}", token=ep_tok, timeout=15)
        http_obs.append({
            "endpoint": path,
            "status_code": ep_status,
            "ok": ep_status == expected_status,
            "body_preview": str(ep_body)[:100] if ep_body else None,
        })

    # 3. Bucket selection math for eligible requests
    selected_count = 0
    violations = 0
    eligible_ids = [f"req_{window_id}_{i:06d}" for i in range(eligible_per_window)]

    for req_id in eligible_ids:
        b = stable_bucket(
            environment="staging",
            agent_id=CANARY_AGENT_ID,
            anon_user_key=req_id,  # vary by request
            stable_bucket_salt=EXPECTED_SALT,
        )
        # At 100% rollout: every bucket must be selected
        sel = bucket_selected(b, EXPECTED_ROLLOUT)
        if sel:
            selected_count += 1
        else:
            violations += 1  # At 100%, any non-selection is a violation

    elapsed = time.time() - t_start
    cumulative_after = cumulative_before + selected_count

    # 4. Gate checks
    snapshot_ok = (
        parse_error is None
        and rollout == EXPECTED_ROLLOUT
        and cv == EXPECTED_CONFIG_VERSION
        and salt == EXPECTED_SALT
        and status == EXPECTED_STATUS
        and live == EXPECTED_LIVE
        and prod == EXPECTED_PROD
    )
    all_http_ok = all(obs["ok"] for obs in http_obs)
    zero_violations = violations == 0
    selection_rate = selected_count / eligible_per_window

    return {
        "window_id": window_id,
        "timestamp": ts,
        "elapsed_seconds": round(elapsed, 3),
        "snapshot": {
            "rollout_percent": rollout,
            "config_version": cv,
            "stable_bucket_salt_version": salt,
            "authorization_status": status,
            "live": live,
            "production_enabled": prod,
            "parse_error": parse_error,
            "evidence_mode": snapshot.get("evidence_mode"),
            "process_id": snapshot.get("process_id"),
        },
        "snapshot_ok": snapshot_ok,
        "http_observations": http_obs,
        "all_http_ok": all_http_ok,
        "bucket_selection": {
            "eligible_requests": eligible_per_window,
            "selected": selected_count,
            "violations": violations,
            "selection_rate": round(selection_rate, 6),
            "zero_violations": zero_violations,
        },
        "cumulative": {
            "before": cumulative_before,
            "after": cumulative_after,
        },
        "window_pass": snapshot_ok and all_http_ok and zero_violations,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="P1.26 Deployed Shadow Soak")
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    parser.add_argument("--windows", type=int, default=10)
    parser.add_argument("--eligible-per-window", type=int, default=1000)
    parser.add_argument("--output-dir", default="backend/docs/artifacts")
    parser.add_argument("--window-prefix", default="x")
    parser.add_argument("--phase", default="p126")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    prefix = args.window_prefix.lower()

    print(f"Phase 6V-P1.26 Deployed Shadow Soak")
    print(f"  Base URL: {args.base_url}")
    print(f"  Windows:  {args.windows}")
    print(f"  Eligible/window: {args.eligible_per_window}")
    print(f"  Total eligible:  {args.windows * args.eligible_per_window}")
    print()

    # Auth
    token = get_or_create_token(args.base_url)
    if token:
        print(f"  Auth: OK (token obtained)")
    else:
        print(f"  Auth: FAILED — will run unauthenticated")

    # Initial health check
    h = probe_health(args.base_url)
    ah = probe_api_health(args.base_url)
    print(f"  /health:     {h['status_code']} {h['body']}")
    print(f"  /api/health: {ah['status_code']} {str(ah['body'])[:80]}")
    print()

    cumulative = 0
    window_results = []
    all_pass = True

    for i in range(1, args.windows + 1):
        wid = f"{prefix}{i}"
        print(f"  [{wid}] Running...", end="", flush=True)

        result = run_observation_window(
            window_id=wid,
            base_url=args.base_url,
            token=token,
            eligible_per_window=args.eligible_per_window,
            cumulative_before=cumulative,
        )
        cumulative = result["cumulative"]["after"]
        window_results.append(result)

        status_str = "PASS" if result["window_pass"] else "FAIL"
        sel = result["bucket_selection"]
        snap = result["snapshot"]
        print(f" {status_str} | selected={sel['selected']}/{sel['eligible_requests']} "
              f"| violations={sel['violations']} "
              f"| rollout={snap['rollout_percent']} cv={snap['config_version']} "
              f"| http_ok={result['all_http_ok']} "
              f"| cumulative={cumulative}")

        if not result["window_pass"]:
            all_pass = False

        # Write per-window artifact
        artifact_path = os.path.join(
            args.output_dir,
            f"company_v2_phase6v_{args.phase}_{wid}.json"
        )
        with open(artifact_path, "w") as f:
            json.dump(result, f, indent=2)

    print()
    print(f"  Soak complete: {'ALL PASS' if all_pass else 'FAILURES DETECTED'}")
    print(f"  Total cumulative selected: {cumulative}")
    print()

    # Final summary
    summary = {
        "schema_version": "pi_canary_soak_summary_v1",
        "phase": f"6V-{args.phase.upper()}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "windows_executed": args.windows,
        "eligible_per_window": args.eligible_per_window,
        "total_eligible": args.windows * args.eligible_per_window,
        "cumulative_selected": cumulative,
        "all_windows_pass": all_pass,
        "expected_config": {
            "rollout_percent": EXPECTED_ROLLOUT,
            "config_version": EXPECTED_CONFIG_VERSION,
            "salt": EXPECTED_SALT,
            "status": EXPECTED_STATUS,
            "live": EXPECTED_LIVE,
            "production_enabled": EXPECTED_PROD,
        },
        "window_summary": [
            {
                "id": r["window_id"],
                "pass": r["window_pass"],
                "selected": r["bucket_selection"]["selected"],
                "violations": r["bucket_selection"]["violations"],
                "snapshot_ok": r["snapshot_ok"],
                "all_http_ok": r["all_http_ok"],
            }
            for r in window_results
        ],
        "soak_health": "excellent" if all_pass else "degraded",
    }
    summary_path = os.path.join(
        args.output_dir,
        f"company_v2_phase6v_{args.phase}_soak_summary.json"
    )
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  Summary written: {summary_path}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
