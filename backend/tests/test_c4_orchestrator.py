"""
C4 Chat Orchestrator — unit tests (no DB / no live APIs required).

Tests verify:
  1. process_message returns OrchestratorResult for each intent
  2. process_confirm returns ConfirmResult for known types
  3. All handlers return _DISCLAIMER
  4. No investment advice phrases in any output

Uses AsyncMock to stub tool calls so no real services are invoked.
"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.chat_orchestrator import (
    OrchestratorResult,
    _DISCLAIMER,
    process_confirm,
    process_message,
)
from app.agents.chat_tools.tool_result import ToolResult

FORBIDDEN_PHRASES = ["买入", "卖出", "持有", "目标价"]

# ── Shared mock tool result ───────────────────────────────────────────────────

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
        summary="获取近72小时新闻 3 条",
        data={"market": "CN", "symbol": "688146",
              "items": [{"title": "中船特气公告", "summary": "...", "source": "新浪财经",
                          "publish_time": "2026-06-12", "url": ""}],
              "count": 3},
    )

def _ok_industry_hot() -> ToolResult:
    return ToolResult(
        ok=True, tool_name="get_industry_hot_tool",
        summary="行业热度排行（Top 5）",
        data={"market": "CN", "items": [
            {"name": "电子", "code": "801080", "hotScore": 4.82, "changePct": "+3.50%", "stockCount": 50},
        ]},
        cards=[{"type": "industry_hot", "data": {}}],
    )

def _ok_watchlist() -> ToolResult:
    return ToolResult(
        ok=True, tool_name="get_watchlist_tool",
        summary="自选股列表，共 2 只",
        data={"items": [{"market": "CN", "symbol": "000001"}], "count": 1, "already_in": False},
    )


# ── Helper: patch registry.call ────────────────────────────────────────────────

def _patch_registry(**side_effects: ToolResult):
    """Return a coroutine that dispatches mock results by tool_name."""
    async def _call(tool_name, db, **kwargs) -> ToolResult:
        if tool_name in side_effects:
            return side_effects[tool_name]
        return ToolResult(ok=False, tool_name=tool_name, summary="mock not set", error="not mocked")
    return _call


# ── Tests ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_anomaly_intent():
    db = AsyncMock()
    uid = uuid.uuid4()
    with patch("app.agents.chat_orchestrator._registry.call",
               side_effect=_patch_registry(
                   resolve_stock_tool=_ok_resolve(),
                   get_quote_tool=_ok_quote(),
                   get_kline_summary_tool=_ok_kline(),
                   get_latest_news_tool=_ok_news(),
               )):
        result = await process_message("中船特气最近为什么涨这么多", db, uid)

    assert isinstance(result, OrchestratorResult)
    assert _DISCLAIMER in result.answer
    assert result.tool_events, "Expected tool_events"
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in result.answer, f"Found forbidden phrase: {phrase}"


@pytest.mark.asyncio
async def test_report_intent_returns_confirmation():
    db = AsyncMock()
    uid = uuid.uuid4()
    with patch("app.agents.chat_orchestrator._registry.call",
               side_effect=_patch_registry(resolve_stock_tool=_ok_resolve())):
        result = await process_message("帮我生成 688146 的综合报告", db, uid)

    assert result.confirmation is not None
    assert result.confirmation["type"] == "create_analysis_run"
    assert "688146" in result.confirmation["text"] or "中船特气" in result.confirmation["text"]


@pytest.mark.asyncio
async def test_watchlist_add_intent():
    db = AsyncMock()
    uid = uuid.uuid4()
    with patch("app.agents.chat_orchestrator._registry.call",
               side_effect=_patch_registry(
                   resolve_stock_tool=_ok_resolve(),
                   get_watchlist_tool=_ok_watchlist(),
               )):
        result = await process_message("把中船特气加入自选股", db, uid)

    assert result.confirmation is not None
    assert result.confirmation["type"] == "add_watchlist"


@pytest.mark.asyncio
async def test_watchlist_already_in():
    db = AsyncMock()
    uid = uuid.uuid4()
    wl_already = ToolResult(
        ok=True, tool_name="get_watchlist_tool", summary="已在自选股",
        data={"items": [], "count": 1, "already_in": True},
    )
    with patch("app.agents.chat_orchestrator._registry.call",
               side_effect=_patch_registry(
                   resolve_stock_tool=_ok_resolve(),
                   get_watchlist_tool=wl_already,
               )):
        result = await process_message("把中船特气加入自选", db, uid)

    assert result.confirmation is None
    assert "已在" in result.answer


@pytest.mark.asyncio
async def test_industry_intent():
    db = AsyncMock()
    uid = uuid.uuid4()
    with patch("app.agents.chat_orchestrator._registry.call",
               side_effect=_patch_registry(get_industry_hot_tool=_ok_industry_hot())):
        result = await process_message("今天哪些行业值得关注", db, uid)

    assert _DISCLAIMER in result.answer
    assert result.tool_events
    assert result.cards


@pytest.mark.asyncio
async def test_compare_intent():
    db = AsyncMock()
    uid = uuid.uuid4()
    result = await process_message("对比宁德时代和紫金矿业", db, uid)
    assert result.confirmation is not None
    assert result.confirmation["type"] == "create_compare"


@pytest.mark.asyncio
async def test_default_intent():
    db = AsyncMock()
    uid = uuid.uuid4()
    result = await process_message("你好", db, uid)
    assert isinstance(result, OrchestratorResult)
    assert _DISCLAIMER in result.answer


@pytest.mark.asyncio
async def test_confirm_report():
    db = AsyncMock()
    uid = uuid.uuid4()
    mock_llm = MagicMock()
    mock_registry = AsyncMock()
    mock_run_ref = MagicMock()
    mock_run_ref.run_id = "run-c4-test"
    mock_registry.create_run = AsyncMock(return_value=mock_run_ref)
    mock_runner = MagicMock()
    mock_runner.run_analysis = AsyncMock()
    with patch("app.agents.chat_tools.action_tools.get_llm_client", return_value=mock_llm), \
         patch("app.agents.chat_tools.action_tools.get_run_registry", return_value=mock_registry), \
         patch("app.agents.chat_tools.action_tools.RealtimeAnalysisRunner", return_value=mock_runner), \
         patch("app.agents.chat_tools.action_tools.asyncio.create_task"):
        result = await process_confirm(
            "create_analysis_run",
            {"name": "中船特气", "market": "CN", "symbol": "688146"},
            db=db, user_id=uid,
        )
    assert result.cards


@pytest.mark.asyncio
async def test_confirm_watchlist():
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)
    db.flush   = AsyncMock()
    nested_ctx = MagicMock()
    nested_ctx.__aenter__ = AsyncMock(return_value=None)
    nested_ctx.__aexit__  = AsyncMock(return_value=False)
    db.begin_nested = MagicMock(return_value=nested_ctx)
    uid = uuid.uuid4()
    result = await process_confirm(
        "add_watchlist",
        {"name": "中船特气", "market": "CN", "symbol": "688146"},
        db=db, user_id=uid,
    )
    assert "✓" in result.answer
    assert result.cards


@pytest.mark.asyncio
async def test_confirm_compare():
    db = AsyncMock()
    uid = uuid.uuid4()
    result = await process_confirm(
        "create_compare",
        {"stocks": [{"name": "A", "market": "CN", "symbol": "000001"}],
         "compare_url": "/compare?stocks=CN:000001"},
        db=db, user_id=uid,
    )
    assert result.cards
    assert _DISCLAIMER in result.answer


@pytest.mark.asyncio
async def test_confirm_unknown():
    db = AsyncMock()
    uid = uuid.uuid4()
    result = await process_confirm("unknown_type", {}, db=db, user_id=uid)
    assert "已完成" in result.answer
