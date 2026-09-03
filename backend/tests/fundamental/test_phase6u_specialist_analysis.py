from __future__ import annotations

import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest


class CapturingLLM:
    def __init__(self, response: str = "## 结论摘要\n基于输入数据回答。") -> None:
        self.response = response
        self.messages = None

    def chat(self, messages, temperature=0.3):
        self.messages = messages
        return self.response


def _fundamental_snapshot(**overrides):
    snapshot = {
        "company": {"name": "贵州茅台", "industry": "白酒", "business_summary": "白酒生产销售"},
        "valuation": {"pe": None, "pb": None, "ps": None, "market_cap": None, "dividend_yield": None},
        "profitability": {"roe": 0, "gross_margin": 90.1, "net_margin": None},
        "growth": {"revenue_growth_yoy": -1.2, "net_profit_growth_yoy": None},
        "financial_health": {"debt_ratio": 12.3, "operating_cashflow": 0},
        "data_quality": {
            "provider": "unit",
            "latest_report_date": "2024-12-31",
            "data_sources": {"fundamental": "fixture"},
            "missing_fields": ["valuation.pe", "valuation.pb"],
        },
    }
    for key, value in overrides.items():
        snapshot[key] = value
    return snapshot


def _bars(count=20, *, volume=True):
    return [
        {
            "date": f"2026-01-{i + 1:02d}",
            "open": 100 + i,
            "high": 101 + i,
            "low": 99 + i,
            "close": 100.5 + i,
            "volume": (1000 + i) if volume else None,
            "amount": None,
            "amount_estimated": None,
        }
        for i in range(count)
    ]


def _indicators(bar_count=20, *, volume=True):
    return {
        "bar_count": bar_count,
        "latest_close": 120,
        "ma5": 118,
        "ma10": 116,
        "ma20": 114 if bar_count >= 20 else None,
        "ma60": 110 if bar_count >= 60 else None,
        "price_vs_ma20_pct": 5.2 if bar_count >= 20 else None,
        "price_vs_ma60_pct": 9.1 if bar_count >= 60 else None,
        "return_1d_pct": 1.0,
        "return_5d_pct": 2.0,
        "return_20d_pct": 3.0 if bar_count >= 20 else None,
        "high_20d": 130 if bar_count >= 20 else None,
        "low_20d": 100 if bar_count >= 20 else None,
        "high_60d": 140 if bar_count >= 60 else None,
        "low_60d": 90 if bar_count >= 60 else None,
        "volume_latest": 1000 if volume else None,
        "volume_avg_5d": 900 if volume else None,
        "volume_avg_20d": 800 if volume and bar_count >= 20 else None,
        "volume_ratio_5_20": 1.1 if volume and bar_count >= 20 else None,
        "volume_ratio_today": 1.2 if volume else None,
        "short_term_trend": "上行",
        "medium_term_trend": "信号不一致",
        "volume_signal": "数据不足" if not volume else "温和放量",
    }


def _peer_snapshot(period_mismatch=False, single_peer=False):
    peers = [
        {
            "name": "宁德时代",
            "market": "CN",
            "symbol": "300750",
            "fundamentals": {"profitability": {"roe": 12.0}, "valuation": {"pe": None}},
        }
    ]
    if not single_peer:
        peers.append(
            {
                "name": "比亚迪",
                "market": "CN",
                "symbol": "002594",
                "fundamentals": {"profitability": {"roe": 10.0}, "valuation": {"pe": None}},
            }
        )
    return {
        "target": {
            "name": "贵州茅台",
            "market": "CN",
            "symbol": "600519",
            "fundamentals": {"profitability": {"roe": 15.0}, "valuation": {"pe": None}},
        },
        "peers": peers,
        "comparison_fields": {
            "available": ["profitability.roe"],
            "missing_in_target": [],
            "missing_in_all": ["valuation.pe"],
            "missing_in_any_peer": [],
            "candidate": ["profitability.roe", "valuation.pe"],
        },
        "data_quality": {
            "peer_source": "manual",
            "latest_report_dates": {
                "600519": "2024-12-31",
                "300750": "2024-09-30" if period_mismatch else "2024-12-31",
                "002594": "2024-12-31",
            },
        },
    }


def test_phase6u_specialist_fixture_has_40_cases():
    fixture = Path(__file__).parents[1] / "fixtures" / "phase6u_specialist_analysis_cases.json"
    cases = json.loads(fixture.read_text(encoding="utf-8"))
    assert len(cases) == 40
    assert {case["agent"] for case in cases} == {"fundamental", "technical", "news", "peer"}
    assert all(len([c for c in cases if c["agent"] == agent]) >= 10 for agent in {"fundamental", "technical", "news", "peer"})


def test_phase6u_common_formatting_keeps_zero_and_hides_missing_values():
    from app.agents.specialist_analysis_utils import format_money_cny, format_number, format_percent, sanitize_specialist_output

    assert format_percent(0) == "0%"
    assert format_number(0) == "0"
    assert format_money_cny(0) == "0.00 亿元"
    assert format_number(None) == "数据缺失"
    assert format_number(float("nan")) == "数据缺失"
    assert format_number(float("inf")) == "数据缺失"

    text = sanitize_specialist_output(
        "None NaN inf /Users/kaffy/secret api_key=abc 强烈买入 明天一定上涨 88%",
        evidence_text="",
    )
    assert "None" not in text
    assert "NaN" not in text
    assert "inf" not in text
    # Multi-segment path /Users/kaffy/secret is redacted
    assert "/Users/" not in text
    assert "api_key" not in text.lower()
    assert "买入" not in text
    assert "一定上涨" not in text
    # FAIL-CLOSED: when evidence_text is empty, numbers are NOT replaced
    # (avoids global digit corruption when evidence wasn't threaded through)
    assert "88%" in text


def test_phase6u_fundamental_prompt_period_zero_missing_and_narrow_scope():
    from app.agents import fundamental_analyst as mod
    from app.agents.fundamental_analyst import FundamentalAnalystAgent

    prompt = FundamentalAnalystAgent._build_user_prompt(
        "CN",
        "600519",
        _fundamental_snapshot(),
        question="经营现金流怎么样？",
    )

    assert "focus: cashflow" in prompt
    assert "2024-12-31" in prompt
    assert "0%" in prompt
    assert "0.00 亿元" in prompt
    assert "估值数据缺失" in mod._SYSTEM_PROMPT or "估值数据缺失" in prompt
    assert "当前数据无法确认具体原因" in mod._SYSTEM_PROMPT


def test_phase6u_fundamental_output_hardening_removes_unsupported_numbers_and_advice():
    from app.agents.fundamental_analyst import FundamentalAnalystAgent

    llm = CapturingLLM("## 结论摘要\nPE 10 倍，建议买入，路径 /Users/a，api_key=abc，None。")
    agent = FundamentalAnalystAgent(llm=llm, svc=SimpleNamespace(get_fundamentals=lambda market, symbol: _fundamental_snapshot()))
    report = agent.analyze("CN", "600519")

    assert "10" not in report
    assert "买入" not in report
    assert "/Users/" not in report
    assert "api_key" not in report.lower()
    assert "None" not in report


def test_phase6u_technical_prompt_time_range_volume_and_data_insufficient(monkeypatch):
    from app.agents.technical_analyst import TechnicalAnalystAgent

    prompt = TechnicalAnalystAgent._build_user_prompt(
        "CN",
        "600519",
        _bars(5, volume=False),
        quote=None,
        indicators=_indicators(5, volume=False),
        question="成交量如何？",
    )

    assert "focus: volume" in prompt
    assert "K线周期: 日 K" in prompt
    assert "截至日期 2026-01-05" in prompt
    assert "实时报价不可用" in prompt
    assert "MA60 = 数据不足" in prompt
    assert "今日:       数据不足" in prompt


def test_phase6u_technical_output_does_not_keep_fabricated_support_or_prediction(monkeypatch):
    from app.agents import technical_analyst as mod
    from app.agents.technical_analyst import TechnicalAnalystAgent

    monkeypatch.setattr(mod.stock_data_service, "get_kline_for_agent", lambda market, symbol, limit=120: _bars(20))
    monkeypatch.setattr(mod.stock_data_service, "get_quote_optional", lambda market, symbol: None)
    monkeypatch.setattr(mod.technical_indicator_service, "calculate", lambda bars: _indicators(20))

    llm = CapturingLLM("## 结论摘要\n支撑位 88 元，明天确定上涨，建议买入。")
    report = TechnicalAnalystAgent(llm).analyze("CN", "600519")

    assert "88" not in report
    assert "确定上涨" not in report
    assert "买入" not in report


def test_phase6u_news_deduplicates_dates_sources_and_empty_news(monkeypatch):
    from app.agents.news_analyst import _build_user_prompt

    snapshot = {
        "items": [
            {"title": "公司发布公告", "summary": "公告正文", "source": "交易所公告", "publish_time": "2026-07-01", "url": "u1"},
            {"title": "公司发布公告", "summary": "转载", "source": "媒体", "publish_time": "2026-07-01", "url": "u2"},
            {"title": "市场评论称需观察", "summary": "评论", "source": "市场评论", "publish_time": "2026-07-02", "url": ""},
        ],
        "count": 3,
        "data_quality": {"provider": "fixture", "cached": False, "message": ""},
    }
    prompt = _build_user_prompt("CN", "600519", 72, 20, snapshot, question="最近有什么监管新闻？")

    assert "去重后: 2 条" in prompt
    assert prompt.count("公司发布公告") == 1
    assert "发布时间：2026-07-01" in prompt
    assert "来源类型：公司公告/监管披露" in prompt
    assert "focus: regulatory_news" in prompt

    empty_prompt = _build_user_prompt("CN", "600519", 72, 20, {"items": [], "count": 0, "data_quality": {}})
    assert "items 为空" in empty_prompt


def test_phase6u_news_tool_exception_is_limited_and_sanitized(monkeypatch):
    from app.agents import news_analyst as mod
    from app.agents.news_analyst import NewsAnalystAgent

    def boom(**kwargs):
        raise RuntimeError("/Users/kaffy/provider api_key=abc")

    monkeypatch.setattr(mod.news_data_service, "get_stock_news", boom)
    llm = CapturingLLM("## 结论摘要\n没有新闻所以公司无事件，api_key=abc，/Users/x")
    report = NewsAnalystAgent(llm).analyze("CN", "600519")

    assert "api_key" not in report.lower()
    assert "/Users/" not in report


def test_phase6u_peer_prompt_period_mismatch_sample_and_missing_valuation():
    from app.agents.peer_comparison_analyst import PeerComparisonAnalystAgent

    prompt = PeerComparisonAnalystAgent._build_user_prompt(
        "CN",
        "600519",
        _peer_snapshot(period_mismatch=True, single_peer=True),
        question="ROE 和同行比怎么样？",
    )

    assert "focus: roe_peer" in prompt
    assert "报告期不一致警告" in prompt
    assert "不得直接排序" in prompt
    assert "样本少于 2 家" in prompt
    assert "市盈率 PE（valuation.pe）" in prompt
    assert "禁止评价" in prompt


def test_phase6u_peer_output_no_direct_buy_or_unprovided_average():
    from app.agents.peer_comparison_analyst import PeerComparisonAnalystAgent

    llm = CapturingLLM("## 结论摘要\n行业平均 99，最值得买，强烈买入。")
    agent = PeerComparisonAnalystAgent(llm=llm, svc=SimpleNamespace(get_peer_fundamentals=lambda market, symbol: _peer_snapshot()))
    report = agent.analyze("CN", "600519")

    assert "99" not in report
    assert "买入" not in report
    assert "最值得买" not in report


def test_phase6u_route_schemas_and_comprehensive_coordinator_compatibility():
    from app.agents.comprehensive_analysis_coordinator import ComprehensiveAnalysisCoordinator
    from app.routers.analysis import (
        FundamentalAnalysisRequest,
        FundamentalAnalysisResponse,
        NewsAnalysisRequest,
        NewsAnalysisResponse,
        PeerComparisonRequest,
        PeerComparisonResponse,
        TechnicalAnalysisRequest,
        TechnicalAnalysisResponse,
    )

    assert TechnicalAnalysisResponse(**TechnicalAnalysisRequest(market="CN", symbol="600519").model_dump(), report="ok").report == "ok"
    assert FundamentalAnalysisResponse(**FundamentalAnalysisRequest(market="CN", symbol="600519").model_dump(), report="ok").report == "ok"
    assert PeerComparisonResponse(**PeerComparisonRequest(market="CN", symbol="600519").model_dump(), report="ok").report == "ok"
    assert NewsAnalysisResponse(**NewsAnalysisRequest(market="CN", symbol="600519").model_dump(), report="ok").report == "ok"

    coordinator = ComprehensiveAnalysisCoordinator(CapturingLLM())
    assert coordinator._technical is not None
    assert coordinator._fundamental is not None
    assert coordinator._peer is not None
    assert coordinator._news is not None


# ===========================================================================
# Phase 6W-R1 P0-A/P0-B — remove_unsupported_numbers & _ABS_PATH_RE fixes
# ===========================================================================

class TestRemoveUnsupportedNumbersP0A:
    """5 regression cases for the overhauled remove_unsupported_numbers()."""

    def setup_method(self):
        from app.agents.specialist_analysis_utils import remove_unsupported_numbers
        self._fn = remove_unsupported_numbers

    def test_case_a_empty_evidence_fail_closed(self):
        """Case A: empty evidence_text → text is returned unchanged (no corruption)."""
        text = "净利润为 1,315.90 亿元，同比增长 +19.80%，日期 2024-01-01。"
        result = self._fn(text, evidence_text="")
        # Must not replace anything — fail-closed
        assert "1,315.90" in result or "1315.90" in result or "315.90" in result, \
            "fail-closed: numbers must NOT be replaced when evidence is empty"
        assert "未提供数字" not in result, \
            "fail-closed: '未提供数字' must not appear when evidence is empty"

    def test_case_b_no_partial_match_corruption(self):
        """Case B: token-level substitution must not split '1315.90' into '131' + '5.90'."""
        # Evidence has 1315.90 so it should be kept; 999 is fabricated so replaced.
        evidence = "净利润 1315.90 亿元"
        text = "净利润 1315.90 亿元，另有虚构数字 999 亿元。"
        result = self._fn(text, evidence_text=evidence)
        assert "1315.90" in result, "1315.90 is in evidence → must be preserved"
        assert "1315未提供数字" not in result, "partial-match corruption must not occur"
        assert "未提供数字" in result, "fabricated 999 should be replaced"

    def test_case_c_canonical_equivalence_trailing_zeros(self):
        """Case C: '1315.90' in text matches evidence '1315.9' (same canonical value)."""
        evidence = "净利润 1315.9 亿元"
        text = "净利润 1315.90 亿元。"  # trailing zero form
        result = self._fn(text, evidence_text=evidence)
        assert "1315.90" in result, \
            "1315.90 and 1315.9 are canonically equal — must preserve 1315.90"
        assert "未提供数字" not in result

    def test_case_d_canonical_equivalence_leading_plus_pct(self):
        """Case D: '+19.80%' in text matches evidence '19.8%' via canonicalization."""
        evidence = "同比增长 19.8%"
        text = "同比增长 +19.80%，符合预期。"
        result = self._fn(text, evidence_text=evidence)
        assert "+19.80%" in result, \
            "+19.80% and 19.8% are canonically equal — must be preserved"
        assert "未提供数字" not in result

    def test_case_e_comma_thousands_separator(self):
        """Case E: '1,315.90' in text matches evidence '1315.90' (comma stripped)."""
        evidence = "营收 1315.90 亿元"
        text = "营收 1,315.90 亿元。"
        result = self._fn(text, evidence_text=evidence)
        # Comma-separated form in text must be recognized as matching evidence
        assert "未提供数字" not in result, \
            "1,315.90 with comma should match evidence 1315.90"


class TestAbsPathReP0B:
    """P0-B: _ABS_PATH_RE must not create false positives for technical tokens."""

    def setup_method(self):
        from app.agents.specialist_analysis_utils import _ABS_PATH_RE
        self._re = _ABS_PATH_RE

    def test_multi_segment_real_path_is_matched(self):
        """Real filesystem paths with ≥2 segments must still be redacted."""
        text = "路径 /usr/lib/python3.11 和 /app/data/report.pdf"
        matches = self._re.findall(text)
        assert len(matches) == 2, f"Expected 2 path matches, got: {matches}"

    def test_single_segment_not_matched(self):
        """Single-segment tokens like /MA5, /day, /v2 must NOT be matched."""
        for token in ["/MA5", "/day", "/v2", "/api", "/data"]:
            assert not self._re.search(token), \
                f"Single-segment token {token!r} must NOT match _ABS_PATH_RE"

    def test_technical_indicator_no_false_positive(self):
        """Technical indicator text must not produce 'MA5[path]' artifacts."""
        from app.agents.specialist_analysis_utils import sanitize_specialist_output
        text = "均线系统：MA5=120.5，MA10=118.3，MA20=115.0，均线多头排列。"
        evidence = "MA5=120.5 MA10=118.3 MA20=115.0"
        result = sanitize_specialist_output(text, evidence_text=evidence)
        assert "[path]" not in result, \
            f"Technical indicator text must not generate [path] artifacts; got: {result!r}"
        assert "MA5" in result, "MA5 must be preserved"

    def test_date_slash_notation_not_matched(self):
        """Date references like 2024/01/01 must not be falsely matched."""
        # Dates start with digits, not /, so should never match _ABS_PATH_RE
        text = "报告日期：2024/01/01 至 2024/12/31。"
        assert not self._re.search(text), \
            "Date slash notation must not match _ABS_PATH_RE"


class TestValidateNumericClaimsR1_1A:
    """Phase 6W-R1.1 Blocking-A: validate_numeric_claims() structured validation.

    Three new E2E cases (Cases 1, 2, 3) verifying that callers receive
    structured state so evidence-missing outputs cannot be published as success.
    """

    def setup_method(self):
        from app.agents.specialist_analysis_utils import validate_numeric_claims
        self._fn = validate_numeric_claims

    def test_case_1_empty_evidence_with_numbers_returns_invalid(self):
        """Case 1: text has numerics, evidence is absent → valid=False, reason=numeric_evidence_missing.

        Callers must NOT publish status='success' when this result is returned.
        """
        text = "净利润 1315.90 亿元，同比增长 +19.80%。"
        result = self._fn(text, evidence_text="")
        assert result["valid"] is False, \
            "Without evidence, numeric claims cannot be verified → valid must be False"
        assert result["reason"] == "numeric_evidence_missing", \
            f"Expected 'numeric_evidence_missing', got {result['reason']!r}"
        assert result["evidence_available"] is False
        # unsupported_tokens is [] because fail-closed returns text unchanged
        # (we can't enumerate which tokens are unsupported without a replacement pass)

    def test_case_2_empty_evidence_no_numbers_returns_valid(self):
        """Case 2: text has NO numerics and evidence is absent → valid=True.

        A purely qualitative response with no numbers is safe to publish even
        without evidence text.
        """
        text = "公司主营业务为白酒生产与销售，品牌护城河较深。"
        result = self._fn(text, evidence_text="")
        assert result["valid"] is True, \
            "Text with no numeric claims is valid even without evidence"
        assert result["reason"] == "ok"
        assert result["evidence_available"] is False

    def test_case_3_evidence_present_unsupported_numbers_returns_invalid(self):
        """Case 3: evidence provided but text has fabricated numbers → valid=False.

        When evidence covers 1315.90 but text also claims fabricated 999,
        validate_numeric_claims must flag 999 as unsupported.
        """
        evidence = "净利润 1315.90 亿元"
        text = "净利润 1315.90 亿元，另有资产 999 亿元，增长 42%。"
        result = self._fn(text, evidence_text=evidence)
        assert result["valid"] is False, \
            "Fabricated numbers (999, 42) not in evidence → valid must be False"
        assert result["reason"] == "unsupported_numbers_found"
        assert result["evidence_available"] is True
        # Both 999 and 42 are not in evidence
        unsupported = result["unsupported_tokens"]
        assert any("999" in t for t in unsupported), \
            f"999 must be listed as unsupported; got {unsupported}"

    def test_case_evidence_fully_covered_returns_valid(self):
        """Bonus: when every numeric in text matches evidence → valid=True."""
        evidence = "净利润 1315.90 亿元 增长 19.8%"
        text = "净利润 1315.90 亿元，同比增长 +19.80%。"
        result = self._fn(text, evidence_text=evidence)
        assert result["valid"] is True
        assert result["reason"] == "ok"
        assert result["evidence_available"] is True
        assert result["unsupported_tokens"] == []


class TestHasSanitizationArtifactsR1_1A:
    """Phase 6W-R1.1 Blocking-A: has_sanitization_artifacts() quality gate."""

    def setup_method(self):
        from app.agents.specialist_analysis_utils import has_sanitization_artifacts
        self._fn = has_sanitization_artifacts

    def test_clean_text_returns_false(self):
        assert self._fn("净利润 1315.90 亿元，同比增长 19.8%。") is False

    def test_replaced_number_marker_returns_true(self):
        assert self._fn("净利润 未提供数字 亿元。") is True

    def test_path_artifact_returns_true(self):
        assert self._fn("路径 [path] 中存在文件。") is True

    def test_both_artifacts_returns_true(self):
        assert self._fn("数字 未提供数字，路径 [path]") is True
