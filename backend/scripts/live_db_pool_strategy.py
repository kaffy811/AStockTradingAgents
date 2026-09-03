"""DB pool strategy gate for live shadow acceptance.

The live benchmark must be run only after environment preflight passes. In an
unready environment the artifact records that no strategy has been selected.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ARTIFACT_PATH = Path("backend/docs/artifacts/live_db_pool_strategy.json")
PREFLIGHT_PATH = Path("backend/docs/artifacts/live_environment_preflight.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_strategy(name: str, reason: str) -> dict[str, Any]:
    return {
        "strategy": name,
        "status": "not_run",
        "serial_select_1": {"requested": 20, "executed": 0},
        "concurrent_select_1": {"requested": 20, "executed": 0},
        "sequential_short_transactions": {"requested": 100, "executed": 0},
        "auth_revalidation_calls": {"requested": 10, "executed": 0},
        "rag_metadata_queries": {"requested": 10, "executed": 0},
        "connect_p50_ms": None,
        "connect_p95_ms": None,
        "checkout_p50_ms": None,
        "checkout_p95_ms": None,
        "query_p50_ms": None,
        "query_p95_ms": None,
        "timeout_count": None,
        "cancellation_count": None,
        "checked_out_baseline": None,
        "checked_out_after": None,
        "rollback_storm": None,
        "connection_terminate_error_storm": None,
        "reason": reason,
    }


def build_payload(*, preflight_path: Path = PREFLIGHT_PATH) -> dict[str, Any]:
    preflight: dict[str, Any] = {}
    if preflight_path.exists():
        preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    ready = bool(preflight.get("environment_ready"))
    reason = "PREFLIGHT_NOT_READY" if preflight else "PREFLIGHT_NOT_RUN"
    if ready:
        reason = "LIVE_BENCHMARK_NOT_EXECUTED_BY_THIS_SAFE_RUNNER"
    strategies = [
        _empty_strategy("transaction_pooler_small_queue_pool", reason),
        _empty_strategy("transaction_pooler_null_pool", reason),
    ]
    return {
        "schema_version": "live_db_pool_strategy.v1",
        "generated_at": _now(),
        "environment_ready": ready,
        "database_mode": ((preflight.get("environment") or {}).get("database_mode") or "unknown"),
        "status": "blocked" if not ready else "not_run",
        "selected_strategy": None,
        "selection_reason": None,
        "strategies": strategies,
        "blockers": list(preflight.get("blockers") or [reason]),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight", default=str(PREFLIGHT_PATH))
    parser.add_argument("--out", default=str(ARTIFACT_PATH))
    args = parser.parse_args()
    payload = build_payload(preflight_path=Path(args.preflight))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(out), "status": payload["status"], "selected_strategy": payload["selected_strategy"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
