"""
C6 Orchestrator Integration — unit tests.

Tests verify the C6 priority order:
  1. Safety guard fires before skill
  2. Action intent fires before skill
  3. SkillRegistry intercepts research intents
  4. metadata.skill_name set when Skill runs
  5. Fallback to direct handlers when no skill matches
  6. Action intent not intercepted by skill
  7. Skill result cards preserved in OrchestratorResult
"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.chat_orchestrator import (
    OrchestratorResult,
    _DISCLAIMER,
    process_message,
)
from app.agents.chat_tools.tool_result import ToolResult


# ── Shared helpers ─────────────────────────────────────────────────────────────

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
        summary="近72小时新闻 1 条",
        data={
            "market": "CN", "symbol": "688146",
            "items": [{"title": "中船特气公告", "summary": "...", "source": "新浪财经",
                       "publish_time": "2026-06-12T00:00:00", "url": ""}],
            "count": 1,
        },
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


DB = MagicMock()
USER_ID = uuid.uuid4()


# ── 1. Safety guard fires before skill ────────────────────────────────────────

@pytest.mark.asyncio
async def test_orchestrator_trading_before_skill():
    """Safety pattern fires; skill_registry never called."""
    with patch("app.agents.chat_orchestrator._registry.call") as mock_call:
        result = await process_message("帮我买入688146", DB, USER_ID)
    assert isinstance(result, OrchestratorResult)
    assert "交易" in result.answer or "系统不提供" in result.answer
    # Safety handler → no metadata.skill_name
    assert result.metadata.get("skill_name") is None


@pytest.mark.asyncio
async def test_orchestrator_price_prediction_before_skill():
    """Price prediction → safety, no skill."""
    with patch("app.agents.chat_orchestrator._registry.call"):
        result = await process_message("价格预测明天会涨吗", DB, USER_ID)
    assert "系统不提供" in result.answer or "交易" in result.answer


# ── 2. Action intent fires before skill ───────────────────────────────────────

@pytest.mark.asyncio
async def test_orchestrator_action_before_skill():
    """'加入自选' → action confirmation; skill_registry not triggered."""
    with patch("app.agents.chat_orchestrator._registry.call", side_effect=[
        _ok_resolve(),
        ToolResult(ok=True, tool_name="get_watchlist_tool", summary="ok",
                   data={"items": [], "count": 0, "already_in": False}),
    ]):
        result = await process_message("把中船特气加入自选", DB, USER_ID)
    assert result.confirmation is not None
    assert result.confirmation["type"] == "add_watchlist"
    assert result.metadata.get("skill_name") is None


# ── 3. SkillRegistry intercepts research intents ──────────────────────────────

@pytest.mark.asyncio
async def test_orchestrator_uses_skill_for_anomaly():
    """'中船特气为什么涨' → StockAnomalySkill → metadata.skill_name set.
    C14: patch retrieve_context so RAG doesn't consume mock tool side effects.
    """
    from app.agents.chat_rag.base import RAGResult
    empty_rag = RAGResult(ok=False, query="中船特气为什么涨", documents=[])
    with patch("app.agents.chat_orchestrator._registry.call", side_effect=[
        _ok_resolve(), _ok_quote(), _ok_kline(), _ok_news()
    ]):
        with patch("app.agents.chat_skills.stock_anomaly_skill.retrieve_context",
                   new=AsyncMock(return_value=empty_rag)):
            result = await process_message("中船特气为什么涨", DB, USER_ID)
    assert isinstance(result, OrchestratorResult)
    assert result.metadata.get("skill_name") == "stock_anomaly_skill"
    assert result.metadata.get("source") == "skill_registry"


@pytest.mark.asyncio
async def test_orchestrator_uses_skill_for_risk_first():
    """'最大风险是什么' → RiskFirstSkill."""
    with patch("app.agents.chat_orchestrator._registry.call", side_effect=[
        # RiskFirstSkill: no hint → skips resolve, goes straight to kline, news, reports
        _ok_kline(), _ok_news(),
        ToolResult(ok=True, tool_name="get_recent_reports_tool", summary="ok",
                   data={"items": [], "count": 0}, cards=[]),
    ]):
        result = await process_message("最大风险是什么", DB, USER_ID)
    assert result.metadata.get("skill_name") == "risk_first_skill"


@pytest.mark.asyncio
async def test_orchestrator_uses_skill_for_industry():
    """'哪些行业值得重点研究' → IndustryHotspotSkill."""
    with patch("app.agents.chat_orchestrator._registry.call", side_effect=[
        _ok_industry_hot()
    ]):
        result = await process_message("哪些行业值得重点研究", DB, USER_ID)
    assert result.metadata.get("skill_name") == "industry_hotspot_skill"


# ── 4. metadata.skill_name set ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_orchestrator_metadata_skill_name():
    """OrchestratorResult.metadata has skill_name and tools_used."""
    with patch("app.agents.chat_orchestrator._registry.call", side_effect=[
        _ok_resolve(), _ok_quote(), _ok_kline(), _ok_news()
    ]):
        result = await process_message("中船特气为什么涨这么多", DB, USER_ID)
    assert "skill_name" in result.metadata
    assert "tools_used" in result.metadata
    assert isinstance(result.metadata["tools_used"], list)
    assert "safety_flags" in result.metadata


# ── 5. Fallback to direct handlers when no skill matches ─────────────────────

@pytest.mark.asyncio
async def test_orchestrator_fallback_when_no_skill():
    """Generic greeting → no skill → default handler."""
    result = await process_message("你好", DB, USER_ID)
    assert isinstance(result, OrchestratorResult)
    assert result.metadata.get("skill_name") is None
    # Default answer should be informative
    assert "TradingAgents" in result.answer or "研究" in result.answer


# ── 6. Action intent not intercepted by skill ─────────────────────────────────

@pytest.mark.asyncio
async def test_action_intent_not_intercepted_by_skill():
    """'帮我生成报告' → confirmation (action), skill_name NOT set."""
    with patch("app.agents.chat_orchestrator._registry.call", side_effect=[
        _ok_resolve(),
    ]):
        result = await process_message("帮我生成688146综合报告", DB, USER_ID)
    assert result.confirmation is not None
    assert result.confirmation["type"] == "create_analysis_run"
    assert result.metadata.get("skill_name") is None


# ── 7. Skill result cards preserved ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_skill_result_cards_preserved():
    """Cards from SkillResult propagate to OrchestratorResult."""
    with patch("app.agents.chat_orchestrator._registry.call", side_effect=[
        _ok_industry_hot()
    ]):
        result = await process_message("行业热点有哪些", DB, USER_ID)
    # IndustryHotspotSkill adds cards from the industry hot tool
    assert result.metadata.get("skill_name") == "industry_hotspot_skill"
    assert isinstance(result.cards, list)


# ── 8. Disclaimer always present ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_disclaimer_always_present_via_skill():
    """All paths through SkillRegistry include _DISCLAIMER in answer."""
    with patch("app.agents.chat_orchestrator._registry.call", side_effect=[
        _ok_resolve(), _ok_quote(), _ok_kline(), _ok_news()
    ]):
        result = await process_message("688146 异动分析", DB, USER_ID)
    assert _DISCLAIMER.strip() in result.answer
