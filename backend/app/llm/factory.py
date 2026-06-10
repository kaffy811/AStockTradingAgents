from app.core.config import settings
from app.llm.base import BaseLLMClient


def get_llm_client() -> BaseLLMClient:
    """
    Return the configured LLM client based on settings.llm_provider.

    This is the single entry point for obtaining an LLM client anywhere in the
    app (routers, agents, LangGraph nodes).  Adding a new provider means adding
    one branch here — nothing else needs to change.

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
