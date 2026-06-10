from abc import ABC, abstractmethod


class BaseLLMClient(ABC):
    """
    Abstract interface for all LLM providers.

    Rules:
    - No financial / business logic here.
    - Only defines how to send messages and receive a text reply.
    - Concrete providers (DeepSeek, OpenAI, Qwen …) subclass this.
    - Agents call this interface; they never import a concrete client directly.
    """

    @abstractmethod
    def chat(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.3,
        model: str | None = None,
    ) -> str:
        """
        Send a list of chat messages and return the assistant reply as a string.

        Args:
            messages:    OpenAI-style message list, e.g.
                         [{"role": "system", "content": "..."},
                          {"role": "user",   "content": "..."}]
            temperature: Sampling temperature (0.0 – 1.0). Ignored in thinking
                         mode (DeepSeek silently drops it).
            model:       Override the provider's default model for this call.
                         Pass None to use the configured default.

        Returns:
            The assistant's reply text (choices[0].message.content).

        Raises:
            ValueError:  If required credentials are missing.
            RuntimeError: If the upstream API returns an error.
        """
        ...
