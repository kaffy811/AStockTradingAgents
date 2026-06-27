"""
C28.4 Final Browser Acceptance Patch — backend tests.

T7–T11: Sentence-level dividend over-inference filter.
T12–T16: Enhanced AI theme attribution downgrade.
"""
from __future__ import annotations

import pytest

from app.agents.financial_safety_postprocessor import (
    sanitize_dividend_overinference,
    sanitize_theme_attribution,
    sanitize_financial_answer,
)


# ---------------------------------------------------------------------------
# Problem 3 — Sentence-level dividend over-inference (C28.4)
# ---------------------------------------------------------------------------

class TestSentenceLevelDividendFilter:
    """T7–T11: new sentence-level patterns from browser validation."""

    def test_T7_fanying_xianjin_liu_replaced(self):
        """T7: '反映公司盈利后现金流状况' replaced."""
        text = "每10股派280.24元，反映公司盈利后现金流状况良好。"
        result = sanitize_dividend_overinference(text)
        assert "反映公司盈利后现金流状况" not in result, f"Not filtered: {result}"
        # Fact preserved
        assert "280.24" in result

    def test_T8_lishi_jingyan_tuibi_replaced(self):
        """T8: '历史经验推断公司盈利能力' replaced."""
        text = "从历史经验推断公司盈利能力较强，且分红稳定。"
        result = sanitize_dividend_overinference(text)
        assert "历史经验推断公司盈利能力" not in result, f"Not filtered: {result}"

    def test_T9_gudong_quanyi_fenpei_replaced(self):
        """T9: '股东权益分配行为' softened."""
        text = "此次分红属于股东权益分配行为，每10股派280元。"
        result = sanitize_dividend_overinference(text)
        assert "股东权益分配行为" not in result, f"Not filtered: {result}"

    def test_T10_fact_preserved(self):
        """T10: factual '每10股派280.24元' is preserved through all filters."""
        text = (
            "新闻提到贵州茅台今日分红，每10股派280.24元。"
            "反映公司盈利后现金流状况，盈利质量较好。"
        )
        result = sanitize_dividend_overinference(text)
        # Fact must survive
        assert "280.24" in result, f"Fact was lost: {result}"
        assert "今日分红" in result or "分红" in result

    def test_T11_disclaimer_appended(self):
        """T11: boundary disclaimer appears when any pattern fires."""
        text = "反映公司盈利后现金流状况，说明盈利质量稳健。"
        result = sanitize_dividend_overinference(text)
        assert "不能进一步判断分红能力" in result, f"Disclaimer missing: {result}"

    def test_sentence_level_fenhong_yingli_neng_li(self):
        """Sentence containing 分红 + 盈利能力 replaced at clause level."""
        text = "今年分红金额较高，盈利能力较强，分红能力充足。"
        result = sanitize_dividend_overinference(text)
        # Either 盈利能力 or 分红能力 should be gone
        assert "盈利能力较强" not in result or "分红能力充足" not in result

    def test_fanying_yingli_zhi_liang(self):
        """'说明盈利质量稳健' type replaced."""
        text = "该分红说明盈利质量稳健，为投资者提供可持续回报。"
        result = sanitize_dividend_overinference(text)
        assert "盈利质量稳健" not in result

    def test_verified_bypasses_all_new_c284_patterns(self):
        """verified_financial_data=True bypasses C28.4 patterns too."""
        text = "反映公司盈利后现金流状况良好，历史经验推断盈利能力稳定。"
        result = sanitize_dividend_overinference(text, {"verified_financial_data": True})
        assert "历史经验推断盈利能力" in result


# ---------------------------------------------------------------------------
# Problem 4 — Enhanced AI theme attribution (C28.4)
# ---------------------------------------------------------------------------

class TestEnhancedAIThemeAttribution:
    """T12–T16: C28.4 AI-specific patterns."""

    def test_T12_ai_suanli_chip_upstream_downgraded(self):
        """T12: 'AI算力芯片上游' downgraded."""
        text = "该公司是AI算力芯片上游核心供应商，受益确定。"
        result = sanitize_theme_attribution(text)
        assert "AI算力芯片上游" not in result, f"Not filtered: {result}"

    def test_T13_ai_chip_fengce_longto_downgraded(self):
        """T13: 'AI芯片封测龙头' downgraded."""
        text = "TCL中环作为AI芯片封测龙头，直接受益AI需求爆发。"
        result = sanitize_theme_attribution(text)
        assert "AI芯片封测龙头" not in result, f"Not filtered: {result}"

    def test_T14_guanlian_du_gao_downgraded(self):
        """T14: 'AI...关联度高' downgraded."""
        text = "与AI穿戴、AI眼镜、AR/VR等终端设备关联度高。"
        result = sanitize_theme_attribution(text)
        # Should no longer say "关联度高" without qualification
        assert "关联度高" not in result, f"Not filtered: {result}"

    def test_T15_zhenshouyi_downgraded(self):
        """T15: '真受益' downgraded."""
        text = "太极实业是AI封装产业链真受益方，直接受益。"
        result = sanitize_theme_attribution(text)
        assert "真受益" not in result, f"Not filtered: {result}"

    def test_T16_boundary_disclaimer_present(self):
        """T16: boundary disclaimer appears in response."""
        text = "AI算力芯片上游，AI芯片封测龙头，真受益方。"
        result = sanitize_theme_attribution(text)
        assert "热门股榜单" in result or "需进一步通过公告或研报确认" in result, (
            f"Boundary missing: {result}"
        )

    def test_verified_preserves_ai_attribution(self):
        """verified_theme_classification=True preserves all AI attributions."""
        text = "AI算力芯片上游，AI芯片封测龙头，关联度高，真受益。"
        result = sanitize_theme_attribution(text, {"verified_theme_classification": True})
        assert "AI算力芯片上游" in result
        assert "AI芯片封测龙头" in result
        assert "真受益" in result

    def test_ai_display_glass_downgraded(self):
        """'AI显示/玻璃基板概念' downgraded."""
        text = "京东方A是AI显示玻璃基板概念龙头。"
        result = sanitize_theme_attribution(text)
        assert "AI显示玻璃基板概念" not in result

    def test_zijin_zhongjin_zhuizhu_downgraded(self):
        """'资金重点追逐上游材料+关键设备' downgraded."""
        text = "资金重点追逐上游材料+关键设备，逻辑清晰。"
        result = sanitize_theme_attribution(text)
        assert "资金重点追逐上游材料" not in result

    def test_full_pipeline_applies_both(self):
        """Full pipeline applies both dividend and theme filters."""
        text = (
            "反映公司现金流状况，历史经验推断盈利能力，"
            "AI算力芯片上游真受益方，AI芯片封测龙头。"
        )
        result = sanitize_financial_answer(text, context=None)
        assert isinstance(result, str)
        # At least some of the strong phrases should be gone
        assert ("AI算力芯片上游" not in result or
                "历史经验推断盈利能力" not in result or
                "真受益" not in result)
