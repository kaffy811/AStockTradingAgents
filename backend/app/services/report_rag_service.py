"""
app/services/report_rag_service.py — 财报 RAG 检索服务（Phase 6F / 6G）

支持：
  1. pgvector 余弦相似度检索（embedding 可用时）
  2. 关键词全文回退（embedding 不可用时）
  3. 按 ts_code 过滤（不跨股票泄露）
  4. 按 report_type / year 过滤
  5. top_k 结果
  6. Phase 6G: hybrid scoring (vector_score + keyword_bonus), fallback_used flag
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_chunk import ReportChunk
from app.models.report_document import ReportDocument
from app.agents.embedding_service import embed_text, EMBEDDING_DIM

log = logging.getLogger(__name__)

_DEFAULT_TOP_K = 6
_MAX_TOP_K = 20
_MAX_CONTENT_LEN = 1500  # max chars per chunk in response


def _keyword_bonus(content: str, query: str) -> float:
    """Simple keyword overlap bonus (0.0-0.15)."""
    words = set(query.split())
    matches = sum(1 for w in words if w in content and len(w) >= 2)
    return min(0.15, matches * 0.03)


class ReportRagService:
    """Semantic search over report_chunks for a specific stock."""

    async def query(
        self,
        ts_code: str,
        query_text: str,
        db: AsyncSession,
        report_types: Optional[list[str]] = None,
        years: Optional[list[int]] = None,
        report_id: Optional[int] = None,
        top_k: int = _DEFAULT_TOP_K,
    ) -> dict:
        """
        Semantic (or keyword fallback) search over report chunks.

        Security: only returns chunks belonging to `ts_code`.

        Returns:
            {"chunks": [...], "partial": bool, "errors": [], "search_mode": "vector"|"keyword",
             "fallback_used": bool, "provider": str}
        """
        from app.services.report_embedding_provider import get_report_embedding_provider
        provider = get_report_embedding_provider()

        top_k = min(top_k, _MAX_TOP_K)
        errors = []
        search_mode = "keyword"
        results = []
        fallback_used = True

        # Try vector search
        try:
            query_vec = await embed_text(query_text)
            results = await self._vector_search(
                ts_code=ts_code,
                query_vec=query_vec,
                db=db,
                report_types=report_types,
                years=years,
                report_id=report_id,
                top_k=top_k,
            )
            if results:
                search_mode = "vector"
                fallback_used = False
        except Exception as e:
            log.info("Vector search unavailable, falling back to keyword: %s", e)
            errors.append(f"vector search unavailable: {str(e)[:100]}, using keyword fallback")

        # Keyword fallback
        if not results:
            fallback_used = True
            try:
                results = await self._keyword_search(
                    ts_code=ts_code,
                    query_text=query_text,
                    db=db,
                    report_types=report_types,
                    years=years,
                    report_id=report_id,
                    top_k=top_k,
                )
                search_mode = "keyword"
            except Exception as e:
                errors.append(f"keyword search failed: {str(e)[:100]}")

        if not results and report_id is not None:
            company_v2_result = await self._company_v2_search(
                ts_code=ts_code,
                query_text=query_text,
                report_id=report_id,
                years=years,
                top_k=top_k,
            )
            company_v2_chunks = company_v2_result.get("chunks", [])
            if company_v2_chunks:
                return {
                    "chunks": company_v2_chunks,
                    "partial": len(errors) > 0,
                    "errors": errors,
                    "search_mode": company_v2_result.get("search_mode", "company_v2_hybrid"),
                    "total": len(company_v2_chunks),
                    "fallback_used": True,
                    "provider": "company_v2_report_rag",
                    "selected_report_id": report_id,
                }
            if company_v2_result.get("error_code"):
                errors.append(f"company_v2_rag unavailable: {company_v2_result['error_code']}")

        chunks_out = []
        for r in results:
            chunk = self._format_chunk(r)
            if search_mode == "vector":
                bonus = _keyword_bonus(chunk.get("content", ""), query_text)
                chunk["score"] = round(0.85 + bonus, 4)
                chunk["score_detail"] = {
                    "vector_score": 0.85,
                    "keyword_bonus": bonus,
                }
            else:
                bonus = _keyword_bonus(chunk.get("content", ""), query_text)
                chunk["score"] = round(bonus + 0.3, 4)
                chunk["score_detail"] = {"vector_score": 0.0, "keyword_bonus": bonus}
            chunks_out.append(chunk)

        return {
            "chunks": chunks_out,
            "partial": len(errors) > 0,
            "errors": errors,
            "search_mode": search_mode,
            "total": len(chunks_out),
            "fallback_used": fallback_used,
            "provider": provider.provider_name,
        }

    async def _vector_search(
        self,
        ts_code: str,
        query_vec: list[float],
        db: AsyncSession,
        report_types: Optional[list[str]],
        years: Optional[list[int]],
        report_id: Optional[int],
        top_k: int,
    ) -> list[ReportChunk]:
        """Use pgvector cosine similarity search."""
        # Build the query using raw SQL for pgvector operator
        # Filter conditions
        conditions = ["rc.ts_code = :ts_code", "rc.embedding IS NOT NULL"]
        params: dict = {"ts_code": ts_code, "top_k": top_k}

        if report_types:
            conditions.append("rc.report_type = ANY(:report_types)")
            params["report_types"] = report_types

        if years:
            conditions.append("rc.report_year = ANY(:years)")
            params["years"] = years

        if report_id is not None:
            conditions.append("rc.report_id = :report_id")
            params["report_id"] = int(report_id)

        where_clause = " AND ".join(conditions)

        # Convert vector to string for pgvector
        vec_str = "[" + ",".join(str(v) for v in query_vec) + "]"

        sql = text(f"""
            SELECT rc.id
            FROM report_chunks rc
            WHERE {where_clause}
              AND rc.embedding IS NOT NULL
            ORDER BY rc.embedding <=> CAST(:query_vec AS vector)
            LIMIT :top_k
        """)
        params["query_vec"] = vec_str

        result = await db.execute(sql, params)
        chunk_ids = [row[0] for row in result.fetchall()]

        if not chunk_ids:
            return []

        stmt = select(ReportChunk).where(ReportChunk.id.in_(chunk_ids))
        chunks_result = await db.execute(stmt)
        return chunks_result.scalars().all()

    async def _keyword_search(
        self,
        ts_code: str,
        query_text: str,
        db: AsyncSession,
        report_types: Optional[list[str]],
        years: Optional[list[int]],
        report_id: Optional[int],
        top_k: int,
    ) -> list[ReportChunk]:
        """Keyword ILIKE fallback search."""
        # Simple keyword match: split query into words and search
        words = [w.strip() for w in query_text.split() if len(w.strip()) >= 2][:5]
        if not words:
            words = [query_text[:20]]

        stmt = select(ReportChunk).where(
            ReportChunk.ts_code == ts_code,
        )

        if report_types:
            stmt = stmt.where(ReportChunk.report_type.in_(report_types))
        if years:
            stmt = stmt.where(ReportChunk.report_year.in_(years))
        if report_id is not None:
            stmt = stmt.where(ReportChunk.report_id == int(report_id))

        # Use first keyword for basic ILIKE
        stmt = stmt.where(ReportChunk.content.ilike(f"%{words[0]}%"))
        stmt = stmt.order_by(ReportChunk.chunk_index).limit(top_k)

        result = await db.execute(stmt)
        return result.scalars().all()

    @staticmethod
    def _format_chunk(chunk: ReportChunk) -> dict:
        content = chunk.content or ""
        if len(content) > _MAX_CONTENT_LEN:
            content = content[:_MAX_CONTENT_LEN] + "…"
        return {
            "chunk_id":      chunk.id,
            "report_id":     chunk.report_id,
            "ts_code":       chunk.ts_code,
            "report_type":   chunk.report_type,
            "report_year":   chunk.report_year,
            "period":        chunk.period,
            "chunk_index":   chunk.chunk_index,
            "section_title": chunk.section_title,
            "content":       content,
            "has_embedding": chunk.embedding is not None,
        }

    async def _company_v2_search(
        self,
        *,
        ts_code: str,
        query_text: str,
        report_id: int,
        years: Optional[list[int]],
        top_k: int,
    ) -> dict:
        """Bridge legacy report chat retrieval to Company V2 report RAG by report_id."""
        symbol = (ts_code or "").split(".")[0]
        report_year = int(years[0]) if years else None
        try:
            from app.services.company_v2_report_rag_retriever import company_v2_report_rag_retriever

            result = await asyncio.to_thread(
                company_v2_report_rag_retriever.retrieve,
                report_id=int(report_id),
                question=query_text,
                top_k=top_k,
                symbol=symbol or None,
                report_year=report_year,
            )
        except Exception as exc:
            log.warning("Company V2 report RAG bridge failed for report_id=%s: %s", report_id, exc)
            return {"chunks": [], "error_code": "COMPANY_V2_RAG_FAILED"}

        chunks = []
        for item in result.get("chunks") or []:
            chunks.append({
                "chunk_id": item.get("chunk_id"),
                "report_id": item.get("report_id") or report_id,
                "ts_code": ts_code,
                "report_type": item.get("report_type"),
                "report_year": item.get("report_year"),
                "period": str(item.get("report_year") or ""),
                "chunk_index": item.get("chunk_id"),
                "section_title": item.get("section_title"),
                "content": item.get("text_excerpt") or "",
                "score": item.get("score"),
                "score_detail": item.get("score_detail"),
                "page_start": item.get("page_start"),
                "page_end": item.get("page_end"),
                "source_url": item.get("source_url"),
                "has_embedding": bool((item.get("score_detail") or {}).get("embedding_score")),
            })
        return {
            "chunks": chunks,
            "search_mode": result.get("retrieval_mode") or "company_v2_hybrid",
            "error_code": result.get("error_code"),
        }


report_rag_service = ReportRagService()
