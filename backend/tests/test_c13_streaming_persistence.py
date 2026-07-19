"""
C13-a: Streaming Persistence Contract Tests.

Verifies that streaming correctly persists messages:
1. User message is saved before streaming starts
2. Assistant message is saved after streaming completes
3. Saved assistant message has correct answer/tool_events/cards
4. Session restore after streaming returns complete message
5. Partial results on failure — error state persisted if possible
6. Metadata includes streamed=True flag
"""

import json
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call


def _make_uid():
    return uuid.UUID("00000000-0000-0000-0000-000000000013")


async def _run_stream(session_id, user_id, content, db):
    """Run stream and collect all chunks (discarded)."""
    from app.agents.chat_streaming import stream_chat_message
    async for _ in stream_chat_message(
        session_id=session_id,
        user_id=user_id,
        content=content,
        output_language="zh-CN",
        db=db,
    ):
        pass


def _event_types(chunks: list[str]) -> list[str]:
    events: list[str] = []
    for chunk in chunks:
        for line in chunk.splitlines():
            if line.startswith("event:"):
                events.append(line.split(":", 1)[1].strip())
    return events


def _event_payloads(chunks: list[str], event_type: str) -> list[dict]:
    payloads: list[dict] = []
    for chunk in chunks:
        data_lines: list[str] = []
        current_type = ""
        for line in chunk.splitlines():
            if line.startswith("event:"):
                current_type = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].lstrip())
        if current_type == event_type and data_lines:
            payloads.append(json.loads("\n".join(data_lines)).get("payload", {}))
    return payloads


# ── 1. User message persistence ───────────────────────────────────────────────

class TestUserMessagePersistence:

    @pytest.mark.asyncio
    async def test_user_message_saved_before_orchestration(self):
        """save_user_message must be called during the stream."""
        from app.agents.chat_orchestrator import OrchestratorResult

        mock_result = OrchestratorResult(answer="ok", tool_events=[], cards=[], confirmation=None)
        saved_user_msg = MagicMock()
        saved_user_msg.id = uuid.uuid4()

        mock_save_user = AsyncMock(return_value=saved_user_msg)

        with (
            patch("app.agents.chat_streaming.process_message", return_value=mock_result),
            patch("app.agents.chat_streaming.save_user_message", mock_save_user),
            patch("app.agents.chat_streaming.save_assistant_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.update_session_last_message"),
        ):
            db = AsyncMock()
            sid = uuid.uuid4()
            await _run_stream(sid, _make_uid(), "茅台行情", db)

        mock_save_user.assert_called_once()
        call_args = mock_save_user.call_args
        assert call_args.args[3] == "茅台行情"   # content

    @pytest.mark.asyncio
    async def test_user_message_saved_with_correct_session(self):
        """save_user_message must be called with correct session_id."""
        from app.agents.chat_orchestrator import OrchestratorResult

        mock_result = OrchestratorResult(answer="ok", tool_events=[], cards=[], confirmation=None)
        mock_save_user = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
        sid = uuid.uuid4()

        with (
            patch("app.agents.chat_streaming.process_message", return_value=mock_result),
            patch("app.agents.chat_streaming.save_user_message", mock_save_user),
            patch("app.agents.chat_streaming.save_assistant_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.update_session_last_message"),
        ):
            await _run_stream(sid, _make_uid(), "test", AsyncMock())

        call_args = mock_save_user.call_args
        assert call_args.args[1] == sid   # session_id


# ── 2. Assistant message persistence ──────────────────────────────────────────

class TestAssistantMessagePersistence:

    @pytest.mark.asyncio
    async def test_assistant_message_saved_after_stream(self):
        """save_assistant_message must be called after streaming completes."""
        from app.agents.chat_orchestrator import OrchestratorResult

        mock_result = OrchestratorResult(
            answer="茅台今天涨了 2%。",
            tool_events=[{"name": "get_quote_tool", "status": "success", "detail": "ok"}],
            cards=[],
            confirmation=None,
        )
        mock_save_asst = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))

        with (
            patch("app.agents.chat_streaming.process_message", return_value=mock_result),
            patch("app.agents.chat_streaming.save_user_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.save_assistant_message", mock_save_asst),
            patch("app.agents.chat_streaming.update_session_last_message"),
        ):
            await _run_stream(uuid.uuid4(), _make_uid(), "茅台行情", AsyncMock())

        mock_save_asst.assert_called_once()
        kwargs = mock_save_asst.call_args.kwargs
        assert kwargs["answer"] == "茅台今天涨了 2%。"
        assert len(kwargs["tool_events"]) == 1
        assert kwargs["confirmation"] is None

    @pytest.mark.asyncio
    async def test_stream_emits_answer_completed_before_done(self):
        """Successful streams must explicitly complete the answer before done."""
        from app.agents.chat_orchestrator import OrchestratorResult

        mock_result = OrchestratorResult(answer="财报回答正文", tool_events=[], cards=[], confirmation=None)
        chunks: list[str] = []

        with (
            patch("app.agents.chat_streaming.process_message", return_value=mock_result),
            patch("app.agents.chat_streaming.save_user_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.save_assistant_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.update_session_last_message"),
        ):
            from app.agents.chat_streaming import stream_chat_message
            async for chunk in stream_chat_message(uuid.uuid4(), _make_uid(), "财报问题", "zh-CN", AsyncMock()):
                chunks.append(chunk)

        events = _event_types(chunks)
        assert "answer_completed" in events
        assert "message_persisted" in events
        assert events.index("answer_completed") < events.index("agent_completed")
        assert events.index("message_persisted") < events.index("agent_completed")
        assert "final_answer" not in events[events.index("agent_completed") + 1:]
        completed = _event_payloads(chunks, "agent_completed")[-1]
        assert completed["status"] == "completed"
        assert completed["answer_length"] == len("财报回答正文")

    @pytest.mark.asyncio
    async def test_empty_final_answer_is_not_persisted_as_completed_empty(self):
        """Empty orchestrator answers are downgraded to failed with non-empty content."""
        from app.agents.chat_orchestrator import OrchestratorResult

        mock_result = OrchestratorResult(answer="", tool_events=[], cards=[], confirmation=None)
        mock_save_asst = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
        chunks: list[str] = []

        with (
            patch("app.agents.chat_streaming.process_message", return_value=mock_result),
            patch("app.agents.chat_streaming.save_user_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.save_assistant_message", mock_save_asst),
            patch("app.agents.chat_streaming.update_session_last_message"),
        ):
            from app.agents.chat_streaming import stream_chat_message
            async for chunk in stream_chat_message(uuid.uuid4(), _make_uid(), "财报问题", "zh-CN", AsyncMock()):
                chunks.append(chunk)

        saved_answer = mock_save_asst.call_args.kwargs["answer"]
        assert saved_answer.strip()
        assert "生成失败" in saved_answer
        answer_completed = _event_payloads(chunks, "answer_completed")[-1]
        assert answer_completed["status"] == "failed"
        assert answer_completed["error_code"] == "EMPTY_FINAL_ANSWER"

    @pytest.mark.asyncio
    async def test_assistant_message_metadata_includes_streamed_flag(self):
        """Persisted assistant message metadata must include streamed=True."""
        from app.agents.chat_orchestrator import OrchestratorResult

        mock_result = OrchestratorResult(answer="ok", tool_events=[], cards=[], confirmation=None)
        mock_save_asst = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))

        with (
            patch("app.agents.chat_streaming.process_message", return_value=mock_result),
            patch("app.agents.chat_streaming.save_user_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.save_assistant_message", mock_save_asst),
            patch("app.agents.chat_streaming.update_session_last_message"),
        ):
            await _run_stream(uuid.uuid4(), _make_uid(), "test", AsyncMock())

        kwargs = mock_save_asst.call_args.kwargs
        assert kwargs.get("extra_metadata", {}).get("streamed") is True

    @pytest.mark.asyncio
    async def test_db_commit_called_after_assistant_save(self):
        """db.commit() must be called after saving assistant message."""
        from app.agents.chat_orchestrator import OrchestratorResult

        mock_result = OrchestratorResult(answer="ok", tool_events=[], cards=[], confirmation=None)
        db = AsyncMock()
        commit_called = []
        original_commit = db.commit

        async def _track_commit():
            commit_called.append(True)
            return await original_commit()

        db.commit = _track_commit

        with (
            patch("app.agents.chat_streaming.process_message", return_value=mock_result),
            patch("app.agents.chat_streaming.save_user_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.save_assistant_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.update_session_last_message"),
        ):
            await _run_stream(uuid.uuid4(), _make_uid(), "test", db)

        assert len(commit_called) >= 1, "db.commit() must be called at least once"

    @pytest.mark.asyncio
    async def test_cards_persisted_in_assistant_message(self):
        """Cards from result must be persisted in assistant message."""
        from app.agents.chat_orchestrator import OrchestratorResult

        cards = [{"type": "stock_summary", "data": {"name": "茅台"}}]
        mock_result = OrchestratorResult(
            answer="ok", tool_events=[], cards=cards, confirmation=None
        )
        mock_save_asst = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))

        with (
            patch("app.agents.chat_streaming.process_message", return_value=mock_result),
            patch("app.agents.chat_streaming.save_user_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.save_assistant_message", mock_save_asst),
            patch("app.agents.chat_streaming.update_session_last_message"),
        ):
            await _run_stream(uuid.uuid4(), _make_uid(), "茅台行情", AsyncMock())

        kwargs = mock_save_asst.call_args.kwargs
        assert kwargs["cards"] == cards

    @pytest.mark.asyncio
    async def test_confirmation_persisted_in_assistant_message(self):
        """Confirmation from result must be persisted in assistant message."""
        from app.agents.chat_orchestrator import OrchestratorResult

        conf = {"id": "c1", "type": "create_analysis_run", "status": "pending"}
        mock_result = OrchestratorResult(
            answer="", tool_events=[], cards=[], confirmation=conf
        )
        mock_save_asst = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))

        with (
            patch("app.agents.chat_streaming.process_message", return_value=mock_result),
            patch("app.agents.chat_streaming.save_user_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.save_assistant_message", mock_save_asst),
            patch("app.agents.chat_streaming.update_session_last_message"),
        ):
            await _run_stream(uuid.uuid4(), _make_uid(), "帮我分析并保存", AsyncMock())

        kwargs = mock_save_asst.call_args.kwargs
        assert kwargs["confirmation"] == conf


class TestStreamingTransactionIsolation:

    @pytest.mark.asyncio
    async def test_short_db_operation_failure_rolls_back(self):
        from app.agents.chat_streaming import _run_short_db_operation

        db = AsyncMock()

        async def _fail(_db):
            raise RuntimeError("first db exception")

        with pytest.raises(RuntimeError, match="first db exception"):
            await _run_short_db_operation("test.owner", _fail, db_override=db)

        db.rollback.assert_awaited_once()
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rollback_failure_does_not_mask_first_exception(self):
        from app.agents.chat_streaming import _run_short_db_operation

        db = AsyncMock()
        db.rollback = AsyncMock(side_effect=RuntimeError("rollback failed"))

        async def _fail(_db):
            raise ValueError("first db exception")

        with pytest.raises(ValueError, match="first db exception"):
            await _run_short_db_operation("test.owner", _fail, db_override=db)

        db.rollback.assert_awaited_once()
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_downstream_agent_completed_is_not_reemitted(self):
        from app.agents.chat_orchestrator import OrchestratorResult
        from app.agents.chat_streaming import stream_chat_message

        async def fake_process(*_args, **kwargs):
            await kwargs["event_callback"]("agent_completed", {"status": "completed"})
            return OrchestratorResult(answer="ok", tool_events=[], cards=[], confirmation=None)

        chunks: list[str] = []
        with (
            patch("app.agents.chat_streaming.process_message", fake_process),
            patch("app.agents.chat_streaming.save_user_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.save_assistant_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.update_session_last_message"),
        ):
            async for chunk in stream_chat_message(uuid.uuid4(), _make_uid(), "test", "zh-CN", AsyncMock()):
                chunks.append(chunk)

        events = _event_types(chunks)
        assert events.count("agent_completed") == 1

    @pytest.mark.asyncio
    async def test_no_yield_after_terminal_event(self):
        from app.agents.chat_orchestrator import OrchestratorResult
        from app.agents.chat_streaming import stream_chat_message

        chunks: list[str] = []
        with (
            patch("app.agents.chat_streaming.process_message", return_value=OrchestratorResult(answer="ok", tool_events=[], cards=[], confirmation=None)),
            patch("app.agents.chat_streaming.save_user_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.save_assistant_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.update_session_last_message"),
        ):
            async for chunk in stream_chat_message(uuid.uuid4(), _make_uid(), "test", "zh-CN", AsyncMock()):
                chunks.append(chunk)

        events = _event_types(chunks)
        terminal_index = events.index("agent_completed")
        assert events[terminal_index + 1:] == []


# ── 3. Session restore after streaming ────────────────────────────────────────

class TestSessionRestoreAfterStreaming:

    def test_chat_message_item_fields_for_restore(self):
        """ChatMessageItem must have all fields needed to restore streamed message."""
        from app.models.chat import ChatMessageItem
        fields = ChatMessageItem.model_fields
        required = {"message_id", "role", "content", "tool_events", "cards", "confirmation"}
        missing = required - fields.keys()
        assert not missing, f"ChatMessageItem missing fields: {missing}"

    @pytest.mark.asyncio
    async def test_streamed_session_restores_tool_events(self):
        """After streaming, session restore must include tool_events."""
        from app.models.chat import ChatSession, ChatMessage, ChatMessageItem
        from app.services.chat_service import get_session_with_messages
        import datetime

        mock_session = MagicMock(spec=ChatSession)
        mock_session.id = uuid.uuid4()
        mock_session.user_id = _make_uid()
        mock_session.title = "Streamed Session"
        mock_session.status = "active"
        mock_session.created_at = datetime.datetime.now(datetime.timezone.utc)
        mock_session.updated_at = mock_session.created_at
        mock_session.deleted_at = None

        tool_events = [{"name": "get_quote_tool", "status": "success", "detail": "ok"}]
        mock_msg = MagicMock(spec=ChatMessage)
        mock_msg.id = uuid.uuid4()
        mock_msg.session_id = mock_session.id
        mock_msg.role = "assistant"
        mock_msg.content = "茅台今天涨了 2%。"
        mock_msg.message_type = "tool_trace"
        mock_msg.tool_events = tool_events
        mock_msg.cards = []
        mock_msg.confirmation = None
        mock_msg.created_at = datetime.datetime.now(datetime.timezone.utc)

        db = AsyncMock()
        db.get = AsyncMock(return_value=mock_session)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_msg]
        db.execute = AsyncMock(return_value=mock_result)

        _, messages = await get_session_with_messages(db, mock_session.id, mock_session.user_id)
        assert len(messages) == 1
        assert messages[0].tool_events == tool_events
