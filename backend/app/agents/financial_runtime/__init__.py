"""Layered financial agent runtime (Phase 6U-E1).

This package is intentionally additive. Legacy chat remains available; the
runtime is selected by ``CHAT_RUNTIME_MODE``.
"""

from app.agents.financial_runtime.runtime import financial_agent_runtime

__all__ = ["financial_agent_runtime"]
