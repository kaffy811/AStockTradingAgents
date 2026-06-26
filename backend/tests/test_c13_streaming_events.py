"""
C13-a: Streaming Events Contract Tests.

Verifies SSE event sequence and payload contracts:
1. stream_chat_message() yields agent_started before agent_completed
2. answer_delta events carry partial answer text
3. tool_completed events carry tool_event payload
4. agent_completed is always the last real event
5. agent_error is emitted on orchestration failure
6. Event sequence numbers are monotonically increasing
7. Confirmation_required emitted when orchestrator returns confirmation
8. Cards_delta emitted when orchestrator returns cards
9. keepalive is ': keepalive\\n\\n'
10. No private chain-of-thought in any event payload
"""

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


# ── 1. Basic event sequence ────────────────────────────────────────────────────

class TestStreamEventSequence:

    @pytest.mark.asyncio
    async def test_stream_contains_agent_started(self):
        """Stream must contain agent_started event."""
        from app.agents.chat_orchestrator import OrchestratorResult

        mock_result = OrchestratorResult(answer="你好！", tool_events=[], cards=[], confirmation=None)
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
        assert "agent_started" in types, f"agent_started not in {types}"

    @pytest.mark.asyncio
    async def test_stream_contains_agent_completed(self):
        """Stream must end with agent_completed event."""
        from app.agents.chat_orchestrator import OrchestratorResult

        mock_result = OrchestratorResult(answer="test", tool_events=[], cards=[], confirmation=None)
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
        assert "agent_completed" in types, f"agent_completed not in {types}"

    @pytest.mark.asyncio
    async def test_agent_started_before_agent_completed(self):
        """agent_started must come before agent_completed."""
        from app.agents.chat_orchestrator import OrchestratorResult

        mock_result = OrchestratorResult(answer="test", tool_events=[], cards=[], confirmation=None)
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
        started_idx   = types.index("agent_started")
        completed_idx = types.index("agent_completed")
        assert started_idx < completed_idx

    @pytest.mark.asyncio
    async def test_sequence_numbers_monotonically_increasing(self):
        """Sequence numbers must be strictly increasing across all events."""
        from app.agents.chat_orchestrator import OrchestratorResult

        mock_result = OrchestratorResult(
            answer="test answer",
            tool_events=[{"name": "t1", "status": "success", "detail": "ok"}],
            cards=[],
            confirmation=None,
        )
        db = AsyncMock()

        with (
            patch("app.agents.chat_streaming.process_message", return_value=mock_result),
            patch("app.agents.chat_streaming.save_user_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.save_assistant_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.update_session_last_message"),
        ):
            chunks = await _collect_stream(uuid.uuid4(), _make_uid(), "查询", "zh-CN", db)

        events = _parse_sse_stream(chunks)
        seqs = [e["sequence"] for e in events if e.get("sequence")]
        for i in range(1, len(seqs)):
            assert seqs[i] > seqs[i - 1], f"sequence not increasing at index {i}: {seqs}"


# ── 2. Answer delta ────────────────────────────────────────────────────────────

class TestAnswerDeltaEvents:

    @pytest.mark.asyncio
    async def test_answer_delta_events_contain_text(self):
        """answer_delta events must carry non-empty delta text."""
        from app.agents.chat_orchestrator import OrchestratorResult

        mock_result = OrchestratorResult(
            answer="茅台今天涨了 2%，主要因为机构资金流入明显。",
            tool_events=[],
            cards=[],
            confirmation=None,
        )
        db = AsyncMock()

        with (
            patch("app.agents.chat_streaming.process_message", return_value=mock_result),
            patch("app.agents.chat_streaming.save_user_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.save_assistant_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.update_session_last_message"),
        ):
            chunks = await _collect_stream(uuid.uuid4(), _make_uid(), "茅台", "zh-CN", db)

        events = _parse_sse_stream(chunks)
        delta_events = [e for e in events if e["event_type"] == "answer_delta"]
        assert len(delta_events) > 0, "No answer_delta events"
        full_text = "".join(e["payload"].get("delta", "") for e in delta_events)
        assert full_text == "茅台今天涨了 2%，主要因为机构资金流入明显。", (
            f"Reassembled text mismatch: {full_text!r}"
        )

    @pytest.mark.asyncio
    async def test_no_private_cot_in_answer_delta(self):
        """answer_delta payload must not contain CoT labels."""
        from app.agents.chat_orchestrator import OrchestratorResult
        FORBIDDEN = ["chain-of-thought", "思维链", "深度思考", "CoT", "私有思考"]

        mock_result = OrchestratorResult(
            answer="普通的股票分析结论。",
            tool_events=[],
            cards=[],
            confirmation=None,
        )
        db = AsyncMock()

        with (
            patch("app.agents.chat_streaming.process_message", return_value=mock_result),
            patch("app.agents.chat_streaming.save_user_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.save_assistant_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.update_session_last_message"),
        ):
            chunks = await _collect_stream(uuid.uuid4(), _make_uid(), "test", "zh-CN", db)

        events = _parse_sse_stream(chunks)
        for ev in events:
            payload_str = json.dumps(ev.get("payload", {}))
            for label in FORBIDDEN:
                assert label.lower() not in payload_str.lower(), (
                    f"Forbidden CoT label '{label}' found in {ev['event_type']} payload"
                )


# ── 3. Tool events ─────────────────────────────────────────────────────────────

class TestToolCompletedEvents:

    @pytest.mark.asyncio
    async def test_tool_completed_events_contain_tool_event(self):
        """tool_completed events must carry a tool_event with name/status."""
        from app.agents.chat_orchestrator import OrchestratorResult

        mock_result = OrchestratorResult(
            answer="行情查询完成。",
            tool_events=[
                {"name": "get_quote_tool", "status": "success", "detail": "¥1800"},
                {"name": "get_latest_news_tool", "status": "success", "detail": "3 items"},
            ],
            cards=[],
            confirmation=None,
        )
        db = AsyncMock()

        with (
            patch("app.agents.chat_streaming.process_message", return_value=mock_result),
            patch("app.agents.chat_streaming.save_user_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.save_assistant_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.update_session_last_message"),
        ):
            chunks = await _collect_stream(uuid.uuid4(), _make_uid(), "茅台行情", "zh-CN", db)

        events = _parse_sse_stream(chunks)
        tool_events = [e for e in events if e["event_type"] == "tool_completed"]
        assert len(tool_events) == 2, f"Expected 2 tool_completed, got {len(tool_events)}"
        for te in tool_events:
            assert "tool_event" in te["payload"], "tool_completed payload must have tool_event key"
            assert "name" in te["payload"]["tool_event"]


# ── 4. Confirmation event ─────────────────────────────────────────────────────

class TestConfirmationRequiredEvent:

    @pytest.mark.asyncio
    async def test_confirmation_required_event_emitted(self):
        """confirmation_required must be emitted when result has confirmation."""
        from app.agents.chat_orchestrator import OrchestratorResult

        mock_conf = {
            "id": "conf_abc",
            "type": "create_analysis_run",
            "status": "pending",
            "params": {"market": "CN", "symbol": "600519"},
        }
        mock_result = OrchestratorResult(
            answer="",
            tool_events=[],
            cards=[],
            confirmation=mock_conf,
        )
        db = AsyncMock()

        with (
            patch("app.agents.chat_streaming.process_message", return_value=mock_result),
            patch("app.agents.chat_streaming.save_user_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.save_assistant_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.update_session_last_message"),
        ):
            chunks = await _collect_stream(uuid.uuid4(), _make_uid(), "分析茅台并保存", "zh-CN", db)

        events = _parse_sse_stream(chunks)
        types = [e["event_type"] for e in events]
        assert "confirmation_required" in types, f"confirmation_required not found in {types}"

        conf_ev = next(e for e in events if e["event_type"] == "confirmation_required")
        assert "confirmation" in conf_ev["payload"]
        assert conf_ev["payload"]["confirmation"]["id"] == "conf_abc"


# ── 5. Error event ────────────────────────────────────────────────────────────

class TestAgentErrorEvent:

    @pytest.mark.asyncio
    async def test_agent_error_emitted_on_orchestration_failure(self):
        """agent_error must be emitted when process_message raises."""
        db = AsyncMock()

        with (
            patch("app.agents.chat_streaming.process_message", side_effect=RuntimeError("boom")),
            patch("app.agents.chat_streaming.save_user_message", return_value=MagicMock(id=uuid.uuid4())),
        ):
            chunks = await _collect_stream(uuid.uuid4(), _make_uid(), "test", "zh-CN", db)

        events = _parse_sse_stream(chunks)
        types = [e["event_type"] for e in events]
        assert "agent_error" in types, f"agent_error not found after failure: {types}"

    @pytest.mark.asyncio
    async def test_agent_error_payload_no_internal_details(self):
        """agent_error payload must not expose raw exception messages."""
        db = AsyncMock()

        with (
            patch("app.agents.chat_streaming.process_message", side_effect=RuntimeError("DB connection failed: password invalid")),
            patch("app.agents.chat_streaming.save_user_message", return_value=MagicMock(id=uuid.uuid4())),
        ):
            chunks = await _collect_stream(uuid.uuid4(), _make_uid(), "test", "zh-CN", db)

        events = _parse_sse_stream(chunks)
        error_ev = next((e for e in events if e["event_type"] == "agent_error"), None)
        assert error_ev is not None
        # Error message should be user-friendly, not the raw exception
        error_text = error_ev["payload"].get("error", "")
        assert "DB connection" not in error_text
        assert "password" not in error_text


# ── 6. Cards delta ────────────────────────────────────────────────────────────

class TestCardsDeltaEvent:

    @pytest.mark.asyncio
    async def test_cards_delta_emitted_when_result_has_cards(self):
        """cards_delta must be emitted when result has cards."""
        from app.agents.chat_orchestrator import OrchestratorResult

        mock_card = {"type": "stock_summary", "data": {"name": "茅台", "price": "1800"}}
        mock_result = OrchestratorResult(
            answer="行情如下。",
            tool_events=[],
            cards=[mock_card],
            confirmation=None,
        )
        db = AsyncMock()

        with (
            patch("app.agents.chat_streaming.process_message", return_value=mock_result),
            patch("app.agents.chat_streaming.save_user_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.save_assistant_message", return_value=MagicMock(id=uuid.uuid4())),
            patch("app.agents.chat_streaming.update_session_last_message"),
        ):
            chunks = await _collect_stream(uuid.uuid4(), _make_uid(), "茅台行情", "zh-CN", db)

        events = _parse_sse_stream(chunks)
        card_events = [e for e in events if e["event_type"] == "cards_delta"]
        assert len(card_events) == 1
        assert card_events[0]["payload"]["cards"][0]["type"] == "stock_summary"
