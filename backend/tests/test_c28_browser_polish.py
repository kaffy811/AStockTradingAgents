"""
C28.1 Browser Polish — backend unit tests T1-T18.

Tests cover:
  T3-T8   : financial_agent.py preamble stripper + safety postprocessor
  T9-T11  : thinking_sanitizer.py skill name mapping
  T12-T15 : answer_metadata.py DataQuality logic
  T16-T18 : answer_metadata.py build_source_refs friendly titles
"""
from __future__ import annotations

import pytest

# ── T3-T6: _strip_model_preamble + financial_safety_postprocessor ─────────────

from app.agents.financial_agent import _strip_model_preamble


def test_T3_strip_preamble_before_section_header():
    """T3: _strip_model_preamble removes '我们分析用户问题' before ###"""
    raw = "我们分析用户问题：茅台，根据工具数据，以下是分析结果：\n\n### 研究摘要\n\n茅台是白酒龙头。"
    result = _strip_model_preamble(raw)
    assert result.startswith("### 研究摘要")
    assert "我们分析" not in result


def test_T3b_strip_preamble_no_headers_selfref():
    """_strip_model_preamble on text with no headers, but explicit opener."""
    raw = "好的，以下是针对茅台的分析结果：\n\n茅台是A股白酒龙头企业。"
    result = _strip_model_preamble(raw)
    # Should remove the opener line
    assert "好的" not in result or "茅台是A股" in result


# ── T4-T6: financial_safety_postprocessor dividend_yield patterns ─────────────

from app.agents.financial_safety_postprocessor import sanitize_unverified_financial_metrics

_REPLACEMENT = "（工具未返回完整公告原文或相关比率字段，因此不计算具体股息率、派息率或收益率）"


def test_T4_dividend_yield_yuewei():
    """T4: '股息率约为2.40%' gets replaced."""
    text = "当前股息率约为2.40%，吸引力较高。"
    result = sanitize_unverified_financial_metrics(text)
    assert _REPLACEMENT in result
    assert "2.40%" not in result


def test_T5_dividend_yield_arithmetic():
    """T5: '28.024 ÷ 1168.63 = 2.4%' gets replaced."""
    text = "分红总额28.024÷1168.63=2.4%，股东回报较好。"
    result = sanitize_unverified_financial_metrics(text)
    assert _REPLACEMENT in result


def test_T6_dividend_yield_current_price_calc():
    """T6: '以当前股价计算' gets replaced."""
    text = "以当前股价计算，估算年化收益。"
    result = sanitize_unverified_financial_metrics(text)
    assert _REPLACEMENT in result
    assert "以当前股价计算" not in result


# ── T7-T8: sanitize_financial_answer applied to dict/str ─────────────────────

from app.agents.financial_safety_postprocessor import sanitize_financial_answer


def test_T7_sanitize_dict_final_answer():
    """T7: dict finalAnswer fields also get sanitized."""
    payload = {
        "summary": "股息率约为3%，回报较高。",
        "analysis": "按当前股价计算股息率为3%。",
        "disclaimer": "仅供参考",
    }
    result = sanitize_financial_answer(payload)
    assert _REPLACEMENT in result["summary"]
    assert "3%" not in result["summary"]


def test_T8_sanitize_dict_analysis_field():
    """T8: dict finalAnswer.analysis also gets sanitized."""
    payload = {
        "summary": "公司基本面稳健",
        "analysis": "粗算股息率为2.5%，投资价值明显。",
    }
    result = sanitize_financial_answer(payload)
    assert _REPLACEMENT in result["analysis"]
    assert "2.5%" not in result["analysis"]


# ── T9-T11: thinking_sanitizer skill name mapping ─────────────────────────────

from app.agents.thinking_sanitizer import sanitize_thinking_content


def test_T9_thinking_general_financial_answer_skill():
    """T9: thinking content with general_financial_answer_skill → replaced."""
    raw = "当前调用 general_financial_answer_skill 处理用户问题。"
    result = sanitize_thinking_content(raw, max_chars=500)
    assert "general_financial_answer_skill" not in result
    assert "智能问答" in result


def test_T10_thinking_report_explanation_skill():
    """T10: thinking content with report_explanation_skill → replaced."""
    raw = "使用 report_explanation_skill 读取年报内容。"
    result = sanitize_thinking_content(raw, max_chars=500)
    assert "report_explanation_skill" not in result
    assert "报告解读" in result


def test_T11_thinking_no_snake_case_skill_names():
    """T11: final thinking payload does not contain snake_case skill names."""
    raw = (
        "系统将使用 financial_rag_search 进行检索，"
        "同时通过 universal_market_search 获取市场数据，"
        "并用 general_financial_answer_skill 生成答复。"
    )
    result = sanitize_thinking_content(raw, max_chars=1000)
    for name in ["financial_rag_search", "universal_market_search", "general_financial_answer_skill"]:
        assert name not in result, f"Snake-case name '{name}' leaked into thinking output"


# ── T12-T15: DataQuality level logic ─────────────────────────────────────────

from app.agents.answer_metadata import compute_data_quality


def test_T12_quote_news_success_report_missing_level_low():
    """T12: quote+news success, report missing → level=low."""
    events = [
        {"name": "get_stock_quote_tool", "status": "success"},
        {"name": "get_news_tool",        "status": "success"},
        {"name": "get_financials_tool",  "status": "failed"},
    ]
    dq = compute_data_quality(events)
    assert dq.level == "low"


def test_T13_no_useful_data_level_insufficient():
    """T13: no useful data → level=insufficient."""
    events = [
        {"name": "get_stock_quote_tool", "status": "failed"},
        {"name": "get_news_tool",        "status": "failed"},
    ]
    dq = compute_data_quality(events)
    assert dq.level == "insufficient"


def test_T14_historical_report_success_level_high_or_medium():
    """T14: historical report detail success → level=high or medium."""
    events = [
        {"name": "get_report_detail_tool", "status": "success"},
        {"name": "get_stock_quote_tool",   "status": "success"},
    ]
    dq = compute_data_quality(events)
    assert dq.level in ("high", "medium")


def test_T15_low_level_missing_data_includes_report():
    """T15: DataQuality low → missing_data mentions 最新已披露定期报告."""
    events = [
        {"name": "get_stock_quote_tool", "status": "success"},
        {"name": "get_news_tool",        "status": "success"},
    ]
    dq = compute_data_quality(events)
    assert dq.level == "low"
    assert "最新已披露定期报告" in dq.missing_data
    # verified_data should include market data
    assert any("行情" in v or "市场" in v or "新闻" in v for v in dq.verified_data)


# ── T16-T18: build_source_refs friendly titles ───────────────────────────────

from app.agents.answer_metadata import build_source_refs


def test_T16_source_ref_title_not_raw_rag_retrieve():
    """T16: SourceRef title not 'rag_retrieve'."""
    events = [
        {"name": "rag_retrieve", "status": "success", "detail": ""},
    ]
    refs = build_source_refs(events)
    for ref in refs:
        assert ref.title != "rag_retrieve", f"Raw 'rag_retrieve' leaked into SourceRef title: {ref.title}"


def test_T17_unknown_provider_maps_to_friendly_label():
    """T17: unknown provider maps to '来源未标注' in display."""
    events = [
        {"name": "unknown", "status": "success", "detail": ""},
    ]
    refs = build_source_refs(events)
    for ref in refs:
        assert ref.title != "unknown"
        # Should use friendly label
        assert ref.title in ("来源未标注", "工具结果", "参考资料") or ref.title


def test_T18_rag_retrieve_event_gets_friendly_title():
    """T18: build_source_refs with 'rag_retrieve' event → friendly title."""
    events = [
        {"name": "rag_retrieve", "status": "success", "detail": "retrieved 5 docs"},
    ]
    refs = build_source_refs(events)
    assert len(refs) >= 1
    ref = refs[0]
    assert ref.title == "金融知识库资料"
    assert ref.source_type == "rag"
