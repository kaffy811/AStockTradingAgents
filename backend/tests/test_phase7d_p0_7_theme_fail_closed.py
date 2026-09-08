from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.agents import chat_orchestrator


THEME_QUERIES = [
    "AI 半导体设备主题问题",
    "AI 热潮带动哪些半导体设备公司？",
    "人工智能产业链受益公司有哪些？",
    "半导体设备行业近期有什么消息？",
    "算力概念有哪些相关上市公司？",
    "机器人产业链有哪些受益股票？",
    "新能源板块最近有哪些动态？",
    "先进封装主题影响哪些公司？",
    "光模块概念相关公司是什么？",
    "低空经济行业有什么资讯？",
    "国产替代供应链有哪些上市公司？",
    "AI 算力主题有哪些标的？",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("query", THEME_QUERIES)
async def test_unapproved_theme_variants_fail_closed_before_llm_or_provider(monkeypatch, query):
    forbidden = AsyncMock(side_effect=AssertionError("downstream LLM/provider path must not run"))
    monkeypatch.setattr(chat_orchestrator.security_entity_resolver, "resolve", forbidden)
    monkeypatch.setattr(chat_orchestrator.official_company_event_service, "list_persisted_events", forbidden)
    monkeypatch.setattr(chat_orchestrator.tushare_eod_gateway, "get_company_snapshot", forbidden)

    result = await chat_orchestrator.process_message(query, None, uuid.uuid4())

    assert result.metadata == {
        "route": "industry_news",
        "fulfillment": "unavailable",
        "reason_code": "NO_APPROVED_INDUSTRY_NEWS_SOURCE",
        "scope": "unapproved_industry_theme_research",
        "sources": [],
        "as_of": None,
        "limitations": ["当前没有已批准的行业、市场或主题新闻来源。"],
        "requires_symbol": False,
        "coverage": "approved_cninfo_only",
        "quality": "unavailable",
    }
    assert result.tool_events == []
    forbidden.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["贵州茅台近期情况", "600519 财务指标、ROE、估值"])
async def test_stock_eod_positive_controls_are_not_captured_by_theme_gate(monkeypatch, query):
    sentinel = chat_orchestrator.OrchestratorResult(
        answer="stock eod",
        metadata={"route": "stock_eod_research", "fulfillment": "fulfilled"},
    )
    handler = AsyncMock(return_value=sentinel)
    monkeypatch.setattr(chat_orchestrator, "_handle_stock_eod_research", handler)

    result = await chat_orchestrator.process_message(query, None, uuid.uuid4())

    assert result.metadata["route"] == "stock_eod_research"
    handler.assert_awaited_once()
