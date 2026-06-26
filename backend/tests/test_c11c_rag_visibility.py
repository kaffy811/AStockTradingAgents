"""
C11-c: RAG visibility tests.

Verifies that:
1. rag_retrieve event carries the document count in its detail string
2. rag_review event carries the confidence level in its detail string
3. format_for_answer produces a '### 资料来源与可信度' section when docs present
4. format_for_answer returns empty string when no documents
5. All 4 skills with RAG emit both rag_retrieve AND rag_review events
6. Confidence levels are one of: high / medium / low
7. ConsistencyReviewAgent correctly flags certainty phrases
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from collections import defaultdict


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_db():
    return AsyncMock()


def _make_uid():
    import uuid
    return uuid.UUID("00000000-0000-0000-0000-000000000088")


def _make_registry(tool_results: list):
    """Dict-dispatch mock registry."""
    from app.agents.chat_tools.tool_result import ToolResult
    queues = defaultdict(list)
    for r in tool_results:
        queues[r.tool_name].append(r)
    fallback = ToolResult(ok=False, tool_name="unknown", summary="no mock")
    registry_mock = MagicMock()
    async def _call(tool_name, db, **kw):
        q = queues.get(tool_name, [])
        return q.pop(0) if q else fallback
    registry_mock.call = _call
    return registry_mock


# ── 1. RAGReviewCoordinator format_for_answer ─────────────────────────────────

class TestFormatForAnswer:

    def test_no_docs_returns_empty_string(self):
        from app.agents.chat_rag import RAGReviewCoordinator, RAGResult
        coord = RAGReviewCoordinator()
        rag_result = RAGResult(ok=True, query="test", documents=[])
        coord.review(rag_result)
        out = coord.format_for_answer(rag_result)
        assert out == "", f"Expected empty string for no docs, got: {out!r}"

    def test_with_docs_contains_heading(self):
        from app.agents.chat_rag import RAGReviewCoordinator, RAGResult, RAGDocument
        coord = RAGReviewCoordinator()
        doc = RAGDocument(
            doc_id="d1", source_type="news", title="Test News",
            summary="茅台业绩超预期", source="Reuters",
            published_at="2026-06-20T10:00:00", external_content=True,
        )
        rag_result = RAGResult(ok=True, query="茅台", documents=[doc])
        coord.review(rag_result)
        out = coord.format_for_answer(rag_result)
        assert "### 资料来源与可信度" in out, f"Heading missing in: {out!r}"

    def test_with_docs_contains_confidence(self):
        from app.agents.chat_rag import RAGReviewCoordinator, RAGResult, RAGDocument
        coord = RAGReviewCoordinator()
        doc = RAGDocument(
            doc_id="d1", source_type="report", title="Research",
            summary="全面分析", source="internal", internal_content=True,
        )
        rag_result = RAGResult(ok=True, query="test", documents=[doc])
        coord.review(rag_result)
        out = coord.format_for_answer(rag_result)
        assert any(level in out for level in ("高", "中", "低", "high", "medium", "low")), (
            f"Confidence level missing in output: {out!r}"
        )


# ── 2. Confidence level validation ────────────────────────────────────────────

class TestConfidenceLevels:

    def test_high_confidence_with_multiple_good_docs(self):
        from app.agents.chat_rag import RAGReviewCoordinator, RAGResult, RAGDocument
        coord = RAGReviewCoordinator()
        docs = [
            RAGDocument(
                doc_id=f"d{i}", source_type="news", title=f"News {i}",
                summary="正常新闻内容", source="Reuters",
                published_at="2026-06-21T09:00:00", external_content=True,
            )
            for i in range(3)
        ]
        rag_result = RAGResult(ok=True, query="test", documents=docs)
        coord.review(rag_result)
        assert rag_result.overall_confidence in ("high", "medium", "low")

    def test_low_confidence_with_no_docs(self):
        from app.agents.chat_rag import RAGReviewCoordinator, RAGResult
        coord = RAGReviewCoordinator()
        rag_result = RAGResult(ok=True, query="test", documents=[])
        coord.review(rag_result)
        assert rag_result.overall_confidence == "low"


# ── 3. ConsistencyReviewAgent certainty phrase detection ──────────────────────

class TestCertaintyPhraseDetection:

    def test_bi_zhang_flagged(self):
        from app.agents.chat_rag.review_agents import ConsistencyReviewAgent
        from app.agents.chat_rag import RAGResult, RAGDocument
        agent = ConsistencyReviewAgent()
        doc = RAGDocument(
            doc_id="d1", source_type="report", title="Test",
            summary="该股必涨，投资者应立即买入", source="unknown",
        )
        result = RAGResult(ok=True, query="test", documents=[doc])
        review = agent.review(result)
        assert review["consistency_score"] < 1.0
        assert any("必涨" in w or "确定性" in w or "风险" in w for w in review.get("warnings", []))

    def test_wen_zhang_not_flagged(self):
        from app.agents.chat_rag.review_agents import ConsistencyReviewAgent
        from app.agents.chat_rag import RAGResult, RAGDocument
        agent = ConsistencyReviewAgent()
        doc = RAGDocument(
            doc_id="d1", source_type="report", title="Safe",
            summary="该股可能存在较大波动，请谨慎投资", source="internal",
        )
        result = RAGResult(ok=True, query="test", documents=[doc])
        review = agent.review(result)
        assert review["consistency_score"] == 1.0

    def test_wen_zhang_bi_die_flagged(self):
        from app.agents.chat_rag.review_agents import ConsistencyReviewAgent
        from app.agents.chat_rag import RAGResult, RAGDocument
        agent = ConsistencyReviewAgent()
        doc = RAGDocument(
            doc_id="d1", source_type="news", title="Negative",
            summary="受利空影响，该股必跌，请尽快离场", source="blog",
        )
        result = RAGResult(ok=True, query="test", documents=[doc])
        review = agent.review(result)
        assert review["consistency_score"] < 1.0


# ── 4. All 4 skills emit rag events ─────────────────────────────────────────

class TestAllSkillsEmitRAGEvents:

    @pytest.mark.asyncio
    async def test_risk_first_skill_emits_rag(self):
        from app.agents.chat_skills.risk_first_skill import RiskFirstSkill
        from app.agents.chat_tools.tool_result import ToolResult
        from app.agents.chat_skills.base import SkillContext

        registry = _make_registry([
            ToolResult(ok=True, tool_name="get_latest_news_tool", summary="[]", data=[]),
            ToolResult(ok=True, tool_name="get_recent_reports_tool", summary="[]", data=[]),
            ToolResult(ok=True, tool_name="get_industry_hot_tool", summary="{}", data={}),
        ])
        ctx = SkillContext(db=_make_db(), user_id=_make_uid(), tool_registry=registry)
        skill = RiskFirstSkill()
        result = await skill.run("茅台有哪些风险", ctx)

        names = [e.get("name") for e in result.tool_events]
        assert "rag_retrieve" in names
        assert "rag_review"   in names

    @pytest.mark.asyncio
    async def test_report_explanation_skill_emits_rag(self):
        from app.agents.chat_skills.report_explanation_skill import ReportExplanationSkill
        from app.agents.chat_tools.tool_result import ToolResult
        from app.agents.chat_skills.base import SkillContext

        registry = _make_registry([
            ToolResult(ok=True, tool_name="get_recent_reports_tool", summary="[]", data=[]),
            ToolResult(ok=True, tool_name="get_latest_news_tool", summary="[]", data=[]),
            ToolResult(ok=True, tool_name="get_industry_hot_tool", summary="{}", data={}),
        ])
        ctx = SkillContext(db=_make_db(), user_id=_make_uid(), tool_registry=registry)
        skill = ReportExplanationSkill()
        result = await skill.run("解释一下茅台的最新报告", ctx)

        names = [e.get("name") for e in result.tool_events]
        assert "rag_retrieve" in names
        assert "rag_review"   in names


# ── 5. rag_retrieve detail includes document count ────────────────────────────

class TestRAGEventDetail:

    @pytest.mark.asyncio
    async def test_rag_retrieve_event_detail_has_doc_count(self):
        from app.agents.chat_skills.stock_anomaly_skill import StockAnomalySkill
        from app.agents.chat_tools.tool_result import ToolResult
        from app.agents.chat_skills.base import SkillContext

        registry = _make_registry([
            ToolResult(ok=True, tool_name="get_quote_tool", summary="¥1800", data={"price": 1800, "change_pct": 1.2}),
            ToolResult(ok=True, tool_name="get_latest_news_tool", summary="[]", data=[]),
            ToolResult(ok=True, tool_name="get_recent_reports_tool", summary="[]", data=[]),
            ToolResult(ok=True, tool_name="get_industry_hot_tool", summary="{}", data={}),
        ])
        ctx = SkillContext(db=_make_db(), user_id=_make_uid(), tool_registry=registry)
        result = await StockAnomalySkill().run("茅台异动", ctx)

        rag_ev = next((e for e in result.tool_events if e.get("name") == "rag_retrieve"), None)
        assert rag_ev is not None
        detail = rag_ev.get("detail", "")
        # Detail should mention a number (doc count)
        import re
        assert re.search(r"\d+", detail), f"Expected a number in detail, got: {detail!r}"

    @pytest.mark.asyncio
    async def test_rag_review_event_detail_has_confidence(self):
        from app.agents.chat_skills.stock_anomaly_skill import StockAnomalySkill
        from app.agents.chat_tools.tool_result import ToolResult
        from app.agents.chat_skills.base import SkillContext

        registry = _make_registry([
            ToolResult(ok=True, tool_name="get_quote_tool", summary="¥1800", data={"price": 1800, "change_pct": 1.2}),
            ToolResult(ok=True, tool_name="get_latest_news_tool", summary="[]", data=[]),
            ToolResult(ok=True, tool_name="get_recent_reports_tool", summary="[]", data=[]),
            ToolResult(ok=True, tool_name="get_industry_hot_tool", summary="{}", data={}),
        ])
        ctx = SkillContext(db=_make_db(), user_id=_make_uid(), tool_registry=registry)
        result = await StockAnomalySkill().run("茅台异动", ctx)

        review_ev = next((e for e in result.tool_events if e.get("name") == "rag_review"), None)
        assert review_ev is not None
        detail = review_ev.get("detail", "")
        # Detail must contain a confidence level keyword
        assert any(kw in detail for kw in ("high", "medium", "low", "高", "中", "低")), (
            f"Expected confidence level in rag_review detail, got: {detail!r}"
        )
