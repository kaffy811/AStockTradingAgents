"""
Tests for Phase C7 PlannerExecutor.

Coverage:
  - merges tool_events and cards from multiple skill results
  - partial skill failure doesn't crash entire execution
  - action step creates confirmation object (does NOT execute write)
  - metadata has planner_used=True, plan_intent_type, skills_used, tools_used
  - unknown skill name → step status "failed", execution continues
  - no forbidden phrases in answer
  - answer contains _DISCLAIMER
  - clarification step handled inline
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.agents.chat_planner.base import ExecutionResult, PlanStep, PlannerResult
from app.agents.chat_planner.executor import PlannerExecutor
from app.agents.chat_skills.base import SkillContext, SkillResult, _DISCLAIMER


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _make_skill(
    name: str,
    answer: str = "skill answer\n\n后续观察\n1. 观察一\n2. 观察二",
    tool_events: list | None = None,
    cards: list | None = None,
    ok: bool = True,
) -> MagicMock:
    skill = MagicMock()
    skill.name = name
    result = SkillResult(
        ok=ok,
        skill_name=name,
        answer=answer,
        tool_events=tool_events or [{"name": f"{name}_tool", "status": "success", "detail": "ok"}],
        cards=cards or [],
    )
    skill.run = AsyncMock(return_value=result)
    return skill


def _make_registry(*skills) -> MagicMock:
    registry = MagicMock()
    lookup = {s.name: s for s in skills}
    registry.select_by_name = MagicMock(side_effect=lambda name: lookup.get(name))
    return registry


def _make_context() -> SkillContext:
    return SkillContext(
        db=AsyncMock(),
        user_id="user-123",
        output_language="zh-CN",
        tool_registry=MagicMock(),
    )


def _make_plan(intent_type: str, steps: list[PlanStep]) -> PlannerResult:
    return PlannerResult(ok=True, intent_type=intent_type, steps=steps)


# ── Tool event merging ─────────────────────────────────────────────────────────

class TestToolEventMerging:
    @pytest.mark.asyncio
    async def test_merges_tool_events_from_two_skills(self):
        s1 = _make_skill("stock_anomaly_skill", tool_events=[{"name": "t1", "status": "success", "detail": ""}])
        s2 = _make_skill("risk_first_skill",    tool_events=[{"name": "t2", "status": "success", "detail": ""}])
        registry = _make_registry(s1, s2)
        executor = PlannerExecutor(registry)

        plan = _make_plan("anomaly_then_risk", [
            PlanStep(step_id="s1", step_type="skill", name="stock_anomaly_skill"),
            PlanStep(step_id="s2", step_type="skill", name="risk_first_skill"),
            PlanStep(step_id="fin", step_type="final_summary", name="final_summary"),
        ])
        result = await executor.execute(plan, "为什么涨然后看风险", _make_context())

        event_names = [e["name"] for e in result.tool_events]
        assert "t1" in event_names
        assert "t2" in event_names

    @pytest.mark.asyncio
    async def test_merges_cards_from_multiple_skills(self):
        s1 = _make_skill("stock_anomaly_skill", cards=[{"type": "stock_summary", "data": {}}])
        s2 = _make_skill("risk_first_skill",    cards=[{"type": "risk_card", "data": {}}])
        registry = _make_registry(s1, s2)
        executor = PlannerExecutor(registry)

        plan = _make_plan("anomaly_then_risk", [
            PlanStep(step_id="s1", step_type="skill", name="stock_anomaly_skill"),
            PlanStep(step_id="s2", step_type="skill", name="risk_first_skill"),
            PlanStep(step_id="fin", step_type="final_summary", name="final_summary"),
        ])
        result = await executor.execute(plan, "为什么涨然后看风险", _make_context())

        card_types = [c["type"] for c in result.cards]
        assert "stock_summary" in card_types
        assert "risk_card" in card_types


# ── Partial failure ────────────────────────────────────────────────────────────

class TestPartialFailure:
    @pytest.mark.asyncio
    async def test_one_skill_raises_execution_continues(self):
        s1 = _make_skill("stock_anomaly_skill")
        s1.run = AsyncMock(side_effect=RuntimeError("network timeout"))
        s2 = _make_skill("risk_first_skill", answer="风险分析：主要风险包括行业竞争")
        registry = _make_registry(s1, s2)
        executor = PlannerExecutor(registry)

        plan = _make_plan("anomaly_then_risk", [
            PlanStep(step_id="s1", step_type="skill", name="stock_anomaly_skill"),
            PlanStep(step_id="s2", step_type="skill", name="risk_first_skill"),
            PlanStep(step_id="fin", step_type="final_summary", name="final_summary"),
        ])
        result = await executor.execute(plan, "为什么涨然后看风险", _make_context())

        assert result.ok is True  # overall execution still ok
        step_statuses = {r["name"]: r["status"] for r in result.steps}
        assert step_statuses["stock_anomaly_skill"] == "failed"
        assert step_statuses["risk_first_skill"] == "completed"

    @pytest.mark.asyncio
    async def test_unknown_skill_name_marks_step_failed(self):
        registry = _make_registry()  # empty — no skills
        executor = PlannerExecutor(registry)

        plan = _make_plan("anomaly_then_risk", [
            PlanStep(step_id="s1", step_type="skill", name="nonexistent_skill"),
            PlanStep(step_id="fin", step_type="final_summary", name="final_summary"),
        ])
        result = await executor.execute(plan, "test", _make_context())

        step_statuses = {r["name"]: r["status"] for r in result.steps}
        assert step_statuses["nonexistent_skill"] == "failed"
        assert result.ok is True  # doesn't crash


# ── Action step — confirmation only ───────────────────────────────────────────

class TestActionStepConfirmation:
    @pytest.mark.asyncio
    async def test_action_step_produces_confirmation_not_execution(self):
        s1 = _make_skill("risk_first_skill")
        registry = _make_registry(s1)
        executor = PlannerExecutor(registry)

        plan = _make_plan("research_then_action", [
            PlanStep(step_id="s1", step_type="skill", name="risk_first_skill"),
            PlanStep(step_id="fin", step_type="final_summary", name="final_summary"),
            PlanStep(
                step_id="act",
                step_type="action",
                name="add_watchlist",
                requires_confirmation=True,
                metadata={"action_type": "add_watchlist"},
            ),
        ])
        result = await executor.execute(plan, "分析688146然后加入自选", _make_context())

        # Confirmation must be present
        assert result.confirmation is not None
        assert result.confirmation["type"] == "add_watchlist"
        assert result.confirmation["status"] == "pending"

    @pytest.mark.asyncio
    async def test_action_step_status_waiting_confirmation(self):
        s1 = _make_skill("risk_first_skill")
        registry = _make_registry(s1)
        executor = PlannerExecutor(registry)

        plan = _make_plan("research_then_action", [
            PlanStep(step_id="s1", step_type="skill", name="risk_first_skill"),
            PlanStep(
                step_id="act",
                step_type="action",
                name="add_watchlist",
                requires_confirmation=True,
                metadata={"action_type": "add_watchlist"},
            ),
        ])
        result = await executor.execute(plan, "分析688146然后加入自选", _make_context())

        step_statuses = {r["name"]: r["status"] for r in result.steps}
        assert step_statuses["add_watchlist"] == "waiting_confirmation"

    @pytest.mark.asyncio
    async def test_action_step_without_stock_hint_skipped(self):
        registry = _make_registry()
        executor = PlannerExecutor(registry)

        plan = _make_plan("research_then_action", [
            PlanStep(
                step_id="act",
                step_type="action",
                name="add_watchlist",
                requires_confirmation=True,
                metadata={"action_type": "add_watchlist"},
            ),
        ])
        # message with no recognizable stock
        result = await executor.execute(plan, "分析然后加入自选", _make_context())

        step_statuses = {r["name"]: r["status"] for r in result.steps}
        assert step_statuses["add_watchlist"] == "skipped"
        assert result.confirmation is None


# ── Metadata ───────────────────────────────────────────────────────────────────

class TestMetadata:
    @pytest.mark.asyncio
    async def test_planner_used_true(self):
        s1 = _make_skill("stock_anomaly_skill")
        s2 = _make_skill("risk_first_skill")
        registry = _make_registry(s1, s2)
        executor = PlannerExecutor(registry)

        plan = _make_plan("anomaly_then_risk", [
            PlanStep(step_id="s1", step_type="skill", name="stock_anomaly_skill"),
            PlanStep(step_id="s2", step_type="skill", name="risk_first_skill"),
            PlanStep(step_id="fin", step_type="final_summary", name="final_summary"),
        ])
        result = await executor.execute(plan, "test", _make_context())
        assert result.metadata["planner_used"] is True

    @pytest.mark.asyncio
    async def test_plan_intent_type_in_metadata(self):
        s1 = _make_skill("stock_anomaly_skill")
        registry = _make_registry(s1)
        executor = PlannerExecutor(registry)

        plan = _make_plan("anomaly_then_risk", [
            PlanStep(step_id="s1", step_type="skill", name="stock_anomaly_skill"),
        ])
        result = await executor.execute(plan, "test", _make_context())
        assert result.metadata["plan_intent_type"] == "anomaly_then_risk"

    @pytest.mark.asyncio
    async def test_skills_used_deduped_in_metadata(self):
        s1 = _make_skill("stock_anomaly_skill")
        s2 = _make_skill("risk_first_skill")
        registry = _make_registry(s1, s2)
        executor = PlannerExecutor(registry)

        plan = _make_plan("anomaly_then_risk", [
            PlanStep(step_id="s1", step_type="skill", name="stock_anomaly_skill"),
            PlanStep(step_id="s2", step_type="skill", name="risk_first_skill"),
            PlanStep(step_id="fin", step_type="final_summary", name="final_summary"),
        ])
        result = await executor.execute(plan, "test", _make_context())
        skills_used = result.metadata["skills_used"]
        assert "stock_anomaly_skill" in skills_used
        assert "risk_first_skill" in skills_used
        # No duplicates
        assert len(skills_used) == len(set(skills_used))

    @pytest.mark.asyncio
    async def test_tools_used_in_metadata(self):
        s1 = _make_skill("stock_anomaly_skill", tool_events=[
            {"name": "get_quote_tool", "status": "success", "detail": ""},
        ])
        registry = _make_registry(s1)
        executor = PlannerExecutor(registry)

        plan = _make_plan("anomaly_then_risk", [
            PlanStep(step_id="s1", step_type="skill", name="stock_anomaly_skill"),
        ])
        result = await executor.execute(plan, "test", _make_context())
        assert "get_quote_tool" in result.metadata["tools_used"]


# ── Safety: no forbidden phrases ──────────────────────────────────────────────

class TestSafety:
    @pytest.mark.asyncio
    async def test_forbidden_phrases_stripped_from_answer(self):
        # Skill answer that contains a forbidden phrase
        s1 = _make_skill(
            "stock_anomaly_skill",
            answer="建议买入，目标价100元，必涨！",
        )
        registry = _make_registry(s1)
        executor = PlannerExecutor(registry)

        plan = _make_plan("anomaly_then_risk", [
            PlanStep(step_id="s1", step_type="skill", name="stock_anomaly_skill"),
        ])
        result = await executor.execute(plan, "test", _make_context())

        for phrase in ["买入", "卖出", "持有", "目标价", "必涨", "稳赚", "抄底", "追涨"]:
            assert phrase not in result.answer, f"Forbidden phrase '{phrase}' found in answer"

    @pytest.mark.asyncio
    async def test_disclaimer_in_answer(self):
        s1 = _make_skill("stock_anomaly_skill")
        registry = _make_registry(s1)
        executor = PlannerExecutor(registry)

        plan = _make_plan("anomaly_then_risk", [
            PlanStep(step_id="s1", step_type="skill", name="stock_anomaly_skill"),
        ])
        result = await executor.execute(plan, "test", _make_context())
        assert "仅供研究参考" in result.answer


# ── Clarification step ────────────────────────────────────────────────────────

class TestClarificationStep:
    @pytest.mark.asyncio
    async def test_clarification_step_completed(self):
        registry = _make_registry()
        executor = PlannerExecutor(registry)

        plan = _make_plan("clarification", [
            PlanStep(
                step_id="c1",
                step_type="clarification",
                name="clarification",
                metadata={"reason": "请提供股票代码"},
            ),
        ])
        result = await executor.execute(plan, "分析一下", _make_context())

        step_statuses = {r["name"]: r["status"] for r in result.steps}
        assert step_statuses["clarification"] == "completed"

    @pytest.mark.asyncio
    async def test_clarification_only_plan_returns_clarification_answer(self):
        registry = _make_registry()
        executor = PlannerExecutor(registry)

        plan = _make_plan("clarification", [
            PlanStep(
                step_id="c1",
                step_type="clarification",
                name="clarification",
                metadata={"reason": ""},
            ),
        ])
        result = await executor.execute(plan, "分析一下", _make_context())
        assert "需要更多信息" in result.answer or "仅供研究参考" in result.answer
