"""Fusion layer between structured financial data and official report evidence."""
from __future__ import annotations

import json
import hashlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any

from app.core.config import settings
from app.models.company_v2_financial_evidence_fusion import (
    FinancialEvidenceFusionRecord,
    FinancialEvidenceFusionSnapshot,
)
from app.services.company_v2_financial_fusion_cache import company_v2_financial_fusion_cache
from app.services.company_v2_financial_fusion_circuit_breaker import company_v2_financial_fusion_circuit_breaker
from app.services.company_v2_financial_fusion_health_service import company_v2_financial_fusion_health_service
from app.services.company_v2_financial_fusion_metrics import company_v2_financial_fusion_metrics
from app.services.company_v2_financial_fusion_review_queue import company_v2_financial_fusion_review_queue
from app.services.company_v2_financial_fusion_rollout_service import company_v2_financial_fusion_rollout_service
from app.services.company_v2_financial_fusion_singleflight import company_v2_financial_fusion_singleflight
from app.services.company_v2_financial_evidence_alignment import align_financial_evidence
from app.services.company_v2_financial_evidence_tolerance import within_tolerance
from app.services.company_v2_financial_field_definition_registry import get_field_definition, get_field_profile
from app.services.company_v2_financial_unit_normalizer import normalize_financial_value
from app.services.company_v2_official_financial_evidence_resolver import resolve_official_financial_evidence


DEFAULT_FUSION_FIELDS = [
    "revenue",
    "net_profit",
    "net_profit_parent",
    "operating_cashflow",
    "total_assets",
    "equity_parent",
    "eps_basic",
    "roe_weighted",
    "total_share",
    "float_share",
]

FIELD_MODULE_MAP = {
    "revenue": "profitability",
    "net_profit": "profitability",
    "net_profit_parent": "profitability",
    "operating_cashflow": "cashflow_quality",
    "total_assets": "solvency",
    "equity_parent": "solvency",
    "eps_basic": "profitability",
    "roe_weighted": "profitability",
    "total_share": "solvency",
    "float_share": "solvency",
}

FIELD_PROVIDER_NAME_MAP = {
    "revenue": "MBRevenue",
    "net_profit": "netProfit",
    "net_profit_parent": "netProfit",
    "operating_cashflow": "operating_cashflow",
    "total_assets": "total_assets",
    "equity_parent": "equity_parent",
    "eps_basic": "eps_basic",
    "roe_weighted": "roeAvg",
    "total_share": "totalShare",
    "float_share": "liqaShare",
}

FIELD_PROVIDER_DEFINITION_MAP = {
    "revenue": "main_business_revenue",
    "net_profit": "net_profit",
    "net_profit_parent": "net_profit",
    "operating_cashflow": "operating_cashflow",
    "total_assets": "total_assets",
    "equity_parent": "equity_parent",
    "eps_basic": "eps_basic",
    "roe_weighted": "roe",
    "total_share": "total_share",
    "float_share": "float_share",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _version_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _file_version(path: str | Path | None) -> str:
    if not path:
        return "none"
    candidate = Path(path)
    try:
        stat = candidate.stat()
        payload = f"{candidate}:{stat.st_mtime_ns}:{stat.st_size}"
    except Exception:
        payload = str(candidate)
    return _version_hash(payload)


def _structured_data_version(seed_path: str | None) -> str:
    return _file_version(seed_path) if seed_path else getattr(settings, "company_v2_financial_fusion_structured_data_version", "v1")


def _field_definition_registry_version() -> str:
    return getattr(settings, "company_v2_financial_fusion_field_definition_registry_version", "v1")


def _tolerance_version() -> str:
    return getattr(settings, "company_v2_financial_fusion_tolerance_version", "v1")


def _embedding_version(report_id: int) -> str:
    try:
        from app.services.company_v2_report_rag_index_service import company_v2_report_rag_index_service

        status = company_v2_report_rag_index_service.status(report_id)
        return str(status.get("embedding_version") or "none")
    except Exception:
        return "none"


def _cache_context(
    *,
    symbol: str,
    report_id: int,
    pdf_hash: str | None,
    parse_version: str | None,
    seed_path: str | None,
    fields: list[str],
    embedding_version: str | None = None,
) -> dict[str, str]:
    structured_version = _structured_data_version(seed_path)
    # Phase 6T-J2: the extractor/unit-normalization version participates in the
    # cache key so pre-fix cached results are invalidated automatically.
    from app.services.company_v2_official_field_extractor import OFFICIAL_EXTRACTOR_VERSION

    resolved_embedding_version = embedding_version or _embedding_version(report_id)

    versioned_parse = f"{parse_version or ''}+{OFFICIAL_EXTRACTOR_VERSION}"
    return {
        "cache_key": company_v2_financial_fusion_cache.build_key(
            symbol=symbol,
            report_id=report_id,
            pdf_hash=pdf_hash,
            parse_version=versioned_parse,
            embedding_version=resolved_embedding_version,
            structured_data_version=structured_version,
            field_definition_registry_version=_field_definition_registry_version(),
            tolerance_version=_tolerance_version(),
            selected_fields=fields,
        ),
        "structured_data_version": structured_version,
        "embedding_version": resolved_embedding_version,
        "field_definition_registry_version": _field_definition_registry_version(),
        "tolerance_version": _tolerance_version(),
        "official_extractor_version": OFFICIAL_EXTRACTOR_VERSION,
        "seed_path": seed_path or "",
    }


def _artifact_paths(symbol: str) -> list[Path]:
    base = _repo_root() / "backend" / "docs" / "artifacts"
    if not base.exists():
        return []
    patterns = [
        f"company_v2_{symbol}_ai_official_verification*.json",
        f"company_v2_{symbol}_official_verification*.json",
    ]
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(sorted(base.glob(pattern)))
    return paths


def _load_seed(symbol: str, report_id: int, report_year: int | None) -> dict[str, Any] | None:
    for path in _artifact_paths(symbol):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if int(data.get("report_id") or -1) != int(report_id):
            continue
        if report_year and int(data.get("report_year") or -1) != int(report_year):
            continue
        fields = data.get("fields") or {}
        if not fields:
            continue
        return {"path": path, "raw": data, "fields": fields}
    return None


def _normalize_unit_for_field(field_name: str) -> str | None:
    profile = get_field_profile(field_name)
    return profile.get("expected_unit")


def _provider_period(field_name: str, seed_item: dict[str, Any], report_year: int | None) -> str | None:
    period = seed_item.get("structured_period") or seed_item.get("provider_period")
    if period:
        return str(period)
    if report_year is not None:
        if field_name in {"total_share", "float_share"}:
            return f"{report_year}-12-31"
        return f"{report_year}-12-31"
    return None


def _provider_definition(field_name: str, seed_item: dict[str, Any]) -> str | None:
    if seed_item.get("provider_definition"):
        return str(seed_item["provider_definition"])
    if field_name == "revenue":
        reason = str(seed_item.get("reason") or "")
        if "main business revenue" in reason or "主营业务收入" in reason:
            return "main_business_revenue"
    return FIELD_PROVIDER_DEFINITION_MAP.get(field_name) or field_name


def _provider_value_basis(field_name: str, seed_item: dict[str, Any]) -> str | None:
    if seed_item.get("value_basis"):
        return str(seed_item["value_basis"])
    profile = get_field_profile(field_name)
    return str(profile.get("value_basis") or "unknown")


def _official_definition(field_name: str, resolver_result: dict[str, Any], seed_item: dict[str, Any]) -> str | None:
    candidate = resolver_result.get("candidate") or {}
    if candidate.get("definition"):
        return str(candidate["definition"])
    if seed_item.get("field_definition"):
        return str(seed_item["field_definition"])
    definition = get_field_definition(field_name)
    return definition.canonical_name if definition else field_name


def _official_value_basis(field_name: str, resolver_result: dict[str, Any], seed_item: dict[str, Any]) -> str | None:
    candidate = resolver_result.get("candidate") or {}
    if candidate.get("value_basis"):
        return str(candidate["value_basis"])
    if field_name in {"total_share", "float_share", "equity_parent", "total_assets"}:
        return "point_in_time"
    if seed_item.get("value_basis"):
        return str(seed_item["value_basis"])
    return "annual_cumulative"


def _field_status_from_seed(field_name: str, seed_item: dict[str, Any]) -> str | None:
    return str(seed_item.get("status") or "") or None


def _confidence_from_seed(seed_item: dict[str, Any], official_result: dict[str, Any]) -> float:
    confidence = seed_item.get("confidence")
    if confidence is None:
        confidence = (official_result.get("candidate") or {}).get("score", 0.5)
    try:
        return float(confidence)
    except Exception:
        return 0.5


def _module_for_field(field_name: str) -> str:
    return FIELD_MODULE_MAP.get(field_name, "profitability")


def _diff(left: float | None, right: float | None) -> tuple[float | None, float | None]:
    if left is None or right is None:
        return None, None
    abs_diff = abs(float(left) - float(right))
    denom = max(abs(float(left)), abs(float(right)), 1e-12)
    rel_diff = abs_diff / denom
    return abs_diff, rel_diff


def _elapsed_ms(start: float, end: float) -> float:
    return max((end - start) * 1000.0, 0.0)


def _same_definition(field_name: str, provider_definition: str | None, official_definition: str | None) -> bool:
    if provider_definition is None or official_definition is None:
        return False
    profile = get_field_profile(field_name)
    incompatible = set(profile.get("incompatible_definitions", [])) | set(profile.get("incompatible_with", []))
    if provider_definition in incompatible or official_definition in incompatible:
        return False

    canonical = str(profile.get("canonical_name") or field_name)
    aliases = set(profile.get("aliases", [])) | set(profile.get("official_report_labels", []))
    providers = set(profile.get("provider_labels", [])) | {profile.get("key"), field_name}

    if provider_definition == official_definition:
        return True
    if provider_definition in providers and official_definition in aliases | {canonical, field_name}:
        return True
    if official_definition in providers and provider_definition in aliases | {canonical, field_name}:
        return True
    if provider_definition == field_name and official_definition in {canonical, *aliases}:
        return True
    if official_definition == field_name and provider_definition in providers | aliases | {canonical}:
        return True
    return False


def _load_structured_seed(
    symbol: str,
    report_id: int,
    report_year: int | None,
    report_type: str | None,
) -> dict[str, Any]:
    seed = _load_seed(symbol, report_id, report_year)
    if not seed:
        return {"source_mode": "unavailable", "fields": {}, "seed_path": None, "report_year": report_year, "report_type": report_type}
    fields: dict[str, Any] = {}
    for field_name, item in seed["fields"].items():
        fields[field_name] = {
            "value": item.get("structured_value"),
            "unit": _normalize_unit_for_field(field_name),
            "provider_definition": _provider_definition(field_name, item),
            "provider_period": _provider_period(field_name, item, report_year or seed["raw"].get("report_year")),
            "value_basis": _provider_value_basis(field_name, item),
            "provider_name": FIELD_PROVIDER_NAME_MAP.get(field_name),
            "confidence": item.get("confidence", 0.75),
            "reason": item.get("reason"),
            "field_status": item.get("status"),
            "field_definition_match": item.get("field_definition_match"),
            "structured_period": item.get("structured_period"),
            "official_period_seed": item.get("official_period"),
            "source_trace": {
                "source": "artifact_seed",
                "artifact_path": str(seed["path"]),
                "field_name": field_name,
            },
        }
    return {
        "source_mode": "artifact_seed",
        "fields": fields,
        "seed_path": str(seed["path"]),
        "structured_data_version": _structured_data_version(str(seed["path"])),
        "report_year": report_year or seed["raw"].get("report_year"),
        "report_type": report_type or seed["raw"].get("report_type"),
        "warnings": seed["raw"].get("warnings") or [],
    }


def _fuse_field(
    *,
    symbol: str,
    report_id: int,
    report_year: int,
    report_type: str,
    field_name: str,
    structured: dict[str, Any] | None,
    official_result: dict[str, Any],
) -> FinancialEvidenceFusionRecord:
    structured_value = structured.get("value") if structured else None
    structured_unit = structured.get("unit") if structured else None
    provider_definition = structured.get("provider_definition") if structured else None
    provider_period = structured.get("provider_period") if structured else None
    provider_value_basis = structured.get("value_basis") if structured else None
    provider_name = structured.get("provider_name") if structured else None
    official_candidate = official_result.get("candidate") or {}
    official_value = official_candidate.get("value")
    official_unit = official_candidate.get("unit")
    official_definition = _official_definition(field_name, official_result, structured or {})
    official_period = official_candidate.get("period") or structured.get("official_period_seed") if structured else None
    official_value_basis = _official_value_basis(field_name, official_result, structured or {})
    official_page = official_candidate.get("page")
    official_chunk_id = official_candidate.get("chunk_id")
    official_excerpt = official_candidate.get("excerpt")
    official_source_url = official_candidate.get("source_url")

    structured_unit = structured_unit or _normalize_unit_for_field(field_name)
    provider_unit = structured_unit

    alignment = align_financial_evidence(
        symbol=symbol,
        report_id=report_id,
        report_year=report_year,
        report_type=report_type,
        field_name=field_name,
        provider_definition=provider_definition,
        provider_period=provider_period,
        provider_value_basis=provider_value_basis,
        provider_unit=provider_unit,
        official_definition=official_definition,
        official_period=official_period,
        official_value_basis=official_value_basis,
        official_unit=official_unit,
    )

    normalized_provider = normalize_financial_value(structured_value, provider_unit, target_unit=provider_unit)
    normalized_official = normalize_financial_value(official_value, official_unit, target_unit=provider_unit)
    tolerance = within_tolerance(field_name, normalized_provider.get("normalized_value"), normalized_official.get("normalized_value"))
    abs_diff, rel_diff = _diff(normalized_provider.get("normalized_value"), normalized_official.get("normalized_value"))
    same_definition = _same_definition(field_name, provider_definition, official_definition)
    same_period = bool(provider_period and official_period and str(provider_period) == str(official_period))
    unit_different = str(provider_unit or "") != str(official_unit or "")
    # Phase 6T-J2 hard guard: when the official evidence unit context is
    # unknown/incomplete while the structured unit is known, a raw官方数值
    # must never be compared against a CNY structured value — value_conflict
    # is forbidden; classify as unit_mismatch instead.
    official_unit_unknown = bool(
        structured_unit
        and (
            official_candidate.get("unit_source") == "unknown"
            or official_candidate.get("classification_hint") == "unit_context_missing"
            or (official_value is not None and official_unit is None)
        )
    )
    if structured_value is None and official_value is None:
        fusion_status = "insufficient_evidence"
    elif structured_value is None:
        fusion_status = "structured_field_missing"
    elif official_value is None:
        fusion_status = "insufficient_evidence"
    elif not same_definition:
        fusion_status = "definition_mismatch"
    elif not same_period:
        fusion_status = "period_basis_mismatch"
    elif official_unit_unknown:
        fusion_status = "unit_mismatch"
    elif not alignment.get("unit_convertible", False):
        fusion_status = "unit_mismatch"
    elif tolerance.get("within_tolerance"):
        fusion_status = "normalized_match" if unit_different else "verified"
    else:
        fusion_status = "likely_match" if float(official_candidate.get("score") or 0.0) < 0.75 else "value_conflict"

    confidence = _confidence_from_seed(structured or {}, official_result)
    if fusion_status == "verified":
        confidence = max(confidence, 0.95)
    elif fusion_status == "normalized_match":
        confidence = max(confidence, 0.92)
    elif fusion_status == "likely_match":
        confidence = min(confidence, 0.75)
    elif fusion_status == "value_conflict":
        confidence = min(confidence, 0.7)
    elif fusion_status in {"definition_mismatch", "period_basis_mismatch", "unit_mismatch"}:
        confidence = min(confidence, 0.85)
    elif fusion_status in {"structured_field_missing", "insufficient_evidence"}:
        confidence = min(confidence, 0.6)

    warnings = list(alignment.get("warnings") or [])
    if structured and structured.get("reason"):
        warnings.append(str(structured["reason"]))
    if official_result.get("warnings"):
        warnings.extend([str(item) for item in official_result.get("warnings") or []])
    if fusion_status == "period_basis_mismatch" and official_period and provider_period:
        warnings.append(f"period mismatch: provider={provider_period} official={official_period}")
    if fusion_status == "definition_mismatch":
        warnings.append("definition mismatch between structured and official evidence")
    if official_unit_unknown and fusion_status == "unit_mismatch":
        warnings.append("official unit context missing/unknown — value comparison refused (no default 元 guess)")
    if fusion_status == "normalized_match":
        warnings.append("units normalized successfully")
    if fusion_status == "insufficient_evidence":
        warnings.append("official evidence not sufficient")

    source_trace = {
        "structured": structured.get("source_trace") if structured else None,
        "official": {
            "status": official_result.get("status"),
            "retrieval_mode": official_result.get("retrieval_mode"),
            "page": official_page,
            "chunk_id": official_chunk_id,
            "excerpt": official_excerpt,
            "source_url": official_source_url,
            "raw_value": official_candidate.get("raw_value"),
            "raw_unit": official_candidate.get("raw_unit"),
            "normalized_value": normalized_official.get("normalized_value"),
            "normalized_unit": normalized_official.get("normalized_unit"),
            "unit_scale": official_candidate.get("unit_scale"),
            "unit_source": official_candidate.get("unit_source"),
            "table_title": official_candidate.get("table_title"),
            "evidence_page": official_candidate.get("evidence_page") or official_page,
            "table_scope_id": official_candidate.get("table_scope_id"),
        },
        "alignment": alignment,
        "normalization": {
            "provider": normalized_provider,
            "official": normalized_official,
            "tolerance": tolerance,
        },
    }

    return FinancialEvidenceFusionRecord(
        id=0,
        market="CN",
        symbol=symbol,
        report_id=report_id,
        report_year=report_year,
        report_type=report_type,
        module=_module_for_field(field_name),
        field_name=field_name,
        provider_name=provider_name,
        provider_value=structured_value,
        provider_unit=provider_unit,
        provider_definition=provider_definition,
        provider_period=provider_period,
        provider_value_basis=provider_value_basis,
        official_value=official_value,
        official_unit=official_unit,
        official_definition=official_definition,
        official_period=official_period,
        official_value_basis=official_value_basis,
        official_page=official_page,
        official_chunk_id=official_chunk_id,
        official_excerpt=official_excerpt,
        normalized_provider_value=normalized_provider.get("normalized_value"),
        normalized_official_value=normalized_official.get("normalized_value"),
        absolute_diff=abs_diff,
        relative_diff=rel_diff,
        tolerance=tolerance.get("absolute_tolerance"),
        fusion_status=fusion_status,
        confidence=confidence,
        warnings_json=warnings,
        source_trace_json=source_trace,
    )


@dataclass(slots=True)
class _FusionState:
    snapshot: FinancialEvidenceFusionSnapshot
    records: dict[str, FinancialEvidenceFusionRecord] = field(default_factory=dict)


class CompanyV2FinancialEvidenceFusionRepository:
    def __init__(self) -> None:
        self._states: dict[int, _FusionState] = {}

    def get(self, report_id: int) -> FinancialEvidenceFusionSnapshot | None:
        state = self._states.get(int(report_id))
        return state.snapshot if state else None

    def get_field(self, report_id: int, field_name: str) -> FinancialEvidenceFusionRecord | None:
        state = self._states.get(int(report_id))
        if not state:
            return None
        return state.records.get(field_name)

    def set(self, snapshot: FinancialEvidenceFusionSnapshot, records: list[FinancialEvidenceFusionRecord]) -> FinancialEvidenceFusionSnapshot:
        for idx, record in enumerate(records, start=1):
            record.id = idx  # type: ignore[misc]
        state = _FusionState(snapshot=snapshot, records={record.field_name: record for record in records})
        self._states[snapshot.report_id] = state
        return snapshot

    def clear(self) -> None:
        self._states.clear()


company_v2_financial_evidence_fusion_repository = CompanyV2FinancialEvidenceFusionRepository()


class CompanyV2FinancialEvidenceFusionService:
    def __init__(self, repository: CompanyV2FinancialEvidenceFusionRepository | None = None) -> None:
        self.repository = repository or company_v2_financial_evidence_fusion_repository

    def _load_structured(self, symbol: str, report_id: int, report_year: int | None, report_type: str | None) -> dict[str, Any]:
        return _load_structured_seed(symbol, report_id, report_year, report_type)

    def _make_cache_context(
        self,
        *,
        symbol: str,
        report_id: int,
        pdf_hash: str | None,
        parse_version: str | None,
        seed_path: str | None,
        selected_fields: list[str],
        embedding_version: str | None = None,
    ) -> dict[str, str]:
        return _cache_context(
            symbol=symbol,
            report_id=report_id,
            pdf_hash=pdf_hash,
            parse_version=parse_version,
            seed_path=seed_path,
            fields=selected_fields,
            embedding_version=embedding_version,
        )

    def _current_records(self, report_id: int, selected_fields: list[str]) -> list[FinancialEvidenceFusionRecord]:
        records = []
        for field in selected_fields:
            record = self.repository.get_field(report_id, field)
            if record:
                records.append(record)
        return records

    def _maybe_enqueue_review(self, records: list[FinancialEvidenceFusionRecord]) -> None:
        for record in records:
            item = company_v2_financial_fusion_review_queue.maybe_enqueue_from_record(asdict(record))
            if item and record.fusion_status == "value_conflict":
                company_v2_financial_fusion_metrics.inc("fusion_false_conflict_suspected_total")

    def _update_metrics(self, snapshot: FinancialEvidenceFusionSnapshot, *, cache_hit: bool, latency_ms: float, eligible: bool, timed_out: bool = False, ineligible: bool = False) -> None:
        company_v2_financial_fusion_metrics.inc("fusion_requests_total")
        if eligible:
            company_v2_financial_fusion_metrics.inc("fusion_eligible_total")
        else:
            company_v2_financial_fusion_metrics.inc("fusion_ineligible_total")
        if cache_hit:
            company_v2_financial_fusion_metrics.inc("fusion_cache_hits_total")
        else:
            company_v2_financial_fusion_metrics.inc("fusion_cache_misses_total")
        if timed_out:
            company_v2_financial_fusion_metrics.inc("fusion_timeout_total")
        if snapshot.failed:
            company_v2_financial_fusion_metrics.inc("fusion_failed_total")
        elif snapshot.verified or snapshot.normalized_match or snapshot.definition_mismatch or snapshot.period_basis_mismatch:
            if snapshot.value_conflict:
                company_v2_financial_fusion_metrics.inc("fusion_partial_total")
            else:
                company_v2_financial_fusion_metrics.inc("fusion_success_total")
        else:
            company_v2_financial_fusion_metrics.inc("fusion_partial_total")

        company_v2_financial_fusion_metrics.inc("fusion_fields_total", snapshot.fields_total)
        company_v2_financial_fusion_metrics.inc("fusion_verified_total", snapshot.verified)
        company_v2_financial_fusion_metrics.inc("fusion_normalized_match_total", snapshot.normalized_match)
        company_v2_financial_fusion_metrics.inc("fusion_definition_mismatch_total", snapshot.definition_mismatch)
        company_v2_financial_fusion_metrics.inc("fusion_period_basis_mismatch_total", snapshot.period_basis_mismatch)
        company_v2_financial_fusion_metrics.inc("fusion_unit_mismatch_total", snapshot.unit_mismatch)
        company_v2_financial_fusion_metrics.inc("fusion_value_conflict_total", snapshot.value_conflict)
        company_v2_financial_fusion_metrics.inc("fusion_structured_missing_total", snapshot.structured_field_missing)
        company_v2_financial_fusion_metrics.inc("fusion_official_missing_total", snapshot.official_field_not_found)
        company_v2_financial_fusion_metrics.inc("fusion_insufficient_evidence_total", snapshot.insufficient_evidence)
        company_v2_financial_fusion_metrics.observe_latency("fusion_latency_ms", latency_ms)

    def _observe_latency_segments(self, segments: dict[str, float | None]) -> None:
        for key, value in segments.items():
            if value is None:
                continue
            company_v2_financial_fusion_metrics.observe_latency(key, float(value))
        total_latency = segments.get("total_latency_ms")
        if total_latency is not None:
            company_v2_financial_fusion_metrics.observe_latency("fusion_latency_ms", float(total_latency))

    def _snapshot_meta(
        self,
        *,
        cache_context: dict[str, str],
        cached: bool,
        source_url: str | None,
        pdf_hash: str | None,
        parse_version: str | None,
        idempotency_key: str | None,
        rollout: dict[str, Any],
        eligible: bool,
        reason: str,
    ) -> dict[str, Any]:
        return {
            "cache_hit": cached,
            "cache_key_version": getattr(settings, "company_v2_financial_fusion_cache_version", "v1"),
            "computed_at": None,
            "expires_at": None,
            "stale_reason": None,
            "cache_context": cache_context,
            "source_url": source_url,
            "pdf_hash": pdf_hash,
            "parse_version": parse_version,
            "idempotency_key": idempotency_key,
            "rollout": rollout,
            "eligible": eligible,
            "reason": reason,
        }

    def run(
        self,
        *,
        market: str,
        symbol: str,
        report_id: int,
        report_year: int,
        report_type: str,
        fields: list[str] | None = None,
        refresh: bool = False,
        sidecar_path: str | Path | None = None,
        source_url: str | None = None,
        pdf_hash: str | None = None,
        parse_version: str | None = None,
        embedding_version: str | None = None,
        structured_data_version: str | None = None,
        field_definition_registry_version: str | None = None,
        tolerance_version: str | None = None,
        report_ready: bool = True,
        rag_ready: bool = True,
        structured_ready: bool = True,
        enforce_rollout: bool = False,
        force_enabled: bool = False,
        idempotency_key: str | None = None,
        request_id: str | None = None,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        selected_fields = list(fields or DEFAULT_FUSION_FIELDS)
        total_start = perf_counter()
        timings: dict[str, float] = {}

        max_fields = int(getattr(settings, "company_v2_financial_fusion_max_fields_per_request", 10))
        if len(selected_fields) > max_fields:
            timings["total_latency_ms"] = _elapsed_ms(total_start, perf_counter())
            self._observe_latency_segments(timings)
            company_v2_financial_fusion_metrics.inc("fusion_requests_total")
            company_v2_financial_fusion_metrics.inc("fusion_ineligible_total")
            return {
                "ok": False,
                "status": "failed",
                "reason": "TOO_MANY_FIELDS",
                "error_code": "TOO_MANY_FIELDS",
                "max_fields": max_fields,
                "requested_fields": len(selected_fields),
                "symbol": symbol,
                "report_id": report_id,
                "report_year": report_year,
                "report_type": report_type,
                "summary": {},
                "fields": [],
                "timings": dict(timings),
            }

        field_definition_registry_version = field_definition_registry_version or _field_definition_registry_version()
        tolerance_version = tolerance_version or _tolerance_version()

        fast_snapshot = self.repository.get(report_id) if not refresh else None
        fast_records = self._current_records(report_id, selected_fields) if fast_snapshot else []
        fast_ready = bool(
            fast_snapshot
            and fast_snapshot.report_year == report_year
            and fast_snapshot.report_type == report_type
            and fast_snapshot.selected_fields
            and set(fast_snapshot.selected_fields) == set(selected_fields)
            and len(fast_records) == len(selected_fields)
        )
        fast_cache_context: dict[str, str] | None = None
        if fast_ready:
            fast_cache_context = dict(fast_snapshot.cache_context or {})
            seed_path = fast_snapshot.seed_path or fast_cache_context.get("seed_path")
            fast_cache_context = self._make_cache_context(
                symbol=symbol,
                report_id=report_id,
                pdf_hash=pdf_hash,
                parse_version=parse_version,
                seed_path=seed_path,
                selected_fields=selected_fields,
                embedding_version=fast_cache_context.get("embedding_version") if fast_cache_context else embedding_version,
            )
            if fast_cache_context.get("seed_path"):
                fast_cache_context["seed_path"] = str(fast_cache_context["seed_path"])
            if fast_snapshot.cache_context and fast_snapshot.cache_context.get("cache_key") == fast_cache_context.get("cache_key"):
                cached = company_v2_financial_fusion_cache.get(fast_cache_context["cache_key"])
                if cached:
                    payload = dict(cached.data)
                    payload["cache_hit"] = True
                    payload["computed_at"] = cached.computed_at
                    payload["expires_at"] = cached.expires_at
                    payload["stale_reason"] = cached.stale_reason
                else:
                    payload = self._snapshot_to_json(fast_snapshot, fast_records)
                    payload.update(
                        self._snapshot_meta(
                            cache_context=fast_cache_context,
                            cached=True,
                            source_url=source_url,
                            pdf_hash=pdf_hash,
                            parse_version=parse_version,
                            idempotency_key=idempotency_key,
                            rollout=company_v2_financial_fusion_rollout_service.evaluate(
                                symbol=symbol,
                                report_id=report_id,
                                report_ready=report_ready,
                                rag_ready=rag_ready,
                                structured_ready=structured_ready,
                                cached=True,
                                last_run_at=fast_snapshot.generated_at,
                                force_enabled=force_enabled,
                                supported_fields=selected_fields,
                            ),
                            eligible=True,
                            reason="CACHE_REPOSITORY_FAST_PATH",
                        )
                    )
                timings["eligibility_latency_ms"] = 0.0
                timings["cache_lookup_latency_ms"] = _elapsed_ms(total_start, perf_counter())
                timings["cache_hit_latency_ms"] = timings["cache_lookup_latency_ms"]
                timings["computed_latency_ms"] = 0.0
                timings["waiting_on_singleflight_ms"] = 0.0
                timings["singleflight_reuse_latency_ms"] = 0.0
                timings["retrieval_latency_ms"] = 0.0
                timings["resolver_latency_ms"] = 0.0
                timings["alignment_latency_ms"] = 0.0
                timings["persistence_latency_ms"] = 0.0
                timings["total_latency_ms"] = _elapsed_ms(total_start, perf_counter())
                payload["timings"] = dict(timings)
                payload["cache_context"] = fast_cache_context
                self._observe_latency_segments(timings)
                self._update_metrics(
                    fast_snapshot,
                    cache_hit=True,
                    latency_ms=float(timings["total_latency_ms"]),
                    eligible=True,
                )
                return payload

        structured_seed = self._load_structured(symbol, report_id, report_year, report_type)
        structured_data_version = structured_data_version or structured_seed.get("structured_data_version") or self._make_cache_context(
            symbol=symbol,
            report_id=report_id,
            pdf_hash=pdf_hash,
            parse_version=parse_version,
            seed_path=structured_seed.get("seed_path"),
            selected_fields=selected_fields,
            embedding_version=embedding_version,
        )["structured_data_version"]
        embedding_version = embedding_version or _embedding_version(report_id)
        cache_context = self._make_cache_context(
            symbol=symbol,
            report_id=report_id,
            pdf_hash=pdf_hash,
            parse_version=parse_version,
            seed_path=structured_seed.get("seed_path"),
            selected_fields=selected_fields,
            embedding_version=embedding_version,
        )
        eligibility_start = perf_counter()
        rollout = company_v2_financial_fusion_rollout_service.evaluate(
            symbol=symbol,
            report_id=report_id,
            report_ready=report_ready,
            rag_ready=rag_ready,
            structured_ready=structured_ready and structured_seed.get("source_mode") != "unavailable",
            cached=False,
            last_run_at=self.repository.get(report_id).generated_at if self.repository.get(report_id) else None,
            force_enabled=force_enabled,
            supported_fields=selected_fields,
        )
        timings["eligibility_latency_ms"] = _elapsed_ms(eligibility_start, perf_counter())

        if not company_v2_financial_fusion_circuit_breaker.allow():
            cached = company_v2_financial_fusion_cache.get(cache_context["cache_key"])
            if cached:
                payload = dict(cached.data)
                payload["circuit"] = company_v2_financial_fusion_circuit_breaker.snapshot()
                payload["status"] = payload.get("status") or "cached"
                timings["cache_lookup_latency_ms"] = 0.0
                timings["computed_latency_ms"] = 0.0
                timings["waiting_on_singleflight_ms"] = 0.0
                timings["singleflight_reuse_latency_ms"] = 0.0
                timings["retrieval_latency_ms"] = 0.0
                timings["resolver_latency_ms"] = 0.0
                timings["alignment_latency_ms"] = 0.0
                timings["persistence_latency_ms"] = 0.0
                timings["cache_hit_latency_ms"] = _elapsed_ms(total_start, perf_counter())
                timings["total_latency_ms"] = timings["cache_hit_latency_ms"]
                payload["timings"] = dict(timings)
                self._observe_latency_segments(timings)
                return payload
            timings["total_latency_ms"] = _elapsed_ms(total_start, perf_counter())
            self._observe_latency_segments(timings)
            company_v2_financial_fusion_metrics.inc("fusion_requests_total")
            company_v2_financial_fusion_metrics.inc("fusion_ineligible_total")
            return {
                "ok": False,
                "status": "blocked",
                "reason": "CIRCUIT_OPEN",
                "circuit": company_v2_financial_fusion_circuit_breaker.snapshot(),
                "rollout": rollout,
                "cache_hit": False,
                "symbol": symbol,
                "report_id": report_id,
                "report_year": report_year,
                "report_type": report_type,
                "summary": {},
                "fields": [],
                "timings": dict(timings),
            }

        if enforce_rollout and not rollout["eligible"]:
            timings["total_latency_ms"] = _elapsed_ms(total_start, perf_counter())
            self._observe_latency_segments(timings)
            company_v2_financial_fusion_metrics.inc("fusion_requests_total")
            company_v2_financial_fusion_metrics.inc("fusion_ineligible_total")
            return {
                "ok": False,
                "status": "ineligible",
                "reason": rollout["reason"],
                "rollout": rollout,
                "cache_hit": False,
                "cache_key_version": getattr(settings, "company_v2_financial_fusion_cache_version", "v1"),
                "computed_at": None,
                "expires_at": None,
                "stale_reason": rollout["reason"],
                "symbol": symbol,
                "report_id": report_id,
                "report_year": report_year,
                "report_type": report_type,
                "summary": {},
                "fields": [],
                "timings": dict(timings),
            }

        cache_entry = None
        cache_key = cache_context["cache_key"]
        cache_lookup_start = perf_counter()
        if not refresh:
            cache_entry = company_v2_financial_fusion_cache.get(cache_key)
        timings["cache_lookup_latency_ms"] = _elapsed_ms(cache_lookup_start, perf_counter())
        if cache_entry:
            payload = dict(cache_entry.data)
            payload["cache_hit"] = True
            payload["computed_at"] = cache_entry.computed_at
            payload["expires_at"] = cache_entry.expires_at
            payload["stale_reason"] = cache_entry.stale_reason
            timings["cache_hit_latency_ms"] = timings["cache_lookup_latency_ms"]
            timings["computed_latency_ms"] = 0.0
            timings["waiting_on_singleflight_ms"] = 0.0
            timings["singleflight_reuse_latency_ms"] = 0.0
            timings["retrieval_latency_ms"] = 0.0
            timings["resolver_latency_ms"] = 0.0
            timings["alignment_latency_ms"] = 0.0
            timings["persistence_latency_ms"] = 0.0
            timings["total_latency_ms"] = _elapsed_ms(total_start, perf_counter())
            payload["timings"] = dict(timings)
            self._observe_latency_segments(timings)
            self._update_metrics(
                FinancialEvidenceFusionSnapshot(
                        symbol=symbol,
                        report_id=report_id,
                        report_year=report_year,
                        report_type=report_type,
                        fields_total=len(payload.get("fields") or []),
                        verified=int(payload.get("summary", {}).get("verified", 0)),
                        normalized_match=int(payload.get("summary", {}).get("normalized_match", 0)),
                        likely_match=int(payload.get("summary", {}).get("likely_match", 0)),
                        definition_mismatch=int(payload.get("summary", {}).get("definition_mismatch", 0)),
                        period_basis_mismatch=int(payload.get("summary", {}).get("period_basis_mismatch", 0)),
                        unit_mismatch=int(payload.get("summary", {}).get("unit_mismatch", 0)),
                        value_conflict=int(payload.get("summary", {}).get("value_conflict", 0)),
                        structured_field_missing=int(payload.get("summary", {}).get("structured_field_missing", 0)),
                        official_field_not_found=int(payload.get("summary", {}).get("official_field_not_found", 0)),
                        insufficient_evidence=int(payload.get("summary", {}).get("insufficient_evidence", 0)),
                        not_applicable=int(payload.get("summary", {}).get("not_applicable", 0)),
                        failed=int(payload.get("summary", {}).get("failed", 0)),
                        fields=[],
                ),
                cache_hit=True,
                latency_ms=float(timings["total_latency_ms"]),
                eligible=True,
            )
            return payload

        if not enforce_rollout and self.repository.get(report_id) and not refresh:
            cached = self.repository.get(report_id)
            if cached and cached.report_year == report_year and cached.report_type == report_type:
                existing = self._current_records(report_id, selected_fields)
                if len(existing) == len(selected_fields):
                    payload = self._snapshot_to_json(cached, existing)
                    payload["cache_hit"] = True
                    timings["cache_hit_latency_ms"] = _elapsed_ms(total_start, perf_counter())
                    timings["computed_latency_ms"] = 0.0
                    timings["waiting_on_singleflight_ms"] = 0.0
                    timings["singleflight_reuse_latency_ms"] = 0.0
                    timings["retrieval_latency_ms"] = 0.0
                    timings["resolver_latency_ms"] = 0.0
                    timings["alignment_latency_ms"] = 0.0
                    timings["persistence_latency_ms"] = 0.0
                    timings["total_latency_ms"] = timings["cache_hit_latency_ms"]
                    payload["timings"] = dict(timings)
                    self._observe_latency_segments(timings)
                    payload.update(
                        self._snapshot_meta(
                            cache_context=cache_context,
                            cached=True,
                            source_url=source_url,
                            pdf_hash=pdf_hash,
                            parse_version=parse_version,
                            idempotency_key=idempotency_key,
                            rollout=rollout,
                            eligible=True,
                            reason=rollout["reason"],
                        )
                    )
                    return payload

        def _compute() -> dict[str, Any]:
            compute_start = perf_counter()
            records: list[FinancialEvidenceFusionRecord] = []
            summary = {
                "verified": 0,
                "normalized_match": 0,
                "likely_match": 0,
                "definition_mismatch": 0,
                "period_basis_mismatch": 0,
                "unit_mismatch": 0,
                "value_conflict": 0,
                "structured_field_missing": 0,
                "official_field_not_found": 0,
                "insufficient_evidence": 0,
                "not_applicable": 0,
                "failed": 0,
            }
            resolver_latency_ms = 0.0
            alignment_latency_ms = 0.0
            for field_name in selected_fields:
                structured = structured_seed.get("fields", {}).get(field_name)
                resolver_start = perf_counter()
                resolver = resolve_official_financial_evidence(
                    symbol=symbol,
                    report_id=report_id,
                    field_name=field_name,
                    provider_definition=(structured or {}).get("provider_definition") if structured else None,
                    provider_period=(structured or {}).get("provider_period") if structured else None,
                    provider_value_basis=(structured or {}).get("value_basis") if structured else None,
                    report_year=report_year,
                    report_type=report_type,
                    sidecar_path=sidecar_path,
                    source_url=source_url,
                )
                resolver_latency_ms += _elapsed_ms(resolver_start, perf_counter())
                fuse_start = perf_counter()
                record = _fuse_field(
                    symbol=symbol,
                    report_id=report_id,
                    report_year=report_year,
                    report_type=report_type,
                    field_name=field_name,
                    structured=structured,
                    official_result=resolver,
                )
                alignment_latency_ms += _elapsed_ms(fuse_start, perf_counter())
                summary[record.fusion_status] = summary.get(record.fusion_status, 0) + 1
                records.append(record)

            persistence_start = perf_counter()
            snapshot = FinancialEvidenceFusionSnapshot(
                symbol=symbol,
                report_id=report_id,
                report_year=report_year,
                report_type=report_type,
                fields_total=len(records),
                verified=summary["verified"],
                normalized_match=summary["normalized_match"],
                likely_match=summary["likely_match"],
                definition_mismatch=summary["definition_mismatch"],
                period_basis_mismatch=summary["period_basis_mismatch"],
                unit_mismatch=summary["unit_mismatch"],
                value_conflict=summary["value_conflict"],
                structured_field_missing=summary["structured_field_missing"],
                official_field_not_found=summary["official_field_not_found"],
                insufficient_evidence=summary["insufficient_evidence"],
                not_applicable=summary["not_applicable"],
                failed=summary["failed"],
                fields=records,
                refreshed=refresh,
                source_mode=structured_seed.get("source_mode", "artifact_seed"),
                selected_fields=list(selected_fields),
                cache_context=dict(cache_context),
                seed_path=structured_seed.get("seed_path"),
            )
            self.repository.set(snapshot, records)
            self._maybe_enqueue_review(records)
            payload = self._snapshot_to_json(snapshot, records)
            payload.update(
                self._snapshot_meta(
                    cache_context=cache_context,
                    cached=False,
                    source_url=source_url,
                    pdf_hash=pdf_hash,
                    parse_version=parse_version,
                    idempotency_key=idempotency_key,
                    rollout=rollout,
                    eligible=True,
                    reason=rollout["reason"],
                )
            )
            entry = company_v2_financial_fusion_cache.set(cache_key, payload)
            payload["computed_at"] = entry.computed_at
            payload["expires_at"] = entry.expires_at
            payload["stale_reason"] = entry.stale_reason
            timings.update(
                {
                    "resolver_latency_ms": resolver_latency_ms,
                    "retrieval_latency_ms": resolver_latency_ms,
                    "alignment_latency_ms": alignment_latency_ms,
                    "persistence_latency_ms": _elapsed_ms(persistence_start, perf_counter()),
                    "computed_latency_ms": _elapsed_ms(compute_start, perf_counter()),
                }
            )
            timings["total_latency_ms"] = _elapsed_ms(total_start, perf_counter())
            payload["timings"] = dict(timings)
            self._observe_latency_segments(timings)
            health = company_v2_financial_fusion_health_service.health()
            if health["status"] == "critical":
                company_v2_financial_fusion_circuit_breaker.trip("health_critical")
            return payload

        request_key = idempotency_key or cache_context["cache_key"]
        if enforce_rollout:
            try:
                singleflight_start = perf_counter()
                result = company_v2_financial_fusion_singleflight.run(request_key, _compute, request_id=request_id)
                singleflight_elapsed = _elapsed_ms(singleflight_start, perf_counter())
                timings["waiting_on_singleflight_ms"] = singleflight_elapsed if result.get("singleflight_status") == "reused" else 0.0
                timings["singleflight_reuse_latency_ms"] = singleflight_elapsed if result.get("singleflight_status") == "reused" else 0.0
                timings.setdefault("computed_latency_ms", singleflight_elapsed if result.get("singleflight_status") == "completed" else 0.0)
                timings.setdefault("retrieval_latency_ms", 0.0)
                timings.setdefault("resolver_latency_ms", 0.0)
                timings.setdefault("alignment_latency_ms", 0.0)
                timings.setdefault("persistence_latency_ms", 0.0)
                timings["total_latency_ms"] = _elapsed_ms(total_start, perf_counter())
                result_timings = dict(result.get("timings") or {})
                result_timings.update(timings)
                result["timings"] = result_timings
                self._observe_latency_segments(timings)
                result.setdefault("rollout", rollout)
                result.setdefault("cache_hit", False)
                return result
            finally:
                pass
        return _compute()

    def get(self, report_id: int) -> dict[str, Any]:
        snapshot = self.repository.get(report_id)
        if not snapshot:
            return {"status": "pending", "report_id": report_id, "fields": [], "summary": {}}
        records = [record for record in self.repository._states[report_id].records.values()]  # noqa: SLF001
        return self._snapshot_to_json(snapshot, records)

    def get_field(self, report_id: int, field_name: str) -> dict[str, Any]:
        record = self.repository.get_field(report_id, field_name)
        if not record:
            return {"status": "pending", "report_id": report_id, "field_name": field_name}
        return asdict(record)

    def _snapshot_to_json(self, snapshot: FinancialEvidenceFusionSnapshot, records: list[FinancialEvidenceFusionRecord]) -> dict[str, Any]:
        return {
            "symbol": snapshot.symbol,
            "report_id": snapshot.report_id,
            "report_year": snapshot.report_year,
            "report_type": snapshot.report_type,
            "summary": {
                "fields_total": snapshot.fields_total,
                "verified": snapshot.verified,
                "normalized_match": snapshot.normalized_match,
                "likely_match": snapshot.likely_match,
                "definition_mismatch": snapshot.definition_mismatch,
                "period_basis_mismatch": snapshot.period_basis_mismatch,
                "unit_mismatch": snapshot.unit_mismatch,
                "value_conflict": snapshot.value_conflict,
                "structured_field_missing": snapshot.structured_field_missing,
                "official_field_not_found": snapshot.official_field_not_found,
                "insufficient_evidence": snapshot.insufficient_evidence,
                "not_applicable": snapshot.not_applicable,
                "failed": snapshot.failed,
            },
            "fields": [asdict(record) for record in records],
            "generated_at": snapshot.generated_at,
            "refreshed": snapshot.refreshed,
            "source_mode": snapshot.source_mode,
        }


company_v2_financial_evidence_fusion_service = CompanyV2FinancialEvidenceFusionService()
