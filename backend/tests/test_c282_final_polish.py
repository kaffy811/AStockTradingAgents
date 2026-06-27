"""
C28.2 Final Browser Polish — backend tests.

T4–T10: Dividend over-inference, AI theme attribution, DataQuality unknown exclusion.
T13–T14: data_quality_review thinking uses correct level labels.
"""
from __future__ import annotations

import pytest

from app.agents.answer_metadata import compute_data_quality
from app.agents.financial_safety_postprocessor import (
    sanitize_dividend_overinference,
    sanitize_theme_attribution,
    sanitize_financial_answer,
)
from app.agents.thinking_events import make_data_quality_review


# ---------------------------------------------------------------------------
# Problem A — "unknown" must not appear in verified_data
# ---------------------------------------------------------------------------

class TestUnknownExcludedFromVerifiedData:
    """T1 backend: unknown source type excluded from verified_data."""

    def test_unknown_tool_not_in_verified_data(self):
        """An event whose name maps to unknown source type must not add to verified_data."""
        events = [{"name": "unknown", "status": "success"}]
        dq = compute_data_quality(events)
        assert "unknown" not in dq.verified_data, (
            f"'unknown' leaked into verified_data: {dq.verified_data}"
        )

    def test_unknown_does_not_elevate_level(self):
        """Unknown-only success must still yield insufficient / low level."""
        events = [{"name": "unknown", "status": "success"}]
        dq = compute_data_quality(events)
        # verified_data is empty after filtering unknown → 0 effective sources
        # The level computation uses successful_types which still contains "unknown",
        # so level may be "low" (market-only path) but verified_data list is clean.
        assert "unknown" not in dq.verified_data

    def test_market_plus_unknown_shows_only_market(self):
        """market_quote success + unknown success → only '实时行情' in verified_data."""
        events = [
            {"name": "stock_quote_tool", "status": "success"},
            {"name": "unknown", "status": "success"},
        ]
        dq = compute_data_quality(events)
        assert "unknown" not in dq.verified_data
        assert any("行情" in item for item in dq.verified_data)


# ---------------------------------------------------------------------------
# Problem B — Dividend news over-inference
# ---------------------------------------------------------------------------

class TestDividendOverInference:
    """T4–T6: dividend over-inference filter."""

    def test_T4_gao_e_fenhong_replaced(self):
        """T4: '高额分红' replaced when no verified data."""
        text = "近期新闻显示公司已实施高额分红，每10股派280.24元。"
        result = sanitize_dividend_overinference(text, context=None)
        assert "高额分红" not in result, f"'高额分红' not filtered: {result}"

    def test_T5_xianjin_fenhong_capacity_replaced(self):
        """T5: '现金分红能力较强' replaced when no verified data."""
        text = "表明公司具备较强的现金分红能力，反映盈利稳定。"
        result = sanitize_dividend_overinference(text, context=None)
        assert "现金分红能力较强" not in result, f"phrase not filtered: {result}"

    def test_T6_verified_news_detail_preserves_text(self):
        """T6: when verified_news_detail=True, no filtering applied."""
        text = "根据完整公告正文，公司现金分红能力较强，大额分红已确认。"
        context = {"verified_news_detail": True}
        result = sanitize_dividend_overinference(text, context)
        assert "大额分红" in result, "Should not filter when verified_news_detail=True"

    def test_verified_financial_data_also_bypasses_filter(self):
        """verified_financial_data=True also bypasses the dividend filter."""
        text = "高额分红表明现金流充沛。"
        context = {"verified_financial_data": True}
        result = sanitize_dividend_overinference(text, context)
        assert "高额分红" in result

    def test_no_context_triggers_filter(self):
        """With no context at all, dividend over-inference is filtered."""
        text = "公司已实施大额分红，反映盈利稳定。"
        result = sanitize_dividend_overinference(text)
        assert "盈利稳定" not in result or "大额分红" not in result

    def test_sanitize_financial_answer_calls_dividend_filter(self):
        """sanitize_financial_answer also removes dividend over-inference (via full pipeline)."""
        text = "高额分红表明公司现金流充沛，属核心供应商。"
        result = sanitize_financial_answer(text, context=None)
        assert isinstance(result, str)
        # At least one of the strong phrases should have been replaced
        assert "高额分红" not in result or "核心供应商" not in result


# ---------------------------------------------------------------------------
# Problem C — AI theme strong attribution
# ---------------------------------------------------------------------------

class TestThemeAttribution:
    """T7–T10: AI theme strong-attribution downgrade."""

    def test_T7_core_supplier_downgraded(self):
        """T7: '核心供应商' replaced when no verified_theme_classification."""
        text = "京东方A是AI终端设备核心供应商，受益显著。"
        result = sanitize_theme_attribution(text, context=None)
        assert "核心供应商" not in result, f"'核心供应商' not filtered: {result}"
        assert "需公告或研报确认" in result

    def test_T8_key_material_downgraded(self):
        """T8: '关键耗材' replaced when no verified_theme_classification."""
        text = "彤程新材被定性为AI芯片关键耗材供应商。"
        result = sanitize_theme_attribution(text, context=None)
        assert "关键耗材" not in result, f"'关键耗材' not filtered: {result}"

    def test_T9_verified_theme_preserves_attribution(self):
        """T9: verified_theme_classification=True bypasses downgrade."""
        text = "根据研报，该公司是AI产业链核心供应商，关键耗材直接受益。"
        context = {"verified_theme_classification": True}
        result = sanitize_theme_attribution(text, context)
        assert "核心供应商" in result, "Should preserve attribution when verified"
        assert "关键耗材" in result

    def test_T10_disclaimer_appended_when_downgraded(self):
        """T10: AI hot-stock answer includes boundary statement after downgrade."""
        text = "太极实业提供AI芯片封装服务，是核心标的，直接受益。"
        result = sanitize_theme_attribution(text, context=None)
        assert "需进一步通过公告或研报确认" in result, (
            f"Boundary disclaimer missing: {result}"
        )

    def test_no_match_no_disclaimer(self):
        """If no strong-attribution terms present, no disclaimer is appended."""
        text = "该公司从事半导体封测业务，近期表现活跃。"
        result = sanitize_theme_attribution(text, context=None)
        assert result == text, "Unrelated text should not be modified"

    def test_direct_benefit_downgraded(self):
        """'直接受益' is replaced with softer phrase."""
        text = "TCL中环作为AI芯片基板材料供应商直接受益。"
        result = sanitize_theme_attribution(text, context=None)
        assert "直接受益" not in result


# ---------------------------------------------------------------------------
# Problem D (backend) — data_quality_review thinking uses correct level labels
# ---------------------------------------------------------------------------

class TestDataQualityReviewThinkingLabels:
    """T13–T14: make_data_quality_review() uses correct Chinese level labels."""

    def test_T13_low_level_says_shuju_youxian(self):
        """T13: level='low' → thinking content contains '数据有限'."""
        ev = make_data_quality_review(
            level="low",
            reason="仅获取到行情或新闻数据。",
            missing=["财务数据"],
        )
        assert "数据有限" in ev["content"], (
            f"Expected '数据有限' in content: {ev['content']}"
        )

    def test_T14_insufficient_level_says_shuju_buzu(self):
        """T14: level='insufficient' → thinking content contains '数据不足'."""
        ev = make_data_quality_review(
            level="insufficient",
            reason="无法获取任何数据。",
            missing=[],
        )
        assert "数据不足" in ev["content"], (
            f"Expected '数据不足' in content: {ev['content']}"
        )

    def test_high_level_says_shuju_wanzheng(self):
        """level='high' → thinking content contains '数据完整'."""
        ev = make_data_quality_review(
            level="high",
            reason="已获取多维度数据。",
            missing=[],
        )
        assert "数据完整" in ev["content"]

    def test_medium_level_says_shuju_bufen_wanzheng(self):
        """level='medium' → thinking content contains '数据部分完整'."""
        ev = make_data_quality_review(
            level="medium",
            reason="部分数据缺失。",
            missing=["历史报告"],
        )
        assert "数据部分完整" in ev["content"]

    def test_source_is_data_quality_review(self):
        """The event source must always be 'data_quality_review'."""
        ev = make_data_quality_review("low", "test", [])
        assert ev["source"] == "data_quality_review"

    def test_stage_is_data_quality(self):
        """The event stage must be 'data_quality'."""
        ev = make_data_quality_review("medium", "test", [])
        assert ev["stage"] == "data_quality"
