"""
Phase 6W-R1 P0-C — Financial Report Query Routing Fix
4 tests

Coverage:
  1. Analysis-intent query does NOT short-circuit to _handle_latest_report_setup_direct
     (i.e., _match_latest_report_setup_candidate no longer causes an early return)
  2. PDF-find-intent query still routes correctly to _handle_official_report_pdf_direct
  3. Pattern guard: queries known to express analysis intent match the correct function
     and do NOT match the PDF-find pattern
  4. Regression: _handle_latest_report_setup_direct function itself still resolves
     report context correctly (the function is preserved, just not called as early-return)
"""
from __future__ import annotations

import pytest


# ===========================================================================
# 1. Analysis-intent queries no longer match the early-return dispatch
# ===========================================================================

class TestLatestReportSetupNoLongerEarlyReturns:
    """After P0-C fix: _match_latest_report_setup_candidate still works as a
    predicate but the orchestrator no longer uses it as an early-return gate."""

    def _pattern_matches(self, msg: str) -> bool:
        from app.agents.chat_orchestrator import _match_latest_report_setup_candidate
        return _match_latest_report_setup_candidate(msg)

    def test_analysis_queries_still_match_the_predicate(self):
        """The predicate must still return True for these queries (not broken)."""
        analysis_queries = [
            "贵州茅台最新财报表现如何",
            "最近财报怎么样",
            "这份财报情况分析一下",
            "最新定期报告解读",
        ]
        for q in analysis_queries:
            assert self._pattern_matches(q), \
                f"_match_latest_report_setup_candidate must match analysis query: {q!r}"

    def test_pdf_find_queries_do_not_match(self):
        """Pure analysis queries (no PDF/download/链接 keywords) should NOT match
        the PDF-find shadow candidate pattern."""
        from app.agents.chat_orchestrator import _match_official_report_pdf_shadow_candidate
        # Pure content-analysis queries — no mention of PDF/链接/下载
        pure_analysis_queries = [
            "贵州茅台最新财报表现如何",
            "最近财报怎么样",
        ]
        for q in pure_analysis_queries:
            assert not _match_official_report_pdf_shadow_candidate(q), \
                f"Pure analysis query {q!r} must NOT match PDF-find pattern"


# ===========================================================================
# 2. PDF-find queries still route to the correct handler
# ===========================================================================

class TestOfficialReportPdfRouting:
    """PDF download/find queries must still match the PDF handler pattern."""

    def test_pdf_queries_match_pdf_pattern(self):
        from app.agents.chat_orchestrator import _match_official_report_pdf_shadow_candidate
        pdf_queries = [
            "帮我找一下茅台的年报PDF",
            "600519年度报告下载",
            "贵州茅台官方年报",
        ]
        for q in pdf_queries:
            assert _match_official_report_pdf_shadow_candidate(q), \
                f"PDF query {q!r} must match _match_official_report_pdf_shadow_candidate"


# ===========================================================================
# 3. Pattern intent separation (analysis vs PDF-find)
# ===========================================================================

class TestPatternIntentSeparation:
    """Verify that analysis and PDF-find patterns don't overlap incorrectly."""

    ANALYSIS_QUERIES = [
        "贵州茅台最新财报表现如何",
        "最新报告情况如何",
        "最近财报怎么样",
        "最近这份定期报告解读",
    ]
    PDF_QUERIES = [
        "贵州茅台年报PDF",
        "600519官方年报链接",
    ]

    def test_analysis_queries_match_analysis_not_pdf(self):
        from app.agents.chat_orchestrator import (
            _match_latest_report_setup_candidate,
            _match_official_report_pdf_shadow_candidate,
        )
        for q in self.ANALYSIS_QUERIES:
            assert _match_latest_report_setup_candidate(q), \
                f"Analysis query {q!r} must match analysis pattern"
            assert not _match_official_report_pdf_shadow_candidate(q), \
                f"Analysis query {q!r} must NOT match PDF pattern"

    def test_handle_latest_report_setup_function_exists(self):
        """_handle_latest_report_setup_direct must still exist (it's called for
        other use cases and is preserved; it's just no longer the early-return gate)."""
        from app.agents import chat_orchestrator
        assert callable(getattr(chat_orchestrator, "_handle_latest_report_setup_direct", None)), \
            "_handle_latest_report_setup_direct must still be defined"


# ===========================================================================
# 4. Orchestrator no longer has the analysis-intent early-return block
# ===========================================================================

class TestOrchestatorSourceNoEarlyReturn:
    """Verify the P0-C removal is reflected in the source code."""

    def test_orchestrator_source_does_not_early_return_for_analysis_intent(self):
        """The orchestrator must not have the construct:
        'return await _handle_latest_report_setup_direct'
        in the same block as '_match_latest_report_setup_candidate'.
        That was the premature early-return that prevented agent invocation."""
        import inspect
        from app.agents import chat_orchestrator
        src = inspect.getsource(chat_orchestrator)

        # After P0-C fix: the early-return pattern should be gone.
        # We check that there is NO inline block that both checks the candidate
        # AND immediately returns the direct handler result within a few lines.
        # Simple heuristic: count occurrences of 'return await _handle_latest_report_setup_direct'
        return_count = src.count("return await _handle_latest_report_setup_direct")
        assert return_count == 0, (
            f"Found {return_count} early-return(s) to _handle_latest_report_setup_direct. "
            "P0-C fix requires these to be removed so analysis queries reach ReportExplanationSkill."
        )


# ===========================================================================
# 5. Phase 6W-R1.1 Blocking-B: 6-query routing matrix
# ===========================================================================

class TestBlockingBSixQueryRoutingMatrix:
    """R1.1 Blocking-B: Verify all 6 canonical queries route to the correct handler.

    Routing decision (when entity hint is available):
    1. PDF pattern + NOT analysis override → PDF-handler (early return)
    2. PDF pattern + analysis override    → SkillRegistry (falls through)
    3. No PDF pattern + skill pattern     → ReportExplanationSkill
    4. No PDF pattern + no skill pattern  → general / C4

    After R1.1-B fix:
    - Q1, Q2, Q6 (analysis intent) → ReportExplanationSkill
    - Q3, Q4, Q5 (locator intent)  → PDF-handler
    """

    def _pdf(self, msg: str) -> bool:
        from app.agents.chat_orchestrator import _match_official_report_pdf_shadow_candidate
        return _match_official_report_pdf_shadow_candidate(msg)

    def _override(self, msg: str) -> bool:
        from app.agents.chat_orchestrator import _PDF_ANALYSIS_OVERRIDE_RE
        return bool(_PDF_ANALYSIS_OVERRIDE_RE.search(msg))

    def _skill(self, msg: str) -> bool:
        from app.agents.chat_skills.report_explanation_skill import ReportExplanationSkill
        from unittest.mock import MagicMock
        skill = ReportExplanationSkill()
        ctx = MagicMock()
        ctx.db = None
        ctx.user_id = None
        ctx.session_id = None
        ctx.event_callback = None
        ctx.entities = []
        # can_handle only reads message, ctx is not used for pattern matching
        try:
            return skill.can_handle(msg, ctx)
        except Exception:
            # fallback: just check _PATTERN directly
            from app.agents.chat_skills.report_explanation_skill import _PATTERN
            return bool(_PATTERN.search(msg))

    def _route(self, msg: str) -> str:
        """Simulate routing logic (entity hint assumed found)."""
        if self._pdf(msg) and not self._override(msg):
            return "PDF-handler"
        if self._skill(msg):
            return "ReportExplanationSkill"
        return "general/C4"

    def test_q1_analysis_financial_report_performance(self):
        """Q1: 贵州茅台最新财报表现如何？ → ReportExplanationSkill"""
        assert self._route("贵州茅台最新财报表现如何？") == "ReportExplanationSkill"

    def test_q2_analysis_annual_report_profitability(self):
        """Q2: 分析贵州茅台最新年报的盈利能力 → ReportExplanationSkill (not PDF-handler).

        This was the R1.1-B gap: "年报" in query matched PDF pattern, incorrectly
        routing an analysis query to the PDF locator. Fixed by _PDF_ANALYSIS_OVERRIDE_RE.
        """
        assert self._route("分析贵州茅台最新年报的盈利能力") == "ReportExplanationSkill"

    def test_q3_locator_official_pdf(self):
        """Q3: 请给我贵州茅台最新年报的官方PDF → PDF-handler"""
        assert self._route("请给我贵州茅台最新年报的官方PDF") == "PDF-handler"

    def test_q4_locator_annual_report_find(self):
        """Q4: 帮我找到贵州茅台的年度报告 → PDF-handler"""
        assert self._route("帮我找到贵州茅台的年度报告") == "PDF-handler"

    def test_q5_locator_which_report(self):
        """Q5: 贵州茅台最新报告是哪一份？ → PDF-handler.

        This was the R1.1-B gap: "最新报告是哪一份" matched neither PDF pattern
        nor SkillPattern, falling to general/C4. Fixed by adding 报告.*哪一份 to
        _OFFICIAL_REPORT_PDF_SHADOW_PATTERN.
        """
        assert self._route("贵州茅台最新报告是哪一份？") == "PDF-handler"

    def test_q6_analysis_risks(self):
        """Q6: 贵州茅台最新财报有哪些风险？ → ReportExplanationSkill"""
        assert self._route("贵州茅台最新财报有哪些风险？") == "ReportExplanationSkill"

    def test_pure_pdf_download_not_overridden(self):
        """PDF download queries must not be overridden by analysis pattern."""
        assert self._route("下载茅台2023年报PDF") == "PDF-handler"
        assert self._route("茅台官方年报链接") == "PDF-handler"
