"""Company V2 financial evidence fusion records."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class FinancialEvidenceFusionRecord:
    id: int
    market: str
    symbol: str
    report_id: int
    report_year: int
    report_type: str
    module: str
    field_name: str
    provider_name: str | None
    provider_value: Any
    provider_unit: str | None
    provider_definition: str | None
    provider_period: str | None
    provider_value_basis: str | None
    official_value: Any
    official_unit: str | None
    official_definition: str | None
    official_period: str | None
    official_value_basis: str | None
    official_page: int | None
    official_chunk_id: int | None
    official_excerpt: str | None
    normalized_provider_value: Any
    normalized_official_value: Any
    absolute_diff: float | None
    relative_diff: float | None
    tolerance: float | None
    fusion_status: str
    confidence: float
    warnings_json: list[str] = field(default_factory=list)
    source_trace_json: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(slots=True)
class FinancialEvidenceFusionSnapshot:
    symbol: str
    report_id: int
    report_year: int
    report_type: str
    fields_total: int
    verified: int
    normalized_match: int
    likely_match: int
    definition_mismatch: int
    period_basis_mismatch: int
    unit_mismatch: int
    value_conflict: int
    structured_field_missing: int
    official_field_not_found: int
    insufficient_evidence: int
    not_applicable: int
    failed: int
    fields: list[FinancialEvidenceFusionRecord]
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    refreshed: bool = False
    source_mode: str = "artifact_fallback"
    selected_fields: list[str] = field(default_factory=list)
    cache_context: dict[str, Any] = field(default_factory=dict)
    seed_path: str | None = None


company_v2_financial_evidence_fusion = FinancialEvidenceFusionRecord
