#!/usr/bin/env python3
"""
scripts/check_data_sources.py — Data source availability check.

Performs lightweight, low-frequency checks on all configured data sources.
Does NOT make bulk requests or modify any data.

Usage:
    uv run python scripts/check_data_sources.py
    uv run python scripts/check_data_sources.py --json

Exit codes:
    0 — all required sources are available
    1 — one or more required sources unavailable
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

REQUIRED_FREE_MODE = ["baostock", "akshare"]
OPTIONAL_SOURCES = ["tushare"]
REPORT_DOMAINS = [
    "static.cninfo.com.cn",
    "www.sse.com.cn",
    "disclosure.szse.cn",
]


def check_import(module_name: str) -> dict:
    try:
        mod = importlib.import_module(module_name)
        version = getattr(mod, "__version__", "unknown")
        return {"source": module_name, "status": "available", "version": version}
    except ImportError as exc:
        return {"source": module_name, "status": "unavailable", "reason": str(exc)}


def check_baostock_login() -> dict:
    """Attempt a BaoStock login + minimal query (no data-intensive calls)."""
    try:
        import baostock as bs
        lg = bs.login()
        if lg.error_code != "0":
            bs.logout()
            return {"source": "baostock_login", "status": "error", "reason": f"error_code={lg.error_code}"}
        bs.logout()
        return {"source": "baostock_login", "status": "ok"}
    except Exception as exc:
        return {"source": "baostock_login", "status": "error", "reason": f"{type(exc).__name__}: {exc}"}


def check_akshare_callable() -> dict:
    """Verify AkShare's stock_zh_a_spot_em function is callable (no network call)."""
    try:
        import akshare as ak
        fn = getattr(ak, "stock_zh_a_spot_em", None)
        if fn is None:
            return {"source": "akshare_callable", "status": "error", "reason": "stock_zh_a_spot_em not found"}
        return {"source": "akshare_callable", "status": "ok", "version": getattr(ak, "__version__", "unknown")}
    except Exception as exc:
        return {"source": "akshare_callable", "status": "error", "reason": f"{type(exc).__name__}: {exc}"}


def check_report_domains() -> list[dict]:
    """Check that configured PDF report domains are not blocked by DNS (no download)."""
    results = []
    try:
        import socket
        for domain in REPORT_DOMAINS:
            try:
                socket.gethostbyname(domain)
                results.append({"source": f"domain_{domain}", "status": "resolvable"})
            except socket.gaierror:
                results.append({"source": f"domain_{domain}", "status": "dns_failed", "reason": "DNS resolution failed"})
    except Exception as exc:
        results.append({"source": "domain_check", "status": "error", "reason": str(exc)})
    return results


def check_embedding_model() -> dict:
    """Check if the local embedding model is importable."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from app.core.config import settings
        provider = settings.report_embedding_provider
        if provider == "local":
            try:
                importlib.import_module("sentence_transformers")
                model = settings.report_embedding_model or "BAAI/bge-small-zh-v1.5"
                return {"source": "embedding_local", "status": "ok", "model": model, "dim": settings.report_embedding_dim}
            except ImportError:
                return {"source": "embedding_local", "status": "unavailable", "reason": "sentence_transformers not installed"}
        return {"source": "embedding_provider", "status": "ok", "provider": provider}
    except Exception as exc:
        return {"source": "embedding_model", "status": "error", "reason": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Check data source availability")
    parser.add_argument("--json", dest="output_json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    checks: list[dict] = []

    print("[data-sources] Checking library imports...")
    for mod in REQUIRED_FREE_MODE + OPTIONAL_SOURCES:
        r = check_import(mod)
        checks.append(r)
        icon = "✓" if r["status"] == "available" else "✗"
        print(f"  [{icon}] {mod}: {r['status']}  {r.get('version','')}")

    print()
    print("[data-sources] Checking BaoStock login...")
    r = check_baostock_login()
    checks.append(r)
    icon = "✓" if r["status"] == "ok" else "✗"
    print(f"  [{icon}] baostock_login: {r['status']}  {r.get('reason','')}")

    print()
    print("[data-sources] Checking AkShare callability...")
    r = check_akshare_callable()
    checks.append(r)
    icon = "✓" if r["status"] == "ok" else "✗"
    print(f"  [{icon}] akshare_callable: {r['status']}  {r.get('reason','')}")

    print()
    print("[data-sources] Checking report PDF domains (DNS)...")
    domain_results = check_report_domains()
    checks.extend(domain_results)
    for r in domain_results:
        icon = "✓" if r["status"] == "resolvable" else "✗"
        print(f"  [{icon}] {r['source']}: {r['status']}")

    print()
    print("[data-sources] Checking embedding provider...")
    r = check_embedding_model()
    checks.append(r)
    icon = "✓" if r["status"] == "ok" else "✗"
    print(f"  [{icon}] {r['source']}: {r['status']}  {r.get('reason','')}")

    # Required free-mode sources must be available
    required_ok = all(
        r["status"] in ("available", "ok", "resolvable")
        for r in checks
        if r["source"] in REQUIRED_FREE_MODE
    )

    summary = {
        "timestamp": datetime.utcnow().isoformat(),
        "required_ok": required_ok,
        "checks": checks,
    }

    print()
    print(f"[data-sources] Required sources {'OK' if required_ok else 'FAILED'}")

    if args.output_json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))

    return 0 if required_ok else 1


if __name__ == "__main__":
    sys.exit(main())
