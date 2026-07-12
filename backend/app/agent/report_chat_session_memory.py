"""
app/agent/report_chat_session_memory.py — 问财报会话记忆（Phase 6K）

Storage: Redis LIST, key = cm:{session_id}:{ts_code}
TTL: REPORT_CHAT_MEMORY_TTL_SECONDS (default 3600s / 1 hour)
Max turns: REPORT_CHAT_MEMORY_MAX_TURNS (default 5)

Rules:
- Memory is strictly isolated by ts_code — questions about stock A never leak into stock B.
- Each turn stored as JSON: {"q": question, "a": answer_snippet, "ts": unix_timestamp}
- Answer snippet is truncated to 300 chars to keep Redis memory bounded.
- On retrieval, turns are ordered oldest→newest (natural list order).
- Redis unavailable → silently skip memory, continue without context.
- enable_report_chat_memory=False → all ops are no-ops.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

log = logging.getLogger(__name__)

_ANSWER_SNIPPET_LEN = 300
_KEY_PREFIX = "cm"  # chat-memory


def _mem_key(session_id: str, ts_code: str) -> str:
    """Deterministic Redis key for this session+stock pair."""
    # Normalise ts_code to uppercase
    return f"{_KEY_PREFIX}:{session_id[:64]}:{ts_code.upper()}"


async def _get_redis() -> Any | None:
    try:
        from app.core.database import get_redis
        return get_redis()
    except Exception:
        return None


def _make_turn(question: str, answer: str) -> str:
    """Serialize a (question, answer) turn to a JSON string."""
    snippet = answer[:_ANSWER_SNIPPET_LEN] if answer else ""
    turn = {
        "q":  question[:500],
        "a":  snippet,
        "ts": int(time.time()),
    }
    return json.dumps(turn, ensure_ascii=False)


def _parse_turn(raw: str | bytes) -> dict | None:
    try:
        return json.loads(raw)
    except Exception:
        return None


# ── Public API ────────────────────────────────────────────────────────────────

async def load_memory(
    session_id: str,
    ts_code: str,
) -> list[dict]:
    """
    Return conversation history for (session_id, ts_code), oldest turn first.

    Each item: {"q": str, "a": str, "ts": int}
    Returns [] if Redis unavailable, memory disabled, or no history.
    """
    from app.core.config import settings
    if not settings.enable_report_chat_memory or not session_id:
        return []

    redis = await _get_redis()
    if redis is None:
        return []

    key = _mem_key(session_id, ts_code)
    try:
        raws = await redis.lrange(key, 0, -1)
        turns = [_parse_turn(r) for r in raws]
        return [t for t in turns if t is not None]
    except Exception as e:
        log.debug("report_chat_session_memory load error: %s", e)
        return []


async def append_turn(
    session_id: str,
    ts_code: str,
    question: str,
    answer: str,
) -> bool:
    """
    Append a new turn to the conversation history for (session_id, ts_code).

    Trims the list to REPORT_CHAT_MEMORY_MAX_TURNS after append.
    Refreshes the Redis TTL.
    Returns True if written, False otherwise. Never raises.
    """
    from app.core.config import settings
    if not settings.enable_report_chat_memory or not session_id:
        return False

    redis = await _get_redis()
    if redis is None:
        return False

    key = _mem_key(session_id, ts_code)
    max_turns = settings.report_chat_memory_max_turns
    ttl = settings.report_chat_memory_ttl_seconds

    try:
        turn_json = _make_turn(question, answer)
        pipe = redis.pipeline()
        pipe.rpush(key, turn_json)
        # Keep only the last max_turns turns (trim from left if list is longer)
        pipe.ltrim(key, -max_turns, -1)
        pipe.expire(key, ttl)
        await pipe.execute()
        return True
    except Exception as e:
        log.debug("report_chat_session_memory append error: %s", e)
        return False


def build_memory_context_prompt(turns: list[dict]) -> str:
    """
    Build a brief multi-turn history block for injection into the LLM system prompt.

    Example output:
    ---
    [以下是本次会话的历史追问（同一股票）]
    用户: 公司的主营业务是什么？
    助手: 根据年报，公司主营业务为……
    用户: 那利润率怎么样？
    助手: 毛利率约为……
    ---
    Returns empty string if turns is empty.
    """
    if not turns:
        return ""
    lines = ["[以下是本次会话的历史追问（同一股票）]"]
    for t in turns:
        q = t.get("q", "")
        a = t.get("a", "")
        if q:
            lines.append(f"用户: {q}")
        if a:
            lines.append(f"助手: {a}")
    return "\n".join(lines)


def memory_meta_dict(
    session_id: str | None,
    turns_loaded: int,
    used: bool,
) -> dict:
    """Return a serializable memory_meta dict for API responses."""
    return {
        "session_id":    session_id,
        "turns_loaded":  turns_loaded,
        "context_used":  used,
    }
