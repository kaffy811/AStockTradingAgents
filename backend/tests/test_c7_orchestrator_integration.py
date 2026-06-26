"""
Tests for Phase C7 Orchestrator integration with Controlled Planner.

Coverage:
  - Trading safety request blocked before planner (planner_used NOT in metadata)
  - Explicit "加入自选" → action confirmation, NOT planner
  - Compound "为什么涨，然后重点看风险" → planner_used=True, plan_intent_type="anomaly_then_risk"
  - research_then_action → confirmation exists with status="pending"
  - metadata has planner_used and plan_intent_type fields
  - Simple single-intent message → skill_registry (source="skill_registry"), NOT planner
  - Planner answer contains _DISCLAIMER
  - Planner answer has no forbidden phrases
"""
from __future__ import annotations

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.chat_orchestrator import OrchestratorResult, process_message


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_db() -> AsyncMock:
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_result)
    db.flush = AsyncMock()
    nested_ctx = MagicMock()
    nested_ctx.__aenter__ = AsyncMock(return_value=None)
    nested_ctx.__aexit__ = AsyncMock(return_value=False)
    db.begin_nested = MagicMock(return_value=nested_ctx)
    return db


def _user() -> uuid.UUID:
    return uuid.UUID("12345678-1234-5678-1234-567812345678")


def _skill_result(name: str) -> MagicMock:
    from app.agents.chat_skills.base import SkillResult
    return SkillResult(
        ok=True,
        skill_name=name,
        answer=f"{name} result\n\n_仅供研究参考，不构成投资建议。_",
        tool_events=[{"name": f"{name}_tool", "status": "success", "detail": ""}],
        cards=[],
    )


# ── Safety guard ───────────────────────────────────────────────────────────────

class TestSafetyGuard:
    @pytest.mark.asyncio
    async def test_trading_request_blocked_before_planner(self):
        db = _make_db()
        result = await process_message("帮我买入688146", db, _user())

        assert isinstance(result, OrchestratorResult)
        # Safety response — no planner in metadata
        assert result.metadata.get("planner_used") is not True
        assert "交易指令" in result.answer or "不提供" in result.answer

    @pytest.mark.asyncio
    async def test_price_prediction_blocked(self):
        db = _make_db()
        result = await process_message("688146明天会涨吗，价格预测一下", db, _user())
        assert result.metadata.get("planner_used") is not True


# ── Action intents bypass planner ─────────────────────────────────────────────

class TestActionIntentsBypassPlanner:
    @pytest.mark.asyncio
    async def test_explicit_watchlist_add_goes_to_action_handler_not_planner(self):
        db = _make_db()
        with patch("app.agents.chat_orchestrator._registry.call") as mock_call:
            mock_call.return_value = MagicMock(
                ok=True,
                data={"market": "CN", "symbol": "688146", "name": "中船特气"},
                cards=[],
                tool_name="resolve_stock_tool",
                summary="resolved",
            )
            result = await process_message("把688146加入自选", db, _user())

        # Should produce a confirmation (action handler), NOT planner
        assert result.confirmation is not None
        assert result.metadata.get("planner_used") is not True

    @pytest.mark.asyncio
    async def test_explicit_report_generation_goes_to_action_handler(self):
        db = _make_db()
        with patch("app.agents.chat_orchestrator._registry.call") as mock_call:
            mock_call.return_value = MagicMock(
                ok=True,
                data={"market": "CN", "symbol": "688146", "name": "中船特气"},
                cards=[],
                tool_name="resolve_stock_tool",
                summary="resolved",
            )
            result = await process_message("帮我生成688146的综合报告", db, _user())

        assert result.confirmation is not None
        assert result.confirmation["type"] == "create_analysis_run"
        assert result.metadata.get("planner_used") is not True


# ── Compound messages → Planner ────────────────────────────────────────────────

class TestCompoundMessagesGoToPlanner:
    @pytest.mark.asyncio
    async def test_anomaly_then_risk_uses_planner(self):
        db = _make_db()
        with patch("app.agents.chat_orchestrator._skill_registry.select_by_name") as mock_select:
            anomaly_skill = MagicMock()
            anomaly_skill.name = "stock_anomaly_skill"
            anomaly_skill.run = AsyncMock(return_value=_skill_result("stock_anomaly_skill"))

            risk_skill = MagicMock()
            risk_skill.name = "risk_first_skill"
            risk_skill.run = AsyncMock(return_value=_skill_result("risk_first_skill"))

            lookup = {
                "stock_anomaly_skill": anomaly_skill,
                "risk_first_skill": risk_skill,
            }
            mock_select.side_effect = lambda name: lookup.get(name)

            result = await process_message(
                "688146为什么涨这么多然后重点看风险",
                db, _user(),
            )

        assert result.metadata.get("planner_used") is True
        assert result.metadata.get("plan_intent_type") == "anomaly_then_risk"

    @pytest.mark.asyncio
    async def test_planner_answer_contains_disclaimer(self):
        db = _make_db()
        with patch("app.agents.chat_orchestrator._skill_registry.select_by_name") as mock_select:
            s1 = MagicMock()
            s1.name = "stock_anomaly_skill"
            s1.run = AsyncMock(return_value=_skill_result("stock_anomaly_skill"))
            mock_select.return_value = s1

            result = await process_message(
                "688146为什么涨这么多然后重点看风险",
                db, _user(),
            )

        assert "仅供研究参考" in result.answer

    @pytest.mark.asyncio
    async def test_planner_answer_no_forbidden_phrases(self):
        db = _make_db()
        with patch("app.agents.chat_orchestrator._skill_registry.select_by_name") as mock_select:
            s1 = MagicMock()
            s1.name = "stock_anomaly_skill"
            s1.run = AsyncMock(return_value=_skill_result("stock_anomaly_skill"))
            mock_select.return_value = s1

            result = await process_message(
                "688146为什么涨这么多然后重点看风险",
                db, _user(),
            )

        for phrase in ["买入", "卖出", "持有", "目标价", "必涨", "稳赚", "抄底", "追涨"]:
            assert phrase not in result.answer

    @pytest.mark.asyncio
    async def test_research_then_action_confirmation_pending(self):
        """
        Planner research_then_action path.
        Uses "加自选" (not "加入自选") so the action handler (_match_watchlist_add) does NOT
        intercept first — only the planner's _ADD_WL_SIG matches "加自选".
        """
        db = _make_db()
        with patch("app.agents.chat_orchestrator._skill_registry.select_by_name") as mock_select:
            s1 = MagicMock()
            s1.name = "stock_anomaly_skill"
            s1.run = AsyncMock(return_value=_skill_result("stock_anomaly_skill"))
            mock_select.return_value = s1

            result = await process_message(
                "688146为什么涨这么多顺便加自选",
                db, _user(),
            )

        # research_then_action via planner: confirmation should exist
        assert result.confirmation is not None
        assert result.confirmation["status"] == "pending"
        assert result.confirmation["type"] == "add_watchlist"
        assert result.metadata.get("planner_used") is True


# ── Simple single-intent → SkillRegistry (not Planner) ────────────────────────

class TestSimpleSingleIntentSkillRegistry:
    @pytest.mark.asyncio
    async def test_simple_anomaly_query_uses_skill_registry_not_planner(self):
        db = _make_db()
        with patch("app.agents.chat_orchestrator._skill_registry.run") as mock_run:
            mock_run.return_value = _skill_result("stock_anomaly_skill")

            result = await process_message("688146 最近为什么涨", db, _user())

        # No compound connector → should hit SkillRegistry, NOT Planner
        assert result.metadata.get("source") == "skill_registry"
        assert result.metadata.get("planner_used") is not True

    @pytest.mark.asyncio
    async def test_skill_registry_metadata_present(self):
        db = _make_db()
        with patch("app.agents.chat_orchestrator._skill_registry.run") as mock_run:
            mock_run.return_value = _skill_result("news_catalyst_skill")

            result = await process_message("688146 最新新闻消息", db, _user())

        assert result.metadata.get("source") == "skill_registry"
        assert "skill_name" in result.metadata


# ── Planner fallthrough on failure ────────────────────────────────────────────

class TestPlannerFallthrough:
    @pytest.mark.asyncio
    async def test_planner_execution_failure_falls_through_to_skill_registry(self):
        db = _make_db()
        with (
            patch("app.agents.chat_orchestrator._executor.execute", side_effect=RuntimeError("test error")),
            patch("app.agents.chat_orchestrator._skill_registry.run") as mock_skill_run,
        ):
            mock_skill_run.return_value = _skill_result("stock_anomaly_skill")

            result = await process_message(
                "688146为什么涨这么多然后重点看风险",
                db, _user(),
            )

        # Should fall through to SkillRegistry
        assert result.metadata.get("source") == "skill_registry"
