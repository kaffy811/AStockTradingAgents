"""Company V2 single-report RAG API."""
from __future__ import annotations

import asyncio
from pathlib import Path as FsPath
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Header, Path
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.report_document import ReportDocument
from app.services.company_v2_report_comparison_answer_service import (
    company_v2_report_comparison_answer_service,
)
from app.services.company_v2_financial_evidence_fusion_service import (
    company_v2_financial_evidence_fusion_service,
)
from app.services.company_v2_financial_fusion_circuit_breaker import company_v2_financial_fusion_circuit_breaker
from app.services.company_v2_financial_fusion_health_service import company_v2_financial_fusion_health_service
from app.services.company_v2_financial_fusion_metrics import company_v2_financial_fusion_metrics
from app.services.company_v2_financial_fusion_rollout_service import company_v2_financial_fusion_rollout_service
from app.services.company_v2_report_rag_answer_service import company_v2_report_rag_answer_service
from app.services.company_v2_report_rag_index_manager import company_v2_report_rag_index_manager
from app.services.company_v2_report_rag_index_service import (
    ReportDescriptor,
    company_v2_report_rag_index_service,
)


router = APIRouter(
    prefix="/api/v2/company/{market}/{symbol}/reports",
    tags=["company-v2-report-rag"],
)


class ReportRagQueryBody(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    top_k: int = Field(default=6, ge=1, le=12)
    answer_style: str = Field(default="concise")
    language: str = Field(default="zh")


class ReportComparisonRequest(BaseModel):
    report_ids: list[int] = Field(..., min_length=2, max_length=4)
    question: str = Field(..., min_length=1, max_length=500)
    comparison_mode: str = Field(default="generic_comparison")
    top_k_per_report: int = Field(default=4, ge=1, le=8)
    answer_style: str = Field(default="concise")


class FinancialFusionRunRequest(BaseModel):
    fields: list[str] = Field(default_factory=list)
    refresh: bool = Field(default=False)


def _json(payload: dict[str, Any], status_code: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status_code)


def _symbol_from_ts_code(ts_code: str | None) -> str:
    return (ts_code or "").split(".")[0]


def _report_source_url(doc: ReportDocument) -> str:
    return doc.pdf_url or doc.source_url or ""


def _report_ready(doc: ReportDocument) -> bool:
    return bool(doc.parsed and doc.parse_status in {"parsed", "partial"})


def _rag_ready(report_id: int) -> bool:
    return company_v2_report_rag_index_service.status(report_id).get("status") in {"indexed", "partial"}


def _structured_ready(symbol: str, report_id: int, report_year: int | None, report_type: str | None) -> bool:
    structured = company_v2_financial_evidence_fusion_service._load_structured(symbol, report_id, report_year, report_type)  # noqa: SLF001
    return structured.get("source_mode") != "unavailable"


def _find_sidecar(doc: ReportDocument) -> FsPath | None:
    if doc.local_path:
        sidecar = FsPath(doc.local_path).with_suffix(".pages.json")
        if sidecar.exists():
            return sidecar
    for candidate in FsPath("/tmp/company_v2_report_pdfs").glob(f"company_v2_report_{doc.id}_*.pages.json"):
        if candidate.exists():
            return candidate
    return None


async def _load_report(
    *,
    report_id: int,
    market: str,
    symbol: str,
    db: AsyncSession,
) -> ReportDocument:
    result = await db.execute(select(ReportDocument).where(ReportDocument.id == report_id))
    doc: ReportDocument | None = result.scalars().first()
    if not doc:
        raise HTTPException(status_code=404, detail={"error_code": "REPORT_NOT_FOUND", "message": "report_id not found"})
    if _symbol_from_ts_code(doc.ts_code) != symbol:
        raise HTTPException(status_code=409, detail={"error_code": "REPORT_SYMBOL_MISMATCH", "message": "report_id does not belong to this symbol"})
    if market.upper() != "CN":
        raise HTTPException(status_code=400, detail={"error_code": "UNSUPPORTED_MARKET", "message": "Only CN market is supported"})
    return doc


def _descriptor_from_doc(doc: ReportDocument, market: str, symbol: str) -> ReportDescriptor:
    return ReportDescriptor(
        report_id=int(doc.id),
        market=market.upper(),
        symbol=symbol,
        company_name=None,
        report_year=int(doc.report_year or 0),
        report_type=doc.report_type or "annual",
        announcement_date=doc.disclosure_date,
        source_url=_report_source_url(doc),
        pdf_hash=doc.file_sha256,
        report_title=doc.title,
    )


@router.get("/rag/indexes")
async def list_company_v2_report_rag_indexes(
    market: str = Path(...),
    symbol: str = Path(...),
) -> JSONResponse:
    if market.upper() != "CN":
        return _json({"ok": False, "error_code": "UNSUPPORTED_MARKET", "message": "Only CN market is supported"}, 400)
    return _json({"ok": True, "symbol": symbol, "indexes": company_v2_report_rag_index_manager.list_indexes(symbol)})


@router.post("/{report_id}/rag/index")
async def index_company_v2_report_rag(
    market: str = Path(...),
    symbol: str = Path(...),
    report_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    doc = await _load_report(report_id=report_id, market=market, symbol=symbol, db=db)
    if not doc.parsed or doc.parse_status not in {"parsed", "partial"}:
        return _json({"ok": False, "status": "failed", "error_code": "PDF_NOT_PARSED", "message": "PDF must be downloaded and parsed before indexing"}, 412)
    sidecar = _find_sidecar(doc)
    if not sidecar:
        return _json({"ok": False, "status": "failed", "error_code": "PDF_NOT_PARSED", "message": "page sidecar unavailable"}, 412)
    job = company_v2_report_rag_index_manager.enqueue_create_index(_descriptor_from_doc(doc, market, symbol), sidecar)
    return _json({"ok": True, "report_id": report_id, "job_id": job["job_id"], "status": job["status"], "duplicate": job.get("duplicate", False)})


@router.post("/{report_id}/rag/refresh")
async def refresh_company_v2_report_rag(
    market: str = Path(...),
    symbol: str = Path(...),
    report_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    doc = await _load_report(report_id=report_id, market=market, symbol=symbol, db=db)
    if not doc.parsed or doc.parse_status not in {"parsed", "partial"}:
        return _json({"ok": False, "status": "failed", "error_code": "PDF_NOT_PARSED", "message": "PDF must be parsed before refresh"}, 412)
    sidecar = _find_sidecar(doc)
    if not sidecar:
        return _json({"ok": False, "status": "failed", "error_code": "PDF_NOT_PARSED", "message": "page sidecar unavailable"}, 412)
    job = company_v2_report_rag_index_manager.enqueue_refresh_index(_descriptor_from_doc(doc, market, symbol), sidecar)
    return _json({"ok": True, "report_id": report_id, "job_id": job["job_id"], "status": job["status"], "duplicate": job.get("duplicate", False)})


@router.delete("/{report_id}/rag/index")
async def delete_company_v2_report_rag_index(
    market: str = Path(...),
    symbol: str = Path(...),
    report_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    await _load_report(report_id=report_id, market=market, symbol=symbol, db=db)
    result = company_v2_report_rag_index_manager.delete_index(report_id)
    return _json(result, 200 if result.get("ok") else 404)


@router.get("/{report_id}/rag/job")
async def get_company_v2_report_rag_job(
    market: str = Path(...),
    symbol: str = Path(...),
    report_id: int = Path(...),
    job_id: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    await _load_report(report_id=report_id, market=market, symbol=symbol, db=db)
    return _json(company_v2_report_rag_index_manager.get_index_progress(report_id, job_id))


@router.get("/{report_id}/rag/status")
async def get_company_v2_report_rag_status(
    market: str = Path(...),
    symbol: str = Path(...),
    report_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    await _load_report(report_id=report_id, market=market, symbol=symbol, db=db)
    return _json(company_v2_report_rag_index_service.status(report_id))


@router.post("/{report_id}/rag/query")
async def query_company_v2_report_rag(
    body: ReportRagQueryBody = Body(...),
    market: str = Path(...),
    symbol: str = Path(...),
    report_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    doc = await _load_report(report_id=report_id, market=market, symbol=symbol, db=db)
    status = company_v2_report_rag_index_service.status(report_id)
    if status["status"] not in {"indexed", "partial"}:
        return _json({"status": "failed", "error_code": "REPORT_NOT_INDEXED", "message": "Build the report QA index first"}, 409)
    result = company_v2_report_rag_answer_service.answer(
        report_id=report_id,
        question=body.question,
        top_k=body.top_k,
        language=body.language,
        answer_style=body.answer_style,
        symbol=symbol,
        report_year=doc.report_year,
    )
    return _json(result)


@router.post("/rag/compare")
async def compare_company_v2_report_rag(
    body: ReportComparisonRequest = Body(...),
    market: str = Path(...),
    symbol: str = Path(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    if market.upper() != "CN":
        return _json({"ok": False, "error_code": "UNSUPPORTED_MARKET", "message": "Only CN market is supported"}, 400)
    if len(set(body.report_ids)) != len(body.report_ids):
        return _json({"ok": False, "error_code": "DUPLICATE_REPORT_ID", "message": "report_ids must be unique"}, 422)

    docs: list[ReportDocument] = []
    for report_id in body.report_ids:
        result = await db.execute(select(ReportDocument).where(ReportDocument.id == report_id))
        doc: ReportDocument | None = result.scalars().first()
        if not doc:
            return _json({"ok": False, "error_code": "REPORT_NOT_FOUND", "message": "report_id not found"}, 404)
        if _symbol_from_ts_code(doc.ts_code) != symbol:
            return _json({"ok": False, "error_code": "REPORT_SYMBOL_MISMATCH", "message": "report_id does not belong to this symbol"}, 409)
        docs.append(doc)

    indexed_missing = [doc.id for doc in docs if not company_v2_report_rag_index_service.status(doc.id).get("status") in {"indexed", "partial"}]
    if indexed_missing:
        return _json({"ok": False, "error_code": "REPORT_NOT_INDEXED", "message": "All selected reports must be indexed", "missing_report_ids": indexed_missing}, 409)

    result = company_v2_report_comparison_answer_service.answer(
        symbol=symbol,
        report_ids=body.report_ids,
        question=body.question,
        comparison_mode=body.comparison_mode,
        top_k_per_report=body.top_k_per_report,
        answer_style=body.answer_style,
    )
    return _json(result)


@router.post("/{report_id}/financial-fusion/run")
async def run_company_v2_financial_fusion(
    body: FinancialFusionRunRequest = Body(...),
    market: str = Path(...),
    symbol: str = Path(...),
    report_id: int = Path(...),
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    doc = await _load_report(report_id=report_id, market=market, symbol=symbol, db=db)
    report_ready = _report_ready(doc)
    rag_ready = _rag_ready(report_id)
    structured_ready = _structured_ready(symbol, report_id, doc.report_year, doc.report_type)
    supported_fields = body.fields or []
    rollout = company_v2_financial_fusion_rollout_service.evaluate(
        symbol=symbol,
        report_id=report_id,
        report_ready=report_ready,
        rag_ready=rag_ready,
        structured_ready=structured_ready,
        supported_fields=supported_fields,
        cached=False,
        last_run_at=None,
    )
    if not report_ready:
        return _json({"ok": False, "status": "failed", "error_code": "PDF_NOT_PARSED", "message": "PDF must be parsed before fusion"}, 412)
    sidecar = _find_sidecar(doc)
    if not sidecar:
        return _json({"ok": False, "status": "failed", "error_code": "PDF_NOT_PARSED", "message": "page sidecar unavailable"}, 412)
    if not rollout["eligible"]:
        return _json({
            "ok": False,
            "status": "ineligible",
            "reason": rollout["reason"],
            "rollout": rollout,
            "eligible": False,
            "report_ready": report_ready,
            "rag_ready": rag_ready,
            "structured_ready": structured_ready,
        })
    timeout_seconds = int(getattr(settings, "company_v2_financial_fusion_timeout_seconds", 60))
    try:
        payload = await asyncio.wait_for(
            asyncio.to_thread(
                company_v2_financial_evidence_fusion_service.run,
                market=market,
                symbol=symbol,
                report_id=report_id,
                report_year=int(doc.report_year or 0),
                report_type=doc.report_type or "annual",
                fields=body.fields or [],
                refresh=body.refresh,
                sidecar_path=sidecar,
                source_url=_report_source_url(doc),
                pdf_hash=doc.file_sha256,
                parse_version=doc.parse_status or "parsed",
                embedding_version=company_v2_report_rag_index_service.status(report_id).get("embedding_version"),
                structured_data_version=None,
                field_definition_registry_version=getattr(settings, "company_v2_financial_fusion_field_definition_registry_version", "v1"),
                tolerance_version=getattr(settings, "company_v2_financial_fusion_tolerance_version", "v1"),
                report_ready=report_ready,
                rag_ready=rag_ready,
                structured_ready=structured_ready,
                enforce_rollout=True,
                idempotency_key=x_idempotency_key,
                timeout_seconds=timeout_seconds,
            ),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        company_v2_financial_fusion_metrics.inc("fusion_timeout_total")
        company_v2_financial_fusion_circuit_breaker.trip("request_timeout")
        return _json({
            "ok": False,
            "status": "timed_out",
            "reason": "TIMEOUT",
            "timeout_seconds": timeout_seconds,
            "rollout": rollout,
            "eligible": rollout["eligible"],
        }, 504)
    return _json({"ok": True, **payload})


@router.get("/{report_id}/financial-fusion")
async def get_company_v2_financial_fusion(
    market: str = Path(...),
    symbol: str = Path(...),
    report_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    await _load_report(report_id=report_id, market=market, symbol=symbol, db=db)
    return _json({"ok": True, **company_v2_financial_evidence_fusion_service.get(report_id)})


@router.get("/{report_id}/financial-fusion/eligibility")
async def get_company_v2_financial_fusion_eligibility(
    market: str = Path(...),
    symbol: str = Path(...),
    report_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    doc = await _load_report(report_id=report_id, market=market, symbol=symbol, db=db)
    report_ready = _report_ready(doc)
    rag_ready = _rag_ready(report_id)
    fusion_snapshot = company_v2_financial_evidence_fusion_service.get(report_id)
    structured_ready = _structured_ready(symbol, report_id, doc.report_year, doc.report_type)
    rollout = company_v2_financial_fusion_rollout_service.evaluate(
        symbol=symbol,
        report_id=report_id,
        report_ready=report_ready,
        rag_ready=rag_ready,
        structured_ready=structured_ready,
        cached=bool(fusion_snapshot.get("fields")),
        last_run_at=fusion_snapshot.get("generated_at"),
        supported_fields=[
            "revenue",
            "net_profit",
            "net_profit_parent",
            "operating_cashflow",
            "total_assets",
            "equity_parent",
            "eps_basic",
            "roe_weighted",
            "total_share",
            "float_share",
        ],
    )
    return _json(
        {
            "ok": True,
            "report_ready": report_ready,
            "rag_ready": rag_ready,
            "structured_ready": structured_ready,
            "supported_fields": [
                "revenue",
                "net_profit",
                "net_profit_parent",
                "operating_cashflow",
                "total_assets",
                "equity_parent",
                "eps_basic",
                "roe_weighted",
                "total_share",
                "float_share",
            ],
            "cached": bool(fusion_snapshot.get("fields")) if fusion_snapshot else False,
            "last_run_at": fusion_snapshot.get("generated_at") if fusion_snapshot else None,
            "rollout": rollout,
            **rollout,
        }
    )


@router.get("/{report_id}/financial-fusion/health")
async def get_company_v2_financial_fusion_health(
    market: str = Path(...),
    symbol: str = Path(...),
    report_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    await _load_report(report_id=report_id, market=market, symbol=symbol, db=db)
    return _json({"ok": True, **company_v2_financial_fusion_health_service.health()})


@router.get("/{report_id}/financial-fusion/{field_name}")
async def get_company_v2_financial_fusion_field(
    market: str = Path(...),
    symbol: str = Path(...),
    report_id: int = Path(...),
    field_name: str = Path(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    await _load_report(report_id=report_id, market=market, symbol=symbol, db=db)
    return _json({"ok": True, **company_v2_financial_evidence_fusion_service.get_field(report_id, field_name)})
