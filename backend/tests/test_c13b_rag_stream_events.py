"""
C13-b: RAG Streaming Event Tests.

Tests for rag_retrieve_started/completed events emitted by retrieve_context():
1. retrieve_context() emits rag_retrieve_started
2. retrieve_context() emits rag_retrieve_completed on success
3. rag_retrieve_completed payload has documents_count and source_types
4. retrieve_context() passes event_callback to tool_registry.call()
5. On exception, emits rag_retrieve_completed with ok=False
6. RAG retrieve does not include full news text in payload
7. Skill wrapping review emits rag_review_started
8. Skill wrapping review emits rag_review_completed
9. rag_review_completed has overall_confidence field
10. rag_review_completed does not contain raw document content
"""
from __future__ import annotations

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.chat_rag.base import RAGDocument, RAGResult
from app.agents.chat_skills.base import SkillContext


def _make_context(cb=None):
    ctx = SkillContext(
        db=AsyncMock(),
        user_id=str(uuid.uuid4()),
        event_callback=cb,
    )
    ctx.tool_registry = AsyncMock()
    return ctx


def _mock_tool_registry_empty(ctx):
    """Configure tool_registry to return empty/failed results."""
    ctx.tool_registry.call = AsyncMock(return_value=MagicMock(
        ok=False, data=None, cards=[], summary="no data", tool_name="mock"
    ))


def _mock_tool_registry_with_news(ctx):
    """Configure tool_registry to return news items."""
    from app.agents.chat_tools.tool_result import ToolResult

    news_result = MagicMock()
    news_result.ok = True
    news_result.data = {
        "items": [
            {"title": "市场新闻", "summary": "摘要", "publish_time": "2026-01-01", "source": "某媒体"},
        ]
    }
    news_result.tool_name = "get_latest_news_tool"
    news_result.cards = []

    ctx.tool_registry.call = AsyncMock(return_value=news_result)


class TestRAGRetrieveEvents:

    @pytest.mark.asyncio
    async def test_emits_rag_retrieve_started(self):
        """retrieve_context must emit rag_retrieve_started."""
        from app.agents.chat_rag.retriever import retrieve_context

        events = []

        async def cb(event_type, payload):
            events.append((event_type, payload))

        ctx = _make_context(cb)
        _mock_tool_registry_empty(ctx)

        await retrieve_context("688146 有什么新闻", ctx)

        types = [e[0] for e in events]
        assert "rag_retrieve_started" in types, f"Events: {types}"

    @pytest.mark.asyncio
    async def test_emits_rag_retrieve_completed_on_success(self):
        """retrieve_context must emit rag_retrieve_completed on success."""
        from app.agents.chat_rag.retriever import retrieve_context

        events = []

        async def cb(event_type, payload):
            events.append((event_type, payload))

        ctx = _make_context(cb)
        _mock_tool_registry_empty(ctx)

        result = await retrieve_context("688146 新闻", ctx)
        assert result.ok is True

        types = [e[0] for e in events]
        assert "rag_retrieve_completed" in types, f"Events: {types}"

    @pytest.mark.asyncio
    async def test_rag_retrieve_completed_has_documents_count_and_source_types(self):
        """rag_retrieve_completed payload must include documents_count and source_types."""
        from app.agents.chat_rag.retriever import retrieve_context

        events = []

        async def cb(event_type, payload):
            events.append((event_type, payload))

        ctx = _make_context(cb)
        _mock_tool_registry_empty(ctx)

        await retrieve_context("688146", ctx)

        completed = next((e[1] for e in events if e[0] == "rag_retrieve_completed"), None)
        assert completed is not None
        assert "documents_count" in completed
        assert "source_types" in completed

    @pytest.mark.asyncio
    async def test_passes_event_callback_to_tool_registry(self):
        """retrieve_context passes event_callback to each tool_registry.call()."""
        from app.agents.chat_rag.retriever import retrieve_context

        received_callbacks = []

        async def fake_call(tool_name, db, event_callback=None, **kwargs):
            received_callbacks.append(event_callback)
            return MagicMock(ok=False, data=None, cards=[])

        ctx = _make_context(AsyncMock())
        ctx.tool_registry.call = fake_call

        await retrieve_context("688146 新闻", ctx)

        # At least one call must have received the event_callback
        assert any(cb is not None for cb in received_callbacks), \
            "event_callback was never passed to tool_registry.call()"

    @pytest.mark.asyncio
    async def test_emits_rag_retrieve_completed_with_ok_false_on_exception(self):
        """On exception, retrieve_context must emit rag_retrieve_completed(ok=False)."""
        from app.agents.chat_rag.retriever import retrieve_context

        events = []

        async def cb(event_type, payload):
            events.append((event_type, payload))

        ctx = _make_context(cb)
        ctx.tool_registry.call = AsyncMock(side_effect=RuntimeError("db error"))

        result = await retrieve_context("688146", ctx)
        assert result.ok is False

        completed = next((e[1] for e in events if e[0] == "rag_retrieve_completed"), None)
        assert completed is not None
        assert completed["ok"] is False

    @pytest.mark.asyncio
    async def test_rag_retrieve_does_not_include_full_news_text(self):
        """rag_retrieve_started payload must not include full article text."""
        from app.agents.chat_rag.retriever import retrieve_context

        events = []

        async def cb(event_type, payload):
            events.append((event_type, payload))

        ctx = _make_context(cb)
        _mock_tool_registry_with_news(ctx)

        await retrieve_context("688146 新闻", ctx)

        started = next((e[1] for e in events if e[0] == "rag_retrieve_started"), None)
        assert started is not None
        # query is truncated to 100 chars
        if "query" in started:
            assert len(started["query"]) <= 100
        # No "content" or "full_text" field
        assert "content" not in started
        assert "full_text" not in started

    @pytest.mark.asyncio
    async def test_rag_retrieve_completed_ok_true_payload_structure(self):
        """rag_retrieve_completed(ok=True) must have ok, documents_count, source_types, source fields."""
        from app.agents.chat_rag.retriever import retrieve_context

        events = []

        async def cb(event_type, payload):
            events.append((event_type, payload))

        ctx = _make_context(cb)
        _mock_tool_registry_empty(ctx)

        await retrieve_context("任意查询", ctx)

        completed = next((e[1] for e in events if e[0] == "rag_retrieve_completed"), None)
        assert completed is not None
        assert "ok" in completed
        assert "source" in completed


class TestRAGReviewEvents:

    @pytest.mark.asyncio
    async def test_skill_emits_rag_review_started(self):
        """Skills that use RAG must emit rag_review_started."""
        from app.agents.chat_skills.stock_anomaly_skill import StockAnomalySkill

        events = []

        async def cb(event_type, payload):
            events.append((event_type, payload))

        ctx = _make_context(cb)

        mock_result = MagicMock(ok=False, data=None, cards=[], summary="no data", tool_name="mock")
        ctx.tool_registry.call = AsyncMock(return_value=mock_result)

        skill = StockAnomalySkill()
        with patch("app.agents.chat_rag.retriever.safe_emit", new=AsyncMock()):
            with patch("app.agents.chat_rag.retriever.SkillContext"):
                pass
        # Run without patching to test real event emission
        await skill.run("中船特气最近为什么涨", ctx)

        types = [e[0] for e in events]
        assert "rag_review_started" in types, f"Events: {types}"

    @pytest.mark.asyncio
    async def test_skill_emits_rag_review_completed(self):
        """Skills that use RAG must emit rag_review_completed."""
        from app.agents.chat_skills.stock_anomaly_skill import StockAnomalySkill

        events = []

        async def cb(event_type, payload):
            events.append((event_type, payload))

        ctx = _make_context(cb)
        mock_result = MagicMock(ok=False, data=None, cards=[], summary="no data", tool_name="mock")
        ctx.tool_registry.call = AsyncMock(return_value=mock_result)

        skill = StockAnomalySkill()
        await skill.run("中船特气最近为什么涨", ctx)

        types = [e[0] for e in events]
        assert "rag_review_completed" in types, f"Events: {types}"

    @pytest.mark.asyncio
    async def test_rag_review_completed_has_overall_confidence(self):
        """rag_review_completed payload must include overall_confidence."""
        from app.agents.chat_skills.stock_anomaly_skill import StockAnomalySkill

        events = []

        async def cb(event_type, payload):
            events.append((event_type, payload))

        ctx = _make_context(cb)
        mock_result = MagicMock(ok=False, data=None, cards=[], summary="no data", tool_name="mock")
        ctx.tool_registry.call = AsyncMock(return_value=mock_result)

        skill = StockAnomalySkill()
        await skill.run("中船特气", ctx)

        review_done = next((e[1] for e in events if e[0] == "rag_review_completed"), None)
        assert review_done is not None
        assert "overall_confidence" in review_done

    @pytest.mark.asyncio
    async def test_rag_review_completed_no_raw_document_content(self):
        """rag_review_completed must not contain raw document content."""
        from app.agents.chat_skills.risk_first_skill import RiskFirstSkill

        events = []

        async def cb(event_type, payload):
            events.append((event_type, payload))

        ctx = _make_context(cb)
        mock_result = MagicMock(ok=False, data=None, cards=[], summary="no data", tool_name="mock")
        ctx.tool_registry.call = AsyncMock(return_value=mock_result)

        skill = RiskFirstSkill()
        await skill.run("最大风险是什么", ctx)

        review_done = next((e[1] for e in events if e[0] == "rag_review_completed"), None)
        assert review_done is not None
        # Must not have raw document fields
        for forbidden in ("documents", "content", "full_text", "raw"):
            assert forbidden not in review_done, f"Forbidden field '{forbidden}' found in payload"
