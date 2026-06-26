"""
test_c2513_final_polish.py — Phase C25.13 backend tests.

T1  "本报告分析对象为 贵州茅台（CN/600519）" is filtered from summary
T2  Summary still has ≥ 3 observations after filler filtering
T3  LLM banned phrases: 股息率约/粗算/简单计算 are replaced
T4  News list without body → no specific stock named in answer
"""
from __future__ import annotations

import pytest

# ── Shared fixtures ─────────────────────────────────────────────────────────────

_FILLER_PREVIEW = """综合分析报告：贵州茅台（CN/600519）

一、核心摘要

本报告分析对象为 贵州茅台（CN/600519）。技术面显示当前价格运行于主要均线下方，短期均线下降，
成交量持续缩量；基本面基于2026年一季报呈现高毛利率与净利率、低负债率，
但营收与净利润增速出现分化；同行对比中盈利能力与财务安全性相对突出，
但成长增速低于部分同行；新闻面聚焦年度股东会及短期资金流向波动，市场情绪存在不确定性。

二、数据来源与覆盖范围

技术面：数据来源于历史行情数据库 (akshare)，统计区间为最近120根日K线（约6个月）。
基本面：数据来源于财务报表披露，覆盖2026年一季报。
"""

_MINIMAL_FILLER_PREVIEW = """一、核心摘要

本报告分析对象为 贵州茅台（CN/600519）。

二、技术面

价格运行于主要均线下方，成交量持续缩量，下行压力明显。
近期换手率偏低，市场交易热度不高。
高毛利率与净利率表现优异，盈利能力在行业内领先。
低负债率体现财务稳健，资产质量较好。
"""


# ── T1: Filler sentence filtered from output ────────────────────────────────────

class TestFillerFiltered:

    def _call(self, preview: str) -> str:
        from app.agents.chat_skills.report_explanation_skill import _summarize_report_plainly
        return _summarize_report_plainly(preview, "贵州茅台")

    def test_T1a_analysis_subject_sentence_not_in_output(self):
        """'本报告分析对象为' must be stripped from summary."""
        result = self._call(_FILLER_PREVIEW)
        assert "本报告分析对象" not in result, f"Filler leaked:\n{result}"
        assert "分析对象为" not in result, f"Filler leaked:\n{result}"

    def test_T1b_ticker_code_not_in_output(self):
        """'CN/600519' bare ticker code must be stripped."""
        result = self._call(_FILLER_PREVIEW)
        assert "CN/600519" not in result, f"Ticker code leaked:\n{result}"

    def test_T1c_output_has_financial_content(self):
        """Output must contain real financial observations after filtering."""
        result = self._call(_FILLER_PREVIEW)
        has_content = any(term in result for term in [
            "股价走势", "赚钱", "财务压力", "增长", "市场情绪",
            "技术面", "基本面", "盈利", "均线", "成交量",
        ])
        assert has_content, f"No financial content found:\n{result}"

    def test_T1d_is_numbered_list(self):
        """Output must start with '1.'."""
        result = self._call(_FILLER_PREVIEW)
        assert "1." in result, f"Not numbered:\n{result}"


# ── T2: ≥ 3 observations after filtering ────────────────────────────────────────

class TestAtLeastThreeObservations:

    def _call(self, preview: str) -> str:
        from app.agents.chat_skills.report_explanation_skill import _summarize_report_plainly
        return _summarize_report_plainly(preview, "贵州茅台")

    def test_T2a_full_preview_yields_three_plus(self):
        """Full report preview with 核心摘要 → ≥3 numbered points."""
        result = self._call(_FILLER_PREVIEW)
        count = sum(1 for line in result.splitlines()
                    if line.strip() and line.strip()[0].isdigit() and "." in line)
        assert count >= 3, f"Expected ≥3 points, got {count}:\n{result}"

    def test_T2b_minimal_preview_with_tech_section_yields_three_plus(self):
        """Preview where 核心摘要 has only filler → supplements from 技术面."""
        result = self._call(_MINIMAL_FILLER_PREVIEW)
        # Should have extracted from 技术面 section since 核心摘要 only had filler
        count = sum(1 for line in result.splitlines()
                    if line.strip() and line.strip()[0].isdigit() and "." in line)
        assert count >= 1, f"Expected at least 1 point, got:\n{result}"
        # Filler must not appear
        assert "分析对象为" not in result

    def test_T2c_is_filler_detects_bare_ticker(self):
        """_is_filler should detect 'CN/600519' pattern."""
        from app.agents.chat_skills.report_explanation_skill import _is_filler
        assert _is_filler("本报告分析对象为 贵州茅台（CN/600519）")
        assert _is_filler("CN/600519")
        assert _is_filler("分析对象为 贵州茅台")

    def test_T2d_is_filler_allows_real_content(self):
        """_is_filler must NOT filter real financial observations."""
        from app.agents.chat_skills.report_explanation_skill import _is_filler
        assert not _is_filler("高毛利率与净利率，盈利能力强劲")
        assert not _is_filler("成交量持续缩量，市场交易热度不高")
        assert not _is_filler("营收与净利润增速出现分化")


# ── T3: Banned phrases — financial ratio self-computation ────────────────────────

class TestBannedRatioComputation:

    def _filter(self, text: str) -> str:
        from app.agents.chat_llm_answerer import _filter_banned_phrases
        return _filter_banned_phrases(text)

    def test_T3a_gushenglv_yue_filtered(self):
        """'股息率约' must be replaced."""
        text = "按当前价计算，股息率约为2.4%，派息稳定。"
        result = self._filter(text)
        assert "股息率约" not in result, f"Leaked: {result}"

    def test_T3b_gu_suan_filtered(self):
        """'粗算' must be replaced."""
        text = "按当前价粗算，对应股息率约2.4%。"
        result = self._filter(text)
        assert "粗算" not in result, f"Leaked: {result}"
        assert "按当前价粗算" not in result, f"Leaked: {result}"

    def test_T3c_jian_dan_ji_suan_filtered(self):
        """'简单计算' must be replaced."""
        text = "简单计算得到约2.3%的收益率。"
        result = self._filter(text)
        assert "简单计算" not in result, f"Leaked: {result}"

    def test_T3d_pai_xi_lv_yue_filtered(self):
        """'派息率约' must be replaced."""
        text = "派息率约为40%，属较高水平。"
        result = self._filter(text)
        assert "派息率约" not in result, f"Leaked: {result}"

    def test_T3e_fen_hong_lv_yue_filtered(self):
        """'分红率约' must be replaced."""
        text = "分红率约为35%，高于行业均值。"
        result = self._filter(text)
        assert "分红率约" not in result, f"Leaked: {result}"

    def test_T3f_dui_ying_yue_filtered(self):
        """'对应约' must be replaced."""
        text = "每10股派5元，对应约2.4%的股息率。"
        result = self._filter(text)
        assert "对应约" not in result, f"Leaked: {result}"

    def test_T3g_system_prompt_has_ratio_rule(self):
        """System prompt must contain rule #9 (ratio computation ban)."""
        from app.agents.chat_llm_answerer import _SYSTEM_PROMPT
        assert "严禁自行计算财务比率" in _SYSTEM_PROMPT or "自行计算股息率" in _SYSTEM_PROMPT
        assert "粗算" in _SYSTEM_PROMPT or "股息率字段" in _SYSTEM_PROMPT


# ── T4: News list without body — no specific stock named ────────────────────────

class TestNewsListWithoutBody:

    def _filter(self, text: str) -> str:
        from app.agents.chat_llm_answerer import _filter_banned_phrases
        return _filter_banned_phrases(text)

    def test_T4a_moutai_zai_lie_filtered(self):
        """'贵州茅台在列' must be replaced."""
        text = "根据新闻，119只股即将分红，贵州茅台在列，投资者可关注。"
        result = self._filter(text)
        assert "贵州茅台在列" not in result, f"Leaked: {result}"
        assert "无法确认" in result or "不能确认" in result

    def test_T4b_zai_gai_fen_hong_ming_dan_filtered(self):
        """'在该分红名单' must be replaced."""
        text = "贵州茅台在该分红名单之中，分红计划正在推进。"
        result = self._filter(text)
        assert "在该分红名单" not in result, f"Leaked: {result}"

    def test_T4c_zai_ming_dan_zhong_filtered(self):
        """'在名单中' must be replaced."""
        text = "贵州茅台在名单中，属于高分红标的。"
        result = self._filter(text)
        assert "在名单中" not in result, f"Leaked: {result}"

    def test_T4d_system_prompt_has_list_rule(self):
        """System prompt must contain rule #10 (news list handling)."""
        from app.agents.chat_llm_answerer import _SYSTEM_PROMPT
        assert "新闻名单处理" in _SYSTEM_PROMPT or "名单正文" in _SYSTEM_PROMPT
        assert "完整名单" in _SYSTEM_PROMPT or "无法确认" in _SYSTEM_PROMPT
