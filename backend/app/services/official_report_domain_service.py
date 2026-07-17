"""Shared official-report domain service used by pages and chat tools."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_document import ReportDocument
from app.services.report_document_classifier import KIND_ANNUAL_FULL, classify_report_document


class OfficialReportDomainService:
    async def list_official_annual_reports(
        self,
        db: AsyncSession,
        *,
        ts_code: str,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(ReportDocument)
                .where(ReportDocument.ts_code == ts_code)
                .order_by(ReportDocument.report_year.desc(), ReportDocument.period_end.desc())
                .limit(max(limit * 3, 20))
            )
        ).scalars().all()
        reports: list[dict[str, Any]] = []
        for row in rows:
            classification = classify_report_document(row.title, report_type=row.report_type)
            if classification.report_document_kind != KIND_ANNUAL_FULL:
                continue
            reports.append({
                "report_id": row.id,
                "ts_code": row.ts_code,
                "title": row.title,
                "report_type": row.report_type,
                "report_year": row.report_year,
                "period_end": row.period_end,
                "disclosure_date": row.disclosure_date,
                "pdf_url": row.pdf_url or row.source_url,
                "parsed": bool(row.parsed),
                "rag_status": row.rag_status,
                "chunk_count": row.chunk_count,
                "report_document_kind": classification.report_document_kind,
                "classification_reason": classification.classification_reason,
            })
            if len(reports) >= limit:
                break
        return reports


official_report_domain_service = OfficialReportDomainService()
