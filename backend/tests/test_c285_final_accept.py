"""
C28.5 Final Safety/DataQuality Cut-through Patch — backend tests.

T1–T4:  Yield-calculation remnant cleanup (Problem 1).
T5–T9:  Dividend-inference → financial-ability sentence removal (Problem 2).
"""
from __future__ import annotations

import pytest

from app.agents.financial_safety_postprocessor import (
    sanitize_unverified_financial_metrics,
    sanitize_dividend_overinference,
    sanitize_financial_answer,
)


# ---------------------------------------------------------------------------
# Problem 1 — Yield calculation remnants must be fully deleted (T1–T4)
# ---------------------------------------------------------------------------

class TestYieldCalculationCleanup:
    """T1–T4: no arithmetic percentage or fraction survives after sanitisation."""

    def test_T1_mangled_disclaimer_plus_calc_cleaned(self):
        """T1: pre-sanitised disclaimer + trailing calc → no 2.40% or 28.024/1168.63."""
        # This is the garbled text produced by earlier passes
        text = (
            "工具未返回完整公告原文或相关比率字段，"
            "因此不计算具体股息率、派息率或收益率）约为2.40%（28.024/1168.63）"
        )
        result = sanitize_unverified_financial_metrics(text)
        assert "2.40%" not in result, f"Percentage survived: {result}"
        assert "28.024/1168.63" not in result, f"Fraction survived: {result}"

    def test_T2_stock_yield_pct_removed(self):
        """T2: '股息率约为2.40%' → no '2.40%' in output."""
        text = "股息率约为2.40%"
        result = sanitize_unverified_financial_metrics(text)
        assert "2.40%" not in result, f"Percentage survived: {result}"

    def test_T3_current_price_calc_removed(self):
        """T3: '以当前股价计算，对应约2.4%' → no '对应约2.4%'."""
        text = "以当前股价计算，对应约2.4%的股息率。"
        result = sanitize_unverified_financial_metrics(text)
        assert "对应约2.4%" not in result, f"Phrase survived: {result}"

    def test_T4_boundary_disclaimer_present(self):
        """T4: output must contain boundary disclaimer text."""
        text = "按当前股价粗算股息率约为2.4%。"
        result = sanitize_unverified_financial_metrics(text)
        assert "不计算具体股息率、派息率或收益率" in result, f"Disclaimer missing: {result}"

    def test_parenthetical_fraction_removed(self):
        """（28.024/1168.63）fraction removed by cleanup."""
        text = "派息金额（28.024/1168.63）约等于股息率。"
        result = sanitize_unverified_financial_metrics(text)
        assert "28.024/1168.63" not in result

    def test_raw_division_removed(self):
        """'28.024÷1168.63' raw arithmetic removed."""
        text = "即28.024÷1168.63。"
        result = sanitize_unverified_financial_metrics(text)
        assert "28.024÷1168.63" not in result
        assert "28.024/1168.63" not in result

    def test_dividend_fact_preserved_through_cleanup(self):
        """Factual '每10股派280.24元' (no ÷) is NOT removed by cleanup patterns."""
        text = "贵州茅台今日分红，每10股派280.24元。"
        result = sanitize_unverified_financial_metrics(text)
        assert "280.24" in result, f"Fact was stripped: {result}"

    def test_verified_context_preserves_yield(self):
        """verified dividend context → cleanup patterns do not run."""
        text = "股息率约为2.40%，对应约2.4%。"
        result = sanitize_unverified_financial_metrics(text, {"dividend_yield": 0.024})
        # With verified context, nothing should be stripped
        assert "2.40%" in result or "2.4%" in result


# ---------------------------------------------------------------------------
# Problem 2 — Dividend-news financial-ability inference (T5–T9)
# ---------------------------------------------------------------------------

class TestDividendInferenceRemoval:
    """T5–T9: sentence-level inference from dividend news must be removed."""

    def test_T5_xianjin_liu_zhuangkuang_removed(self):
        """T5: '反映公司盈利后现金流状况' removed when no verified data."""
        text = "每10股派280.24元，反映公司盈利后现金流状况良好。"
        result = sanitize_dividend_overinference(text)
        assert "反映公司盈利后现金流状况" not in result, f"Not filtered: {result}"
        # Factual part preserved
        assert "280.24" in result

    def test_T6_lishi_tuibi_yingli_removed(self):
        """T6: '历史经验推断公司盈利能力' removed when no verified data."""
        text = "仅依据分红金额和历史经验推断公司盈利能力存在偏差风险。"
        result = sanitize_dividend_overinference(text)
        assert "历史经验推断公司盈利能力" not in result, f"Not filtered: {result}"

    def test_T7_gudong_quanyi_removed(self):
        """T7: '股东权益分配行为' removed."""
        text = "此次分红属于股东权益分配行为，每10股派280元。"
        result = sanitize_dividend_overinference(text)
        assert "股东权益分配行为" not in result, f"Not filtered: {result}"

    def test_T8_boundary_disclaimer_preserved(self):
        """T8: boundary disclaimer is present in output."""
        text = "反映公司盈利后现金流状况，说明盈利质量稳健。"
        result = sanitize_dividend_overinference(text)
        assert "不能进一步判断分红能力、盈利质量或现金流状况" in result, (
            f"Disclaimer missing: {result}"
        )

    def test_T9_verified_no_over_deletion(self):
        """T9: verified_financial_data=True → nothing deleted."""
        text = "反映公司盈利后现金流状况，历史经验推断盈利能力稳定，股东权益分配行为合规。"
        result = sanitize_dividend_overinference(text, {"verified_financial_data": True})
        assert "历史经验推断盈利能力" in result
        assert "股东权益分配行为" in result

    def test_fenhong_xingwei_budeng_tongyu_removed(self):
        """C28.5: '分红行为不能等同于当期财务表现提升' removed."""
        text = "分红行为不能等同于当期财务表现提升，但说明资金状况较好。"
        result = sanitize_dividend_overinference(text)
        assert "当期财务表现" not in result, f"Not filtered: {result}"

    def test_jiyü_fenhong_tuibi_yingli_removed(self):
        """C28.5: '仅依据分红金额...推断...盈利能力' removed."""
        text = "仅依据分红金额推断盈利能力存在偏差风险，请参阅完整财报。"
        result = sanitize_dividend_overinference(text)
        assert "推断盈利能力" not in result, f"Not filtered: {result}"

    def test_full_pipeline_both_filters(self):
        """Full pipeline: both yield cleanup and dividend inference work together."""
        text = (
            "新闻提到贵州茅台今日分红，每10股派280.24元（28.024/1168.63）。"
            "反映公司盈利后现金流状况，盈利质量较好。"
        )
        result = sanitize_financial_answer(text, context=None)
        assert isinstance(result, str)
        assert "280.24" in result                    # fact preserved
        assert "28.024/1168.63" not in result        # fraction removed
        assert "反映公司盈利后现金流状况" not in result  # inference removed
