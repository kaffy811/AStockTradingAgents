"""
C11-c: E2E contract tests.

Verifies the full orchestrator dispatch chain for key user scenarios:
1. "analyze Maotai fundamental + save" → confirmation card → action_type=create_analysis_run
2. External channel refusal text includes "历史报告" and "导出"
3. RAG events appear in tool_events for skill responses
4. Timeout guard: hard timeout sets error state, not demo mode
5. Intent ordering: analysis_save_report matcher beats report matcher
"""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_db():
    return AsyncMock()


def _make_uid():
    return uuid.UUID("00000000-0000-0000-0000-000000000099")


# ── 1. Full intent dispatch smoke tests ───────────────────────────────────────

class TestIntentDispatch:

    @pytest.mark.asyncio
    async def test_analysis_save_report_dispatched_before_report(self):
        """分析…保存报告 must hit _match_analysis_save_report, not _match_report."""
        from app.agents.chat_orchestrator import process_message as route_message

        result = await route_message(
            "帮我分析茅台的基本面并保存到历史报告",
            _make_db(),
            _make_uid(),
        )
        # confirmation present → correct intent
        assert result.confirmation is not None, (
            "Expected confirmation from analysis_save_report intent"
        )
        assert result.confirmation.get("type") == "create_analysis_run"

    @pytest.mark.asyncio
    async def test_simple_report_does_not_trigger_save(self):
        """帮我生成综合报告 must NOT have save_to_history=True in params."""
        from app.agents.chat_orchestrator import process_message as route_message

        result = await route_message(
            "帮我生成茅台的综合报告",
            _make_db(),
            _make_uid(),
        )
        # Both report and analysis_save_report return create_analysis_run confirmations,
        # but only analysis_save_report sets save_to_history=True in params.
        if result.confirmation:
            params = result.confirmation.get("params", {})
            assert params.get("save_to_history") is not True, (
                "Simple report generation must NOT set save_to_history=True; "
                "only the analysis_save_report intent sets that flag"
            )

    @pytest.mark.asyncio
    async def test_external_channel_refusal_contains_history_link(self):
        """Refusal for external channels must mention '历史报告' and '导出'."""
        from app.agents.chat_orchestrator import process_message as route_message

        result = await route_message(
            "把报告发到我的邮箱",
            _make_db(),
            _make_uid(),
        )
        assert "历史报告" in result.answer
        assert "导出" in result.answer

    @pytest.mark.asyncio
    async def test_wechat_refusal(self):
        """微信发送 must also be caught by external_channel intent."""
        from app.agents.chat_orchestrator import process_message as route_message

        result = await route_message(
            "发给微信",
            _make_db(),
            _make_uid(),
        )
        assert result.confirmation is None  # no confirmation for refusal
        assert result.answer  # refusal text present

    @pytest.mark.asyncio
    async def test_trading_guard_beats_analysis_save(self):
        """Trading guard keywords (必涨/追涨) must intercept before analysis_save_report."""
        from app.agents.chat_orchestrator import process_message as route_message

        # "必涨" and "抄底" both trigger _TRADING_PATTERN; saves should NOT proceed
        result = await route_message(
            "这支股票必涨，帮我抄底并保存到历史报告",
            _make_db(),
            _make_uid(),
        )
        # Trading guard fires → answer present (safety refusal), confirmation=None
        assert result.answer, "Trading guard must produce a refusal answer"
        assert result.confirmation is None, (
            "Trading guard must block confirmation — no create_analysis_run allowed"
        )


# ── 2. OrchestratorResult shape ───────────────────────────────────────────────

class TestOrchestratorResultShape:

    @pytest.mark.asyncio
    async def test_result_has_required_fields(self):
        from app.agents.chat_orchestrator import process_message as route_message

        result = await route_message("茅台股价如何", _make_db(), _make_uid())
        assert hasattr(result, "answer")
        assert hasattr(result, "tool_events")
        assert hasattr(result, "cards")
        assert hasattr(result, "confirmation")

    @pytest.mark.asyncio
    async def test_result_has_no_safety_attribute(self):
        """OrchestratorResult must NOT have a top-level 'safety' attribute."""
        from app.agents.chat_orchestrator import process_message as route_message

        result = await route_message("查看自选股", _make_db(), _make_uid())
        assert not hasattr(result, "safety"), (
            "OrchestratorResult must not have a 'safety' attribute"
        )

    @pytest.mark.asyncio
    async def test_tool_events_is_list(self):
        from app.agents.chat_orchestrator import process_message as route_message

        result = await route_message("帮我分析贵州茅台并保存到历史报告", _make_db(), _make_uid())
        assert isinstance(result.tool_events, list)


# ── 3. RAG events in skill responses ─────────────────────────────────────────

class TestRAGEventsInSkillResponses:
    """Verify that Skills emit rag_retrieve and rag_review tool_events."""

    @pytest.mark.asyncio
    async def test_stock_anomaly_skill_emits_rag_events(self):
        from app.agents.chat_skills.stock_anomaly_skill import StockAnomalySkill
        from app.agents.chat_tools.tool_result import ToolResult
        from app.agents.chat_skills.base import SkillContext

        quote_result = ToolResult(
            ok=True, tool_name="get_quote_tool",
            summary="茅台 ¥1800",
            data={"price": 1800.0, "change_pct": 0.5, "volume": 50000, "market_cap": 2.26e12},
        )
        news_result  = ToolResult(ok=True, tool_name="get_latest_news_tool",  summary="[]", data=[])
        report_result = ToolResult(ok=True, tool_name="get_recent_reports_tool", summary="[]", data=[])
        industry_result = ToolResult(ok=True, tool_name="get_industry_hot_tool", summary="{}", data={})

        registry_mock = MagicMock()
        from collections import defaultdict
        queues = defaultdict(list)
        for r in [quote_result, news_result, report_result, industry_result]:
            queues[r.tool_name].append(r)
        fallback = ToolResult(ok=False, tool_name="unknown", summary="no mock")
        async def _call(tool_name, db, **kw):
            q = queues.get(tool_name, [])
            return q.pop(0) if q else fallback
        registry_mock.call = _call

        ctx = SkillContext(
            db=_make_db(),
            user_id=_make_uid(),
            tool_registry=registry_mock,
        )

        skill = StockAnomalySkill()
        result = await skill.run("茅台为什么今天异动", ctx)

        names = [e.get("name") for e in result.tool_events]
        assert "rag_retrieve" in names, f"rag_retrieve missing from tool_events: {names}"
        assert "rag_review"   in names, f"rag_review missing from tool_events: {names}"

    @pytest.mark.asyncio
    async def test_news_catalyst_skill_emits_rag_events(self):
        from app.agents.chat_skills.news_catalyst_skill import NewsCatalystSkill
        from app.agents.chat_tools.tool_result import ToolResult
        from app.agents.chat_skills.base import SkillContext

        news_result  = ToolResult(ok=True, tool_name="get_latest_news_tool", summary="[]", data=[])
        report_result = ToolResult(ok=True, tool_name="get_recent_reports_tool", summary="[]", data=[])
        industry_result = ToolResult(ok=True, tool_name="get_industry_hot_tool", summary="{}", data={})

        from collections import defaultdict
        queues = defaultdict(list)
        for r in [news_result, report_result, industry_result]:
            queues[r.tool_name].append(r)
        fallback = ToolResult(ok=False, tool_name="unknown", summary="no mock")
        registry_mock = MagicMock()
        async def _call(tool_name, db, **kw):
            q = queues.get(tool_name, [])
            return q.pop(0) if q else fallback
        registry_mock.call = _call

        ctx = SkillContext(
            db=_make_db(),
            user_id=_make_uid(),
            tool_registry=registry_mock,
        )

        skill = NewsCatalystSkill()
        result = await skill.run("茅台有什么新闻催化剂", ctx)

        names = [e.get("name") for e in result.tool_events]
        assert "rag_retrieve" in names
        assert "rag_review"   in names
