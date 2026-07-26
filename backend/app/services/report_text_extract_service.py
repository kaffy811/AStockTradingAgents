"""
app/services/report_text_extract_service.py — PDF 文本提取服务（Phase 6E）

使用 pdfminer.six 提取 PDF 正文，截取 5000-8000 字符作为 text_excerpt，
供 AI Data Agent 的 source_reports 使用。

安全约束：
- 只处理 download_status=downloaded 的本地文件
- 文件不存在时写 parse_error，不抛出异常
- 最大提取 8000 字符（AI 上下文预算）
"""
from __future__ import annotations

import logging
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_document import ReportDocument
from app.services.company_v2_pdf_text_parser import parse_pdf_text

log = logging.getLogger(__name__)

_EXCERPT_MAX = 8000
_EXCERPT_MIN = 5000


def _extract_text_pdfminer(path: Path) -> str:
    """Extract plain text from a PDF file using pdfminer.six."""
    try:
        from pdfminer.high_level import extract_text
        text = extract_text(str(path))
        return text or ""
    except ImportError:
        # Fallback to pypdf if pdfminer.six is not installed
        return _extract_text_pypdf(path)
    except Exception as e:
        raise RuntimeError(f"pdfminer extraction failed: {e}") from e


def _extract_text_pypdf(path: Path) -> str:
    """Fallback: extract text using pypdf."""
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    parts = []
    for page in reader.pages:
        t = page.extract_text() or ""
        parts.append(t)
        if sum(len(p) for p in parts) > _EXCERPT_MAX * 2:
            break
    return "\n".join(parts)


def _clean_text(raw: str) -> str:
    """Remove excessive whitespace while preserving CJK structure."""
    import re
    # Collapse multiple blank lines
    text = re.sub(r'\n{3,}', '\n\n', raw)
    # Collapse multiple spaces (but not newlines)
    text = re.sub(r'[ \t]{3,}', ' ', text)
    return text.strip()


class ReportTextExtractService:
    """Extract text excerpt from downloaded annual report PDFs."""

    async def parse(
        self,
        report_id: int,
        db: AsyncSession,
    ) -> dict:
        """
        Extract text excerpt from a downloaded PDF.

        Returns:
            {"status": "parsed"|"skipped"|"failed", "report_id": int, "reason": str, "chars": int}
        """
        stmt = select(ReportDocument).where(ReportDocument.id == report_id)
        result = await db.execute(stmt)
        doc: ReportDocument | None = result.scalars().first()

        if not doc:
            return {"status": "failed", "report_id": report_id, "reason": "report_id not found", "chars": 0}

        if doc.download_status != "downloaded":
            return {
                "status": "skipped",
                "report_id": report_id,
                "reason": f"download_status={doc.download_status!r}, must be 'downloaded' first",
                "chars": 0,
            }

        local_path = doc.local_path or ""
        if not local_path or not Path(local_path).exists():
            err = f"local file not found: {local_path!r}"
            doc.parse_status = "failed"
            doc.parse_error = err
            await db.commit()
            return {"status": "failed", "report_id": report_id, "reason": err, "chars": 0}

        try:
            parsed = parse_pdf_text(local_path, report_id=report_id)
            pages = parsed.get("text_pages") or []
            raw_text = "\n".join(page.get("text") or "" for page in pages) or _extract_text_pdfminer(Path(local_path))
            cleaned = _clean_text(raw_text)

            # Truncate to _EXCERPT_MAX chars
            excerpt = cleaned[:_EXCERPT_MAX]

            sidecar_payload = {
                "report_id": str(report_id),
                "page_count": parsed.get("page_count", 0),
                "text_pages": pages,
                "parse_status": parsed.get("parse_status"),
                "warnings": parsed.get("warnings") or [],
            }
            try:
                Path(local_path).with_suffix(".pages.json").write_text(
                    json.dumps(sidecar_payload, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception:
                pass

            doc.text_excerpt = excerpt
            doc.parsed = parsed.get("parse_status") in {"parsed", "partial"}
            doc.parse_status = "parsed" if parsed.get("parse_status") == "parsed" else parsed.get("parse_status") or "parsed"
            doc.parse_error = None
            await db.commit()

            log.info("Parsed report_id=%d → %d chars excerpt", report_id, len(excerpt))
            return {
                "status": doc.parse_status,
                "report_id": report_id,
                "chars": len(excerpt),
                "reason": "ok",
                "page_count": parsed.get("page_count", 0),
            }

        except Exception as e:
            err = str(e)[:500]
            log.warning("PDF parse failed report_id=%d: %s", report_id, err)
            doc.parse_status = "failed"
            doc.parse_error = err
            try:
                await db.commit()
            except Exception:
                await db.rollback()
            return {"status": "failed", "report_id": report_id, "reason": err, "chars": 0}

    async def get_text(self, report_id: int, db: AsyncSession) -> dict:
        """Return text_excerpt for a report."""
        stmt = select(ReportDocument).where(ReportDocument.id == report_id)
        result = await db.execute(stmt)
        doc: ReportDocument | None = result.scalars().first()

        if not doc:
            return {"found": False, "report_id": report_id, "text": None}

        return {
            "found": True,
            "report_id": report_id,
            "ts_code": doc.ts_code,
            "title": doc.title,
            "report_type": doc.report_type,
            "period_end": doc.period_end,
            "parse_status": doc.parse_status,
            "chars": len(doc.text_excerpt) if doc.text_excerpt else 0,
            "text": doc.text_excerpt,
        }


report_text_extract_service = ReportTextExtractService()
