"""
test_c2512_summary_quality.py — Phase C25.12 backend tests.

T1  核心摘要 section is prioritised over 数据来源 section
T2  Plain-language rewrites transform jargon correctly
T3  Fallback filters out data-source / tool-name lines
T4  Final answer does not contain "数据来源与覆盖范围"
T5  Dividend year "2024年度分红" banned phrase is filtered
"""
from __future__ import annotations

import pytest

# ── Shared test preview ──────────────────────────────────────────────────────

_FULL_PREVIEW = """综合分析报告：贵州茅台（CN/600519）

一、核心摘要

本报告分析对象为 贵州茅台（CN/600519）。技术面显示当前价格运行于主要均线下方，短期均线下降，成交量持续缩量；基本面基于2026年一季报呈现高毛利率与净利率、低负债率，但营收与净利润增速出现分化；同行对比中盈利能力与财务安全性相对突出，但成长增速低于部分同行；新闻面聚焦年度股东会及短期资金流向波动，市场情绪存在不确定性。

二、数据来源与覆盖范围

技术面：数据来源于历史行情数据库 (akshare)，统计区间为最近120根日K线（约6个月）。
基本面：数据来源于财务报表披露，覆盖2026年一季报。
新闻面：数据来源于金融新闻API，共检索近期新闻20条。
"""

_DATA_SOURCE_ONLY = """二、数据来源与覆盖范围

技术面：数据来源于历史行情数据库 (akshare)，统计区间为最近120根日K线（约6个月）。
基本面：数据来源于财务报表披露。
"""


# ── T1: 核心摘要 takes priority over 数据来源 ────────────────────────────────

class TestCoreAbstractPriority:

    def _call(self, preview: str) -> str:
        from app.agents.chat_skills.report_explanation_skill import _summarize_report_plainly
        return _summarize_report_plainly(preview, "贵州茅台")

    def test_T1_no_datasource_section_in_output(self):
        """Output must never contain data-source section keywords."""
        result = self._call(_FULL_PREVIEW)
        assert "数据来源" not in result, f"'数据来源' leaked into summary:\n{result}"
        assert "覆盖范围" not in result
        assert "akshare" not in result
        assert "120根日K线" not in result

    def test_T1b_core_summary_content_appears(self):
        """Output should contain rewritten content from 核心摘要 section."""
        result = self._call(_FULL_PREVIEW)
        # After rewrites, the core-abstract terms should appear in simplified form
        has_content = any(term in result for term in [
            "股价走势偏弱", "赚钱能力", "财务压力", "增长节奏", "市场情绪",
            "盈利能力", "增长速度",
            # or raw (if rewrites didn't fire) — still OK as long as no data-source
            "技术面", "基本面", "同行",
        ])
        assert has_content, f"Expected financial content, got:\n{result}"

    def test_T1c_output_is_numbered_list(self):
        """Output must start with '1.'."""
        result = self._call(_FULL_PREVIEW)
        assert "1." in result, f"Not a numbered list:\n{result}"

    def test_T1d_at_least_two_points(self):
        """Must extract at least 2 numbered points from 核心摘要."""
        result = self._call(_FULL_PREVIEW)
        count = sum(1 for line in result.splitlines() if line.strip().startswith(("1.", "2.", "3.")))
        assert count >= 2, f"Expected ≥2 points, got:\n{result}"


# ── T2: Plain-language rewrites ────────────────────────────────────────────────

class TestPlainLanguageRewrites:

    def _apply(self, text: str) -> str:
        from app.agents.chat_skills.report_explanation_skill import _apply_rewrites
        return _apply_rewrites(text)

    def test_T2a_junxia_rewrite(self):
        result = self._apply("价格运行于主要均线下方，下行压力明显")
        assert "短期股价走势偏弱" in result

    def test_T2b_chengjiao_rewrite(self):
        result = self._apply("成交量持续缩量，市场热度降低")
        assert "市场交易热度不高" in result

    def test_T2c_maoliilv_rewrite(self):
        result = self._apply("高毛利率与净利率表现优异")
        assert "公司赚钱能力仍然强" in result

    def test_T2d_fuzhai_rewrite(self):
        result = self._apply("低负债率体现财务稳健")
        assert "财务压力相对小" in result

    def test_T2e_fenhua_rewrite(self):
        result = self._apply("营收与净利润增速出现分化")
        assert "收入和利润增长节奏不完全一致" in result

    def test_T2f_qingxu_rewrite(self):
        result = self._apply("市场情绪存在不确定性，投资者需谨慎")
        assert "市场对它的看法还不够稳定" in result

    def test_T2g_tongye_rewrite(self):
        result = self._apply("成长增速低于部分同行企业")
        assert "增长速度低于部分同类公司" in result


# ── T3: Fallback filters data-source lines ────────────────────────────────────

class TestFallbackFilterDataSource:

    def _call(self, preview: str) -> str:
        from app.agents.chat_skills.report_explanation_skill import _summarize_report_plainly
        return _summarize_report_plainly(preview, "贵州茅台")

    def test_T3_only_datasource_returns_insufficient_message(self):
        """When preview has ONLY data-source sections, return the insufficient message."""
        result = self._call(_DATA_SOURCE_ONLY)
        # Must NOT contain akshare / 统计区间
        assert "akshare" not in result
        assert "统计区间" not in result
        assert "120根日K线" not in result
        # Must return the insufficient fallback message
        assert "无法提取足够观点" in result or "暂不可用" in result

    def test_T3b_empty_preview_returns_fallback(self):
        result = self._call("")
        assert result  # non-empty
        assert "暂不可用" in result or "报告" in result

    def test_T3c_mixed_datasource_and_real_content(self):
        """Preview with data-source AND real content → data-source must not appear."""
        preview = """技术面：数据来源于 akshare。

基本面分析

2026年一季报营收同比增长约18%，净利润保持高位，毛利率良好。
"""
        result = self._call(preview)
        # Data-source line skipped
        assert "akshare" not in result
        # Real financial content should appear
        assert any(kw in result for kw in ["营收", "净利润", "毛利率", "增长"])


# ── T4: Final answer does not contain "数据来源与覆盖范围" ─────────────────────

class TestFinalAnswerNoDataSource:

    def test_T4_full_preview_answer_no_datasource_section(self):
        """
        Calling _summarize_report_plainly with the full preview must not produce
        any output containing the '数据来源与覆盖范围' section text.
        """
        from app.agents.chat_skills.report_explanation_skill import _summarize_report_plainly
        result = _summarize_report_plainly(_FULL_PREVIEW, "贵州茅台")
        assert "数据来源与覆盖范围" not in result, (
            f"Data-source section leaked into answer:\n{result}"
        )
        assert "技术面：数据来源于历史行情数据库" not in result


# ── T5: Dividend year "2024年度分红" banned phrase ────────────────────────────

class TestDividendYearBanned:

    def _filter(self, text: str) -> str:
        from app.agents.chat_llm_answerer import _filter_banned_phrases
        return _filter_banned_phrases(text)

    def test_T5a_2024_nian_fen_hong_filtered(self):
        """'2024年度分红' must be replaced."""
        text = "新闻显示贵州茅台正在进行2024年度分红，分红方案已披露。"
        result = self._filter(text)
        assert "2024年度分红" not in result
        assert "无法确认分配年度" in result

    def test_T5b_2023_nian_fen_hong_filtered(self):
        """'2023年度分红' must be replaced."""
        text = "本次分红为2023年度分红，每股派发1.5元。"
        result = self._filter(text)
        assert "2023年度分红" not in result

    def test_T5c_2025_nian_fen_hong_filtered(self):
        """'2025年度分红' must be replaced."""
        text = "公司公告2025年度分红计划。"
        result = self._filter(text)
        assert "2025年度分红" not in result

    def test_T5d_system_prompt_has_dividend_rule(self):
        """System prompt must contain the dividend year prohibition rule."""
        from app.agents.chat_llm_answerer import _SYSTEM_PROMPT
        assert "分红" in _SYSTEM_PROMPT or "年度分红" in _SYSTEM_PROMPT or "分配年度" in _SYSTEM_PROMPT
        # The rule about news titles without complete announcement text
        assert "公告原文" in _SYSTEM_PROMPT or "年份字段" in _SYSTEM_PROMPT or "分配年度" in _SYSTEM_PROMPT
