"""Write live external pytest result artifact for Phase 6U-E1.3."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ARTIFACT_PATH = Path("backend/docs/artifacts/live_external_test_results.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    if args.live_external_failed:
        failures.append({
            "suite": "integration_live_or_live_external",
            "count": args.live_external_failed,
            "classification": args.live_external_failure_classification,
            "reason": args.live_external_reason,
        })
    if args.soak_failed:
        failures.append({
            "suite": "soak",
            "count": args.soak_failed,
            "classification": args.soak_failure_classification,
            "reason": args.soak_reason,
        })
    return {
        "schema_version": "live_external_test_results.v1",
        "generated_at": _now(),
        "environment": {
            "environment_id": args.environment_id,
            "region": args.region,
            "external_environment": args.external_environment,
        },
        "suites": {
            "integration_live_or_live_external": {
                "command": "pytest -q -m \"integration_live or live_external\"",
                "status": args.live_external_status,
                "passed": args.live_external_passed,
                "skipped": args.live_external_skipped,
                "failed": args.live_external_failed,
                "duration_seconds": args.live_external_duration_seconds,
                "reason": args.live_external_reason,
            },
            "soak": {
                "command": "pytest -q -m soak",
                "status": args.soak_status,
                "passed": args.soak_passed,
                "skipped": args.soak_skipped,
                "failed": args.soak_failed,
                "duration_seconds": args.soak_duration_seconds,
                "reason": args.soak_reason,
            },
        },
        "failures": failures,
        "passed": args.live_external_status == "passed" and args.soak_status == "passed",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ARTIFACT_PATH))
    parser.add_argument("--environment-id", default="local_unverified")
    parser.add_argument("--region", default="unknown")
    parser.add_argument("--external-environment", default="current_local_environment")
    parser.add_argument("--live-external-status", default="not_run")
    parser.add_argument("--live-external-passed", type=int)
    parser.add_argument("--live-external-skipped", type=int)
    parser.add_argument("--live-external-failed", type=int)
    parser.add_argument("--live-external-duration-seconds", type=float)
    parser.add_argument("--live-external-reason")
    parser.add_argument("--live-external-failure-classification", default="environment")
    parser.add_argument("--soak-status", default="not_run")
    parser.add_argument("--soak-passed", type=int)
    parser.add_argument("--soak-skipped", type=int)
    parser.add_argument("--soak-failed", type=int)
    parser.add_argument("--soak-duration-seconds", type=float)
    parser.add_argument("--soak-reason")
    parser.add_argument("--soak-failure-classification", default="environment")
    args = parser.parse_args()
    payload = build_payload(args)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(out), "passed": payload["passed"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
