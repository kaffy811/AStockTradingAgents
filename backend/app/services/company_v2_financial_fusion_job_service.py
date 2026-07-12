"""DB-backed manual jobs for Company V2 financial fusion."""
from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from time import perf_counter

from sqlalchemy import insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text

from app.core.config import settings
from app.core.database import AsyncSessionLocal, async_engine, Base
from app.models.company_v2_financial_fusion_job import CompanyV2FinancialFusionJob
from app.models.report_document import ReportDocument
from app.services.company_v2_financial_evidence_fusion_service import (
    DEFAULT_FUSION_FIELDS,
    company_v2_financial_evidence_fusion_service,
)
from app.services.company_v2_financial_fusion_circuit_breaker import company_v2_financial_fusion_circuit_breaker
from app.services.company_v2_financial_fusion_rollout_service import company_v2_financial_fusion_rollout_service
from app.services.company_v2_official_field_extractor import OFFICIAL_EXTRACTOR_VERSION
from app.services.company_v2_report_rag_index_service import company_v2_report_rag_index_service


JOB_TERMINAL_STATUSES = {"completed", "partial", "failed", "cancelled", "timed_out"}
ACTIVE_JOB_INDEX_SQL = text(
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_company_v2_financial_fusion_jobs_active_fingerprint
    ON company_v2_financial_fusion_jobs (request_fingerprint)
    WHERE status IN ('queued', 'running')
    """
)
STAGE_PROGRESS = {
    "queued": 0.0,
    "eligibility": 0.05,
    "readiness": 0.08,
    "validating_readiness": 0.08,
    "cache_lookup": 0.18,
    "structured_data_load": 0.28,
    "rag_retrieval": 0.38,
    "official_evidence_extract": 0.5,
    "unit_normalization": 0.6,
    "field_alignment": 0.7,
    "classification": 0.8,
    "citation_validation": 0.88,
    "result_persistence": 0.95,
    "completed": 1.0,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _symbol_from_ts_code(ts_code: str | None) -> str:
    return (ts_code or "").split(".")[0]


def _report_source_url(doc: ReportDocument) -> str:
    return doc.pdf_url or doc.source_url or ""


def _find_sidecar(doc: ReportDocument) -> Path | None:
    if doc.local_path:
        sidecar = Path(doc.local_path).with_suffix(".pages.json")
        if sidecar.exists():
            return sidecar
    for base in (Path("/tmp/report_pdfs"), Path("/tmp/company_v2_report_pdfs")):
        for candidate in base.glob(f"*{doc.id}_*.pages.json"):
            if candidate.exists():
                return candidate
    return None


def _fingerprint(*, symbol: str, report_id: int, fields: list[str], refresh: bool) -> str:
    field_key = ",".join(sorted(dict.fromkeys(fields)))
    payload = f"{symbol}|{int(report_id)}|{field_key}|refresh={bool(refresh)}|{OFFICIAL_EXTRACTOR_VERSION}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sanitize_result(payload: dict[str, Any]) -> dict[str, Any]:
    blocked = {"local_path", "sidecar_path", "database_url", "traceback", "stack"}
    if isinstance(payload, dict):
        return {k: _sanitize_result(v) if isinstance(v, dict) else [_sanitize_result(i) if isinstance(i, dict) else i for i in v] if isinstance(v, list) else v for k, v in payload.items() if k not in blocked}
    return payload


class CompanyV2FinancialFusionJobService:
    def __init__(self) -> None:
        self._schema_ready = False
        self._schema_lock = threading.Lock()

    async def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            if async_engine.url.get_backend_name() == "postgresql":
                await conn.execute(ACTIVE_JOB_INDEX_SQL)
        self._schema_ready = True

    @staticmethod
    def _row_to_status(row: CompanyV2FinancialFusionJob) -> dict[str, Any]:
        terminal = row.status in JOB_TERMINAL_STATUSES
        return {
            "job_id": row.job_id,
            "symbol": row.symbol,
            "report_id": row.report_id,
            "report_year": row.report_year,
            "requested_fields": _json_loads(row.requested_fields_json, []),
            "requester_scope": row.requester_scope,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "status": row.status,
            "progress": row.progress,
            "current_stage": row.current_stage,
            "cache_hit": bool(row.cache_hit),
            "result_id": row.result_id,
            "error_code": row.error_code,
            "retryable": bool(row.retryable),
            "repository_backend": row.repository_backend,
            "extractor_version": row.extractor_version,
            "active_generation": row.active_generation,
            "poll_after_ms": 1000 if not terminal else 0,
            "retry_after_ms": 1000 if not terminal else 0,
            "terminal": terminal,
        }

    async def create_job(
        self,
        *,
        db: AsyncSession,
        market: str,
        symbol: str,
        report: ReportDocument,
        fields: list[str] | None,
        refresh: bool,
        requester_scope: str = "manual",
        force_enabled: bool = False,
        manual_admission: bool | None = None,
        trace: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        trace = trace if trace is not None else {}
        await self.ensure_schema()
        selected_fields = list(fields or DEFAULT_FUSION_FIELDS)
        manual_admission = requester_scope == "manual" if manual_admission is None else bool(manual_admission)
        started = perf_counter()
        rollout = company_v2_financial_fusion_rollout_service.evaluate(
            symbol=symbol,
            report_id=int(report.id),
            report_ready=True,
            rag_ready=True,
            structured_ready=True,
            force_enabled=force_enabled,
            manual_admission=manual_admission,
            supported_fields=selected_fields,
        )
        trace["allowlist_check_ms"] = round((perf_counter() - started) * 1000, 2)
        if not rollout.get("eligible"):
            return {
                "ok": False,
                "status": "ineligible",
                "error_code": rollout.get("reason") or "NOT_IN_ALLOWLIST",
                "eligible": False,
                "rollout": rollout,
                "poll_after_ms": 0,
            }
        fingerprint = _fingerprint(symbol=symbol, report_id=int(report.id), fields=selected_fields, refresh=refresh)
        job_id = str(uuid.uuid4())
        created_at = _now().replace(tzinfo=None)
        insert_values = {
            "job_id": job_id,
            "market": market.upper(),
            "symbol": symbol,
            "report_id": int(report.id),
            "report_year": int(report.report_year or 0),
            "report_type": report.report_type or "annual",
            "requested_fields_json": json.dumps(selected_fields, ensure_ascii=False),
            "request_fingerprint": fingerprint,
            "requester_scope": requester_scope,
            "status": "queued",
            "progress": STAGE_PROGRESS["queued"],
            "current_stage": "queued",
            "repository_backend": str(getattr(company_v2_report_rag_index_service.repository, "backend", "database")),
            "extractor_version": OFFICIAL_EXTRACTOR_VERSION,
            "active_generation": None,
            "requester_metadata_json": json.dumps({"manual_only": True, "refresh": refresh}, ensure_ascii=False),
            "created_at": created_at,
            "updated_at": created_at,
        }
        dialect_name = getattr(getattr(getattr(db, "bind", None), "dialect", None), "name", None)
        if dialect_name == "postgresql":
            stmt = (
                pg_insert(CompanyV2FinancialFusionJob)
                .values(**insert_values)
                .on_conflict_do_nothing(
                    index_elements=[CompanyV2FinancialFusionJob.request_fingerprint],
                    index_where=CompanyV2FinancialFusionJob.status.in_(["queued", "running"]),
                )
                .returning(CompanyV2FinancialFusionJob.job_id)
            )
            started = perf_counter()
            inserted_job_id = (await db.execute(stmt)).scalar_one_or_none()
            trace["insert_ms"] = round((perf_counter() - started) * 1000, 2)
            if inserted_job_id is None:
                started = perf_counter()
                running = (
                    await db.execute(
                        select(
                            CompanyV2FinancialFusionJob.job_id,
                            CompanyV2FinancialFusionJob.symbol,
                            CompanyV2FinancialFusionJob.report_id,
                            CompanyV2FinancialFusionJob.report_year,
                            CompanyV2FinancialFusionJob.requested_fields_json,
                            CompanyV2FinancialFusionJob.requester_scope,
                            CompanyV2FinancialFusionJob.created_at,
                            CompanyV2FinancialFusionJob.started_at,
                            CompanyV2FinancialFusionJob.completed_at,
                            CompanyV2FinancialFusionJob.status,
                            CompanyV2FinancialFusionJob.progress,
                            CompanyV2FinancialFusionJob.current_stage,
                            CompanyV2FinancialFusionJob.cache_hit,
                            CompanyV2FinancialFusionJob.result_id,
                            CompanyV2FinancialFusionJob.error_code,
                            CompanyV2FinancialFusionJob.retryable,
                            CompanyV2FinancialFusionJob.repository_backend,
                            CompanyV2FinancialFusionJob.extractor_version,
                            CompanyV2FinancialFusionJob.active_generation,
                        ).where(
                            CompanyV2FinancialFusionJob.symbol == symbol,
                            CompanyV2FinancialFusionJob.report_id == int(report.id),
                            CompanyV2FinancialFusionJob.request_fingerprint == fingerprint,
                            CompanyV2FinancialFusionJob.status.in_(["queued", "running"]),
                        )
                    )
                ).first()
                trace["active_job_dedup_query_ms"] = round((perf_counter() - started) * 1000, 2)
                if running:
                    payload = {
                        "job_id": running.job_id,
                        "symbol": running.symbol,
                        "report_id": running.report_id,
                        "report_year": running.report_year,
                        "requested_fields": _json_loads(running.requested_fields_json, []),
                        "requester_scope": running.requester_scope,
                        "created_at": running.created_at.isoformat() if running.created_at else None,
                        "started_at": running.started_at.isoformat() if running.started_at else None,
                        "completed_at": running.completed_at.isoformat() if running.completed_at else None,
                        "status": running.status,
                        "progress": running.progress,
                        "current_stage": running.current_stage,
                        "cache_hit": bool(running.cache_hit),
                        "result_id": running.result_id,
                        "error_code": running.error_code,
                        "retryable": bool(running.retryable),
                        "repository_backend": running.repository_backend,
                        "extractor_version": running.extractor_version,
                        "active_generation": running.active_generation,
                        "poll_after_ms": 1000 if running.status not in JOB_TERMINAL_STATUSES else 0,
                        "retry_after_ms": 1000 if running.status not in JOB_TERMINAL_STATUSES else 0,
                        "terminal": running.status in JOB_TERMINAL_STATUSES,
                        "ok": True,
                        "duplicate": True,
                        "estimated_wait_seconds": 30,
                    }
                    started = perf_counter()
                    await db.commit()
                    trace["commit_ms"] = round((perf_counter() - started) * 1000, 2)
                    return payload
        else:
            started = perf_counter()
            await db.execute(
                insert(CompanyV2FinancialFusionJob).values(**insert_values)
            )
            trace["insert_ms"] = round((perf_counter() - started) * 1000, 2)
            trace["active_job_dedup_query_ms"] = 0.0
        started = perf_counter()
        await db.commit()
        trace["commit_ms"] = round((perf_counter() - started) * 1000, 2)
        payload = {
            "job_id": job_id,
            "symbol": symbol,
            "report_id": int(report.id),
            "report_year": int(report.report_year or 0),
            "requested_fields": selected_fields,
            "requester_scope": requester_scope,
            "created_at": created_at.isoformat(),
            "started_at": None,
            "completed_at": None,
            "status": "queued",
            "progress": STAGE_PROGRESS["queued"],
            "current_stage": "queued",
            "cache_hit": False,
            "result_id": None,
            "error_code": None,
            "retryable": False,
            "repository_backend": str(getattr(company_v2_report_rag_index_service.repository, "backend", "database")),
            "extractor_version": OFFICIAL_EXTRACTOR_VERSION,
            "active_generation": None,
            "poll_after_ms": 1000,
            "retry_after_ms": 1000,
            "terminal": False,
            "ok": True,
            "estimated_wait_seconds": 30,
        }
        return payload

    async def _set_status(self, db: AsyncSession, job_id: str, *, status: str, stage: str, **values: Any) -> None:
        payload = {
            "status": status,
            "current_stage": stage,
            "progress": STAGE_PROGRESS.get(stage, values.pop("progress", 0.0)),
            "updated_at": _now().replace(tzinfo=None),
            **values,
        }
        await db.execute(update(CompanyV2FinancialFusionJob).where(CompanyV2FinancialFusionJob.job_id == job_id).values(**payload))
        await db.commit()

    async def run_job(self, job_id: str) -> None:
        await self.ensure_schema()
        async with AsyncSessionLocal() as db:
            row = (await db.execute(select(CompanyV2FinancialFusionJob).where(CompanyV2FinancialFusionJob.job_id == job_id))).scalars().first()
            if not row or row.status != "queued":
                return
            await self._set_status(db, job_id, status="running", stage="validating_readiness", started_at=_now().replace(tzinfo=None))
            report = (await db.execute(select(ReportDocument).where(ReportDocument.id == row.report_id))).scalars().first()
            if not report or _symbol_from_ts_code(report.ts_code) != row.symbol:
                await self._set_status(db, job_id, status="failed", stage="completed", error_code="REPORT_NOT_FOUND", retryable=0, completed_at=_now().replace(tzinfo=None))
                return
            sidecar = _find_sidecar(report)
            if not sidecar:
                await self._set_status(db, job_id, status="failed", stage="completed", error_code="REPORT_NOT_READY", retryable=1, completed_at=_now().replace(tzinfo=None))
                return
            try:
                rag_status = company_v2_report_rag_index_service.status(row.report_id)
            except Exception:
                rag_status = {}
            rag_state = str(rag_status.get("status") or report.rag_status or "pending")
            if rag_state not in {"indexed", "partial"}:
                await self._set_status(db, job_id, status="failed", stage="completed", error_code="RAG_NOT_INDEXED", retryable=1, completed_at=_now().replace(tzinfo=None))
                return
            if not company_v2_financial_fusion_circuit_breaker.allow():
                await self._set_status(db, job_id, status="failed", stage="completed", error_code="CIRCUIT_OPEN", retryable=1, completed_at=_now().replace(tzinfo=None))
                return
            fields = _json_loads(row.requested_fields_json, list(DEFAULT_FUSION_FIELDS))
            refresh = bool((_json_loads(row.requester_metadata_json, {}) or {}).get("refresh"))
            timeout_seconds = int(getattr(settings, "company_v2_financial_fusion_timeout_seconds", 60))

        async def _compute() -> dict[str, Any]:
            for stage in ["cache_lookup", "structured_data_load", "rag_retrieval", "official_evidence_extract", "unit_normalization", "field_alignment", "classification", "citation_validation"]:
                async with AsyncSessionLocal() as stage_db:
                    await self._set_status(stage_db, job_id, status="running", stage=stage)
            return await asyncio.to_thread(
                company_v2_financial_evidence_fusion_service.run,
                market=row.market,
                symbol=row.symbol,
                report_id=row.report_id,
                report_year=int(row.report_year or 0),
                report_type=row.report_type or "annual",
                fields=fields,
                refresh=refresh,
                sidecar_path=sidecar,
                source_url=_report_source_url(report),
                pdf_hash=report.file_sha256,
                parse_version=report.parse_status or "parsed",
                embedding_version=company_v2_report_rag_index_service.status(row.report_id).get("embedding_version"),
                report_ready=True,
                rag_ready=True,
                structured_ready=True,
                enforce_rollout=True,
                force_enabled=True,
                idempotency_key=row.request_fingerprint,
                request_id=job_id,
                timeout_seconds=timeout_seconds,
            )

        try:
            result = await asyncio.wait_for(_compute(), timeout=timeout_seconds + 10)
        except asyncio.TimeoutError:
            company_v2_financial_fusion_circuit_breaker.trip("fusion_job_timeout")
            async with AsyncSessionLocal() as db:
                await self._set_status(db, job_id, status="timed_out", stage="completed", error_code="FUSION_TIMEOUT", retryable=1, completed_at=_now().replace(tzinfo=None))
            return
        except Exception as exc:  # noqa: BLE001
            async with AsyncSessionLocal() as db:
                await self._set_status(db, job_id, status="failed", stage="completed", error_code="INTERNAL_ERROR", error_message=str(exc)[:300], retryable=1, completed_at=_now().replace(tzinfo=None))
            return

        sanitized = _sanitize_result(result)
        status = "completed" if sanitized.get("ok", True) and sanitized.get("status") not in {"failed", "timed_out"} else "partial"
        async with AsyncSessionLocal() as db:
            await self._set_status(
                db,
                job_id,
                status=status,
                stage="completed",
                cache_hit=1 if sanitized.get("cache_hit") else 0,
                result_id=f"{row.symbol}:{row.report_id}:{row.job_id}",
                result_json=json.dumps(sanitized, ensure_ascii=False),
                cache_key=(sanitized.get("cache_context") or {}).get("cache_key"),
                cache_key_version=sanitized.get("cache_key_version"),
                timings_json=json.dumps(sanitized.get("timings") or {}, ensure_ascii=False),
                completed_at=_now().replace(tzinfo=None),
            )

    async def get_job(self, *, db: AsyncSession, job_id: str, symbol: str, report_id: int | None = None) -> dict[str, Any] | None:
        stmt = select(CompanyV2FinancialFusionJob).where(CompanyV2FinancialFusionJob.job_id == job_id, CompanyV2FinancialFusionJob.symbol == symbol)
        if report_id is not None:
            stmt = stmt.where(CompanyV2FinancialFusionJob.report_id == int(report_id))
        row = (await db.execute(stmt)).scalars().first()
        return self._row_to_status(row) if row else None

    async def get_result(self, *, db: AsyncSession, job_id: str, symbol: str) -> dict[str, Any] | None:
        row = (
            await db.execute(
                select(CompanyV2FinancialFusionJob).where(
                    CompanyV2FinancialFusionJob.job_id == job_id,
                    CompanyV2FinancialFusionJob.symbol == symbol,
                )
            )
        ).scalars().first()
        if not row:
            return None
        status = self._row_to_status(row)
        if row.status not in {"completed", "partial"} or not row.result_json:
            return {"ok": False, **status, "error_code": row.error_code or "JOB_NOT_COMPLETED"}
        return {"ok": True, **status, "result": _json_loads(row.result_json, {})}

    async def cancel_job(self, *, db: AsyncSession, job_id: str, symbol: str) -> dict[str, Any] | None:
        row = (
            await db.execute(
                select(CompanyV2FinancialFusionJob).where(
                    CompanyV2FinancialFusionJob.job_id == job_id,
                    CompanyV2FinancialFusionJob.symbol == symbol,
                )
            )
        ).scalars().first()
        if not row:
            return None
        if row.status == "queued":
            row.status = "cancelled"
            row.current_stage = "completed"
            row.progress = 1.0
            row.completed_at = _now().replace(tzinfo=None)
            row.retryable = 0
            row.claimed_by = None
            row.claimed_at = None
            row.heartbeat_at = None
            row.lease_expires_at = None
            row.next_retry_at = None
            await db.commit()
            await db.refresh(row)
        return self._row_to_status(row)


company_v2_financial_fusion_job_service = CompanyV2FinancialFusionJobService()
