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
    assert "/Users/" not in text
    assert "api_key" not in text.lower()
    assert "买入" not in text
    assert "一定上涨" not in text
    assert "88%" not in text


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
