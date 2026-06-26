"""
Chat Tool Registry — Phase C4.

All tools are read-only. Write operations (add watchlist, generate report,
compare) remain as mock confirmation flows in chat_orchestrator.py.
"""
from app.agents.chat_tools.registry import ToolRegistry
from app.agents.chat_tools.tool_result import ToolResult

__all__ = ["ToolRegistry", "ToolResult"]
