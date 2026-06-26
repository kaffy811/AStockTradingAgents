"""
ToolResult — standard return type for all Chat Tools (Phase C4).

Every tool returns exactly one ToolResult.  Callers inspect `ok` first;
on failure the orchestrator falls back gracefully without surfacing raw errors.

C8 additions: duration_ms, started_at, permission_level, data_source for audit trail.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ToolResult:
    ok: bool
    tool_name: str
    summary: str                        # Human-readable one-liner shown in tool trace
    data: dict | None = None            # Structured payload for orchestrator logic
    cards: list = field(default_factory=list)   # UI cards to render
    error: str | None = None            # Debug message (never sent to frontend)
    text: str = ""                      # Optional long-form text for LLM context injection
    source: str = "existing_service"    # e.g. "eastmoney", "db", "akshare"
    # ── C8 Audit fields ───────────────────────────────────────────────────────
    duration_ms: int | None = None      # Wall-clock execution time in ms
    started_at: str | None = None       # ISO timestamp when call started
    permission_level: str = "read_only" # "read_only" | "write_user_data" | "long_running"
