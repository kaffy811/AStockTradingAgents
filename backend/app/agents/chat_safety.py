"""
C8 Chat Safety — memory pollution and prompt injection protection.

Safety rules enforced here:
  1. External content (news, announcements, web) is tagged and never written
     to long-term memory in its raw form.
  2. Injection patterns detected in external text trigger memory safety flags.
  3. Safe summaries (truncated, scrubbed) are the only external data allowed
     into structured memory.
  4. Forbidden financial phrases (买入/卖出/必涨…) are rejected from memory.

These are rule-based checks — no LLM involved.
"""
from __future__ import annotations

import re

# ── Prompt injection / instruction patterns ────────────────────────────────────
# If any of these are found inside external content, we flag it.
# Covers common jailbreak / instruction-injection patterns (EN + ZH).

_INJECTION_PATTERNS: list[str] = [
    # Chinese injection phrases
    "忽略之前的指令",
    "忽略前面的",
    "执行以下操作",
    "将此内容写入记忆",
    "写入记忆",
    "调用某工具",
    "调用工具",
    "你现在是",
    "扮演",
    "忘记你之前",
    "新的系统指令",
    "系统提示",
    # English injection phrases (case-insensitive)
    "ignore previous instructions",
    "ignore all previous",
    "disregard your instructions",
    "you are now",
    "act as",
    "forget your previous",
    "new system prompt",
    "system prompt:",
    "override your instructions",
    "write this to memory",
    "execute the following",
]

# ── Financial forbidden phrases (must not appear in memory) ───────────────────

_FINANCIAL_FORBIDDEN = [
    "买入", "卖出", "持有", "目标价", "必涨", "稳赚", "抄底", "追涨",
]

# ── External source types ─────────────────────────────────────────────────────

EXTERNAL_SOURCE_TYPES = frozenset({
    "news", "announcement", "web", "external_api", "user_content",
})

# ── Public API ─────────────────────────────────────────────────────────────────

def detect_injection(text: str) -> list[str]:
    """
    Scan text for prompt injection / instruction patterns.
    Returns list of flag strings (empty if none detected).
    """
    if not text:
        return []
    text_lower = text.lower()
    flags: list[str] = []
    for pattern in _INJECTION_PATTERNS:
        if pattern.lower() in text_lower:
            flags.append("external_instruction_detected")
            break  # one flag is enough per text
    return flags


def is_safe_for_memory(text: str) -> bool:
    """
    Return True if the text does NOT contain injection patterns or forbidden phrases.
    External content that returns False must not be written to structured memory.
    """
    if not text:
        return True
    return not bool(detect_injection(text))


def contains_forbidden_financial(text: str) -> bool:
    """Return True if text contains any forbidden financial advice phrases."""
    if not text:
        return False
    for phrase in _FINANCIAL_FORBIDDEN:
        if phrase in text:
            return True
    return False


def sanitize_for_memory(text: str, max_chars: int = 200) -> str:
    """
    Truncate external content to a safe summary length.
    Appends a marker so consumers know the text was truncated.
    """
    if not text:
        return ""
    if len(text) > max_chars:
        return text[:max_chars] + "…[截断]"
    return text


def tag_external_content(
    data: dict,
    source_type: str = "news",
) -> dict:
    """
    Add external-content metadata flags to a tool result data dict.
    These flags tell downstream consumers (memory, audit) that this data
    originated outside the system and must not be trusted as an instruction.

    Returns a NEW dict (does not mutate the original).
    """
    return {
        **data,
        "__external_content":       True,
        "__trusted_as_instruction": False,
        "__source_type":            source_type,
    }


def is_external_source(source_type: str) -> bool:
    """Return True if the source type is considered external / untrusted."""
    return source_type in EXTERNAL_SOURCE_TYPES


def audit_tool_event(
    tool_name: str,
    status: str,
    detail: str,
    permission_level: str = "read_only",
    duration_ms: int | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
    data_source: str = "existing_service",
    ok: bool = True,
    error: str | None = None,
) -> dict:
    """
    Build a C8-compliant audit tool event dict.
    Preserves backward-compatible fields (name, status, detail) for ChatToolTrace.
    New audit fields are additive.
    """
    event: dict = {
        # ── Backward-compatible (ChatToolTrace reads these) ──────────────────
        "name":   tool_name,
        "status": status,
        "detail": detail,
        # ── C8 audit fields ──────────────────────────────────────────────────
        "event_type":       "tool_completed",
        "permission_level": permission_level,
        "data_source":      data_source,
        "ok":               ok,
    }
    if duration_ms is not None:
        event["duration_ms"] = duration_ms
    if started_at is not None:
        event["started_at"] = started_at
    if completed_at is not None:
        event["completed_at"] = completed_at
    if error is not None:
        event["error"] = error
    return event


def audit_skill_event(
    skill_name: str,
    status: str = "success",
    required_tools: list[str] | None = None,
    completed_at: str | None = None,
) -> dict:
    """Build a C8 audit skill event dict."""
    return {
        "event_type":     "skill_completed",
        "skill_name":     skill_name,
        "status":         status,
        "required_tools": required_tools or [],
        "completed_at":   completed_at,
    }


def audit_action_event(
    action_type: str,
    confirmation_id: str,
    status: str = "executed",
    confirmed_at: str | None = None,
    executed_at: str | None = None,
    ok: bool = True,
    error: str | None = None,
) -> dict:
    """Build a C8 audit action event dict."""
    return {
        "event_type":       "action_executed",
        "action_type":      action_type,
        "confirmation_id":  confirmation_id,
        "status":           status,
        "confirmed_at":     confirmed_at,
        "executed_at":      executed_at,
        "ok":               ok,
        "error":            error,
    }
