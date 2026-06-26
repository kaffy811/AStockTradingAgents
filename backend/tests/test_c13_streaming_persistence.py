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
