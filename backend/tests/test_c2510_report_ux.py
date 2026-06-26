"""
test_c2510_report_ux.py — Phase C25.10 tests.

Validates:
T1  summarize_report_plainly: does NOT start with "# 综合分析报告"
T2  summarize_report_plainly: output is a numbered list
T3  latest_periodic_report not exposed — not_found_reason uses Chinese label
T4  "假设为" banned phrase filtered by chat_llm_answerer._filter_banned_phrases
T5  official_report_search query_label uses Chinese label
T6  annual_report label correct
T7  semi_annual_report label correct
"""
from __future__ import annotations

import pytest


# ── T1-T2: plain-language report summarization ────────────────────────────────

_SAMPLE_PREVIEW = """# 综合分析报告：贵州茅台（600519）

## 综合结论

贵州茅台基本面稳健，净利率保持高位，品牌壁垒清晰。但短期股价位于主要均线下方，
技术面偏弱，需关注市场情绪波动。

## 基本面分析

公司2023年营业收入同比增长约18%，净利润持续保持高位。ROE表现优异，资产负债率低。

## 技术面分析

当前股价处于20日均线下方，MACD出现死叉信号，RSI在50以下，短期偏弱。

## 风险因素

- 白酒行业消费复苏不及预期
- 市场整体情绪低迷可能导致估值回落
- 政策环境变化对高端消费的潜在影响

_仅供研究参考，不构成投资建议。_
"""


class TestSummarizeReportPlainly:

    def _call(self, preview: str, stock_name: str = "贵州茅台") -> str:
        from app.agents.chat_skills.report_explanation_skill import _summarize_report_plainly
        return _summarize_report_plainly(preview, stock_name)

    def test_T1_does_not_paste_raw_header(self):
        """Output must not start with '# 综合分析报告'."""
        result = self._call(_SAMPLE_PREVIEW)
        assert not result.startswith("# 综合分析报告"), (
            "summarize_report_plainly must not paste raw Markdown title"
        )
        assert "综合分析报告：贵州茅台" not in result.split("\n")[0]

    def test_T2_output_is_numbered_list(self):
        """Output should be a numbered list (starts with '1.')."""
        result = self._call(_SAMPLE_PREVIEW)
        assert "1." in result, f"Expected numbered list, got: {result[:100]}"

    def test_T2b_output_has_content(self):
        """Output must have at least one meaningful sentence."""
        result = self._call(_SAMPLE_PREVIEW)
        assert len(result) > 30, "Summary too short"

    def test_T2c_empty_preview_returns_fallback(self):
        """Empty preview returns fallback message, not crash."""
        result = self._call("")
        assert result, "Should return non-empty fallback"
        assert "暂不可用" in result or "报告" in result


# ── T3: latest_periodic_report not exposed to users ──────────────────────────

class TestReportTypeEnumHidden:

    def test_T3_not_found_reason_uses_chinese_label(self):
        """not_found_reason must not contain 'latest_periodic_report' raw enum."""
        from app.agents.official_report_search import _REPORT_TYPE_DISPLAY
        # Verify the display dict is complete
        assert "latest_periodic_report" in _REPORT_TYPE_DISPLAY
        assert _REPORT_TYPE_DISPLAY["latest_periodic_report"] == "最新已披露定期报告"

    def test_T3b_not_found_uses_display_label(self):
        """
        When official_financial_report_search builds a not_found_reason,
        it should use the Chinese label, not the raw enum key.
        Verify by inspecting the source.
        """
        import inspect
        import app.agents.official_report_search as mod
        src = inspect.getsource(mod.official_financial_report_search)
        # The raw enum must not appear in the not_found_reason string
        assert "latest_periodic_report" not in src.split("not_found_reason")[1][:200], (
            "not_found_reason must use Chinese label, not raw enum key"
        )

    def test_T5_query_label_uses_chinese(self):
        """query_label must not use raw enum key either."""
        import inspect
        import app.agents.official_report_search as mod
        src = inspect.getsource(mod.official_financial_report_search)
        # After _type_label assignment, query_label should use _type_label
        assert "_type_label" in src

    def test_T6_annual_report_label(self):
        from app.agents.official_report_search import _REPORT_TYPE_DISPLAY
        assert _REPORT_TYPE_DISPLAY["annual_report"] == "年度报告"

    def test_T7_semi_annual_label(self):
        from app.agents.official_report_search import _REPORT_TYPE_DISPLAY
        assert _REPORT_TYPE_DISPLAY["semi_annual_report"] == "半年度报告"


# ── T4: "假设为" banned phrase filter ─────────────────────────────────────────

class TestBannedPhraseFilter:

    def _filter(self, text: str) -> str:
        from app.agents.chat_llm_answerer import _filter_banned_phrases
        return _filter_banned_phrases(text)

    def test_T4a_jiashewei_filtered(self):
        """'假设为年报分红' must be replaced."""
        text = "这是2023年度利润分配的一部分（假设为年报分红）。"
        result = self._filter(text)
        assert "假设为年报分红" not in result, "假设为年报分红 must be filtered"
        assert "工具未提供" in result or "依据" in result

    def test_T4b_jiashewei_generic_filtered(self):
        """Generic '假设为' must be replaced."""
        text = "假设为季报数据。"
        result = self._filter(text)
        assert "假设为" not in result

    def test_T4c_tuicetwei_filtered(self):
        """'推测为' must be replaced."""
        text = "根据市场情况推测为年报数据。"
        result = self._filter(text)
        assert "推测为" not in result

    def test_T4d_enum_string_filtered(self):
        """Internal enum strings must not pass through to users."""
        text = "未检索到 latest_periodic_report 财报。"
        result = self._filter(text)
        assert "latest_periodic_report" not in result
        assert "最新已披露定期报告" in result
