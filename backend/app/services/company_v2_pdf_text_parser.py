"""CompanyV2 PDF text parser.

Extracts page-level text for internal verification. API callers should receive
only summaries/excerpts, not full PDF text.
"""
from __future__ import annotations

from pathlib import Path
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_document import ReportDocument

LOW_COVERAGE_CODE = "TEXT_EXTRACTION_LOW_COVERAGE"


def parse_pdf_text(path: str | Path, *, report_id: str | int = "") -> dict[str, Any]:
    pdf_path = Path(path)
    warnings: list[str] = []
    pages: list[dict[str, Any]] = []
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path))
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            pages.append({"page": index, "text": text})
    except Exception:
        try:
            from pdfminer.high_level import extract_text
            text = extract_text(str(pdf_path)) or ""
            pages = [{"page": 1, "text": text}]
        except Exception as exc:
            return {
                "report_id": str(report_id),
                "page_count": 0,
                "text_pages": [],
                "parse_status": "failed",
                "warnings": [str(exc)[:200]],
            }

    chars = sum(len(page.get("text") or "") for page in pages)
    page_count = len(pages)
    status = "parsed"
    if page_count and chars / max(page_count, 1) < 80:
        status = "partial"
        warnings.append(LOW_COVERAGE_CODE)
    return {
        "report_id": str(report_id),
        "page_count": page_count,
        "text_pages": pages,
        "parse_status": status,
        "warnings": warnings,
    }


def safe_parse_summary(parsed: dict[str, Any], *, excerpt_chars: int = 500) -> dict[str, Any]:
    excerpts = []
    for page in parsed.get("text_pages") or []:
        text = (page.get("text") or "").strip()
        if text:
            excerpts.append({"page": page.get("page"), "excerpt": text[:excerpt_chars]})
        if len(excerpts) >= 3:
            break
    return {
        "report_id": parsed.get("report_id"),
        "page_count": parsed.get("page_count", 0),
        "parse_status": parsed.get("parse_status"),
        "warnings": parsed.get("warnings") or [],
        "chars": sum(len(page.get("text") or "") for page in parsed.get("text_pages") or []),
        "excerpts": excerpts,
    }


class CompanyV2PdfTextParser:
    async def parse_report(self, report_id: int, db: AsyncSession) -> dict[str, Any]:
        result = await db.execute(select(ReportDocument).where(ReportDocument.id == report_id))
        doc: ReportDocument | None = result.scalars().first()
        if not doc:
            return {"ok": False, "status": "parse_failed", "report_id": report_id, "error_code": "REPORT_NOT_FOUND"}
        if not doc.local_path or not Path(doc.local_path).exists():
            doc.parse_status = "parse_failed"
            doc.parse_error = "PDF file not downloaded"
            await db.commit()
            return {"ok": False, "status": "parse_failed", "report_id": report_id, "error_code": "PDF_NOT_DOWNLOADED"}

        parsed = parse_pdf_text(doc.local_path, report_id=report_id)
        summary = safe_parse_summary(parsed)
        doc.parse_status = "parsed" if parsed["parse_status"] == "parsed" else parsed["parse_status"]
        doc.parsed = parsed["parse_status"] in {"parsed", "partial"}
        joined_text = "\n".join(page.get("text") or "" for page in parsed.get("text_pages") or [])
        try:
            Path(doc.local_path).with_suffix(".pages.json").write_text(
                json.dumps(
                    {
                        "report_id": str(report_id),
                        "page_count": parsed.get("page_count", 0),
                        "text_pages": parsed.get("text_pages") or [],
                        "parse_status": parsed.get("parse_status"),
                        "warnings": parsed.get("warnings") or [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception:
            pass
        doc.text_excerpt = joined_text[:8000]
        doc.parse_error = None if doc.parsed else ";".join(parsed.get("warnings") or [])
        await db.commit()
        return {"ok": doc.parsed, "status": doc.parse_status, **summary}


company_v2_pdf_text_parser = CompanyV2PdfTextParser()
