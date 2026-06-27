"""
Chat Streaming — Phase C13-a.

stream_chat_message() is an async generator that yields SSE-formatted strings.
It wraps the existing process_message() orchestrator with:

  1.  Phase-level events emitted BEFORE orchestration starts
      (user_message_saved, agent_started, assistant_placeholder_created)
  2.  Fine-grained events emitted BY the orchestrator via event_callback
      (intent_detected, skill_started, skill_completed, tool_completed, …)
  3.  Result events streamed AFTER orchestration completes
      (confirmation_required, cards_delta, answer_delta, agent_completed)
  4.  Keepalive comments every 15 s while the orchestrator is working
  5.  agent_error on any exception — graceful close

Architecture:
  - Uses asyncio.Queue + background Task so keepalives can be sent while
    process_message() is running (both share the same event loop / db session;
    no concurrent db access because the generator only reads from the queue).
  - The background task owns all db operations.  The generator only yields
    strings from the queue.

Safety constraints (inherited from C11/C12):
  - Payload must NOT contain private chain-of-thought.
  - Payload must NOT contain raw news full-text.
  - answer_delta carries final answer text only.
  - tool events carry tool_name / status / summary (no internal prompts).
"""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Callable

import logging

from app.agents.chat_orchestrator import process_message
from app.agents.financial_safety_postprocessor import sanitize_financial_answer
from app.services.chat_service import (
    save_user_message,
    save_assistant_message,
    update_session_last_message,
    maybe_update_session_title,
)

log = logging.getLogger(__name__)

# ── Event types ────────────────────────────────────────────────────────────────

ETYPE_USER_SAVED          = "user_message_saved"
ETYPE_AGENT_STARTED       = "agent_started"
ETYPE_PLACEHOLDER_CREATED = "assistant_placeholder_created"
ETYPE_INTENT_DETECTED     = "intent_detected"
ETYPE_PLANNER_STARTED     = "planner_started"
ETYPE_PLANNER_STEP_START  = "planner_step_started"
ETYPE_PLANNER_STEP_DONE   = "planner_step_completed"
ETYPE_SKILL_STARTED       = "skill_started"
ETYPE_SKILL_COMPLETED     = "skill_completed"
ETYPE_TOOL_STARTED        = "tool_started"
ETYPE_TOOL_COMPLETED      = "tool_completed"
ETYPE_RAG_RETRIEVE_START  = "rag_retrieve_started"
ETYPE_RAG_RETRIEVE_DONE   = "rag_retrieve_completed"
ETYPE_RAG_REVIEW_START    = "rag_review_started"
ETYPE_RAG_REVIEW_DONE     = "rag_review_completed"
ETYPE_CONFIRM_REQUIRED    = "confirmation_required"
ETYPE_ANSWER_DELTA        = "answer_delta"
ETYPE_CARDS_DELTA         = "cards_delta"
ETYPE_COMPLETED           = "agent_completed"
ETYPE_ERROR               = "agent_error"
ETYPE_KEEPALIVE           = "keepalive"

# Phase 1: real thinking and structured final_answer
ETYPE_THINKING            = "thinking"
ETYPE_TOOL_CALL_START     = "tool_call_start"
ETYPE_TOOL_CALL_RESULT    = "tool_call_result"
ETYPE_FINAL_ANSWER        = "final_answer"

# Phase 2E-1: Multi-Agent Orchestrator events
ETYPE_ORCHESTRATOR_START  = "orchestrator_start"
ETYPE_SUBAGENT_START      = "subagent_start"
ETYPE_SUBAGENT_RESULT     = "subagent_result"
ETYPE_RISK_REVIEW_START   = "risk_review_start"
ETYPE_RISK_REVIEW_RESULT  = "risk_review_result"
ETYPE_SYNTHESIS_START     = "synthesis_start"

_TERMINAL_TYPES = {ETYPE_COMPLETED, ETYPE_ERROR}


# ── Fallback final answer ──────────────────────────────────────────────────────

def build_fallback_final_answer(reason: str = "") -> dict:
    """
    Return a safe, no-hallucination fallback final_answer payload.

    Called when SSE stream hits an exception or timeout before a real
    final_answer has been emitted.  Never invents data — only returns
    a structured error shell with the safety disclaimer.
    """
    note = f"（{reason[:120]}）" if reason else ""
    return {
        "summary":      f"本次请求未能完成，请稍后重试。{note}",
        "analysis":     "由于技术原因，本次分析未能完成。请检查网络或稍后重试。",
        "data_points":  [],
        "risk_points":  ["分析过程发生错误，结论不可信赖，请重新提问"],
        "sources":      [],
        "disclaimer":   "仅供研究参考，不构成投资建议。",
        "data_quality": {"market_data_available": False, "warnings": []},
    }


# ── ChatStreamEvent ────────────────────────────────────────────────────────────

@dataclass
class ChatStreamEvent:
    event_type: str
    sequence: int
    payload: dict = field(default_factory=dict)
    message_id: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_sse(self) -> str:
        data = {
            "event_type": self.event_type,
            "sequence":   self.sequence,
            "message_id": self.message_id,
            "payload":    self.payload,
            "created_at": self.created_at,
        }
        return (
            f"event: {self.event_type}\n"
            f"id: {self.sequence}\n"
            f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
        )


# ── Main generator ─────────────────────────────────────────────────────────────

_KEEPALIVE_INTERVAL = 15.0   # seconds between keepalive comments
_ANSWER_CHUNK_SIZE  = 25     # chars per answer_delta chunk
_TOOL_EVENT_DELAY   = 0.05   # seconds between streaming consecutive tool events


async def stream_chat_message(
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    content: str,
    output_language: str,
    db: Any,
) -> AsyncGenerator[str, None]:
    """
    Async generator that yields SSE-formatted strings for the chat stream
    endpoint.

    Callers should wrap this in StreamingResponse (media_type="text/event-stream").
    Client disconnection / hard timeout triggers CancelledError which cancels
    the background orchestration task automatically.
    """
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    seq_counter = [0]
    # placeholder ID used before the real assistant message is persisted
    assistant_placeholder_id = str(uuid.uuid4())

    # ── helpers ────────────────────────────────────────────────────────────────

    def _make_sse(event_type: str, payload: dict, mid: str = "") -> str:
        seq_counter[0] += 1
        ev = ChatStreamEvent(
            event_type=event_type,
            sequence=seq_counter[0],
            payload=payload,
            message_id=mid,
        )
        return ev.to_sse()

    def _keepalive() -> str:
        return ": keepalive\n\n"

    # ── background orchestration task ──────────────────────────────────────────

    async def _orchestrate() -> None:
        """
        Runs the full chat pipeline and puts SSE strings into the queue.
        Sentinel None signals stream-end.

        C25 guarantee: regardless of success / tool failure / LLM failure /
        timeout / any unhandled exception, the stream ALWAYS emits:
          1. final_answer  (real or fallback)
          2. agent_completed (or agent_error + agent_completed)
          3. None sentinel
        """
        # C25: track whether these critical events have been emitted
        final_answer_sent = [False]
        done_sent         = [False]

        try:
            # ── Phase 1: persist user message ─────────────────────────────────
            user_msg = await save_user_message(
                db, session_id, user_id, content, output_language
            )
            await queue.put(_make_sse(
                ETYPE_USER_SAVED,
                {"message_id": str(user_msg.id)},
            ))

            # ── Phase 1b: auto-update session title on first message ──────────
            try:
                new_title = await maybe_update_session_title(db, session_id, content)
                if new_title:
                    await queue.put(_make_sse(
                        "session_title_updated",
                        {"session_id": str(session_id), "title": new_title},
                    ))
            except Exception:
                log.debug("chat_streaming: session title update failed (non-fatal)")

            # ── Phase 2: emit immediate phase events ──────────────────────────
            await queue.put(_make_sse(
                ETYPE_AGENT_STARTED,
                {"session_id": str(session_id)},
                mid=assistant_placeholder_id,
            ))
            await queue.put(_make_sse(
                ETYPE_PLACEHOLDER_CREATED,
                {"message_id": assistant_placeholder_id},
                mid=assistant_placeholder_id,
            ))

            # ── Phase 3: build event_callback for real-time fine events ───────
            # Dedup tracking: tool events emitted in real-time
            # Key = (tool_name, started_at) to handle duplicate tool calls
            _emitted_tool_keys: set[str] = set()
            # Track whether FinancialAgent already streamed answer_delta in real-time.
            # If True, Phase 8 must NOT replay result.answer (would double the text).
            _realtime_answer_delta_emitted = [False]

            async def _emit(event_type: str, payload: dict) -> None:
                """Safe callback passed to orchestrator / skills."""
                try:
                    # Track tool_completed events for dedup in Phase 5
                    if event_type == "tool_completed":
                        key = f"{payload.get('tool_name', '')}|{payload.get('started_at', '')}"
                        _emitted_tool_keys.add(key)
                    # Track whether real-time answer streaming already happened
                    if event_type == "answer_delta":
                        _realtime_answer_delta_emitted[0] = True
                    # C25: track sentinel events so finally-block can fill gaps
                    # C26: sanitize all final_answer payloads before emitting
                    if event_type in ("final_answer", ETYPE_FINAL_ANSWER):
                        payload = sanitize_financial_answer(payload)
                        final_answer_sent[0] = True
                    if event_type in ("agent_completed", ETYPE_COMPLETED):
                        done_sent[0] = True
                    sse = _make_sse(event_type, payload, mid=assistant_placeholder_id)
                    await queue.put(sse)
                except Exception:  # never crash the main flow
                    log.debug("stream emit failed for %s", event_type)

            # ── Phase 4: run orchestrator ─────────────────────────────────────
            result = await process_message(
                content=content,
                db=db,
                user_id=user_id,
                output_language=output_language,
                session_id=session_id,
                event_callback=_emit,
            )

            # ── Phase 5: stream tool events from result (fallback for non-real-time) ──
            for te in result.tool_events:
                # Skip RAG pseudo-events from replay (they're sent as distinct
                # rag_retrieve/review events in real-time via event_callback)
                tool_name = te.get("name", te.get("tool_name", ""))
                if tool_name in ("rag_retrieve", "rag_review"):
                    continue
                # Dedup: skip events already emitted in real-time via event_callback.
                # C25.12: ToolRegistry.call() does not set started_at in tool_completed
                # payload, so started_at is always "". The old guard `and started_at`
                # caused dedup to never fire. Fix: check set membership alone.
                # Also always skip report skill tools — they always emit in real-time.
                if tool_name in ("get_recent_reports_tool", "get_report_detail_tool"):
                    continue
                started_at = te.get("started_at", "")
                dedup_key = f"{tool_name}|{started_at}"
                if dedup_key in _emitted_tool_keys:
                    continue  # already pushed real-time
                await queue.put(_make_sse(
                    ETYPE_TOOL_COMPLETED,
                    {"tool_event": te},
                    mid=assistant_placeholder_id,
                ))
                await asyncio.sleep(_TOOL_EVENT_DELAY)

            # ── Phase 6: confirmation ─────────────────────────────────────────
            if result.confirmation:
                await queue.put(_make_sse(
                    ETYPE_CONFIRM_REQUIRED,
                    {"confirmation": result.confirmation},
                    mid=assistant_placeholder_id,
                ))

            # ── Phase 7: cards ────────────────────────────────────────────────
            if result.cards:
                await queue.put(_make_sse(
                    ETYPE_CARDS_DELTA,
                    {"cards": result.cards},
                    mid=assistant_placeholder_id,
                ))

            # ── Phase 8: answer delta (chunked) ───────────────────────────────
            # Skip replay if FinancialAgent already streamed answer_delta in
            # real-time via event_callback — replaying would double the text.
            answer = result.answer or ""
            if not _realtime_answer_delta_emitted[0]:
                for i in range(0, len(answer), _ANSWER_CHUNK_SIZE):
                    chunk = answer[i : i + _ANSWER_CHUNK_SIZE]
                    await queue.put(_make_sse(
                        ETYPE_ANSWER_DELTA,
                        {"delta": chunk},
                        mid=assistant_placeholder_id,
                    ))
                    await asyncio.sleep(0.02)

            # ── Phase 9: persist assistant message ────────────────────────────
            saved_msg = await save_assistant_message(
                db=db,
                session_id=session_id,
                user_id=user_id,
                answer=result.answer,
                tool_events=result.tool_events,
                cards=result.cards,
                confirmation=result.confirmation,
                output_language=output_language,
                extra_metadata={**result.metadata, "streamed": True},
            )
            await update_session_last_message(db, session_id)
            await db.commit()

            final_mid = str(saved_msg.id)
            await queue.put(_make_sse(
                ETYPE_COMPLETED,
                {
                    "message_id":       final_mid,
                    "has_confirmation": result.confirmation is not None,
                    "has_cards":        bool(result.cards),
                    "answer_length":    len(result.answer),
                },
                mid=final_mid,
            ))
            done_sent[0] = True

        except Exception as exc:
            log.exception("chat_streaming: orchestration error")
            # C25: guarantee final_answer + done are emitted even on exception
            try:
                if not final_answer_sent[0]:
                    await queue.put(_make_sse(
                        ETYPE_FINAL_ANSWER,
                        build_fallback_final_answer(str(exc)),
                        mid=assistant_placeholder_id,
                    ))
                    final_answer_sent[0] = True
                await queue.put(_make_sse(
                    ETYPE_ERROR,
                    {"error": "请求处理失败，请稍后重试。"},
                    mid=assistant_placeholder_id,
                ))
                if not done_sent[0]:
                    await queue.put(_make_sse(
                        ETYPE_COMPLETED,
                        {
                            "message_id":       assistant_placeholder_id,
                            "has_confirmation": False,
                            "has_cards":        False,
                            "answer_length":    0,
                        },
                        mid=assistant_placeholder_id,
                    ))
                    done_sent[0] = True
            except Exception:
                pass
        finally:
            # C25: last-resort guarantee — if anything above crashed silently
            try:
                if not final_answer_sent[0]:
                    await queue.put(_make_sse(
                        ETYPE_FINAL_ANSWER,
                        build_fallback_final_answer(""),
                        mid=assistant_placeholder_id,
                    ))
                if not done_sent[0]:
                    await queue.put(_make_sse(
                        ETYPE_COMPLETED,
                        {
                            "message_id":       assistant_placeholder_id,
                            "has_confirmation": False,
                            "has_cards":        False,
                            "answer_length":    0,
                        },
                        mid=assistant_placeholder_id,
                    ))
            except Exception:
                pass
            await queue.put(None)  # sentinel — close stream

    # ── Start background task ──────────────────────────────────────────────────
    task = asyncio.create_task(_orchestrate())

    # ── Yield from queue with keepalive ───────────────────────────────────────
    try:
        while True:
            try:
                item = await asyncio.wait_for(
                    asyncio.shield(queue.get()),
                    timeout=_KEEPALIVE_INTERVAL,
                )
            except asyncio.TimeoutError:
                yield _keepalive()
                continue

            if item is None:
                yield ": stream-end\n\n"
                break
            yield item

    except asyncio.CancelledError:
        # Client disconnected or server cancelled the stream
        task.cancel()
        raise
    except Exception:
        task.cancel()
        raise
