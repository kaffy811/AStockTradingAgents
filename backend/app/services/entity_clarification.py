"""Generic entity-selection clarification contract for Legacy chat responses.

Built from normal resolver candidates only — never from Pi shadow diagnostics,
never hardcoded to specific companies, and never carrying internal confidence,
prompts or chain-of-thought.  The deterministic text fallback keeps the answer
fully usable even for clients that cannot render candidate components.
"""
from __future__ import annotations

from typing import Any

CLARIFICATION_KIND_ENTITY_SELECTION = "entity_selection"

_MAX_CANDIDATES = 5


def build_entity_clarification(
    *,
    query_term: str,
    candidates: list[dict[str, Any]],
    language: str = "zh-CN",
) -> dict[str, Any] | None:
    """Build the structured clarification contract.

    Candidates are deduplicated by (market, symbol) and kept in the caller's
    deterministic order.  Returns None when fewer than one candidate remains —
    callers keep their generic clarification copy in that case.
    """
    seen: set[tuple[str, str]] = set()
    compact: list[dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        display_name = str(item.get("display_name") or item.get("short_name") or item.get("name") or "").strip()
        symbol = str(item.get("symbol") or item.get("code") or "").strip()
        market = str(item.get("market") or "CN").strip().upper()
        if not display_name:
            continue
        key = (market, symbol or display_name)
        if key in seen:
            continue
        seen.add(key)
        compact.append({
            "display_name": display_name,
            "symbol": symbol or None,
            "market": market,
            "reason": str(item.get("reason") or _default_reason(display_name, query_term)),
        })
        if len(compact) >= _MAX_CANDIDATES:
            break
    if not compact:
        return None
    return {
        "kind": CLARIFICATION_KIND_ENTITY_SELECTION,
        "prompt": _prompt(language),
        "query_term": str(query_term or ""),
        "candidates": compact,
        "selection_required": True,
    }


def clarification_answer_text(clarification: dict[str, Any], *, language: str = "zh-CN") -> str:
    """Deterministic user-facing text generated from the structured contract."""
    term = clarification.get("query_term") or ""
    lines = [f"“{term}”可能指多家公司。请确认你想查询哪一家：" if term else "请确认你想查询哪家公司："]
    for index, item in enumerate(clarification.get("candidates") or [], start=1):
        symbol = item.get("symbol")
        suffix = f"（{symbol}）" if symbol else ""
        lines.append(f"{index}. {item.get('display_name')}{suffix}")
    lines.append("")
    lines.append("你可以直接回复公司名称或股票代码。")
    return "\n".join(lines)


def compact_clarification_for_metadata(clarification: dict[str, Any] | None) -> dict[str, Any] | None:
    """Sanitized subset for message metadata / API payloads."""
    if not isinstance(clarification, dict):
        return None
    candidates = [
        {
            "display_name": item.get("display_name"),
            "symbol": item.get("symbol"),
            "market": item.get("market"),
            "reason": item.get("reason"),
        }
        for item in (clarification.get("candidates") or [])
        if isinstance(item, dict) and item.get("display_name")
    ]
    if not candidates:
        return None
    return {
        "kind": clarification.get("kind") or CLARIFICATION_KIND_ENTITY_SELECTION,
        "prompt": clarification.get("prompt"),
        "query_term": clarification.get("query_term"),
        "candidates": candidates,
        "selection_required": bool(clarification.get("selection_required", True)),
    }


def _prompt(language: str) -> str:
    return "请确认你指的是哪家公司：" if language.startswith("zh") else "Please confirm which company you mean:"


def _default_reason(display_name: str, query_term: str) -> str:
    if query_term and display_name.startswith(query_term):
        return f"名称以“{query_term}”开头"
    if query_term:
        return f"名称包含“{query_term}”"
    return "名称相关"
