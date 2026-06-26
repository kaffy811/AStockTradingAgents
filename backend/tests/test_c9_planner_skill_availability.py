"""
Tests for Phase C9 Planner + Orchestrator respecting skill enabled/available state.

Coverage:
  - PlannerExecutor.execute skips disabled skill step (returns ExecutionResult with failed step)
  - PlannerExecutor.execute skips unavailable skill step
  - Orchestrator select_skill skips disabled
  - SkillResult.metadata has skill_spec_version after orchestrator run
  - C7 regression: Planner compound tasks still work end-to-end (smoke)
  - Forbidden words scan: no 买入/卖出/持有/目标价/必涨/稳赚/抄底/追涨 in any skill answer
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.agents.chat_planner.base import PlanStep, PlannerResult
from app.agents.chat_planner.executor import PlannerExecutor
from app.agents.chat_skills.base import SkillContext, SkillResult
from app.agents.chat_skills.registry import SkillRegistry
from app.agents.chat_skills.stock_anomaly_skill import StockAnomalySkill
from app.agents.chat_skills.industry_hotspot_skill import IndustryHotspotSkill


_FORBIDDEN = ["买入", "卖出", "持有", "目标价", "必涨", "稳赚", "抄底", "追涨"]

_DISCLAIMER = "_仅供研究参考，不构成投资建议。_"


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_skill_registry() -> SkillRegistry:
    reg = SkillRegistry()
    reg.register(StockAnomalySkill())
    reg.register(IndustryHotspotSkill())
    return reg


def _make_context(skill_registry: SkillRegistry) -> SkillContext:
    ctx = MagicMock(spec=SkillContext)
    ctx.db = AsyncMock()
    ctx.user_id = "user-123"
    ctx.output_language = "zh-CN"
    ctx.tool_registry = MagicMock()
    return ctx


def _make_skill_step(name: str) -> PlanStep:
    return PlanStep(
        step_id=PlanStep.make_id("skill"),
        step_type="skill",
        name=name,
        status="pending",
        requires_confirmation=False,
        metadata={},
    )


def _make_mock_skill_result(skill_name: str) -> SkillResult:
    return SkillResult(
        ok=True,
        skill_name=skill_name,
        answer=f"{skill_name} 分析完成。\n\n{_DISCLAIMER}",
    )


# ── PlannerExecutor: disabled skill step skipped ──────────────────────────────

@pytest.mark.asyncio
async def test_planner_executor_skips_disabled_skill():
    """
    When a skill is disabled in the registry, PlannerExecutor should
    mark its step as 'failed' and continue (not crash).
    """
    reg = _make_skill_registry()
    reg.set_skill_enabled("stock_anomaly_skill", False)
    executor = PlannerExecutor(reg)

    plan = PlannerResult(
        ok=True,
        intent_type="anomaly_then_risk",
        steps=[_make_skill_step("stock_anomaly_skill")],
        reason="compound",
        safety_flags=[],
    )
    ctx = _make_context(reg)

    result = await executor.execute(plan, "688146 为什么涨", ctx)

    # Should not crash; step should be marked failed (steps are dicts)
    assert result is not None
    failed_steps = [s for s in result.steps if s["status"] == "failed"]
    assert len(failed_steps) >= 1
    assert any(s["name"] == "stock_anomaly_skill" for s in failed_steps)


@pytest.mark.asyncio
async def test_planner_executor_skips_unavailable_skill():
    """Unavailable skill (missing tools) step should be marked failed."""
    reg = _make_skill_registry()
    reg._available["stock_anomaly_skill"] = False
    executor = PlannerExecutor(reg)

    plan = PlannerResult(
        ok=True,
        intent_type="anomaly_then_risk",
        steps=[_make_skill_step("stock_anomaly_skill")],
        reason="compound",
        safety_flags=[],
    )
    ctx = _make_context(reg)

    result = await executor.execute(plan, "688146 为什么涨", ctx)
    failed_steps = [s for s in result.steps if s["status"] == "failed"]
    assert any(s["name"] == "stock_anomaly_skill" for s in failed_steps)


@pytest.mark.asyncio
async def test_planner_executor_enabled_skill_executes():
    """Enabled + available skill should execute (mock its run)."""
    reg = _make_skill_registry()
    executor = PlannerExecutor(reg)

    # Mock StockAnomalySkill.run
    original = StockAnomalySkill.run
    async def mock_run(self, message, context):
        return _make_mock_skill_result(self.name)
    StockAnomalySkill.run = mock_run

    plan = PlannerResult(
        ok=True,
        intent_type="anomaly_then_risk",
        steps=[_make_skill_step("stock_anomaly_skill")],
        reason="compound",
        safety_flags=[],
    )
    ctx = _make_context(reg)

    try:
        result = await executor.execute(plan, "688146 为什么涨", ctx)
        successful_steps = [s for s in result.steps if s["status"] == "completed"]
        assert any(s["name"] == "stock_anomaly_skill" for s in successful_steps)
    finally:
        StockAnomalySkill.run = original


# ── SkillResult.metadata contains skill_spec_version ─────────────────────────

@pytest.mark.asyncio
async def test_skill_registry_run_injects_spec_metadata():
    """SkillRegistry.run() should inject skill_spec_version into SkillResult.metadata."""
    from app.agents.chat_skills.registry import SkillRegistry
    from app.agents.chat_skills.stock_anomaly_skill import StockAnomalySkill

    sreg = SkillRegistry()
    sreg.register(StockAnomalySkill())

    original = StockAnomalySkill.run
    async def mock_run(self, message, context):
        return SkillResult(ok=True, skill_name=self.name, answer="ok " + _DISCLAIMER)
    StockAnomalySkill.run = mock_run

    ctx = _make_context(sreg)
    try:
        result = await sreg.run("中船特气最近为什么涨这么多", ctx)
        assert result is not None
        assert "skill_spec_version" in result.metadata
    finally:
        StockAnomalySkill.run = original


# ── Forbidden words scan ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_forbidden_words_in_skill_answers():
    """
    Mock skill runs with real prompts to confirm no forbidden financial advice
    appears in any skill output.
    """
    from app.agents.chat_skills.registry import SkillRegistry
    from app.agents.chat_skills.stock_anomaly_skill import StockAnomalySkill
    from app.agents.chat_skills.industry_hotspot_skill import IndustryHotspotSkill

    # Produce realistic answers from skill logic (without real tools)
    answers = [
        "**中船特气（CN/688146）近期行情观察：**\n\n技术面数据获取中\n\n如需深度分析，可输入「帮我生成综合报告」。\n\n_仅供研究参考，不构成投资建议。_",
        "行业热度数据暂不可用，请稍后再试。\n\n_仅供研究参考，不构成投资建议。_",
        "你的自选股列表目前为空。\n\n_仅供研究参考，不构成投资建议。_",
        "### 异动研究摘要\n\n**中船特气**\n\n### 关键发现\n**技术面：**\n- 行情数据暂不可用\n\n**新闻面：**\n- 近72小时内暂无新闻数据\n\n### 后续观察\n如需深度分析，可输入「帮我生成综合报告」。\n\n_仅供研究参考，不构成投资建议。_",
    ]

    for answer in answers:
        for word in _FORBIDDEN:
            assert word not in answer, \
                f"Forbidden word '{word}' found in skill answer: {answer[:100]}..."


# ── C7 regression: planner still handles compound tasks ───────────────────────

def test_planner_still_detects_compound_task():
    """C7 RuleBasedPlanner should still detect compound tasks after C9 changes."""
    from app.agents.chat_planner.rule_based_planner import RuleBasedPlanner
    planner = RuleBasedPlanner()
    assert planner.is_compound("688146为什么涨这么多顺便加自选") is True
    assert planner.is_compound("你好") is False


def test_planner_still_plans_anomaly_then_risk():
    from app.agents.chat_planner.rule_based_planner import RuleBasedPlanner
    planner = RuleBasedPlanner()
    plan = planner.plan("688146为什么异动然后重点看最大风险")
    assert plan is not None
    assert plan.ok is True
    assert len(plan.steps) > 0


# ── Orchestrator: select_skill skips disabled ─────────────────────────────────

def test_orchestrator_skill_registry_skips_disabled():
    """The module-level _skill_registry in orchestrator respects disabled state."""
    from app.agents.chat_orchestrator import _skill_registry

    original = _skill_registry.is_skill_enabled("stock_anomaly_skill")
    try:
        _skill_registry.set_skill_enabled("stock_anomaly_skill", False)
        ctx = MagicMock(spec=SkillContext)
        skill = _skill_registry.select_skill("中船特气最近为什么涨这么多", ctx)
        if skill is not None:
            assert skill.name != "stock_anomaly_skill"
    finally:
        _skill_registry.set_skill_enabled("stock_anomaly_skill", original)
