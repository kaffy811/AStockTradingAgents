"""
C8 SessionMemory — structured memory manager for Chat Copilot.

Reads and writes to chat_sessions.session_metadata JSONB.
No new DB tables. No new migrations.

Memory structure (stored under session_metadata["memory_v1"]):
{
  "memory_version": "c8_v1",
  "recent_symbols": [
    {"market": "CN", "symbol": "688146", "name": "中船特气", "last_seen_at": "..."}
  ],                                  # max MAX_SYMBOLS entries (FIFO, dedup by symbol)
  "recent_intents": [
    {"intent": "stock_anomaly", "created_at": "..."}
  ],                                  # max MAX_INTENTS entries (FIFO)
  "recent_scopes": ["comprehensive"], # max MAX_SCOPES entries (FIFO, dedup)
  "last_report_id": null,
  "last_output_language": "zh-CN",
  "task_state": {},                   # last Planner / Skill execution state
  "pending_confirmation_id": null,
  "memory_safety_flags": []           # detected injection / pollution flags
}

Safety rules:
  - All writes are fire-and-forget; failures are logged but never propagate.
  - External content (news/announcements) is never written to memory.
  - Memory writes are only triggered by explicit, rule-based conditions.
  - user_id / session_id must be verified before any write.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.chat import ChatSession

log = logging.getLogger(__name__)

MEMORY_KEY  = "memory_v1"
MAX_SYMBOLS = 10
MAX_INTENTS = 20
MAX_SCOPES  = 5


# ── Empty memory template ──────────────────────────────────────────────────────

def _empty_memory() -> dict:
    return {
        "memory_version":        "c8_v1",
        "recent_symbols":        [],
        "recent_intents":        [],
        "recent_scopes":         [],
        "last_report_id":        None,
        "last_output_language":  "zh-CN",
        "task_state":            {},
        "pending_confirmation_id": None,
        "memory_safety_flags":   [],
    }


# ── Internal helpers ───────────────────────────────────────────────────────────

async def _load(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> "tuple[ChatSession | None, dict]":
    """Load session row and extract memory dict."""
    stmt = select(ChatSession).where(
        ChatSession.id == session_id,
        ChatSession.user_id == user_id,
        ChatSession.status != "deleted",
    )
    session = (await db.execute(stmt)).scalar_one_or_none()
    if session is None:
        return None, _empty_memory()

    meta = session.session_metadata or {}
    memory = meta.get(MEMORY_KEY)
    if not isinstance(memory, dict):
        memory = _empty_memory()
    return session, memory


async def _save(
    db: AsyncSession,
    session: ChatSession,
    memory: dict,
) -> None:
    """Write memory back into session_metadata and mark modified."""
    meta = dict(session.session_metadata or {})
    meta[MEMORY_KEY] = memory
    session.session_metadata = meta
    flag_modified(session, "session_metadata")
    await db.flush()


# ── Public read ────────────────────────────────────────────────────────────────

async def get_memory(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> dict:
    """Return the structured memory dict for the session (never raises)."""
    try:
        _, memory = await _load(db, session_id, user_id)
        return memory
    except Exception:
        log.warning("chat_memory.get_memory: failed for session %s", session_id)
        return _empty_memory()


# ── recent_symbols ─────────────────────────────────────────────────────────────

async def update_symbols(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    symbol_info: dict,
) -> None:
    """
    Add or refresh a stock symbol in recent_symbols.
    Dedup by (market, symbol); evict oldest when > MAX_SYMBOLS.
    symbol_info: {"market": "CN", "symbol": "688146", "name": "中船特气"}
    """
    market = symbol_info.get("market", "")
    symbol = symbol_info.get("symbol", "")
    if not symbol:
        return
    try:
        session, memory = await _load(db, session_id, user_id)
        if session is None:
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        entry = {
            "market":       market,
            "symbol":       symbol,
            "name":         symbol_info.get("name", symbol),
            "last_seen_at": now_iso,
        }

        # Remove existing entry for same symbol (dedup)
        symbols: list = [
            s for s in memory.get("recent_symbols", [])
            if not (s.get("market") == market and s.get("symbol") == symbol)
        ]
        # Prepend newest
        symbols.insert(0, entry)
        # Enforce cap
        memory["recent_symbols"] = symbols[:MAX_SYMBOLS]

        await _save(db, session, memory)
    except Exception:
        log.warning("chat_memory.update_symbols: failed for session %s", session_id)


# ── recent_intents ─────────────────────────────────────────────────────────────

async def update_intents(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    intent: str,
) -> None:
    """Append intent to recent_intents (max MAX_INTENTS, FIFO)."""
    if not intent:
        return
    try:
        session, memory = await _load(db, session_id, user_id)
        if session is None:
            return

        entry = {"intent": intent, "created_at": datetime.now(timezone.utc).isoformat()}
        intents: list = memory.get("recent_intents", [])
        intents.insert(0, entry)
        memory["recent_intents"] = intents[:MAX_INTENTS]

        await _save(db, session, memory)
    except Exception:
        log.warning("chat_memory.update_intents: failed for session %s", session_id)


# ── recent_scopes ──────────────────────────────────────────────────────────────

async def update_scopes(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    scope: str,
) -> None:
    """Add scope to recent_scopes (max MAX_SCOPES, dedup)."""
    if not scope:
        return
    try:
        session, memory = await _load(db, session_id, user_id)
        if session is None:
            return

        scopes: list = [s for s in memory.get("recent_scopes", []) if s != scope]
        scopes.insert(0, scope)
        memory["recent_scopes"] = scopes[:MAX_SCOPES]

        await _save(db, session, memory)
    except Exception:
        log.warning("chat_memory.update_scopes: failed for session %s", session_id)


# ── last_report_id ─────────────────────────────────────────────────────────────

async def update_last_report(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    report_id: str,
) -> None:
    """Update last_report_id in memory."""
    if not report_id:
        return
    try:
        session, memory = await _load(db, session_id, user_id)
        if session is None:
            return
        memory["last_report_id"] = report_id
        await _save(db, session, memory)
    except Exception:
        log.warning("chat_memory.update_last_report: failed for session %s", session_id)


# ── pending_confirmation_id ────────────────────────────────────────────────────

async def update_pending_confirmation(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    confirmation_id: str | None,
) -> None:
    """Record or clear the current pending confirmation ID."""
    try:
        session, memory = await _load(db, session_id, user_id)
        if session is None:
            return
        memory["pending_confirmation_id"] = confirmation_id
        await _save(db, session, memory)
    except Exception:
        log.warning("chat_memory.update_pending_confirmation: failed for session %s", session_id)


# ── task_state ─────────────────────────────────────────────────────────────────

async def update_task_state(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    task_state: dict,
) -> None:
    """Overwrite task_state in memory with the latest execution snapshot."""
    try:
        session, memory = await _load(db, session_id, user_id)
        if session is None:
            return
        memory["task_state"] = task_state
        await _save(db, session, memory)
    except Exception:
        log.warning("chat_memory.update_task_state: failed for session %s", session_id)


# ── output_language ────────────────────────────────────────────────────────────

async def update_output_language(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    language: str,
) -> None:
    """Remember the last output_language used in this session."""
    if not language:
        return
    try:
        session, memory = await _load(db, session_id, user_id)
        if session is None:
            return
        memory["last_output_language"] = language
        await _save(db, session, memory)
    except Exception:
        log.warning("chat_memory.update_output_language: failed for session %s", session_id)


# ── safety flags ───────────────────────────────────────────────────────────────

async def add_safety_flag(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    flag: str,
) -> None:
    """Append a safety flag (dedup) to memory_safety_flags."""
    if not flag:
        return
    try:
        session, memory = await _load(db, session_id, user_id)
        if session is None:
            return
        flags: list = memory.get("memory_safety_flags", [])
        if flag not in flags:
            flags.append(flag)
        memory["memory_safety_flags"] = flags
        await _save(db, session, memory)
    except Exception:
        log.warning("chat_memory.add_safety_flag: failed for session %s", session_id)


# ── clear ──────────────────────────────────────────────────────────────────────

async def clear_memory(
    db: AsyncSession,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    """
    Reset memory to empty structure.
    Returns True if session found and cleared, False otherwise.
    Does NOT delete messages.
    """
    try:
        session, _ = await _load(db, session_id, user_id)
        if session is None:
            return False
        await _save(db, session, _empty_memory())
        await db.commit()
        return True
    except Exception:
        log.exception("chat_memory.clear_memory: failed for session %s", session_id)
        return False
