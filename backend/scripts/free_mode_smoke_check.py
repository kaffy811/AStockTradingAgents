#!/usr/bin/env python3
"""
scripts/free_mode_smoke_check.py — Free-mode production smoke check.

Verifies that the core free-mode data pipeline is functional for a set
of known-good A-share stocks.

Usage:
    uv run python scripts/free_mode_smoke_check.py
    uv run python scripts/free_mode_smoke_check.py --base-url http://localhost:8000
    uv run python scripts/free_mode_smoke_check.py --dry-run

Exit codes:
    0 — all checks passed
    1 — one or more checks failed
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx", file=sys.stderr)
    sys.exit(1)

# ── Test stock set ─────────────────────────────────────────────────────────────

SMOKE_STOCKS = [
    {"code": "600519", "name": "贵州茅台", "market": "CN"},
    {"code": "000725", "name": "京东方A", "market": "CN"},
    {"code": "600186", "name": "荷美尔", "market": "CN"},
]

# ── Checks ────────────────────────────────────────────────────────────────────


def check_health(client: httpx.Client, base_url: str) -> dict:
    """GET /api/v1/health"""
    try:
        r = client.get(f"{base_url}/api/v1/health", timeout=10)
        r.raise_for_status()
        body = r.json()
        ok = body.get("status") == "ok"
        return {"check": "health", "passed": ok, "status": body.get("status"), "db": body.get("db_status"), "redis": body.get("redis_status")}
    except Exception as exc:
        return {"check": "health", "passed": False, "error": str(exc)}


def check_deep_health(client: httpx.Client, base_url: str) -> dict:
    """GET /api/v1/health/deep"""
    try:
        r = client.get(f"{base_url}/api/v1/health/deep", timeout=15)
        r.raise_for_status()
        body = r.json()
        postgres_ok = body.get("checks", {}).get("postgres", {}).get("status") == "ok"
        return {
            "check": "health_deep",
            "passed": postgres_ok,
            "overall": body.get("status"),
            "postgres": body.get("checks", {}).get("postgres", {}).get("status"),
            "redis": body.get("checks", {}).get("redis", {}).get("status"),
            "pgvector": body.get("checks", {}).get("pgvector", {}).get("status"),
            "embedding_provider": body.get("checks", {}).get("embedding_provider", {}).get("status"),
        }
    except Exception as exc:
        return {"check": "health_deep", "passed": False, "error": str(exc)}


def check_fundamentals(client: httpx.Client, base_url: str, code: str, name: str) -> dict:
    """GET /api/v1/stock/{code}/modules — check that fundamentals load."""
    url = f"{base_url}/api/v1/stock/{code}/modules"
    try:
        r = client.get(url, timeout=20)
        body = r.json()
        partial = body.get("partial", True)
        module_count = len(body.get("modules", []))
        passed = r.status_code == 200 and module_count > 0
        return {
            "check": f"fundamentals_{code}",
            "stock": name,
            "passed": passed,
            "http_status": r.status_code,
            "module_count": module_count,
            "partial": partial,
        }
    except Exception as exc:
        return {"check": f"fundamentals_{code}", "stock": name, "passed": False, "error": str(exc)}


def check_report_chat(client: httpx.Client, base_url: str, code: str, name: str, dry_run: bool) -> dict:
    """POST /api/v1/stock/{code}/report-chat — very short question."""
    if dry_run:
        return {"check": f"report_chat_{code}", "stock": name, "passed": True, "note": "dry-run skipped"}
    url = f"{base_url}/api/v1/stock/{code}/report-chat"
    payload = {
        "question": "公司主营业务是什么？",
        "report_types": ["annual"],
        "years": [2023],
        "top_k": 3,
        "use_memory": False,
    }
    try:
        r = client.post(url, json=payload, timeout=60)
        body = r.json()
        has_answer = bool(body.get("answer"))
        error_code = body.get("error_code")
        # REPORT_RAG_NOT_READY is acceptable if no index exists for this stock
        passed = has_answer or error_code in ("REPORT_RAG_NOT_READY", "REPORT_CHAT_NO_EVIDENCE")
        return {
            "check": f"report_chat_{code}",
            "stock": name,
            "passed": passed,
            "http_status": r.status_code,
            "has_answer": has_answer,
            "error_code": error_code,
            "cache_hit": body.get("cache_meta", {}).get("hit"),
        }
    except Exception as exc:
        return {"check": f"report_chat_{code}", "stock": name, "passed": False, "error": str(exc)}


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Free-mode smoke check")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--dry-run", action="store_true", help="Skip LLM-backed checks")
    parser.add_argument(
        "--symbols",
        help="Comma-separated stock codes to test, e.g. 600519,000725,600186 (overrides default set)",
    )
    parser.add_argument("--json", dest="output_json", action="store_true", help="Output JSON summary")
    args = parser.parse_args()

    # Build stock list from --symbols or default
    if args.symbols:
        stocks = [{"code": c.strip(), "name": c.strip(), "market": "CN"} for c in args.symbols.split(",") if c.strip()]
    else:
        stocks = SMOKE_STOCKS

    started_at = datetime.utcnow().isoformat()
    results: list[dict] = []

    print(f"[smoke] Free-mode smoke check  base_url={args.base_url}  dry_run={args.dry_run}")
    print(f"[smoke] Started at {started_at} UTC")
    print()

    with httpx.Client() as client:
        for fn, label in [
            (lambda: check_health(client, args.base_url), "health"),
            (lambda: check_deep_health(client, args.base_url), "health/deep"),
        ]:
            r = fn()
            results.append(r)
            icon = "✓" if r["passed"] else "✗"
            print(f"  [{icon}] {label}: {r}")

        print()
        for stock in stocks:
            r = check_fundamentals(client, args.base_url, stock["code"], stock["name"])
            results.append(r)
            icon = "✓" if r["passed"] else "✗"
            print(f"  [{icon}] fundamentals/{stock['code']}: {r}")

        print()
        for stock in stocks[:1]:  # Only first stock for report-chat to avoid rate limits
            r = check_report_chat(client, args.base_url, stock["code"], stock["name"], args.dry_run)
            results.append(r)
            icon = "✓" if r["passed"] else "✗"
            print(f"  [{icon}] report-chat/{stock['code']}: {r}")

    passed = sum(1 for r in results if r["passed"])
    failed = len(results) - passed

    summary = {
        "started_at": started_at,
        "base_url": args.base_url,
        "dry_run": args.dry_run,
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "results": results,
    }

    print()
    print(f"[smoke] Result: {passed}/{len(results)} passed, {failed} failed")

    if args.output_json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
