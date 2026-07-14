"""Durable shadow worker foundation for Company V2 financial fusion."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
import hashlib
from typing import Any

from sqlalchemy import and_, cast, func, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.company_v2_financial_fusion_job import CompanyV2FinancialFusionJob
from app.models.company_v2_financial_fusion_worker_observation import CompanyV2FinancialFusionWorkerObservation
from app.models.report_document import ReportDocument
from app.services.company_v2_financial_fusion_circuit_breaker import company_v2_financial_fusion_circuit_breaker


WORKER_VERSION = "phase6tr-shadow-v1"
SHADOW_EXECUTION_MODE = "shadow"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_allowlist(value: str | None) -> set[str]:
    return {item.strip() for item in (value or "").split(",") if item.strip()}


def _symbol_from_ts_code(ts_code: str | None) -> str:
    return (ts_code or "").split(".")[0]


def _stable_bucket(symbol: str, report_id: int) -> int:
    digest = hashlib.sha256(f"{symbol}:{int(report_id)}:financial_fusion".encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def _requester_run_id(metadata_json: str | None) -> str | None:
    if not metadata_json:
        return None
    try:
        metadata = json.loads(metadata_json)
    except Exception:
        return None
    if isinstance(metadata, dict):
        run_id = metadata.get("run_id")
        return str(run_id) if run_id else None
    return None


class CompanyV2FinancialFusionWorkerService:
    async def claim_next_job(
        self,
        *,
        db: AsyncSession,
        worker_id: str,
        lease_seconds: int | None = None,
        heartbeat_seconds: int | None = None,
        execution_mode: str = SHADOW_EXECUTION_MODE,
        max_attempts: int | None = None,
        requester_scope: str | None = None,
        requester_run_id: str | None = None,
        allowed_job_ids: list[str] | set[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any] | None:
        lease_seconds = int(lease_seconds or getattr(settings, "company_v2_financial_fusion_worker_lease_seconds", 60))
        heartbeat_seconds = int(heartbeat_seconds or getattr(settings, "company_v2_financial_fusion_worker_heartbeat_seconds", 15))
        max_attempts = int(max_attempts or 3)
        is_shadow = str(execution_mode or SHADOW_EXECUTION_MODE) == SHADOW_EXECUTION_MODE
        allowed_ids = [str(job_id) for job_id in (allowed_job_ids or []) if str(job_id).strip()]
        if allowed_job_ids is not None and not allowed_ids:
            return None
        now = _now()
        lease_expires_at = now + timedelta(seconds=lease_seconds)

        async with db.begin():
            stmt = (
                select(CompanyV2FinancialFusionJob)
                .where(
                    CompanyV2FinancialFusionJob.status == "queued",
                    or_(CompanyV2FinancialFusionJob.next_retry_at.is_(None), CompanyV2FinancialFusionJob.next_retry_at <= now),
                    or_(CompanyV2FinancialFusionJob.lease_expires_at.is_(None), CompanyV2FinancialFusionJob.lease_expires_at <= now),
                )
                .order_by(
                    CompanyV2FinancialFusionJob.created_at.asc(),
                    CompanyV2FinancialFusionJob.id.asc(),
                )
            )
            if not is_shadow:
                stmt = stmt.where(
                    or_(
                        CompanyV2FinancialFusionJob.attempt_count.is_(None),
                        CompanyV2FinancialFusionJob.attempt_count < max_attempts,
                    )
                )
            if requester_scope:
                stmt = stmt.where(CompanyV2FinancialFusionJob.requester_scope == requester_scope)
            if allowed_ids:
                stmt = stmt.where(CompanyV2FinancialFusionJob.job_id.in_(allowed_ids))
            if requester_run_id and getattr(getattr(db, "bind", None), "dialect", None) and db.bind.dialect.name == "postgresql":
                stmt = stmt.where(
                    func.coalesce(
                        func.jsonb_extract_path_text(
                            cast(CompanyV2FinancialFusionJob.requester_metadata_json, JSONB),
                            "run_id",
                        ),
                        "",
                    ) == requester_run_id
                )
            if getattr(getattr(db, "bind", None), "dialect", None) and db.bind.dialect.name == "postgresql":
                stmt = stmt.with_for_update(skip_locked=True)
            row = (await db.execute(stmt.limit(1))).scalars().first()
            if not row:
                return None
            if requester_scope and row.requester_scope != requester_scope:
                raise RuntimeError(
                    f"scope isolation violation: expected requester_scope={requester_scope!r}, got {row.requester_scope!r}"
                )
            if allowed_ids and row.job_id not in set(allowed_ids):
                raise RuntimeError(
                    f"scope isolation violation: job_id {row.job_id!r} not in allowed_job_ids"
                )
            if requester_run_id and _requester_run_id(row.requester_metadata_json) != requester_run_id:
                raise RuntimeError(
                    f"scope isolation violation: run_id mismatch for job_id={row.job_id!r}"
                )
            row.claimed_by = worker_id
            row.claimed_at = now
            row.heartbeat_at = now
            row.lease_expires_at = lease_expires_at
            if not is_shadow:
                row.attempt_count = int(row.attempt_count or 0) + 1
            row.execution_mode = execution_mode
            row.worker_version = WORKER_VERSION
            row.rollout_bucket_at_claim = _stable_bucket(row.symbol, row.report_id)
            row.rollout_percent_at_claim = int(getattr(settings, "company_v2_financial_fusion_rollout_percent", 0) or 0)
            row.auto_run_at_claim = bool(getattr(settings, "company_v2_financial_fusion_auto_run", False))
            row.last_error_message_sanitized = None
            await db.flush()
            return {
                "job_id": row.job_id,
                "symbol": row.symbol,
                "report_id": row.report_id,
                "report_year": row.report_year,
                "requester_scope": row.requester_scope,
                "claimed_by": row.claimed_by,
                "claimed_at": row.claimed_at,
                "heartbeat_at": row.heartbeat_at,
                "lease_expires_at": row.lease_expires_at,
                "attempt_count": row.attempt_count,
                "execution_mode": row.execution_mode,
                "worker_version": row.worker_version,
                "rollout_percent_at_claim": row.rollout_percent_at_claim,
                "auto_run_at_claim": row.auto_run_at_claim,
                "heartbeat_seconds": heartbeat_seconds,
            }

    async def heartbeat(self, *, db: AsyncSession, job_id: str, worker_id: str, lease_seconds: int | None = None) -> dict[str, Any] | None:
        lease_seconds = int(lease_seconds or getattr(settings, "company_v2_financial_fusion_worker_lease_seconds", 60))
        now = _now()
        lease_expires_at = now + timedelta(seconds=lease_seconds)
        async with db.begin():
            result = await db.execute(
                update(CompanyV2FinancialFusionJob)
                .where(
                    CompanyV2FinancialFusionJob.job_id == job_id,
                    CompanyV2FinancialFusionJob.claimed_by == worker_id,
                    CompanyV2FinancialFusionJob.lease_expires_at > now,
                    CompanyV2FinancialFusionJob.status == "queued",
                )
                .values(heartbeat_at=now, lease_expires_at=lease_expires_at, updated_at=now)
                .returning(CompanyV2FinancialFusionJob.job_id)
            )
            updated = result.scalar_one_or_none()
            if not updated:
                return None
            return {"job_id": job_id, "worker_id": worker_id, "heartbeat_at": now.isoformat(), "lease_expires_at": lease_expires_at.isoformat()}

    async def release_claim(
        self,
        *,
        db: AsyncSession,
        job_id: str,
        worker_id: str,
        block_reason: str | None = None,
        observation_payload: dict[str, Any] | None = None,
        backoff_seconds: int | None = None,
    ) -> dict[str, Any] | None:
        now = _now()
        next_retry_at = now + timedelta(seconds=int(backoff_seconds or getattr(settings, "company_v2_financial_fusion_worker_heartbeat_seconds", 15)))
        async with db.begin():
            result = await db.execute(
                update(CompanyV2FinancialFusionJob)
                .where(
                    CompanyV2FinancialFusionJob.job_id == job_id,
                    CompanyV2FinancialFusionJob.claimed_by == worker_id,
                    CompanyV2FinancialFusionJob.lease_expires_at > now,
                    CompanyV2FinancialFusionJob.status == "queued",
                )
                .values(
                    claimed_by=None,
                    claimed_at=None,
                    heartbeat_at=None,
                    lease_expires_at=None,
                    next_retry_at=next_retry_at,
                    last_error_message_sanitized=block_reason[:400] if block_reason else None,
                    updated_at=now,
                )
                .returning(
                    CompanyV2FinancialFusionJob.job_id,
                    CompanyV2FinancialFusionJob.status,
                    CompanyV2FinancialFusionJob.next_retry_at,
                )
            )
            updated = result.first()
            if not updated:
                return None
            if observation_payload is not None:
                observation = CompanyV2FinancialFusionWorkerObservation(
                    job_id=job_id,
                    symbol=str(observation_payload["symbol"]),
                    report_id=int(observation_payload["report_id"]),
                    worker_id=worker_id,
                    observed_at=now,
                    claimed_at=observation_payload.get("claimed_at"),
                    released_at=now,
                    would_execute=bool(observation_payload.get("would_execute")),
                    block_reason=observation_payload.get("block_reason"),
                    allowlist_match=bool(observation_payload.get("allowlist_match")),
                    report_ready=bool(observation_payload.get("report_ready")),
                    rag_ready=bool(observation_payload.get("rag_ready")),
                    structured_ready=bool(observation_payload.get("structured_ready")),
                    circuit_open=bool(observation_payload.get("circuit_open")),
                    auto_run=bool(observation_payload.get("auto_run")),
                    rollout_percent=int(observation_payload.get("rollout_percent") or 0),
                    stage3_authorized=bool(observation_payload.get("stage3_authorized")),
                    worker_version=str(observation_payload.get("worker_version") or WORKER_VERSION),
                    execution_mode=str(observation_payload.get("execution_mode") or SHADOW_EXECUTION_MODE),
                    provider_calls=int(observation_payload.get("provider_calls") or 0),
                    rag_query_calls=int(observation_payload.get("rag_query_calls") or 0),
                    extractor_calls=int(observation_payload.get("extractor_calls") or 0),
                    fusion_calls=int(observation_payload.get("fusion_calls") or 0),
                    sanitized_payload_json=json.dumps(observation_payload.get("sanitized_payload") or {}, ensure_ascii=False),
                )
                db.add(observation)
            return {"job_id": job_id, "next_retry_at": next_retry_at.isoformat(), "updated": True}

    async def evaluate_shadow_job(
        self,
        *,
        db: AsyncSession,
        job: CompanyV2FinancialFusionJob,
        worker_id: str,
        expected_requester_scope: str | None = None,
        expected_requester_run_id: str | None = None,
        allowed_job_ids: set[str] | None = None,
    ) -> dict[str, Any]:
        if allowed_job_ids is not None and job.job_id not in allowed_job_ids:
            raise RuntimeError(f"scope isolation violation: job_id {job.job_id!r} not allowed")
        if expected_requester_scope and job.requester_scope != expected_requester_scope:
            raise RuntimeError(
                f"scope isolation violation: expected requester_scope={expected_requester_scope!r}, got {job.requester_scope!r}"
            )
        if expected_requester_run_id and _requester_run_id(job.requester_metadata_json) != expected_requester_run_id:
            raise RuntimeError(
                f"scope isolation violation: run_id mismatch for job_id={job.job_id!r}"
            )
        result = await db.execute(select(ReportDocument).where(ReportDocument.id == job.report_id))
        report = result.scalars().first()
        if db.in_transaction():
            await db.commit()
        allowlist = _parse_allowlist(getattr(settings, "company_v2_financial_fusion_symbol_allowlist", ""))
        now = _now()
        auto_run = bool(getattr(settings, "company_v2_financial_fusion_auto_run", False))
        rollout_percent = int(getattr(settings, "company_v2_financial_fusion_rollout_percent", 0) or 0)
        stage3_authorized = bool(getattr(settings, "company_v2_financial_fusion_stage3_authorized", False))
        allowlist_match = job.symbol in allowlist
        report_ready = bool(report and _symbol_from_ts_code(report.ts_code) == job.symbol and report.download_status in {"downloaded", "exists"} and (report.local_path is not None or report.pdf_url or report.source_url))
        rag_ready = bool(report and (report.rag_status in {"indexed", "partial"} or (report.chunk_count or 0) > 0))
        structured_ready = bool(report and (report.parsed or report.parse_status in {"parsed", "partial"}))
        circuit_open = not company_v2_financial_fusion_circuit_breaker.allow()
        would_execute = bool(
            allowlist_match
            and report_ready
            and rag_ready
            and structured_ready
            and not circuit_open
            and stage3_authorized
            and auto_run
            and rollout_percent > 0
            and job.status == "queued"
        )
        if not allowlist_match:
            block_reason = "NOT_IN_ALLOWLIST"
        elif not report_ready:
            block_reason = "REPORT_NOT_READY"
        elif not rag_ready:
            block_reason = "RAG_NOT_READY"
        elif not structured_ready:
            block_reason = "STRUCTURED_DATA_UNAVAILABLE"
        elif circuit_open:
            block_reason = "CIRCUIT_OPEN"
        elif not stage3_authorized:
            block_reason = "STAGE3_NOT_AUTHORIZED"
        elif not auto_run:
            block_reason = "AUTO_RUN_DISABLED"
        elif rollout_percent <= 0:
            block_reason = "ROLLOUT_DISABLED"
        else:
            block_reason = None
        observation_payload = {
            "job_id": job.job_id,
            "symbol": job.symbol,
            "report_id": job.report_id,
            "worker_id": worker_id,
            "claimed_at": job.claimed_at,
            "would_execute": would_execute,
            "block_reason": block_reason,
            "allowlist_match": allowlist_match,
            "report_ready": report_ready,
            "rag_ready": rag_ready,
            "structured_ready": structured_ready,
            "circuit_open": circuit_open,
            "auto_run": auto_run,
            "rollout_percent": rollout_percent,
            "stage3_authorized": stage3_authorized,
            "worker_version": WORKER_VERSION,
            "execution_mode": SHADOW_EXECUTION_MODE,
            "provider_calls": 0,
            "rag_query_calls": 0,
            "extractor_calls": 0,
            "fusion_calls": 0,
            "sanitized_payload": {
                "job_id": job.job_id,
                "symbol": job.symbol,
                "report_id": job.report_id,
                "worker_id": worker_id,
                "observed_at": now.isoformat(),
                "would_execute": would_execute,
                "block_reason": block_reason,
                "allowlist_match": allowlist_match,
                "report_ready": report_ready,
                "rag_ready": rag_ready,
                "structured_ready": structured_ready,
                "circuit_open": circuit_open,
                "auto_run": auto_run,
                "rollout_percent": rollout_percent,
                "stage3_authorized": stage3_authorized,
                "worker_version": WORKER_VERSION,
                "execution_mode": SHADOW_EXECUTION_MODE,
                "provider_calls": 0,
                "rag_query_calls": 0,
                "extractor_calls": 0,
                "fusion_calls": 0,
            },
        }
        await self.release_claim(db=db, job_id=job.job_id, worker_id=worker_id, block_reason=block_reason, observation_payload=observation_payload)
        return observation_payload

    async def run_shadow_cycle(
        self,
        *,
        db: AsyncSession,
        worker_id: str,
        lease_seconds: int | None = None,
        heartbeat_seconds: int | None = None,
        max_jobs: int | None = None,
        requester_scope: str | None = None,
        requester_run_id: str | None = None,
        allowed_job_ids: list[str] | set[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        max_jobs = int(max_jobs or 1)
        allowed_ids_set = {str(job_id) for job_id in (allowed_job_ids or []) if str(job_id).strip()}
        if allowed_job_ids is not None and not allowed_ids_set:
            return {
                "worker_id": worker_id,
                "execution_mode": SHADOW_EXECUTION_MODE,
                "claimed_jobs": [],
                "observations": [],
                "real_execution_count": 0,
                "shadow_mode_verified": True,
                "stage3_authorized": bool(getattr(settings, "company_v2_financial_fusion_stage3_authorized", False)),
                "auto_run": bool(getattr(settings, "company_v2_financial_fusion_auto_run", False)),
                "rollout_percent": int(getattr(settings, "company_v2_financial_fusion_rollout_percent", 0) or 0),
            }
        claimed: list[dict[str, Any]] = []
        observations: list[dict[str, Any]] = []
        for _ in range(max_jobs):
            job = await self.claim_next_job(
                db=db,
                worker_id=worker_id,
                lease_seconds=lease_seconds,
                heartbeat_seconds=heartbeat_seconds,
                requester_scope=requester_scope,
                requester_run_id=requester_run_id,
                allowed_job_ids=allowed_ids_set or None,
            )
            if not job:
                break
            claimed.append(job)
            loaded_job = await self._load_job(db, job["job_id"])
            if db.in_transaction():
                await db.commit()
            if loaded_job is None:
                raise RuntimeError(f"scope isolation violation: missing job_id={job['job_id']!r}")
            record = await self.evaluate_shadow_job(
                db=db,
                job=loaded_job,
                worker_id=worker_id,
                expected_requester_scope=requester_scope,
                expected_requester_run_id=requester_run_id,
                allowed_job_ids=allowed_ids_set or None,
            )
            observations.append(record)
        return {
            "worker_id": worker_id,
            "execution_mode": SHADOW_EXECUTION_MODE,
            "claimed_jobs": claimed,
            "observations": observations,
            "real_execution_count": 0,
            "shadow_mode_verified": all(not item["would_execute"] for item in observations) if observations else True,
            "stage3_authorized": bool(getattr(settings, "company_v2_financial_fusion_stage3_authorized", False)),
            "auto_run": bool(getattr(settings, "company_v2_financial_fusion_auto_run", False)),
            "rollout_percent": int(getattr(settings, "company_v2_financial_fusion_rollout_percent", 0) or 0),
        }

    async def _load_job(self, db: AsyncSession, job_id: str) -> CompanyV2FinancialFusionJob:
        result = await db.execute(select(CompanyV2FinancialFusionJob).where(CompanyV2FinancialFusionJob.job_id == job_id))
        row = result.scalars().first()
        if not row:
            raise RuntimeError(f"job {job_id} not found")
        return row


company_v2_financial_fusion_worker_service = CompanyV2FinancialFusionWorkerService()
