"""Stage 2 manual preparation plan and status helpers for Company V2 fusion."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_document import ReportDocument
from app.services.company_v2_financial_fusion_report_readiness import (
    company_v2_financial_fusion_report_readiness_service,
)
from app.services.company_v2_report_rag_index_manager import company_v2_report_rag_index_manager
from app.services.company_v2_report_rag_index_service import company_v2_report_rag_index_service


@dataclass(slots=True)
class Stage2PlanRecord:
    symbol: str
    report_id: int | None
    report_year: int | None
    report_type: str | None
    title: str | None
    current_status: str
    discovery_status: str
    download_status: str
    parse_status: str
    index_status: str
    fusion_readiness: str
    current_job: dict[str, Any] | None
    last_error: str | None
    next_manual_action: str | None
    steps: list[dict[str, Any]]
    report: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "report_id": self.report_id,
            "report_year": self.report_year,
            "report_type": self.report_type,
            "title": self.title,
            "current_status": self.current_status,
            "discovery_status": self.discovery_status,
            "download_status": self.download_status,
            "parse_status": self.parse_status,
            "index_status": self.index_status,
            "fusion_readiness": self.fusion_readiness,
            "current_job": self.current_job,
            "last_error": self.last_error,
            "next_manual_action": self.next_manual_action,
            "steps": self.steps,
            "report": self.report,
        }


def _symbol_from_ts_code(ts_code: str | None) -> str:
    return (ts_code or "").split(".")[0]


def _select_latest_annual_report(docs: list[ReportDocument]) -> ReportDocument | None:
    annuals = [doc for doc in docs if (doc.report_type or "").lower() == "annual"]
    pool = annuals or docs
    if not pool:
        return None
    return sorted(pool, key=lambda item: ((item.report_year or 0), item.id), reverse=True)[0]


def _local_sidecar(doc: ReportDocument) -> str | None:
    if not doc.local_path:
        return None
    sidecar = Path(doc.local_path).with_suffix(".pages.json")
    return str(sidecar) if sidecar.exists() else None


class CompanyV2FinancialFusionStage2PlanService:
    async def _load_docs(self, market: str, symbol: str, db: AsyncSession) -> list[ReportDocument]:
        stmt = select(ReportDocument).where(ReportDocument.ts_code.like(f"{symbol}.%"))
        result = await db.execute(stmt)
        docs = list(result.scalars().all())
        if market.upper() != "CN":
            return []
        return sorted(docs, key=lambda item: ((item.report_year or 0), item.id), reverse=True)

    def _build_steps(self, *, report_view_ready: bool, current_status: str) -> list[dict[str, Any]]:
        if current_status == "ready":
            return [
                {"step": "view", "status": "ready" if report_view_ready else "blocked", "required_for_view": True, "required_for_rag": False},
                {"step": "download", "status": "done", "required": True},
                {"step": "parse", "status": "done", "required": True},
                {"step": "index", "status": "done", "required": True},
                {"step": "fusion", "status": "pending", "required": True},
            ]
        if current_status == "structured_data_missing":
            return [
                {"step": "view", "status": "ready" if report_view_ready else "blocked", "required_for_view": True, "required_for_rag": False},
                {"step": "download", "status": "done", "required": True},
                {"step": "parse", "status": "done", "required": True},
                {"step": "index", "status": "done", "required": True},
                {"step": "fusion", "status": "blocked", "required": True},
            ]
        if current_status == "rag_not_indexed":
            return [
                {"step": "view", "status": "ready" if report_view_ready else "blocked", "required_for_view": True, "required_for_rag": False},
                {"step": "download", "status": "done", "required": True},
                {"step": "parse", "status": "done", "required": True},
                {"step": "index", "status": "pending", "required": True},
                {"step": "fusion", "status": "blocked", "required": True},
            ]
        if current_status == "parse_pending":
            return [
                {"step": "view", "status": "ready" if report_view_ready else "blocked", "required_for_view": True, "required_for_rag": False},
                {"step": "download", "status": "done", "required": True},
                {"step": "parse", "status": "pending", "required": True},
                {"step": "index", "status": "blocked", "required": True},
                {"step": "fusion", "status": "blocked", "required": True},
            ]
        if current_status == "pdf_not_downloaded":
            return [
                {"step": "view", "status": "ready" if report_view_ready else "blocked", "required_for_view": True, "required_for_rag": False},
                {"step": "download", "status": "pending", "required": True},
                {"step": "parse", "status": "blocked", "required": True},
                {"step": "index", "status": "blocked", "required": True},
                {"step": "fusion", "status": "blocked", "required": True},
            ]
        return [
            {"step": "view", "status": "ready" if report_view_ready else "blocked", "required_for_view": True, "required_for_rag": False},
            {"step": "download", "status": "blocked", "required": True},
            {"step": "parse", "status": "blocked", "required": True},
            {"step": "index", "status": "blocked", "required": True},
            {"step": "fusion", "status": "blocked", "required": True},
        ]

    async def get_report_prepare_status(self, market: str, symbol: str, report_id: int, db: AsyncSession) -> dict[str, Any]:
        result = await db.execute(select(ReportDocument).where(ReportDocument.id == report_id))
        doc: ReportDocument | None = result.scalars().first()
        if not doc:
            return {"ok": False, "error_code": "REPORT_NOT_FOUND", "message": "report_id not found"}
        if _symbol_from_ts_code(doc.ts_code) != symbol:
            return {"ok": False, "error_code": "REPORT_SYMBOL_MISMATCH", "message": "report_id does not belong to this symbol"}

        readiness = await company_v2_financial_fusion_report_readiness_service.get_report_readiness(market, symbol, report_id, db)
        rag_status = company_v2_report_rag_index_service.status(report_id)
        current_job = company_v2_report_rag_index_manager.get_index_progress(report_id)
        current_status = readiness.get("status") if readiness.get("ok") else "report_not_discovered"
        download_status = doc.download_status or "pending"
        parse_status = doc.parse_status or "pending"
        index_status = rag_status.get("status") or "pending"
        report_view_ready = bool(readiness.get("report_view_ready"))
        fusion_readiness = "ready" if readiness.get("fusion_ready") else current_status
        last_error = doc.download_error or doc.parse_error or doc.rag_error or rag_status.get("last_error") or readiness.get("reason")
        next_manual_action = readiness.get("next_manual_action_for_rag") or readiness.get("next_manual_action")
        return {
            "ok": True,
            "market": market.upper(),
            "symbol": symbol,
            "report_id": report_id,
            "report_year": doc.report_year,
            "report_type": doc.report_type,
            "title": doc.title,
            "report_view_ready": report_view_ready,
            "pdf_url_ready": bool(readiness.get("pdf_url_ready")),
            "source_url": readiness.get("source_url"),
            "url_whitelist_valid": bool(readiness.get("url_whitelist_valid")),
            "canonical_report": bool(readiness.get("canonical_report")),
            "qa_ready": bool(readiness.get("qa_ready")),
            "discovery_status": "report_discovered" if doc.source_url or doc.pdf_url else "report_not_discovered",
            "download_status": download_status,
            "parse_status": parse_status,
            "rag_index_status": index_status,
            "index_status": index_status,
            "fusion_readiness": fusion_readiness,
            "rag_readiness_status": current_status,
            "fusion_readiness_status": fusion_readiness,
            "current_job": current_job,
            "last_error": last_error,
            "next_manual_action": next_manual_action,
            "next_manual_action_for_view": readiness.get("next_manual_action_for_view"),
            "next_manual_action_for_rag": readiness.get("next_manual_action_for_rag"),
            "next_manual_action_for_fusion": readiness.get("next_manual_action_for_fusion"),
            "steps": self._build_steps(report_view_ready=report_view_ready, current_status=current_status),
            "readiness": readiness,
        }

    async def get_symbol_stage2_plan(self, market: str, symbol: str, db: AsyncSession) -> dict[str, Any]:
        docs = await self._load_docs(market, symbol, db)
        if not docs:
            return {
                "ok": True,
                "market": market.upper(),
                "symbol": symbol,
                "report_id": None,
                "report_year": None,
                "report_type": None,
                "title": None,
                "current_status": "report_not_discovered",
                "discovery_status": "report_not_discovered",
                "report_view_ready": False,
                "pdf_url_ready": False,
                "source_url": None,
                "url_whitelist_valid": False,
                "canonical_report": False,
                "download_status": "pending",
                "parse_status": "parse_pending",
                "rag_index_status": "pending",
                "index_status": "pending",
                "fusion_readiness": "report_not_discovered",
                "rag_readiness_status": "report_not_discovered",
                "fusion_readiness_status": "report_not_discovered",
                "current_job": None,
                "last_error": "no reports found",
                "next_manual_action": "discover_report",
                "next_manual_action_for_view": None,
                "next_manual_action_for_rag": "discover_report",
                "next_manual_action_for_fusion": "discover_report",
                "steps": [
                    {"step": "view", "status": "blocked", "required_for_view": True, "required_for_rag": False},
                    {"step": "download", "status": "blocked", "required": True},
                    {"step": "parse", "status": "blocked", "required": True},
                    {"step": "index", "status": "blocked", "required": True},
                    {"step": "fusion", "status": "blocked", "required": True},
                ],
                "report": None,
            }

        doc = _select_latest_annual_report(docs) or docs[0]
        detail = await self.get_report_prepare_status(market, symbol, doc.id, db)
        return {
            "ok": True,
            "market": market.upper(),
            "symbol": symbol,
            "report_id": detail["report_id"],
            "report_year": detail["report_year"],
            "report_type": detail["report_type"],
            "title": detail["title"],
            "current_status": detail["rag_readiness_status"],
            "discovery_status": detail["discovery_status"],
            "report_view_ready": detail["report_view_ready"],
            "pdf_url_ready": detail["pdf_url_ready"],
            "source_url": detail["source_url"],
            "url_whitelist_valid": detail["url_whitelist_valid"],
            "canonical_report": detail["canonical_report"],
            "download_status": detail["download_status"],
            "parse_status": detail["parse_status"],
            "rag_index_status": detail["rag_index_status"],
            "index_status": detail["index_status"],
            "qa_ready": detail["qa_ready"],
            "fusion_readiness": detail["fusion_readiness_status"],
            "rag_readiness_status": detail["rag_readiness_status"],
            "fusion_readiness_status": detail["fusion_readiness_status"],
            "current_job": detail["current_job"],
            "last_error": detail["last_error"],
            "next_manual_action": detail["next_manual_action"],
            "next_manual_action_for_view": detail["next_manual_action_for_view"],
            "next_manual_action_for_rag": detail["next_manual_action_for_rag"],
            "next_manual_action_for_fusion": detail["next_manual_action_for_fusion"],
            "steps": detail["steps"],
            "report": detail["readiness"],
            "reports": [await self.get_report_prepare_status(market, symbol, row.id, db) for row in docs],
        }


company_v2_financial_fusion_stage2_plan_service = CompanyV2FinancialFusionStage2PlanService()
