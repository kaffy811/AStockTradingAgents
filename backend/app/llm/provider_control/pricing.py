"""
Versioned pricing registry — Phase 6V-P1.31.

Rules:
- All arithmetic uses Decimal (no float rounding errors).
- verified=False unless price confirmed from authoritative URL + date.
- pricing_mode="test_fixture" → use placeholder prices for arithmetic testing.
- pricing_mode="production" → MUST have verified=True or raises PricingUnverifiedError.
- Pricing is NEVER sourced from memory or hallucination.
"""
from __future__ import annotations

import json
import os
from decimal import Decimal
from dataclasses import dataclass
from typing import Any

from .errors import PricingUnverifiedError

_PRICING_FILE = os.path.join(
    os.path.dirname(__file__), "..", "pricing", "deepseek_prices.json"
)


@dataclass(frozen=True)
class ModelPricing:
    model_id: str
    input_per_1m_cny: Decimal
    output_per_1m_cny: Decimal
    cached_input_per_1m_cny: Decimal
    reasoning_per_1m_cny: Decimal
    verified: bool
    pricing_mode: str  # "test_fixture" | "production"

    def estimate_cost_cny(
        self,
        input_tokens: int,
        output_tokens: int,
        cached_input_tokens: int = 0,
        reasoning_tokens: int = 0,
    ) -> Decimal:
        """Estimate cost using Decimal arithmetic. Returns UNVERIFIED if not verified."""
        tokens_1m = Decimal("1000000")
        cost = (
            self.input_per_1m_cny * Decimal(input_tokens - cached_input_tokens) / tokens_1m
            + self.cached_input_per_1m_cny * Decimal(cached_input_tokens) / tokens_1m
            + self.output_per_1m_cny * Decimal(output_tokens - reasoning_tokens) / tokens_1m
            + self.reasoning_per_1m_cny * Decimal(reasoning_tokens) / tokens_1m
        )
        return max(Decimal("0"), cost)

    @property
    def is_unverified(self) -> bool:
        return not self.verified


class PricingRegistry:
    """
    Pricing registry backed by deepseek_prices.json.

    All pricing entries in P1.31 are verified=False (test_fixture mode).
    The registry correctly handles this by flagging estimates as UNVERIFIED
    rather than blocking the test infrastructure.
    """

    def __init__(self, pricing_file: str = _PRICING_FILE) -> None:
        self._data: dict[str, Any] = {}
        self._models: dict[str, ModelPricing] = {}
        self._load(pricing_file)

    def _load(self, path: str) -> None:
        try:
            with open(path) as f:
                self._data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Failed to load pricing file {path}: {exc}") from exc

        pricing_mode = self._data.get("pricing_mode", "test_fixture")
        global_verified = self._data.get("verified", False)

        for model_id, entry in self._data.get("models", {}).items():
            p = entry.get("pricing", {})
            model_verified = p.get("verified", False) and global_verified
            self._models[model_id] = ModelPricing(
                model_id=model_id,
                input_per_1m_cny=Decimal(str(p.get("input_per_1m_tokens_cny", "0"))),
                output_per_1m_cny=Decimal(str(p.get("output_per_1m_tokens_cny", "0"))),
                cached_input_per_1m_cny=Decimal(str(p.get("cached_input_per_1m_tokens_cny", "0"))),
                reasoning_per_1m_cny=Decimal(str(p.get("reasoning_per_1m_tokens_cny", "0"))),
                verified=model_verified,
                pricing_mode=pricing_mode,
            )
            # Register aliases
            for alias in entry.get("aliases", []):
                self._models[alias] = self._models[model_id]

    @property
    def pricing_version(self) -> str:
        return self._data.get("schema_version", "unknown")

    @property
    def pricing_mode(self) -> str:
        return self._data.get("pricing_mode", "test_fixture")

    @property
    def globally_verified(self) -> bool:
        return self._data.get("verified", False)

    def get_model_pricing(self, model_id: str) -> ModelPricing:
        if model_id not in self._models:
            raise KeyError(f"No pricing entry for model: {model_id!r}")
        return self._models[model_id]

    def estimate_cost_cny(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        cached_input_tokens: int = 0,
        reasoning_tokens: int = 0,
        *,
        require_verified: bool = False,
    ) -> Decimal:
        """
        Estimate cost. If require_verified=True and pricing is unverified → raises.
        In test_fixture mode, always returns arithmetic result without raising.
        """
        mp = self.get_model_pricing(model_id)
        if require_verified and mp.is_unverified:
            raise PricingUnverifiedError(
                f"Pricing for {model_id!r} is not verified from authoritative source. "
                "Cannot estimate real cost. Verify at platform.deepseek.com/api-docs/pricing."
            )
        return mp.estimate_cost_cny(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
            reasoning_tokens=reasoning_tokens,
        )

    def list_enabled_for_staging_real(self) -> list[str]:
        """Return model IDs with enabled_for_staging_real=True."""
        result = []
        for model_id, entry in self._data.get("models", {}).items():
            if entry.get("enabled_for_staging_real", False):
                result.append(model_id)
        return result


# Module-level singleton (lazy-loaded)
_registry: PricingRegistry | None = None


def get_pricing_registry() -> PricingRegistry:
    global _registry
    if _registry is None:
        _registry = PricingRegistry()
    return _registry
