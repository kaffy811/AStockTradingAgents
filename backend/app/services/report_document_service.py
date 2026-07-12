"""
app/services/report_document_service.py — 年报文件录入服务（Phase 6D）

提供 upsert_discovered_report：
  - 根据 ts_code + report_type + period + source 去重
  - 根据 pdf_url 去重
  - 高置信度（>= 0.75）候选自动入库
  - 返回 report_id 或 None（已存在或跳过）
"""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_document import ReportDocument

log = logging.getLogger(__name__)

_HIGH_CONFIDENCE = 0.75


def _ts_code_from_stock_code(stock_code: str) -> str:
    """Convert plain stock code to ts_code format."""
    code = stock_code.strip()
    if "." in code:
        return code
    if code.startswith(("6", "5")):
        return f"{code}.SH"
    elif code.startswith(("0", "2", "3")):
        return f"{code}.SZ"
    elif code.startswith(("4", "8", "9")):
        return f"{code}.BJ"
    return f"{code}.SH"


class ReportDocumentService:
    """Service for managing report_documents table entries."""

    async def upsert_discovered_report(
        self,
        candidate: dict[str, Any],
        db: AsyncSession,
    ) -> dict[str, Any]:
        """
        Upsert a discovered report candidate into report_documents.

        Returns:
            {"status": "inserted"|"exists"|"skipped", "report_id": int|None, "reason": str}
        """
        stock_code = candidate.get("stock_code") or ""
        report_type = candidate.get("report_type") or ""
        period = candidate.get("period") or ""
        source = candidate.get("source") or ""
        pdf_url = candidate.get("pdf_url") or ""
        confidence = candidate.get("confidence") or 0.0
        ts_code = _ts_code_from_stock_code(stock_code)

        if not stock_code or not report_type:
            return {"status": "skipped", "report_id": None, "reason": "Missing stock_code or report_type"}

        if confidence < _HIGH_CONFIDENCE:
            return {
                "status": "skipped",
                "report_id": None,
                "reason": f"confidence {confidence:.2f} < {_HIGH_CONFIDENCE} (threshold)",
            }

        # Check duplicate: by pdf_url
        if pdf_url:
            stmt = select(ReportDocument).where(ReportDocument.pdf_url == pdf_url)
            result = await db.execute(stmt)
            existing = result.scalars().first()
            if existing:
                return {"status": "exists", "report_id": existing.id, "reason": "pdf_url already in db"}

        # Format period_end as YYYY-MM-DD
        period_end = period
        if len(period) == 8:
            period_end = f"{period[:4]}-{period[4:6]}-{period[6:]}"

        # Check duplicate: by ts_code + report_type + period_end + source
        stmt2 = select(ReportDocument).where(
            ReportDocument.ts_code == ts_code,
            ReportDocument.report_type == report_type,
            ReportDocument.period_end == period_end,
            ReportDocument.source == source,
        )
        result2 = await db.execute(stmt2)
        existing2 = result2.scalars().first()
        if existing2:
            return {"status": "exists", "report_id": existing2.id, "reason": "ts_code+type+period+source already in db"}

        # Format disclosure_date
        ann_date = candidate.get("ann_date") or ""
        disclosure_date = ann_date
        if len(ann_date) == 8:
            disclosure_date = f"{ann_date[:4]}-{ann_date[4:6]}-{ann_date[6:]}"

        warnings = candidate.get("warnings") or []
        doc = ReportDocument(
            ts_code=ts_code,
            report_type=report_type,
            period_end=period_end,
            title=candidate.get("title") or "",
            source_url=candidate.get("source_url") or "",
            pdf_url=pdf_url,
            report_year=candidate.get("report_year"),
            source=source,
            download_status="pending",
            confidence=confidence,
            warnings_json=json.dumps(warnings, ensure_ascii=False) if warnings else None,
            disclosure_date=disclosure_date,
            parsed=False,
        )

        try:
            db.add(doc)
            await db.flush()
            await db.commit()
            log.info(
                "ReportDocumentService: inserted report_id=%d ts_code=%s %s %s",
                doc.id, ts_code, report_type, period_end,
            )
            return {"status": "inserted", "report_id": doc.id, "reason": "new record created"}
        except Exception as e:
            await db.rollback()
            log.error("ReportDocumentService: insert failed: %s", e)
            return {"status": "skipped", "report_id": None, "reason": f"db error: {e}"}

    async def get_by_ts_code(
        self,
        ts_code: str,
        db: AsyncSession,
        limit: int = 20,
    ) -> list[dict]:
        """Fetch all report_documents for a ts_code, ordered by period_end desc."""
        stmt = (
            select(ReportDocument)
            .where(ReportDocument.ts_code == ts_code)
            .order_by(ReportDocument.period_end.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        docs = result.scalars().all()
        return [self._to_dict(d) for d in docs]

    async def get_by_id(self, report_id: int, db: AsyncSession) -> ReportDocument | None:
        """Fetch a single report document by ID."""
        stmt = select(ReportDocument).where(ReportDocument.id == report_id)
        result = await db.execute(stmt)
        return result.scalars().first()

    @staticmethod
    def _to_dict(doc: ReportDocument) -> dict:
        excerpt = doc.text_excerpt
        return {
            "id":              doc.id,
            "ts_code":         doc.ts_code,
            "report_type":     doc.report_type,
            "report_year":     doc.report_year,
            "period_end":      doc.period_end,
            "title":           doc.title,
            "source":          doc.source,
            "source_url":      doc.source_url,
            "pdf_url":         doc.pdf_url,
            "download_status": doc.download_status,
            "confidence":      doc.confidence,
            "disclosure_date": doc.disclosure_date,
            "parsed":          doc.parsed,
            "file_size":       doc.file_size,
            "parse_status":    doc.parse_status,
            "text_excerpt":    (excerpt[:200] + "…") if excerpt and len(excerpt) > 200 else excerpt,
            "warnings":        json.loads(doc.warnings_json) if doc.warnings_json else [],
            "created_at":      doc.created_at.isoformat() if doc.created_at else None,
        }


report_document_service = ReportDocumentService()
