"""
C30.2 Tests: Report Repository + Intent Routing + P3 Constraints.

T1-T5:   ReportRepository single data source contract
T6-T12:  IntentDecisionAgent routing (C30.2.3)
T13-T16: P3 completed condition constraints (C30.2.4)
T17-T21: User-visible Run ID elimination (C30.2.5)
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_uid(suffix: int = 42) -> uuid.UUID:
    return uuid.UUID(f"00000000-0000-0000-0000-{suffix:012d}")


def _make_db():
    return AsyncMock()


def _frontend_card_path() -> Path:
    card_path = (
        Path(__file__).resolve().parents[2]
        / "frontend"
        / "src"
        / "components"
        / "chat"
        / "ChatResultCard.vue"
    )
    assert card_path.exists(), f"missing frontend component file: {card_path}"
    return card_path


# ══════════════════════════════════════════════════════════════════════════════
# T1-T5: ReportRepository data source contract
# ══════════════════════════════════════════════════════════════════════════════

class TestReportRepositoryContract:
    """Verify ReportRepository exposes the four expected operations."""

    def test_t1_repository_has_create_report(self):
        """T1: ReportRepository.create_report exists and is async."""
        from app.repositories.report_repository import ReportRepository
        import inspect
        assert hasattr(ReportRepository, "create_report")
        assert inspect.iscoroutinefunction(ReportRepository.create_report)

    def test_t2_repository_has_get_report(self):
        """T2: ReportRepository.get_report exists and is async."""
        from app.repositories.report_repository import ReportRepository
        import inspect
        assert hasattr(ReportRepository, "get_report")
        assert inspect.iscoroutinefunction(ReportRepository.get_report)

    def test_t3_repository_has_list_reports(self):
        """T3: ReportRepository.list_reports exists and is async."""
        from app.repositories.report_repository import ReportRepository
        import inspect
        assert hasattr(ReportRepository, "list_reports")
        assert inspect.iscoroutinefunction(ReportRepository.list_reports)

    def test_t4_repository_has_delete_report(self):
        """T4: ReportRepository.delete_report exists and is async."""
        from app.repositories.report_repository import ReportRepository
        import inspect
        assert hasattr(ReportRepository, "delete_report")
        assert inspect.iscoroutinefunction(ReportRepository.delete_report)

    def test_t5_save_generated_report_uses_repository(self):
        """T5: save_generated_report calls ReportRepository, not raw AnalysisReport ORM."""
        import inspect
        import app.agents.report_persistence as rp
        src = inspect.getsource(rp)
        # Must use repository, not raw AnalysisReport construction
        assert "ReportRepository" in src
        assert "repo.create_report" in src
        # Must NOT directly construct AnalysisReport (repository handles that)
        assert "AnalysisReport(" not in src

    def test_t5b_reports_router_uses_repository(self):
        """T5b: reports.py router uses ReportRepository for list/get/delete."""
        import inspect
        import app.routers.reports as rr
        src = inspect.getsource(rr)
        assert "ReportRepository" in src
        assert "repo.create_report" in src
        assert "repo.list_reports" in src
        assert "repo.get_report" in src
        assert "repo.delete_report" in src


# ══════════════════════════════════════════════════════════════════════════════
# T6-T12: IntentDecisionAgent routing (C30.2.3)
# ══════════════════════════════════════════════════════════════════════════════

class TestIntentDecisionRouting:

    @pytest.mark.asyncio
    async def test_t6_direct_analysis_no_report_confirmation(self):
        """T6: '帮我分析贵州茅台的基本面' → no confirmation card (direct Q&A)."""
        from app.agents.chat_orchestrator import process_message

        result = await process_message(
            "帮我分析贵州茅台的基本面",
            _make_db(),
            _make_uid(),
        )
        # Must NOT return a confirmation card (that would start a 30s pipeline)
        assert result.confirmation is None, (
            "Plain analysis question must NOT trigger report-generation confirmation. "
            f"Got confirmation: {result.confirmation}"
        )

    @pytest.mark.asyncio
    async def test_t7_generate_report_shows_confirmation(self):
        """T7: '生成贵州茅台综合报告' → confirmation card for report generation."""
        from app.agents.chat_orchestrator import process_message

        result = await process_message(
            "生成贵州茅台综合报告",
            _make_db(),
            _make_uid(),
        )
        assert result.confirmation is not None, (
            "Explicit report generation request must produce a confirmation card."
        )
        assert result.confirmation.get("type") == "create_analysis_run"

    @pytest.mark.asyncio
    async def test_t8_save_to_history_shows_confirmation_with_flag(self):
        """T8: '分析688146并保存到历史报告' → confirmation, save_to_history=True."""
        from app.agents.chat_orchestrator import process_message

        result = await process_message(
            "分析688146并保存到历史报告",
            _make_db(),
            _make_uid(),
        )
        assert result.confirmation is not None
        params = result.confirmation.get("params", {})
        assert params.get("save_to_history") is True, (
            "Explicit save-to-history request must set save_to_history=True"
        )

    def test_t9_industry_query_not_compare_intent(self):
        """T9: '最近哪些行业比较火' → industry_research, NOT compare_stocks."""
        from app.agents.intent_decision_agent import classify_intent
        d = classify_intent("最近哪些行业比较火？该行业最有前景的几家公司是哪些？")
        assert d.intent == "industry_research", f"Expected industry_research, got {d.intent}"
        assert d.intent != "compare_stocks"

    def test_t10_explicit_compare_triggers_compare(self):
        """T10: '对比宁德时代、紫金矿业、华大九天' → compare_stocks intent."""
        from app.agents.intent_decision_agent import classify_intent
        d = classify_intent("对比宁德时代、紫金矿业、华大九天")
        assert d.intent == "compare_stocks", f"Expected compare_stocks, got {d.intent}"

    def test_t11_historical_report_read_intent(self):
        """T11: '帮我读6.11茅台报告' → historical_report_read intent."""
        from app.agents.intent_decision_agent import classify_intent
        d = classify_intent("帮我读6.11茅台报告")
        assert d.intent == "historical_report_read", f"Expected historical_report_read, got {d.intent}"

    @pytest.mark.asyncio
    async def test_t12_watchlist_query_not_blocked_by_direct_answer(self):
        """T12: '查看自选股' routes to watchlist view even if direct_answer-ish."""
        from app.agents.chat_orchestrator import process_message

        result = await process_message(
            "查看自选股",
            _make_db(),
            _make_uid(),
        )
        # Should get a real answer (not blocked or empty)
        assert result.answer, "watchlist query should produce an answer"
        # Should NOT produce a report confirmation card
        assert result.confirmation is None or result.confirmation.get("type") != "create_analysis_run"

    @pytest.mark.asyncio
    async def test_t12b_general_question_goes_to_skill(self):
        """T12b: Generic financial Q&A reaches SkillRegistry without report confirmation."""
        from app.agents.chat_orchestrator import process_message

        result = await process_message(
            "什么是市盈率？",
            _make_db(),
            _make_uid(),
        )
        # Pure Q&A — no confirmation card
        assert result.confirmation is None, (
            "General financial Q&A must NOT produce a confirmation card."
        )
        # Should have an answer
        assert result.answer


# ══════════════════════════════════════════════════════════════════════════════
# T13-T16: P3 completed condition constraint (C30.2.4)
# ══════════════════════════════════════════════════════════════════════════════

class TestP3CompletedConstraint:

    def test_t13_both_runners_save_before_completed(self):
        """T13: Both runners call save_generated_report before update_status('completed')."""
        import inspect
        import app.agents.realtime_analysis_runner as rar
        import app.agents.langgraph_realtime_runner as lgr

        for mod, name in [(rar, "realtime_analysis_runner"), (lgr, "langgraph_realtime_runner")]:
            src = inspect.getsource(mod)
            # save_generated_report must appear before update_status("completed")
            save_pos = src.find("save_generated_report")
            completed_pos = src.find('"completed"')
            assert save_pos > 0, f"{name}: save_generated_report not found"
            assert completed_pos > 0, f"{name}: update_status('completed') not found"
            assert save_pos < completed_pos, (
                f"{name}: save_generated_report must appear before update_status('completed')"
            )

    def test_t14_failed_persistence_becomes_failed_status(self):
        """T14: If save_generated_report returns None, status is set to 'failed', not 'completed'."""
        import inspect
        import app.agents.realtime_analysis_runner as rar
        import app.agents.langgraph_realtime_runner as lgr

        for mod, name in [(rar, "realtime_analysis_runner"), (lgr, "langgraph_realtime_runner")]:
            src = inspect.getsource(mod)
            # After save_generated_report, there must be a None check → failed
            assert 'report_id is None' in src or 'if report_id is None' in src, (
                f"{name}: must check report_id is None and set status to 'failed'"
            )
            assert '"failed"' in src, f"{name}: must set status to 'failed' on persistence error"

    def test_t15_frontend_card_shows_hint_for_no_report_id(self):
        """T15: ChatResultCard shows hint text (not 'view report') when completed + no report_id."""
        import re
        card_path = _frontend_card_path()
        with open(card_path, encoding="utf-8") as f:
            src = f.read()
        # Must have hint for completed-without-report-id case
        assert "hasDirectReportLink" in src, "ChatResultCard must check hasDirectReportLink"
        assert "报告生成完成，但暂未获取到报告链接" in src, (
            "ChatResultCard must show hint text when completed but no report link"
        )

    def test_t16_run_id_not_in_failed_card_hint(self):
        """T16: The failed card hint must NOT mention 'Run ID' or raw run_id."""
        card_path = _frontend_card_path()
        with open(card_path, encoding="utf-8") as f:
            src = f.read()
        # The error hint text must not expose run_id
        hint_match = re.search(r'rc-run-hint--error.*?</p>', src, re.DOTALL)
        if hint_match:
            hint_text = hint_match.group(0)
            assert "run_id" not in hint_text.lower(), "Error hint must not show run_id"
            assert "Run ID" not in hint_text, "Error hint must not show 'Run ID'"


# ══════════════════════════════════════════════════════════════════════════════
# T17-T21: User-visible Run ID elimination (C30.2.5)
# ══════════════════════════════════════════════════════════════════════════════

class TestRunIdElimination:

    def test_t17_action_tools_answer_has_no_run_id(self):
        """T17: execute_create_analysis_run answer must NOT contain 'Run ID' text."""
        import inspect
        import app.agents.chat_tools.action_tools as at
        src = inspect.getsource(at)
        # Check that the old "Run ID：`{run_ref.run_id}`" pattern is gone
        assert "Run ID：`{run_ref.run_id}`" not in src, (
            "User-visible answer must not expose 'Run ID：`{run_ref.run_id}`'"
        )

    def test_t18_answer_source_has_no_run_id_label(self):
        """T18: execute_create_analysis_run answer source must not contain 'Run ID：`{...}`'."""
        import inspect
        import app.agents.chat_tools.action_tools as at
        src = inspect.getsource(at)
        # The old offending line: f"Run ID：`{run_ref.run_id}`。"
        assert "Run ID：" not in src, (
            "User-visible answer must not contain 'Run ID：' label"
        )

    def test_t19_analysis_run_card_template_has_no_run_id_display(self):
        """T19: ChatResultCard analysis_run template must not render run_id to users."""
        card_path = _frontend_card_path()
        with open(card_path, encoding="utf-8") as f:
            src = f.read()
        # The template section for analysis_run must not display card.data.run_id as text
        # (it can store it as data but not render it in visible text)
        template_match = src.find('<template v-else-if="card.type === \'analysis_run\'">')
        end_match = src.find('</template>', template_match + 1)
        if template_match > 0 and end_match > 0:
            template_src = src[template_match:end_match]
            # run_id must not appear in visible text nodes
            assert "{{ card.data.run_id }}" not in template_src, (
                "analysis_run card must not render run_id as visible text"
            )

    def test_t20_action_tool_events_have_no_run_id_label(self):
        """T20: tool_events detail string must not say 'run_id=...' to the user."""
        import inspect
        import app.agents.chat_tools.action_tools as at
        src = inspect.getsource(at)
        # Old pattern was: f"... 分析已提交（run_id={run_ref.run_id}..."
        # New pattern should not expose raw run_id in the detail string shown to users
        # (debug info in logs is OK; tool_event detail goes to ChatToolTrace which may be visible)
        # We check the specific old pattern is removed
        assert "run_id={run_ref.run_id}" not in src, (
            "tool_event detail must not expose raw run_id pattern"
        )

    def test_t21_debug_metadata_still_has_run_id(self):
        """T21: Internal metadata / SSE events may still carry run_id for debugging."""
        import inspect
        import app.agents.realtime_analysis_runner as rar
        src = inspect.getsource(rar)
        # run_id should appear in log/internal fields, not stripped from backend entirely
        assert "run_id" in src, "Backend must still track run_id internally for debugging"
        assert "run_ref.run_id" in src
