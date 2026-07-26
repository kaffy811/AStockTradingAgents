"""SecurityMaster live sampling gate for Phase 6U-E1.3."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ARTIFACT_PATH = Path("backend/docs/artifacts/security_entity_live_sampling.json")
PREFLIGHT_PATH = Path("backend/docs/artifacts/live_environment_preflight.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_payload(*, preflight_path: Path = PREFLIGHT_PATH) -> dict[str, Any]:
    preflight: dict[str, Any] = {}
    if preflight_path.exists():
        preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    ready = bool(preflight.get("environment_ready"))
    reason = "PREFLIGHT_NOT_READY" if preflight else "PREFLIGHT_NOT_RUN"
    markets = {
        "CN": {
            "requested_active_full_scan": 5166,
            "executed_active_full_scan": 0,
            "requested_stratified_sample": {
                "sse_main": 20,
                "szse_main": 20,
                "chinext": 20,
                "star": 20,
                "bse": 10,
                "st": 10,
                "former_name_or_alias": 10,
                "ambiguous_name_groups": 10,
            },
            "executed_stratified_sample": 0,
        },
        "HK": {"requested_active_full_scan": 30, "executed_active_full_scan": 0},
        "US": {"requested_active_full_scan": 0, "executed_active_full_scan": 0, "reason": "current local SecurityMaster US coverage is 0"},
    }
    return {
        "schema_version": "security_entity_live_sampling.v1",
        "generated_at": _now(),
        "status": "blocked" if not ready else "not_run",
        "environment_ready": ready,
        "markets": markets,
        "checks": {
            "code_resolution": {"executed": 0, "passed": None},
            "short_name_resolution": {"executed": 0, "passed": None},
            "full_name_resolution": {"executed": 0, "passed": None},
            "continuous_chinese_query": {"executed": 0, "passed": None},
            "market_isolation": {"executed": 0, "passed": None},
            "hardcode_scan": {"executed": 0, "passed": None},
            "ambiguity_behavior": {"executed": 0, "passed": None},
        },
        "success_rate": None,
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
    print(json.dumps({"artifact": str(out), "status": payload["status"], "success_rate": payload["success_rate"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
