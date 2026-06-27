"""
C28.6 Sentence-level Safety Rewrite + Final DataQuality Sync — backend tests.

T1–T5:  Sentence-level dividend over-inference cleanup (Problem 1).
T6–T10: Sentence-level AI theme attribution rewrite (Problem 2).
"""
from __future__ import annotations

import pytest

from app.agents.financial_safety_postprocessor import (
    sanitize_dividend_overinference_sentence_level,
    sanitize_theme_attribution_sentence_level,
    sanitize_financial_answer,
)


# ---------------------------------------------------------------------------
# Problem 1 — Sentence-level dividend over-inference (T1–T5)
# ---------------------------------------------------------------------------

class TestSentenceLevelDividend:
    """No garbled residue from mid-sentence keyword insertion."""

    def test_T1_pure_inference_sentence_deleted(self):
        """T1: '这通常较强、现金流充裕。' is deleted (pure inference, no fact)."""
        text = "这通常较强、现金流充裕。"
        result = sanitize_dividend_overinference_sentence_level(text)
        assert "较强、现金流充裕" not in result, f"Inference survived: {result}"

    def test_T2_mixed_sentence_rewritten_to_fact(self):
        """T2: sentence with fact + inference → rewritten to fact only + disclaimer."""
        text = "新闻显示每10股派280.24元，这通常说明公司现金流充裕。"
        result = sanitize_dividend_overinference_sentence_level(text)
        # Fact preserved
        assert "280.24" in result, f"Fact lost: {result}"
        # Inference removed
        assert "现金流充裕" not in result, f"Inference survived: {result}"
        # Disclaimer present
        assert "工具仅返回新闻标题" in result, f"Disclaimer missing: {result}"

    def test_T3_lishi_yingli_sentence_deleted(self):
        """T3: '分红本身是历史盈利的结果' — whole sentence deleted."""
        text = "分红本身是历史盈利的结果。"
        result = sanitize_dividend_overinference_sentence_level(text)
        assert "历史盈利的结果" not in result, f"Inference survived: {result}"

    def test_T4_double_risk_sentence_deleted(self):
        """T4: '股东权益分配行为，反映公司盈利后现金流状况' — deleted."""
        text = "股东权益分配行为，反映公司盈利后现金流状况。"
        result = sanitize_dividend_overinference_sentence_level(text)
        assert "股东权益分配行为" not in result, f"Risk phrase survived: {result}"
        assert "现金流状况" not in result, f"Risk phrase survived: {result}"

    def test_T5_no_garbled_note_residue(self):
        """T5: garbled '这通常（注…）较强' never appears in output."""
        # This tests that sentence-level runs BEFORE keyword-level (no mid-sentence insert)
        text = "新闻显示每10股派280.24元。这通常说明公司盈利能力较强、现金流充裕。"
        result = sanitize_dividend_overinference_sentence_level(text)
        assert "这通常（注" not in result, f"Garbled residue: {result}"
        assert "）较强" not in result, f"Garbled residue: {result}"

    def test_fact_sentence_preserved(self):
        """Pure fact sentence (no risk terms) is always preserved."""
        text = "新闻提到贵州茅台今日分红，每10股派280.24元。"
        result = sanitize_dividend_overinference_sentence_level(text)
        assert "280.24" in result

    def test_disclaimer_sentence_never_deleted(self):
        """Boundary disclaimer sentence is never removed."""
        disclaimer = (
            "_工具仅返回新闻标题，未提供完整公告原文或财务数据，"
            "因此不能进一步判断分红能力、盈利质量或现金流状况。_"
        )
        text = disclaimer
        result = sanitize_dividend_overinference_sentence_level(text)
        assert "工具仅返回新闻标题" in result

    def test_verified_bypasses_sentence_level(self):
        """verified_financial_data=True → no sentence deletion."""
        text = "这通常说明公司盈利能力较强，现金流充裕。"
        result = sanitize_dividend_overinference_sentence_level(
            text, {"verified_financial_data": True}
        )
        assert "盈利能力" in result

    def test_multi_sentence_only_risk_deleted(self):
        """Multi-sentence text: only the inference sentence is deleted."""
        text = (
            "新闻提到贵州茅台今日分红，每10股派280.24元。"
            "这通常说明公司留存收益充裕、盈利能力较强。"
            "投资者应关注公司后续股价走势。"
        )
        result = sanitize_dividend_overinference_sentence_level(text)
        assert "280.24" in result
        assert "留存收益充裕" not in result
        assert "投资者应关注" in result


# ---------------------------------------------------------------------------
# Problem 2 — Sentence-level AI theme attribution rewrite (T6–T10)
# ---------------------------------------------------------------------------

class TestSentenceLevelTheme:
    """Whole sentences rewritten; no nested/duplicate replacements."""

    def test_T6_ai_chip_upstream_rewritten(self):
        """T6: 'AI算力芯片上游（半导体硅片）' → no 'AI算力芯片上游'."""
        text = "AI算力芯片上游（半导体硅片）是核心受益方。"
        result = sanitize_theme_attribution_sentence_level(text)
        assert "AI算力芯片上游" not in result, f"Risk term survived: {result}"

    def test_T7_nested_keyi_yu_not_duplicated(self):
        """T7: '可能与可能与AI芯片制造上游' → no '可能与可能与'."""
        text = "可能与可能与AI芯片制造上游材料或设备存在间接关联。"
        result = sanitize_theme_attribution_sentence_level(text)
        assert "可能与可能与" not in result, f"Duplicate survived: {result}"
        assert "AI芯片制造上游" not in result, f"Risk term survived: {result}"

    def test_T8_named_entity_rewritten(self):
        """T8: '长电科技作为AI芯片封测龙头' → no 'AI芯片封测龙头'."""
        text = "长电科技作为AI芯片封测龙头，直接受益AI需求爆发。"
        result = sanitize_theme_attribution_sentence_level(text)
        assert "AI芯片封测龙头" not in result, f"Risk term survived: {result}"

    def test_T9_idempotent(self):
        """T9: running sanitizer twice does not change the result."""
        text = "太极实业是AI算力芯片上游关键供应商，真受益方，关联度高。"
        r1 = sanitize_theme_attribution_sentence_level(text)
        r2 = sanitize_theme_attribution_sentence_level(r1)
        assert r1 == r2, f"Not idempotent.\nFirst:  {r1}\nSecond: {r2}"

    def test_T10_boundary_disclaimer_in_output(self):
        """T10: boundary disclaimer appears when any attribution was rewritten."""
        text = "该公司是AI芯片封测龙头，直接受益。"
        result = sanitize_theme_attribution_sentence_level(text)
        assert (
            "热门股榜单" in result or "需进一步通过公告或研报确认" in result
        ), f"Boundary missing: {result}"

    def test_safe_sentence_not_re_processed(self):
        """Sentence already starting with '可能与' (and no risk terms) is preserved."""
        safe = "可能与相关产业链方向存在间接关联，仍需进一步核验。"
        result = sanitize_theme_attribution_sentence_level(safe)
        assert result.startswith('可能与') or '可能与' in result

    def test_verified_preserves_attribution(self):
        """verified_theme_classification=True → no rewrite."""
        text = "该公司是AI芯片封测龙头，直接受益AI芯片需求拉动。"
        result = sanitize_theme_attribution_sentence_level(
            text, {"verified_theme_classification": True}
        )
        assert "AI芯片封测龙头" in result

    def test_full_pipeline_sentence_level_runs_first(self):
        """Full pipeline: sentence-level runs first, no garbled mid-sentence insertion."""
        text = (
            "新闻显示每10股派280.24元，这通常说明公司盈利能力较强。"
            "太极实业是AI芯片封测龙头，关联度高，受益确定。"
        )
        result = sanitize_financial_answer(text, context=None)
        assert isinstance(result, str)
        # No garble
        assert "这通常（注" not in result
        assert "）较强" not in result
        # No nested "可能与可能与"
        assert "可能与可能与" not in result
        # Fact preserved
        assert "280.24" in result
