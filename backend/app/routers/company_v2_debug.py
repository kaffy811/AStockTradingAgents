from __future__ import annotations

import asyncio
import json
import hashlib
import re
import uuid
from pathlib import Path as FsPath
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Body, Depends, Path, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_db
from app.dependencies import get_optional_user
from app.models.user import User
from app.models.report_document import ReportDocument
from app.services.company_v2_ai_verification_response import (
    build_ai_verify_error_payload,
    sanitize_ai_verification_payload,
)
from app.services.company_v2_financial_fusion_circuit_breaker import company_v2_financial_fusion_circuit_breaker
from app.services.company_v2_financial_fusion_health_service import company_v2_financial_fusion_health_service
from app.services.company_v2_financial_fusion_metrics import company_v2_financial_fusion_metrics
from app.services.company_v2_financial_fusion_review_queue import company_v2_financial_fusion_review_queue
from app.services.company_v2_debug_service import MODULE_KEYS, company_v2_debug_service
from app.services.company_v2_report_pdf_service import validate_cninfo_pdf_url

router = APIRouter(prefix="/api/v2/company", tags=["company-v2-debug"])

_VALID_PROVIDERS = {"baostock", "akshare", "tencent", "sina", "eastmoney", "pdf", "cninfo", "sse", "szse", "pdf_metrics"}

_ALLOWED_PDF_HOSTS = frozenset(["static.cninfo.com.cn", "www.cninfo.com.cn", "cninfo.com.cn"])
_REPORT_VERIFICATION_CACHE: dict[int, dict[str, Any]] = {}
_REPORT_AI_VERIFICATION_CACHE: dict[str, dict[str, Any]] = {}


def _is_dev_or_admin(user: User | None) -> bool:
    env = getattr(settings, "app_env", "development").lower()
    if env in ("development", "dev", "local", "test", "testing"):
        return True
    return user is not None


def _json(data: Any, status_code: int = 200) -> JSONResponse:
    return JSONResponse(content=data, status_code=status_code)


def _parse_providers(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [p.strip() for p in value.split(",") if p.strip() in _VALID_PROVIDERS]


def _allow_raw(include_raw: bool, user: User | None) -> bool:
    env = getattr(settings, "app_env", "development").lower()
    if env in ("development", "dev", "local", "test", "testing"):
        return include_raw
    return include_raw and user is not None


def _financial_fusion_debug_guard(user: User | None) -> bool:
    return settings.enable_company_v2_debug_api and _is_dev_or_admin(user)


def _validate_manual_pdf_url(url: str) -> tuple[bool, str]:
    """Strict whitelist validation for manually submitted PDF URLs."""
    if not url:
        return False, "empty URL"
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, "only http/https allowed"
    host = (parsed.hostname or "").lower()
    if host not in _ALLOWED_PDF_HOSTS:
        return False, f"host {host!r} not in whitelist"
    if re.match(r"^(127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)", host):
        return False, "internal address blocked"
    path_upper = (parsed.path or "").upper()
    if not path_upper.endswith(".PDF"):
        return False, "URL must end with .PDF"
    return True, "ok"


@router.get("/{market}/{symbol}/debug/full")
async def debug_full(
    market: str = Path(...),
    symbol: str = Path(...),
    include_raw: bool = Query(False),
    providers: str | None = Query(None),
    force_refresh: bool = Query(False),
    max_raw_chars: int = Query(20000, ge=1000, le=100000),
    max_validation_checks: int | None = Query(None, ge=1, le=500),
    history: bool = Query(False),
    period: str = Query("annual", description="annual | quarterly | all"),
    start_year: int | None = Query(None),
    end_year: int | None = Query(None),
    profile: str = Query("debug", description="page | debug（page 为轻量生产展示）"),
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    if not settings.enable_company_v2_debug_api or not _is_dev_or_admin(user):
        return _json({"ok": False, "error_code": "AUTH_REQUIRED", "message": "CompanyV2 debug API is disabled"}, 403)
    try:
        from app.services.company_v2_response_profile import apply_response_profile
        effective_profile = profile if profile in ("page", "debug") else "debug"
        # page profile 不返回 raw
        data = await company_v2_debug_service.build_full(
            market, symbol,
            include_raw=_allow_raw(include_raw, user) and effective_profile != "page",
            providers=_parse_providers(providers),
            force_refresh=force_refresh,
            max_raw_chars=max_raw_chars,
            db=db,
            max_validation_checks=max_validation_checks,
            history=history,
            period=period if period in ("annual", "quarterly", "all") else "annual",
            start_year=start_year,
            end_year=end_year,
        )
        return _json(apply_response_profile(data, effective_profile))
    except Exception as exc:
        return _json({"ok": False, "error_code": "MAPPING_ERROR", "message": str(exc)[:500]}, 200)


@router.get("/{market}/{symbol}/debug/module/{module_key}")
async def debug_module(
    market: str = Path(...),
    symbol: str = Path(...),
    module_key: str = Path(...),
    include_raw: bool = Query(False),
    providers: str | None = Query(None),
    force_refresh: bool = Query(False),
    max_raw_chars: int = Query(20000, ge=1000, le=100000),
    max_validation_checks: int | None = Query(None, ge=1, le=500),
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    if not settings.enable_company_v2_debug_api or not _is_dev_or_admin(user):
        return _json({"ok": False, "error_code": "AUTH_REQUIRED", "message": "CompanyV2 debug API is disabled"}, 403)
    if module_key not in MODULE_KEYS:
        return _json({"ok": False, "error_code": "MODULE_NOT_FOUND", "message": f"Unknown module_key: {module_key}"}, 200)
    try:
        env = await company_v2_debug_service.build_module(
            market, symbol, module_key,
            include_raw=_allow_raw(include_raw, user),
            providers=_parse_providers(providers),
            force_refresh=force_refresh,
            max_raw_chars=max_raw_chars,
            db=db,
            max_validation_checks=max_validation_checks,
        )
        return _json(env.model_dump())
    except Exception as exc:
        return _json({"ok": False, "error_code": "MAPPING_ERROR", "message": str(exc)[:500]}, 200)


@router.get("/{market}/{symbol}/debug/provider/{provider}")
async def debug_provider(
    market: str = Path(...),
    symbol: str = Path(...),
    provider: str = Path(...),
    include_raw: bool = Query(False),
    force_refresh: bool = Query(False),
    max_raw_chars: int = Query(20000, ge=1000, le=100000),
    max_validation_checks: int | None = Query(None, ge=1, le=500),
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    if not settings.enable_company_v2_debug_api or not _is_dev_or_admin(user):
        return _json({"ok": False, "error_code": "AUTH_REQUIRED", "message": "CompanyV2 debug API is disabled"}, 403)
    if provider not in _VALID_PROVIDERS:
        return _json({"ok": False, "error_code": "PROVIDER_EMPTY", "message": f"Unsupported provider: {provider}"}, 200)
    module_key = "report_documents" if provider in {"cninfo", "sse", "szse", "pdf", "pdf_metrics"} else "quote_overview"
    if provider in {"baostock", "akshare"}:
        module_key = "profitability"
    env = await company_v2_debug_service.build_module(
        market, symbol, module_key,
        include_raw=_allow_raw(include_raw, user),
        providers=[provider],
        force_refresh=force_refresh,
        max_raw_chars=max_raw_chars,
        db=db,
        max_validation_checks=max_validation_checks,
    )
    return _json(env.model_dump())


@router.post("/{market}/{symbol}/debug/refresh")
async def debug_refresh(
    market: str = Path(...),
    symbol: str = Path(...),
    user: User | None = Depends(get_optional_user),
) -> JSONResponse:
    if not settings.enable_company_v2_debug_api or not _is_dev_or_admin(user):
        return _json({"ok": False, "error_code": "AUTH_REQUIRED", "message": "CompanyV2 debug API is disabled"}, 403)
    prefix = f"company_v2:{market.upper()}:{symbol}:"
    keys = [f"{prefix}{module_key}" for module_key in MODULE_KEYS]
    for key in keys:
        await company_v2_debug_service._write_cache(key, {}, 1)
    return _json({"ok": True, "market": market.upper(), "symbol": symbol, "refreshed_keys": keys})


# ── Financial Fusion Monitoring / Admin ─────────────────────────────────────


@router.get("/debug/financial-fusion/health")
async def debug_financial_fusion_health(user: User | None = Depends(get_optional_user)) -> JSONResponse:
    if not _financial_fusion_debug_guard(user):
        return _json({"ok": False, "error_code": "AUTH_REQUIRED", "message": "CompanyV2 debug API is disabled"}, 403)
    return _json({"ok": True, **company_v2_financial_fusion_health_service.health()})


@router.get("/debug/financial-fusion/metrics")
async def debug_financial_fusion_metrics(user: User | None = Depends(get_optional_user)) -> JSONResponse:
    if not _financial_fusion_debug_guard(user):
        return _json({"ok": False, "error_code": "AUTH_REQUIRED", "message": "CompanyV2 debug API is disabled"}, 403)
    return _json({"ok": True, "metrics": company_v2_financial_fusion_metrics.snapshot()})


@router.get("/debug/financial-fusion/circuit")
async def debug_financial_fusion_circuit(user: User | None = Depends(get_optional_user)) -> JSONResponse:
    if not _financial_fusion_debug_guard(user):
        return _json({"ok": False, "error_code": "AUTH_REQUIRED", "message": "CompanyV2 debug API is disabled"}, 403)
    return _json({"ok": True, "circuit": company_v2_financial_fusion_circuit_breaker.snapshot()})


@router.post("/debug/financial-fusion/circuit/reset")
async def debug_financial_fusion_circuit_reset(user: User | None = Depends(get_optional_user)) -> JSONResponse:
    if not _financial_fusion_debug_guard(user):
        return _json({"ok": False, "error_code": "AUTH_REQUIRED", "message": "CompanyV2 debug API is disabled"}, 403)
    return _json({"ok": True, "circuit": company_v2_financial_fusion_circuit_breaker.reset(), "audit": "manual_reset"})


@router.get("/debug/financial-fusion/review-queue")
async def debug_financial_fusion_review_queue(user: User | None = Depends(get_optional_user)) -> JSONResponse:
    if not _financial_fusion_debug_guard(user):
        return _json({"ok": False, "error_code": "AUTH_REQUIRED", "message": "CompanyV2 debug API is disabled"}, 403)
    return _json({"ok": True, "items": company_v2_financial_fusion_review_queue.list()})


# ── Report Timeline Endpoints ────────────────────────────────────────────────


@router.get("/{market}/{symbol}/reports")
async def get_reports(
    market: str = Path(...),
    symbol: str = Path(...),
    start_year: int = Query(default=None),
    end_year: int = Query(default=None),
    report_type: str = Query(default="annual"),
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """返回 CNINFO 年报/季报时间线。"""
    if market.upper() != "CN":
        return _json({"ok": True, "reports": [], "total": 0, "message": "Only CN market supported"})
    from app.services.cninfo_report_discovery_agent import cninfo_report_discovery_agent
    report_types = None if report_type in ("all", "", None) else [report_type]
    result = await cninfo_report_discovery_agent.discover(
        market, symbol,
        start_year=start_year,
        end_year=end_year,
        report_types=report_types,
        force_refresh=False,
    )
    reports = result.get("reports") or []
    try:
        reports = await _persist_report_documents(db, symbol, reports)
    except Exception as exc:
        result.setdefault("errors", []).append(f"report_persist_failed:{str(exc)[:100]}")
    return _json({
        "ok": True,
        "symbol": symbol,
        "market": market.upper(),
        "reports": reports,
        "timeline": reports,
        "total": len(reports),
        "documents_count": len(reports),
        "annual_reports_count": result.get("annual_reports_count", 0),
        "quarterly_reports_count": result.get("quarterly_reports_count", 0),
        "from_cache": result.get("from_cache", False),
        "errors": result.get("errors", []),
    })


@router.get("/{market}/{symbol}/reports/discover")
@router.post("/{market}/{symbol}/reports/discover")
async def discover_reports(
    market: str = Path(...),
    symbol: str = Path(...),
    start_year: int = Query(default=None),
    end_year: int = Query(default=None),
    report_type: str = Query(default="annual"),
    force_refresh: bool = Query(default=False),
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """触发 CNINFO 年报/季报发现。GET 用于轮询状态，POST 用于触发刷新。"""
    if market.upper() != "CN":
        return _json({"ok": False, "error_code": "UNSUPPORTED_MARKET", "message": "Only CN market supported"})
    from app.services.cninfo_report_discovery_agent import cninfo_report_discovery_agent
    report_types = None if report_type in ("all", "", None) else [report_type]
    result = await cninfo_report_discovery_agent.discover(
        market, symbol,
        start_year=start_year,
        end_year=end_year,
        report_types=report_types,
        force_refresh=force_refresh,
    )
    reports = result.get("reports") or []
    try:
        reports = await _persist_report_documents(db, symbol, reports)
    except Exception as exc:
        result.setdefault("errors", []).append(f"report_persist_failed:{str(exc)[:100]}")
    return _json({
        "ok": True,
        "symbol": symbol,
        "market": market.upper(),
        "reports": reports,
        "timeline": reports,
        "total_found": len(reports),
        "documents_count": len(reports),
        "annual_reports_count": result.get("annual_reports_count", 0),
        "quarterly_reports_count": result.get("quarterly_reports_count", 0),
        "from_cache": result.get("from_cache", False),
        "errors": result.get("errors", []),
        "discovery_method": "cninfo_his_announcement_query",
    })


class ManualReportBody(BaseModel):
    pdf_url: str
    title: str = ""
    report_year: int = 0
    announcement_date: str = ""
    source: str = "manual"


class AIVerificationBody(BaseModel):
    report_year: int | None = None
    report_type: str | None = None
    target_fields: list[str] | None = None
    confidence_threshold: float = 0.75
    force_refresh: bool = False


def _strip_sensitive_report_payload(data: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in data.items() if k not in {"local_path", "path"}}


def _report_view_state(symbol: str, report: dict[str, Any]) -> dict[str, Any]:
    source_url = report.get("pdf_url") or report.get("source_url") or ""
    url_whitelist_valid, _reason = validate_cninfo_pdf_url(source_url)
    return {
        "source_url": source_url or None,
        "report_view_ready": bool(source_url and url_whitelist_valid and (report.get("symbol") in {None, "", symbol})),
        "url_whitelist_valid": url_whitelist_valid,
        "canonical_report": bool(source_url),
    }


def _ts_code(symbol: str) -> str:
    if "." in symbol:
        return symbol
    return f"{symbol}.SH" if symbol.startswith(("6", "5", "9")) else f"{symbol}.SZ"


def _period_end(report: dict[str, Any]) -> str | None:
    year = report.get("report_year")
    report_type = report.get("report_type")
    if not year:
        return None
    suffix = {
        "annual": "12-31",
        "semi_annual": "06-30",
        "q1": "03-31",
        "q3": "09-30",
    }.get(report_type, "12-31")
    return f"{year}-{suffix}"


async def _persist_report_documents(db: AsyncSession, symbol: str, reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Persist discovered CNINFO reports and attach safe report_id values."""
    ts_code = _ts_code(symbol)
    persisted: list[dict[str, Any]] = []
    for report in reports:
        safe_report = dict(report)
        pdf_url = safe_report.get("pdf_url")
        if not pdf_url:
            persisted.append(safe_report)
            continue
        result = await db.execute(
            select(ReportDocument).where(
                ReportDocument.ts_code == ts_code,
                ReportDocument.pdf_url == pdf_url,
            )
        )
        doc = result.scalars().first()
        if not doc:
            doc = ReportDocument(
                ts_code=ts_code,
                report_type=safe_report.get("report_type") or "annual",
                period_end=_period_end(safe_report),
                title=safe_report.get("title") or "",
                source_url=pdf_url,
                pdf_url=pdf_url,
                report_year=safe_report.get("report_year"),
                source=safe_report.get("source") or "cninfo",
                disclosure_date=safe_report.get("announcement_date") or safe_report.get("disclosure_date"),
                confidence=safe_report.get("confidence"),
                download_status=safe_report.get("download_status") or "discovered",
                parse_status=safe_report.get("parse_status") or "pending",
            )
            db.add(doc)
            await db.flush()
        else:
            doc.report_type = safe_report.get("report_type") or doc.report_type
            doc.period_end = _period_end(safe_report) or doc.period_end
            doc.title = safe_report.get("title") or doc.title
            doc.report_year = safe_report.get("report_year") or doc.report_year
            doc.disclosure_date = safe_report.get("announcement_date") or safe_report.get("disclosure_date") or doc.disclosure_date
            doc.source = safe_report.get("source") or doc.source
            doc.confidence = safe_report.get("confidence") or doc.confidence
        safe_report["id"] = doc.id
        safe_report["report_id"] = doc.id
        safe_report["download_status"] = doc.download_status
        safe_report["parse_status"] = doc.parse_status
        safe_report["pdf_status"] = doc.download_status
        safe_report.update(_report_view_state(symbol, safe_report))
        safe_report["qa_ready"] = bool(doc.parsed and doc.parse_status in {"parsed", "partial"})
        safe_report["fusion_ready"] = bool(doc.rag_status in {"indexed", "partial"})
        safe_report["rag_index_status"] = doc.rag_status
        persisted.append({k: v for k, v in safe_report.items() if k not in {"local_path", "path"}})
    await db.commit()
    return persisted


@router.post("/{market}/{symbol}/reports/manual")
async def add_manual_report(
    market: str = Path(...),
    symbol: str = Path(...),
    body: ManualReportBody = Body(...),
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """
    手动录入 PDF URL（兜底入口）。

    安全校验：
    - URL host 必须在白名单内
    - URL 必须是 PDF
    - URL 必须 https 或 static.cninfo.com.cn（允许 http）
    - 不允许 file:// 或内网地址
    - 不泄露 local_path
    """
    valid, reason = _validate_manual_pdf_url(body.pdf_url)
    if not valid:
        return _json({
            "ok": False,
            "error_code": "INVALID_PDF_URL",
            "message": f"PDF URL rejected: {reason}",
        }, 400)
    # Store to DB if available
    record = {
        "symbol": symbol,
        "ts_code": f"{symbol}.SH" if symbol.startswith(("6", "5")) else f"{symbol}.SZ",
        "market": market.upper(),
        "report_year": body.report_year or 0,
        "title": body.title or f"{symbol} 年报 PDF",
        "announcement_date": body.announcement_date or "",
        "pdf_url": body.pdf_url,
        "source": "manual",
        "source_host": (urlparse(body.pdf_url).hostname or ""),
        "confidence": 0.80,
        "discovery_method": "manual",
        "is_summary": False,
        "is_correction": False,
    }
    return _json({"ok": True, "record": record, "message": "Manual PDF URL accepted"})


@router.post("/{market}/{symbol}/reports/{report_id}/download")
async def download_company_v2_report_pdf(
    market: str = Path(...),
    symbol: str = Path(...),
    report_id: int = Path(...),
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    if not settings.enable_company_v2_debug_api or not _is_dev_or_admin(user):
        return _json({"ok": False, "error_code": "AUTH_REQUIRED"}, 403)
    try:
        from app.services.company_v2_report_pdf_service import company_v2_report_pdf_service
        result = await company_v2_report_pdf_service.download_report(report_id, db)
        return _json(_strip_sensitive_report_payload(result))
    except Exception as exc:
        return _json({"ok": False, "status": "download_failed", "error_code": "PDF_DOWNLOAD_FAILED", "message": str(exc)[:500]}, 200)


@router.post("/{market}/{symbol}/reports/{report_id}/parse")
async def parse_company_v2_report_pdf(
    market: str = Path(...),
    symbol: str = Path(...),
    report_id: int = Path(...),
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    if not settings.enable_company_v2_debug_api or not _is_dev_or_admin(user):
        return _json({"ok": False, "error_code": "AUTH_REQUIRED"}, 403)
    try:
        from app.services.company_v2_pdf_text_parser import company_v2_pdf_text_parser
        result = await company_v2_pdf_text_parser.parse_report(report_id, db)
        return _json(_strip_sensitive_report_payload(result))
    except Exception as exc:
        return _json({"ok": False, "status": "parse_failed", "error_code": "PDF_PARSE_FAILED", "message": str(exc)[:500]}, 200)


@router.post("/{market}/{symbol}/reports/{report_id}/verify")
async def verify_company_v2_report_pdf(
    market: str = Path(...),
    symbol: str = Path(...),
    report_id: int = Path(...),
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    if not settings.enable_company_v2_debug_api or not _is_dev_or_admin(user):
        return _json({"ok": False, "error_code": "AUTH_REQUIRED"}, 403)
    try:
        from app.services.company_v2_official_field_extractor import extract_official_fields
        from app.services.company_v2_official_verification_service import extract_structured_fields, verify_official_fields

        result = await db.execute(select(ReportDocument).where(ReportDocument.id == report_id))
        doc: ReportDocument | None = result.scalars().first()
        if not doc:
            return _json({"ok": False, "status": "unverified", "error_code": "REPORT_NOT_FOUND", "report_id": report_id}, 200)
        if not doc.text_excerpt:
            return _json({"ok": False, "status": "unverified", "error_code": "REPORT_NOT_PARSED", "report_id": report_id}, 200)

        parsed_source: Any = doc.text_excerpt
        if doc.local_path:
            sidecar = FsPath(doc.local_path).with_suffix(".pages.json")
            if sidecar.exists():
                try:
                    parsed_source = json.loads(sidecar.read_text(encoding="utf-8"))
                except Exception:
                    parsed_source = doc.text_excerpt
        official = extract_official_fields(parsed_source, report_id=report_id)
        debug_data = await company_v2_debug_service.build_full(
            market, symbol,
            include_raw=False,
            providers=None,
            force_refresh=False,
            max_raw_chars=5000,
            db=db,
            history=True,
            period="annual",
            start_year=doc.report_year,
            end_year=doc.report_year,
        )
        structured = extract_structured_fields(
            debug_data,
            report_year=doc.report_year,
            report_type=doc.report_type,
            annual_required=doc.report_type == "annual",
        )
        verification = verify_official_fields(
            structured,
            official.get("official_fields") or {},
            report_year=doc.report_year,
            report_type=doc.report_type,
        )
        payload = {
            "ok": True,
            "report_id": report_id,
            "report_year": doc.report_year,
            "report_type": doc.report_type,
            "period": "annual" if doc.report_type == "annual" else None,
            "official_fields": official.get("official_fields") or {},
            "official_verification": verification,
        }
        _REPORT_VERIFICATION_CACHE[report_id] = payload
        doc.download_status = "verified" if verification.get("verified_fields_count", 0) else doc.download_status
        await db.commit()
        return _json(payload)
    except Exception as exc:
        return _json({"ok": False, "status": "unverified", "error_code": "OFFICIAL_VERIFICATION_FAILED", "message": str(exc)[:500]}, 200)


@router.post("/{market}/{symbol}/reports/{report_id}/ai-verify")
async def ai_verify_company_v2_report_pdf(
    market: str = Path(...),
    symbol: str = Path(...),
    report_id: int = Path(...),
    body: AIVerificationBody = Body(default_factory=AIVerificationBody),
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    if not settings.enable_company_v2_debug_api or not _is_dev_or_admin(user):
        return _json({"ok": False, "error_code": "AUTH_REQUIRED"}, 403)
    request_id = str(uuid.uuid4())
    try:
        from app.services.company_v2_ai_official_verification_agent import verify_with_ai

        result = await db.execute(select(ReportDocument).where(ReportDocument.id == report_id))
        doc: ReportDocument | None = result.scalars().first()
        if not doc:
            return _json(build_ai_verify_error_payload(
                request_id=request_id,
                report_id=report_id,
                report_year=body.report_year,
                report_type=body.report_type,
                error_code="REPORT_NOT_FOUND",
                warnings=["report document unavailable"],
            ), 200)

        parsed_source: Any = None
        if doc.local_path:
            sidecar = FsPath(doc.local_path).with_suffix(".pages.json")
            if sidecar.exists():
                try:
                    parsed_source = json.loads(sidecar.read_text(encoding="utf-8"))
                except Exception:
                    parsed_source = None
        if parsed_source is None and doc.text_excerpt:
            parsed_source = {"text_pages": [{"page": 1, "text": doc.text_excerpt}]}
        if parsed_source is None:
            return _json(build_ai_verify_error_payload(
                request_id=request_id,
                report_id=report_id,
                report_year=body.report_year or doc.report_year,
                report_type=body.report_type or doc.report_type or "annual",
                error_code="REPORT_NOT_PARSED",
                warnings=["parsed PDF text/pages unavailable"],
            ), 200)

        report_year = body.report_year or doc.report_year
        report_type = body.report_type or doc.report_type or "annual"
        debug_data = await company_v2_debug_service.build_full(
            market, symbol,
            include_raw=False,
            providers=None,
            force_refresh=False,
            max_raw_chars=5000,
            db=db,
            history=True,
            period="annual" if report_type == "annual" else "all",
            start_year=report_year,
            end_year=report_year,
        )
        request_id = debug_data.get("request_id") or request_id
        from app.services.company_v2_official_verification_service import (
            ANNUAL_PERIOD_REQUIRED,
            STRUCTURED_ANNUAL_ROW_NOT_FOUND,
            extract_structured_fields,
        )
        structured_probe = extract_structured_fields(
            debug_data,
            report_year=int(report_year) if report_year else None,
            report_type=report_type,
            annual_required=report_type == "annual",
        )
        target_probe_fields = body.target_fields or ["revenue", "net_profit_parent", "net_profit", "operating_cashflow"]
        probe_entries = [structured_probe.get(field) for field in target_probe_fields if field in structured_probe]
        if probe_entries and all(isinstance(item, dict) and item.get("reason") in {STRUCTURED_ANNUAL_ROW_NOT_FOUND, ANNUAL_PERIOD_REQUIRED} for item in probe_entries):
            return _json(build_ai_verify_error_payload(
                request_id=request_id,
                report_id=report_id,
                report_year=report_year,
                report_type=report_type,
                error_code="STRUCTURED_ANNUAL_HISTORY_MISSING",
                warnings=["structured annual history unavailable for requested report year"],
            ), 200)
        structured_hash = hashlib.sha256(
            json.dumps(debug_data, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:16]
        file_hash = doc.file_sha256 or "nohash"
        cache_key = f"{report_id}:{file_hash}:{structured_hash}:{report_year}:{report_type}:{','.join(body.target_fields or [])}:{body.confidence_threshold}"
        if not body.force_refresh and cache_key in _REPORT_AI_VERIFICATION_CACHE:
            return _json(_REPORT_AI_VERIFICATION_CACHE[cache_key])

        report_document = {
            "report_id": report_id,
            "ts_code": doc.ts_code,
            "symbol": symbol,
            "report_year": report_year,
            "report_type": report_type,
            "pdf_url": doc.pdf_url,
            "source": doc.source or "cninfo",
        }
        ai_result = await asyncio.to_thread(
            verify_with_ai,
            report_document,
            parsed_source,
            debug_data,
            body.target_fields,
            int(report_year) if report_year else 0,
            report_type,
            confidence_threshold=body.confidence_threshold,
        )
        payload = {
            "ok": True,
            "report_id": report_id,
            "report_year": report_year,
            "report_type": report_type,
            "ai_verification_status": ai_result.get("verification_status"),
            "fields": ai_result.get("fields") or {},
            "human_review_queue": ai_result.get("human_review_queue") or [],
            "non_blocking_findings": ai_result.get("non_blocking_findings") or [],
            "summary_counts": ai_result.get("summary_counts") or {},
            "warnings": ai_result.get("warnings") or [],
            "request_id": request_id,
        }
        payload = sanitize_ai_verification_payload(payload)
        _REPORT_AI_VERIFICATION_CACHE[cache_key] = payload
        return _json(payload)
    except Exception as exc:
        return _json(build_ai_verify_error_payload(
            request_id=request_id,
            report_id=report_id,
            report_year=body.report_year,
            report_type=body.report_type,
            error_code="AI_VERIFICATION_FAILED",
            message=str(exc)[:500],
            warnings=["ai verification failed safely"],
        ), 200)


@router.get("/{market}/{symbol}/reports/{report_id}/verification")
async def get_company_v2_report_verification(
    market: str = Path(...),
    symbol: str = Path(...),
    report_id: int = Path(...),
    user: User | None = Depends(get_optional_user),
) -> JSONResponse:
    if not settings.enable_company_v2_debug_api or not _is_dev_or_admin(user):
        return _json({"ok": False, "error_code": "AUTH_REQUIRED"}, 403)
    cached = _REPORT_VERIFICATION_CACHE.get(report_id)
    if cached:
        return _json(cached)
    return _json({"ok": False, "report_id": report_id, "status": "unverified", "error_code": "VERIFICATION_NOT_FOUND"}, 200)


@router.get("/{market}/{symbol}/accuracy_audit")
async def accuracy_audit(
    market: str = Path(...),
    symbol: str = Path(...),
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """返回当前 CompanyV2 数据准确性审计报告。"""
    if not settings.enable_company_v2_debug_api or not _is_dev_or_admin(user):
        return _json({"ok": False, "error_code": "AUTH_REQUIRED"}, 403)
    try:
        from app.services.company_v2_accuracy_audit_service import audit_full_debug
        debug_data = await company_v2_debug_service.build_full(
            market, symbol,
            include_raw=False,
            providers=None,
            force_refresh=False,
            max_raw_chars=5000,
            db=db,
        )
        report_docs_module = debug_data.get("modules", {}).get("report_documents", {})
        row = (report_docs_module.get("normalized") or {}).get("rows", [{}])
        has_pdf = (row[0].get("documents_count") or 0) > 0 if row else False
        audit = audit_full_debug(debug_data, has_official_pdf=has_pdf)
        return _json({"ok": True, **audit})
    except Exception as exc:
        return _json({"ok": False, "error_code": "INTERNAL_ERROR", "message": str(exc)[:500]}, 200)


# ── Full-History Financial Dashboard Endpoints（Phase 6T-B） ──────────────────

@router.get("/{market}/{symbol}/history")
async def get_company_history(
    market: str = Path(...),
    symbol: str = Path(...),
    period: str = Query("quarterly", description="annual | quarterly | all"),
    start_year: int | None = Query(None, description="起始年份，默认从上市年份"),
    end_year: int | None = Query(None, description="截止年份，默认当前年"),
    force_refresh: bool = Query(False),
    user: User | None = Depends(get_optional_user),
) -> JSONResponse:
    """
    获取股票全历史财务仪表盘数据（上市以来全量）。

    返回所有财务模块的 history 序列，用于前端可视化。
    - period=annual: 仅年末数据
    - period=quarterly: 所有季度（默认）
    - period=all: 同 quarterly
    """
    if not settings.enable_company_v2_debug_api or not _is_dev_or_admin(user):
        return _json({"ok": False, "error_code": "AUTH_REQUIRED"}, 403)
    if market.upper() != "CN":
        return _json({"ok": False, "error_code": "UNSUPPORTED_MARKET", "message": "Only CN market supported"})
    if period not in ("annual", "quarterly", "all"):
        period = "quarterly"
    try:
        from app.services.company_v2_history_service import build_company_history_dashboard
        data = await build_company_history_dashboard(
            market, symbol,
            period=period,
            start_year=start_year,
            end_year=end_year,
            force_refresh=force_refresh,
        )
        return _json(data)
    except Exception as exc:
        return _json({"ok": False, "error_code": "HISTORY_ERROR", "message": str(exc)[:500]}, 200)


@router.get("/{market}/{symbol}/history/module/{module_key}")
async def get_module_history(
    market: str = Path(...),
    symbol: str = Path(...),
    module_key: str = Path(...),
    period: str = Query("quarterly"),
    start_year: int | None = Query(None),
    end_year: int | None = Query(None),
    force_refresh: bool = Query(False),
    user: User | None = Depends(get_optional_user),
) -> JSONResponse:
    """
    获取单个财务模块的全历史数据（轻量接口）。
    """
    if not settings.enable_company_v2_debug_api or not _is_dev_or_admin(user):
        return _json({"ok": False, "error_code": "AUTH_REQUIRED"}, 403)
    valid_modules = {"profitability", "growth", "cashflow_quality", "solvency", "operation_capability", "dupont"}
    if module_key not in valid_modules:
        return _json({"ok": False, "error_code": "MODULE_NOT_FOUND", "message": f"Unknown: {module_key}"})
    try:
        from app.services.company_v2_history_service import get_module_history
        data = await get_module_history(
            market, symbol, module_key,
            period=period,
            start_year=start_year,
            end_year=end_year,
            force_refresh=force_refresh,
        )
        return _json(data)
    except Exception as exc:
        return _json({"ok": False, "error_code": "HISTORY_ERROR", "message": str(exc)[:500]}, 200)


@router.get("/{market}/{symbol}/stock_basic")
async def get_stock_basic(
    market: str = Path(...),
    symbol: str = Path(...),
    user: User | None = Depends(get_optional_user),
) -> JSONResponse:
    """
    获取股票/公司基本信息（含上市日期）。
    - list_date: 上市日期，用于确定历史数据起始年份
    - list_date_status: exact | seed | unknown
    """
    if not settings.enable_company_v2_debug_api or not _is_dev_or_admin(user):
        return _json({"ok": False, "error_code": "AUTH_REQUIRED"}, 403)
    try:
        from app.services.company_v2_stock_basic_service import get_stock_basic as _get_basic
        data = await _get_basic(symbol)
        return _json({"ok": True, **data})
    except Exception as exc:
        return _json({"ok": False, "error_code": "STOCK_BASIC_ERROR", "message": str(exc)[:500]}, 200)
