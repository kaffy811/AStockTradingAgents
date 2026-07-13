"""Phase 6T-S shadow soak runner for Company V2 financial fusion."""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import math
import sys
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, select

from app.core.config import settings
from app.core.database import AsyncSessionLocal, async_engine
from app.models.company_v2_financial_fusion_job import CompanyV2FinancialFusionJob
from app.models.company_v2_financial_fusion_worker_observation import CompanyV2FinancialFusionWorkerObservation
from app.models.report_document import ReportDocument
from app.services.company_v2_financial_fusion_job_service import company_v2_financial_fusion_job_service
from app.services.company_v2_financial_fusion_worker_service import company_v2_financial_fusion_worker_service


DEFAULT_SYMBOLS = ["601686", "600519", "300750", "000725", "000001"]
DEFAULT_DURATION_SECONDS = 7200
DEFAULT_WORKER_COUNT = 2
DEFAULT_POLL_INTERVAL_SECONDS = 5
DEFAULT_LEASE_SECONDS = 60
DEFAULT_HEARTBEAT_SECONDS = 15
DEFAULT_MAX_JOBS_PER_CYCLE = 5
DEFAULT_SAMPLE_INTERVAL_SECONDS = 30
DEFAULT_BASE_ARTIFACT_DIR = ROOT / "docs" / "artifacts"
JOB_SCOPE = "phase6ts_shadow_soak"
WORKER_VERSION = "phase6ts-shadow-soak-v1"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        blocked = {"database_url", "password", "token", "traceback", "stack", "local_path", "path", "sidecar_path"}
        return {k: _sanitize(v) for k, v in value.items() if k not in blocked}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, str) and (value.startswith("/Users/") or value.startswith("/private/") or value.startswith("/tmp/")):
        return "[redacted]"
    return value


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    rank = (len(ordered) - 1) * (p / 100.0)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return round(ordered[int(rank)], 3)
    lower_value = ordered[lower]
    upper_value = ordered[upper]
    return round(lower_value + (upper_value - lower_value) * (rank - lower), 3)


@dataclass
class SoakMetrics:
    duration_seconds: int
    worker_count: int
    worker_ids: list[str] = field(default_factory=list)
    jobs_created: int = 0
    jobs_observed: int = 0
    unique_jobs_claimed: set[str] = field(default_factory=set)
    claimed_jobs: list[str] = field(default_factory=list)
    claim_events: list[float] = field(default_factory=list)
    loop_events: list[float] = field(default_factory=list)
    heartbeat_events: list[float] = field(default_factory=list)
    lease_renewal_failures: int = 0
    heartbeat_failures: int = 0
    duplicate_claim_count: int = 0
    simultaneous_claim_conflicts: int = 0
    observation_rows_written: int = 0
    active_leases_peak: int = 0
    active_leases_end: int | None = None
    stale_leases_end: int | None = None
    worker_restart_count: int = 0
    db_disconnect_count: int = 0
    db_reconnect_count: int = 0
    unrecovered_worker_failures: int = 0
    real_execution_count: int = 0
    provider_call_count: int = 0
    rag_query_count: int = 0
    extractor_call_count: int = 0
    fusion_result_write_count: int = 0
    unknown_jobs_modified: int = 0
    jobs_cancelled: int = 0
    cleanup_cancelled_job_ids: list[str] = field(default_factory=list)
    preexisting_active_jobs_found: int = 0
    preexisting_active_jobs_cancelled: int = 0
    created_job_ids: list[str] = field(default_factory=list)
    observed_job_ids: list[str] = field(default_factory=list)
    claimed_job_ids: list[str] = field(default_factory=list)
    worker_restart_events: list[dict[str, Any]] = field(default_factory=list)
    db_reconnect_events: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def record_loop(self, ms: float) -> None:
        self.loop_events.append(ms)

    def record_claim(self, job_id: str, ms: float, active_claims: set[str]) -> None:
        self.claim_events.append(ms)
        self.unique_jobs_claimed.add(job_id)
        self.claimed_job_ids.append(job_id)
        if job_id in active_claims:
            self.duplicate_claim_count += 1
            self.simultaneous_claim_conflicts += 1
        active_claims.add(job_id)
        self.active_leases_peak = max(self.active_leases_peak, len(active_claims))

    def record_release(self, job_id: str, active_claims: set[str]) -> None:
        active_claims.discard(job_id)

    def as_dict(self) -> dict[str, Any]:
        return {
            "duration_seconds": self.duration_seconds,
            "worker_count": self.worker_count,
            "worker_ids": self.worker_ids,
            "jobs_created": self.jobs_created,
            "jobs_observed": self.jobs_observed,
            "unique_jobs_claimed": len(self.unique_jobs_claimed),
            "duplicate_claim_count": self.duplicate_claim_count,
            "simultaneous_claim_conflicts": self.simultaneous_claim_conflicts,
            "observation_rows_written": self.observation_rows_written,
            "active_leases_peak": self.active_leases_peak,
            "active_leases_end": self.active_leases_end,
            "stale_leases_end": self.stale_leases_end,
            "heartbeat_failures": self.heartbeat_failures,
            "lease_renewal_failures": self.lease_renewal_failures,
            "db_disconnect_count": self.db_disconnect_count,
            "db_reconnect_count": self.db_reconnect_count,
            "worker_restart_count": self.worker_restart_count,
            "loop_p50_ms": percentile(self.loop_events, 50),
            "loop_p95_ms": percentile(self.loop_events, 95),
            "claim_p50_ms": percentile(self.claim_events, 50),
            "claim_p95_ms": percentile(self.claim_events, 95),
            "real_execution_count": self.real_execution_count,
            "provider_call_count": self.provider_call_count,
            "rag_query_count": self.rag_query_count,
            "extractor_call_count": self.extractor_call_count,
            "fusion_result_write_count": self.fusion_result_write_count,
            "unknown_jobs_modified": self.unknown_jobs_modified,
            "jobs_cancelled": self.jobs_cancelled,
            "preexisting_active_jobs_found": self.preexisting_active_jobs_found,
            "preexisting_active_jobs_cancelled": self.preexisting_active_jobs_cancelled,
            "worker_restart_events": self.worker_restart_events,
            "db_reconnect_events": self.db_reconnect_events,
            "errors": self.errors,
        }


async def _resolve_latest_report(symbol: str) -> ReportDocument:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ReportDocument).where(ReportDocument.ts_code.like(f"{symbol}.%")))
        docs = list(result.scalars().all())
        annuals = [doc for doc in docs if (doc.report_type or "").lower() == "annual"]
        pool = annuals or docs
        if not pool:
            raise RuntimeError(f"no report documents found for {symbol}")
        return sorted(pool, key=lambda item: ((item.report_year or 0), item.id), reverse=True)[0]


async def _cleanup_jobs(job_ids: list[str]) -> None:
    if not job_ids:
        return
    async with AsyncSessionLocal() as db:
        await db.execute(delete(CompanyV2FinancialFusionWorkerObservation).where(CompanyV2FinancialFusionWorkerObservation.job_id.in_(job_ids)))
        await db.execute(delete(CompanyV2FinancialFusionJob).where(CompanyV2FinancialFusionJob.job_id.in_(job_ids)))
        await db.commit()


async def _preexisting_active_jobs(scope: str) -> list[str]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(CompanyV2FinancialFusionJob.job_id).where(
                CompanyV2FinancialFusionJob.requester_scope == scope,
                CompanyV2FinancialFusionJob.status.in_(["queued", "running"]),
            )
        )
        return [row[0] for row in result.all()]


async def _insert_soak_job(report: ReportDocument, *, run_id: str, symbol: str) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        payload = await company_v2_financial_fusion_job_service.create_job(
            db=db,
            market="CN",
            symbol=symbol,
            report=report,
            fields=None,
            refresh=False,
            requester_scope=JOB_SCOPE,
            manual_admission=True,
        )
        if not payload.get("ok"):
            raise RuntimeError(f"failed to create soak job for {symbol}: {payload.get('error_code')}")
        row = await db.execute(select(CompanyV2FinancialFusionJob).where(CompanyV2FinancialFusionJob.job_id == payload["job_id"]))
        job = row.scalars().first()
        if not job:
            raise RuntimeError("created job not found")
        job.requester_scope = JOB_SCOPE
        job.requester_metadata_json = json.dumps({"run_id": run_id, "phase": "6ts_shadow_soak", "symbol": symbol}, ensure_ascii=False)
        await db.commit()
        return payload


async def _cancel_job(job_id: str, symbol: str) -> None:
    async with AsyncSessionLocal() as db:
        await company_v2_financial_fusion_job_service.cancel_job(db=db, job_id=job_id, symbol=symbol)


async def _count_active_leases() -> int:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(CompanyV2FinancialFusionJob).where(
                CompanyV2FinancialFusionJob.claimed_by.is_not(None),
                CompanyV2FinancialFusionJob.status == "queued",
            )
        )
        return len(list(result.scalars().all()))


async def _count_stale_leases() -> int:
    now = _now()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(CompanyV2FinancialFusionJob).where(
                CompanyV2FinancialFusionJob.claimed_by.is_not(None),
                CompanyV2FinancialFusionJob.status == "queued",
                CompanyV2FinancialFusionJob.lease_expires_at.is_not(None),
                CompanyV2FinancialFusionJob.lease_expires_at <= now,
            )
        )
        return len(list(result.scalars().all()))


async def _hold_and_heartbeat(
    *,
    job_id: str,
    worker_id: str,
    hold_seconds: float,
    heartbeat_seconds: float,
    metrics: SoakMetrics,
    stop_event: asyncio.Event,
) -> None:
    started = perf_counter()
    next_heartbeat = started + max(1.0, heartbeat_seconds / 2.0)
    deadline = started + max(0.0, hold_seconds)
    while perf_counter() < deadline and not stop_event.is_set():
        await asyncio.sleep(min(0.5, max(0.1, deadline - perf_counter())))
        if perf_counter() >= next_heartbeat and not stop_event.is_set():
            try:
                async with AsyncSessionLocal() as db:
                    result = await company_v2_financial_fusion_worker_service.heartbeat(db=db, job_id=job_id, worker_id=worker_id, lease_seconds=int(max(heartbeat_seconds * 2, heartbeat_seconds + 1)))
                if result is None:
                    metrics.heartbeat_failures += 1
                else:
                    metrics.heartbeat_events.append((perf_counter() - started) * 1000.0)
                    next_heartbeat = perf_counter() + max(1.0, heartbeat_seconds / 2.0)
            except Exception:  # noqa: BLE001
                metrics.heartbeat_failures += 1
                next_heartbeat = perf_counter() + max(1.0, heartbeat_seconds / 2.0)


async def _worker_loop(
    *,
    worker_id: str,
    metrics: SoakMetrics,
    stop_event: asyncio.Event,
    active_claims: set[str],
    poll_interval_seconds: float,
    lease_seconds: int,
    heartbeat_seconds: int,
    max_jobs_per_cycle: int,
    sample_interval_seconds: int,
) -> None:
    while not stop_event.is_set():
        cycle_started = perf_counter()
        claimed_any = False
        try:
            for _ in range(max_jobs_per_cycle):
                if stop_event.is_set():
                    break
                claim_started = perf_counter()
                async with AsyncSessionLocal() as db:
                    claim = await company_v2_financial_fusion_worker_service.claim_next_job(
                        db=db,
                        worker_id=worker_id,
                        lease_seconds=lease_seconds,
                        heartbeat_seconds=heartbeat_seconds,
                    )
                claim_ms = (perf_counter() - claim_started) * 1000.0
                if not claim:
                    break
                claimed_any = True
                metrics.record_claim(claim["job_id"], claim_ms, active_claims)
                try:
                    hold_task = asyncio.create_task(
                        _hold_and_heartbeat(
                            job_id=claim["job_id"],
                            worker_id=worker_id,
                            hold_seconds=float(sample_interval_seconds),
                            heartbeat_seconds=float(heartbeat_seconds),
                            metrics=metrics,
                            stop_event=stop_event,
                        )
                    )
                    async with AsyncSessionLocal() as db:
                        loaded = await db.execute(select(CompanyV2FinancialFusionJob).where(CompanyV2FinancialFusionJob.job_id == claim["job_id"]))
                        job = loaded.scalars().first()
                    if job is None:
                        metrics.unrecovered_worker_failures += 1
                        hold_task.cancel()
                        with contextlib.suppress(Exception):
                            await hold_task
                        continue
                    await hold_task
                    async with AsyncSessionLocal() as db:
                        observation = await company_v2_financial_fusion_worker_service.evaluate_shadow_job(db=db, job=job, worker_id=worker_id)
                    metrics.jobs_observed += 1
                    metrics.observation_rows_written += 1
                    metrics.real_execution_count += int(observation.get("real_execution_count") or 0)
                    metrics.provider_call_count += int(observation.get("provider_calls") or 0)
                    metrics.rag_query_count += int(observation.get("rag_query_calls") or 0)
                    metrics.extractor_call_count += int(observation.get("extractor_calls") or 0)
                    metrics.fusion_result_write_count += int(observation.get("fusion_calls") or 0)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    metrics.errors.append({"worker_id": worker_id, "job_id": claim["job_id"], "message": str(exc)[:200]})
                    metrics.unrecovered_worker_failures += 1
                finally:
                    metrics.record_release(claim["job_id"], active_claims)
        except asyncio.CancelledError:
            metrics.worker_restart_count += 1
            break
        finally:
            metrics.record_loop((perf_counter() - cycle_started) * 1000.0)
        if not claimed_any:
            await asyncio.sleep(max(0.1, poll_interval_seconds))


async def run_soak(args: argparse.Namespace) -> dict[str, Any]:
    run_id = uuid.uuid4().hex
    symbols = [item.strip() for item in (args.symbols or ",".join(DEFAULT_SYMBOLS)).split(",") if item.strip()]
    metrics = SoakMetrics(duration_seconds=int(args.duration_seconds), worker_count=int(args.worker_count))
    metrics.worker_ids = [f"{args.worker_id_prefix}-{i+1}" for i in range(metrics.worker_count)]

    preexisting = await _preexisting_active_jobs(JOB_SCOPE)
    metrics.preexisting_active_jobs_found = len(preexisting)
    if preexisting:
        metrics.errors.append({"code": "PREEXISTING_ACTIVE_JOBS", "count": len(preexisting)})
        return {
            "phase": "phase6ts_shadow_soak",
            "status": "failed",
            "run_id": run_id,
            "stage3_status": "not_authorized",
            "stage3_authorized": bool(getattr(settings, "company_v2_financial_fusion_stage3_authorized", False)),
            "worker_mode": "shadow",
            "worker_enabled": bool(getattr(settings, "company_v2_financial_fusion_worker_enabled", False)),
            "auto_run": bool(getattr(settings, "company_v2_financial_fusion_auto_run", False)),
            "rollout_percent": int(getattr(settings, "company_v2_financial_fusion_rollout_percent", 0) or 0),
            "symbols": symbols,
            "created_jobs": [],
            "metrics": metrics.as_dict(),
            "real_execution_count": 0,
            "provider_call_count": 0,
            "rag_query_count": 0,
            "extractor_call_count": 0,
            "fusion_result_write_count": 0,
            "blocking_issues": ["PREEXISTING_ACTIVE_JOBS"],
            "errors": metrics.errors,
            "shadow_soak_completed": False,
        }

    reports = {symbol: await _resolve_latest_report(symbol) for symbol in symbols}
    created_jobs: list[dict[str, Any]] = []
    for symbol in symbols:
        job_payload = await _insert_soak_job(reports[symbol], run_id=run_id, symbol=symbol)
        metrics.jobs_created += 1
        metrics.created_job_ids.append(job_payload["job_id"])
        created_jobs.append(job_payload)

    stop_event = asyncio.Event()
    active_claims: set[str] = set()

    workers = [
        asyncio.create_task(
            _worker_loop(
                worker_id=worker_id,
                metrics=metrics,
                stop_event=stop_event,
                active_claims=active_claims,
                poll_interval_seconds=float(args.poll_interval_seconds),
                lease_seconds=int(args.lease_seconds),
                heartbeat_seconds=int(args.heartbeat_seconds),
                max_jobs_per_cycle=int(args.max_jobs_per_cycle),
                sample_interval_seconds=int(args.sample_interval_seconds),
            )
        )
        for worker_id in metrics.worker_ids
    ]

    started = perf_counter()
    restart_done = False
    reconnect_done = False
    try:
        while perf_counter() - started < float(args.duration_seconds):
            elapsed = perf_counter() - started
            if args.inject_worker_restart_at is not None and not restart_done and elapsed >= float(args.inject_worker_restart_at):
                victim = workers[0]
                victim.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await victim
                metrics.worker_restart_events.append({"at_seconds": round(elapsed, 2), "worker_id": metrics.worker_ids[0]})
                metrics.worker_restart_count += 1
                workers[0] = asyncio.create_task(
                    _worker_loop(
                        worker_id=metrics.worker_ids[0],
                        metrics=metrics,
                        stop_event=stop_event,
                        active_claims=active_claims,
                        poll_interval_seconds=float(args.poll_interval_seconds),
                        lease_seconds=int(args.lease_seconds),
                        heartbeat_seconds=int(args.heartbeat_seconds),
                        max_jobs_per_cycle=int(args.max_jobs_per_cycle),
                        sample_interval_seconds=int(args.sample_interval_seconds),
                    )
                )
                restart_done = True
            if args.inject_db_reconnect_at is not None and not reconnect_done and elapsed >= float(args.inject_db_reconnect_at):
                try:
                    await async_engine.dispose()
                    metrics.db_disconnect_count += 1
                    metrics.db_reconnect_count += 1
                    metrics.db_reconnect_events.append({"at_seconds": round(elapsed, 2), "disposed": True})
                except Exception as exc:  # noqa: BLE001
                    metrics.errors.append({"code": "DB_RECONNECT_FAILED", "message": str(exc)[:200]})
                reconnect_done = True
            await asyncio.sleep(max(0.2, float(args.sample_interval_seconds) / 5.0))
    finally:
        stop_event.set()
        for task in workers:
            task.cancel()
        for task in workers:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    for job in created_jobs:
        await _cancel_job(job["job_id"], job["symbol"])
        metrics.jobs_cancelled += 1
        metrics.cleanup_cancelled_job_ids.append(job["job_id"])

    metrics.active_leases_end = await _count_active_leases()
    metrics.stale_leases_end = await _count_stale_leases()
    metrics.preexisting_active_jobs_cancelled = 0

    cleanup_ids = list(metrics.created_job_ids)
    await _cleanup_jobs(cleanup_ids)

    payload = {
        "phase": "phase6ts_shadow_soak",
        "status": "passed" if not metrics.errors and metrics.real_execution_count == 0 else "failed",
        "run_id": run_id,
        "stage3_status": "not_authorized",
        "stage3_authorized": bool(getattr(settings, "company_v2_financial_fusion_stage3_authorized", False)),
        "worker_mode": "shadow",
        "worker_enabled": bool(getattr(settings, "company_v2_financial_fusion_worker_enabled", False)),
        "auto_run": bool(getattr(settings, "company_v2_financial_fusion_auto_run", False)),
        "rollout_percent": int(getattr(settings, "company_v2_financial_fusion_rollout_percent", 0) or 0),
        "symbols": symbols,
        "created_jobs": _sanitize(created_jobs),
        "metrics": metrics.as_dict(),
        "real_execution_count": metrics.real_execution_count,
        "provider_call_count": metrics.provider_call_count,
        "rag_query_count": metrics.rag_query_count,
        "extractor_call_count": metrics.extractor_call_count,
        "fusion_result_write_count": metrics.fusion_result_write_count,
        "blocking_issues": [],
        "errors": metrics.errors,
    }
    payload["shadow_soak_completed"] = payload["status"] == "passed" and not metrics.errors and metrics.real_execution_count == 0
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration-seconds", type=int, default=DEFAULT_DURATION_SECONDS)
    parser.add_argument("--poll-interval-seconds", type=float, default=DEFAULT_POLL_INTERVAL_SECONDS)
    parser.add_argument("--worker-count", type=int, default=DEFAULT_WORKER_COUNT)
    parser.add_argument("--worker-id-prefix", default="phase6ts-worker")
    parser.add_argument("--lease-seconds", type=int, default=DEFAULT_LEASE_SECONDS)
    parser.add_argument("--heartbeat-seconds", type=int, default=DEFAULT_HEARTBEAT_SECONDS)
    parser.add_argument("--max-jobs-per-cycle", type=int, default=DEFAULT_MAX_JOBS_PER_CYCLE)
    parser.add_argument("--sample-interval-seconds", type=int, default=DEFAULT_SAMPLE_INTERVAL_SECONDS)
    parser.add_argument("--base-artifact-dir", default=str(DEFAULT_BASE_ARTIFACT_DIR))
    parser.add_argument("--out-json", default=None)
    parser.add_argument("--out-md", default=None)
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--inject-worker-restart-at", type=float, default=None)
    parser.add_argument("--inject-db-reconnect-at", type=float, default=None)
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    return parser.parse_args(argv)


def _default_paths(base_artifact_dir: str) -> tuple[str, str]:
    base = Path(base_artifact_dir)
    return (
        str(base / "company_v2_phase6ts_shadow_soak.json"),
        str(base / "company_v2_phase6ts_shadow_soak.md"),
    )


def _artifact_lines(payload: dict[str, Any]) -> str:
    return "# Phase 6T-S Shadow Soak\n\n```json\n" + json.dumps(_sanitize(payload), ensure_ascii=False, indent=2) + "\n```\n"


def _write_artifacts(payload: dict[str, Any], *, out_json: str, out_md: str) -> None:
    sanitized = _sanitize(payload)
    Path(out_json).write_text(json.dumps(sanitized, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(out_md).write_text(_artifact_lines(payload), encoding="utf-8")


def _secondary_artifacts(payload: dict[str, Any], base_artifact_dir: str) -> None:
    base = Path(base_artifact_dir)
    restart_payload = {
        "phase": "phase6ts_worker_restart",
        "status": payload["status"],
        "worker_restart_count": payload["metrics"]["worker_restart_count"],
        "worker_restart_events": payload["metrics"]["worker_restart_events"],
        "real_execution_count": payload["real_execution_count"],
        "blocking_issues": payload["blocking_issues"],
    }
    reconnect_payload = {
        "phase": "phase6ts_db_reconnect",
        "status": payload["status"],
        "db_disconnect_count": payload["metrics"]["db_disconnect_count"],
        "db_reconnect_count": payload["metrics"]["db_reconnect_count"],
        "db_reconnect_events": payload["metrics"]["db_reconnect_events"],
        "real_execution_count": payload["real_execution_count"],
        "blocking_issues": payload["blocking_issues"],
    }
    for name, value in {
        "company_v2_phase6ts_worker_restart.json": restart_payload,
        "company_v2_phase6ts_worker_restart.md": restart_payload,
        "company_v2_phase6ts_db_reconnect.json": reconnect_payload,
        "company_v2_phase6ts_db_reconnect.md": reconnect_payload,
    }.items():
        path = base / name
        if path.suffix == ".json":
            path.write_text(json.dumps(_sanitize(value), ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            path.write_text("# Phase 6T-S Secondary Artifact\n\n```json\n" + json.dumps(_sanitize(value), ensure_ascii=False, indent=2) + "\n```\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out_json, out_md = args.out_json, args.out_md
    if not out_json or not out_md:
        default_json, default_md = _default_paths(args.base_artifact_dir)
        out_json = out_json or default_json
        out_md = out_md or default_md
    payload = asyncio.run(run_soak(args))
    _write_artifacts(payload, out_json=out_json, out_md=out_md)
    _secondary_artifacts(payload, args.base_artifact_dir)
    print(json.dumps({"status": payload["status"], "real_execution_count": payload["real_execution_count"]}, ensure_ascii=False))
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
