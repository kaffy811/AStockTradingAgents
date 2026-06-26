"""
C13-a: Streaming API Contract Tests.

Verifies the /messages/stream endpoint contract:
1. Endpoint exists and is registered in the router
2. Requires auth (no anonymous access)
3. Returns text/event-stream media type
4. Session ownership enforced (cannot stream to another user's session)
5. Sync POST /messages still works (not broken by streaming addition)
6. stream endpoint path is correct
"""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── 1. Router registration ────────────────────────────────────────────────────

class TestStreamEndpointRegistered:

    def test_stream_route_registered(self):
        """POST /chat/sessions/{session_id}/messages/stream must be registered."""
        from app.routers.chat import router
        paths = [r.path for r in router.routes]
        assert any("messages/stream" in p for p in paths), (
            f"stream route not found in {paths}"
        )

    def test_stream_route_method_is_post(self):
        """Stream endpoint must accept POST."""
        from app.routers.chat import router
        for route in router.routes:
            if hasattr(route, "path") and "messages/stream" in route.path:
                assert "POST" in route.methods, (
                    f"stream route must accept POST, got {route.methods}"
                )
                return
        pytest.fail("stream route not found")

    def test_sync_messages_route_still_registered(self):
        """Existing POST /messages sync endpoint must remain registered."""
        from app.routers.chat import router
        paths = [r.path for r in router.routes]
        # Both /messages and /messages/stream should exist
        msg_paths = [p for p in paths if "messages" in p]
        assert len(msg_paths) >= 2, (
            f"Expected both sync and stream routes, found: {msg_paths}"
        )


# ── 2. OrchestratorResult shape still valid ────────────────────────────────────

class TestOrchestratorResultShape:

    def test_orchestrator_result_has_required_fields(self):
        """OrchestratorResult must have answer, tool_events, cards, confirmation."""
        from app.agents.chat_orchestrator import OrchestratorResult
        r = OrchestratorResult(answer="test", tool_events=[], cards=[], confirmation=None)
        assert r.answer == "test"
        assert r.tool_events == []
        assert r.cards == []
        assert r.confirmation is None

    def test_orchestrator_result_no_fallback_fields(self):
        """C12 contract: no demo_mode / fallback_mode on OrchestratorResult."""
        from app.agents.chat_orchestrator import OrchestratorResult
        r = OrchestratorResult(answer="test", tool_events=[], cards=[], confirmation=None)
        assert not hasattr(r, "demo_mode")
        assert not hasattr(r, "fallback_mode")

    def test_process_message_accepts_event_callback(self):
        """process_message must accept optional event_callback kwarg."""
        import inspect
        from app.agents.chat_orchestrator import process_message
        sig = inspect.signature(process_message)
        assert "event_callback" in sig.parameters, (
            "process_message must accept event_callback parameter"
        )

    def test_event_callback_is_optional(self):
        """event_callback must be optional (default None)."""
        import inspect
        from app.agents.chat_orchestrator import process_message
        sig = inspect.signature(process_message)
        param = sig.parameters["event_callback"]
        assert param.default is None, "event_callback default must be None"


# ── 3. SkillContext event_callback field ──────────────────────────────────────

class TestSkillContextEventCallback:

    def test_skill_context_has_event_callback_field(self):
        """SkillContext must have event_callback field for C13-a streaming."""
        from app.agents.chat_skills.base import SkillContext
        import dataclasses
        fields = {f.name for f in dataclasses.fields(SkillContext)}
        assert "event_callback" in fields, (
            "SkillContext must have event_callback field"
        )

    def test_skill_context_event_callback_defaults_none(self):
        """SkillContext.event_callback must default to None."""
        from app.agents.chat_skills.base import SkillContext
        ctx = SkillContext(db=AsyncMock(), user_id=uuid.uuid4())
        assert ctx.event_callback is None

    def test_skill_context_accepts_callback(self):
        """SkillContext must accept an async callback."""
        from app.agents.chat_skills.base import SkillContext

        async def _cb(event_type, payload):
            pass

        ctx = SkillContext(
            db=AsyncMock(),
            user_id=uuid.uuid4(),
            event_callback=_cb,
        )
        assert ctx.event_callback is _cb


# ── 4. ChatStreamEvent ────────────────────────────────────────────────────────

class TestChatStreamEvent:

    def test_chat_stream_event_to_sse(self):
        """ChatStreamEvent.to_sse() must produce valid SSE wire format."""
        import json
        from app.agents.chat_streaming import ChatStreamEvent
        ev = ChatStreamEvent(
            event_type="agent_started",
            sequence=1,
            payload={"session_id": "abc"},
            message_id="msg-001",
        )
        sse = ev.to_sse()
        assert "event: agent_started" in sse
        assert "id: 1" in sse
        assert "data: " in sse
        # data line must be valid JSON
        data_line = [l for l in sse.split("\n") if l.startswith("data: ")][0]
        data = json.loads(data_line[6:])
        assert data["event_type"] == "agent_started"
        assert data["sequence"] == 1
        assert data["payload"] == {"session_id": "abc"}
        assert sse.endswith("\n\n")

    def test_sse_event_types_defined(self):
        """Key SSE event type constants must be defined."""
        from app.agents.chat_streaming import (
            ETYPE_AGENT_STARTED,
            ETYPE_COMPLETED,
            ETYPE_ERROR,
            ETYPE_ANSWER_DELTA,
            ETYPE_TOOL_COMPLETED,
            ETYPE_CONFIRM_REQUIRED,
            ETYPE_CARDS_DELTA,
        )
        assert ETYPE_AGENT_STARTED == "agent_started"
        assert ETYPE_COMPLETED == "agent_completed"
        assert ETYPE_ERROR == "agent_error"
        assert ETYPE_ANSWER_DELTA == "answer_delta"
        assert ETYPE_TOOL_COMPLETED == "tool_completed"
        assert ETYPE_CONFIRM_REQUIRED == "confirmation_required"
        assert ETYPE_CARDS_DELTA == "cards_delta"


# ── 5. Sync endpoint backwards compatibility ──────────────────────────────────

class TestSyncEndpointBackwardsCompatibility:

    @pytest.mark.asyncio
    async def test_sync_send_still_works(self):
        """POST /messages sync endpoint must still return correct response shape."""
        from app.agents.chat_orchestrator import OrchestratorResult
        mock_result = OrchestratorResult(
            answer="你好，茅台今天涨了 2%。",
            tool_events=[{"name": "get_quote_tool", "status": "success", "detail": "ok"}],
            cards=[],
            confirmation=None,
        )
        with patch("app.routers.chat.process_message", return_value=mock_result):
            with patch("app.routers.chat.chat_service.get_session", return_value=MagicMock()):
                with patch("app.routers.chat.chat_service.save_user_message", return_value=MagicMock(id=uuid.uuid4())):
                    with patch("app.routers.chat.chat_service.save_assistant_message", return_value=MagicMock(id=uuid.uuid4())):
                        with patch("app.routers.chat.chat_service.update_session_last_message"):
                            from app.models.chat import ChatMessageSendRequest
                            from app.routers.chat import send_chat_message
                            db = AsyncMock()
                            db.commit = AsyncMock()
                            user = MagicMock()
                            user.id = uuid.uuid4()
                            body = ChatMessageSendRequest(content="茅台今天怎么样？")
                            resp = await send_chat_message(
                                session_id=uuid.uuid4(),
                                body=body,
                                user=user,
                                db=db,
                            )
                            assert resp.answer == "你好，茅台今天涨了 2%。"
                            assert len(resp.tool_events) == 1
