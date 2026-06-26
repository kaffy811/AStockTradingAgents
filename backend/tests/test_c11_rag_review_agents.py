"""
test_c11_rag_review_agents.py — Phase C11 RAG Review Agents unit tests.

Tests: SourceReviewAgent, FreshnessReviewAgent, ConsistencyReviewAgent,
       RAGReviewCoordinator (aggregate + format_for_answer).
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from app.agents.chat_rag.base import RAGDocument, RAGResult
from app.agents.chat_rag.review_agents import (
    SourceReviewAgent,
    FreshnessReviewAgent,
    ConsistencyReviewAgent,
    RAGReviewCoordinator,
)


# ── helpers ────────────────────────────────────────────────────────────────────

def _doc(doc_id="d1", source_type="news", title="T", summary="S",
         source="新华社", published_at=None, symbol=None,
         external_content=False, internal_content=True) -> RAGDocument:
    return RAGDocument(
        doc_id=doc_id,
        source_type=source_type,
        title=title,
        summary=summary,
        source=source,
        published_at=published_at,
        symbol=symbol,
        external_content=external_content,
        internal_content=internal_content,
    )


def _result(docs=None) -> RAGResult:
    return RAGResult(ok=True, query="test", documents=docs or [])


_NOW = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)


# ── SourceReviewAgent ─────────────────────────────────────────────────────────

class TestSourceReviewAgent:
    def test_all_sources_present(self):
        docs = [_doc("d1", source="Reuters"), _doc("d2", source="Bloomberg")]
        r = SourceReviewAgent().review(_result(docs))
        assert r["source_score"] == 1.0
        assert r["missing_sources"] == []

    def test_missing_source_penalised(self):
        docs = [_doc("d1", source=None, external_content=True)]
        r = SourceReviewAgent().review(_result(docs))
        assert r["source_score"] < 1.0
        assert "d1" in r["missing_sources"]

    def test_empty_docs_low_score(self):
        r = SourceReviewAgent().review(_result([]))
        assert r["source_score"] == 0.3

    def test_unknown_source_penalised(self):
        docs = [_doc("d1", source="unknown", external_content=True)]
        r = SourceReviewAgent().review(_result(docs))
        assert r["source_score"] < 1.0


# ── FreshnessReviewAgent ─────────────────────────────────────────────────────

class TestFreshnessReviewAgent:
    def test_fresh_news_no_penalty(self):
        ts = (_NOW - timedelta(days=2)).isoformat()
        docs = [_doc("d1", source_type="news", published_at=ts)]
        r = FreshnessReviewAgent().review(_result(docs), now=_NOW)
        assert r["freshness_score"] == 1.0
        assert r["stale_documents"] == []

    def test_stale_news_penalised(self):
        ts = (_NOW - timedelta(days=10)).isoformat()
        docs = [_doc("d1", source_type="news", published_at=ts)]
        r = FreshnessReviewAgent().review(_result(docs), now=_NOW)
        assert "d1" in r["stale_documents"]
        assert r["freshness_score"] < 1.0

    def test_fresh_report_no_penalty(self):
        ts = (_NOW - timedelta(days=10)).isoformat()
        docs = [_doc("d1", source_type="report", published_at=ts)]
        r = FreshnessReviewAgent().review(_result(docs), now=_NOW)
        assert r["freshness_score"] == 1.0

    def test_stale_report_penalised(self):
        ts = (_NOW - timedelta(days=35)).isoformat()
        docs = [_doc("d1", source_type="report", published_at=ts)]
        r = FreshnessReviewAgent().review(_result(docs), now=_NOW)
        assert "d1" in r["stale_documents"]

    def test_missing_timestamp_penalised(self):
        docs = [_doc("d1", published_at=None)]
        r = FreshnessReviewAgent().review(_result(docs), now=_NOW)
        assert r["freshness_score"] < 1.0

    def test_empty_docs(self):
        r = FreshnessReviewAgent().review(_result([]), now=_NOW)
        assert r["freshness_score"] == 0.3


# ── ConsistencyReviewAgent ────────────────────────────────────────────────────

class TestConsistencyReviewAgent:
    def test_no_conflicts(self):
        docs = [_doc("d1", symbol="688146"), _doc("d2", symbol="688146")]
        r = ConsistencyReviewAgent().review(_result(docs))
        assert r["consistency_score"] == 1.0
        assert r["conflicts"] == []

    def test_forbidden_certainty_language(self):
        docs = [_doc("d1", summary="该股必涨，稳赚不赔")]
        r = ConsistencyReviewAgent().review(_result(docs))
        assert r["consistency_score"] < 1.0
        assert any("d1" in c for c in r["conflicts"])

    def test_empty_docs(self):
        r = ConsistencyReviewAgent().review(_result([]))
        assert r["consistency_score"] == 0.3


# ── RAGReviewCoordinator ──────────────────────────────────────────────────────

class TestRAGReviewCoordinator:
    def test_aggregate_high_confidence(self):
        ts = (_NOW - timedelta(days=1)).isoformat()
        docs = [_doc("d1", source="新华社", source_type="news", published_at=ts, external_content=True)]
        result = _result(docs)
        coord = RAGReviewCoordinator()
        rr = coord.review(result)
        assert rr["overall_confidence"] in ("high", "medium")
        assert result.reviewed is True
        assert result.review_result is not None

    def test_aggregate_approved_with_docs(self):
        ts = (_NOW - timedelta(days=1)).isoformat()
        docs = [_doc("d1", source="Bloomberg", source_type="news", published_at=ts, external_content=True)]
        result = _result(docs)
        rr = RAGReviewCoordinator().review(result)
        assert rr["approved_for_answer"] is True

    def test_aggregate_not_approved_empty(self):
        result = _result([])
        rr = RAGReviewCoordinator().review(result)
        assert rr["approved_for_answer"] is False

    def test_format_for_answer_empty_when_no_docs(self):
        result = _result([])
        coord = RAGReviewCoordinator()
        coord.review(result)
        text = coord.format_for_answer(result)
        assert text == ""

    def test_format_for_answer_contains_confidence(self):
        ts = (_NOW - timedelta(days=1)).isoformat()
        docs = [_doc("d1", source="S", source_type="news", published_at=ts, external_content=True)]
        result = _result(docs)
        coord = RAGReviewCoordinator()
        coord.review(result)
        text = coord.format_for_answer(result)
        assert "资料来源与可信度" in text
        assert "新闻" in text or "报告" in text or "行业" in text or "内部数据" in text

    def test_warnings_capped_at_10(self):
        # 15 docs with missing timestamps → 15 potential warnings
        docs = [_doc(f"d{i}", published_at=None) for i in range(15)]
        result = _result(docs)
        rr = RAGReviewCoordinator().review(result)
        assert len(rr["warnings"]) <= 10
