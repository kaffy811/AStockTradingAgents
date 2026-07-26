"""Hybrid retriever for Company V2 single-report QA."""
from __future__ import annotations

import math
import re
from difflib import SequenceMatcher
from typing import Any

from app.services.company_v2_report_embedding_service import (
    cosine_similarity,
    embed_text,
    extract_retrieval_terms,
)
from app.services.company_v2_report_rag_index_service import (
    CompanyV2ReportRagRepository,
    company_v2_report_rag_repository,
)


DEFAULT_TOP_K = 6
MAX_TOP_K = 12


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


def _metric_page_boost(query: str, text: str, page_start: int) -> float:
    metric_terms = ["营业收入", "归属于上市公司股东的净利润", "经营活动产生的现金流量净额", "现金流量净额"]
    if not any(term in query for term in metric_terms):
        return 0.0
    boost = 0.0
    if "主要会计数据" in text or "主要财务指标" in text:
        boost += 0.18
    if page_start <= 30:
        boost += 0.10
    if page_start >= 180 and "附注" not in query:
        boost -= 0.06
    return boost


def _excerpt(text: str, query: str, limit: int = 420) -> str:
    terms = [term for term in extract_retrieval_terms(query) if len(term) >= 2]
    best = 0
    for term in terms:
        pos = text.find(term)
        if pos >= 0:
            best = max(0, pos - limit // 3)
            break
    excerpt = text[best : best + limit].strip()
    if best > 0:
        excerpt = "..." + excerpt
    if best + limit < len(text):
        excerpt += "..."
    return excerpt


def _is_near_duplicate(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return SequenceMatcher(None, left[:500], right[:500]).ratio() > 0.92


class CompanyV2ReportRagRetriever:
    def __init__(self, repository: CompanyV2ReportRagRepository | None = None) -> None:
        self.repository = repository or company_v2_report_rag_repository

    def retrieve(
        self,
        *,
        report_id: int,
        question: str,
        top_k: int = DEFAULT_TOP_K,
        section_filter: str | None = None,
        symbol: str | None = None,
        report_year: int | None = None,
    ) -> dict[str, Any]:
        doc = self.repository.get_document(report_id)
        if not doc or doc.status not in {"indexed", "partial"}:
            return {
                "report_id": report_id,
                "selected_report_id": report_id,
                "retrieved_report_ids": [],
                "cross_report_leakage_detected": False,
                "query": question,
                "chunks": [],
                "retrieval_mode": "unavailable",
                "error_code": "REPORT_NOT_INDEXED",
            }
        if symbol and doc.symbol != symbol:
            return {"report_id": report_id, "query": question, "chunks": [], "retrieval_mode": "blocked", "error_code": "REPORT_SYMBOL_MISMATCH"}
        if report_year and int(doc.report_year) != int(report_year):
            return {"report_id": report_id, "query": question, "chunks": [], "retrieval_mode": "blocked", "error_code": "REPORT_YEAR_MISMATCH"}

        capped_top_k = max(1, min(int(top_k or DEFAULT_TOP_K), MAX_TOP_K))
        query_vec = embed_text(question)
        scored: list[tuple[float, dict[str, Any], str]] = []

        for chunk in doc.chunks:
            if section_filter and section_filter not in (chunk.section_title or ""):
                continue
            vector_score = cosine_similarity(query_vec, chunk.embedding)
            keyword = _keyword_score(question, chunk.text)
            final = 0.7 * vector_score + 0.3 * keyword + _metric_page_boost(question, chunk.text, chunk.page_start)
            if keyword > 0.55:
                final = max(final, 0.55 + 0.2 * vector_score)
            if final <= 0:
                continue
            item = {
                "chunk_id": chunk.id,
                "score": round(final, 4),
                "score_detail": {
                    "embedding_score": round(vector_score, 4),
                    "keyword_score": round(keyword, 4),
                },
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "section_title": chunk.section_title,
                "text_excerpt": _excerpt(chunk.text, question),
                "source_url": doc.source_url,
                "report_id": doc.report_id,
                "symbol": doc.symbol,
                "report_year": doc.report_year,
                "report_type": doc.report_type,
            }
            scored.append((final, item, chunk.text))

        scored.sort(key=lambda item: item[0], reverse=True)
        results: list[dict[str, Any]] = []
        used_pages: set[tuple[int, int]] = set()
        used_texts: list[str] = []
        for _, item, full_text in scored:
            page_key = (item["page_start"], item["page_end"])
            if page_key in used_pages and len(results) >= max(2, capped_top_k // 2):
                continue
            if any(_is_near_duplicate(full_text, existing) for existing in used_texts):
                continue
            results.append(item)
            used_pages.add(page_key)
            used_texts.append(full_text)
            if len(results) >= capped_top_k:
                break

        return {
            "report_id": doc.report_id,
            "selected_report_id": doc.report_id,
            "retrieved_report_ids": sorted({item["report_id"] for item in results}),
            "cross_report_leakage_detected": any(item["report_id"] != doc.report_id for item in results),
            "query": question,
            "chunks": results,
            "retrieval_mode": "hybrid" if any(chunk.embedding for chunk in doc.chunks) else "keyword",
            "top_k": capped_top_k,
            "filters": {"report_id": doc.report_id, "symbol": doc.symbol, "report_year": doc.report_year},
        }


company_v2_report_rag_retriever = CompanyV2ReportRagRetriever()
