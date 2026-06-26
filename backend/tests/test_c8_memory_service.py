"""
Tests for Phase C8 chat_memory service.

Coverage:
  - _empty_memory returns correct structure with memory_version
  - update_symbols: add, dedup, evict at MAX_SYMBOLS
  - update_intents: add, cap at MAX_INTENTS
  - update_scopes: add, dedup, cap at MAX_SCOPES
  - update_last_report: stores report_id
  - update_pending_confirmation: stores and clears
  - update_task_state: overwrites task_state
  - update_output_language: stores language
  - add_safety_flag: dedup
  - clear_memory: resets to empty
  - get_memory: returns empty dict when session not found
  - fire-and-forget: exceptions do not propagate
"""
from __future__ import annotations

import uuid
from datetime import timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.agents.chat_memory as mem
from app.agents.chat_memory import (
    MEMORY_KEY,
    MAX_INTENTS,
    MAX_SCOPES,
    MAX_SYMBOLS,
    _empty_memory,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_session(metadata: dict | None = None) -> MagicMock:
    s = MagicMock()
    s.session_metadata = metadata or {}
    return s


def _make_db(session: MagicMock | None = None) -> AsyncMock:
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = session
    db.execute.return_value = result
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


SESSION_ID = uuid.uuid4()
USER_ID    = uuid.uuid4()


# ── _empty_memory ──────────────────────────────────────────────────────────────

def test_empty_memory_structure():
    m = _empty_memory()
    assert m["memory_version"] == "c8_v1"
    assert m["recent_symbols"] == []
    assert m["recent_intents"] == []
    assert m["recent_scopes"] == []
    assert m["last_report_id"] is None
    assert m["last_output_language"] == "zh-CN"
    assert m["task_state"] == {}
    assert m["pending_confirmation_id"] is None
    assert m["memory_safety_flags"] == []


# ── update_symbols ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_symbols_adds_entry():
    session = _make_session()
    db = _make_db(session)
    await mem.update_symbols(db, SESSION_ID, USER_ID, {"market": "CN", "symbol": "688146", "name": "中船特气"})
    meta = session.session_metadata
    symbols = meta[MEMORY_KEY]["recent_symbols"]
    assert len(symbols) == 1
    assert symbols[0]["symbol"] == "688146"
    assert symbols[0]["market"] == "CN"
    assert symbols[0]["name"] == "中船特气"
    assert "last_seen_at" in symbols[0]


@pytest.mark.asyncio
async def test_update_symbols_dedup():
    session = _make_session()
    db = _make_db(session)
    info = {"market": "CN", "symbol": "688146", "name": "中船特气"}
    await mem.update_symbols(db, SESSION_ID, USER_ID, info)
    await mem.update_symbols(db, SESSION_ID, USER_ID, info)
    symbols = session.session_metadata[MEMORY_KEY]["recent_symbols"]
    assert len(symbols) == 1


@pytest.mark.asyncio
async def test_update_symbols_evict_at_max():
    session = _make_session()
    db = _make_db(session)
    for i in range(MAX_SYMBOLS + 3):
        await mem.update_symbols(db, SESSION_ID, USER_ID, {"market": "CN", "symbol": f"{i:06d}"})
    symbols = session.session_metadata[MEMORY_KEY]["recent_symbols"]
    assert len(symbols) == MAX_SYMBOLS


@pytest.mark.asyncio
async def test_update_symbols_noop_when_empty_symbol():
    session = _make_session()
    db = _make_db(session)
    await mem.update_symbols(db, SESSION_ID, USER_ID, {"market": "CN", "symbol": ""})
    # db.execute should never be called
    db.execute.assert_not_called()


# ── update_intents ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_intents_appends():
    session = _make_session()
    db = _make_db(session)
    await mem.update_intents(db, SESSION_ID, USER_ID, "stock_anomaly")
    intents = session.session_metadata[MEMORY_KEY]["recent_intents"]
    assert intents[0]["intent"] == "stock_anomaly"
    assert "created_at" in intents[0]


@pytest.mark.asyncio
async def test_update_intents_capped_at_max():
    session = _make_session()
    db = _make_db(session)
    for i in range(MAX_INTENTS + 5):
        await mem.update_intents(db, SESSION_ID, USER_ID, f"intent_{i}")
    intents = session.session_metadata[MEMORY_KEY]["recent_intents"]
    assert len(intents) == MAX_INTENTS


# ── update_scopes ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_scopes_dedup():
    session = _make_session()
    db = _make_db(session)
    await mem.update_scopes(db, SESSION_ID, USER_ID, "comprehensive")
    await mem.update_scopes(db, SESSION_ID, USER_ID, "comprehensive")
    scopes = session.session_metadata[MEMORY_KEY]["recent_scopes"]
    assert scopes.count("comprehensive") == 1


@pytest.mark.asyncio
async def test_update_scopes_capped_at_max():
    session = _make_session()
    db = _make_db(session)
    for i in range(MAX_SCOPES + 2):
        await mem.update_scopes(db, SESSION_ID, USER_ID, f"scope_{i}")
    scopes = session.session_metadata[MEMORY_KEY]["recent_scopes"]
    assert len(scopes) == MAX_SCOPES


# ── update_last_report ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_last_report():
    session = _make_session()
    db = _make_db(session)
    await mem.update_last_report(db, SESSION_ID, USER_ID, "report-abc-123")
    assert session.session_metadata[MEMORY_KEY]["last_report_id"] == "report-abc-123"


# ── update_pending_confirmation ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_pending_confirmation_set_and_clear():
    session = _make_session()
    db = _make_db(session)
    await mem.update_pending_confirmation(db, SESSION_ID, USER_ID, "conf-xyz")
    assert session.session_metadata[MEMORY_KEY]["pending_confirmation_id"] == "conf-xyz"
    await mem.update_pending_confirmation(db, SESSION_ID, USER_ID, None)
    assert session.session_metadata[MEMORY_KEY]["pending_confirmation_id"] is None


# ── update_task_state ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_task_state():
    session = _make_session()
    db = _make_db(session)
    state = {"plan_intent_type": "anomaly_then_risk", "skills_used": ["anomaly"]}
    await mem.update_task_state(db, SESSION_ID, USER_ID, state)
    assert session.session_metadata[MEMORY_KEY]["task_state"] == state


# ── update_output_language ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_output_language():
    session = _make_session()
    db = _make_db(session)
    await mem.update_output_language(db, SESSION_ID, USER_ID, "en-US")
    assert session.session_metadata[MEMORY_KEY]["last_output_language"] == "en-US"


# ── add_safety_flag ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_safety_flag_dedup():
    session = _make_session()
    db = _make_db(session)
    await mem.add_safety_flag(db, SESSION_ID, USER_ID, "injection_detected")
    await mem.add_safety_flag(db, SESSION_ID, USER_ID, "injection_detected")
    flags = session.session_metadata[MEMORY_KEY]["memory_safety_flags"]
    assert flags.count("injection_detected") == 1


# ── clear_memory ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_clear_memory_resets():
    session = _make_session()
    db = _make_db(session)
    # seed some data
    await mem.update_symbols(db, SESSION_ID, USER_ID, {"market": "CN", "symbol": "688146"})
    # clear
    result = await mem.clear_memory(db, SESSION_ID, USER_ID)
    assert result is True
    assert session.session_metadata[MEMORY_KEY]["recent_symbols"] == []


@pytest.mark.asyncio
async def test_clear_memory_returns_false_when_session_missing():
    db = _make_db(session=None)
    result = await mem.clear_memory(db, SESSION_ID, USER_ID)
    assert result is False


# ── get_memory ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_memory_returns_empty_when_no_session():
    db = _make_db(session=None)
    memory = await mem.get_memory(db, SESSION_ID, USER_ID)
    assert memory["memory_version"] == "c8_v1"
    assert memory["recent_symbols"] == []


# ── fire-and-forget safety ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_symbols_does_not_raise_on_db_error():
    db = AsyncMock()
    db.execute.side_effect = RuntimeError("DB down")
    # must not raise
    await mem.update_symbols(db, SESSION_ID, USER_ID, {"market": "CN", "symbol": "688146"})


@pytest.mark.asyncio
async def test_update_intents_does_not_raise_on_db_error():
    db = AsyncMock()
    db.execute.side_effect = RuntimeError("DB down")
    await mem.update_intents(db, SESSION_ID, USER_ID, "stock_anomaly")
