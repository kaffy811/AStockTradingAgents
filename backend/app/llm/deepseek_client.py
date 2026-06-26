from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator

from openai import OpenAI, APIError, AuthenticationError

from app.core.config import settings
from app.llm.base import BaseLLMClient

log = logging.getLogger(__name__)


class DeepSeekClient(BaseLLMClient):
    """
    LLM client for DeepSeek, using the OpenAI-compatible API.

    Default model : deepseek-v4-flash  (low-latency, everyday analysis)
    Pro model     : deepseek-v4-pro    (complex agent reasoning, deep analysis)

    This class is intentionally free of any financial or agent logic.
    """

    def __init__(self) -> None:
        if not settings.deepseek_api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY is not set. "
                "Add it to your .env file before using DeepSeekClient."
            )
        self._default_model = settings.deepseek_default_model
        self._pro_model = settings.deepseek_pro_model
        self._client = OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )

    def chat(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.3,
        model: str | None = None,
    ) -> str:
        """
        Send messages to DeepSeek and return the reply text.

        Pass model="deepseek-v4-pro" to use the pro model for this call.
        Omit model (or pass None) to use the configured default (deepseek-v4-flash).
        """
        target_model = model or self._default_model

        try:
            response = self._client.chat.completions.create(
                model=target_model,
                messages=messages,
                temperature=temperature,
            )
        except AuthenticationError as exc:
            raise ValueError(f"DeepSeek authentication failed: {exc}") from exc
        except APIError as exc:
            raise RuntimeError(f"DeepSeek API error [{exc.status_code}]: {exc.message}") from exc

        content = response.choices[0].message.content
        if content is None:
            raise RuntimeError("DeepSeek returned an empty response (content is None).")
        return content

    # ── Convenience shortcuts ─────────────────────────────────────────────────

    def chat_flash(self, messages: list[dict], *, temperature: float = 0.3) -> str:
        """Explicitly call deepseek-v4-flash regardless of configured default."""
        return self.chat(messages, temperature=temperature, model=self._default_model)

    def chat_pro(self, messages: list[dict], *, temperature: float = 0.3) -> str:
        """Explicitly call deepseek-v4-pro for complex reasoning tasks."""
        return self.chat(messages, temperature=temperature, model=self._pro_model)

    # ── Async streaming ───────────────────────────────────────────────────────

    async def async_stream_chat(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.3,
        model: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        """
        Async generator that streams DeepSeek response chunks.

        Yields dicts with shape:
            {"type": "thinking", "content": str}   — reasoning_content (R1 models)
            {"type": "answer",   "content": str}   — final answer tokens
            {"type": "done"}                        — stream finished sentinel

        Uses a Queue bridge so the sync OpenAI streaming loop runs in a thread
        while the caller awaits events asynchronously.
        """
        return self._stream_generator(messages, temperature=temperature, model=model)

    async def _stream_generator(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.3,
        model: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        target_model = model or self._default_model
        queue: asyncio.Queue[dict | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _run_sync_stream() -> None:
            try:
                stream = self._client.chat.completions.create(
                    model=target_model,
                    messages=messages,
                    temperature=temperature,
                    stream=True,
                )
                for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta

                    # reasoning_content: only available on deepseek-reasoner models
                    reasoning = getattr(delta, "reasoning_content", None)
                    if isinstance(reasoning, str) and reasoning:
                        loop.call_soon_threadsafe(queue.put_nowait, {"type": "thinking", "content": reasoning})

                    content = getattr(delta, "content", None)
                    if isinstance(content, str) and content:
                        loop.call_soon_threadsafe(queue.put_nowait, {"type": "answer", "content": content})

            except AuthenticationError as exc:
                loop.call_soon_threadsafe(queue.put_nowait, {
                    "type": "error", "content": f"认证失败: {exc}"
                })
            except APIError as exc:
                loop.call_soon_threadsafe(queue.put_nowait, {
                    "type": "error", "content": f"API错误 [{exc.status_code}]: {exc.message}"
                })
            except Exception as exc:
                loop.call_soon_threadsafe(queue.put_nowait, {
                    "type": "error", "content": str(exc)
                })
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

        # Run sync stream in thread
        task = loop.run_in_executor(None, _run_sync_stream)

        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            await task
