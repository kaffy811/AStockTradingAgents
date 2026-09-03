"""Async Company V2 report evidence service for request-path tools."""
from __future__ import annotations

import math
from typing import Any

from app.services.company_v2_report_embedding_service import (
    cosine_similarity,
    embed_text,
    extract_retrieval_terms,
)
from app.services.company_v2_report_rag_index_service import company_v2_report_rag_repository


def _keyword_score(query: str, text: str) -> float:
    q_terms = set(extract_retrieval_terms(query))
    if not q_terms:
        return 0.0
    matches = 0.0
    text_terms = set(extract_retrieval_terms(text[:4000]))
    for term in q_terms:
        if term in text:
            matches += 1.4 if len(term) >= 4 else 1.0
        elif term in text_terms:
            matches += 0.8
    return min(1.0, matches / max(3.0, math.sqrt(len(q_terms))))


class CompanyV2ReportEvidenceService:
    """Async report evidence lookup with no sync bridge in request path."""

    async def query_report_evidence(self, *, report_id: int, question: str, top_k: int = 6) -> dict[str, Any]:
        repository = company_v2_report_rag_repository
        if hasattr(repository, "get_document_async"):
            doc = await repository.get_document_async(report_id)
        else:
            doc = repository.get_document(report_id)
        if not doc or doc.status not in {"indexed", "partial"}:
            return {
                "report_id": report_id,
                "chunks": [],
                "status": "unavailable",
                "error_code": "REPORT_NOT_INDEXED",
            }

        capped = max(1, min(int(top_k or 6), 8))
        query_vec = embed_text(question)
        scored: list[tuple[float, dict[str, Any]]] = []
        for chunk in doc.chunks:
            text = chunk.text or ""
            keyword = _keyword_score(question, text)
            vector = cosine_similarity(query_vec, chunk.embedding)
            score = 0.65 * vector + 0.35 * keyword
            if score <= 0 and keyword <= 0:
                continue
            scored.append((score, {
                "evidence_id": f"report:{doc.report_id}:chunk:{chunk.id}",
                "report_id": doc.report_id,
                "report_year": doc.report_year,
                "report_type": doc.report_type,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "section_title": chunk.section_title,
                "text_excerpt": text[:420],
                "score": round(score, 4),
                "source_url": doc.source_url,
                "rag_document_id": doc.id,
                "chunk_id": chunk.id,
            }))
        scored.sort(key=lambda item: item[0], reverse=True)
        return {
            "report_id": doc.report_id,
            "report_year": doc.report_year,
            "report_type": doc.report_type,
            "source_url": doc.source_url,
            "status": "completed",
            "chunks": [item for _, item in scored[:capped]],
        }


company_v2_report_evidence_service = CompanyV2ReportEvidenceService()
