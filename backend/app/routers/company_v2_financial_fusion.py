"""Company V2 financial fusion readiness and preparation APIs."""
from __future__ import annotations

from pathlib import Path as FsPath
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Path
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from app.core.database import get_db
from app.models.report_document import ReportDocument
from app.services.company_v2_financial_fusion_report_readiness import (
    company_v2_financial_fusion_report_readiness_service,
)
from app.services.company_v2_financial_fusion_stage2_plan import (
    company_v2_financial_fusion_stage2_plan_service,
)
from app.services.company_v2_financial_fusion_job_service import company_v2_financial_fusion_job_service
from app.services.company_v2_report_rag_index_manager import company_v2_report_rag_index_manager
from app.services.company_v2_report_rag_index_service import ReportDescriptor
from app.services.report_pdf_download_service import report_pdf_download_service
from app.services.report_text_extract_service import report_text_extract_service


router = APIRouter(
    prefix="/api/v2/company/{market}/{symbol}",
    tags=["company-v2-financial-fusion"],
)


class PrepareStepRequest(BaseModel):
    step: Literal["download", "parse", "index"] = Field(...)


class FinancialFusionJobRequest(BaseModel):
    report_id: int = Field(...)
    fields: list[str] = Field(default_factory=list)
    refresh: bool = Field(default=False)


def _json(payload: dict[str, Any], status_code: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status_code)


def _strip_private_paths(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key not in {"local_path", "path", "sidecar_path"}}


def _symbol_from_ts_code(ts_code: str | None) -> str:
    return (ts_code or "").split(".")[0]


def _report_source_url(doc: ReportDocument) -> str:
    return doc.pdf_url or doc.source_url or ""


async def _load_report(*, report_id: int, market: str, symbol: str, db: AsyncSession) -> ReportDocument:
    result = await db.execute(select(ReportDocument).where(ReportDocument.id == report_id))
    doc: ReportDocument | None = result.scalars().first()
    if not doc:
        raise HTTPException(status_code=404, detail={"error_code": "REPORT_NOT_FOUND", "message": "report_id not found"})
    if _symbol_from_ts_code(doc.ts_code) != symbol:
        raise HTTPException(status_code=409, detail={"error_code": "REPORT_SYMBOL_MISMATCH", "message": "report_id does not belong to this symbol"})
    if market.upper() != "CN":
        raise HTTPException(status_code=400, detail={"error_code": "UNSUPPORTED_MARKET", "message": "Only CN market is supported"})
    return doc


async def _load_report_for_job_create(*, report_id: int, market: str, symbol: str, db: AsyncSession) -> ReportDocument:
    result = await db.execute(
        select(ReportDocument)
        .options(
            load_only(
                ReportDocument.id,
                ReportDocument.ts_code,
                ReportDocument.report_year,
                ReportDocument.report_type,
            )
        )
        .where(ReportDocument.id == report_id)
    )
    doc: ReportDocument | None = result.scalars().first()
    if not doc:
        raise HTTPException(status_code=404, detail={"error_code": "REPORT_NOT_FOUND", "message": "report_id not found"})
    if _symbol_from_ts_code(doc.ts_code) != symbol:
        raise HTTPException(status_code=409, detail={"error_code": "REPORT_SYMBOL_MISMATCH", "message": "report_id does not belong to this symbol"})
    if market.upper() != "CN":
        raise HTTPException(status_code=400, detail={"error_code": "UNSUPPORTED_MARKET", "message": "Only CN market is supported"})
    return doc


def _find_sidecar(doc: ReportDocument) -> FsPath | None:
    if doc.local_path:
        sidecar = FsPath(doc.local_path).with_suffix(".pages.json")
        if sidecar.exists():
            return sidecar
    for candidate in FsPath("/tmp/company_v2_report_pdfs").glob(f"company_v2_report_{doc.id}_*.pages.json"):
        if candidate.exists():
            return candidate
    return None


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


@router.post("/financial-fusion/jobs")
async def create_company_v2_financial_fusion_job(
    background_tasks: BackgroundTasks,
    body: FinancialFusionJobRequest = Body(...),
    market: str = Path(...),
    symbol: str = Path(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    doc = await _load_report_for_job_create(report_id=body.report_id, market=market, symbol=symbol, db=db)
    payload = await company_v2_financial_fusion_job_service.create_job(
        db=db,
        market=market,
        symbol=symbol,
        report=doc,
        fields=body.fields,
        refresh=body.refresh,
        requester_scope="manual",
    )
    if not payload.get("ok"):
        return _json(payload, 200)
    if not payload.get("duplicate") and payload.get("status") == "queued":
        background_tasks.add_task(company_v2_financial_fusion_job_service.run_job, payload["job_id"])
    return _json(
        {
            "job_id": payload["job_id"],
            "status": payload["status"],
            "cache_hit": bool(payload.get("cache_hit")),
            "estimated_wait_seconds": payload.get("estimated_wait_seconds", 30),
            "poll_after_ms": payload.get("poll_after_ms", 1000),
            "terminal": payload.get("terminal", False),
        },
        202,
    )


@router.get("/financial-fusion/jobs/{job_id}")
async def get_company_v2_financial_fusion_job(
    job_id: str = Path(...),
    market: str = Path(...),
    symbol: str = Path(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    payload = await company_v2_financial_fusion_job_service.get_job(db=db, job_id=job_id, symbol=symbol)
    if not payload:
        return _json({"ok": False, "error_code": "JOB_NOT_FOUND", "message": "job not found"}, 404)
    return _json({"ok": True, **payload})


@router.get("/financial-fusion/jobs/{job_id}/result")
async def get_company_v2_financial_fusion_job_result(
    job_id: str = Path(...),
    market: str = Path(...),
    symbol: str = Path(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    payload = await company_v2_financial_fusion_job_service.get_result(db=db, job_id=job_id, symbol=symbol)
    if not payload:
        return _json({"ok": False, "error_code": "JOB_NOT_FOUND", "message": "job not found"}, 404)
    status_code = 200 if payload.get("ok") else 409
    return _json(payload, status_code)


@router.post("/financial-fusion/jobs/{job_id}/cancel")
async def cancel_company_v2_financial_fusion_job(
    job_id: str = Path(...),
    market: str = Path(...),
    symbol: str = Path(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    payload = await company_v2_financial_fusion_job_service.cancel_job(db=db, job_id=job_id, symbol=symbol)
    if not payload:
        return _json({"ok": False, "error_code": "JOB_NOT_FOUND", "message": "job not found"}, 404)
    return _json({"ok": True, **payload})


@router.get("/financial-fusion/readiness")
async def get_company_v2_financial_fusion_readiness(
    market: str = Path(...),
    symbol: str = Path(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    payload = await company_v2_financial_fusion_report_readiness_service.get_symbol_readiness(market, symbol, db)
    return _json(payload)


@router.post("/reports/{report_id}/prepare-step")
async def prepare_company_v2_financial_fusion_step(
    body: PrepareStepRequest = Body(...),
    market: str = Path(...),
    symbol: str = Path(...),
    report_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    doc = await _load_report(report_id=report_id, market=market, symbol=symbol, db=db)

    if body.step == "download":
        result = await report_pdf_download_service.download(report_id, db)
        return _json({"ok": result.get("status") != "failed", **_strip_private_paths(result)})

    if body.step == "parse":
        if doc.download_status != "downloaded" or not doc.local_path:
            return _json(
                {
                    "ok": False,
                    "status": "failed",
                    "error_code": "PDF_NOT_DOWNLOADED",
                    "message": "PDF must be downloaded before parsing",
                },
                412,
            )
        result = await report_text_extract_service.parse(report_id, db)
        return _json({"ok": result.get("status") == "parsed", **_strip_private_paths(result)})

    if doc.parse_status not in {"parsed", "partial"} or not doc.parsed:
        return _json(
            {
                "ok": False,
                "status": "failed",
                "error_code": "PDF_NOT_PARSED",
                "message": "PDF must be parsed before indexing",
            },
            412,
        )

    sidecar = _find_sidecar(doc)
    if not sidecar:
        return _json(
            {
                "ok": False,
                "status": "failed",
                "error_code": "PDF_NOT_PARSED",
                "message": "page sidecar unavailable",
            },
            412,
        )
    job = company_v2_report_rag_index_manager.enqueue_create_index(_descriptor_from_doc(doc, market, symbol), sidecar)
    return _json({"ok": True, "report_id": report_id, "job_id": job["job_id"], "status": job["status"], "duplicate": job.get("duplicate", False)})


@router.get("/reports/{report_id}/prepare-status")
async def get_company_v2_financial_fusion_prepare_status(
    market: str = Path(...),
    symbol: str = Path(...),
    report_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    payload = await company_v2_financial_fusion_stage2_plan_service.get_report_prepare_status(market, symbol, report_id, db)
    if not payload.get("ok"):
        raise HTTPException(status_code=404 if payload.get("error_code") == "REPORT_NOT_FOUND" else 409, detail=payload)
    return _json(payload)
