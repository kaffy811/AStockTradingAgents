"""Durable shadow worker CLI for Company V2 financial fusion."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.company_v2_financial_fusion_job import CompanyV2FinancialFusionJob
from app.services.company_v2_financial_fusion_worker_service import (
    SHADOW_EXECUTION_MODE,
    company_v2_financial_fusion_worker_service,
)

ARTIFACT_DIR = ROOT / "docs" / "artifacts"


def _sanitize(value):
    if isinstance(value, dict):
        return {k: _sanitize(v) for k, v in value.items() if k not in {"database_url", "password", "token", "traceback", "stack", "local_path", "path", "sidecar_path"}}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, str) and (value.startswith("/Users/") or value.startswith("/private/") or value.startswith("/tmp/")):
        return "[redacted]"
    return value


async def _count_active_leases() -> int:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(CompanyV2FinancialFusionJob).where(
                CompanyV2FinancialFusionJob.claimed_by.is_not(None),
                CompanyV2FinancialFusionJob.status == "queued",
            )
        )
        return len(list(result.scalars().all()))


async def run_worker(args: argparse.Namespace) -> dict[str, object]:
    mode = (args.mode or SHADOW_EXECUTION_MODE).lower()
    stage3_authorized = bool(getattr(settings, "company_v2_financial_fusion_stage3_authorized", False))
    worker_enabled = bool(getattr(settings, "company_v2_financial_fusion_worker_enabled", False))
    auto_run = bool(getattr(settings, "company_v2_financial_fusion_auto_run", False))
    rollout_percent = int(getattr(settings, "company_v2_financial_fusion_rollout_percent", 0) or 0)

    payload: dict[str, object] = {
        "phase": "phase6tr_shadow_worker",
        "status": "failed",
        "mode": mode,
        "worker_id": args.worker_id,
        "worker_enabled": worker_enabled,
        "stage3_authorized": stage3_authorized,
        "auto_run": auto_run,
        "rollout_percent": rollout_percent,
        "real_execution_count": 0,
        "claimed_jobs": [],
        "observations": [],
        "active_leases_after": None,
        "errors": [],
    }

    if mode != SHADOW_EXECUTION_MODE:
        payload["errors"].append({"code": "STAGE3_NOT_AUTHORIZED", "message": "only shadow mode is allowed in this phase"})
        return payload

    async with AsyncSessionLocal() as db:
        if not worker_enabled and not args.once:
            payload["errors"].append({"code": "WORKER_DISABLED", "message": "worker is disabled; run shadow once explicitly to audit queued jobs"})
            return payload
        try:
            claimed_jobs = []
            observations = []
            shadow_mode_verified = True
            real_execution_count = 0
            for _ in range(max(1, int(args.max_jobs))):
                cycle = await company_v2_financial_fusion_worker_service.run_shadow_cycle(
                    db=db,
                    worker_id=args.worker_id,
                    lease_seconds=args.lease_seconds,
                    heartbeat_seconds=args.heartbeat_seconds,
                    max_jobs=args.max_jobs,
                )
                claimed_jobs.extend(cycle["claimed_jobs"])
                observations.extend(cycle["observations"])
                real_execution_count += int(cycle.get("real_execution_count") or 0)
                shadow_mode_verified = shadow_mode_verified and bool(cycle.get("shadow_mode_verified"))
                payload["stage3_authorized"] = bool(cycle.get("stage3_authorized"))
                payload["auto_run"] = bool(cycle.get("auto_run"))
                payload["rollout_percent"] = int(cycle.get("rollout_percent") or 0)
                if args.once or not cycle["claimed_jobs"]:
                    break
                await asyncio.sleep(max(0.0, float(args.poll_interval)))
            payload["claimed_jobs"] = _sanitize(claimed_jobs)
            payload["observations"] = _sanitize(observations)
            payload["real_execution_count"] = real_execution_count
            payload["shadow_mode_verified"] = shadow_mode_verified
            payload["status"] = "passed"
        except Exception as exc:  # noqa: BLE001
            payload["errors"].append({"code": "INTERNAL_ERROR", "message": str(exc)})
            return payload

    payload["active_leases_after"] = await _count_active_leases()
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="shadow", choices=["shadow", "disabled", "canary", "rollout"])
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--worker-id", default="phase6tr-worker")
    parser.add_argument("--lease-seconds", type=int, default=60)
    parser.add_argument("--heartbeat-seconds", type=int, default=15)
    parser.add_argument("--max-jobs", type=int, default=5)
    parser.add_argument("--out-json", default=str(ARTIFACT_DIR / "company_v2_phase6tr_shadow_worker.json"))
    parser.add_argument("--out-md", default=str(ARTIFACT_DIR / "company_v2_phase6tr_shadow_worker.md"))
    return parser.parse_args(argv)


def _write_artifacts(payload: dict[str, object], *, out_json: str, out_md: str) -> None:
    sanitized = _sanitize(payload)
    Path(out_json).write_text(json.dumps(sanitized, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(out_md).write_text("# Phase 6T-R Shadow Worker\n\n```json\n" + json.dumps(sanitized, ensure_ascii=False, indent=2) + "\n```\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = asyncio.run(run_worker(args))
    _write_artifacts(payload, out_json=args.out_json, out_md=args.out_md)
    print(json.dumps({"status": payload["status"], "real_execution_count": payload["real_execution_count"]}, ensure_ascii=False))
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
