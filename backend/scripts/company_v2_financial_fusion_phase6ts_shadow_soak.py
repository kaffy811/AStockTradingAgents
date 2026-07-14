"""Phase 6T-S shadow soak runner for Company V2 financial fusion."""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import math
import os
import signal
import subprocess
import sys
import traceback
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

from sqlalchemy import delete, select, update

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
SHADOW_EXECUTION_MODE = "shadow"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        blocked = {
            "database_url",
            "password",
            "token",
            "traceback",
            "traceback_sanitized",
            "stack",
            "local_path",
            "path",
            "sidecar_path",
        }
        return {k: _sanitize(v) for k, v in value.items() if k not in blocked}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, str) and (value.startswith("/Users/") or value.startswith("/private/") or value.startswith("/tmp/")):
        return "[redacted]"
    return value


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _coerce_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None
    return None


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ROOT.parent),
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None


def _error_payload(code: str, exc: BaseException | str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code}
    if isinstance(exc, BaseException):
        payload["message"] = str(exc)[:500]
        payload["traceback_sanitized"] = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-4000:]
    else:
        payload["message"] = str(exc)[:500]
    payload.update(extra)
    return payload


def _metadata_run_id(metadata_json: str | None) -> str | None:
    if not metadata_json:
        return None
    try:
        payload = json.loads(metadata_json)
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(payload, dict):
        return None
    run_id = payload.get("run_id")
    return str(run_id) if run_id else None


def _assert_soak_claim_scope(
    job: Any,
    *,
    requester_scope: str | None,
    requester_run_id: str | None,
    allowed_job_ids: set[str] | None,
) -> None:
    if allowed_job_ids is not None and job.job_id not in allowed_job_ids:
        raise RuntimeError(f"scope isolation violation: job_id={job.job_id!r} not allowed")
    if requester_scope and job.requester_scope != requester_scope:
        raise RuntimeError(
            f"scope isolation violation: expected requester_scope={requester_scope!r}, got {job.requester_scope!r}"
        )
    if requester_run_id and _metadata_run_id(job.requester_metadata_json) != requester_run_id:
        raise RuntimeError(f"scope isolation violation: run_id mismatch for job_id={job.job_id!r}")


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
    shadow_observation_count: int = 0
    unique_jobs_claimed: set[str] = field(default_factory=set)
    claimed_jobs: list[str] = field(default_factory=list)
    claim_events: list[float] = field(default_factory=list)
    loop_events: list[float] = field(default_factory=list)
    heartbeat_events: list[float] = field(default_factory=list)
    lease_renewal_failures: int = 0
    heartbeat_failures: int = 0
    duplicate_claim_count: int = 0
    simultaneous_claim_conflicts: int = 0
    reclaim_after_restart_count: int = 0
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
    cleanup_errors: list[dict[str, Any]] = field(default_factory=list)
    cleanup_cancelled_job_ids: list[str] = field(default_factory=list)
    preexisting_active_jobs_found: int = 0
    preexisting_active_jobs_cancelled: int = 0
    created_job_ids: list[str] = field(default_factory=list)
    observed_job_ids: list[str] = field(default_factory=list)
    claimed_job_ids: list[str] = field(default_factory=list)
    worker_restart_events: list[dict[str, Any]] = field(default_factory=list)
    db_reconnect_events: list[dict[str, Any]] = field(default_factory=list)
    claim_reclaim_events: list[dict[str, Any]] = field(default_factory=list)
    duplicate_claim_events: list[dict[str, Any]] = field(default_factory=list)
    _claim_event_ids_seen: set[str] = field(default_factory=set, repr=False)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def record_loop(self, ms: float) -> None:
        self.loop_events.append(ms)

    def _active_lease_count(self, active_claims: dict[str, list[dict[str, Any]]]) -> int:
        return sum(len(events) for events in active_claims.values())

    def _claim_event_id(self, claim: dict[str, Any], requester_run_id: str | None) -> str:
        return "|".join(
            [
                str(requester_run_id or ""),
                str(claim.get("job_id") or ""),
                str(claim.get("claimed_by") or claim.get("worker_id") or ""),
                str(_iso(_coerce_datetime(claim.get("claimed_at"))) or ""),
                str(_iso(_coerce_datetime(claim.get("lease_expires_at"))) or ""),
            ]
        )

    def _claim_diagnostic(
        self,
        first: dict[str, Any],
        second: dict[str, Any],
        *,
        overlap: bool,
        reclaim_reason: str,
        requester_run_id: str | None,
    ) -> dict[str, Any]:
        return {
            "duplicate_job_id": second.get("job_id"),
            "first_worker_id": first.get("worker_id"),
            "second_worker_id": second.get("worker_id"),
            "first_claim_timestamp": _iso(first.get("claimed_at")),
            "second_claim_timestamp": _iso(second.get("claimed_at")),
            "first_lease_expires_at": _iso(first.get("lease_expires_at")),
            "second_lease_expires_at": _iso(second.get("lease_expires_at")),
            "overlap": overlap,
            "reclaim_reason": reclaim_reason,
            "requester_run_id": requester_run_id,
        }

    def record_claim(
        self,
        claim: dict[str, Any] | str,
        ms: float,
        active_claims: dict[str, list[dict[str, Any]]],
        *,
        requester_run_id: str | None = None,
    ) -> str:
        if isinstance(claim, str):
            now = _now()
            claim = {
                "job_id": claim,
                "claimed_by": "unknown",
                "claimed_at": now,
                "lease_expires_at": now,
            }
        job_id = str(claim.get("job_id") or "")
        worker_id = str(claim.get("claimed_by") or claim.get("worker_id") or "")
        claimed_at = _coerce_datetime(claim.get("claimed_at")) or _now()
        lease_expires_at = _coerce_datetime(claim.get("lease_expires_at")) or claimed_at
        event = {
            "job_id": job_id,
            "worker_id": worker_id,
            "claimed_at": claimed_at,
            "lease_expires_at": lease_expires_at,
        }
        event_id = self._claim_event_id(claim, requester_run_id)
        event["event_id"] = event_id
        if event_id in self._claim_event_ids_seen:
            return event_id
        self._claim_event_ids_seen.add(event_id)
        self.claim_events.append(ms)
        self.unique_jobs_claimed.add(job_id)
        self.claimed_job_ids.append(job_id)

        previous_events = list(active_claims.get(job_id, []))
        overlapping = [
            previous
            for previous in previous_events
            if previous.get("lease_expires_at") and claimed_at < previous["lease_expires_at"]
        ]
        if overlapping:
            first = sorted(overlapping, key=lambda item: item["claimed_at"])[0]
            self.duplicate_claim_count += 1
            self.simultaneous_claim_conflicts += 1
            self.duplicate_claim_events.append(
                self._claim_diagnostic(
                    first,
                    event,
                    overlap=True,
                    reclaim_reason="lease_overlap",
                    requester_run_id=requester_run_id,
                )
            )
        elif previous_events:
            first = sorted(previous_events, key=lambda item: item["claimed_at"])[-1]
            self.reclaim_after_restart_count += 1
            self.claim_reclaim_events.append(
                self._claim_diagnostic(
                    first,
                    event,
                    overlap=False,
                    reclaim_reason="lease_expired_before_reclaim",
                    requester_run_id=requester_run_id,
                )
            )

        active_claims[job_id] = [
            previous for previous in previous_events
            if previous.get("lease_expires_at") and claimed_at < previous["lease_expires_at"]
        ]
        active_claims[job_id].append(event)
        self.active_leases_peak = max(self.active_leases_peak, self._active_lease_count(active_claims))
        return event_id

    def record_release(
        self,
        job_id: str,
        active_claims: dict[str, list[dict[str, Any]]],
        *,
        worker_id: str | None = None,
        claim_event_id: str | None = None,
    ) -> None:
        events = list(active_claims.get(job_id, []))
        if not events:
            return
        if claim_event_id:
            events = [event for event in events if event.get("event_id") != claim_event_id]
        elif worker_id:
            events = [event for event in events if event.get("worker_id") != worker_id]
        else:
            events = []
        if events:
            active_claims[job_id] = events
        else:
            active_claims.pop(job_id, None)

    def as_dict(self) -> dict[str, Any]:
        return {
            "duration_seconds": self.duration_seconds,
            "worker_count": self.worker_count,
            "worker_ids": self.worker_ids,
            "jobs_created": self.jobs_created,
            "jobs_observed": self.jobs_observed,
            "shadow_observation_count": self.shadow_observation_count,
            "unique_jobs_claimed": len(self.unique_jobs_claimed),
            "duplicate_claim_count": self.duplicate_claim_count,
            "simultaneous_claim_conflicts": self.simultaneous_claim_conflicts,
            "reclaim_after_restart_count": self.reclaim_after_restart_count,
            "duplicate_claim_events": self.duplicate_claim_events,
            "claim_reclaim_events": self.claim_reclaim_events,
            "observation_rows_written": self.observation_rows_written,
            "active_leases_peak": self.active_leases_peak,
            "active_leases_end": self.active_leases_end,
            "stale_leases_end": self.stale_leases_end,
            "heartbeat_failures": self.heartbeat_failures,
            "lease_renewal_failures": self.lease_renewal_failures,
            "db_disconnect_count": self.db_disconnect_count,
            "db_reconnect_count": self.db_reconnect_count,
            "worker_restart_count": self.worker_restart_count,
            "unrecovered_worker_failures": self.unrecovered_worker_failures,
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
            "cleanup_errors": self.cleanup_errors,
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


async def _release_run_leases(job_ids: list[str]) -> int:
    if not job_ids:
        return 0
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            update(CompanyV2FinancialFusionJob)
            .where(
                CompanyV2FinancialFusionJob.job_id.in_(job_ids),
                CompanyV2FinancialFusionJob.requester_scope == JOB_SCOPE,
            )
            .values(
                claimed_by=None,
                claimed_at=None,
                heartbeat_at=None,
                lease_expires_at=None,
                last_error_message_sanitized="phase6ts cleanup release",
                updated_at=_now(),
            )
            .returning(CompanyV2FinancialFusionJob.job_id)
        )
        released = [row[0] for row in result.all()]
        await db.commit()
        return len(released)


async def _count_active_leases(job_ids: list[str] | None = None) -> int:
    async with AsyncSessionLocal() as db:
        stmt = (
            select(CompanyV2FinancialFusionJob).where(
                CompanyV2FinancialFusionJob.claimed_by.is_not(None),
                CompanyV2FinancialFusionJob.status == "queued",
            )
        )
        if job_ids is not None:
            if not job_ids:
                return 0
            stmt = stmt.where(CompanyV2FinancialFusionJob.job_id.in_(job_ids))
        result = await db.execute(stmt)
        return len(list(result.scalars().all()))


async def _count_stale_leases(job_ids: list[str] | None = None) -> int:
    now = _now()
    async with AsyncSessionLocal() as db:
        stmt = (
            select(CompanyV2FinancialFusionJob).where(
                CompanyV2FinancialFusionJob.claimed_by.is_not(None),
                CompanyV2FinancialFusionJob.status == "queued",
                CompanyV2FinancialFusionJob.lease_expires_at.is_not(None),
                CompanyV2FinancialFusionJob.lease_expires_at <= now,
            )
        )
        if job_ids is not None:
            if not job_ids:
                return 0
            stmt = stmt.where(CompanyV2FinancialFusionJob.job_id.in_(job_ids))
        result = await db.execute(stmt)
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
    active_claims: dict[str, list[dict[str, Any]]],
    poll_interval_seconds: float,
    lease_seconds: int,
    heartbeat_seconds: int,
    max_jobs_per_cycle: int,
    sample_interval_seconds: int,
    requester_scope: str | None = None,
    requester_run_id: str | None = None,
    allowed_job_ids: set[str] | None = None,
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
                        requester_scope=requester_scope,
                        requester_run_id=requester_run_id,
                        allowed_job_ids=allowed_job_ids,
                    )
                claim_ms = (perf_counter() - claim_started) * 1000.0
                if not claim:
                    break
                claimed_any = True
                claim_event_id = metrics.record_claim(
                    claim,
                    claim_ms,
                    active_claims,
                    requester_run_id=requester_run_id,
                )
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
                    try:
                        _assert_soak_claim_scope(
                            job,
                            requester_scope=requester_scope,
                            requester_run_id=requester_run_id,
                            allowed_job_ids=allowed_job_ids,
                        )
                    except RuntimeError as exc:
                        metrics.unknown_jobs_modified += 1
                        metrics.errors.append(
                            {
                                "code": "SOAK_CLAIM_SCOPE_ISOLATION_FAILED",
                                "job_id": claim["job_id"],
                                "message": str(exc)[:200],
                            }
                        )
                        stop_event.set()
                        hold_task.cancel()
                        with contextlib.suppress(Exception):
                            await hold_task
                        continue
                    await hold_task
                    async with AsyncSessionLocal() as db:
                        observation = await company_v2_financial_fusion_worker_service.evaluate_shadow_job(
                            db=db,
                            job=job,
                            worker_id=worker_id,
                            expected_requester_scope=requester_scope,
                            expected_requester_run_id=requester_run_id,
                            allowed_job_ids=allowed_job_ids,
                        )
                    metrics.jobs_observed += 1
                    metrics.shadow_observation_count += 1
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
                    metrics.record_release(
                        claim["job_id"],
                        active_claims,
                        worker_id=worker_id,
                        claim_event_id=claim_event_id,
                    )
        except asyncio.CancelledError:
            metrics.worker_restart_count += 1
            break
        finally:
            metrics.record_loop((perf_counter() - cycle_started) * 1000.0)
        if not claimed_any:
            await asyncio.sleep(max(0.1, poll_interval_seconds))


def _start_worker_task(
    *,
    worker_id: str,
    args: argparse.Namespace,
    run_id: str,
    metrics: SoakMetrics,
    stop_event: asyncio.Event,
    active_claims: dict[str, list[dict[str, Any]]],
    allowed_job_ids: set[str],
) -> asyncio.Task:
    return asyncio.create_task(
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
            requester_scope=JOB_SCOPE,
            requester_run_id=run_id,
            allowed_job_ids=allowed_job_ids,
        )
    )


async def _cancel_created_jobs(created_jobs: list[dict[str, Any]], metrics: SoakMetrics) -> None:
    for job in created_jobs:
        try:
            await _cancel_job(job["job_id"], job["symbol"])
            metrics.jobs_cancelled += 1
            metrics.cleanup_cancelled_job_ids.append(job["job_id"])
        except Exception as exc:  # noqa: BLE001
            error = _error_payload("CLEANUP_CANCEL_JOB_FAILED", exc, job_id=job.get("job_id"))
            metrics.cleanup_errors.append(error)
            metrics.errors.append(error)


def _build_payload(
    *,
    status: str,
    run_id: str,
    symbols: list[str],
    created_jobs: list[dict[str, Any]],
    metrics: SoakMetrics,
    blocking_issues: list[str],
    started_at: datetime,
    finished_at: datetime | None,
    requested_duration_seconds: float,
    actual_duration_seconds: float,
    exit_reason: str,
    process_pid: int,
    git_commit: str | None,
) -> dict[str, Any]:
    payload = {
        "phase": "phase6ts_shadow_soak",
        "status": status,
        "run_id": run_id,
        "started_at": _iso(started_at),
        "finished_at": _iso(finished_at),
        "requested_duration_seconds": requested_duration_seconds,
        "actual_duration_seconds": round(actual_duration_seconds, 3),
        "process_pid": process_pid,
        "git_commit": git_commit,
        "exit_reason": exit_reason,
        "stage3_status": "not_authorized",
        "stage3_authorized": bool(getattr(settings, "company_v2_financial_fusion_stage3_authorized", False)),
        "worker_mode": "shadow",
        "worker_enabled": bool(getattr(settings, "company_v2_financial_fusion_worker_enabled", False)),
        "auto_run": bool(getattr(settings, "company_v2_financial_fusion_auto_run", False)),
        "rollout_percent": int(getattr(settings, "company_v2_financial_fusion_rollout_percent", 0) or 0),
        "symbols": symbols,
        "created_jobs": _sanitize(created_jobs),
        "jobs_created": metrics.jobs_created,
        "jobs_cancelled": metrics.jobs_cancelled,
        "active_leases_end": metrics.active_leases_end,
        "stale_leases_end": metrics.stale_leases_end,
        "metrics": metrics.as_dict(),
        "real_execution_count": metrics.real_execution_count,
        "provider_call_count": metrics.provider_call_count,
        "rag_query_count": metrics.rag_query_count,
        "extractor_call_count": metrics.extractor_call_count,
        "fusion_result_write_count": metrics.fusion_result_write_count,
        "blocking_issues": blocking_issues,
        "errors": metrics.errors,
    }
    payload["shadow_soak_completed"] = status == "passed" and not metrics.errors and metrics.real_execution_count == 0
    payload["phase6ts_passed"] = payload["shadow_soak_completed"]
    return payload


async def run_soak(
    args: argparse.Namespace,
    *,
    run_id: str | None = None,
    started_at: datetime | None = None,
    process_pid: int | None = None,
    git_commit: str | None = None,
) -> dict[str, Any]:
    run_id = run_id or uuid.uuid4().hex
    started_at = started_at or _now()
    process_pid = process_pid or os.getpid()
    requested_duration_seconds = float(args.duration_seconds)
    run_started_monotonic = perf_counter()
    soak_started_monotonic = run_started_monotonic
    deadline = soak_started_monotonic + requested_duration_seconds
    symbols = [item.strip() for item in (args.symbols or ",".join(DEFAULT_SYMBOLS)).split(",") if item.strip()]
    metrics = SoakMetrics(duration_seconds=int(args.duration_seconds), worker_count=int(args.worker_count))
    metrics.worker_ids = [f"{args.worker_id_prefix}-{i+1}" for i in range(metrics.worker_count)]
    created_jobs: list[dict[str, Any]] = []
    blocking_issues: list[str] = []
    exit_reason = "duration_elapsed"
    stop_event = asyncio.Event()
    active_claims: dict[str, list[dict[str, Any]]] = {}
    workers: list[asyncio.Task] = []
    restart_done = False
    reconnect_done = False
    loop = asyncio.get_running_loop()
    installed_signals: list[signal.Signals] = []

    def request_signal_stop(signum: signal.Signals) -> None:
        nonlocal exit_reason
        exit_reason = f"signal:{signum.name}"
        metrics.errors.append({"code": "SIGNAL_RECEIVED", "signal": signum.name})
        stop_event.set()

    for signum in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
            loop.add_signal_handler(signum, request_signal_stop, signum)
            installed_signals.append(signum)

    try:
        preexisting = await _preexisting_active_jobs(JOB_SCOPE)
        metrics.preexisting_active_jobs_found = len(preexisting)
        if preexisting:
            metrics.errors.append({"code": "PREEXISTING_ACTIVE_JOBS", "count": len(preexisting)})
            blocking_issues.append("PREEXISTING_ACTIVE_JOBS")
            exit_reason = "preexisting_active_jobs"
            stop_event.set()
        else:
            reports = {symbol: await _resolve_latest_report(symbol) for symbol in symbols}
            for symbol in symbols:
                job_payload = await _insert_soak_job(reports[symbol], run_id=run_id, symbol=symbol)
                metrics.jobs_created += 1
                metrics.created_job_ids.append(job_payload["job_id"])
                created_jobs.append(job_payload)

            allowed_job_ids = set(metrics.created_job_ids)
            soak_started_monotonic = perf_counter()
            deadline = soak_started_monotonic + requested_duration_seconds
            workers = [
                _start_worker_task(
                    worker_id=worker_id,
                    args=args,
                    run_id=run_id,
                    metrics=metrics,
                    stop_event=stop_event,
                    active_claims=active_claims,
                    allowed_job_ids=allowed_job_ids,
                )
                for worker_id in metrics.worker_ids
            ]

            while perf_counter() < deadline and not stop_event.is_set():
                elapsed = perf_counter() - soak_started_monotonic
                for index, task in enumerate(list(workers)):
                    if not task.done():
                        continue
                    worker_id = metrics.worker_ids[index]
                    try:
                        exc = task.exception()
                    except asyncio.CancelledError:
                        exc = None
                    if exc is not None:
                        metrics.unrecovered_worker_failures += 1
                        metrics.errors.append(_error_payload("WORKER_TASK_FAILED", exc, worker_id=worker_id))
                    metrics.worker_restart_count += 1
                    metrics.worker_restart_events.append({"at_seconds": round(elapsed, 2), "worker_id": worker_id, "reason": "task_done"})
                    workers[index] = _start_worker_task(
                        worker_id=worker_id,
                        args=args,
                        run_id=run_id,
                        metrics=metrics,
                        stop_event=stop_event,
                        active_claims=active_claims,
                        allowed_job_ids=allowed_job_ids,
                    )

                if args.inject_worker_restart_at is not None and not restart_done and elapsed >= float(args.inject_worker_restart_at):
                    victim = workers[0]
                    victim.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await victim
                    metrics.worker_restart_events.append({"at_seconds": round(elapsed, 2), "worker_id": metrics.worker_ids[0], "reason": "injected"})
                    metrics.worker_restart_count += 1
                    workers[0] = _start_worker_task(
                        worker_id=metrics.worker_ids[0],
                        args=args,
                        run_id=run_id,
                        metrics=metrics,
                        stop_event=stop_event,
                        active_claims=active_claims,
                        allowed_job_ids=allowed_job_ids,
                    )
                    restart_done = True
                if args.inject_db_reconnect_at is not None and not reconnect_done and elapsed >= float(args.inject_db_reconnect_at):
                    try:
                        await async_engine.dispose()
                        metrics.db_disconnect_count += 1
                        metrics.db_reconnect_count += 1
                        metrics.db_reconnect_events.append({"at_seconds": round(elapsed, 2), "disposed": True})
                    except Exception as exc:  # noqa: BLE001
                        metrics.errors.append(_error_payload("DB_RECONNECT_FAILED", exc))
                    reconnect_done = True
                await asyncio.sleep(min(max(0.2, float(args.sample_interval_seconds) / 5.0), max(0.0, deadline - perf_counter())))
    except Exception as exc:  # noqa: BLE001
        exit_reason = "exception"
        metrics.errors.append(_error_payload("SOAK_RUNNER_EXCEPTION", exc))
        blocking_issues.append("SOAK_RUNNER_EXCEPTION")
    finally:
        stop_event.set()
        for signum in installed_signals:
            with contextlib.suppress(NotImplementedError, RuntimeError, ValueError):
                loop.remove_signal_handler(signum)
        for index, task in enumerate(workers):
            if not task.done():
                continue
            try:
                exc = task.exception()
            except asyncio.CancelledError:
                exc = None
            if exc is not None:
                worker_id = metrics.worker_ids[index] if index < len(metrics.worker_ids) else "unknown"
                metrics.unrecovered_worker_failures += 1
                metrics.errors.append(_error_payload("WORKER_TASK_FAILED", exc, worker_id=worker_id))
        for task in workers:
            task.cancel()
        for task in workers:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        try:
            await _release_run_leases(list(metrics.created_job_ids))
        except Exception as exc:  # noqa: BLE001
            error = _error_payload("CLEANUP_RELEASE_LEASES_FAILED", exc)
            metrics.cleanup_errors.append(error)
            metrics.errors.append(error)
        await _cancel_created_jobs(created_jobs, metrics)
        try:
            metrics.active_leases_end = await _count_active_leases(list(metrics.created_job_ids))
        except Exception as exc:  # noqa: BLE001
            error = _error_payload("CLEANUP_COUNT_ACTIVE_LEASES_FAILED", exc)
            metrics.cleanup_errors.append(error)
            metrics.errors.append(error)
        try:
            metrics.stale_leases_end = await _count_stale_leases(list(metrics.created_job_ids))
        except Exception as exc:  # noqa: BLE001
            error = _error_payload("CLEANUP_COUNT_STALE_LEASES_FAILED", exc)
            metrics.cleanup_errors.append(error)
            metrics.errors.append(error)

    if metrics.unknown_jobs_modified and "SOAK_CLAIM_SCOPE_ISOLATION_FAILED" not in blocking_issues:
        blocking_issues.append("SOAK_CLAIM_SCOPE_ISOLATION_FAILED")
    if metrics.real_execution_count:
        blocking_issues.append("REAL_EXECUTION_OCCURRED")
    if metrics.provider_call_count or metrics.rag_query_count or metrics.extractor_call_count or metrics.fusion_result_write_count:
        blocking_issues.append("SHADOW_EXTERNAL_CALL_OCCURRED")
    if metrics.active_leases_end not in (0, None):
        blocking_issues.append("ACTIVE_LEASES_REMAIN")
    actual_duration_seconds = perf_counter() - (soak_started_monotonic if created_jobs else run_started_monotonic)
    if exit_reason == "duration_elapsed" and actual_duration_seconds + 0.05 < requested_duration_seconds:
        blocking_issues.append("SHADOW_SOAK_EXITED_BEFORE_REQUESTED_DURATION")
        exit_reason = "exited_before_duration"
    if stop_event.is_set() and exit_reason.startswith("signal:"):
        blocking_issues.append("SHADOW_SOAK_INTERRUPTED")
    status = "passed" if not metrics.errors and not blocking_issues and metrics.real_execution_count == 0 and metrics.active_leases_end == 0 else "failed"
    finished_at = _now()
    metrics.preexisting_active_jobs_cancelled = 0
    return _build_payload(
        status=status,
        run_id=run_id,
        symbols=symbols,
        created_jobs=created_jobs,
        metrics=metrics,
        blocking_issues=blocking_issues,
        started_at=started_at,
        finished_at=finished_at,
        requested_duration_seconds=requested_duration_seconds,
        actual_duration_seconds=actual_duration_seconds,
        exit_reason=exit_reason,
        process_pid=process_pid,
        git_commit=git_commit,
    )


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


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)


def _write_artifacts(payload: dict[str, Any], *, out_json: str, out_md: str) -> None:
    sanitized = _sanitize(payload)
    _atomic_write_text(Path(out_json), json.dumps(sanitized, ensure_ascii=False, indent=2))
    _atomic_write_text(Path(out_md), _artifact_lines(payload))


def _metric(payload: dict[str, Any], key: str, default: Any = 0) -> Any:
    metrics = payload.get("metrics") or {}
    return metrics.get(key, payload.get(key, default))


def _build_gate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    metrics = payload.get("metrics") or {}
    gate_payload = {
        "phase6ts_passed": bool(payload.get("phase6ts_passed")),
        "stage3_status": payload.get("stage3_status", "not_authorized"),
        "stage3_authorized": bool(payload.get("stage3_authorized", False)),
        "shadow_soak_completed": bool(payload.get("shadow_soak_completed")),
        "run_id": payload.get("run_id"),
        "status": payload.get("status"),
        "worker_mode": payload.get("worker_mode", "shadow"),
        "duration_seconds": metrics.get("duration_seconds", payload.get("duration_seconds")),
        "requested_duration_seconds": payload.get("requested_duration_seconds"),
        "actual_duration_seconds": payload.get("actual_duration_seconds"),
        "worker_count": metrics.get("worker_count", payload.get("worker_count")),
        "symbols": payload.get("symbols", []),
        "jobs_created": payload.get("jobs_created", metrics.get("jobs_created", 0)),
        "jobs_cancelled": payload.get("jobs_cancelled", metrics.get("jobs_cancelled", 0)),
        "jobs_observed": metrics.get("jobs_observed", 0),
        "observation_rows_written": metrics.get("observation_rows_written", 0),
        "duplicate_claim_count": metrics.get("duplicate_claim_count", 0),
        "simultaneous_claim_conflicts": metrics.get("simultaneous_claim_conflicts", 0),
        "reclaim_after_restart_count": metrics.get("reclaim_after_restart_count", 0),
        "duplicate_claim_events": metrics.get("duplicate_claim_events", []),
        "claim_reclaim_events": metrics.get("claim_reclaim_events", []),
        "unknown_jobs_modified": metrics.get("unknown_jobs_modified", 0),
        "active_leases_peak": metrics.get("active_leases_peak", 0),
        "active_leases_end": payload.get("active_leases_end", metrics.get("active_leases_end")),
        "stale_leases_end": payload.get("stale_leases_end", metrics.get("stale_leases_end")),
        "heartbeat_failures": metrics.get("heartbeat_failures", 0),
        "lease_renewal_failures": metrics.get("lease_renewal_failures", 0),
        "worker_restart_count": metrics.get("worker_restart_count", 0),
        "db_disconnect_count": metrics.get("db_disconnect_count", 0),
        "db_reconnect_count": metrics.get("db_reconnect_count", 0),
        "preexisting_active_jobs_found": metrics.get("preexisting_active_jobs_found", 0),
        "real_execution_count": payload.get("real_execution_count", metrics.get("real_execution_count", 0)),
        "provider_call_count": payload.get("provider_call_count", metrics.get("provider_call_count", 0)),
        "rag_query_count": payload.get("rag_query_count", metrics.get("rag_query_count", 0)),
        "extractor_call_count": payload.get("extractor_call_count", metrics.get("extractor_call_count", 0)),
        "fusion_result_write_count": payload.get("fusion_result_write_count", metrics.get("fusion_result_write_count", 0)),
        "auto_run": bool(payload.get("auto_run", False)),
        "rollout_percent": int(payload.get("rollout_percent", 0) or 0),
        "blocking_issues": payload.get("blocking_issues", []),
        "errors": payload.get("errors", []),
    }
    _assert_gate_consistency(gate_payload, payload)
    return gate_payload


def _assert_gate_consistency(gate_payload: dict[str, Any], payload: dict[str, Any]) -> None:
    if gate_payload.get("status") != "passed":
        return
    comparisons = {
        "run_id": payload.get("run_id"),
        "duration_seconds": _metric(payload, "duration_seconds"),
        "jobs_created": payload.get("jobs_created", _metric(payload, "jobs_created")),
        "jobs_cancelled": payload.get("jobs_cancelled", _metric(payload, "jobs_cancelled")),
        "worker_restart_count": _metric(payload, "worker_restart_count"),
        "db_disconnect_count": _metric(payload, "db_disconnect_count"),
        "db_reconnect_count": _metric(payload, "db_reconnect_count"),
    }
    mismatches = [
        key for key, expected in comparisons.items()
        if gate_payload.get(key) != expected
    ]
    if mismatches:
        raise RuntimeError(f"phase6ts gate artifact inconsistent for passed run: {', '.join(mismatches)}")


def _running_payload(
    *,
    run_id: str,
    started_at: datetime,
    requested_duration_seconds: float,
    process_pid: int,
    git_commit: str | None,
) -> dict[str, Any]:
    return {
        "phase": "phase6ts_shadow_soak",
        "status": "running",
        "run_id": run_id,
        "started_at": _iso(started_at),
        "finished_at": None,
        "requested_duration_seconds": requested_duration_seconds,
        "actual_duration_seconds": 0.0,
        "process_pid": process_pid,
        "git_commit": git_commit,
        "exit_reason": "running",
        "stage3_status": "not_authorized",
        "stage3_authorized": bool(getattr(settings, "company_v2_financial_fusion_stage3_authorized", False)),
        "auto_run": bool(getattr(settings, "company_v2_financial_fusion_auto_run", False)),
        "rollout_percent": int(getattr(settings, "company_v2_financial_fusion_rollout_percent", 0) or 0),
        "real_execution_count": 0,
        "provider_call_count": 0,
        "rag_query_count": 0,
        "extractor_call_count": 0,
        "fusion_result_write_count": 0,
        "blocking_issues": [],
        "errors": [],
        "shadow_soak_completed": False,
        "phase6ts_passed": False,
    }


def _secondary_artifacts(payload: dict[str, Any], base_artifact_dir: str) -> None:
    base = Path(base_artifact_dir)
    gate_payload = _build_gate_payload(payload)
    restart_payload = {
        "phase": "phase6ts_worker_restart",
        "status": payload["status"],
        "run_id": payload.get("run_id"),
        "started_at": payload.get("started_at"),
        "finished_at": payload.get("finished_at"),
        "duration_seconds": _metric(payload, "duration_seconds"),
        "requested_duration_seconds": payload.get("requested_duration_seconds"),
        "actual_duration_seconds": payload.get("actual_duration_seconds"),
        "process_pid": payload.get("process_pid"),
        "git_commit": payload.get("git_commit"),
        "worker_count": _metric(payload, "worker_count"),
        "jobs_created": payload.get("jobs_created", _metric(payload, "jobs_created")),
        "jobs_cancelled": payload.get("jobs_cancelled", _metric(payload, "jobs_cancelled")),
        "duplicate_claim_count": _metric(payload, "duplicate_claim_count"),
        "reclaim_after_restart_count": _metric(payload, "reclaim_after_restart_count"),
        "duplicate_claim_events": _metric(payload, "duplicate_claim_events", []),
        "claim_reclaim_events": _metric(payload, "claim_reclaim_events", []),
        "unknown_jobs_modified": _metric(payload, "unknown_jobs_modified"),
        "active_leases_end": payload.get("active_leases_end", _metric(payload, "active_leases_end")),
        "stale_leases_end": payload.get("stale_leases_end", _metric(payload, "stale_leases_end")),
        "worker_restart_count": payload["metrics"]["worker_restart_count"],
        "worker_restart_events": payload["metrics"]["worker_restart_events"],
        "real_execution_count": payload["real_execution_count"],
        "provider_call_count": payload["provider_call_count"],
        "rag_query_count": payload["rag_query_count"],
        "extractor_call_count": payload["extractor_call_count"],
        "fusion_result_write_count": payload["fusion_result_write_count"],
        "blocking_issues": payload["blocking_issues"],
    }
    reconnect_payload = {
        "phase": "phase6ts_db_reconnect",
        "status": payload["status"],
        "run_id": payload.get("run_id"),
        "started_at": payload.get("started_at"),
        "finished_at": payload.get("finished_at"),
        "duration_seconds": _metric(payload, "duration_seconds"),
        "requested_duration_seconds": payload.get("requested_duration_seconds"),
        "actual_duration_seconds": payload.get("actual_duration_seconds"),
        "process_pid": payload.get("process_pid"),
        "git_commit": payload.get("git_commit"),
        "worker_count": _metric(payload, "worker_count"),
        "jobs_created": payload.get("jobs_created", _metric(payload, "jobs_created")),
        "jobs_cancelled": payload.get("jobs_cancelled", _metric(payload, "jobs_cancelled")),
        "duplicate_claim_count": _metric(payload, "duplicate_claim_count"),
        "reclaim_after_restart_count": _metric(payload, "reclaim_after_restart_count"),
        "duplicate_claim_events": _metric(payload, "duplicate_claim_events", []),
        "claim_reclaim_events": _metric(payload, "claim_reclaim_events", []),
        "unknown_jobs_modified": _metric(payload, "unknown_jobs_modified"),
        "active_leases_end": payload.get("active_leases_end", _metric(payload, "active_leases_end")),
        "stale_leases_end": payload.get("stale_leases_end", _metric(payload, "stale_leases_end")),
        "db_disconnect_count": payload["metrics"]["db_disconnect_count"],
        "db_reconnect_count": payload["metrics"]["db_reconnect_count"],
        "db_reconnect_events": payload["metrics"]["db_reconnect_events"],
        "real_execution_count": payload["real_execution_count"],
        "provider_call_count": payload["provider_call_count"],
        "rag_query_count": payload["rag_query_count"],
        "extractor_call_count": payload["extractor_call_count"],
        "fusion_result_write_count": payload["fusion_result_write_count"],
        "blocking_issues": payload["blocking_issues"],
    }
    for name, value in {
        "company_v2_phase6ts_gate.json": gate_payload,
        "company_v2_phase6ts_gate.md": gate_payload,
        "company_v2_phase6ts_worker_restart.json": restart_payload,
        "company_v2_phase6ts_worker_restart.md": restart_payload,
        "company_v2_phase6ts_db_reconnect.json": reconnect_payload,
        "company_v2_phase6ts_db_reconnect.md": reconnect_payload,
    }.items():
        path = base / name
        if path.suffix == ".json":
            _atomic_write_text(path, json.dumps(_sanitize(value), ensure_ascii=False, indent=2))
        else:
            _atomic_write_text(path, "# Phase 6T-S Secondary Artifact\n\n```json\n" + json.dumps(_sanitize(value), ensure_ascii=False, indent=2) + "\n```\n")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out_json, out_md = args.out_json, args.out_md
    if not out_json or not out_md:
        default_json, default_md = _default_paths(args.base_artifact_dir)
        out_json = out_json or default_json
        out_md = out_md or default_md
    run_id = uuid.uuid4().hex
    started_at = _now()
    started_monotonic = perf_counter()
    process_pid = os.getpid()
    git_commit = _git_commit()
    payload: dict[str, Any] | None = None
    _write_artifacts(
        _running_payload(
            run_id=run_id,
            started_at=started_at,
            requested_duration_seconds=float(args.duration_seconds),
            process_pid=process_pid,
            git_commit=git_commit,
        ),
        out_json=out_json,
        out_md=out_md,
    )
    try:
        payload = asyncio.run(
            run_soak(
                args,
                run_id=run_id,
                started_at=started_at,
                process_pid=process_pid,
                git_commit=git_commit,
            )
        )
    except Exception as exc:  # noqa: BLE001
        metrics = SoakMetrics(duration_seconds=int(args.duration_seconds), worker_count=int(args.worker_count))
        metrics.errors.append(_error_payload("SOAK_MAIN_EXCEPTION", exc))
        blocking_issues = ["SOAK_MAIN_EXCEPTION"]
        payload = _build_payload(
            status="failed",
            run_id=run_id,
            symbols=[item.strip() for item in (args.symbols or ",".join(DEFAULT_SYMBOLS)).split(",") if item.strip()],
            created_jobs=[],
            metrics=metrics,
            blocking_issues=blocking_issues,
            started_at=started_at,
            finished_at=_now(),
            requested_duration_seconds=float(args.duration_seconds),
            actual_duration_seconds=perf_counter() - started_monotonic,
            exit_reason="exception",
            process_pid=process_pid,
            git_commit=git_commit,
        )
    finally:
        if payload is not None:
            with contextlib.suppress(Exception):
                _write_artifacts(payload, out_json=out_json, out_md=out_md)
                _secondary_artifacts(payload, args.base_artifact_dir)
    print(json.dumps({"status": payload["status"], "real_execution_count": payload["real_execution_count"]}, ensure_ascii=False))
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
