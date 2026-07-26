"""
Provider usage normalization — Phase 6V-P1.31.

Defines the standard ProviderUsageResult dataclass and normalization logic
for extracting token counts from DeepSeek (OpenAI-compatible) API responses.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass
class ProviderUsageResult:
    """
    Normalized token usage from a provider API call.

    Fields are captured from response.usage (OpenAI-compatible schema).
    usage_complete=False means usage was absent or partial — cost estimate unreliable.
    """
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    usage_complete: bool = False
    usage_source: str = "not_captured"  # "api_response" | "not_captured" | "fake" | "fallback"

    @property
    def effective_input_tokens(self) -> int:
        """Non-cached input tokens (billed at full rate)."""
        return max(0, self.input_tokens - self.cached_input_tokens)

    @classmethod
    def from_openai_usage(cls, usage: Any) -> "ProviderUsageResult":
        """
        Extract usage from an openai.types.CompletionUsage object.

        Handles None gracefully → returns usage_complete=False.
        """
        if usage is None:
            return cls(usage_complete=False, usage_source="not_captured")

        try:
            input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
            total_tokens = int(getattr(usage, "total_tokens", 0) or 0)

            # Cached input tokens (available via completion_tokens_details)
            cached_input = 0
            details = getattr(usage, "prompt_tokens_details", None)
            if details is not None:
                cached_input = int(getattr(details, "cached_tokens", 0) or 0)

            # Reasoning tokens (deepseek-reasoner / R1 models)
            reasoning = 0
            comp_details = getattr(usage, "completion_tokens_details", None)
            if comp_details is not None:
                reasoning = int(getattr(comp_details, "reasoning_tokens", 0) or 0)

            return cls(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_input_tokens=cached_input,
                reasoning_tokens=reasoning,
                total_tokens=total_tokens or (input_tokens + output_tokens),
                usage_complete=input_tokens > 0 or output_tokens > 0,
                usage_source="api_response",
            )
        except Exception:
            return cls(usage_complete=False, usage_source="not_captured")

    @classmethod
    def fake(
        cls,
        *,
        input_tokens: int = 100,
        output_tokens: int = 50,
        cached_input_tokens: int = 0,
        reasoning_tokens: int = 0,
    ) -> "ProviderUsageResult":
        """Create a deterministic fake usage result for tests."""
        return cls(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
            reasoning_tokens=reasoning_tokens,
            total_tokens=input_tokens + output_tokens,
            usage_complete=True,
            usage_source="fake",
        )

    @classmethod
    def not_captured(cls) -> "ProviderUsageResult":
        """Sentinel for missing usage data."""
        return cls(usage_complete=False, usage_source="not_captured")

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "total_tokens": self.total_tokens,
            "usage_complete": self.usage_complete,
            "usage_source": self.usage_source,
        }
