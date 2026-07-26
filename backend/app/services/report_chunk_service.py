"""
app/services/report_chunk_service.py — PDF 文本切块服务（Phase 6F）

功能：
  - 从 report_documents.text_excerpt 或 local_path 读取文本
  - 清理文本
  - 按 800-1200 字切分，100-200 字 overlap
  - SHA-256 去重（跨 report 去重）
  - 写入 report_chunks
  - 更新 report_documents.rag_status / chunk_count
"""
from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_chunk import ReportChunk
from app.models.report_document import ReportDocument

log = logging.getLogger(__name__)

_CHUNK_SIZE = 1000     # target chars per chunk
_CHUNK_OVERLAP = 150   # overlap chars between adjacent chunks
_MIN_CHUNK_SIZE = 100  # discard chunks shorter than this


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _detect_section_title(chunk_text: str) -> Optional[str]:
    """Extract the first Markdown-style heading in the chunk, if any."""
    for line in chunk_text.splitlines()[:5]:
        line = line.strip()
        if re.match(r'^#{1,3}\s+.{2,50}$', line):
            return re.sub(r'^#+\s+', '', line)
        if re.match(r'^[一二三四五六七八九十][、.．]\s*.{2,30}$', line):
            return line.split('、', 1)[-1].split('.', 1)[-1].strip() if '、' in line or '.' in line else line
    return None


def _split_text(text: str, chunk_size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks, trying to break at paragraph boundaries."""
    if not text:
        return []

    # Paragraph boundaries preferred
    paragraphs = re.split(r'\n{2,}', text)
    chunks = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(current) + len(para) + 2 <= chunk_size:
            current = (current + "\n\n" + para).strip()
        else:
            if current:
                chunks.append(current)
            # If para itself exceeds chunk_size, force-split it
            if len(para) > chunk_size:
                start = 0
                while start < len(para):
                    end = min(start + chunk_size, len(para))
                    chunks.append(para[start:end])
                    start = end - overlap
                    if start < 0:
                        start = 0
                current = ""
            else:
                # Start new chunk with overlap from previous
                if chunks:
                    overlap_text = chunks[-1][-overlap:] if len(chunks[-1]) > overlap else chunks[-1]
                    current = overlap_text + "\n\n" + para
                else:
                    current = para

    if current and len(current.strip()) >= _MIN_CHUNK_SIZE:
        chunks.append(current.strip())

    return [c for c in chunks if len(c) >= _MIN_CHUNK_SIZE]


class ReportChunkService:
    """Chunk a report's text and persist to report_chunks."""

    async def chunk_report(
        self,
        report_id: int,
        db: AsyncSession,
    ) -> dict:
        """
        Chunk a report's text and write to report_chunks.

        Returns:
            {"status": "chunked"|"skipped"|"failed", "report_id": int, "chunk_count": int, "reason": str}
        """
        stmt = select(ReportDocument).where(ReportDocument.id == report_id)
        result = await db.execute(stmt)
        doc: Optional[ReportDocument] = result.scalars().first()

        if not doc:
            return {"status": "failed", "report_id": report_id, "chunk_count": 0, "reason": "report_id not found"}

        # Get text: try full local file first, then text_excerpt
        text = await self._get_text(doc)

        if not text or len(text.strip()) < _MIN_CHUNK_SIZE:
            err = "no parseable text (parse PDF first)"
            doc.rag_status = "failed"
            doc.rag_error = err
            await db.commit()
            return {"status": "skipped", "report_id": report_id, "chunk_count": 0, "reason": err}

        # Extract ts_code/symbol from doc
        ts_code = doc.ts_code or ""
        symbol = ts_code.split(".")[0] if "." in ts_code else ts_code
        market = "CN"

        # Delete existing chunks for this report (re-chunk is idempotent)
        await db.execute(delete(ReportChunk).where(ReportChunk.report_id == report_id))
        await db.flush()

        # Split into chunks
        raw_chunks = _split_text(text)
        inserted = 0

        for idx, chunk_text in enumerate(raw_chunks):
            ch = chunk_text.strip()
            if len(ch) < _MIN_CHUNK_SIZE:
                continue

            c_hash = _content_hash(ch)

            # Dedup: skip if content_hash already exists (across reports)
            existing_stmt = select(ReportChunk).where(ReportChunk.content_hash == c_hash)
            existing_result = await db.execute(existing_stmt)
            if existing_result.scalars().first():
                continue

            section = _detect_section_title(ch)
            chunk = ReportChunk(
                report_id=report_id,
                ts_code=ts_code,
                symbol=symbol,
                market=market,
                report_type=doc.report_type,
                report_year=doc.report_year,
                period=doc.period_end,
                chunk_index=idx,
                section_title=section,
                content=ch,
                content_hash=c_hash,
                token_count=len(ch),  # approx: 1 CJK char ≈ 1 token
            )
            db.add(chunk)
            inserted += 1

        # Update report status
        doc.rag_status = "chunked"
        doc.chunk_count = inserted
        doc.rag_error = None

        try:
            await db.commit()
            log.info("Chunked report_id=%d → %d chunks", report_id, inserted)
            return {"status": "chunked", "report_id": report_id, "chunk_count": inserted, "reason": "ok"}
        except Exception as e:
            await db.rollback()
            err = str(e)[:500]
            doc.rag_status = "failed"
            doc.rag_error = err
            return {"status": "failed", "report_id": report_id, "chunk_count": 0, "reason": err}

    async def _get_text(self, doc: ReportDocument) -> str:
        """Try to get full text from local PDF, fallback to text_excerpt."""
        local = doc.local_path or ""
        if local and Path(local).exists() and doc.parsed:
            try:
                from app.services.report_text_extract_service import _extract_text_pdfminer, _clean_text
                raw = _extract_text_pdfminer(Path(local))
                # Don't truncate here — we want the full text for chunking
                return _clean_text(raw)
            except Exception as e:
                log.warning("Full text extraction failed for report_id=%d: %s", doc.id, e)

        # Fallback to stored excerpt
        return doc.text_excerpt or ""


report_chunk_service = ReportChunkService()
