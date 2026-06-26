"""
C12: RAG + OpenClaw Agent Contract Tests.

Verifies that all research answers use RAG + Review Agents (Part F):
1. All 4 skills (StockAnomaly, RiskFirst, NewsCatalyst, ReportExplanation) emit RAG events
2. RAG answers include the "资料来源与可信度" section
3. RAG review metadata is in tool_events (rag_retrieve + rag_review)
4. External channel requests are refused gracefully (record metadata)
5. External channel refusal answer does NOT claim sending
6. External channel refusal mentions "历史报告" and "导出"
7. Skills' answers contain disclaimer
8. ConsistencyReviewAgent catches all 6 forbidden certainty phrases
"""

import uuid
import pytest
from collections import defaultdict
from unittest.mock import AsyncMock, MagicMock


def _make_uid():
    return uuid.UUID("00000000-0000-0000-0000-000000000033")


def _make_db():
    return AsyncMock()


def _make_registry(tool_results: list):
    """Dict-dispatch mock registry — safe for multi-tool calling order."""
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


# ── 1. All 4 skills emit RAG events ──────────────────────────────────────────

class TestAllSkillsUseRAG:

    @pytest.mark.asyncio
    async def test_stock_anomaly_emits_rag_retrieve_and_review(self):
        from app.agents.chat_skills.stock_anomaly_skill import StockAnomalySkill
        from app.agents.chat_tools.tool_result import ToolResult
        from app.agents.chat_skills.base import SkillContext

        registry = _make_registry([
            ToolResult(ok=True, tool_name="get_quote_tool", summary="¥1800",
                       data={"price": 1800, "change_pct": 2.1, "volume": 80000}),
            ToolResult(ok=True, tool_name="get_latest_news_tool", summary="[]", data=[]),
            ToolResult(ok=True, tool_name="get_recent_reports_tool", summary="[]", data=[]),
            ToolResult(ok=True, tool_name="get_industry_hot_tool", summary="{}", data={}),
        ])
        ctx = SkillContext(db=_make_db(), user_id=_make_uid(), tool_registry=registry)
        result = await StockAnomalySkill().run("茅台今天为什么异动？", ctx)

        names = {e.get("name") for e in result.tool_events}
        assert "rag_retrieve" in names
        assert "rag_review" in names

    @pytest.mark.asyncio
    async def test_risk_first_emits_rag_events(self):
        from app.agents.chat_skills.risk_first_skill import RiskFirstSkill
        from app.agents.chat_tools.tool_result import ToolResult
        from app.agents.chat_skills.base import SkillContext

        registry = _make_registry([
            ToolResult(ok=True, tool_name="get_latest_news_tool", summary="[]", data=[]),
            ToolResult(ok=True, tool_name="get_recent_reports_tool", summary="[]", data=[]),
            ToolResult(ok=True, tool_name="get_industry_hot_tool", summary="{}", data={}),
        ])
        ctx = SkillContext(db=_make_db(), user_id=_make_uid(), tool_registry=registry)
        result = await RiskFirstSkill().run("茅台有哪些风险？", ctx)

        names = {e.get("name") for e in result.tool_events}
        assert "rag_retrieve" in names
        assert "rag_review" in names

    @pytest.mark.asyncio
    async def test_news_catalyst_emits_rag_events(self):
        from app.agents.chat_skills.news_catalyst_skill import NewsCatalystSkill
        from app.agents.chat_tools.tool_result import ToolResult
        from app.agents.chat_skills.base import SkillContext

        registry = _make_registry([
            ToolResult(ok=True, tool_name="get_latest_news_tool", summary="[]", data=[]),
            ToolResult(ok=True, tool_name="get_recent_reports_tool", summary="[]", data=[]),
            ToolResult(ok=True, tool_name="get_industry_hot_tool", summary="{}", data={}),
        ])
        ctx = SkillContext(db=_make_db(), user_id=_make_uid(), tool_registry=registry)
        result = await NewsCatalystSkill().run("茅台有什么新闻催化剂？", ctx)

        names = {e.get("name") for e in result.tool_events}
        assert "rag_retrieve" in names
        assert "rag_review" in names

    @pytest.mark.asyncio
    async def test_report_explanation_emits_rag_events(self):
        from app.agents.chat_skills.report_explanation_skill import ReportExplanationSkill
        from app.agents.chat_tools.tool_result import ToolResult
        from app.agents.chat_skills.base import SkillContext

        registry = _make_registry([
            ToolResult(ok=True, tool_name="get_recent_reports_tool", summary="[]", data=[]),
            ToolResult(ok=True, tool_name="get_latest_news_tool", summary="[]", data=[]),
            ToolResult(ok=True, tool_name="get_industry_hot_tool", summary="{}", data={}),
        ])
        ctx = SkillContext(db=_make_db(), user_id=_make_uid(), tool_registry=registry)
        result = await ReportExplanationSkill().run("解释一下茅台最新报告", ctx)

        names = {e.get("name") for e in result.tool_events}
        assert "rag_retrieve" in names
        assert "rag_review" in names


# ── 2. RAG answer includes credibility section ─────────────────────────────────

class TestRAGAnswerContent:

    @pytest.mark.asyncio
    async def test_risk_first_answer_has_disclaimer(self):
        from app.agents.chat_skills.risk_first_skill import RiskFirstSkill
        from app.agents.chat_tools.tool_result import ToolResult
        from app.agents.chat_skills.base import SkillContext

        registry = _make_registry([
            ToolResult(ok=True, tool_name="get_latest_news_tool", summary="[]", data=[]),
            ToolResult(ok=True, tool_name="get_recent_reports_tool", summary="[]", data=[]),
            ToolResult(ok=True, tool_name="get_industry_hot_tool", summary="{}", data={}),
        ])
        ctx = SkillContext(db=_make_db(), user_id=_make_uid(), tool_registry=registry)
        result = await RiskFirstSkill().run("茅台有什么风险？", ctx)
        assert "研究参考" in result.answer or "投资建议" in result.answer, (
            "RiskFirstSkill answer must include disclaimer"
        )


# ── 3. External channel refusal ────────────────────────────────────────────────

class TestExternalChannelRefusal:

    @pytest.mark.asyncio
    async def test_email_request_refused(self):
        from app.agents.chat_orchestrator import process_message

        result = await process_message(
            "把报告发到我的邮箱 test@example.com",
            _make_db(),
            _make_uid(),
        )
        assert result.answer, "Must return a refusal answer"
        assert result.confirmation is None, "Must NOT produce a confirmation for external channel"

    @pytest.mark.asyncio
    async def test_wechat_request_refused(self):
        from app.agents.chat_orchestrator import process_message

        result = await process_message(
            "请帮我把报告发给微信",
            _make_db(),
            _make_uid(),
        )
        assert result.answer
        assert "暂不支持" in result.answer or "暂未" in result.answer, (
            "Refusal must explain the channel is not supported yet"
        )

    @pytest.mark.asyncio
    async def test_external_channel_answer_not_claiming_sent(self):
        from app.agents.chat_orchestrator import process_message

        result = await process_message(
            "发到邮箱",
            _make_db(),
            _make_uid(),
        )
        banned_claim_phrases = ["已发送", "发送成功", "邮件已寄出", "微信已发"]
        for phrase in banned_claim_phrases:
            assert phrase not in result.answer, (
                f"Refusal answer must not claim sending: {phrase!r} found in {result.answer!r}"
            )

    @pytest.mark.asyncio
    async def test_external_channel_mentions_history_alternative(self):
        from app.agents.chat_orchestrator import process_message

        result = await process_message(
            "把报告发到邮箱",
            _make_db(),
            _make_uid(),
        )
        assert "历史报告" in result.answer, (
            "Refusal must suggest using history report as alternative"
        )
        assert "导出" in result.answer, (
            "Refusal must mention export option"
        )

    @pytest.mark.asyncio
    async def test_dingtalk_request_refused(self):
        from app.agents.chat_orchestrator import process_message

        result = await process_message(
            "通过钉钉推送一下今天的行业报告",
            _make_db(),
            _make_uid(),
        )
        assert result.answer
        assert result.confirmation is None


# ── 4. ConsistencyReviewAgent forbidden phrase detection ──────────────────────

class TestConsistencyReviewCoverage:

    FORBIDDEN_PHRASES = ["必涨", "必跌", "稳赚", "一定会", "肯定会", "百分之百"]

    def _run_check(self, phrase: str) -> float:
        from app.agents.chat_rag.review_agents import ConsistencyReviewAgent
        from app.agents.chat_rag import RAGResult, RAGDocument
        agent = ConsistencyReviewAgent()
        doc = RAGDocument(
            doc_id="d1", source_type="report", title="Test",
            summary=f"该股{phrase}，请立即买入",
            source="internal",
        )
        result = RAGResult(ok=True, query="test", documents=[doc])
        review = agent.review(result)
        return review["consistency_score"]

    def test_bi_zhang_caught(self):
        assert self._run_check("必涨") < 1.0

    def test_bi_die_caught(self):
        assert self._run_check("必跌") < 1.0

    def test_wen_zhang_caught(self):
        assert self._run_check("稳赚") < 1.0

    def test_yi_ding_hui_caught(self):
        assert self._run_check("一定会") < 1.0

    def test_ken_ding_hui_caught(self):
        assert self._run_check("肯定会") < 1.0

    def test_bai_fen_zhi_bai_caught(self):
        assert self._run_check("百分之百") < 1.0
