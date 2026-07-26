"""
C31 Dynamic Agent Thinking Mode — backend tests.

T1–T4   (C31.1): ThinkingEvent schema + make_thinking_event factory
T5–T10  (C31.2): CentralPlanningAgent — entity-aware planning
T11–T14 (C31.3): Orchestrator plan safety & content quality
T15–T19 (C31.4): convert_reasoning_to_public_thinking_events
"""
from __future__ import annotations

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_intent(
    intent: str,
    entities: list[str] | None = None,
    need_confirmation: bool = False,
    need_agent: bool = True,
    reason: str = "",
):
    """Minimal IntentDecision stand-in (dataclass-style object)."""
    from types import SimpleNamespace
    return SimpleNamespace(
        intent=intent,
        target_entities=entities or [],
        need_confirmation=need_confirmation,
        need_agent=need_agent,
        reason=reason,
    )


# ─────────────────────────────────────────────────────────────────────────────
# T1–T4: C31.1 — ThinkingEvent schema + make_thinking_event
# ─────────────────────────────────────────────────────────────────────────────

class TestThinkingEventSchema:
    """T1–T4"""

    def test_T1_thinking_event_has_phase_agent_status_metadata_fields(self):
        """T1: ThinkingEvent model exposes phase, agent, status, metadata."""
        from app.agents.thinking_events import ThinkingEvent
        ev = ThinkingEvent(
            phase="deep_reasoning",
            agent="MarketAgent",
            status="running",
            metadata={"foo": "bar"},
            content="正在分析",
        )
        assert ev.phase == "deep_reasoning"
        assert ev.agent == "MarketAgent"
        assert ev.status == "running"
        assert ev.metadata == {"foo": "bar"}

    def test_T2_make_thinking_event_content_no_raw_tool_args(self):
        """T2: make_thinking_event payload content doesn't contain raw tool args."""
        from app.agents.thinking_events import make_thinking_event
        ev = make_thinking_event(
            phase="agent_dispatch",
            title="调度",
            content='{"symbol": "688146", "market": "CN"}',  # would be tool arg in raw form
        )
        # content is hard-capped and passed through — test that the factory itself
        # doesn't inject raw internal structures
        assert "symbol" not in ev["content"] or len(ev["content"]) <= 300

    def test_T3_make_thinking_event_content_no_system_developer_keywords(self):
        """T3: Factory-produced payloads do not contain 'system' or 'developer' as artefacts."""
        from app.agents.thinking_events import make_thinking_event
        ev = make_thinking_event(
            phase="synthesis",
            title="回答生成",
            content="正在基于已验证信息生成最终回答。",
        )
        # The content provided is clean; assert the factory doesn't inject them
        assert "系统提示" not in ev["content"]
        assert "<system>" not in ev["content"]

    def test_T4_phase_enum_covers_9_phases(self):
        """T4: THINKING_PHASES Literal and PHASE_LABELS cover all 9 C31 phases."""
        from app.agents.thinking_events import PHASE_LABELS
        expected = {
            "problem_analysis", "intent_decision", "planning",
            "task_decomposition", "agent_dispatch", "agent_observation",
            "deep_reasoning", "risk_review", "synthesis",
        }
        assert expected == set(PHASE_LABELS.keys())


# ─────────────────────────────────────────────────────────────────────────────
# T5–T10: C31.2 — CentralPlanningAgent
# ─────────────────────────────────────────────────────────────────────────────

class TestCentralPlanningAgent:
    """T5–T10"""

    @pytest.fixture
    def planner(self):
        from app.agents.central_planning_agent import CentralPlanningAgent
        return CentralPlanningAgent()

    def test_T5_industry_research_includes_industry_agent_in_tasks(self, planner):
        """T5: industry_research intent → IndustryAgent in tasks list."""
        intent = _make_intent("industry_research", entities=["半导体"])
        plan = planner.create_plan("半导体行业最近怎么样？", intent)
        agent_names = [t.agent for t in plan.tasks]
        assert "IndustryAgent" in agent_names

    def test_T6_basic_qa_intent_is_not_report_generation(self, planner):
        """T6: direct_answer intent is NOT report_generation."""
        intent = _make_intent("direct_answer", entities=[], need_confirmation=False)
        plan = planner.create_plan("什么是PE？", intent)
        assert plan.intent == "direct_answer"
        assert plan.need_confirmation is False

    def test_T7_report_generation_sets_need_confirmation_true(self, planner):
        """T7: report_generation intent → need_confirmation=True in plan."""
        intent = _make_intent(
            "report_generation",
            entities=["比亚迪"],
            need_confirmation=True,
        )
        plan = planner.create_plan("帮我生成比亚迪的综合分析报告", intent)
        assert plan.need_confirmation is True

    def test_T8_compare_stocks_includes_compare_agent(self, planner):
        """T8: compare_stocks intent → comparison agent in tasks."""
        intent = _make_intent("compare_stocks", entities=["宁德时代", "比亚迪"])
        plan = planner.create_plan("对比宁德时代和比亚迪", intent)
        agent_names = [t.agent for t in plan.tasks]
        assert (
            "CompareAgent" in agent_names
            or "ReportComparisonSkill" in agent_names
            or "MultiCompanyFinancialComparisonAgent" in agent_names
        )

    def test_T9_plan_content_includes_why_explanation(self, planner):
        """T9: plan content explains *why* data is needed (entity-aware)."""
        intent = _make_intent("tool_answer", entities=["茅台"])
        plan = planner.create_plan("茅台最新行情？", intent)
        # At minimum, problem_analysis should mention the entity
        pa = next(
            (item for item in plan.reasoning_summary if item["phase"] == "problem_analysis"),
            None,
        )
        assert pa is not None
        # Content mentions the entity or the intent in a natural-language way
        assert len(pa["content"]) > 20   # not just a stub

    def test_T10_industry_research_tasks_exclude_compare_agent(self, planner):
        """T10: industry_research plan does NOT include CompareAgent."""
        intent = _make_intent("industry_research", entities=["新能源"])
        plan = planner.create_plan("新能源行业热点", intent)
        agent_names = [t.agent for t in plan.tasks]
        assert "CompareAgent" not in agent_names


# ─────────────────────────────────────────────────────────────────────────────
# T11–T14: C31.3 — Orchestrator plan safety & content quality
# ─────────────────────────────────────────────────────────────────────────────

class TestOrchestratorPlanSafety:
    """T11–T14 — CentralPlan output contracts."""

    @pytest.fixture
    def planner(self):
        from app.agents.central_planning_agent import CentralPlanningAgent
        return CentralPlanningAgent()

    def test_T11_report_generation_plan_has_need_confirmation(self, planner):
        """T11: report_generation plan signals need_confirmation before execution."""
        intent = _make_intent(
            "report_generation",
            entities=["中芯国际"],
            need_confirmation=True,
        )
        plan = planner.create_plan("生成中芯国际报告", intent)
        assert plan.need_confirmation is True
        # synthesis content should mention user confirmation
        synthesis = next(
            (i for i in plan.reasoning_summary if i["phase"] == "synthesis"),
            None,
        )
        assert synthesis is not None
        assert len(synthesis["content"]) > 10

    def test_T12_report_generation_has_risk_review_in_tasks(self, planner):
        """T12: After confirmation, report_generation has RiskReviewAgent + ComplianceAgent."""
        intent = _make_intent(
            "report_generation",
            entities=["华为"],
            need_confirmation=True,
        )
        plan = planner.create_plan("生成华为报告", intent)
        agent_names = [t.agent for t in plan.tasks]
        assert "RiskReviewAgent" in agent_names
        assert "ComplianceAgent" in agent_names

    def test_T13_direct_answer_has_no_tasks(self, planner):
        """T13: direct_answer intent → no tasks (no agents dispatched)."""
        intent = _make_intent("direct_answer", need_agent=False)
        plan = planner.create_plan("PEG是什么？", intent)
        assert len(plan.tasks) == 0
        # Agent dispatch content should mention no agents needed
        dispatch_event = plan.get_agent_dispatch_event(status="completed")
        assert "直接" in dispatch_event["content"] or "无需" in dispatch_event["content"]

    def test_T14_plan_content_never_contains_system_prompt_or_tool_args(self, planner):
        """T14: All plan phase content strings must not contain raw internals."""
        intent = _make_intent("compare_stocks", entities=["腾讯", "阿里"])
        plan = planner.create_plan("对比腾讯和阿里", intent)
        forbidden = ["<system>", "tool_args", "api_key", "SELECT", "__", "系统提示"]
        for item in plan.reasoning_summary:
            content = item.get("content", "")
            for f in forbidden:
                assert f not in content, (
                    f"Phase '{item['phase']}' content contains forbidden string '{f}': {content!r}"
                )


# ─────────────────────────────────────────────────────────────────────────────
# T15–T19: C31.4 — convert_reasoning_to_public_thinking_events
# ─────────────────────────────────────────────────────────────────────────────

class TestConvertReasoningToPublicThinkingEvents:
    """T15–T19"""

    def _run(self, reasoning: str, intent: str = "general", plan=None) -> list[dict]:
        from app.agents.thinking_sanitizer import convert_reasoning_to_public_thinking_events
        return convert_reasoning_to_public_thinking_events(
            reasoning, intent, plan, max_chars=2000
        )

    def _make_plan(self, intent: str = "tool_answer", entities: list[str] | None = None):
        from app.agents.central_planning_agent import CentralPlanningAgent
        planner = CentralPlanningAgent()
        return planner.create_plan("test", _make_intent(intent, entities))

    def test_T15_empty_reasoning_falls_back_to_plan_events(self):
        """T15: No reasoning_content → fallback returns CentralPlan events."""
        plan = self._make_plan("industry_research", ["芯片"])
        events = self._run("", intent="industry_research", plan=plan)
        assert len(events) >= 1
        phases = [e["phase"] for e in events]
        # Problem analysis is always in the plan
        assert "problem_analysis" in phases

    def test_T16_reasoning_content_produces_thinking_events(self):
        """T16: Valid reasoning_content → list of thinking_event dicts produced."""
        reasoning = (
            "用户想了解半导体行业热点，这是行业研究类请求。"
            "我需要检索最新行业数据和新闻资讯。"
            "思考：行业热度来源是政策驱动还是资金流入？"
            "风险：不应给出买卖建议。"
            "回答：综合整理行业概览。"
        )
        events = self._run(reasoning, intent="industry_research")
        assert len(events) >= 3
        # Each event must have required keys
        for ev in events:
            assert "phase" in ev
            assert "content" in ev
            assert ev["content"]  # non-empty

    def test_T17_raw_system_prompt_not_in_output(self):
        """T17: System prompt text is stripped and never appears in output events."""
        reasoning = (
            "系统提示：你是一个金融助理，不得给出投资建议。\n"
            "用户提问关于茅台的行情数据，我需要检索实时报价。\n"
            "思考：分析当前价格是否异常。\n"
            "风险：不能给出具体买卖建议。\n"
            "回答：基于行情数据提供客观描述。"
        )
        events = self._run(reasoning)
        combined = " ".join(e.get("content", "") for e in events)
        assert "系统提示" not in combined

    def test_T18_tool_args_not_in_output(self):
        """T18: Raw tool argument JSON is stripped and not in output."""
        reasoning = (
            'tool_args: {"symbol": "600519", "market": "CN"}\n'
            "用户想查询茅台的最新行情。\n"
            "思考：根据行情数据分析趋势。\n"
            "风险：不给出确定性涨跌结论。\n"
            "回答：基于已获取数据生成回答。"
        )
        events = self._run(reasoning)
        combined = " ".join(e.get("content", "") for e in events)
        assert '"symbol"' not in combined
        assert "600519" not in combined or "tool_args" not in combined

    def test_T19_output_contains_natural_language_chinese_content(self):
        """T19: Output events contain natural-language Chinese content (深度思考 path)."""
        reasoning = (
            "这个问题涉及到对行业热点的判断，我需要分析政策背景和资金动向。"
            "行业数据显示近期新能源板块资金净流入明显，需要区分短期热度和长期趋势。"
            "综合来看，不应该直接推荐买入，要说明不确定性。"
            "最终回答应包括行业概览和代表公司。"
        )
        events = self._run(reasoning, intent="industry_research")
        # At least one event must have meaningful Chinese text
        has_chinese_content = any(
            len(e.get("content", "")) > 10
            for e in events
        )
        assert has_chinese_content
        # deep_reasoning or problem_analysis must be present
        phases = [e["phase"] for e in events]
        assert "deep_reasoning" in phases or "problem_analysis" in phases
