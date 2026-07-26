"""Shared official-report domain service used by pages and chat tools."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_document import ReportDocument
from app.services.report_document_classifier import KIND_ANNUAL_FULL, classify_report_document


class OfficialReportDomainService:
    async def get_official_report_by_id(
        self,
        db: AsyncSession,
        *,
        report_id: int,
    ) -> dict[str, Any] | None:
        row = await db.get(ReportDocument, report_id)
        if row is None:
            return None
        classification = classify_report_document(row.title, report_type=row.report_type)
        return {
            "report_id": row.id,
            "ts_code": row.ts_code,
            "title": row.title,
            "report_type": row.report_type,
            "report_year": row.report_year,
            "period_end": row.period_end,
            "disclosure_date": row.disclosure_date,
            "source_page_url": row.source_url,
            "source_url": row.source_url,
            "pdf_url": row.pdf_url or row.source_url,
            "parsed": bool(row.parsed),
            "rag_status": row.rag_status,
            "chunk_count": row.chunk_count,
            "report_document_kind": classification.report_document_kind,
            "classification_reason": classification.classification_reason,
        }

    async def list_official_annual_reports(
        self,
        db: AsyncSession,
        *,
        ts_code: str,
        limit: int = 8,
        requested_year: int | None = None,
    ) -> list[dict[str, Any]]:
        """List annual full-text reports for one symbol (P1.9 selection policy).

        - ``requested_year`` is pushed down to SQL: exact-year requests never
          see (and can never fall back to) other years.
        - Deterministic ordering: report_year desc, period_end desc,
          disclosure_date desc (nulls last), then stable id asc tie-break —
          never insertion order / created_at / URL strings.
        - Rows that are not annual full-text documents (inquiry-letter replies,
          disclosure reminders misfiled as report_type=annual) are excluded by
          the title classifier; the scan window is sized so pollution rows
          cannot truncate real reports (bounded per symbol, no market scan).
        - One official document per (ts_code, report_year): duplicates and
          re-crawled variants dedup to the first row in deterministic order.
        """
        stmt = select(ReportDocument).where(ReportDocument.ts_code == ts_code)
        if requested_year is not None:
            stmt = stmt.where(ReportDocument.report_year == int(requested_year))
        stmt = stmt.order_by(
            ReportDocument.report_year.desc(),
            ReportDocument.period_end.desc(),
            ReportDocument.disclosure_date.desc().nulls_last(),
            ReportDocument.id.asc(),
        ).limit(20 if requested_year is not None else max(limit * 6, 40))
        rows = (await db.execute(stmt)).scalars().all()
        reports: list[dict[str, Any]] = []
        seen_years: set[int | None] = set()
        for row in rows:
            classification = classify_report_document(row.title, report_type=row.report_type)
            if classification.report_document_kind != KIND_ANNUAL_FULL:
                continue
            if row.report_year in seen_years:
                continue  # dedup: one official annual document per year
            seen_years.add(row.report_year)
            reports.append({
                "report_id": row.id,
                "ts_code": row.ts_code,
                "title": row.title,
                "report_type": row.report_type,
                "report_year": row.report_year,
                "period_end": row.period_end,
                "disclosure_date": row.disclosure_date,
                "source_url": row.source_url,
                "source_page_url": row.source_url,
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
