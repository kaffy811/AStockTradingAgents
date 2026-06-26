"""
test_c11_rag_retriever.py — Phase C11 RAG Retriever unit tests.

Tests: _extract_hint, retrieve_context edge cases, document limits.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.chat_rag.retriever import retrieve_context, _extract_hint
from app.agents.chat_rag.base import RAGDocument, RAGResult
from app.agents.chat_skills.base import SkillContext


# ── _extract_hint ─────────────────────────────────────────────────────────────

def test_extract_hint_named_stock():
    hint = _extract_hint("中船特气最近为什么涨")
    assert hint is not None
    assert hint["symbol"] == "688146"
    assert hint["market"] == "CN"


def test_extract_hint_numeric_code():
    hint = _extract_hint("600519 现在多少钱")
    assert hint is not None
    assert hint["symbol"] == "600519"


def test_extract_hint_no_match():
    hint = _extract_hint("哪些行业最热")
    assert hint is None


def test_extract_hint_maotai_alias():
    hint = _extract_hint("茅台今天表现如何")
    assert hint is not None
    assert hint["symbol"] == "600519"


# ── retrieve_context ──────────────────────────────────────────────────────────

def _make_context(news_items=None, report_items=None, industry_items=None):
    """Build a mock SkillContext with a ToolRegistry that returns controlled data."""
    mock_tr = MagicMock()

    async def mock_call(tool_name, db, **kwargs):
        result = MagicMock()
        result.ok = True
        if tool_name == "get_latest_news_tool":
            result.data = {"items": news_items or []}
        elif tool_name == "get_recent_reports_tool":
            result.data = {"items": report_items or []}
        elif tool_name == "get_industry_hot_tool":
            result.data = {"industries": industry_items or []}
        else:
            result.ok = False
            result.data = None
        return result

    mock_tr.call = mock_call
    ctx = SkillContext(db=object(), user_id="user-1", tool_registry=mock_tr)
    return ctx


@pytest.mark.asyncio
async def test_retrieve_context_returns_news():
    news = [{"title": "中船特气获大订单", "summary": "公告", "source": "新华社", "publish_time": "2026-06-01T00:00:00Z"}]
    ctx = _make_context(news_items=news)
    result = await retrieve_context("中船特气最近为什么涨", ctx)
    assert result.ok
    assert len(result.news_docs) == 1
    assert result.news_docs[0].external_content is True


@pytest.mark.asyncio
async def test_retrieve_context_report_query():
    reports = [{"id": 1, "title": "688146 综合报告", "summary": "基本面良好", "created_at": "2026-06-01T00:00:00Z", "symbol": "688146"}]
    ctx = _make_context(report_items=reports)
    result = await retrieve_context("解释最近报告", ctx)
    assert result.ok
    assert len(result.report_docs) >= 1
    assert result.report_docs[0].internal_content is True


@pytest.mark.asyncio
async def test_retrieve_context_industry_query():
    industry = [{"name": "半导体", "hot_score": 8.5, "avg_change_pct": 2.3}]
    ctx = _make_context(industry_items=industry)
    result = await retrieve_context("今天哪些行业热", ctx)
    assert result.ok
    assert len(result.industry_docs) >= 1


@pytest.mark.asyncio
async def test_retrieve_context_max_8_docs():
    news = [{"title": f"新闻{i}", "source": "s", "publish_time": "2026-06-01T00:00:00Z"} for i in range(10)]
    reports = [{"id": i, "title": f"报告{i}", "summary": "", "created_at": "2026-06-01T00:00:00Z", "symbol": "688146"} for i in range(5)]
    ctx = _make_context(news_items=news, report_items=reports)
    result = await retrieve_context("中船特气分析", ctx)
    assert result.ok
    assert len(result.documents) <= 8


@pytest.mark.asyncio
async def test_retrieve_context_failure_returns_ok_false():
    """If ToolRegistry raises, retrieve_context returns ok=False (never raises)."""
    mock_tr = MagicMock()
    async def bad_call(*a, **kw):
        raise RuntimeError("DB failure")
    mock_tr.call = bad_call
    ctx = SkillContext(db=object(), user_id="u", tool_registry=mock_tr)
    result = await retrieve_context("688146", ctx)
    assert result.ok is False
    assert result.documents == []
    assert result.error is not None


@pytest.mark.asyncio
async def test_retrieve_context_empty_returns_empty_doc_list():
    ctx = _make_context()
    result = await retrieve_context("茅台最新消息", ctx)
    assert result.ok
    assert isinstance(result.documents, list)
