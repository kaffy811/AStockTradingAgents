"""
Tests for Phase C7 RuleBasedPlanner.

Coverage:
  - is_compound() detection with connector words and multi-signal messages
  - plan() returns None for simple single-intent messages
  - plan() returns correct PlannerResult for each compound intent type
  - Step structure validation for each intent type
  - MAX_STEPS enforcement
  - PlanStep.make_id() uniqueness
  - clarification fallback for unknown compound intent
"""
from __future__ import annotations

import pytest

from app.agents.chat_planner.rule_based_planner import RuleBasedPlanner, MAX_STEPS
from app.agents.chat_planner.base import PlannerResult, PlanStep


@pytest.fixture
def planner() -> RuleBasedPlanner:
    return RuleBasedPlanner()


# ── is_compound() ──────────────────────────────────────────────────────────────

class TestIsCompound:
    def test_connector_word_然后(self, planner):
        assert planner.is_compound("为什么涨然后看看风险") is True

    def test_connector_word_并且(self, planner):
        assert planner.is_compound("看行业热点并且找几个股票") is True

    def test_connector_word_之后(self, planner):
        assert planner.is_compound("解释报告之后告诉我风险") is True

    def test_connector_word_如果(self, planner):
        assert planner.is_compound("分析688146如果可以就加入自选") is True

    def test_two_signals_no_connector(self, planner):
        # anomaly + risk signals, no connector word
        assert planner.is_compound("为什么异动这么大风险在哪里") is True

    def test_simple_single_intent_is_not_compound(self, planner):
        assert planner.is_compound("688146 现在多少钱") is False

    def test_simple_news_is_not_compound(self, planner):
        assert planner.is_compound("中船特气最新新闻") is False

    def test_simple_watchlist_view_is_not_compound(self, planner):
        assert planner.is_compound("查看我的自选股") is False


# ── plan() returns None for simple messages ────────────────────────────────────

class TestPlanReturnsNone:
    def test_simple_quote_returns_none(self, planner):
        assert planner.plan("600519 现在多少钱") is None

    def test_simple_report_gen_returns_none(self, planner):
        # "帮我生成报告" alone is not compound (no connector word, only 1 signal)
        assert planner.plan("帮我生成688146的综合报告") is None

    def test_not_compound_returns_none(self, planner):
        assert planner.plan("我的自选股") is None


# ── anomaly_then_risk ──────────────────────────────────────────────────────────

class TestAnomalyThenRisk:
    def test_plan_returns_plannerresult(self, planner):
        result = planner.plan("为什么涨这么多然后重点看风险")
        assert isinstance(result, PlannerResult)
        assert result.ok is True

    def test_intent_type(self, planner):
        result = planner.plan("为什么涨这么多然后重点看风险")
        assert result.intent_type == "anomaly_then_risk"

    def test_three_steps(self, planner):
        result = planner.plan("为什么涨这么多然后重点看风险")
        assert len(result.steps) == 3

    def test_step_order(self, planner):
        result = planner.plan("688146为什么异动然后重点看风险")
        names = [s.name for s in result.steps]
        assert names == ["stock_anomaly_skill", "risk_first_skill", "final_summary"]

    def test_step_types(self, planner):
        result = planner.plan("688146为什么异动然后重点看风险")
        types = [s.step_type for s in result.steps]
        assert types == ["skill", "skill", "final_summary"]

    def test_all_steps_pending(self, planner):
        result = planner.plan("688146为什么异动然后重点看风险")
        for step in result.steps:
            assert step.status == "pending"


# ── report_then_risk ───────────────────────────────────────────────────────────

class TestReportThenRisk:
    def test_intent_type(self, planner):
        result = planner.plan("解释这份报告然后告诉我主要风险")
        assert result is not None
        assert result.intent_type == "report_then_risk"

    def test_steps(self, planner):
        result = planner.plan("解释这份报告并告诉我风险")
        assert result is not None
        names = [s.name for s in result.steps]
        assert "report_explanation_skill" in names
        assert "risk_first_skill" in names
        assert "final_summary" in names

    def test_three_steps(self, planner):
        result = planner.plan("解释这份报告并告诉我风险")
        assert result is not None
        assert len(result.steps) == 3


# ── watchlist_scan ─────────────────────────────────────────────────────────────

class TestWatchlistScan:
    def test_intent_type(self, planner):
        # connector "然后" makes it compound
        result = planner.plan("看看自选股然后找有没有最近波动大的")
        assert result is not None
        assert result.intent_type == "watchlist_scan"

    def test_contains_watchlist_review_skill(self, planner):
        result = planner.plan("看看自选股然后找有没有最近波动大的")
        assert result is not None
        names = [s.name for s in result.steps]
        assert "watchlist_review_skill" in names

    def test_two_steps(self, planner):
        result = planner.plan("看看自选股然后找有没有最近波动大的")
        assert result is not None
        assert len(result.steps) == 2


# ── industry_then_stocks ───────────────────────────────────────────────────────

class TestIndustryThenStocks:
    def test_intent_type(self, planner):
        result = planner.plan("哪些行业最热然后每个行业挑几个股票看一下")
        assert result is not None
        assert result.intent_type == "industry_then_stocks"

    def test_contains_industry_skill(self, planner):
        result = planner.plan("哪些行业最热然后每个行业挑几个股票看一下")
        assert result is not None
        names = [s.name for s in result.steps]
        assert "industry_hotspot_skill" in names

    def test_two_steps(self, planner):
        result = planner.plan("哪些行业最热然后每个行业挑几个股票看一下")
        assert result is not None
        assert len(result.steps) == 2


# ── research_then_action ───────────────────────────────────────────────────────

class TestResearchThenAction:
    def test_intent_type(self, planner):
        # anomaly signal + add_watchlist signal → research_then_action
        result = planner.plan("688146为什么涨这么多如果合理就加入自选")
        assert result is not None
        assert result.intent_type == "research_then_action"

    def test_has_action_step_with_confirmation(self, planner):
        result = planner.plan("688146为什么涨这么多如果合理就加入自选")
        assert result is not None
        action_steps = [s for s in result.steps if s.step_type == "action"]
        assert len(action_steps) == 1
        assert action_steps[0].requires_confirmation is True

    def test_action_step_metadata(self, planner):
        result = planner.plan("688146为什么涨这么多如果合理就加入自选")
        assert result is not None
        action_steps = [s for s in result.steps if s.step_type == "action"]
        assert action_steps[0].metadata.get("action_type") == "add_watchlist"

    def test_anomaly_research_skill_when_anomaly_signal(self, planner):
        result = planner.plan("688146为什么涨这么多如果合理就加入自选")
        assert result is not None
        skill_steps = [s for s in result.steps if s.step_type == "skill"]
        assert skill_steps[0].name == "stock_anomaly_skill"

    def test_risk_skill_fallback_when_no_anomaly_signal(self, planner):
        # report signal + add_watchlist → research_then_action with risk fallback
        result = planner.plan("看看688146的最新报告结论然后加入自选")
        assert result is not None
        assert result.intent_type == "research_then_action"
        skill_steps = [s for s in result.steps if s.step_type == "skill"]
        assert skill_steps[0].name == "risk_first_skill"


# ── compare_then_report ────────────────────────────────────────────────────────

class TestCompareThenReport:
    def test_intent_type(self, planner):
        result = planner.plan("比较宁德时代和紫金矿业然后帮我生成报告")
        assert result is not None
        assert result.intent_type == "compare_then_report"

    def test_has_clarification_step(self, planner):
        result = planner.plan("比较宁德时代和紫金矿业然后帮我生成报告")
        assert result is not None
        clarify_steps = [s for s in result.steps if s.step_type == "clarification"]
        assert len(clarify_steps) >= 1

    def test_has_action_step(self, planner):
        result = planner.plan("比较宁德时代和紫金矿业然后帮我生成报告")
        assert result is not None
        action_steps = [s for s in result.steps if s.step_type == "action"]
        assert len(action_steps) >= 1


# ── MAX_STEPS enforcement ──────────────────────────────────────────────────────

class TestMaxSteps:
    def test_max_steps_not_exceeded(self, planner):
        # anomaly_then_risk produces 3 steps; verify never > MAX_STEPS
        result = planner.plan("为什么涨然后重点看风险")
        assert result is not None
        assert len(result.steps) <= MAX_STEPS

    def test_max_steps_constant_is_5(self):
        assert MAX_STEPS == 5


# ── PlanStep.make_id() uniqueness ──────────────────────────────────────────────

class TestPlanStepMakeId:
    def test_ids_are_unique(self):
        ids = {PlanStep.make_id("s") for _ in range(20)}
        assert len(ids) == 20  # all unique

    def test_id_contains_prefix(self):
        step_id = PlanStep.make_id("s1")
        assert step_id.startswith("s1_")

    def test_id_has_hex_suffix(self):
        step_id = PlanStep.make_id("step")
        suffix = step_id.split("_", 1)[1]
        assert len(suffix) == 6
        assert all(c in "0123456789abcdef" for c in suffix)
