"""
app/services/report_embedding_service.py — Chunk 向量化服务（Phase 6F / 6G）

Phase 6G: Uses the new ReportEmbeddingProvider abstraction (mock/local/disabled)
instead of the financial_rag embedding_service directly.

0-成本模式：report_embedding_provider=mock（默认）时，使用确定性 hash-based 向量，
无外部 API 调用，无费用，可完整走通 RAG 检索流程。
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_chunk import ReportChunk
from app.models.report_document import ReportDocument
from app.services.report_embedding_provider import get_report_embedding_provider
from app.core.config import get_settings  # noqa: E402 — module-level for patchability

log = logging.getLogger(__name__)

_BATCH_SIZE = 16  # chunks per embed call (conservative for local/free mode)


class ReportEmbeddingService:
    """Generate and store embeddings for report chunks."""

    async def embed_report(
        self,
        report_id: int,
        db: AsyncSession,
    ) -> dict:
        """
        Generate embeddings for all chunks of a report.

        Returns:
            {"status": "embedded"|"partial"|"skipped"|"failed", "report_id": int,
             "embedded": int, "failed": int, "provider": str, "reason": str}
        """
        # Verify report exists and has been chunked
        doc_stmt = select(ReportDocument).where(ReportDocument.id == report_id)
        doc_result = await db.execute(doc_stmt)
        doc: Optional[ReportDocument] = doc_result.scalars().first()

        if not doc:
            return {"status": "failed", "report_id": report_id, "embedded": 0, "failed": 0, "provider": "unknown", "reason": "report_id not found"}

        if doc.rag_status not in ("chunked", "embedded", "partial"):
            return {
                "status": "skipped", "report_id": report_id, "embedded": 0, "failed": 0,
                "provider": "unknown",
                "reason": f"rag_status={doc.rag_status!r}, chunk the report first",
            }

        # Get embedding provider
        provider = get_report_embedding_provider()

        if not provider.is_available():
            return {
                "status": "skipped",
                "report_id": report_id,
                "embedded": 0,
                "failed": 0,
                "provider": provider.provider_name,
                "reason": provider.unavailability_reason() or "provider unavailable",
            }

        # Load chunks without embeddings
        chunk_stmt = select(ReportChunk).where(
            ReportChunk.report_id == report_id,
            ReportChunk.embedding.is_(None),
        ).order_by(ReportChunk.chunk_index)
        chunk_result = await db.execute(chunk_stmt)
        chunks = chunk_result.scalars().all()

        if not chunks:
            doc.rag_status = "embedded"
            await db.commit()
            return {"status": "embedded", "report_id": report_id, "embedded": 0, "failed": 0, "provider": provider.provider_name, "reason": "all chunks already embedded"}

        settings = get_settings()
        model_name = settings.report_embedding_model or f"report-rag-{provider.provider_name}"

        embedded_count = 0
        failed_count = 0

        # Process in batches
        for batch_start in range(0, len(chunks), _BATCH_SIZE):
            batch = chunks[batch_start : batch_start + _BATCH_SIZE]
            texts = [c.content for c in batch]

            try:
                vectors = await provider.embed_texts(texts)
                for chunk, vector in zip(batch, vectors):
                    chunk.embedding = vector
                    chunk.embedding_model = model_name
                    chunk.embed_error = None
                embedded_count += len(batch)
            except Exception as e:
                err = str(e)[:300]
                log.warning("Embedding batch failed for report_id=%d batch=%d: %s", report_id, batch_start, err)
                for chunk in batch:
                    chunk.embed_error = err
                failed_count += len(batch)

        # Update rag_status
        if failed_count == 0:
            doc.rag_status = "embedded"
        elif embedded_count > 0:
            doc.rag_status = "partial"
        else:
            doc.rag_status = "failed"
            doc.rag_error = "all embedding calls failed"

        try:
            await db.commit()
            log.info("Embedded report_id=%d: %d ok, %d failed", report_id, embedded_count, failed_count)
            return {
                "status": doc.rag_status,
                "report_id": report_id,
                "embedded": embedded_count,
                "failed": failed_count,
                "provider": provider.provider_name,
                "reason": "ok" if failed_count == 0 else f"{failed_count} batches failed",
            }
        except Exception as e:
            await db.rollback()
            return {"status": "failed", "report_id": report_id, "embedded": 0, "failed": len(chunks), "provider": provider.provider_name, "reason": str(e)[:300]}


report_embedding_service = ReportEmbeddingService()
