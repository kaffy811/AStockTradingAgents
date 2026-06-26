"""
ToolRegistry — central lookup for all Chat Tools (Phase C4).

Usage:
    registry = ToolRegistry()
    result = await registry.call("get_quote_tool", db=db, market="CN", symbol="688146")

C8: call() now records duration_ms and started_at for audit trail.
C13-b: call() accepts optional event_callback; emits tool_started / tool_completed.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.chat_tools.base import BaseTool
from app.agents.chat_tools.tool_result import ToolResult
from app.agents.chat_events import safe_emit

log = logging.getLogger(__name__)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    async def call(
        self,
        tool_name: str,
        db: AsyncSession,
        event_callback: Any = None,
        **kwargs: Any,
    ) -> ToolResult:
        tool = self._tools.get(tool_name)
        if tool is None:
            await safe_emit(event_callback, "tool_completed", {
                "tool_name": tool_name,
                "status": "failed",
                "ok": False,
                "duration_ms": 0,
                "error": f"Tool '{tool_name}' not registered",
                "permission_level": "read_only",
                "source": "tool_registry",
            })
            return ToolResult(
                ok=False,
                tool_name=tool_name,
                summary=f"未知工具：{tool_name}",
                error=f"Tool '{tool_name}' not registered",
            )

        await safe_emit(event_callback, "tool_started", {
            "tool_name": tool_name,
            "permission_level": tool.permission_level,
            "source": "tool_registry",
        })

        started_at = datetime.now(timezone.utc).isoformat()
        t0 = time.monotonic()
        try:
            result = await tool.run(db=db, **kwargs)
            duration_ms = int((time.monotonic() - t0) * 1000)
            # Inject audit fields (tool.run returns a fresh ToolResult dataclass)
            result.duration_ms  = duration_ms
            result.started_at   = started_at
            await safe_emit(event_callback, "tool_completed", {
                "tool_name": tool_name,
                "status": "success",
                "ok": True,
                "duration_ms": duration_ms,
                "summary": result.summary or "",
                "permission_level": tool.permission_level,
                "source": "tool_registry",
            })
            return result
        except Exception as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            log.exception("ToolRegistry: unexpected error in %s", tool_name)
            await safe_emit(event_callback, "tool_completed", {
                "tool_name": tool_name,
                "status": "failed",
                "ok": False,
                "duration_ms": duration_ms,
                "error": "tool_exception",
                "permission_level": getattr(tool, "permission_level", "read_only"),
                "source": "tool_registry",
            })
            return ToolResult(
                ok=False,
                tool_name=tool_name,
                summary="工具执行异常",
                error=str(exc),
                duration_ms=duration_ms,
                started_at=started_at,
            )
