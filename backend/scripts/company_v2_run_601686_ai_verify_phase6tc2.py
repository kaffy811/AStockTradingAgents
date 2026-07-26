#!/usr/bin/env python3
"""Run Phase 6T-C2 live AI verification artifact capture for 601686.

Scope is intentionally narrow:
- CN/601686 2024 annual report only
- no RAG ingestion
- no batch processing
- no CompanyV2/PDF/CNINFO main-chain changes
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_document import ReportDocument
from app.services.cninfo_report_discovery_agent import cninfo_report_discovery_agent
from app.services.company_v2_ai_official_verification_agent import verify_with_ai
from app.services.company_v2_ai_verification_response import sanitize_ai_verification_payload
from app.services.company_v2_debug_service import company_v2_debug_service
from app.services.company_v2_pdf_text_parser import company_v2_pdf_text_parser
from app.services.company_v2_report_pdf_service import company_v2_report_pdf_service

MARKET = "CN"
SYMBOL = "601686"
TS_CODE = "601686.SH"
REPORT_YEAR = 2024
REPORT_TYPE = "annual"
ARTIFACT_DIR = BACKEND / "docs" / "artifacts"
OFFICIAL_ARTIFACT = ARTIFACT_DIR / "company_v2_601686_ai_official_verification_phase6tc2.json"
QUEUE_ARTIFACT = ARTIFACT_DIR / "company_v2_601686_ai_human_review_queue_phase6tc2.json"
SUMMARY_ARTIFACT = ARTIFACT_DIR / "company_v2_601686_ai_verification_summary_phase6tc2.md"
ALLOWED_PDF_HOSTS = {"static.cninfo.com.cn", "www.cninfo.com.cn", "cninfo.com.cn"}


def _period_end(report_year: int, report_type: str) -> str:
    suffix = {
        "annual": "12-31",
        "semi_annual": "06-30",
        "q1": "03-31",
        "q3": "09-30",
    }.get(report_type, "12-31")
    return f"{report_year}-{suffix}"


def _pdf_host_ok(url: str | None) -> bool:
    return (urlparse(url or "").hostname or "").lower() in ALLOWED_PDF_HOSTS


def _safe_doc_snapshot(doc: ReportDocument | None) -> dict[str, Any]:
    if not doc:
        return {}
    local_path = Path(doc.local_path) if doc.local_path else None
    sidecar = local_path.with_suffix(".pages.json") if local_path else None
    page_count = None
    if sidecar and sidecar.exists():
        try:
            page_count = json.loads(sidecar.read_text(encoding="utf-8")).get("page_count")
        except Exception:
            page_count = None
    return {
        "report_id": doc.id,
        "ts_code": doc.ts_code,
        "report_year": doc.report_year,
        "report_type": doc.report_type,
        "title": doc.title,
        "source": doc.source,
        "pdf_url": doc.pdf_url,
        "download_status": doc.download_status,
        "parse_status": doc.parse_status,
        "file_hash_exists": bool(doc.file_sha256),
        "file_size": doc.file_size,
        "parsed": bool(doc.parsed),
        "page_count": page_count,
        "parsed_page_sidecar_exists": bool(sidecar and sidecar.exists()),
        "pdf_file_exists": bool(local_path and local_path.exists()),
    }


async def _find_existing_report(db: AsyncSession) -> ReportDocument | None:
    result = await db.execute(
        select(ReportDocument)
        .where(
            ReportDocument.ts_code == TS_CODE,
            ReportDocument.report_year == REPORT_YEAR,
            ReportDocument.report_type == REPORT_TYPE,
        )
        .order_by(ReportDocument.id.asc())
    )
    return result.scalars().first()


async def _persist_discovered_report(db: AsyncSession, report: dict[str, Any]) -> ReportDocument:
    result = await db.execute(
        select(ReportDocument).where(
            ReportDocument.ts_code == TS_CODE,
            ReportDocument.pdf_url == report.get("pdf_url"),
        )
    )
    doc = result.scalars().first()
    if not doc:
        doc = ReportDocument(
            ts_code=TS_CODE,
            report_type=report.get("report_type") or REPORT_TYPE,
            period_end=_period_end(REPORT_YEAR, report.get("report_type") or REPORT_TYPE),
            title=report.get("title") or "",
            source_url=report.get("pdf_url"),
            pdf_url=report.get("pdf_url"),
            report_year=report.get("report_year") or REPORT_YEAR,
            source=report.get("source") or "cninfo",
            disclosure_date=report.get("announcement_date") or report.get("disclosure_date"),
            confidence=report.get("confidence"),
            download_status=report.get("download_status") or "discovered",
            parse_status=report.get("parse_status") or "pending",
        )
        db.add(doc)
        await db.flush()
    else:
        doc.report_type = report.get("report_type") or doc.report_type
        doc.period_end = _period_end(REPORT_YEAR, doc.report_type or REPORT_TYPE)
        doc.title = report.get("title") or doc.title
        doc.report_year = report.get("report_year") or doc.report_year
        doc.disclosure_date = report.get("announcement_date") or report.get("disclosure_date") or doc.disclosure_date
        doc.source = report.get("source") or doc.source
        doc.confidence = report.get("confidence") or doc.confidence
    await db.commit()
    await db.refresh(doc)
    return doc


def _status_counts(fields: dict[str, Any]) -> dict[str, int]:
    counts = {
        "verified_count": 0,
        "likely_match_count": 0,
        "mismatch_count": 0,
        "needs_human_review_count": 0,
        "insufficient_evidence_count": 0,
    }
    for entry in fields.values():
        if not isinstance(entry, dict):
            continue
        status = entry.get("status")
        if status == "verified":
            counts["verified_count"] += 1
        elif status == "likely_match":
            counts["likely_match_count"] += 1
        elif status == "mismatch":
            counts["mismatch_count"] += 1
        elif status == "needs_human_review":
            counts["needs_human_review_count"] += 1
        elif status in {"insufficient_evidence", "not_found"}:
            counts["insufficient_evidence_count"] += 1
    return counts


def _contains_full_pdf_text(payload: Any) -> bool:
    text = json.dumps(payload, ensure_ascii=False, default=str)
    return "text_pages" in text or "full_pdf_text" in text or "raw_pdf_text" in text


def _contains_local_path(payload: Any) -> bool:
    text = json.dumps(payload, ensure_ascii=False, default=str)
    return "local_path" in text or "/tmp/company_v2_report_pdfs" in text


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _write_summary(summary: dict[str, Any]) -> None:
    lines = [
        "# CompanyV2 601686 AI Verification Phase 6T-C2",
        "",
        f"- report_id: {summary.get('report_id')}",
        f"- report_year: {summary.get('report_year')}",
        f"- report_type: {summary.get('report_type')}",
        f"- pdf_url: {summary.get('pdf_url')}",
        f"- download_status: {summary.get('download_status')}",
        f"- parse_status: {summary.get('parse_status')}",
        f"- page_count: {summary.get('page_count')}",
        f"- parsed_page_sidecar_exists: {str(summary.get('parsed_page_sidecar_exists')).lower()}",
        f"- fields_checked: {summary.get('fields_checked')}",
        f"- verified_count: {summary.get('verified_count')}",
        f"- likely_match_count: {summary.get('likely_match_count')}",
        f"- mismatch_count: {summary.get('mismatch_count')}",
        f"- needs_human_review_count: {summary.get('needs_human_review_count')}",
        f"- insufficient_evidence_count: {summary.get('insufficient_evidence_count')}",
        f"- final_status: {summary.get('final_status')}",
        f"- local_path_leaked: {str(summary.get('local_path_leaked')).lower()}",
        f"- full_pdf_text_returned: {str(summary.get('full_pdf_text_returned')).lower()}",
        "",
        "## human_review_queue",
        "",
    ]
    queue = summary.get("human_review_queue") or []
    if not queue:
        lines.append("- []")
    else:
        for item in queue:
            lines.append(
                "- field={field}; reason={reason}; confidence={confidence}; page={page}".format(
                    field=item.get("field"),
                    reason=item.get("reason"),
                    confidence=item.get("confidence"),
                    page=item.get("evidence_page"),
                )
            )
    SUMMARY_ARTIFACT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _save_failure(stage: str, reason: str, *, report_id: int | None = None, doc: ReportDocument | None = None) -> dict[str, Any]:
    payload = sanitize_ai_verification_payload({
        "ok": False,
        "stage": stage,
        "error_code": stage,
        "message": reason,
        "report_id": report_id,
        "report_year": REPORT_YEAR,
        "report_type": REPORT_TYPE,
        "report_document": _safe_doc_snapshot(doc),
        "ai_verification_status": "insufficient_evidence",
        "fields": {},
        "human_review_queue": [],
        "warnings": [reason],
    })
    _write_json(OFFICIAL_ARTIFACT, payload)
    _write_json(QUEUE_ARTIFACT, {"report_id": report_id, "human_review_queue": []})
    _write_summary({
        "report_id": report_id,
        "report_year": REPORT_YEAR,
        "report_type": REPORT_TYPE,
        "pdf_url": doc.pdf_url if doc else None,
        "download_status": doc.download_status if doc else stage,
        "parse_status": doc.parse_status if doc else stage,
        "page_count": None,
        "parsed_page_sidecar_exists": False,
        "fields_checked": 0,
        "verified_count": 0,
        "likely_match_count": 0,
        "mismatch_count": 0,
        "needs_human_review_count": 0,
        "insufficient_evidence_count": 0,
        "human_review_queue": [],
        "final_status": "insufficient_evidence",
        "local_path_leaked": _contains_local_path(payload),
        "full_pdf_text_returned": _contains_full_pdf_text(payload),
    })
    print(json.dumps({"ok": False, "stage": stage, "message": reason, "report_id": report_id}, ensure_ascii=False))
    return payload


async def run() -> dict[str, Any]:
    from app.core.database import AsyncSessionLocal

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    async with AsyncSessionLocal() as db:
        discover_result = await cninfo_report_discovery_agent.discover(
            MARKET,
            SYMBOL,
            start_year=REPORT_YEAR,
            end_year=REPORT_YEAR,
            force_refresh=True,
            report_types=[REPORT_TYPE],
        )
        reports = [
            report for report in (discover_result.get("reports") or [])
            if report.get("report_year") == REPORT_YEAR
            and report.get("report_type") == REPORT_TYPE
            and _pdf_host_ok(report.get("pdf_url"))
        ]
        if not reports:
            return _save_failure("DISCOVER_FAILED", "CNINFO annual report not discovered")

        doc = await _find_existing_report(db)
        if not doc:
            doc = await _persist_discovered_report(db, reports[0])
        elif doc.pdf_url != reports[0].get("pdf_url") and _pdf_host_ok(reports[0].get("pdf_url")):
            doc = await _persist_discovered_report(db, reports[0])

        report_id = int(doc.id)

        download_result = await company_v2_report_pdf_service.download_report(report_id, db)
        await db.refresh(doc)
        if not download_result.get("ok") and doc.download_status not in {"downloaded", "parsed", "verified"}:
            return _save_failure("DOWNLOAD_FAILED", str(download_result.get("reason") or download_result.get("error_code")), report_id=report_id, doc=doc)

        parse_result = await company_v2_pdf_text_parser.parse_report(report_id, db)
        await db.refresh(doc)
        if not parse_result.get("ok") and doc.parse_status not in {"parsed", "partial"}:
            return _save_failure("PARSE_FAILED", str(parse_result.get("error_code") or parse_result.get("status")), report_id=report_id, doc=doc)

        local_path = Path(doc.local_path) if doc.local_path else None
        sidecar = local_path.with_suffix(".pages.json") if local_path else None
        if not sidecar or not sidecar.exists():
            return _save_failure("PARSE_FAILED", "parsed page sidecar unavailable", report_id=report_id, doc=doc)

        parsed_source = json.loads(sidecar.read_text(encoding="utf-8"))
        debug_data = await company_v2_debug_service.build_full(
            MARKET,
            SYMBOL,
            include_raw=False,
            providers=None,
            force_refresh=False,
            max_raw_chars=5000,
            db=db,
            history=True,
            period="annual",
            start_year=REPORT_YEAR,
            end_year=REPORT_YEAR,
        )

        report_document = {
            "report_id": report_id,
            "ts_code": doc.ts_code,
            "symbol": SYMBOL,
            "report_year": REPORT_YEAR,
            "report_type": REPORT_TYPE,
            "pdf_url": doc.pdf_url,
            "source": doc.source or "cninfo",
        }
        try:
            ai_result = await asyncio.to_thread(
                verify_with_ai,
                report_document,
                parsed_source,
                debug_data,
                None,
                REPORT_YEAR,
                REPORT_TYPE,
            )
        except Exception as exc:
            return _save_failure("AI_VERIFY_FAILED", str(exc)[:500], report_id=report_id, doc=doc)

        payload = sanitize_ai_verification_payload({
            "ok": True,
            "report_id": report_id,
            "report_year": REPORT_YEAR,
            "report_type": REPORT_TYPE,
            "pdf_url": doc.pdf_url,
            "download_status": doc.download_status,
            "parse_status": doc.parse_status,
            "page_count": parsed_source.get("page_count"),
            "parsed_page_sidecar_exists": True,
            "ai_verification_status": ai_result.get("verification_status"),
            "fields": ai_result.get("fields") or {},
            "human_review_queue": ai_result.get("human_review_queue") or [],
            "warnings": ai_result.get("warnings") or [],
        })
        _write_json(OFFICIAL_ARTIFACT, payload)
        _write_json(QUEUE_ARTIFACT, {
            "report_id": report_id,
            "report_year": REPORT_YEAR,
            "report_type": REPORT_TYPE,
            "human_review_queue": payload.get("human_review_queue") or [],
        })

        fields = payload.get("fields") or {}
        counts = _status_counts(fields)
        summary = {
            "report_id": report_id,
            "report_year": REPORT_YEAR,
            "report_type": REPORT_TYPE,
            "pdf_url": doc.pdf_url,
            "download_status": doc.download_status,
            "parse_status": doc.parse_status,
            "page_count": parsed_source.get("page_count"),
            "parsed_page_sidecar_exists": True,
            "fields_checked": len(fields),
            **counts,
            "human_review_queue": payload.get("human_review_queue") or [],
            "final_status": payload.get("ai_verification_status"),
            "local_path_leaked": _contains_local_path(payload),
            "full_pdf_text_returned": _contains_full_pdf_text(payload),
        }
        _write_summary(summary)

        print(json.dumps({
            "ok": True,
            "report_id": report_id,
            "download_status": doc.download_status,
            "parse_status": doc.parse_status,
            "page_count": parsed_source.get("page_count"),
            "parsed_page_sidecar_exists": True,
            "ai_verification_status": payload.get("ai_verification_status"),
            "human_review_queue_count": len(payload.get("human_review_queue") or []),
            "artifacts": {
                "official": str(OFFICIAL_ARTIFACT),
                "queue": str(QUEUE_ARTIFACT),
                "summary": str(SUMMARY_ARTIFACT),
            },
        }, ensure_ascii=False, indent=2))
        return payload


if __name__ == "__main__":
    asyncio.run(run())
