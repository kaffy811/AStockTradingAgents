"""Canonical data contracts for the layered financial chat runtime."""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


SCHEMA_VERSION = "financial_agent_runtime.v1"
STATUS_SUCCESS = "success"
STATUS_PARTIAL_SUCCESS = "partial_success"
STATUS_FAILED = "failed"
STATUS_CLARIFICATION_REQUIRED = "clarification_required"
STATUS_UNAVAILABLE = "unavailable"
STATUS_CANCELLED = "cancelled"
VALID_STATUSES = {
    STATUS_SUCCESS,
    STATUS_PARTIAL_SUCCESS,
    STATUS_FAILED,
    STATUS_CLARIFICATION_REQUIRED,
    STATUS_UNAVAILABLE,
    STATUS_CANCELLED,
    "pending",
    "started",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass(slots=True)
class RuntimeEnvelope:
    trace_id: str
    schema_version: str = SCHEMA_VERSION
    request_id: str = field(default_factory=lambda: new_id("req"))
    status: str = "pending"
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    completed_at: str | None = None
    error_code: str | None = None
    warnings: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RuntimeRequest(RuntimeEnvelope):
    raw_query: str = ""
    conversation_id: str = ""
    page_context: dict[str, Any] = field(default_factory=dict)
    user_context: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentRequest(RuntimeRequest):
    pass


@dataclass(slots=True)
class SecurityEntity(RuntimeEnvelope):
    entity_type: str = "equity"
    market: str = ""
    symbol: str = ""
    exchange: str = ""
    ts_code: str = ""
    short_name: str = ""
    full_name: str = ""
    aliases: list[str] = field(default_factory=list)
    industry: str | None = None
    confidence: float = 0.0
    match_type: str = ""
    ambiguity: bool = False
    candidates: list[dict[str, Any]] = field(default_factory=list)
    source: str = ""


@dataclass(slots=True)
class IntentRoutingResult(RuntimeEnvelope):
    intent: str = "ambiguous"
    intent_confidence: float = 0.0
    resolved_entities: list[SecurityEntity] = field(default_factory=list)
    policy_class: str = "normal"
    needs_clarification: bool = False
    clarification_options: list[dict[str, Any]] = field(default_factory=list)
    reason: str = ""


@dataclass(slots=True)
class FinancialSessionContext(RuntimeEnvelope):
    primary_entity: SecurityEntity | None = None
    secondary_entities: list[SecurityEntity] = field(default_factory=list)
    active_market: str = ""
    active_symbol: str = ""
    active_report_id: int | None = None
    active_report_year: int | None = None
    active_report_type: str | None = None
    active_period: str | None = None
    last_intent: str = ""
    last_skill: str = ""
    page_context: dict[str, Any] = field(default_factory=dict)
    market_clock: dict[str, Any] = field(default_factory=dict)
    pending_clarification: dict[str, Any] | None = None
    last_successful_context: dict[str, Any] | None = None
    resolved_pronouns: dict[str, Any] = field(default_factory=dict)
    context_version: int = 1


@dataclass(slots=True)
class PlanStep:
    step_id: str
    capability: str
    depends_on: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    timeout_ms: int = 5000


@dataclass(slots=True)
class ExecutionPlan(RuntimeEnvelope):
    plan_id: str = ""
    intent: str = ""
    entities: list[SecurityEntity] = field(default_factory=list)
    steps: list[PlanStep] = field(default_factory=list)
    dependencies: dict[str, list[str]] = field(default_factory=dict)
    execution_mode: str = "serial"
    timeout_budget_ms: int = 15000
    ui_stages: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ToolRequest(RuntimeEnvelope):
    tool_call_id: str = ""
    capability: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolResponse(RuntimeEnvelope):
    tool_call_id: str = ""
    capability: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    provenance: list[dict[str, Any]] = field(default_factory=list)
    freshness: dict[str, Any] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)
    error: dict[str, Any] | None = None
    latency_ms: int = 0


@dataclass(slots=True)
class ProvenanceRecord(RuntimeEnvelope):
    source_id: str = ""
    source_type: str = ""
    provider: str = ""
    as_of: str | None = None
    retrieved_at: str = field(default_factory=utc_now)


@dataclass(slots=True)
class DataFreshness(RuntimeEnvelope):
    as_of: str | None = None
    is_realtime: bool = False
    is_stale: bool = False


@dataclass(slots=True)
class DataQuality(RuntimeEnvelope):
    completeness: float | None = None
    applicable_field_count: int = 0
    available_field_count: int = 0
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class FinancialFact(RuntimeEnvelope):
    fact_id: str = ""
    label: str = ""
    value: Any = None
    unit: str = ""
    period: str | None = None
    entity: SecurityEntity | None = None
    evidence_ids: list[str] = field(default_factory=list)
    provenance: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class FinancialInference(RuntimeEnvelope):
    inference_id: str = ""
    statement: str = ""
    confidence: float | None = None
    evidence_ids: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ConflictRecord(RuntimeEnvelope):
    conflict_id: str = ""
    conflict_type: str = ""
    entities: list[SecurityEntity] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    description: str = ""


@dataclass(slots=True)
class AgentResponse(RuntimeEnvelope):
    agent_run_id: str = ""
    agent_type: str = ""
    findings: list[dict[str, Any]] = field(default_factory=list)
    metrics: list[FinancialFact] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    inferences: list[dict[str, Any]] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    error: dict[str, Any] | None = None


@dataclass(slots=True)
class StructuredAnswer(RuntimeEnvelope):
    title: str = ""
    conclusion: str = ""
    tables: list[dict[str, Any]] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    owner: str = "financial_agent_runtime"


@dataclass(slots=True)
class ComplianceReview(RuntimeEnvelope):
    passed: bool = True
    policy_findings: list[dict[str, Any]] = field(default_factory=list)
    logic_findings: list[dict[str, Any]] = field(default_factory=list)
    edit_instructions: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class FinalChatResponse(RuntimeEnvelope):
    answer: str = ""
    structured_answer: StructuredAnswer | None = None
    tool_events: list[dict[str, Any]] = field(default_factory=list)
    cards: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class RuntimeError(RuntimeEnvelope):
    message: str = ""
    retryable: bool = False
    details: dict[str, Any] = field(default_factory=dict)
