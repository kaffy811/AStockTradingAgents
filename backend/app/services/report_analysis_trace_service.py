"""Failure-safe durable trace recorder for the Report Chat S0-S8 pipeline."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy import text

log = logging.getLogger(__name__)

PIPELINE_VERSION = "report_chat_s0_s8_v1"
RETENTION_DAYS = 30
MAX_TEXT_CHARS = 12_000
_SECRET_KEY_RE = re.compile(
    r"(?i)^(authorization|cookie|set-cookie|api[_-]?key|client[_-]?secret|"
    r"access[_-]?token|refresh[_-]?token|auth[_-]?token|password|connection[_-]?string)$"
)
_BEARER_RE = re.compile(r"(?i)bearer\s+[a-z0-9._~+/-]+=*")
_URL_SECRET_RE = re.compile(r"(?i)(postgres(?:ql)?(?:\+asyncpg)?://)[^\s]+")


def stable_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def redact(value: Any, *, max_text_chars: int = MAX_TEXT_CHARS) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _SECRET_KEY_RE.search(str(key)) else redact(item, max_text_chars=max_text_chars)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item, max_text_chars=max_text_chars) for item in value]
    if isinstance(value, str):
        cleaned = _BEARER_RE.sub("Bearer [REDACTED]", value)
        cleaned = _URL_SECRET_RE.sub(r"\1[REDACTED]", cleaned)
        return cleaned[:max_text_chars]
    return value


class TraceRepository(Protocol):
    async def create_trace(self, payload: dict[str, Any]) -> None: ...
    async def upsert_stage(self, trace_id: uuid.UUID, stage_name: str, payload: dict[str, Any]) -> None: ...
    async def finalize_trace(self, trace_id: uuid.UUID, payload: dict[str, Any]) -> None: ...


class PostgresTraceRepository:
    """Internal-only repository; no public read endpoint is registered."""

    async def create_trace(self, payload: dict[str, Any]) -> None:
        from app.core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await session.execute(text("""
                INSERT INTO report_analysis_traces
                    (trace_id, request_id, pipeline_version, git_sha, runtime_image_identity,
                     session_hash, question_redacted, question_hash, market, symbol,
                     requested_report_id, requested_years, final_status, partial,
                     trace_persistence_failed, started_at, expires_at)
                VALUES
                    (:trace_id, :request_id, :pipeline_version, :git_sha, :runtime_image_identity,
                     :session_hash, :question_redacted, :question_hash, :market, :symbol,
                     :requested_report_id, CAST(:requested_years AS jsonb), 'started', false,
                     false, :started_at, :expires_at)
            """), {**payload, "requested_years": json.dumps(payload["requested_years"])})
            await session.commit()

    async def upsert_stage(self, trace_id: uuid.UUID, stage_name: str, payload: dict[str, Any]) -> None:
        from app.core.database import AsyncSessionLocal
        params = {**payload, "trace_id": trace_id, "stage_name": stage_name, "payload": json.dumps(payload.get("payload") or {}, ensure_ascii=False, default=str)}
        async with AsyncSessionLocal() as session:
            await session.execute(text("""
                INSERT INTO report_analysis_trace_stages
                    (trace_id, stage_name, started_at, completed_at, duration_ms, status,
                     error_code, input_hash, output_hash, payload)
                VALUES
                    (:trace_id, :stage_name, :started_at, :completed_at, :duration_ms, :status,
                     :error_code, :input_hash, :output_hash, CAST(:payload AS jsonb))
                ON CONFLICT (trace_id, stage_name) DO UPDATE SET
                    completed_at=EXCLUDED.completed_at, duration_ms=EXCLUDED.duration_ms,
                    status=EXCLUDED.status, error_code=EXCLUDED.error_code,
                    input_hash=COALESCE(EXCLUDED.input_hash, report_analysis_trace_stages.input_hash),
                    output_hash=EXCLUDED.output_hash, payload=EXCLUDED.payload
            """), params)
            await session.commit()

    async def finalize_trace(self, trace_id: uuid.UUID, payload: dict[str, Any]) -> None:
        from app.core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await session.execute(text("""
                UPDATE report_analysis_traces SET final_status=:final_status, partial=:partial,
                    trace_persistence_failed=:trace_persistence_failed, completed_at=:completed_at
                WHERE trace_id=:trace_id
            """), {**payload, "trace_id": trace_id})
            await session.commit()


@dataclass
class ReportAnalysisTraceRecorder:
    request_id: str
    repository: TraceRepository = field(default_factory=PostgresTraceRepository)
    trace_id: uuid.UUID = field(default_factory=uuid.uuid4)
    persistence_failed: bool = False
    _started: dict[str, tuple[dt.datetime, float, str | None]] = field(default_factory=dict)

    async def initialize(self, *, question: str, session_id: str | None, market: str, symbol: str,
                         report_id: int | None, years: list[int] | None) -> None:
        now = dt.datetime.now(dt.timezone.utc)
        payload = {
            "trace_id": self.trace_id, "request_id": self.request_id,
            "pipeline_version": PIPELINE_VERSION,
            "git_sha": os.getenv("GIT_SHA") or os.getenv("RELEASE_SHA"),
            "runtime_image_identity": os.getenv("IMAGE_DIGEST") or os.getenv("HOSTNAME"),
            "session_hash": stable_hash(session_id) if session_id else None,
            "question_redacted": redact(question, max_text_chars=500),
            "question_hash": stable_hash(question), "market": market, "symbol": symbol,
            "requested_report_id": report_id, "requested_years": years or [],
            "started_at": now, "expires_at": now + dt.timedelta(days=RETENTION_DAYS),
        }
        await self._safe("create", self.repository.create_trace(payload))

    async def start(self, stage: str, input_data: Any = None) -> None:
        now = dt.datetime.now(dt.timezone.utc)
        input_hash = stable_hash(redact(input_data)) if input_data is not None else None
        self._started[stage] = (now, time.perf_counter(), input_hash)
        await self._safe("stage_started", self.repository.upsert_stage(self.trace_id, stage, {
            "started_at": now, "completed_at": None, "duration_ms": None, "status": "started",
            "error_code": None, "input_hash": input_hash, "output_hash": None,
            "payload": {"event": "stage_started"},
        }))

    async def finish(self, stage: str, *, status: str = "completed", error_code: str | None = None,
                     output_data: Any = None, payload: dict[str, Any] | None = None) -> None:
        now = dt.datetime.now(dt.timezone.utc)
        started, perf_started, input_hash = self._started.get(stage, (now, time.perf_counter(), None))
        clean_output = redact(output_data) if output_data is not None else None
        await self._safe("stage_finished", self.repository.upsert_stage(self.trace_id, stage, {
            "started_at": started, "completed_at": now,
            "duration_ms": max(0, int((time.perf_counter() - perf_started) * 1000)),
            "status": status, "error_code": error_code, "input_hash": input_hash,
            "output_hash": stable_hash(clean_output) if clean_output is not None else None,
            "payload": redact(payload or {}),
        }))
        self._started.pop(stage, None)

    async def finalize(self, result: dict[str, Any]) -> None:
        await self._safe("finalize", self.repository.finalize_trace(self.trace_id, {
            "final_status": str(result.get("status") or "completed"),
            "partial": bool(result.get("partial")),
            "trace_persistence_failed": self.persistence_failed,
            "completed_at": dt.datetime.now(dt.timezone.utc),
        }))

    async def fail_active(self, error_code: str) -> None:
        active = [stage for stage in self._started if stage]
        if active:
            await self.finish(active[-1], status="failed", error_code=error_code,
                              payload={"trace_persistence_failed": self.persistence_failed})

    async def skip(self, stage: str, reason: str) -> None:
        await self.start(stage, {"skip_reason": reason})
        await self.finish(stage, status="skipped", error_code=reason, payload={"skip_reason": reason})

    async def _safe(self, operation: str, awaitable: Any) -> None:
        try:
            await awaitable
        except Exception as exc:
            self.persistence_failed = True
            log.error("report trace persistence failed request_id=%s trace_id=%s operation=%s error=%s",
                      self.request_id, self.trace_id, operation, type(exc).__name__)


def numeric_token_contexts(answer: str, tokens: list[str]) -> list[dict[str, Any]]:
    sentences = [part.strip() for part in re.split(r"(?<=[。！？!?；;\n])", answer or "") if part.strip()]
    output = []
    for token in tokens:
        normalized = str(token).replace(",", "")
        sentence = next((item for item in sentences if str(token) in item or normalized in item.replace(",", "")), "")
        output.append({"token": str(token), "token_context_sentence": sentence[:1000], "first_observed_stage": "S6"})
    return output


def numeric_token_provenance(answer: str, tokens: list[str], stage_sources: dict[str, Any]) -> list[dict[str, Any]]:
    contexts = {item["token"]: item["token_context_sentence"] for item in numeric_token_contexts(answer, tokens)}
    ordered_stages = ("S0", "S1", "S2", "S3", "S4", "S5", "S6")
    output = []
    for token in tokens:
        raw_token = str(token)
        compact = raw_token.replace(",", "")
        first = "S6"
        for stage in ordered_stages:
            text_value = json.dumps(stage_sources.get(stage), ensure_ascii=False, default=str)
            if raw_token in text_value or compact in text_value.replace(",", ""):
                first = stage
                break
        output.append({
            "token": raw_token,
            "token_context_sentence": contexts.get(raw_token, ""),
            "first_observed_stage": first,
        })
    return output


def final_response_audit_payload(result: dict[str, Any]) -> dict[str, Any]:
    sources = result.get("source_chunks") or []
    return redact({
        "status": result.get("status"), "partial": bool(result.get("partial")),
        "error_code": result.get("error_code"), "errors": result.get("errors") or [],
        "answer": result.get("answer") or "",
        "numeric_validation": result.get("numeric_validation"),
        "review_audit": result.get("review_audit"),
        "source_chunk_ids": [item.get("chunk_id") for item in sources if isinstance(item, dict)],
        "rag_status": result.get("rag_status"),
    })
