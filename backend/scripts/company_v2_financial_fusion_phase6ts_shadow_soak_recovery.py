"""Audit and optional recovery for Phase 6T-S shadow soak claim scope violations."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select, update

from app.core.database import AsyncSessionLocal
from app.models.company_v2_financial_fusion_job import CompanyV2FinancialFusionJob


DEFAULT_SCOPE = "phase6ts_shadow_soak"
DEFAULT_WORKER_PREFIX = "phase6ts-worker-"


@dataclass
class RecoveryResult:
    status: str = "passed"
    run_id: str | None = None
    scope: str = DEFAULT_SCOPE
    worker_prefix: str = DEFAULT_WORKER_PREFIX
    known_job_ids: list[str] = field(default_factory=list)
    matched_jobs: list[dict[str, Any]] = field(default_factory=list)
    released_job_ids: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)


def _metadata_run_id(metadata_json: str | None) -> str | None:
    if not metadata_json:
        return None
    try:
        payload = json.loads(metadata_json)
    except Exception:  # noqa: BLE001
        return None
    if isinstance(payload, dict) and payload.get("run_id"):
        return str(payload["run_id"])
    return None


async def run_recovery(args: argparse.Namespace) -> dict[str, Any]:
    result = RecoveryResult(run_id=args.run_id, scope=args.scope, worker_prefix=args.worker_prefix, known_job_ids=args.known_job_ids or [])
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(CompanyV2FinancialFusionJob).where(
                    CompanyV2FinancialFusionJob.requester_scope == args.scope,
                    CompanyV2FinancialFusionJob.claimed_by.like(f"{args.worker_prefix}%"),
                )
            )
        ).scalars().all()
        for row in rows:
            metadata_run_id = _metadata_run_id(row.requester_metadata_json)
            matched = {
                "job_id": row.job_id,
                "symbol": row.symbol,
                "report_id": row.report_id,
                "claimed_by": row.claimed_by,
                "attempt_count": int(row.attempt_count or 0),
                "lease_expires_at": row.lease_expires_at.isoformat() if row.lease_expires_at else None,
                "requester_scope": row.requester_scope,
                "requester_run_id": metadata_run_id,
            }
            if args.run_id and metadata_run_id != args.run_id:
                matched["match"] = False
                result.matched_jobs.append(matched)
                continue
            if result.known_job_ids and row.job_id not in set(result.known_job_ids):
                matched["match"] = False
                result.matched_jobs.append(matched)
                continue
            matched["match"] = True
            result.matched_jobs.append(matched)
            if args.release_known_claims:
                await db.execute(
                    update(CompanyV2FinancialFusionJob)
                    .where(
                        CompanyV2FinancialFusionJob.job_id == row.job_id,
                        CompanyV2FinancialFusionJob.claimed_by == row.claimed_by,
                        CompanyV2FinancialFusionJob.requester_scope == args.scope,
                    )
                    .values(
                        claimed_by=None,
                        claimed_at=None,
                        heartbeat_at=None,
                        lease_expires_at=None,
                        last_error_message_sanitized="phase6ts recovery release",
                        attempt_count=max(0, int(row.attempt_count or 0) - 1),
                    )
                )
                result.released_job_ids.append(row.job_id)
        if args.release_known_claims and result.released_job_ids:
            await db.commit()
    return asdict(result)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--scope", default=DEFAULT_SCOPE)
    parser.add_argument("--worker-prefix", default=DEFAULT_WORKER_PREFIX)
    parser.add_argument("--known-job-ids", default=None)
    parser.add_argument("--release-known-claims", action="store_true")
    parser.add_argument("--out-json", default=None)
    parser.add_argument("--out-md", default=None)
    return parser.parse_args(argv)


def _write_artifacts(payload: dict[str, Any], *, out_json: str | None, out_md: str | None) -> None:
    if out_json:
        Path(out_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if out_md:
        Path(out_md).write_text("# Phase 6T-S Recovery\n\n```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.known_job_ids:
        args.known_job_ids = [item.strip() for item in args.known_job_ids.split(",") if item.strip()]
    payload = asyncio.run(run_recovery(args))
    _write_artifacts(payload, out_json=args.out_json, out_md=args.out_md)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
