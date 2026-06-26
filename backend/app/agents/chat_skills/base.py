"""
Base classes for Chat Skills — Phase C6.

SkillContext  — data passed into every skill.run()
SkillResult   — standard return type from skill.run()
BaseSkill     — ABC all skills must implement
"""
from __future__ import annotations

import abc
import re
from dataclasses import dataclass, field
from typing import Any

_DISCLAIMER = "\n\n_仅供研究参考，不构成投资建议。_"


@dataclass
class SkillContext:
    db: Any
    user_id: str
    session_id: str = ""
    output_language: str = "zh-CN"
    tool_registry: Any = None        # ToolRegistry instance
    recent_symbols: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    # C13-a: optional async callback for streaming fine-grained events
    # Signature: async (event_type: str, payload: dict) -> None
    # Never raises — failures are silently ignored by the streaming layer.
    event_callback: Any = None


@dataclass
class SkillResult:
    ok: bool
    skill_name: str
    answer: str
    tool_events: list = field(default_factory=list)
    cards: list = field(default_factory=list)
    data: dict | None = None
    error: str | None = None
    safety_flags: list = field(default_factory=list)
    source: str = "skill_registry"
    # C9: spec metadata injected by SkillRegistry after run()
    metadata: dict = field(default_factory=dict)


class BaseSkill(abc.ABC):
    name: str = ""
    description: str = ""
    intent_examples: list[str] = []
    required_tools: list[str] = []
    optional_tools: list[str] = []
    safety_level: str = "read_only"
    priority: int = 50

    @abc.abstractmethod
    def can_handle(self, message: str, context: SkillContext) -> bool:
        ...

    @abc.abstractmethod
    async def run(self, message: str, context: SkillContext) -> SkillResult:
        ...

    # ── helpers ──────────────────────────────────────────────────────────────

    def _tool_event(self, name: str, detail: str, status: str = "success") -> dict:
        return {"name": name, "status": status, "detail": detail}

    def _card(self, card_type: str, data: dict) -> dict:
        return {"type": card_type, "data": data}

    def _result_event(self, tool_result: Any) -> dict:
        status = "success" if tool_result.ok else "error"
        return self._tool_event(tool_result.tool_name, tool_result.summary, status)

    def _ensure_disclaimer(self, text: str) -> str:
        if _DISCLAIMER.strip() not in text:
            return text + _DISCLAIMER
        return text


# ── Module-level stock extraction helper ──────────────────────────────────────

def _extract_stock_hint(msg: str) -> dict:
    """Best-effort extraction of {market, symbol, name, query} from user message."""
    if re.search(r"688146|中船特气", msg):
        return {"market": "CN", "symbol": "688146", "name": "中船特气", "query": "688146"}
    if re.search(r"600519|茅台", msg):
        return {"market": "CN", "symbol": "600519", "name": "贵州茅台", "query": "600519"}
    if re.search(r"300750|宁德时代", msg):
        return {"market": "CN", "symbol": "300750", "name": "宁德时代", "query": "300750"}
    if re.search(r"601899|紫金矿业", msg):
        return {"market": "CN", "symbol": "601899", "name": "紫金矿业", "query": "601899"}
    # Generic CN code: 6-digit
    m = re.search(r"\b(\d{6})\b", msg)
    if m:
        return {"market": "CN", "symbol": m.group(1), "name": m.group(1), "query": m.group(1)}
    # HK code: 5-digit or 4-digit
    m = re.search(r"\b0?(\d{4,5})\b", msg)
    if m:
        return {"market": "HK", "symbol": m.group(1).zfill(5), "name": m.group(1), "query": m.group(1)}
    return {}
