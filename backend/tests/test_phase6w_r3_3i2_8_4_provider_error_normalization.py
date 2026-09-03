from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest
from openai import (
    APIConnectionError,
    APIResponseValidationError,
    APIStatusError,
)

from app.llm.deepseek_client import (
    DeepSeekClient,
    NormalizedProviderError,
    ProviderPayloadError,
    normalize_provider_error,
)


SECRET = "sk-test-secret-never-emit"
PRIVATE_URL = "https://provider.invalid/v1/chat?api_key=private"


def request() -> httpx.Request:
    return httpx.Request(
        "POST", PRIVATE_URL,
        headers={"Authorization": f"Bearer {SECRET}"},
        content=f'{{"secret":"{SECRET}"}}',
    )


def status_error(status: int, code: str | None = None) -> APIStatusError:
    body = {"error": {"code": code, "message": SECRET}}
    response = httpx.Response(status, request=request(), json=body)
    return APIStatusError("unsafe provider message " + SECRET, response=response, body=body)


def client_raising(exc: BaseException) -> DeepSeekClient:
    client = object.__new__(DeepSeekClient)
    client._default_model = "test-model"
    client._last_usage = MagicMock()
    client._client = MagicMock()
    client._client.chat.completions.create.side_effect = exc
    return client


def assert_safe(record, rendered: str) -> None:
    assert SECRET not in rendered
    assert PRIVATE_URL not in rendered
    assert "Authorization" not in rendered
    assert set(record.to_dict()) == {
        "category", "retryable", "http_status", "provider_code",
        "safe_reason_code", "original_exception_type",
    }


def test_connection_error_is_non_http_retryable_and_keeps_cause():
    original = APIConnectionError(message="connection failed " + SECRET, request=request())
    client = client_raising(original)
    with pytest.raises(NormalizedProviderError) as caught:
        client.chat([{"role": "user", "content": "test"}])
    record = caught.value.record
    assert record.category == "connection"
    assert record.retryable is True
    assert record.http_status is None
    assert record.safe_reason_code == "PROVIDER_CONNECTION_FAILED"
    assert caught.value.__cause__ is original
    assert_safe(record, str(caught.value))


@pytest.mark.parametrize(
    ("status", "retryable", "reason"),
    [(429, True, "PROVIDER_RATE_LIMITED"), (401, False, "PROVIDER_AUTHENTICATION_FAILED"),
     (503, True, "PROVIDER_HTTP_ERROR")],
)
def test_http_status_errors_preserve_status_policy(status, retryable, reason):
    original = status_error(status, code="safe_code")
    record = normalize_provider_error(original)
    assert record.category == "http_status"
    assert record.http_status == status
    assert record.retryable is retryable
    assert record.safe_reason_code == reason
    assert_safe(record, str(NormalizedProviderError(record)))


def test_payload_validation_and_local_errors_are_non_http_and_redacted():
    response = httpx.Response(200, request=request(), json={"raw": SECRET})
    payload_error = APIResponseValidationError(response=response, body={"raw": SECRET})
    payload_record = normalize_provider_error(payload_error)
    assert payload_record.category == "provider_payload"
    assert payload_record.http_status is None
    assert payload_record.retryable is False
    assert_safe(payload_record, str(NormalizedProviderError(payload_record)))

    local_record = normalize_provider_error(RuntimeError("local " + SECRET))
    assert local_record.category == "local_client"
    assert local_record.http_status is None
    assert local_record.retryable is False
    assert_safe(local_record, str(NormalizedProviderError(local_record)))


def test_none_content_is_normalized_as_provider_payload():
    client = object.__new__(DeepSeekClient)
    client._default_model = "test-model"
    client._last_usage = MagicMock()
    client._client = MagicMock()
    client._client.chat.completions.create.return_value = SimpleNamespace(
        usage=None, choices=[SimpleNamespace(message=SimpleNamespace(content=None))]
    )
    with pytest.raises(NormalizedProviderError) as caught:
        client.chat([{"role": "user", "content": "test"}])
    assert isinstance(caught.value.__cause__, ProviderPayloadError)
    assert caught.value.record.category == "provider_payload"


def test_success_response_behavior_is_unchanged():
    client = object.__new__(DeepSeekClient)
    client._default_model = "test-model"
    client._last_usage = MagicMock()
    client._client = MagicMock()
    client._client.chat.completions.create.return_value = SimpleNamespace(
        usage=None, choices=[SimpleNamespace(message=SimpleNamespace(content="safe answer"))]
    )
    assert client.chat([{"role": "user", "content": "test"}]) == "safe answer"


@pytest.mark.asyncio
async def test_stream_connection_error_uses_same_safe_record():
    original = APIConnectionError(message="connection failed " + SECRET, request=request())
    client = client_raising(original)
    events = [event async for event in client._stream_generator([{"role": "user", "content": "test"}])]
    assert len(events) == 1
    event = events[0]
    assert event["type"] == "error"
    assert event["provider_error"] == normalize_provider_error(original).to_dict()
    assert event["provider_error"]["category"] == "connection"
    assert event["provider_error"]["http_status"] is None
    assert_safe(normalize_provider_error(original), event["content"])


@pytest.mark.asyncio
async def test_stream_status_error_uses_same_safe_record():
    original = status_error(429, code="rate_limit")
    client = client_raising(original)
    events = [event async for event in client._stream_generator([{"role": "user", "content": "test"}])]
    event = events[0]
    assert event["provider_error"] == normalize_provider_error(original).to_dict()
    assert event["provider_error"]["http_status"] == 429
    assert event["provider_error"]["retryable"] is True
    assert_safe(normalize_provider_error(original), event["content"])
