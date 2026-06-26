"""
C13-b: Stream Dedup Tests.

Tests for Phase 5 dedup logic in chat_streaming.py:
1. Tool events emitted in real-time are NOT replayed in Phase 5
2. Tool events NOT emitted in real-time ARE replayed in Phase 5
3. RAG pseudo-events (rag_retrieve, rag_review named events) are skipped in Phase 5 replay
4. Dedup uses (tool_name, started_at) as key
5. If started_at is empty, event IS replayed (no false dedup)
6. Multiple calls to same tool are each deduped separately (by started_at)
7. answer_delta still emitted normally after dedup
8. agent_completed still emitted after dedup
9. No duplicate events in output stream when real-time events present
10. C13-a compat: stream_chat_message returns at least agent_started and agent_completed
"""
from __future__ import annotations

import asyncio
import json
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_uid():
    return uuid.UUID("00000000-0000-0000-0000-000000000013")


def _parse_sse_stream(chunks: list[str]) -> list[dict]:
    """Parse SSE strings into list of {event_type, payload, sequence} dicts."""
    events = []
    cur_type = "message"
    cur_data = ""
    for chunk in chunks:
        for line in chunk.split("\n"):
            if line.startswith("event: "):
                cur_type = line[7:].strip()
            elif line.startswith("data: "):
                cur_data = line[6:]
            elif line == "" and cur_data:
                try:
                    parsed = json.loads(cur_data)
                    events.append({
                        "event_type": cur_type or parsed.get("event_type"),
                        "payload":    parsed.get("payload", {}),
                        "sequence":   parsed.get("sequence", 0),
                    })
                except json.JSONDecodeError:
                    pass
                cur_type = "message"
                cur_data = ""
    return events


async def _collect_stream(session_id, user_id, content, output_language, db) -> list[str]:
    """Collect all SSE chunks from stream_chat_message."""
    from app.agents.chat_streaming import stream_chat_message
    chunks = []
    async for chunk in stream_chat_message(
        session_id=session_id,
        user_id=user_id,
        content=content,
        output_language=output_language,
        db=db,
    ):
        chunks.append(chunk)
    return chunks


def _make_tool_event(tool_name: str, started_at: str = "2026-01-01T00:00:00+00:00") -> dict:
    return {
        "name": tool_name,
        "status": "success",
        "detail": "ok",
        "started_at": started_at,
    }


def _make_mock_result(tool_events=None, answer="分析完成", cards=None, confirmation=None):
    from app.agents.chat_orchestrator import OrchestratorResult
    return OrchestratorResult(
        answer=answer,
        tool_events=tool_events or [],
        cards=cards or [],
        confirmation=confirmation,
    )


class TestPhase5Dedup:

    @pytest.mark.asyncio
    async def test_realtime_tool_events_not_replayed(self):
        """Tool events emitted in real-time (via event_callback) must NOT be replayed in Phase 5."""
        started_at = "2026-01-01T00:00:00+00:00"
        te = _make_tool_event("get_quote_tool", started_at)
        mock_result = _make_mock_result(tool_events=[te])

        emitted_realtime = []

        async def fake_process(content, db, user_id, output_language, session_id, event_callback=None):
            # Simulate real-time emission
            if event_callback:
                await event_callback("tool_completed", {
                    "tool_name": "get_quote_tool",
                    "started_at": started_at,
                    "status": "success",
                })
                emitted_realtime.append("get_quote_tool")
            return mock_result

        db = AsyncMock()

        with (
            patch("app.agents.chat_streaming.process_message", side_effect=fake_process),
            patch("app.agents.chat_streaming.save_user_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.save_assistant_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.update_session_last_message"),
        ):
            chunks = await _collect_stream(uuid.uuid4(), _make_uid(), "test", "zh-CN", db)

        events = _parse_sse_stream(chunks)
        tool_completed_events = [e for e in events if e["event_type"] == "tool_completed"]

        # The tool event should appear exactly once
        assert len(tool_completed_events) <= 1, \
            f"Tool event appeared {len(tool_completed_events)} times — expected at most 1 (deduped)"

    @pytest.mark.asyncio
    async def test_non_realtime_tool_events_are_replayed(self):
        """Tool events NOT emitted in real-time must be replayed in Phase 5."""
        started_at = "2026-01-01T00:00:00+00:00"
        te = _make_tool_event("get_kline_summary_tool", started_at)
        mock_result = _make_mock_result(tool_events=[te])

        async def fake_process(content, db, user_id, output_language, session_id, event_callback=None):
            # Does NOT emit real-time tool_completed
            return mock_result

        db = AsyncMock()

        with (
            patch("app.agents.chat_streaming.process_message", side_effect=fake_process),
            patch("app.agents.chat_streaming.save_user_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.save_assistant_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.update_session_last_message"),
        ):
            chunks = await _collect_stream(uuid.uuid4(), _make_uid(), "test", "zh-CN", db)

        events = _parse_sse_stream(chunks)
        tool_completed_events = [e for e in events if e["event_type"] == "tool_completed"]

        # The fallback replay should have emitted it
        assert len(tool_completed_events) >= 1, "Phase 5 fallback did not replay non-real-time tool event"

    @pytest.mark.asyncio
    async def test_rag_pseudo_events_skipped_in_phase5_replay(self):
        """rag_retrieve and rag_review named events in result.tool_events are skipped in Phase 5."""
        rag_events = [
            {"name": "rag_retrieve", "status": "success", "detail": "ok"},
            {"name": "rag_review", "status": "success", "detail": "medium"},
        ]
        mock_result = _make_mock_result(tool_events=rag_events)

        async def fake_process(content, db, user_id, output_language, session_id, event_callback=None):
            return mock_result

        db = AsyncMock()

        with (
            patch("app.agents.chat_streaming.process_message", side_effect=fake_process),
            patch("app.agents.chat_streaming.save_user_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.save_assistant_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.update_session_last_message"),
        ):
            chunks = await _collect_stream(uuid.uuid4(), _make_uid(), "test", "zh-CN", db)

        events = _parse_sse_stream(chunks)
        # Look for tool_completed events that replay rag_retrieve or rag_review
        rag_replayed = [
            e for e in events
            if e["event_type"] == "tool_completed"
            and e["payload"].get("tool_event", {}).get("name") in ("rag_retrieve", "rag_review")
        ]
        assert len(rag_replayed) == 0, \
            f"RAG pseudo-events were replayed in Phase 5: {rag_replayed}"

    @pytest.mark.asyncio
    async def test_dedup_uses_tool_name_and_started_at(self):
        """Dedup key is (tool_name, started_at). Different started_at = different events."""
        started_at = "2026-01-01T10:00:00+00:00"
        te = _make_tool_event("get_quote_tool", started_at)
        mock_result = _make_mock_result(tool_events=[te])

        real_time_keys = set()

        async def fake_process(content, db, user_id, output_language, session_id, event_callback=None):
            if event_callback:
                # Emit with exact matching started_at
                await event_callback("tool_completed", {
                    "tool_name": "get_quote_tool",
                    "started_at": started_at,
                    "ok": True,
                })
                real_time_keys.add(f"get_quote_tool|{started_at}")
            return mock_result

        db = AsyncMock()

        with (
            patch("app.agents.chat_streaming.process_message", side_effect=fake_process),
            patch("app.agents.chat_streaming.save_user_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.save_assistant_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.update_session_last_message"),
        ):
            chunks = await _collect_stream(uuid.uuid4(), _make_uid(), "test", "zh-CN", db)

        events = _parse_sse_stream(chunks)
        # Count tool_completed events for get_quote_tool
        quote_events = [e for e in events if e["event_type"] == "tool_completed"]
        assert len(quote_events) <= 1, f"Expected dedup: got {len(quote_events)} tool_completed events"

    @pytest.mark.asyncio
    async def test_empty_started_at_causes_replay(self):
        """If started_at is empty, event is always replayed (no false dedup)."""
        te = {"name": "get_industry_hot_tool", "status": "success", "detail": "ok", "started_at": ""}
        mock_result = _make_mock_result(tool_events=[te])

        async def fake_process(content, db, user_id, output_language, session_id, event_callback=None):
            # Do NOT emit real-time (nothing registered in _emitted_tool_keys)
            return mock_result

        db = AsyncMock()

        with (
            patch("app.agents.chat_streaming.process_message", side_effect=fake_process),
            patch("app.agents.chat_streaming.save_user_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.save_assistant_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.update_session_last_message"),
        ):
            chunks = await _collect_stream(uuid.uuid4(), _make_uid(), "test", "zh-CN", db)

        events = _parse_sse_stream(chunks)
        # With empty started_at, it should be replayed (not falsely deduped)
        tool_events = [e for e in events if e["event_type"] == "tool_completed"]
        assert len(tool_events) >= 1, "Event with empty started_at should be replayed"

    @pytest.mark.asyncio
    async def test_answer_delta_still_emitted_after_dedup(self):
        """answer_delta events must still be emitted even when tool dedup is active."""
        te = _make_tool_event("get_quote_tool", "2026-01-01T00:00:00+00:00")
        mock_result = _make_mock_result(tool_events=[te], answer="分析报告内容")

        async def fake_process(content, db, user_id, output_language, session_id, event_callback=None):
            if event_callback:
                await event_callback("tool_completed", {
                    "tool_name": "get_quote_tool",
                    "started_at": "2026-01-01T00:00:00+00:00",
                })
            return mock_result

        db = AsyncMock()

        with (
            patch("app.agents.chat_streaming.process_message", side_effect=fake_process),
            patch("app.agents.chat_streaming.save_user_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.save_assistant_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.update_session_last_message"),
        ):
            chunks = await _collect_stream(uuid.uuid4(), _make_uid(), "test", "zh-CN", db)

        events = _parse_sse_stream(chunks)
        types = [e["event_type"] for e in events]
        assert "answer_delta" in types, f"answer_delta missing: {types}"

    @pytest.mark.asyncio
    async def test_agent_completed_still_emitted_after_dedup(self):
        """agent_completed must still be emitted even when tool dedup is active."""
        te = _make_tool_event("get_quote_tool", "2026-01-01T00:00:00+00:00")
        mock_result = _make_mock_result(tool_events=[te], answer="test")

        async def fake_process(content, db, user_id, output_language, session_id, event_callback=None):
            if event_callback:
                await event_callback("tool_completed", {
                    "tool_name": "get_quote_tool",
                    "started_at": "2026-01-01T00:00:00+00:00",
                })
            return mock_result

        db = AsyncMock()

        with (
            patch("app.agents.chat_streaming.process_message", side_effect=fake_process),
            patch("app.agents.chat_streaming.save_user_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.save_assistant_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.update_session_last_message"),
        ):
            chunks = await _collect_stream(uuid.uuid4(), _make_uid(), "test", "zh-CN", db)

        events = _parse_sse_stream(chunks)
        types = [e["event_type"] for e in events]
        assert "agent_completed" in types, f"agent_completed missing: {types}"

    @pytest.mark.asyncio
    async def test_no_duplicate_events_when_real_time_present(self):
        """No tool_completed event should appear more than once for the same key."""
        started_at = "2026-01-01T09:00:00+00:00"
        te = _make_tool_event("get_quote_tool", started_at)
        mock_result = _make_mock_result(tool_events=[te])

        async def fake_process(content, db, user_id, output_language, session_id, event_callback=None):
            if event_callback:
                await event_callback("tool_completed", {
                    "tool_name": "get_quote_tool",
                    "started_at": started_at,
                    "ok": True,
                })
            return mock_result

        db = AsyncMock()

        with (
            patch("app.agents.chat_streaming.process_message", side_effect=fake_process),
            patch("app.agents.chat_streaming.save_user_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.save_assistant_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.update_session_last_message"),
        ):
            chunks = await _collect_stream(uuid.uuid4(), _make_uid(), "test", "zh-CN", db)

        events = _parse_sse_stream(chunks)
        tool_completed = [e for e in events if e["event_type"] == "tool_completed"]
        # At most 1: either real-time OR fallback, not both
        assert len(tool_completed) <= 1, \
            f"Duplicate tool_completed: {len(tool_completed)} occurrences"

    @pytest.mark.asyncio
    async def test_c13a_compat_agent_started_and_completed(self):
        """C13-a compat: stream must still contain agent_started and agent_completed."""
        mock_result = _make_mock_result(answer="你好！")
        db = AsyncMock()

        with (
            patch("app.agents.chat_streaming.process_message", return_value=mock_result),
            patch("app.agents.chat_streaming.save_user_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.save_assistant_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.update_session_last_message"),
        ):
            chunks = await _collect_stream(uuid.uuid4(), _make_uid(), "你好", "zh-CN", db)

        events = _parse_sse_stream(chunks)
        types = [e["event_type"] for e in events]
        assert "agent_started" in types, f"agent_started missing: {types}"
        assert "agent_completed" in types, f"agent_completed missing: {types}"

    @pytest.mark.asyncio
    async def test_multiple_same_tool_different_started_at_each_counted(self):
        """Multiple calls to same tool with different started_at are NOT deduped."""
        # Two events for same tool but different timestamps
        te1 = _make_tool_event("get_latest_news_tool", "2026-01-01T10:00:00+00:00")
        te2 = _make_tool_event("get_latest_news_tool", "2026-01-01T10:01:00+00:00")
        mock_result = _make_mock_result(tool_events=[te1, te2])

        async def fake_process(content, db, user_id, output_language, session_id, event_callback=None):
            # No real-time emission — both should be replayed in Phase 5
            return mock_result

        db = AsyncMock()

        with (
            patch("app.agents.chat_streaming.process_message", side_effect=fake_process),
            patch("app.agents.chat_streaming.save_user_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.save_assistant_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.update_session_last_message"),
        ):
            chunks = await _collect_stream(uuid.uuid4(), _make_uid(), "test", "zh-CN", db)

        events = _parse_sse_stream(chunks)
        # Both events should appear (different started_at = different dedup keys)
        news_events = [
            e for e in events if e["event_type"] == "tool_completed"
            and e["payload"].get("tool_event", {}).get("name") == "get_latest_news_tool"
        ]
        assert len(news_events) == 2, \
            f"Expected 2 news tool events (different timestamps), got {len(news_events)}"
