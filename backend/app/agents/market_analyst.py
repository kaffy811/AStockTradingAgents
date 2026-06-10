"""
Backward-compatibility shim.

MarketAnalystAgent has been renamed to TechnicalAnalystAgent.
This module re-exports the new class under the old name so that any
existing imports continue to work without changes.

Prefer importing from app.agents.technical_analyst directly.
"""

from app.agents.technical_analyst import TechnicalAnalystAgent as MarketAnalystAgent  # noqa: F401

__all__ = ["MarketAnalystAgent"]
