"""
Circuit breaker — Phase 6V-P1.31.

Re-exports ProviderCircuitBreaker from budget module for clean imports.
"""
from __future__ import annotations

from .budget import ProviderCircuitBreaker

__all__ = ["ProviderCircuitBreaker"]
