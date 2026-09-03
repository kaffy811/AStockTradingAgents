"""Contracts for the Pi-compatible financial agent runtime."""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol


RUNTIME_SCHEMA_VERSION = "pi_financial_runtime_v1"
EVENT_SCHEMA_VERSION = "pi_financial_event_v1"
TOOL_SCHEMA_VERSION = "financial_tool_v1"

STATUS_SUCCESS = "success"
STATUS_PARTIAL_SUCCESS = "partial_success"
STATUS_FAILED = "failed"
STATUS_UNAVAILABLE = "unavailable"
STATUS_CANCELLED = "cancelled"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass(slots=True)
class PiRuntimeBudgets:
    deadline_ms: int = 5000
    max_turns: int = 3
    max_tool_calls: int = 4
    max_parallel_tools: int = 2
    max_output_tokens: int = 1000

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PiRuntimeRequest:
    trace_id: str
    run_id: str
    conversation_id: str
    user_id: str
    intent: str
    schema_version: str = RUNTIME_SCHEMA_VERSION
    entities: list[dict[str, Any]] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    execution_plan: dict[str, Any] = field(default_factory=dict)
    allowed_tools: list[str] = field(default_factory=list)
    model_profile: str = "tool_routing_light"
    budgets: PiRuntimeBudgets = field(default_factory=PiRuntimeBudgets)
    runtime_mode: str = "shadow"
    read_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PiRuntimeMetrics:
    latency_ms: int = 0
    model_calls: int = 0
    tool_calls: int = 0
    tool_failures: int = 0
    tool_validation_failures: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    tool_latency_breakdown: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PiRuntimeEvent:
    trace_id: str
    run_id: str
    event_type: str
    sequence: int
    payload: dict[str, Any] = field(default_factory=dict)
    schema_version: str = EVENT_SCHEMA_VERSION
    event_id: str = field(default_factory=lambda: new_id("event"))
    timestamp: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PiToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    mode: str = "read_only"
    risk_level: str = "low"
    parallel_safe: bool = True
    idempotent: bool = True
    timeout_ms: int = 3000
    requires_provenance: bool = True
    required_permissions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PiToolCall:
    id: str
    name: str
    arguments: dict[str, Any]

    def signature(self) -> tuple[str, str]:
        return self.name, repr(sorted(self.arguments.items()))


@dataclass(slots=True)
class PiToolResponse:
    trace_id: str
    tool_call_id: str
    capability: str
    status: str
    data: dict[str, Any] = field(default_factory=dict)
    provenance: list[dict[str, Any]] = field(default_factory=list)
    freshness: dict[str, Any] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    error_code: str | None = None
    error: dict[str, Any] | None = None
    latency_ms: int = 0
    schema_version: str = TOOL_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PiAgentMessage:
    role: str
    content: Any
    timestamp: str = field(default_factory=utc_now)


@dataclass(slots=True)
class ModelProfile:
    name: str
    provider: str = "current_project_provider"
    model: str = "current_project_model"
    supports_tools: bool = True
    supports_structured_output: bool = True
    supports_streaming: bool = True
    context_window: int = 16000
    timeout_ms: int = 5000
    max_output_tokens: int = 1000
    temperature: float = 0.0
    data_policy: str = "financial_internal_only"


@dataclass(slots=True)
class ModelRequest:
    trace_id: str
    run_id: str
    model_profile: ModelProfile
    messages: list[PiAgentMessage]
    tools: list[PiToolDefinition]
    max_output_tokens: int


@dataclass(slots=True)
class ModelStreamEvent:
    event_type: str
    text_delta: str = ""
    tool_call: PiToolCall | None = None
    structured_output: dict[str, Any] | None = None
    error_code: str | None = None


@dataclass(slots=True)
class ModelResponse:
    text: str = ""
    structured_output: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[PiToolCall] = field(default_factory=list)
    status: str = STATUS_SUCCESS
    error_code: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0


class ModelGateway(Protocol):
    async def stream(self, request: ModelRequest):
        """Yield ModelStreamEvent values."""
        ...


@dataclass(slots=True)
class AgentCapabilityManifest:
    agent_id: str
    version: str
    purpose: str
    supported_intents: list[str]
    supported_markets: list[str]
    execution_mode: str
    model_profile: str
    allowed_tools: list[str]
    required_data_quality: dict[str, Any]
    max_turns: int
    max_tool_calls: int
    deadline_ms: int
    read_only: bool
    output_schema: str
    compliance_profile: str
    fallback: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PiAgentRunResult:
    trace_id: str
    run_id: str
    status: str
    agent_id: str
    turn_count: int = 0
    tool_call_count: int = 0
    events: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    structured_answer: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] | None = None
    metrics: PiRuntimeMetrics = field(default_factory=PiRuntimeMetrics)
    schema_version: str = RUNTIME_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
