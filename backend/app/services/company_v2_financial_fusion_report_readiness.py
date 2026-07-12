"""Readiness state machine for Company V2 financial fusion."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_document import ReportDocument
from app.services.company_v2_financial_evidence_fusion_service import company_v2_financial_evidence_fusion_service
from app.services.company_v2_report_rag_index_service import company_v2_report_rag_index_service
from app.services.company_v2_report_pdf_service import validate_cninfo_pdf_url


_PDF_READY_STATUSES = {"downloaded", "exists"}
_PARSE_READY_STATUSES = {"parsed", "partial"}
_RAG_READY_STATUSES = {"indexed", "partial"}


def _symbol_from_ts_code(ts_code: str | None) -> str:
    return (ts_code or "").split(".")[0]


@dataclass(slots=True)
class ReadinessRecord:
    report_id: int | None
    report_year: int | None
    report_type: str | None
    title: str | None
    source_url: str | None
    report_view_ready: bool
    pdf_url_ready: bool
    url_whitelist_valid: bool
    canonical_report: bool
    discovery_status: str
    pdf_status: str
    parse_status: str
    rag_status: str
    rag_index_status: str
    structured_status: str
    status: str
    discovery_ready: bool
    qa_ready: bool
    pdf_ready: bool
    parse_ready: bool
    rag_ready: bool
    structured_ready: bool
    fusion_ready: bool
    missing_prerequisites: list[str]
    next_manual_action: str | None
    next_manual_action_for_view: str | None
    next_manual_action_for_rag: str | None
    next_manual_action_for_fusion: str | None
    local_path_exists: bool
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "report_year": self.report_year,
            "report_type": self.report_type,
            "title": self.title,
            "source_url": self.source_url,
            "report_view_ready": self.report_view_ready,
            "pdf_url_ready": self.pdf_url_ready,
            "url_whitelist_valid": self.url_whitelist_valid,
            "canonical_report": self.canonical_report,
            "discovery_status": self.discovery_status,
            "pdf_status": self.pdf_status,
            "parse_status": self.parse_status,
            "rag_status": self.rag_status,
            "rag_index_status": self.rag_index_status,
            "structured_status": self.structured_status,
            "status": self.status,
            "discovery_ready": self.discovery_ready,
            "qa_ready": self.qa_ready,
            "pdf_ready": self.pdf_ready,
            "parse_ready": self.parse_ready,
            "rag_ready": self.rag_ready,
            "structured_ready": self.structured_ready,
            "fusion_ready": self.fusion_ready,
            "missing_prerequisites": self.missing_prerequisites,
            "next_manual_action": self.next_manual_action,
            "next_manual_action_for_view": self.next_manual_action_for_view,
            "next_manual_action_for_rag": self.next_manual_action_for_rag,
            "next_manual_action_for_fusion": self.next_manual_action_for_fusion,
            "local_path_exists": self.local_path_exists,
            "reason": self.reason,
        }


class CompanyV2FinancialFusionReportReadinessService:
    def _structured_ready(self, symbol: str, report_id: int, report_year: int | None, report_type: str | None) -> bool:
        structured = company_v2_financial_evidence_fusion_service._load_structured(symbol, report_id, report_year, report_type)  # noqa: SLF001
        return structured.get("source_mode") != "unavailable"

    def _view_state(self, symbol: str, doc: ReportDocument) -> dict[str, Any]:
        source_url = doc.pdf_url or doc.source_url or ""
        url_whitelist_valid, url_reason = validate_cninfo_pdf_url(source_url)
        symbol_match = _symbol_from_ts_code(doc.ts_code) == symbol
        report_view_ready = bool(source_url and url_whitelist_valid and symbol_match)
        return {
            "source_url": source_url or None,
            "report_view_ready": report_view_ready,
            "pdf_url_ready": report_view_ready,
            "url_whitelist_valid": url_whitelist_valid,
            "canonical_report": symbol_match and bool(source_url),
            "view_reason": None if report_view_ready else url_reason,
        }

    def _summarize_doc(self, symbol: str, doc: ReportDocument) -> ReadinessRecord:
        local_path_exists = bool(doc.local_path and Path(doc.local_path).exists())
        pdf_ready = doc.download_status in _PDF_READY_STATUSES and local_path_exists
        parse_ready = bool(doc.parsed or doc.parse_status in _PARSE_READY_STATUSES)
        rag_status = company_v2_report_rag_index_service.status(doc.id).get("status") or doc.rag_status or "pending"
        rag_ready = rag_status in _RAG_READY_STATUSES
        structured_ready = self._structured_ready(symbol, doc.id, doc.report_year, doc.report_type)
        view_state = self._view_state(symbol, doc)

        discovery_status = "report_discovered"
        if not doc.source_url and not doc.pdf_url:
            discovery_status = "report_not_discovered"

        pdf_status = "pdf_downloaded" if pdf_ready else "pdf_not_downloaded"
        parse_status = "parsed" if parse_ready else ("parse_pending" if pdf_ready else "pdf_not_downloaded")
        if not pdf_ready and doc.download_status in {"failed"}:
            pdf_status = "pdf_not_downloaded"
            parse_status = "parse_pending"

        if not doc.download_status or doc.download_status == "pending":
            if not local_path_exists:
                pdf_status = "pdf_not_downloaded"
                parse_status = "parse_pending"

        if not parse_ready and pdf_ready:
            parse_status = "parse_pending"
        if parse_ready and not rag_ready:
            rag_status = "rag_not_indexed"
        if rag_ready and not structured_ready:
            structured_status = "structured_data_missing"
        else:
            structured_status = "ready" if structured_ready else "structured_data_missing"

        status = "ready"
        missing_prerequisites: list[str] = []
        next_manual_action: str | None = None

        if not discovery_status or discovery_status == "report_not_discovered":
            status = "report_not_discovered"
            missing_prerequisites.append("report_discovery")
            next_manual_action = "discover_report"
        elif not pdf_ready:
            status = "pdf_not_downloaded"
            missing_prerequisites.append("pdf_download")
            next_manual_action = "download_report"
        elif not parse_ready:
            status = "parse_pending"
            missing_prerequisites.append("parse_report")
            next_manual_action = "parse_report"
        elif not rag_ready:
            status = "rag_not_indexed"
            missing_prerequisites.append("rag_index")
            next_manual_action = "build_rag_index"
        elif not structured_ready:
            status = "structured_data_missing"
            missing_prerequisites.append("structured_data")
            next_manual_action = "review_structured_data"
        else:
            status = "ready"
            next_manual_action = "run_fusion"

        next_manual_action_for_view = None if view_state["report_view_ready"] else "open_official_report"
        next_manual_action_for_rag = next_manual_action if status != "report_not_discovered" else "discover_report"
        next_manual_action_for_fusion = next_manual_action_for_rag

        fusion_ready = status == "ready"
        return ReadinessRecord(
            report_id=doc.id,
            report_year=doc.report_year,
            report_type=doc.report_type,
            title=doc.title,
            source_url=view_state["source_url"],
            report_view_ready=view_state["report_view_ready"],
            pdf_url_ready=view_state["pdf_url_ready"],
            url_whitelist_valid=view_state["url_whitelist_valid"],
            canonical_report=view_state["canonical_report"],
            discovery_status=discovery_status,
            pdf_status=pdf_status,
            parse_status=parse_status,
            rag_status=rag_status,
            rag_index_status=rag_status,
            structured_status=structured_status,
            status=status,
            discovery_ready=discovery_status != "report_not_discovered",
            qa_ready=rag_ready,
            pdf_ready=pdf_ready,
            parse_ready=parse_ready,
            rag_ready=rag_ready,
            structured_ready=structured_ready,
            fusion_ready=fusion_ready,
            missing_prerequisites=missing_prerequisites,
            next_manual_action=next_manual_action,
            next_manual_action_for_view=next_manual_action_for_view,
            next_manual_action_for_rag=next_manual_action_for_rag,
            next_manual_action_for_fusion=next_manual_action_for_fusion,
            local_path_exists=local_path_exists,
        )

    def _missing_record(self, symbol: str) -> ReadinessRecord:
        return ReadinessRecord(
            report_id=None,
            report_year=None,
            report_type=None,
            title=None,
            source_url=None,
            report_view_ready=False,
            pdf_url_ready=False,
            url_whitelist_valid=False,
            canonical_report=False,
            discovery_status="report_not_discovered",
            pdf_status="pdf_not_downloaded",
            parse_status="parse_pending",
            rag_status="rag_not_indexed",
            rag_index_status="rag_not_indexed",
            structured_status="structured_data_missing",
            status="report_not_discovered",
            discovery_ready=False,
            qa_ready=False,
            pdf_ready=False,
            parse_ready=False,
            rag_ready=False,
            structured_ready=False,
            fusion_ready=False,
            missing_prerequisites=["report_discovery"],
            next_manual_action="discover_report",
            next_manual_action_for_view=None,
            next_manual_action_for_rag="discover_report",
            next_manual_action_for_fusion="discover_report",
            local_path_exists=False,
            reason=f"no reports found for {symbol}",
        )

    async def get_symbol_readiness(self, market: str, symbol: str, db: AsyncSession) -> dict[str, Any]:
        stmt = select(ReportDocument).where(ReportDocument.ts_code.like(f"{symbol}.%"))
        result = await db.execute(stmt)
        docs = list(result.scalars().all())
        if not docs:
            missing = self._missing_record(symbol)
            return {
                "ok": True,
                "market": market.upper(),
                "symbol": symbol,
                "status": missing.status,
                "latest_annual_report_year": None,
                "latest_report_id": None,
                "report_view_ready": False,
                "pdf_url_ready": False,
                "source_url": None,
                "url_whitelist_valid": False,
                "canonical_report": False,
                "discovery_ready": False,
                "rag_index_status": "rag_not_indexed",
                "pdf_ready": False,
                "parse_ready": False,
                "rag_ready": False,
                "qa_ready": False,
                "structured_ready": False,
                "fusion_ready": False,
                "fusion_readiness_status": missing.status,
                "missing_prerequisites": missing.missing_prerequisites,
                "next_manual_action": missing.next_manual_action,
                "next_manual_action_for_view": missing.next_manual_action_for_view,
                "next_manual_action_for_rag": missing.next_manual_action_for_rag,
                "next_manual_action_for_fusion": missing.next_manual_action_for_fusion,
                "reports": [],
                "reason": missing.reason,
            }

        summaries = [self._summarize_doc(symbol, doc).to_dict() for doc in sorted(docs, key=lambda item: (item.report_year or 0, item.id), reverse=True)]
        annuals = [summary for summary in summaries if summary.get("report_type") == "annual"]
        selected = annuals[0] if annuals else summaries[0]
        return {
            "ok": True,
            "market": market.upper(),
            "symbol": symbol,
            "status": selected["status"],
            "latest_annual_report_year": selected.get("report_year") if selected.get("report_type") == "annual" else (annuals[0].get("report_year") if annuals else None),
            "latest_report_id": selected.get("report_id"),
            "report_view_ready": selected.get("report_view_ready", False),
            "pdf_url_ready": selected.get("pdf_url_ready", False),
            "source_url": selected.get("source_url"),
            "url_whitelist_valid": selected.get("url_whitelist_valid", False),
            "canonical_report": selected.get("canonical_report", False),
            "discovery_ready": selected.get("discovery_ready", False),
            "rag_index_status": selected.get("rag_index_status", selected.get("rag_status")),
            "qa_ready": selected.get("qa_ready", False),
            "pdf_ready": selected.get("pdf_ready", False),
            "parse_ready": selected.get("parse_ready", False),
            "rag_ready": selected.get("rag_ready", False),
            "structured_ready": selected.get("structured_ready", False),
            "fusion_ready": selected.get("fusion_ready", False),
            "fusion_readiness_status": selected.get("status"),
            "missing_prerequisites": selected.get("missing_prerequisites", []),
            "next_manual_action": selected.get("next_manual_action"),
            "next_manual_action_for_view": selected.get("next_manual_action_for_view"),
            "next_manual_action_for_rag": selected.get("next_manual_action_for_rag"),
            "next_manual_action_for_fusion": selected.get("next_manual_action_for_fusion"),
            "reports": summaries,
            "reason": selected.get("reason"),
        }

    async def get_report_readiness(self, market: str, symbol: str, report_id: int, db: AsyncSession) -> dict[str, Any]:
        stmt = select(ReportDocument).where(ReportDocument.id == report_id)
        result = await db.execute(stmt)
        doc: ReportDocument | None = result.scalars().first()
        if not doc:
            return {
                "ok": False,
                "error_code": "REPORT_NOT_FOUND",
                "message": "report_id not found",
            }
        if not doc.ts_code.startswith(symbol):
            return {
                "ok": False,
                "error_code": "REPORT_SYMBOL_MISMATCH",
                "message": "report_id does not belong to this symbol",
            }
        record = self._summarize_doc(symbol, doc).to_dict()
        return {"ok": True, "market": market.upper(), "symbol": symbol, **record}


company_v2_financial_fusion_report_readiness_service = CompanyV2FinancialFusionReportReadinessService()
