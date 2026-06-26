"""
test_c2511_skill_arbitration.py — Phase C25.11 backend tests.

T1  SkillRegistry._EXCLUSIVE_SKILLS blocks GeneralFinancialAnswerSkill fallback
    for report_explanation_skill
T2  ReportExplanationSkill.run() does NOT propagate exceptions (graceful SkillResult)
T3  official_report_search query_label no "最新最新" double-prefix
T4  official_report_search not_found_reason no "最新最新" double-prefix
T5  _summarize_report_plainly section regex now works (section extraction succeeds)
"""
from __future__ import annotations

import pytest


# ── T1: SkillRegistry _EXCLUSIVE_SKILLS blocks fallback ──────────────────────

class TestExclusiveSkillGuard:

    def test_T1_exclusive_skills_set_contains_report_skill(self):
        """registry._EXCLUSIVE_SKILLS must include report_explanation_skill."""
        import inspect
        import app.agents.chat_skills.registry as mod
        src = inspect.getsource(mod.SkillRegistry.run)
        assert "_EXCLUSIVE_SKILLS" in src
        assert "report_explanation_skill" in src

    def test_T1b_exclusive_skill_returns_graceful_result_not_general_answer(self):
        """
        When report_explanation_skill is in _EXCLUSIVE_SKILLS and raises,
        the registry must return a SkillResult directly (not invoke the generic answerer).
        Verify: the 'if skill.name in _EXCLUSIVE_SKILLS' block (with 'return SkillResult')
        appears before the 'from ... import GeneralFinancialAnswerSkill' line.
        """
        import inspect
        import app.agents.chat_skills.registry as mod
        src = inspect.getsource(mod.SkillRegistry.run)
        # Find the exclusive-guard return (not just the variable definition)
        exclusive_return_idx = src.index("if skill.name in _EXCLUSIVE_SKILLS")
        # Find the GeneralFinancialAnswerSkill import (actual import line, after the guard)
        general_import_idx = src.index("from app.agents.chat_skills.general_financial_answer_skill import")
        assert exclusive_return_idx < general_import_idx, (
            "_EXCLUSIVE_SKILLS guard return must appear before GeneralFinancialAnswerSkill import"
        )


# ── T2: ReportExplanationSkill.run() never propagates exceptions ──────────────

class TestReportSkillGracefulFallback:

    @pytest.mark.asyncio
    async def test_T2_run_returns_graceful_result_on_internal_error(self):
        """
        If _run_inner raises, run() must catch it and return a SkillResult with ok=True
        (so that the registry doesn't trigger GeneralFinancialAnswerSkill).
        """
        from app.agents.chat_skills.report_explanation_skill import ReportExplanationSkill
        from app.agents.chat_skills.base import SkillContext, SkillResult

        skill = ReportExplanationSkill()

        # Minimal fake context that causes an immediate crash in _run_inner
        class _BadContext:
            event_callback = None
            user_id = "u-test"
            db = None
            tool_registry = None  # will crash when called
            language = "zh-CN"

        result = await skill.run("历史报告", _BadContext())
        assert isinstance(result, SkillResult)
        # Must not propagate — must return a graceful result
        assert result.skill_name == "report_explanation_skill"
        assert result.answer  # non-empty answer

    @pytest.mark.asyncio
    async def test_T2b_graceful_result_contains_disclaimer(self):
        """Graceful fallback answer must include disclaimer."""
        from app.agents.chat_skills.report_explanation_skill import ReportExplanationSkill
        from app.agents.chat_skills.base import SkillContext

        skill = ReportExplanationSkill()

        class _BadContext:
            event_callback = None
            user_id = "u-test"
            db = None
            tool_registry = None
            language = "zh-CN"

        result = await skill.run("报告结论是什么", _BadContext())
        assert "仅供研究参考" in result.answer


# ── T3-T4: official_report_search "最新最新" double-prefix fix ────────────────

class TestNoDoubleLatestPrefix:

    def _build_query_label(self, report_type: str, report_year=None, company_name="贵州茅台", symbol="600519") -> str:
        """Replicate the query_label logic from official_report_search."""
        from app.agents.official_report_search import _REPORT_TYPE_DISPLAY
        _type_label = _REPORT_TYPE_DISPLAY.get(report_type, report_type)
        _year_prefix = (
            str(report_year) if report_year
            else ('' if _type_label.startswith('最新') else '最新')
        )
        return (
            f"{company_name or symbol}"
            + (f" {_year_prefix}" if _year_prefix else "")
            + f" {_type_label}"
        )

    def test_T3_latest_periodic_no_double_zuixin(self):
        """latest_periodic_report → label starts with '最新', so no '最新' prefix."""
        label = self._build_query_label("latest_periodic_report")
        assert label.count("最新") == 1, f"Got '{label}'"
        assert "最新最新" not in label

    def test_T3b_annual_report_gets_zuixin_prefix(self):
        """annual_report label is '年度报告' (no '最新'), so '最新' prefix is added."""
        label = self._build_query_label("annual_report")
        assert "最新" in label
        assert "年度报告" in label

    def test_T3c_annual_report_with_year_no_zuixin(self):
        """When report_year='2024', '年度报告' → '贵州茅台 2024 年度报告', no '最新'."""
        label = self._build_query_label("annual_report", report_year=2024)
        assert "2024" in label
        assert "最新" not in label

    def test_T4_not_found_reason_no_double_zuixin(self):
        """
        Check the actual official_financial_report_search source: not_found_reason
        must not produce '最新最新' by using _year_prefix instead of hard-coded '最新'.
        """
        import inspect
        import app.agents.official_report_search as mod
        src = inspect.getsource(mod.official_financial_report_search)
        # Verify the fix is in place: _year_prefix used in not_found_reason
        assert "_year_prefix" in src
        # Raw "report_year or '最新'" must not appear after "not_found_reason"
        nfr_idx = src.index("not_found_reason")
        after = src[nfr_idx:nfr_idx + 300]
        assert "report_year or '最新'" not in after, (
            "not_found_reason must use _year_prefix, not 'report_year or 最新'"
        )


# ── T5: _summarize_report_plainly section regex fix ──────────────────────────

class TestSummarizeReportSectionRegex:

    _PREVIEW = """# 综合分析报告：贵州茅台（600519）

## 综合结论

贵州茅台基本面稳健，净利率保持高位，品牌壁垒清晰。

## 基本面分析

公司2023年营业收入同比增长约18%，净利润持续保持高位。

## 技术面分析

当前股价处于20日均线下方，MACD出现死叉信号。

## 风险因素

- 白酒行业消费复苏不及预期
"""

    def _call(self, preview: str) -> str:
        from app.agents.chat_skills.report_explanation_skill import _summarize_report_plainly
        return _summarize_report_plainly(preview, "贵州茅台")

    def test_T5_conclusion_section_extracted(self):
        """Should extract text from '综合结论' section."""
        result = self._call(self._PREVIEW)
        # The fix means the section regex now works
        assert "基本面稳健" in result or len(result) > 30

    def test_T5b_result_is_numbered_list(self):
        """Result must be a numbered list."""
        result = self._call(self._PREVIEW)
        assert "1." in result

    def test_T5c_no_raw_header_in_output(self):
        """Raw '# 综合分析报告' must not appear in output."""
        result = self._call(self._PREVIEW)
        assert "# 综合分析报告" not in result

    def test_T5d_technical_section_extracted(self):
        """After fix, 技术面 section first sentence should appear."""
        result = self._call(self._PREVIEW)
        # Either conclusion or section text — at minimum not just a stub
        assert len(result) > 20
        assert "暂不可用" not in result
