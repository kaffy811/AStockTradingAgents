"""
test_c259_report_detail_fix.py — Phase C25.9 tests.

Validates:
T1  _parse_report_period: "最新财报" → latest_periodic_report (NOT annual_report)
T2  _parse_report_period: "年报" still → annual_report
T3  _parse_report_period: "财报" alone → latest_periodic_report
T4  _parse_report_period: "2023年报" → annual_report + year=2023
T5  report_explanation_skill _PATTERN matches "6.11报告"/"历史报告"
T6  report_explanation_skill uses report_id kwarg (not run_id)
"""
from __future__ import annotations

import asyncio
import re
import pytest


# ── T1-T4: _parse_report_period fixes ─────────────────────────────────────────

class TestParseReportPeriod:

    def _call(self, query: str) -> dict:
        from app.agents.official_report_search import _parse_report_period  # type: ignore
        return _parse_report_period(query)

    def test_T1_zuixin_caibao_not_annual(self):
        """'最新财报' must not map to annual_report — should be latest_periodic_report."""
        result = self._call("贵州茅台最新财报")
        assert result["report_type"] == "latest_periodic_report", (
            f"Expected latest_periodic_report, got {result['report_type']!r}"
        )

    def test_T2_nianbao_still_annual(self):
        """'年报' must still map to annual_report."""
        result = self._call("茅台2023年报")
        assert result["report_type"] == "annual_report"
        assert result["report_year"] == 2023

    def test_T3_caibao_alone_latest_periodic(self):
        """'财报' alone (without 年报 keyword) → latest_periodic_report."""
        result = self._call("查询茅台最近财报")
        assert result["report_type"] == "latest_periodic_report"

    def test_T4_explicit_year_annual(self):
        """'2024年度报告' must map to annual_report."""
        result = self._call("请查找茅台2024年度报告")
        assert result["report_type"] == "annual_report"
        assert result["report_year"] == 2024


# ── T5: ReportExplanationSkill _PATTERN ────────────────────────────────────────

class TestReportExplanationPattern:

    def _matches(self, message: str) -> bool:
        from app.agents.chat_skills.report_explanation_skill import _PATTERN  # type: ignore
        return bool(_PATTERN.search(message))

    def test_T5a_date_report_pattern(self):
        assert self._matches("6.11的报告讲了什么") is True

    def test_T5b_lishi_baogao(self):
        assert self._matches("帮我看历史报告") is True

    def test_T5c_jie_shi_baogao(self):
        assert self._matches("解释最近报告") is True

    def test_T5d_yue_ri_pattern(self):
        assert self._matches("6月11日的报告") is True

    def test_T5e_normal_query_no_match(self):
        """A plain price query should not match report_explanation_skill."""
        assert self._matches("茅台今天股价多少") is False


# ── T6: report_explanation_skill passes report_id (not run_id) ─────────────────

class TestReportDetailToolKwarg:
    """
    Verify that report_explanation_skill.run() calls get_report_detail_tool
    with 'report_id' kwarg, not 'run_id'.
    """

    def test_T6_uses_report_id_kwarg(self):
        """
        Inspect the source code to confirm 'report_id=str(report_id)' appears
        and 'run_id=str(report_id)' does NOT appear.
        (C25.11: run() delegates to _run_inner(); inspect the class source.)
        """
        import inspect
        import app.agents.chat_skills.report_explanation_skill as mod
        src = inspect.getsource(mod.ReportExplanationSkill)
        assert "report_id=str(report_id)" in src, (
            "report_explanation_skill must pass report_id= kwarg to get_report_detail_tool"
        )
        assert "run_id=str(report_id)" not in src, (
            "report_explanation_skill must NOT use run_id= (old bug)"
        )

    def test_T6b_preview_field_used(self):
        """Skill should read 'preview' field first from report_detail."""
        import inspect
        import app.agents.chat_skills.report_explanation_skill as mod
        src = inspect.getsource(mod.ReportExplanationSkill)
        assert 'report_detail.get("preview")' in src, (
            "report_explanation_skill must read 'preview' field (GetReportDetailTool returns 'preview', not 'summary')"
        )
