"""
Chat Service — CRUD for chat_sessions and chat_messages (Phase C3).

All user-scoped: every query includes user_id so sessions cannot
cross between users.
"""
from __future__ import annotations

import logging
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

from app.models.chat import (
    ChatMessage,
    ChatMessageItem,
    ChatSession,
    ChatSessionCreateResponse,
    ChatSessionListItem,
    ChatSessionSearchItem,
)


# ── Session CRUD ───────────────────────────────────────────────────────────────

async def create_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    title: str | None,
) -> ChatSessionCreateResponse:
    effective_title = title or "新的研究对话"
    session = ChatSession(
        user_id=user_id,
        title=effective_title,
        status="active",
        session_metadata={"orchestrator": "c4_real_tools", "mock_mode": False},
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return ChatSessionCreateResponse(
        session_id=session.id,
        title=session.title,
        status=session.status,
        created_at=session.created_at,
    )


async def list_sessions(
    db: AsyncSession,
    user_id: uuid.UUID,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[ChatSessionListItem], int]:
    """Return (items, total) for a user's non-deleted sessions."""
    count_stmt = (
        select(func.count())
        .select_from(ChatSession)
        .where(
            ChatSession.user_id == user_id,
            ChatSession.status != "deleted",
        )
    )
    total: int = (await db.execute(count_stmt)).scalar_one()

    if total == 0:
        return [], 0

    list_stmt = (
        select(ChatSession)
        .where(
            ChatSession.user_id == user_id,
            ChatSession.status != "deleted",
        )
        .order_by(ChatSession.last_message_at.desc().nullslast(), desc(ChatSession.created_at))
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(list_stmt)).scalars().all()

    # Build preview from last message (one extra query — acceptable at list scale)
    items: list[ChatSessionListItem] = []
    for row in rows:
        preview = await _get_session_preview(db, row.id)
        items.append(ChatSessionListItem(
            session_id=row.id,
            title=row.title,
            status=row.status,
            last_message_at=row.last_message_at,
            preview=preview,
        ))

    return items, total


async def _get_session_preview(db: AsyncSession, session_id: uuid.UUID) -> str:
    """Return last assistant message content (first 80 chars) or ''."""
    stmt = (
        select(ChatMessage.content)
        .where(
            ChatMessage.session_id == session_id,
            ChatMessage.role == "assistant",
        )
        .order_by(desc(ChatMessage.created_at))
        .limit(1)
    )
    content: str | None = (await db.execute(stmt)).scalar_one_or_none()
    if not content:
        return ""
    return content[:80] + ("…" if len(content) > 80 else "")


async def get_session(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> ChatSession | None:
    """Return session only if it belongs to user and is not deleted."""
    stmt = select(ChatSession).where(
        ChatSession.id == session_id,
        ChatSession.user_id == user_id,
        ChatSession.status != "deleted",
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def get_session_with_messages(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> tuple[ChatSession | None, list[ChatMessageItem]]:
    """Return (session, messages) or (None, []) if not found / wrong user."""
    session = await get_session(db, session_id, user_id)
    if session is None:
        return None, []

    msg_stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    msg_rows = (await db.execute(msg_stmt)).scalars().all()

    messages = [
        ChatMessageItem(
            message_id=m.id,
            role=m.role,
            content=m.content,
            message_type=m.message_type,
            tool_events=m.tool_events or [],
            cards=m.cards or [],
            confirmation=m.confirmation,
            created_at=m.created_at,
            metadata=public_message_metadata(m.msg_metadata),
        )
        for m in msg_rows
    ]
    return session, messages


async def soft_delete_session(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    """Soft-delete a session. Returns True if found, False if not."""
    session = await get_session(db, session_id, user_id)
    if session is None:
        return False
    session.status = "deleted"
    session.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return True


# ── C32.4: Session search ─────────────────────────────────────────────────────

_DATE_RANGE_MAP = {
    "today":     0,
    "yesterday": 1,
    "7days":     7,
    "30days":    30,
    "month":     30,
}


async def search_sessions(
    db: AsyncSession,
    user_id: uuid.UUID,
    q: str | None = None,
    date_from: datetime | None = None,
    date_to:   datetime | None = None,
    date_ranges: list[str] | None = None,
    limit:  int = 20,
    offset: int = 0,
) -> tuple[list[ChatSessionSearchItem], int]:
    """
    Search user's chat sessions by keyword and/or time range.

    q            — keyword searched in session title + message content
    date_ranges  — list of preset strings: "today" | "yesterday" | "7days" | "30days" | "month"
    date_from/to — explicit ISO date range (overrides date_ranges)
    Returns (items, total).
    """
    from datetime import timedelta  # noqa: PLC0415

    # ── Resolve date window ────────────────────────────────────────────────
    if date_from is None and date_ranges:
        # Compute earliest start date from all selected ranges
        now = datetime.now(timezone.utc)
        earliest = now
        for dr in date_ranges:
            days = _DATE_RANGE_MAP.get(dr, 0)
            if dr == "today":
                start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            elif dr == "yesterday":
                start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                start = now - timedelta(days=days)
            if start < earliest:
                earliest = start
        date_from = earliest
    if date_to is None and date_from is not None:
        date_to = datetime.now(timezone.utc)

    # ── Base filter (always: correct user, not deleted) ────────────────────
    base_filters = [
        ChatSession.user_id == user_id,
        ChatSession.status != "deleted",
    ]
    if date_from is not None:
        base_filters.append(
            or_(
                ChatSession.last_message_at >= date_from,
                ChatSession.created_at >= date_from,
            )
        )
    if date_to is not None:
        base_filters.append(
            or_(
                ChatSession.last_message_at <= date_to,
                ChatSession.created_at <= date_to,
            )
        )

    # ── Keyword filter ────────────────────────────────────────────────────
    if q and q.strip():
        q_stripped = q.strip()
        title_match = ChatSession.title.ilike(f"%{q_stripped}%")
        # Subquery: sessions that have at least one message matching q
        msg_subq = (
            select(ChatMessage.session_id)
            .where(ChatMessage.content.ilike(f"%{q_stripped}%"))
            .scalar_subquery()
        )
        content_match = ChatSession.id.in_(msg_subq)
        base_filters.append(or_(title_match, content_match))

    # ── Count ─────────────────────────────────────────────────────────────
    count_stmt = (
        select(func.count())
        .select_from(ChatSession)
        .where(*base_filters)
    )
    total: int = (await db.execute(count_stmt)).scalar_one()

    if total == 0:
        return [], 0

    # ── List ──────────────────────────────────────────────────────────────
    list_stmt = (
        select(ChatSession)
        .where(*base_filters)
        .order_by(
            ChatSession.last_message_at.desc().nullslast(),
            desc(ChatSession.created_at),
        )
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(list_stmt)).scalars().all()

    items: list[ChatSessionSearchItem] = []
    for row in rows:
        preview = await _get_session_preview(db, row.id)
        snippet = await _get_match_snippet(db, row.id, q or "")
        items.append(ChatSessionSearchItem(
            session_id      = row.id,
            title           = row.title,
            status          = row.status,
            last_message_at = row.last_message_at,
            preview         = preview,
            matched_snippet = snippet,
        ))

    return items, total


async def _get_match_snippet(
    db: AsyncSession,
    session_id: uuid.UUID,
    q: str,
) -> str:
    """Return the first 80 chars of the first message matching q, or ''."""
    if not q or not q.strip():
        return ""
    stmt = (
        select(ChatMessage.content)
        .where(
            ChatMessage.session_id == session_id,
            ChatMessage.content.ilike(f"%{q.strip()}%"),
        )
        .order_by(ChatMessage.created_at.asc())
        .limit(1)
    )
    content: str | None = (await db.execute(stmt)).scalar_one_or_none()
    if not content:
        return ""
    # Find the keyword position and return surrounding context
    lower_content = content.lower()
    lower_q = q.lower().strip()
    idx = lower_content.find(lower_q)
    if idx < 0:
        return content[:80] + ("…" if len(content) > 80 else "")
    start = max(0, idx - 20)
    end   = min(len(content), idx + len(lower_q) + 60)
    snippet = ("…" if start > 0 else "") + content[start:end] + ("…" if end < len(content) else "")
    return snippet[:100]


# ── Transaction helpers ────────────────────────────────────────────────────────

async def safe_flush(db: AsyncSession, *, context: str) -> None:
    """
    C30.3.2: Flush pending ORM changes; on failure rollback and re-raise.

    Guarantees that after an exception the session is clean (no
    PendingRollback state) so callers can decide how to recover.
    """
    try:
        await db.flush()
    except Exception:
        await db.rollback()
        log.exception("DB flush failed in %s", context)
        raise


_COMPACT_METADATA_KEYS = {
    "trace_id",
    "request_id",
    "intent",
    "status",
    "error_code",
    "skill_name",
    "source",
    "runtime_mode",
    "answer_owner",
    "output_language",
    "disclaimer_version",
    "streamed",
    "verified_financial_data",
    "source_chunks_count",
    "common_metric_count",
    "fallback",
    "response_kind",
}
_DROP_METADATA_KEYS = {
    "source_chunks",
    "chunks",
    "diagnostics",
    "compliance_review",
    "review_audit",
    "agent_response",
    "plan",
    "planner_state",
    "shadow_diagnostics",
    "tool_responses",
    "prompt",
    "system_prompt",
}


def _compact_entities(value: object) -> list[dict]:
    entities = value if isinstance(value, list) else []
    compact = []
    for entity in entities[:5]:
        if not isinstance(entity, dict):
            continue
        compact.append({
            "market": entity.get("market"),
            "symbol": entity.get("symbol"),
            "name": entity.get("name") or entity.get("short_name"),
        })
    return compact


def public_message_metadata(metadata: dict | None) -> dict:
    """Sanitized metadata subset exposed to chat clients (P1.6.8)."""
    raw = metadata or {}
    public: dict = {}
    if raw.get("response_kind"):
        public["response_kind"] = raw.get("response_kind")
    if isinstance(raw.get("clarification"), dict):
        public["clarification"] = raw.get("clarification")
    return public


def compact_chat_message_metadata(metadata: dict | None) -> dict:
    """Keep chat_messages metadata small; large diagnostics belong in debug storage."""
    raw = dict(metadata or {})
    compact: dict = {
        "mock_mode": raw.get("mock_mode", False),
        "orchestrator": raw.get("orchestrator", "c8_memory_audit"),
    }
    for key in _COMPACT_METADATA_KEYS:
        if key in raw and raw.get(key) is not None:
            compact[key] = raw.get(key)

    # P1.6.8: persist the sanitized clarification contract so candidates can
    # be restored after refresh (existing JSONB metadata; no migration).
    clarification = raw.get("clarification")
    if not isinstance(clarification, dict):
        skill_data_probe = raw.get("skill_data") if isinstance(raw.get("skill_data"), dict) else {}
        clarification = skill_data_probe.get("clarification")
    if isinstance(clarification, dict):
        from app.services.entity_clarification import compact_clarification_for_metadata  # noqa: PLC0415

        compact_clar = compact_clarification_for_metadata(clarification)
        if compact_clar is not None:
            compact["response_kind"] = "clarification"
            compact["clarification"] = compact_clar

    skill_data = raw.get("skill_data") if isinstance(raw.get("skill_data"), dict) else {}
    if skill_data:
        compact["status"] = skill_data.get("status") or compact.get("status")
        if skill_data.get("error_code"):
            compact["error_code"] = skill_data.get("error_code")
        comparison_input = skill_data.get("comparison_input") or {}
        if isinstance(comparison_input, dict):
            compact["entities"] = _compact_entities(comparison_input.get("entities"))
        report_context = skill_data.get("report_context") or {}
        if isinstance(report_context, dict):
            compact["report_context"] = {
                "market": report_context.get("market"),
                "symbol": report_context.get("symbol"),
                "report_year": report_context.get("report_year"),
                "report_type": report_context.get("report_type"),
            }
        if isinstance(skill_data.get("comparison_summary"), dict):
            compact["comparison_summary"] = skill_data["comparison_summary"]
        if isinstance(skill_data.get("availability"), dict):
            compact["availability_summary"] = skill_data["availability"]

    tool_names = raw.get("tools_used") or []
    if tool_names:
        compact["tools_used"] = list(tool_names)[:12]

    for key in _DROP_METADATA_KEYS:
        compact.pop(key, None)

    encoded = json.dumps(compact, ensure_ascii=False, default=str)
    if len(encoded.encode("utf-8")) > 8 * 1024:
        compact = {
            key: compact.get(key)
            for key in (
                "trace_id",
                "intent",
                "status",
                "error_code",
                "skill_name",
                "runtime_mode",
                "output_language",
                "entities",
                "report_context",
                "comparison_summary",
                "source_chunks_count",
                "common_metric_count",
                "streamed",
            )
            if compact.get(key) is not None
        }
        compact["metadata_compacted"] = True
    return compact


# ── Message CRUD ───────────────────────────────────────────────────────────────

async def save_user_message(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    content: str,
    output_language: str,
) -> ChatMessage:
    msg = ChatMessage(
        session_id=session_id,
        user_id=user_id,
        role="user",
        content=content,
        message_type="text",
        tool_events=[],
        cards=[],
        confirmation=None,
        msg_metadata={"output_language": output_language},
    )
    db.add(msg)
    await safe_flush(db, context="save_user_message")  # C30.3.2: clean rollback on failure
    return msg


async def save_assistant_message(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    answer: str,
    tool_events: list,
    cards: list,
    confirmation: dict | None,
    output_language: str,
    extra_metadata: dict | None = None,
) -> ChatMessage:
    answer = str(answer or "")
    if not answer.strip() and confirmation is None:
        raise ValueError("assistant message content cannot be empty without confirmation")

    # Determine message_type
    if confirmation:
        msg_type = "confirmation"
    elif tool_events:
        msg_type = "tool_trace"
    else:
        msg_type = "text"

    base_meta: dict = {
        "mock_mode": False,
        "orchestrator": "c8_memory_audit",
        "output_language": output_language,
    }
    if extra_metadata:
        base_meta.update(extra_metadata)
    base_meta = compact_chat_message_metadata(base_meta)

    msg = ChatMessage(
        session_id=session_id,
        user_id=user_id,
        role="assistant",
        content=answer,
        message_type=msg_type,
        tool_events=tool_events,
        cards=cards,
        confirmation=confirmation,
        msg_metadata=base_meta,
    )
    db.add(msg)
    await safe_flush(db, context="save_assistant_message")  # C30.3.2: clean rollback on failure
    return msg


async def update_session_last_message(
    db: AsyncSession,
    session_id: uuid.UUID,
) -> None:
    stmt = select(ChatSession).where(ChatSession.id == session_id)
    session = (await db.execute(stmt)).scalar_one_or_none()
    if session:
        now = datetime.now(timezone.utc)
        session.last_message_at = now
        session.updated_at = now


_DEFAULT_TITLE = "新的研究对话"


async def maybe_update_session_title(
    db: AsyncSession,
    session_id: uuid.UUID,
    content: str,
) -> str | None:
    """
    C14: If the session title is still the default placeholder or blank,
    update it to the first 30 chars of the user's first message.

    Returns the new title string if updated, None if no change needed.
    Does NOT commit — caller is responsible for committing the transaction.
    """
    stmt = select(ChatSession).where(ChatSession.id == session_id)
    session = (await db.execute(stmt)).scalar_one_or_none()
    if session is None:
        return None
    current = (session.title or "").strip()
    if current and current != _DEFAULT_TITLE:
        return None  # already has a meaningful title
    # Derive title from first message content
    title = content.replace("\n", " ").replace("\r", " ").strip()[:30]
    if not title:
        return None
    session.title = title
    session.updated_at = datetime.now(timezone.utc)
    return title


async def find_pending_confirmation(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    confirmation_id: str,
) -> ChatMessage | None:
    """
    Find the assistant message in a session that has matching confirmation.id.
    Uses JSONB field access: confirmation->>'id' = confirmation_id.
    """
    stmt = select(ChatMessage).where(
        ChatMessage.session_id == session_id,
        ChatMessage.user_id == user_id,
        ChatMessage.role == "assistant",
        ChatMessage.confirmation["id"].astext == confirmation_id,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def update_confirmation_status(
    db: AsyncSession,
    message_id: uuid.UUID,
    new_status: str,
    extra: dict | None = None,
) -> None:
    """
    Update confirmation["status"] in a ChatMessage JSONB field.
    Also merges any extra fields (e.g. confirmed_at, executed_at, error).
    Uses flag_modified() so SQLAlchemy detects the mutation.
    """
    from sqlalchemy.orm.attributes import flag_modified

    stmt = select(ChatMessage).where(ChatMessage.id == message_id)
    msg = (await db.execute(stmt)).scalar_one_or_none()
    if msg is None or msg.confirmation is None:
        return

    # Copy to a new dict so SQLAlchemy detects the change
    conf = dict(msg.confirmation)
    conf["status"] = new_status
    if extra:
        conf.update(extra)
    msg.confirmation = conf
    flag_modified(msg, "confirmation")
