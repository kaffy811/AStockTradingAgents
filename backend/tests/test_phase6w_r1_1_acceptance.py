"""
Phase 6W-R1.1 Acceptance Audit — Blocking Items F + cache key separation

Tests
-----
F-1: make_cache_key includes intent_type in key
F-2: analysis and locator keys for same (ts_code, question) are different
F-3: read_cache / write_cache accept intent_type parameter (no TypeError)
F-4: default intent_type is "analysis" for backward compatibility
F-5: Cache key format is rc:{version}:{intent_type}:{ts_code}:{qh}:{fh}
"""
from __future__ import annotations

import pytest


class TestCacheKeyIntentSeparationF:
    """R1.1 Blocking-F: Cache key must include intent_type segment."""

    def _key(self, ts_code: str, question: str, intent_type: str = "analysis") -> str:
        from app.agent.report_chat_cache import make_cache_key
        return make_cache_key(ts_code, question, intent_type=intent_type)

    def test_f1_key_contains_intent_type_segment(self):
        """F-1: make_cache_key must embed intent_type in the returned key."""
        key = self._key("600519.SH", "最新财报表现如何", intent_type="analysis")
        assert "analysis" in key, \
            f"Cache key must contain 'analysis'; got {key!r}"

    def test_f2_analysis_and_locator_keys_are_different(self):
        """F-2: Same ts_code + question must produce different keys for different intents.

        This is the core correctness requirement: a locator answer cached under
        'locator' must never be served for an 'analysis' query.
        """
        q = "最新年报怎么样"
        k_analysis = self._key("600519.SH", q, intent_type="analysis")
        k_locator  = self._key("600519.SH", q, intent_type="locator")
        assert k_analysis != k_locator, (
            f"Analysis and locator keys must differ for the same question.\n"
            f"analysis: {k_analysis!r}\n"
            f"locator:  {k_locator!r}"
        )

    def test_f3_default_intent_type_is_analysis(self):
        """F-4: Backward-compat: calling make_cache_key without intent_type → 'analysis' slot."""
        from app.agent.report_chat_cache import make_cache_key
        key_default  = make_cache_key("600519.SH", "最新年报怎么样")
        key_explicit = make_cache_key("600519.SH", "最新年报怎么样", intent_type="analysis")
        assert key_default == key_explicit, \
            "Default intent_type must be 'analysis' for backward compatibility"

    def test_f4_key_format_has_intent_segment(self):
        """F-5: Key format must be rc:{version}:{intent_type}:{ts_code}:{qh}:{fh}."""
        key = self._key("600519.SH", "最新财报如何", intent_type="analysis")
        # Split by ':'
        parts = key.split(":")
        assert parts[0] == "rc", f"Prefix must be 'rc'; key={key!r}"
        assert parts[2] in ("analysis", "locator"), \
            f"Third segment must be intent_type; key={key!r}"
        assert parts[3] == "600519.SH", \
            f"Fourth segment must be ts_code; key={key!r}"

    def test_f5_locator_key_contains_locator_segment(self):
        """F-1 (locator side): key for locator intent contains 'locator'."""
        key = self._key("000858.SZ", "年报是哪一份", intent_type="locator")
        assert "locator" in key, \
            f"Cache key must contain 'locator'; got {key!r}"

    def test_f6_read_write_cache_accept_intent_type(self):
        """F-3: read_cache and write_cache accept intent_type without TypeError."""
        import inspect
        from app.agent import report_chat_cache
        # Verify signatures include intent_type
        read_sig  = inspect.signature(report_chat_cache.read_cache)
        write_sig = inspect.signature(report_chat_cache.write_cache)
        assert "intent_type" in read_sig.parameters, \
            "read_cache must accept intent_type parameter"
        assert "intent_type" in write_sig.parameters, \
            "write_cache must accept intent_type parameter"

    def test_f7_report_copilot_agent_chat_accepts_intent_type(self):
        """F-3 (agent): ReportChatCopilotAgent.chat() must accept intent_type."""
        import inspect
        from app.agent.report_chat_copilot_agent import ReportChatCopilotAgent
        sig = inspect.signature(ReportChatCopilotAgent.chat)
        assert "intent_type" in sig.parameters, \
            "ReportChatCopilotAgent.chat must accept intent_type parameter"
        # Default value must be "analysis"
        default = sig.parameters["intent_type"].default
        assert default == "analysis", \
            f"Default intent_type must be 'analysis', got {default!r}"


class TestBlockingESkeletonLoadingCoverage:
    """R1.1 Blocking-E: Skeleton loading refs must always be cleared via finally.

    Verifies that the four loading refs in CompanyFundamentalsPanel.vue
    have corresponding finally blocks so skeleton never persists on error.
    """

    def _read_cfp_source(self) -> str:
        import os
        path = os.path.join(
            os.path.dirname(__file__),
            "../../frontend/src/components/CompanyFundamentalsPanel.vue",
        )
        with open(os.path.normpath(path)) as f:
            return f.read()

    def test_e1_overview_loading_cleared_in_finally(self):
        """E-1: overviewLoading.value = false must appear inside a finally block."""
        src = self._read_cfp_source()
        # Find the pattern: "finally" ... "overviewLoading.value = false"
        import re
        # Find all finally blocks and check overviewLoading is cleared
        finally_blocks = list(re.finditer(r"finally\s*\{[^}]*overviewLoading\.value\s*=\s*false", src, re.DOTALL))
        assert len(finally_blocks) >= 1, \
            "overviewLoading.value = false must be inside a finally block"

    def test_e2_diagnostics_loading_cleared_in_finally(self):
        """E-2: diagnosticsLoading.value = false must appear inside a finally block."""
        src = self._read_cfp_source()
        import re
        blocks = list(re.finditer(r"finally\s*\{[^}]*diagnosticsLoading\.value\s*=\s*false", src, re.DOTALL))
        assert len(blocks) >= 1, \
            "diagnosticsLoading.value = false must be inside a finally block"

    def test_e3_module_loading_cleared_in_finally(self):
        """E-3: moduleLoading per-key must be set to false inside a finally block."""
        src = self._read_cfp_source()
        import re
        blocks = list(re.finditer(r"finally\s*\{[^}]*moduleLoading\.value\s*=", src, re.DOTALL))
        assert len(blocks) >= 2, \
            "moduleLoading must be reset to false in at least 2 finally blocks (loadModule + loadAiSummary)"

    def test_e4_ai_summary_loading_cleared_in_finally(self):
        """E-4: aiSummaryLoading.value = false must appear inside a finally block."""
        src = self._read_cfp_source()
        import re
        blocks = list(re.finditer(r"finally\s*\{[^}]*aiSummaryLoading\.value\s*=\s*false", src, re.DOTALL))
        assert len(blocks) >= 1, \
            "aiSummaryLoading.value = false must be inside a finally block"

    def test_e5_top_skeleton_controlled_by_diagnostics_loading(self):
        """E-5: The top-level skeleton (cfp-sections-skeleton) is gated on diagnosticsLoading.

        This ensures the skeleton is shown only during initial section loading
        and is cleared as soon as loadDiagnostics() completes (success or error).
        """
        src = self._read_cfp_source()
        # The skeleton div must be under v-if="diagnosticsLoading"
        import re
        pattern = re.compile(r'v-if="diagnosticsLoading"[^>]*>.*?cfp-sections-skeleton', re.DOTALL)
        assert pattern.search(src), \
            "Top-level skeleton must be under v-if=\"diagnosticsLoading\" control"
