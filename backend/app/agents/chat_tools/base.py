"""
BaseTool ABC — all Chat Tools inherit from this (Phase C4).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.chat_tools.tool_result import ToolResult


class BaseTool(ABC):
    """
    All tools must be async-safe and must NEVER raise exceptions to callers.
    Catch all errors internally and return ToolResult(ok=False, ...).
    """

    # Default permission level for all read-only tools.
    # Action tools that write data should override this with "write_user_data"
    # or "long_running" as appropriate.
    permission_level: str = "read_only"

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def run(self, db: AsyncSession, **kwargs: Any) -> ToolResult: ...
