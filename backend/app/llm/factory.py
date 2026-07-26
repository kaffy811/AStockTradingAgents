import logging
from typing import Any

from app.core.config import settings
from app.llm.base import BaseLLMClient

log = logging.getLogger(__name__)


def check_real_provider_gate(
    *,
    redis_client: Any | None = None,
    estimated_cost_cny: "Decimal | None" = None,
) -> dict:
    """
    Phase MVP-R1: Run full ProviderControlPlane gate (8/8 checks when Redis available).

    Falls back to 3-check synchronous gate if Redis is not injected.
    Returns ProviderGateDecision as dict for backward compatibility.

    Args:
        redis_client: Optional Redis client. If None, only synchronous checks run.
        estimated_cost_cny: Estimated cost for cost budget check. Defaults to 0.

    Returns:
        {
          "gate_pass": bool,
          "blocked_by": str | None,
          "allowed": bool,
          "reservation_id": str | None,
          "gate_checks_performed": list[str],
          "gate_checks_skipped": list[str],
          "total_checks_active": int,
        }
    """
    from decimal import Decimal
    # activation_gate is the underlying gate used by ProviderControlPlane
    from app.llm.provider_control.activation_gate import ProviderActivationGate  # noqa: F401
    from app.llm.provider_control.control_plane import get_provider_control_plane

    est = estimated_cost_cny if estimated_cost_cny is not None else Decimal("0")
    plane = get_provider_control_plane(redis_client=redis_client)
    decision = plane.check_gate(estimated_cost_cny=est)

    return {
        "gate_pass": decision.allowed,
        "blocked_by": decision.blocked_reason,
        "error_class": decision.error_class,
        "allowed": decision.allowed,
        "reservation_id": decision.reservation_id,
        "gate_checks_performed": decision.gate_checks_performed,
        "gate_checks_skipped": decision.gate_checks_skipped,
        "total_checks_active": plane.total_checks_active,
    }


def get_llm_client() -> BaseLLMClient:
    """
    Return the configured LLM client based on settings.llm_provider.

    This is the single entry point for obtaining an LLM client anywhere in the
    app (routers, agents, LangGraph nodes).  Adding a new provider means adding
    one branch here — nothing else needs to change.

    Phase 6V-P1.32: When pi_real_provider_enabled=True, check_real_provider_gate()
    must PASS before constructing a real provider client. Default is fail-closed
    (gate will block at Gate I — kill_switch=True / enabled=False), so normal
    operation is completely unchanged.

    Supported providers
    -------------------
    deepseek  → DeepSeekClient  (OpenAI-compatible, default)
    openai    → (reserved for future implementation)
    qwen      → (reserved for future implementation)
    claude    → (reserved for future implementation)
    """
    provider = settings.llm_provider.lower()

    if provider == "deepseek":
        from app.llm.deepseek_client import DeepSeekClient
        return DeepSeekClient()

    # ── Future providers ──────────────────────────────────────────────────────
    # if provider == "openai":
    #     from app.llm.openai_client import OpenAIClient
    #     return OpenAIClient()
    #
    # if provider == "qwen":
    #     from app.llm.qwen_client import QwenClient
    #     return QwenClient()
    #
    # if provider == "claude":
    #     from app.llm.claude_client import ClaudeClient
    #     return ClaudeClient()

    raise ValueError(
        f"Unsupported LLM provider: '{provider}'. "
        f"Set LLM_PROVIDER to one of: deepseek, openai, qwen, claude"
    )
