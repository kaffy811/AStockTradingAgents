"""
test_c11_chat_ux_contract.py — Phase C11 Chat UX Contract tests.

Validates structural contracts that the frontend depends on:
- OrchestratorResult shape
- RAG events appear in tool_events when skills run
- Skill answer includes disclaimer
- New intent matchers don't break existing safety or action matchers
"""
from __future__ import annotations

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.chat_orchestrator import (
    OrchestratorResult,
    _match_trading_request,
    _match_analysis_save_report,
    _match_external_channel,
    _match_report,
    _match_watchlist_add,
    process_message,
)
from app.agents.chat_rag.base import RAGDocument, RAGResult
from app.agents.chat_rag.review_agents import RAGReviewCoordinator


# ── OrchestratorResult contract ───────────────────────────────────────────────

class TestOrchestratorResultContract:
    def test_default_fields(self):
        r = OrchestratorResult(answer="hello")
        assert r.tool_events == []
        assert r.cards == []
        assert r.confirmation is None
        assert r.metadata == {}

    def test_no_safety_field(self):
        r = OrchestratorResult(answer="x")
        assert not hasattr(r, "safety")


# ── Intent matcher isolation ──────────────────────────────────────────────────

class TestIntentMatcherIsolation:
    """New C11 matchers should not steal traffic from existing matchers."""

    def test_simple_report_goes_to_match_report(self):
        msg = "帮我生成综合报告"
        assert _match_report(msg)
        assert not _match_analysis_save_report(msg)

    def test_save_report_goes_to_analysis_save(self):
        msg = "分析688146并保存到历史报告"
        assert _match_analysis_save_report(msg)

    def test_safety_not_broken_by_new_matchers(self):
        # Trading safety patterns still work
        assert _match_trading_request("帮我买入688146")
        assert _match_trading_request("帮我卖出600519")

    def test_watchlist_add_still_works(self):
        assert _match_watchlist_add("加入自选")
        assert not _match_external_channel("加入自选")

    def test_external_channel_not_triggered_by_analysis(self):
        assert not _match_external_channel("帮我分析688146")


# ── Safety guard takes priority over C11 matchers ────────────────────────────

@pytest.mark.asyncio
async def test_trading_guard_beats_analysis_save():
    """Even if message mentions save+report, trading pattern takes priority."""
    msg = "帮我买入688146并保存到历史报告"
    # Safety pattern matches
    assert _match_trading_request(msg)
    # Process should return safety refusal
    with patch("app.agents.chat_orchestrator._registry", MagicMock()):
        result = await process_message(
            content=msg,
            db=AsyncMock(),
            user_id=uuid.uuid4(),
            session_id=None,
        )
    assert "不提供交易指令" in result.answer


# ── RAG events in tool_events ─────────────────────────────────────────────────

class TestRAGEventsInSkills:
    """Verify that running a skill produces rag_retrieve/rag_review in tool_events."""

    @pytest.mark.asyncio
    async def test_stock_anomaly_skill_has_rag_events(self):
        from app.agents.chat_skills.stock_anomaly_skill import StockAnomalySkill
        from app.agents.chat_skills.base import SkillContext

        mock_tr = MagicMock()
        tool_result = MagicMock()
        tool_result.ok = True
        tool_result.data = {"market": "CN", "symbol": "688146", "name": "中船特气",
                            "price": "100", "change_pct": "+2%", "change_dir": "up"}
        tool_result.tool_name = "mock_tool"
        tool_result.summary = "ok"
        tool_result.cards = []
        tool_result.permission_level = "read_only"
        tool_result.duration_ms = None
        tool_result.started_at = None
        tool_result.error = None

        async def _call(*args, **kw):
            return tool_result

        mock_tr.call = _call
        ctx = SkillContext(db=object(), user_id="u", tool_registry=mock_tr)
        skill = StockAnomalySkill()
        result = await skill.run("中船特气最近为什么涨这么多", ctx)

        event_names = [e["name"] for e in result.tool_events]
        assert "rag_retrieve" in event_names
        assert "rag_review" in event_names

    @pytest.mark.asyncio
    async def test_report_explanation_skill_has_rag_events(self):
        from app.agents.chat_skills.report_explanation_skill import ReportExplanationSkill
        from app.agents.chat_skills.base import SkillContext

        mock_tr = MagicMock()
        tool_result = MagicMock()
        tool_result.ok = False
        tool_result.data = None
        tool_result.tool_name = "get_recent_reports_tool"
        tool_result.summary = "no reports"
        tool_result.cards = []
        tool_result.permission_level = "read_only"
        tool_result.duration_ms = None
        tool_result.started_at = None
        tool_result.error = None

        async def _call(*args, **kw):
            return tool_result

        mock_tr.call = _call
        ctx = SkillContext(db=object(), user_id="u", tool_registry=mock_tr)
        skill = ReportExplanationSkill()
        result = await skill.run("解释最近报告", ctx)

        event_names = [e["name"] for e in result.tool_events]
        assert "rag_retrieve" in event_names
        assert "rag_review" in event_names


# ── Disclaimer in skill answers ───────────────────────────────────────────────

class TestSkillAnswerDisclaimer:
    _DISCLAIMER_FRAG = "不构成投资建议"

    @pytest.mark.asyncio
    async def test_risk_first_skill_has_disclaimer(self):
        from app.agents.chat_skills.risk_first_skill import RiskFirstSkill
        from app.agents.chat_skills.base import SkillContext

        mock_tr = MagicMock()
        tool_result = MagicMock()
        tool_result.ok = False
        tool_result.data = None
        tool_result.tool_name = "mock"
        tool_result.summary = ""
        tool_result.cards = []
        tool_result.permission_level = "read_only"
        tool_result.duration_ms = None
        tool_result.started_at = None
        tool_result.error = None

        async def _call(*args, **kw):
            return tool_result

        mock_tr.call = _call
        ctx = SkillContext(db=object(), user_id="u", tool_registry=mock_tr)
        skill = RiskFirstSkill()
        result = await skill.run("中船特气最大风险是什么", ctx)
        assert self._DISCLAIMER_FRAG in result.answer

    @pytest.mark.asyncio
    async def test_news_catalyst_skill_has_disclaimer(self):
        from app.agents.chat_skills.news_catalyst_skill import NewsCatalystSkill
        from app.agents.chat_skills.base import SkillContext

        mock_tr = MagicMock()
        tool_result = MagicMock()
        tool_result.ok = False
        tool_result.data = None
        tool_result.tool_name = "mock"
        tool_result.summary = ""
        tool_result.cards = []
        tool_result.permission_level = "read_only"
        tool_result.duration_ms = None
        tool_result.started_at = None
        tool_result.error = None

        async def _call(*args, **kw):
            return tool_result

        mock_tr.call = _call
        ctx = SkillContext(db=object(), user_id="u", tool_registry=mock_tr)
        skill = NewsCatalystSkill()
        result = await skill.run("688146 新闻有什么影响", ctx)
        assert self._DISCLAIMER_FRAG in result.answer
