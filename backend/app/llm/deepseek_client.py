from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import asdict, dataclass
from typing import AsyncGenerator

from openai import (
    APIConnectionError,
    APIError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)

from app.core.config import settings
from app.llm.base import BaseLLMClient
from app.llm.provider_control.usage import ProviderUsageResult

log = logging.getLogger(__name__)

_SAFE_PROVIDER_CODE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


@dataclass(frozen=True)
class ProviderErrorRecord:
    """Allowlisted provider failure facts safe for request-local propagation."""

    category: str
    retryable: bool
    http_status: int | None
    provider_code: str | None
    safe_reason_code: str
    original_exception_type: str

    def to_dict(self) -> dict[str, str | int | bool | None]:
        return asdict(self)


class NormalizedProviderError(RuntimeError):
    """A provider failure whose public string contains no request/provider detail."""

    def __init__(self, record: ProviderErrorRecord) -> None:
        self.record = record
        safe_summary = (
            "DeepSeek returned an empty response or invalid payload"
            if record.category == "provider_payload"
            else "LLM provider request failed"
        )
        super().__init__(
            f"{safe_summary} ({record.safe_reason_code}; "
            f"category={record.category}; retryable={str(record.retryable).lower()}; "
            f"http_status={record.http_status})"
        )


class ProviderPayloadError(RuntimeError):
    """The provider response exists but does not satisfy the client contract."""


def _safe_provider_code(exc: BaseException) -> str | None:
    code = getattr(exc, "code", None)
    if isinstance(code, str) and _SAFE_PROVIDER_CODE_RE.fullmatch(code):
        return code
    return None


def normalize_provider_error(exc: BaseException) -> ProviderErrorRecord:
    """Classify SDK failures without probing fields absent from their type."""

    exception_type = type(exc).__name__
    if isinstance(exc, APITimeoutError):
        return ProviderErrorRecord(
            category="connection", retryable=True, http_status=None,
            provider_code=None, safe_reason_code="PROVIDER_TIMEOUT",
            original_exception_type=exception_type,
        )
    if isinstance(exc, APIConnectionError):
        return ProviderErrorRecord(
            category="connection", retryable=True, http_status=None,
            provider_code=None, safe_reason_code="PROVIDER_CONNECTION_FAILED",
            original_exception_type=exception_type,
        )
    if isinstance(exc, APIResponseValidationError) or isinstance(exc, ProviderPayloadError):
        return ProviderErrorRecord(
            category="provider_payload", retryable=False, http_status=None,
            provider_code=_safe_provider_code(exc),
            safe_reason_code="PROVIDER_PAYLOAD_INVALID",
            original_exception_type=exception_type,
        )
    if isinstance(exc, APIStatusError):
        status = exc.status_code
        retryable = status == 429 or status >= 500
        reason = (
            "PROVIDER_AUTHENTICATION_FAILED" if status == 401
            else "PROVIDER_RATE_LIMITED" if status == 429
            else "PROVIDER_HTTP_ERROR"
        )
        return ProviderErrorRecord(
            category="http_status", retryable=retryable, http_status=status,
            provider_code=_safe_provider_code(exc), safe_reason_code=reason,
            original_exception_type=exception_type,
        )
    return ProviderErrorRecord(
        category="local_client", retryable=False, http_status=None,
        provider_code=None, safe_reason_code="PROVIDER_CLIENT_ERROR",
        original_exception_type=exception_type,
    )


def _normalized_exception(exc: BaseException) -> NormalizedProviderError:
    return NormalizedProviderError(normalize_provider_error(exc))


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
        self._default_model  = settings.deepseek_default_model
        self._pro_model      = settings.deepseek_pro_model
        self._reasoner_model = settings.deepseek_reasoner_model  # C32
        # P1.31: explicit timeout ≤30s (SDK default 600s is unsafe for live arbitration)
        _timeout = getattr(settings, "pi_real_provider_timeout_seconds", 30.0)
        self._client = OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            timeout=_timeout,
        )
        # P1.31: last call usage (captured from response.usage)
        self._last_usage: ProviderUsageResult = ProviderUsageResult.not_captured()

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
            # P1.31: capture token usage from response
            self._last_usage = ProviderUsageResult.from_openai_usage(
                getattr(response, "usage", None)
            )
            content = response.choices[0].message.content
            if content is None:
                raise ProviderPayloadError("empty response content")
            return content
        except AuthenticationError as exc:
            self._last_usage = ProviderUsageResult.not_captured()
            raise _normalized_exception(exc) from exc
        except RateLimitError as exc:
            # P1.31: rate limit → legacy_pi_failed signal
            self._last_usage = ProviderUsageResult.not_captured()
            raise _normalized_exception(exc) from exc
        except APITimeoutError as exc:
            self._last_usage = ProviderUsageResult.not_captured()
            raise _normalized_exception(exc) from exc
        except APIError as exc:
            self._last_usage = ProviderUsageResult.not_captured()
            raise _normalized_exception(exc) from exc
        except Exception as exc:
            self._last_usage = ProviderUsageResult.not_captured()
            raise _normalized_exception(exc) from exc

    @property
    def last_usage(self) -> ProviderUsageResult:
        """Return token usage from the most recent chat() call."""
        return self._last_usage

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

    # ── C32: Reasoning model (deepseek-reasoner) ─────────────────────────────

    async def async_stream_reasoner(
        self,
        messages: list[dict],
    ) -> AsyncGenerator[dict, None]:
        """
        C32: Stream from the deepseek-reasoner (R1) model.

        The reasoner model:
          - Produces `reasoning_content` tokens before the final answer.
          - Does NOT support `temperature`, `top_p`, or similar sampling params.

        Yields the same shape as async_stream_chat:
            {"type": "thinking", "content": str}  — reasoning_content tokens
            {"type": "answer",   "content": str}  — final answer tokens
            {"type": "done"}                        — stream finished sentinel
        """
        return self._stream_generator(
            messages,
            temperature=None,         # reasoner ignores temperature
            model=self._reasoner_model,
        )

    async def _stream_generator(
        self,
        messages: list[dict],
        *,
        temperature: float | None = 0.3,
        model: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        target_model = model or self._default_model
        queue: asyncio.Queue[dict | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _run_sync_stream() -> None:
            try:
                # C32: reasoner model doesn't support temperature; omit when None
                create_kwargs: dict = {
                    "model":    target_model,
                    "messages": messages,
                    "stream":   True,
                }
                if temperature is not None:
                    create_kwargs["temperature"] = temperature
                stream = self._client.chat.completions.create(**create_kwargs)
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

            except Exception as exc:
                normalized = _normalized_exception(exc)
                loop.call_soon_threadsafe(queue.put_nowait, {
                    "type": "error",
                    "content": str(normalized),
                    "provider_error": normalized.record.to_dict(),
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
