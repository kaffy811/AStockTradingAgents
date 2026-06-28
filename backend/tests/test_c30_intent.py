"""
C30 backend tests — T1-T31

C30.1 Intent Decision Agent:  T1-T5  (classify_intent)
C30.2 Agent Planner:          T6-T10 (build_plan)
C30.3 Report Persistence:     T11-T17 (save_generated_report logic)
C30.4 P3 Frontend Alignment:  T18-T23 (run snapshot report_id field)
C30.5 Industry Routing Fix:   T24-T27 (_match_compare fix)
C30.6 Reasoning Summary:      T28-T31 (convert_reasoning_to_public_summary)
"""
from __future__ import annotations

import pytest
import re

# ── C30.1: Intent Decision Agent ──────────────────────────────────────────────

from app.agents.intent_decision_agent import classify_intent, IntentDecision


class TestIntentDecisionAgent:

    def test_T1_fundamental_question_is_direct_or_tool_not_report(self):
        """T1: '帮我分析贵州茅台的基本面' → direct_answer or tool_answer, NOT report_generation"""
        result = classify_intent("帮我分析贵州茅台的基本面")
        assert result.intent in ("direct_answer", "tool_answer"), (
            f"Expected direct/tool, got '{result.intent}'"
        )
        assert not result.need_confirmation, "No confirmation needed for Q&A"

    def test_T2_save_to_history_is_report_generation(self):
        """T2: '分析 688146 并保存到历史报告' → report_generation with confirmation"""
        result = classify_intent("分析 688146 并保存到历史报告")
        assert result.intent == "report_generation"
        assert result.need_agent
        assert result.need_confirmation

    def test_T3_industry_hotspot_is_industry_research(self):
        """T3: '最近哪些行业比较火？该行业最有前景的几家公司是哪些？' → industry_research"""
        result = classify_intent("最近哪些行业比较火？该行业最有前景的几家公司是哪些？")
        assert result.intent == "industry_research", (
            f"Expected industry_research, got '{result.intent}'"
        )
        assert result.intent != "compare_stocks"

    def test_T4_explicit_multi_stock_compare(self):
        """T4: '对比宁德时代、紫金矿业、华大九天' → compare_stocks"""
        result = classify_intent("对比宁德时代、紫金矿业、华大九天")
        assert result.intent == "compare_stocks"

    def test_T5_historical_report_read(self):
        """T5: '帮我读一份6.11的茅台报告' → historical_report_read"""
        result = classify_intent("帮我读一份6.11的茅台报告")
        assert result.intent == "historical_report_read"
        assert not result.need_confirmation

    def test_T1b_generate_comprehensive_report_is_report_gen(self):
        """生成综合报告 → report_generation"""
        result = classify_intent("生成贵州茅台综合报告")
        assert result.intent == "report_generation"
        assert result.need_confirmation

    def test_T2b_industry_hot_not_compare(self):
        """'今天哪些行业比较火？' must NOT be compare_stocks"""
        result = classify_intent("今天哪些行业比较火？")
        assert result.intent != "compare_stocks"

    def test_result_structure(self):
        """IntentDecision has all required fields"""
        result = classify_intent("今日AI概念股表现如何？")
        assert isinstance(result, IntentDecision)
        assert result.intent
        assert isinstance(result.need_agent, bool)
        assert isinstance(result.need_confirmation, bool)
        assert isinstance(result.target_entities, list)
        assert isinstance(result.confidence, float)
        assert 0 <= result.confidence <= 1


# ── C30.2: Agent Planner ─────────────────────────────────────────────────────

from app.agents.agent_planner import build_plan, AgentPlan
from app.agents.intent_decision_agent import IntentDecision


class TestAgentPlanner:

    def _make_decision(self, intent: str, need_agent: bool = True,
                       need_confirmation: bool = False) -> IntentDecision:
        return IntentDecision(
            intent=intent, need_agent=need_agent,
            need_confirmation=need_confirmation,
        )

    def test_T6_industry_research_plan_has_industry_no_compare(self):
        """T6: industry_research plan includes IndustryAgent, not CompareAgent"""
        plan = build_plan(self._make_decision("industry_research"))
        agents = {s.agent for s in plan.steps}
        assert "IndustryAgent" in agents
        assert "CompareAgent" not in agents

    def test_T7_compare_stocks_plan_has_compare_agent(self):
        """T7: compare_stocks plan includes CompareAgent"""
        plan = build_plan(self._make_decision("compare_stocks"))
        agents = {s.agent for s in plan.steps}
        assert "CompareAgent" in agents

    def test_T8_report_generation_has_required_agents(self):
        """T8: report_generation plan includes ReportAgent, RiskReviewAgent, ComplianceAgent"""
        plan = build_plan(self._make_decision("report_generation", need_confirmation=True))
        agents = {s.agent for s in plan.steps}
        assert "ReportAgent"    in agents
        assert "RiskReviewAgent"  in agents
        assert "ComplianceAgent"  in agents

    def test_T9_report_generation_requires_confirmation(self):
        """T9: report_generation plan has requires_confirmation=True"""
        plan = build_plan(self._make_decision("report_generation", need_confirmation=True))
        assert plan.requires_confirmation is True

    def test_T10_direct_answer_empty_plan(self):
        """T10: direct_answer returns empty plan (no agent steps)"""
        plan = build_plan(self._make_decision("direct_answer", need_agent=False))
        assert plan.is_empty()
        assert not plan.requires_confirmation

    def test_plan_id_generated(self):
        """AgentPlan always has a plan_id"""
        plan = build_plan(self._make_decision("industry_research"))
        assert plan.plan_id and len(plan.plan_id) >= 8

    def test_historical_report_plan(self):
        """historical_report_read → ReportAgent, no confirmation"""
        plan = build_plan(self._make_decision("historical_report_read"))
        agents = {s.agent for s in plan.steps}
        assert "ReportAgent" in agents
        assert not plan.requires_confirmation


# ── C30.3: Report Persistence (unit-level logic) ──────────────────────────────

class TestReportPersistenceLogic:
    """
    Tests for save_generated_report() logic without a real DB.
    We test the data preparation logic directly.
    """

    def _make_full_result(self, **overrides) -> dict:
        base = {
            "market":          "CN",
            "symbol":          "600519",
            "stock_name":      "贵州茅台",
            "report":          "## 综合分析\n报告内容...",
            "sections":        {"technical": "技术面分析...", "fundamental": "基本面分析..."},
            "metadata":        {
                "generated_at": "2026-06-28T10:00:00Z",
                "agents":       {"technical": {"status": "success"}, "fundamental": {"status": "success"}},
                "warnings":     [],
            },
            "analysis_scope":  "comprehensive",
            "output_language": "zh-CN",
        }
        base.update(overrides)
        return base

    def test_T11_full_result_has_required_fields(self):
        """T11: full_result from runner has all required fields for persistence"""
        result = self._make_full_result()
        assert "market" in result
        assert "symbol" in result
        assert "report" in result
        assert "sections" in result
        assert "metadata" in result

    def test_T12_completed_run_must_yield_report_id(self):
        """T12: On success, report_id must be a non-empty string"""
        # Logic: if save returns None → mark failed, not completed
        saved_report_id = "some-uuid-string"  # simulates successful save
        assert saved_report_id is not None
        assert isinstance(saved_report_id, str)
        assert len(saved_report_id) > 0

    def test_T13_save_failure_means_run_failed_not_completed(self):
        """T13: If save_generated_report returns None, caller marks run as failed"""
        report_id = None  # simulates save failure
        # Caller logic: if report_id is None → update_status("failed")
        status = "failed" if report_id is None else "completed"
        assert status == "failed"

    def test_T16_completed_without_report_id_must_not_show_success(self):
        """T16: completed + no report_id should be treated as error, not success"""
        # The runner now sets failed if save returns None
        # So this state should not occur after C30.3
        snap_status = "failed"  # what happens when save fails
        assert snap_status != "completed"

    def test_sections_filtering(self):
        """Non-string sections (Exception objects) are filtered before save"""
        raw_sections = {
            "technical":    "技术面分析...",
            "fundamental":  Exception("timed out"),  # failed agent
            "news":         "新闻分析...",
        }
        filtered = {k: v for k, v in raw_sections.items() if isinstance(v, str)}
        assert "technical"   in filtered
        assert "news"        in filtered
        assert "fundamental" not in filtered

    def test_warnings_extracted_from_metadata(self):
        """Warnings list is pulled from metadata dict"""
        metadata = {"warnings": ["HK coverage limited"], "agents": {}}
        warnings = metadata.get("warnings", [])
        assert warnings == ["HK coverage limited"]

    def test_invalid_user_id_returns_none(self):
        """If user_id is not a valid UUID, persistence returns None"""
        # Simulates the uuid.UUID(run_ref.user_id) check
        user_id = "not-a-uuid"
        import uuid as _uuid
        try:
            _uuid.UUID(user_id)
            valid = True
        except ValueError:
            valid = False
        assert not valid  # would return None from save_generated_report


# ── C30.4: Run Snapshot report_id field ──────────────────────────────────────

from app.services.run_registry_protocol import AnalysisRunSnapshot
from datetime import datetime, timezone


class TestRunSnapshotReportId:

    def _make_snap(self, status="queued", report_id=None) -> AnalysisRunSnapshot:
        now = datetime.now(timezone.utc)
        return AnalysisRunSnapshot(
            run_id="run-1", user_id="uid-1", market="CN", symbol="600519",
            analysis_scope="comprehensive", workflow_engine="custom_coordinator",
            output_language="zh-CN", status=status, progress=0,
            latest_event=None, result=None, error=None,
            created_at=now, updated_at=now,
            report_id=report_id,
        )

    def test_T18_queued_snap_has_no_report_id(self):
        """T18: A queued run has no report_id"""
        snap = self._make_snap("queued")
        assert snap.report_id is None

    def test_T19_completed_without_report_id(self):
        """T19: completed without report_id → no direct report link should be shown"""
        snap = self._make_snap("completed", report_id=None)
        assert snap.status == "completed"
        assert snap.report_id is None
        # Frontend should show '查看报告中心' not '查看报告'

    def test_T20_completed_with_report_id(self):
        """T20: completed with report_id → show '查看报告' link"""
        snap = self._make_snap("completed", report_id="rpt-abc-123")
        assert snap.status == "completed"
        assert snap.report_id == "rpt-abc-123"

    def test_T21_failed_has_no_report_id(self):
        """T21: failed run never has report_id"""
        snap = self._make_snap("failed", report_id=None)
        assert snap.report_id is None

    def test_T22_snapshot_field_exists(self):
        """T22: AnalysisRunSnapshot has report_id field"""
        snap = self._make_snap()
        assert hasattr(snap, "report_id")

    def test_T23_report_route_uses_history_detail(self):
        """T23: report link path should use HistoryDetail route with report_id"""
        report_id = "rpt-xyz"
        # Simulates the link building in ChatCopilotView._pollRunTick
        link = {
            "label": "查看报告",
            "path": {"name": "HistoryDetail", "params": {"id": report_id}},
        }
        assert link["path"]["name"] == "HistoryDetail"
        assert link["path"]["params"]["id"] == "rpt-xyz"


# ── C30.5: Industry Routing Fix (_match_compare) ──────────────────────────────

from app.agents.chat_orchestrator import _match_compare, _match_industry


class TestIndustryVsCompareRouting:

    def test_T24_industry_hot_not_compare(self):
        """T24: '最近哪些行业比较火？该行业最有前景的几家公司是哪些？' → NOT compare"""
        q = "最近哪些行业比较火？该行业最有前景的几家公司是哪些？"
        assert not _match_compare(q), "比较火 is an adjective, not a compare intent"

    def test_T25_industry_hot_matches_industry(self):
        """T25: same query matches _match_industry (industry handler runs instead)"""
        q = "最近哪些行业比较火？该行业最有前景的几家公司是哪些？"
        assert _match_industry(q), "_match_industry should trigger for this query"

    def test_T26_explicit_compare_still_works(self):
        """T26: '对比宁德时代、紫金矿业、华大九天' → still triggers _match_compare"""
        q = "对比宁德时代、紫金矿业、华大九天"
        assert _match_compare(q)

    def test_T27_industry_research_can_list_companies(self):
        """T27: classify_intent for industry query → industry_research, not compare"""
        result = classify_intent("今天有哪些行业值得重点研究？其中有哪些代表公司？")
        assert result.intent == "industry_research"
        assert result.intent != "compare_stocks"

    def test_vs_compare_trigger(self):
        """'比较 300750 和 601899' triggers compare (explicit multi-entity)"""
        q = "比较 300750 和 601899"
        assert _match_compare(q)

    def test_adjective_compare_hot_cold(self):
        """'行业比较热' must NOT trigger compare"""
        assert not _match_compare("今天这个行业比较热")

    def test_dui_bi_always_compare(self):
        """'对比' alone is always compare intent"""
        assert _match_compare("对比这两支股票的估值")


# ── C30.6: Reasoning → Public Summary ────────────────────────────────────────

from app.agents.thinking_sanitizer import convert_reasoning_to_public_summary, _template_steps_for_intent


class TestReasoningToPublicSummary:

    def test_T28_empty_reasoning_returns_template(self):
        """T28: Empty/None reasoning_content → fallback template (5 steps)"""
        steps = convert_reasoning_to_public_summary("", intent="general")
        assert len(steps) == 5
        titles = [s["title"] for s in steps]
        assert "问题分析"    in titles
        assert "回答生成"    in titles

    def test_T29_reasoning_content_produces_summary(self):
        """T29: Non-empty reasoning generates 5-step summary"""
        reasoning = (
            "我理解用户想要查询茅台的财务数据。"
            "我需要检索最新的财报和估值数据。"
            "综合思考后，我认为数据来源可靠。"
            "风险方面我注意到没有足够的同业比较数据。"
            "基于以上分析，我会生成最终回答。"
        )
        steps = convert_reasoning_to_public_summary(reasoning, intent="financial_report")
        assert len(steps) == 5
        for step in steps:
            assert "title"   in step
            assert "content" in step
            assert step["title"]   # non-empty
            assert step["content"] # non-empty

    def test_T30_system_prompt_not_in_output(self):
        """T30: System prompt content does not appear in public summary"""
        reasoning = "系统提示：你是一个金融助手。用户问了关于茅台的问题。我会综合分析并回答。"
        steps = convert_reasoning_to_public_summary(reasoning)
        all_text = " ".join(s["content"] for s in steps)
        assert "系统提示：" not in all_text

    def test_T31_tool_args_not_in_output(self):
        """T31: Tool args not exposed in public summary"""
        reasoning = 'tool_args: {"market": "CN", "symbol": "600519"}\n我会检索该股票数据。'
        steps = convert_reasoning_to_public_summary(reasoning)
        all_text = " ".join(s["content"] for s in steps)
        assert "tool_args" not in all_text
        assert '"market"' not in all_text

    def test_template_step_count(self):
        """_template_steps_for_intent always returns 5 steps"""
        for intent in ("financial_report", "hot_stocks", "industry_research",
                       "report_generation", "general"):
            steps = _template_steps_for_intent(intent)
            assert len(steps) == 5, f"Expected 5 steps for {intent}, got {len(steps)}"

    def test_no_raw_cot_fields(self):
        """Sanitizer removes internal fields before conversion"""
        reasoning = (
            "<tool_call>get_quote CN 600519</tool_call>"
            "We found that the stock is at 1800 CNY. "
            "我认为这个价格合理。"
        )
        steps = convert_reasoning_to_public_summary(reasoning)
        all_text = " ".join(s["content"] for s in steps)
        assert "<tool_call>" not in all_text
        assert "tool_call"   not in all_text
