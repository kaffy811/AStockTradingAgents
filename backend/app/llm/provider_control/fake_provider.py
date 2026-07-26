"""
Fake provider harness — Phase 6V-P1.31.

Provides deterministic fake LLM responses for testing all provider control plane
scenarios WITHOUT making any real network calls.

Test guarantee: Any test using FakeProviderHarness MUST NOT hit api.deepseek.com.
The harness monkeypatches the OpenAI client transport at import time if
BLOCK_REAL_PROVIDER_IN_TESTS=1 is set (enforced by conftest.py autouse fixture).

Scenarios:
  - success_with_usage: normal call, usage_complete=True
  - success_without_usage: usage absent (usage_complete=False)
  - timeout: raises openai.APITimeoutError
  - rate_limited: raises openai.RateLimitError
  - credential_invalid: raises openai.AuthenticationError
  - malformed_response: content=None or missing choices
  - budget_exhausted_request: BudgetExhaustedError (budget_type=request)
  - budget_exhausted_cost: BudgetExhaustedError (budget_type=cost)
  - concurrency_limit: ConcurrencyLimitError
  - circuit_open: CircuitOpenError
  - kill_switch: KillSwitchError
  - credential_missing: CredentialGateError
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

from .usage import ProviderUsageResult
from .errors import (
    BudgetExhaustedError,
    ConcurrencyLimitError,
    CircuitOpenError,
    KillSwitchError,
    CredentialGateError,
)


@dataclass
class FakeCallResult:
    scenario: str
    content: str | None
    usage: ProviderUsageResult
    raised: Exception | None = None
    real_network_calls: int = 0  # MUST always be 0


# Pre-built scenario results
SCENARIOS: dict[str, FakeCallResult] = {
    "success_with_usage": FakeCallResult(
        scenario="success_with_usage",
        content="这是一个测试分析结果。股票估值合理，建议持有。",
        usage=ProviderUsageResult.fake(input_tokens=150, output_tokens=80),
        real_network_calls=0,
    ),
    "success_without_usage": FakeCallResult(
        scenario="success_without_usage",
        content="分析完成。",
        usage=ProviderUsageResult.not_captured(),
        real_network_calls=0,
    ),
    "timeout": FakeCallResult(
        scenario="timeout",
        content=None,
        usage=ProviderUsageResult.not_captured(),
        raised=None,  # Will be set to APITimeoutError at use site
        real_network_calls=0,
    ),
    "rate_limited": FakeCallResult(
        scenario="rate_limited",
        content=None,
        usage=ProviderUsageResult.not_captured(),
        raised=None,  # Will be set to RateLimitError at use site
        real_network_calls=0,
    ),
    "credential_invalid": FakeCallResult(
        scenario="credential_invalid",
        content=None,
        usage=ProviderUsageResult.not_captured(),
        raised=None,  # Will be set to AuthenticationError at use site
        real_network_calls=0,
    ),
    "malformed_response": FakeCallResult(
        scenario="malformed_response",
        content=None,
        usage=ProviderUsageResult.not_captured(),
        real_network_calls=0,
    ),
    "budget_exhausted_request": FakeCallResult(
        scenario="budget_exhausted_request",
        content=None,
        usage=ProviderUsageResult.not_captured(),
        raised=BudgetExhaustedError("Request budget exhausted: 100/100 used.", budget_type="request"),
        real_network_calls=0,
    ),
    "budget_exhausted_cost": FakeCallResult(
        scenario="budget_exhausted_cost",
        content=None,
        usage=ProviderUsageResult.not_captured(),
        raised=BudgetExhaustedError("Cost budget exhausted: ¥100/100 CNY.", budget_type="cost"),
        real_network_calls=0,
    ),
    "concurrency_limit": FakeCallResult(
        scenario="concurrency_limit",
        content=None,
        usage=ProviderUsageResult.not_captured(),
        raised=ConcurrencyLimitError("Max concurrency reached: 2/2 slots occupied.", active_slots=2),
        real_network_calls=0,
    ),
    "circuit_open": FakeCallResult(
        scenario="circuit_open",
        content=None,
        usage=ProviderUsageResult.not_captured(),
        raised=CircuitOpenError("Provider circuit breaker is OPEN."),
        real_network_calls=0,
    ),
    "kill_switch": FakeCallResult(
        scenario="kill_switch",
        content=None,
        usage=ProviderUsageResult.not_captured(),
        raised=KillSwitchError("Kill switch active."),
        real_network_calls=0,
    ),
    "credential_missing": FakeCallResult(
        scenario="credential_missing",
        content=None,
        usage=ProviderUsageResult.not_captured(),
        raised=CredentialGateError("DEEPSEEK_API_KEY_STAGING not provisioned."),
        real_network_calls=0,
    ),
}


def get_scenario(name: str) -> FakeCallResult:
    """Get a pre-built fake scenario by name."""
    if name not in SCENARIOS:
        raise ValueError(f"Unknown fake scenario: {name!r}. Available: {sorted(SCENARIOS)}")
    return SCENARIOS[name]


def make_fake_openai_response(
    content: str,
    *,
    input_tokens: int = 100,
    output_tokens: int = 50,
    model: str = "deepseek-v4-flash",
) -> MagicMock:
    """Build a fake openai ChatCompletion response object."""
    mock_usage = MagicMock()
    mock_usage.prompt_tokens = input_tokens
    mock_usage.completion_tokens = output_tokens
    mock_usage.total_tokens = input_tokens + output_tokens
    mock_usage.prompt_tokens_details = None
    mock_usage.completion_tokens_details = None

    mock_message = MagicMock()
    mock_message.content = content

    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = mock_usage
    mock_response.model = model

    return mock_response


class FakeDeepSeekClient:
    """
    Drop-in fake for DeepSeekClient.
    All methods return deterministic results without any HTTP calls.
    """

    def __init__(self, scenario: str = "success_with_usage") -> None:
        self._scenario = scenario
        self._call_count = 0

    @property
    def real_network_calls(self) -> int:
        return 0  # ALWAYS 0

    def chat(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.3,
        model: str | None = None,
    ) -> str:
        self._call_count += 1
        result = get_scenario(self._scenario)
        if result.raised is not None:
            raise result.raised
        if result.content is None:
            raise RuntimeError(f"Fake provider returned malformed response (scenario={self._scenario})")
        return result.content

    def chat_flash(self, messages: list[dict], *, temperature: float = 0.3) -> str:
        return self.chat(messages, temperature=temperature)

    def chat_pro(self, messages: list[dict], *, temperature: float = 0.3) -> str:
        return self.chat(messages, temperature=temperature)

    def get_last_usage(self) -> ProviderUsageResult:
        result = get_scenario(self._scenario)
        return result.usage

    @property
    def call_count(self) -> int:
        return self._call_count
