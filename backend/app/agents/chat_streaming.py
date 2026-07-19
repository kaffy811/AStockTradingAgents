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
from app.core.database import AsyncSessionLocal
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
ETYPE_ANSWER_COMPLETED    = "answer_completed"
ETYPE_CARDS_DELTA         = "cards_delta"
ETYPE_MESSAGE_PERSISTED   = "message_persisted"
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


# ── Error sanitization ────────────────────────────────────────────────────────

_DB_ERROR_PATTERNS = (
    "PendingRollback", "InFailedSQLTransaction", "sqlalchemy",
    "asyncpg", "psycopg", "connection", "IntegrityError",
    "OperationalError", "DatabaseError",
)

def _sanitize_error_for_user(exc: BaseException) -> str:
    """
    C30.3.6: Return a user-safe error description.

    Raw SQLAlchemy / DB error messages must never reach the user — they
    may contain connection strings, table schemas, or SQL fragments.
    Replace them with a generic, friendly message.
    """
    raw = str(exc)
    if any(pat in raw for pat in _DB_ERROR_PATTERNS) or any(
        pat in type(exc).__name__ for pat in _DB_ERROR_PATTERNS
    ):
        return "服务暂时不可用"
    return raw[:200]  # cap length for non-DB errors


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
_EMPTY_FINAL_ANSWER_TEXT = "报告数据已获取，但本次回答生成失败，请重新尝试。"
_ORCHESTRATION_TIMEOUT_SECONDS = 55.0
_DB_OPERATION_TIMEOUT_SECONDS = 8.0
_DB_ROLLBACK_TIMEOUT_SECONDS = 3.0


async def _rollback_safely(db: Any, *, owner: str) -> None:
    try:
        await asyncio.wait_for(db.rollback(), timeout=_DB_ROLLBACK_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        log.warning("db_session_rollback_timeout owner=%s", owner)
    except Exception as exc:  # noqa: BLE001
        log.warning("db_session_rollback_failed owner=%s error_class=%s", owner, type(exc).__name__)


class _BorrowedSessionContext:
    """Compatibility context for unit tests that inject a mocked DB session."""

    def __init__(self, session: Any) -> None:
        self.session = session

    async def __aenter__(self) -> Any:
        return self.session

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


def _session_context(db_override: Any = None) -> Any:
    if db_override is not None:
        return _BorrowedSessionContext(db_override)
    return AsyncSessionLocal()


async def _run_short_db_operation(
    owner: str,
    operation: Callable[[Any], Any],
    *,
    db_override: Any = None,
) -> Any:
    """Run one DB operation in an isolated transaction and close the session."""
    async with _session_context(db_override) as session:
        try:
            result = operation(session)
            if hasattr(result, "__await__"):
                result = await asyncio.wait_for(result, timeout=_DB_OPERATION_TIMEOUT_SECONDS)
            await asyncio.wait_for(session.commit(), timeout=_DB_OPERATION_TIMEOUT_SECONDS)
            return result
        except asyncio.TimeoutError:
            await _rollback_safely(session, owner=owner)
            log.warning("db_session_failed owner=%s error_class=TimeoutError", owner)
            raise
        except asyncio.CancelledError:
            await _rollback_safely(session, owner=owner)
            raise
        except Exception:
            await _rollback_safely(session, owner=owner)
            log.exception("db_session_failed owner=%s", owner)
            raise


def _answer_text_from_final_payload(payload: dict) -> str:
    """Build a user-visible text answer from a structured final_answer payload."""
    if not isinstance(payload, dict):
        return str(payload or "").strip()
    for key in ("full_text", "answer", "content", "text", "message", "response"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "\n\n".join(
        str(payload.get(key) or "").strip()
        for key in ("summary", "analysis", "disclaimer")
        if str(payload.get(key) or "").strip()
    ).strip()


async def stream_chat_message(
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    content: str,
    output_language: str,
    db: Any = None,
) -> AsyncGenerator[str, None]:
    """
    Async generator that yields SSE-formatted strings for the chat stream
    endpoint.

    Callers should wrap this in StreamingResponse (media_type="text/event-stream").
    Client disconnection / hard timeout triggers CancelledError which cancels
    the background orchestration task automatically.

    The optional ``db`` argument is retained for existing unit tests and direct
    internal callers.  The HTTP route intentionally does not pass its request
    scoped session here; production streaming uses operation-scoped sessions.
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
        answer_completed_sent = [False]
        done_sent         = [False]
        # Track the orchestration result so we can persist it even on error
        _result_ref: list = [None]
        # C32.1.4: True when result is confirmation-only (no answer expected).
        # The finally/except blocks must NOT emit a fallback final_answer in
        # this case — the confirmation card IS the result, not an error.
        _has_confirmation_only = [False]

        try:
            # ── Phase 1: persist user message ─────────────────────────────────
            user_message_id = await _run_short_db_operation(
                "chat_stream.user_message",
                lambda op_db: _save_user_message_id(op_db, session_id, user_id, content, output_language),
                db_override=db,
            )
            await queue.put(_make_sse(
                ETYPE_USER_SAVED,
                {"message_id": user_message_id},
            ))

            # ── Phase 1b: auto-update session title on first message ──────────
            # C30.3.1: title update runs in its own mini-transaction.  If it
            # fails we explicitly rollback so the session is clean before the
            # orchestrator (Phase 4) starts — no PendingRollback can leak.
            try:
                new_title = await _run_short_db_operation(
                    "chat_stream.session_title",
                    lambda op_db: maybe_update_session_title(op_db, session_id, content),
                    db_override=db,
                )
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
                    if event_type in ("agent_completed", ETYPE_COMPLETED):
                        return
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
                    if event_type == ETYPE_ANSWER_COMPLETED:
                        answer_completed_sent[0] = True
                    sse = _make_sse(event_type, payload, mid=assistant_placeholder_id)
                    await queue.put(sse)
                except Exception:  # never crash the main flow
                    log.debug("stream emit failed for %s", event_type)

            # ── Phase 4: run orchestrator ─────────────────────────────────────
            async with _session_context(db) as legacy_db:
                legacy_task: asyncio.Task | None = None
                try:
                    legacy_task = asyncio.create_task(
                        process_message(
                            content=content,
                            db=legacy_db,
                            user_id=user_id,
                            output_language=output_language,
                            session_id=session_id,
                            event_callback=_emit,
                        )
                    )
                    result = _result_ref[0] = await asyncio.wait_for(
                        asyncio.shield(legacy_task),
                        timeout=_ORCHESTRATION_TIMEOUT_SECONDS,
                    )
                    await legacy_db.rollback()
                except asyncio.TimeoutError:
                    if legacy_task is not None:
                        legacy_task.cancel()
                        done, _pending = await asyncio.wait({legacy_task}, timeout=1.0)
                        for completed in done:
                            try:
                                completed.exception()
                            except asyncio.CancelledError:
                                pass
                            except Exception as exc:  # noqa: BLE001
                                log.debug("chat_streaming: timed-out legacy task failed during cancellation: %s", exc)
                    _record_shadow_timeout_diagnostic(
                        raw_query=content,
                        conversation_id=str(session_id),
                        user_id=str(user_id),
                    )
                    await _rollback_safely(legacy_db, owner="chat_stream.legacy_execution_timeout")
                    raise TimeoutError("STREAM_ORCHESTRATION_TIMEOUT")
                except asyncio.CancelledError:
                    if legacy_task is not None:
                        legacy_task.cancel()
                    await _rollback_safely(legacy_db, owner="chat_stream.legacy_execution")
                    raise
                except Exception:
                    if legacy_task is not None and not legacy_task.done():
                        legacy_task.cancel()
                    await _rollback_safely(legacy_db, owner="chat_stream.legacy_execution")
                    raise

            # C32.1.4: flag confirmation-only results so finally doesn't send
            # fallback final_answer (which would show "本次请求未能完成" to the user)
            if result.confirmation is not None and not result.answer:
                _has_confirmation_only[0] = True
            else:
                answer_text = str(result.answer or "").strip()
                if not answer_text:
                    result.answer = _EMPTY_FINAL_ANSWER_TEXT
                    result.metadata = {
                        **(result.metadata or {}),
                        "status": "failed",
                        "error_code": "EMPTY_FINAL_ANSWER",
                    }
                else:
                    result.answer = answer_text
                    result.metadata = {
                        **(result.metadata or {}),
                        "status": (result.metadata or {}).get("status") or "completed",
                    }

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

            # ── Phase 7b: C27 data_quality_update for skill path ─────────────
            # For the financial_agent path, data_quality is already embedded in
            # the final_answer SSE event emitted by the agent.  For skills, we
            # emit a separate data_quality_update event so the frontend can show
            # the DataQuality card even when there is no structured final_answer.
            if not final_answer_sent[0]:
                dq_payload = result.metadata.get("data_quality")
                sources_payload = result.metadata.get("sources_c27")
                if dq_payload:
                    await queue.put(_make_sse(
                        "data_quality_update",
                        {
                            "data_quality": dq_payload,
                            "sources":      sources_payload or [],
                        },
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

            # ── Phase 8b: canonical answer completion ───────────────────────
            if not _has_confirmation_only[0]:
                await queue.put(_make_sse(
                    ETYPE_ANSWER_COMPLETED,
                    {
                        "answer":        answer,
                        "final_answer":  answer,
                        "answer_length": len(answer),
                        "status":        result.metadata.get("status", "completed"),
                        "error_code":    result.metadata.get("error_code"),
                    },
                    mid=assistant_placeholder_id,
                ))
                answer_completed_sent[0] = True

            # ── Phase 9: persist assistant message ────────────────────────────
            final_mid = await _run_short_db_operation(
                "chat_stream.assistant_message",
                lambda op_db: _save_assistant_message_id(
                    op_db,
                    session_id=session_id,
                    user_id=user_id,
                    answer=result.answer,
                    tool_events=result.tool_events,
                    cards=result.cards,
                    confirmation=result.confirmation,
                    output_language=output_language,
                    extra_metadata={**result.metadata, "streamed": True},
                ),
                db_override=db,
            )
            await queue.put(_make_sse(
                ETYPE_MESSAGE_PERSISTED,
                {
                    "message_id":           final_mid,
                    "assistant_message_id": final_mid,
                    "answer_length":        len(result.answer or ""),
                    "status":               result.metadata.get("status", "completed"),
                    "error_code":           result.metadata.get("error_code"),
                },
                mid=final_mid,
            ))
            await queue.put(_make_sse(
                ETYPE_COMPLETED,
                {
                    "message_id":           final_mid,
                    "assistant_message_id": final_mid,
                    "has_confirmation":     result.confirmation is not None,
                    "has_cards":            bool(result.cards),
                    "answer_length":        len(result.answer or ""),
                    "status":               result.metadata.get("status", "completed"),
                    "error_code":           result.metadata.get("error_code"),
                },
                mid=final_mid,
            ))
            done_sent[0] = True

        except Exception as exc:
            log.exception("chat_streaming: orchestration error")
            # C25: guarantee final_answer + done are emitted even on exception
            try:
                # C32.1.4: skip fallback for confirmation-only flows
                if not final_answer_sent[0] and not answer_completed_sent[0] and not _has_confirmation_only[0]:
                    fallback_payload = build_fallback_final_answer(
                        _sanitize_error_for_user(exc)  # C30.3.6: no raw DB errors
                    )
                    await queue.put(_make_sse(
                        ETYPE_FINAL_ANSWER,
                        fallback_payload,
                        mid=assistant_placeholder_id,
                    ))
                    final_answer_sent[0] = True
                    if not answer_completed_sent[0]:
                        fallback_answer = _answer_text_from_final_payload(fallback_payload) or _EMPTY_FINAL_ANSWER_TEXT
                        await queue.put(_make_sse(
                            ETYPE_ANSWER_COMPLETED,
                            {
                                "answer":        fallback_answer,
                                "final_answer":  fallback_answer,
                                "answer_length": len(fallback_answer),
                                "status":        "failed",
                                "error_code":    "STREAM_ORCHESTRATION_ERROR",
                            },
                            mid=assistant_placeholder_id,
                        ))
                        answer_completed_sent[0] = True
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
                            "assistant_message_id": assistant_placeholder_id,
                            "has_confirmation": False,
                            "has_cards":        False,
                            "answer_length":    0,
                            "status":           "failed",
                            "error_code":       "STREAM_ORCHESTRATION_ERROR",
                        },
                        mid=assistant_placeholder_id,
                    ))
                    done_sent[0] = True
            except Exception:
                pass
            # C32-fix: persist assistant message even on error when possible,
            # but never delay the terminal event or stream sentinel.
            _err_result = _result_ref[0]
            _err_answer = (
                _err_result.answer
                if _err_result is not None and _err_result.answer
                else "请求处理遇到错误，无法生成完整分析。请稍后重试。"
            )
            _persist_task = asyncio.create_task(_persist_error_assistant_message_best_effort(
                db_override=db,
                session_id=session_id,
                user_id=user_id,
                answer=_err_answer,
                tool_events=_err_result.tool_events if _err_result else [],
                output_language=output_language,
            ))

            def _consume_persist_error(done_task: asyncio.Task) -> None:
                try:
                    done_task.exception()
                except asyncio.CancelledError:
                    pass
                except Exception as persist_exc:  # noqa: BLE001
                    log.debug("chat_streaming: error assistant persistence task failed: %s", persist_exc)

            _persist_task.add_done_callback(_consume_persist_error)
        finally:
            # C25: last-resort guarantee — if anything above crashed silently
            try:
                # C32.1.4: confirmation-only results don't need a final_answer
                if not final_answer_sent[0] and not answer_completed_sent[0] and not _has_confirmation_only[0]:
                    fallback_payload = build_fallback_final_answer("")
                    await queue.put(_make_sse(
                        ETYPE_FINAL_ANSWER,
                        fallback_payload,
                        mid=assistant_placeholder_id,
                    ))
                    final_answer_sent[0] = True
                if not answer_completed_sent[0] and not _has_confirmation_only[0]:
                    fallback_answer = _answer_text_from_final_payload(build_fallback_final_answer("")) or _EMPTY_FINAL_ANSWER_TEXT
                    await queue.put(_make_sse(
                        ETYPE_ANSWER_COMPLETED,
                        {
                            "answer":        fallback_answer,
                            "final_answer":  fallback_answer,
                            "answer_length": len(fallback_answer),
                            "status":        "failed",
                            "error_code":    "EMPTY_FINAL_ANSWER",
                        },
                        mid=assistant_placeholder_id,
                    ))
                if not done_sent[0]:
                    await queue.put(_make_sse(
                        ETYPE_COMPLETED,
                        {
                            "message_id":           assistant_placeholder_id,
                            "assistant_message_id": assistant_placeholder_id,
                            "has_confirmation":     False,
                            "has_cards":            False,
                            "answer_length":        0,
                            "status":               "failed",
                            "error_code":           "STREAM_INCOMPLETE",
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


async def _save_user_message_id(
    db: Any,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    content: str,
    output_language: str,
) -> str:
    msg = await save_user_message(db, session_id, user_id, content, output_language)
    return str(msg.id)


async def _save_assistant_message_id(
    db: Any,
    *,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    answer: str,
    tool_events: list,
    cards: list,
    confirmation: dict | None,
    output_language: str,
    extra_metadata: dict | None,
) -> str:
    saved_msg = await save_assistant_message(
        db=db,
        session_id=session_id,
        user_id=user_id,
        answer=answer,
        tool_events=tool_events,
        cards=cards,
        confirmation=confirmation,
        output_language=output_language,
        extra_metadata=extra_metadata,
    )
    await update_session_last_message(db, session_id)
    return str(saved_msg.id)


async def _persist_error_assistant_message_best_effort(
    *,
    db_override: Any,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    answer: str,
    tool_events: list,
    output_language: str,
) -> None:
    try:
        await _run_short_db_operation(
            "chat_stream.error_assistant_message",
            lambda op_db: _save_assistant_message_id(
                op_db,
                session_id=session_id,
                user_id=user_id,
                answer=answer,
                tool_events=tool_events,
                cards=[],
                confirmation=None,
                output_language=output_language,
                extra_metadata={"streamed": True, "error": True},
            ),
            db_override=db_override,
        )
    except Exception:
        log.debug("chat_streaming: could not persist assistant message on error (non-fatal)")


def _record_shadow_timeout_diagnostic(*, raw_query: str, conversation_id: str, user_id: str) -> None:
    try:
        from app.agent_runtime.contracts import new_id  # noqa: PLC0415
        from app.agent_runtime.shadow_diagnostics import pi_shadow_diagnostics_sink  # noqa: PLC0415
        from app.core.config import settings  # noqa: PLC0415

        if (getattr(settings, "agent_executor_mode", "legacy") or "").strip().lower() != "pi_compatible_shadow":
            return
        pi_shadow_diagnostics_sink.record(
            raw_query=raw_query,
            conversation_id=conversation_id,
            user_id=user_id,
            result={
                "schema_version": "pi_financial_runtime_v1",
                "trace_id": new_id("trace"),
                "run_id": new_id("run"),
                "status": "timeout",
                "agent_id": "official_report_pdf_pi_v1",
                "turn_count": 0,
                "tool_call_count": 0,
                "metrics": {"latency_ms": int(_ORCHESTRATION_TIMEOUT_SECONDS * 1000), "model_calls": 0, "tool_calls": 0},
                "error": {"code": "PI_SHADOW_STREAM_ORCHESTRATION_TIMEOUT"},
                "events": [],
                "findings": [],
                "evidence_ids": [],
                "shadow_input": {"conversation_id": conversation_id},
            },
        )
    except Exception as exc:  # noqa: BLE001
        log.debug("chat_streaming: shadow timeout diagnostic failed: %s", exc)
