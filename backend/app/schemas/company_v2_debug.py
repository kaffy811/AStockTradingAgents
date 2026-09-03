from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


CompanyV2Stage = Literal["raw", "normalized", "completed", "render", "final"]


class CompanyV2Error(BaseModel):
    layer: str
    error_code: str
    message: str
    provider: str | None = None
    endpoint: str | None = None
    field: str | None = None


class CompanyV2SourceAttempt(BaseModel):
    provider: str
    endpoint: str
    attempted: bool = True
    success: bool = False
    status: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    elapsed_ms: int | None = None
    latency_ms: int = 0
    rows_count: int = 0
    columns: list[str] = Field(default_factory=list)
    non_null_fields: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    cache_hit: bool = False
    cache_stale: bool = False
    cache_status: str | None = None
    raw_type: str | None = None
    raw_shape: list[int] | None = None
    detached_timeout: bool = False
    aggregate_source_id: str | None = None
    data_success: bool | None = None


class CompanyV2Normalized(BaseModel):
    rows: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    fields: dict[str, Any] = Field(default_factory=dict)


class CompanyV2Completion(BaseModel):
    filled_fields: dict[str, Any] = Field(default_factory=dict)
    still_missing_fields: dict[str, Any] = Field(default_factory=dict)
    computed_fields: dict[str, Any] = Field(default_factory=dict)
    fallback_chain: dict[str, Any] = Field(default_factory=dict)


class CompanyV2Render(BaseModel):
    renderable: bool = False
    chart_renderable: bool = False
    table_renderable: bool = False
    has_displayable_data: bool = False
    visible_fields: list[str] = Field(default_factory=list)
    hidden_fields: list[str] = Field(default_factory=list)
    reason: str | None = None


class CompanyV2DebugMeta(BaseModel):
    enabled: bool = True
    raw_truncated: bool = False
    max_raw_chars: int = 20000


class CompanyV2DebugEnvelope(BaseModel):
    schema_version: str = "2.0"
    schema_features: list[str] = Field(default_factory=lambda: [
        "formatter_registry",
        "field_trace",
        "coverage",
        "provider_summary",
        "computed_field_registry",
        "report_status_machine",
        "data_validation_engine",
    ])
    request_id: str
    market: str
    symbol: str
    ts_code: str
    module_key: str
    data_mode: str
    stage: CompanyV2Stage = "final"
    ok: bool = True
    partial: bool = False
    stale: bool = False
    source_chain: list[CompanyV2SourceAttempt] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)
    normalized: CompanyV2Normalized = Field(default_factory=CompanyV2Normalized)
    completion: CompanyV2Completion = Field(default_factory=CompanyV2Completion)
    render: CompanyV2Render = Field(default_factory=CompanyV2Render)
    field_trace: dict[str, Any] = Field(default_factory=dict)
    coverage: dict[str, Any] = Field(default_factory=dict)
    provider_summary: dict[str, Any] = Field(default_factory=dict)
    errors: list[CompanyV2Error] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    diagnosis: dict[str, Any] = Field(default_factory=dict)
    agent_summary: dict[str, Any] = Field(default_factory=dict)
    validation_summary: dict[str, Any] = Field(default_factory=dict)
    validation_checks: list[dict[str, Any]] = Field(default_factory=list)
    debug: CompanyV2DebugMeta = Field(default_factory=CompanyV2DebugMeta)
