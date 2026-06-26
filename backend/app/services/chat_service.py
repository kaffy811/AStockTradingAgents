"""
Chat Service — CRUD for chat_sessions and chat_messages (Phase C3).

All user-scoped: every query includes user_id so sessions cannot
cross between users.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import (
    ChatMessage,
    ChatMessageItem,
    ChatSession,
    ChatSessionCreateResponse,
    ChatSessionListItem,
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
    await db.flush()  # get id without committing
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
    await db.flush()
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
