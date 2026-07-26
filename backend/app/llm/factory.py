import logging

from app.core.config import settings
from app.llm.base import BaseLLMClient

log = logging.getLogger(__name__)


def check_real_provider_gate() -> dict:
    """
    Phase 6V-P1.32: Run ProviderActivationGate.check_all() and return result.

    Called before any real provider call attempt. Fail-closed by default
    (kill_switch=True, enabled=False) — safe to call at any time.

    Returns:
        {
          "gate_pass": bool,
          "blocked_by": str | None,   # human-readable reason
          "error_class": str | None,  # ProviderControlError subclass name
        }
    """
    from app.llm.provider_control.activation_gate import ProviderActivationGate
    from app.llm.provider_control.errors import ProviderControlError

    gate = ProviderActivationGate(settings=settings)
    try:
        gate.check_all()
        log.info("pi_canary: real provider activation gate PASS")
        return {"gate_pass": True, "blocked_by": None, "error_class": None}
    except ProviderControlError as exc:
        gate_id = getattr(exc, "gate", "unknown")
        log.warning(
            "pi_canary: real provider activation gate BLOCKED [Gate %s] %s: %s",
            gate_id, type(exc).__name__, exc,
        )
        return {
            "gate_pass": False,
            "blocked_by": str(exc),
            "error_class": type(exc).__name__,
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
