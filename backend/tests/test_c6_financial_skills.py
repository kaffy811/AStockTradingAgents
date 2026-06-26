"""
C6 Financial Skills — unit tests.

Tests verify:
  1. can_handle() returns True for known matching inputs
  2. Graceful partial result on tool failure
  3. Empty watchlist state
  4. All skills include _DISCLAIMER in answer
  5. No forbidden phrases
  6. skill_name always set
"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.chat_skills.base import SkillContext, _DISCLAIMER
from app.agents.chat_skills.stock_anomaly_skill import StockAnomalySkill
from app.agents.chat_skills.risk_first_skill import RiskFirstSkill
from app.agents.chat_skills.news_catalyst_skill import NewsCatalystSkill
from app.agents.chat_skills.watchlist_review_skill import WatchlistReviewSkill
from app.agents.chat_skills.industry_hotspot_skill import IndustryHotspotSkill
from app.agents.chat_skills.report_explanation_skill import ReportExplanationSkill
from app.agents.chat_tools.tool_result import ToolResult

FORBIDDEN_PHRASES = ["买入", "卖出", "持有", "目标价"]
_DISCLAIMER_STRIPPED = _DISCLAIMER.strip()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ok_resolve(symbol: str = "688146", name: str = "中船特气") -> ToolResult:
    return ToolResult(
        ok=True, tool_name="resolve_stock_tool",
        summary=f"CN/{symbol} → {name}",
        data={"market": "CN", "symbol": symbol, "name": name},
    )


def _ok_quote() -> ToolResult:
    return ToolResult(
        ok=True, tool_name="get_quote_tool",
        summary="当前价 330.5（+12.30%）",
        data={"market": "CN", "symbol": "688146", "name": "中船特气",
              "price": "330.5", "change_pct": "+12.30%", "change_dir": "up"},
        cards=[{"type": "stock_summary", "data": {}}],
    )


def _ok_kline() -> ToolResult:
    return ToolResult(
        ok=True, tool_name="get_kline_summary_tool",
        summary="近20日涨幅 +147.87%",
        data={"market": "CN", "symbol": "688146",
              "bars_count": 20, "period_change_pct": 147.87, "bars_sample": []},
    )


def _ok_news() -> ToolResult:
    return ToolResult(
        ok=True, tool_name="get_latest_news_tool",
        summary="获取近72小时新闻 1 条",
        data={
            "market": "CN", "symbol": "688146",
            "items": [{"title": "中船特气公告", "summary": "...", "source": "新浪财经",
                       "publish_time": "2026-06-12T00:00:00", "url": ""}],
            "count": 1,
        },
    )


def _ok_watchlist_with_items() -> ToolResult:
    return ToolResult(
        ok=True, tool_name="get_watchlist_tool",
        summary="自选股 2 只",
        data={
            "items": [
                {"market": "CN", "symbol": "688146", "name": "中船特气"},
                {"market": "CN", "symbol": "600519", "name": "贵州茅台"},
            ],
            "count": 2,
            "already_in": False,
        },
        cards=[{"type": "watchlist_list", "data": {}}],
    )


def _ok_watchlist_empty() -> ToolResult:
    return ToolResult(
        ok=True, tool_name="get_watchlist_tool",
        summary="自选股 0 只",
        data={"items": [], "count": 0, "already_in": False},
        cards=[],
    )


def _ok_industry_hot() -> ToolResult:
    return ToolResult(
        ok=True, tool_name="get_industry_hot_tool",
        summary="行业热度排行（Top 5）",
        data={"market": "CN", "items": [
            {"name": "电子", "code": "801080", "hotScore": 4.82, "changePct": "+3.50%", "stockCount": 50},
            {"name": "医药生物", "code": "801150", "hotScore": 3.75, "changePct": "+1.20%", "stockCount": 40},
        ]},
        cards=[{"type": "industry_hot", "data": {}}],
    )


def _ok_reports() -> ToolResult:
    return ToolResult(
        ok=True, tool_name="get_recent_reports_tool",
        summary="报告 2 份",
        data={
            "items": [
                {"id": "run-001", "symbol": "688146", "name": "中船特气",
                 "created_at": "2026-06-12T00:00:00", "scope": "comprehensive"},
            ],
            "count": 2,
        },
        cards=[{"type": "report_list", "data": {}}],
    )


def _ok_report_detail() -> ToolResult:
    return ToolResult(
        ok=True, tool_name="get_report_detail_tool",
        summary="报告详情已获取",
        data={
            "run_id": "run-001",
            "summary": "综合分析显示技术面强势，基本面稳健",
            "risk_factors": "主要风险：行业竞争加剧，原材料价格波动",
        },
    )


def _fail_tool(name: str) -> ToolResult:
    return ToolResult(ok=False, tool_name=name, summary="工具执行失败", error="Simulated failure")


def _make_context(tool_registry=None) -> SkillContext:
    return SkillContext(
        db=MagicMock(),
        user_id=str(uuid.uuid4()),
        output_language="zh-CN",
        tool_registry=tool_registry,
    )


def _make_registry_mock(*side_effects) -> MagicMock:
    """Create a mock tool_registry that dispatches by tool name.

    Each ToolResult in side_effects is keyed by its .tool_name. When the skill
    (or RAG) calls a tool, the matching result is returned. Unknown tool names
    (e.g. RAG retrieval calls that are not in the expected list) receive a
    generic failure result so they don't disturb the skill's own tool sequence.

    If multiple results share the same tool_name, they are consumed in order
    (queue per tool_name).
    """
    from collections import defaultdict
    import queue as _queue

    queues: dict[str, list] = defaultdict(list)
    for r in side_effects:
        queues[r.tool_name].append(r)

    _fallback = ToolResult(ok=False, tool_name="unknown", summary="no side effect for this tool")

    async def _call_fn(tool_name, db, **kw):
        q = queues.get(tool_name, [])
        if q:
            return q.pop(0)
        return _fallback

    mock = MagicMock()
    mock.call = _call_fn
    return mock


# ── 1. can_handle() — per-skill ────────────────────────────────────────────────

def test_anomaly_skill_can_handle():
    skill = StockAnomalySkill()
    ctx = _make_context()
    assert skill.can_handle("中船特气最近为什么涨这么多", ctx) is True
    assert skill.can_handle("688146 异动分析", ctx) is True
    assert skill.can_handle("为什么涨那么多", ctx) is True


def test_risk_first_skill_can_handle():
    skill = RiskFirstSkill()
    ctx = _make_context()
    assert skill.can_handle("最大风险是什么", ctx) is True
    assert skill.can_handle("重点看风险", ctx) is True
    assert skill.can_handle("风险优先分析", ctx) is True


def test_news_catalyst_skill_can_handle():
    skill = NewsCatalystSkill()
    ctx = _make_context()
    assert skill.can_handle("有没有实质利好", ctx) is True
    assert skill.can_handle("新闻有什么影响", ctx) is True
    assert skill.can_handle("催化剂是什么", ctx) is True


def test_watchlist_review_skill_can_handle():
    skill = WatchlistReviewSkill()
    ctx = _make_context()
    assert skill.can_handle("看看我的自选股", ctx) is True
    assert skill.can_handle("帮我巡检自选股", ctx) is True
    assert skill.can_handle("自选股有哪些", ctx) is True


def test_industry_hotspot_skill_can_handle():
    skill = IndustryHotspotSkill()
    ctx = _make_context()
    assert skill.can_handle("行业热点有哪些", ctx) is True
    assert skill.can_handle("哪些行业值得重点研究", ctx) is True
    assert skill.can_handle("板块热度排行", ctx) is True


def test_report_explanation_skill_can_handle():
    skill = ReportExplanationSkill()
    ctx = _make_context()
    assert skill.can_handle("解释最近报告", ctx) is True
    assert skill.can_handle("报告结论是什么", ctx) is True
    assert skill.can_handle("报告里的风险", ctx) is True


# ── 2. Graceful partial on tool failure ───────────────────────────────────────

@pytest.mark.asyncio
async def test_anomaly_skill_run_tool_failure():
    """All tools fail → SkillResult still ok=True with partial data, no crash."""
    skill = StockAnomalySkill()
    reg = _make_registry_mock(
        _fail_tool("resolve_stock_tool"),
        _fail_tool("get_quote_tool"),
        _fail_tool("get_kline_summary_tool"),
        _fail_tool("get_latest_news_tool"),
    )
    ctx = _make_context(tool_registry=reg)
    result = await skill.run("中船特气为什么涨", ctx)
    assert result.ok is True  # Partial result, no crash
    assert result.skill_name == "stock_anomaly_skill"
    assert _DISCLAIMER_STRIPPED in result.answer


@pytest.mark.asyncio
async def test_risk_first_skill_run_tool_failure():
    """Tool failures in RiskFirstSkill → still returns partial answer."""
    skill = RiskFirstSkill()
    reg = _make_registry_mock(
        _fail_tool("resolve_stock_tool"),
        _fail_tool("get_kline_summary_tool"),
        _fail_tool("get_latest_news_tool"),
        _fail_tool("get_recent_reports_tool"),
    )
    ctx = _make_context(tool_registry=reg)
    result = await skill.run("最大风险是什么 688146", ctx)
    assert result.ok is True
    assert _DISCLAIMER_STRIPPED in result.answer


# ── 3. Empty watchlist state ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_watchlist_skill_empty_state():
    skill = WatchlistReviewSkill()
    reg = _make_registry_mock(_ok_watchlist_empty())
    ctx = _make_context(tool_registry=reg)
    result = await skill.run("看看我的自选股", ctx)
    assert result.ok is True
    assert result.skill_name == "watchlist_review_skill"
    assert "为空" in result.answer or "empty" in result.answer.lower() or "目前" in result.answer
    assert _DISCLAIMER_STRIPPED in result.answer


# ── 4. All skills answer contains _DISCLAIMER ─────────────────────────────────

@pytest.mark.asyncio
async def test_all_skills_answer_contains_disclaimer():
    test_cases = [
        (StockAnomalySkill(), "688146为什么涨", [
            _ok_resolve(), _ok_quote(), _ok_kline(), _ok_news()
        ]),
        (RiskFirstSkill(), "最大风险是什么 688146", [
            _ok_resolve(), _ok_kline(), _ok_news(), _ok_reports()
        ]),
        (NewsCatalystSkill(), "有没有实质利好 688146", [
            _ok_resolve(), _ok_news(), _ok_quote()
        ]),
        (WatchlistReviewSkill(), "看看我的自选股", [
            _ok_watchlist_with_items(), _ok_quote(), _ok_quote()
        ]),
        (IndustryHotspotSkill(), "行业热点有哪些", [
            _ok_industry_hot()
        ]),
        (ReportExplanationSkill(), "解释最近报告", [
            _ok_reports(), _ok_report_detail()
        ]),
    ]

    for skill, message, tool_returns in test_cases:
        reg = _make_registry_mock(*tool_returns)
        ctx = _make_context(tool_registry=reg)
        result = await skill.run(message, ctx)
        assert _DISCLAIMER_STRIPPED in result.answer, (
            f"{skill.name}: _DISCLAIMER not found in answer"
        )


# ── 5. No forbidden phrases ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_all_skills_no_forbidden_phrases():
    test_cases = [
        (StockAnomalySkill(), "688146为什么涨", [
            _ok_resolve(), _ok_quote(), _ok_kline(), _ok_news()
        ]),
        (RiskFirstSkill(), "最大风险是什么 688146", [
            _ok_resolve(), _ok_kline(), _ok_news(), _ok_reports()
        ]),
        (NewsCatalystSkill(), "有没有实质利好 688146", [
            _ok_resolve(), _ok_news(), _ok_quote()
        ]),
        (WatchlistReviewSkill(), "看看我的自选股", [
            _ok_watchlist_with_items(), _ok_quote(), _ok_quote()
        ]),
        (IndustryHotspotSkill(), "行业热点有哪些", [
            _ok_industry_hot()
        ]),
        (ReportExplanationSkill(), "解释最近报告", [
            _ok_reports(), _ok_report_detail()
        ]),
    ]

    for skill, message, tool_returns in test_cases:
        reg = _make_registry_mock(*tool_returns)
        ctx = _make_context(tool_registry=reg)
        result = await skill.run(message, ctx)
        for phrase in FORBIDDEN_PHRASES:
            assert phrase not in result.answer, (
                f"{skill.name}: forbidden phrase '{phrase}' found in answer"
            )


# ── 6. skill_name always set ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_skill_result_has_skill_name():
    skill = StockAnomalySkill()
    reg = _make_registry_mock(
        _ok_resolve(), _ok_quote(), _ok_kline(), _ok_news()
    )
    ctx = _make_context(tool_registry=reg)
    result = await skill.run("中船特气最近为什么涨", ctx)
    assert result.skill_name == "stock_anomaly_skill"


@pytest.mark.asyncio
async def test_all_skills_have_correct_skill_name():
    expected_names = {
        StockAnomalySkill: "stock_anomaly_skill",
        RiskFirstSkill: "risk_first_skill",
        NewsCatalystSkill: "news_catalyst_skill",
        WatchlistReviewSkill: "watchlist_review_skill",
        IndustryHotspotSkill: "industry_hotspot_skill",
        ReportExplanationSkill: "report_explanation_skill",
    }
    test_data = {
        StockAnomalySkill: ("688146为什么涨", [_ok_resolve(), _ok_quote(), _ok_kline(), _ok_news()]),
        RiskFirstSkill: ("最大风险 688146", [_ok_resolve(), _ok_kline(), _ok_news(), _ok_reports()]),
        NewsCatalystSkill: ("有没有实质利好 688146", [_ok_resolve(), _ok_news(), _ok_quote()]),
        WatchlistReviewSkill: ("看看我的自选股", [_ok_watchlist_with_items(), _ok_quote(), _ok_quote()]),
        IndustryHotspotSkill: ("行业热点", [_ok_industry_hot()]),
        ReportExplanationSkill: ("解释最近报告", [_ok_reports(), _ok_report_detail()]),
    }
    for cls, (message, returns) in test_data.items():
        skill = cls()
        reg = _make_registry_mock(*returns)
        ctx = _make_context(tool_registry=reg)
        result = await skill.run(message, ctx)
        assert result.skill_name == expected_names[cls], (
            f"{cls.__name__}: expected skill_name={expected_names[cls]}, got {result.skill_name}"
        )


# ── 7. tool_events always populated ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_anomaly_skill_has_tool_events():
    skill = StockAnomalySkill()
    reg = _make_registry_mock(
        _ok_resolve(), _ok_quote(), _ok_kline(), _ok_news()
    )
    ctx = _make_context(tool_registry=reg)
    result = await skill.run("中船特气为什么涨", ctx)
    assert len(result.tool_events) >= 1


# ── 8. Report explanation empty state ────────────────────────────────────────

@pytest.mark.asyncio
async def test_report_explanation_empty_state():
    skill = ReportExplanationSkill()
    empty_reports = ToolResult(
        ok=True, tool_name="get_recent_reports_tool",
        summary="无报告",
        data={"items": [], "count": 0},
        cards=[],
    )
    reg = _make_registry_mock(empty_reports)
    ctx = _make_context(tool_registry=reg)
    result = await skill.run("解释最近报告", ctx)
    assert result.ok is True
    assert _DISCLAIMER_STRIPPED in result.answer
    # Should give clear empty state message
    assert "暂未找到" in result.answer or "没有" in result.answer or "为空" in result.answer
