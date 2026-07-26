from __future__ import annotations

from typing import Any

from app.schemas.company_v2_debug import CompanyV2DebugEnvelope


def _has_effective_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and value.strip() in ("", "—", "--", "nan", "NaN"):
        return False
    if isinstance(value, float) and value != value:
        return False
    return True


def diagnose_company_v2_envelope(
    envelope: CompanyV2DebugEnvelope | dict[str, Any],
    *,
    frontend_visible: bool | None = None,
) -> dict[str, Any]:
    data = envelope.model_dump() if isinstance(envelope, CompanyV2DebugEnvelope) else envelope
    module_key = data.get("module_key")
    source_chain = data.get("source_chain") or []
    raw = data.get("raw") or {}
    normalized = data.get("normalized") or {}
    render = data.get("render") or {}
    errors = data.get("errors") or []
    coverage = data.get("coverage") or {}
    field_trace = data.get("field_trace") or {}

    raw_rows = 0
    for source in source_chain:
        raw_rows += int(source.get("rows_count") or 0)
    if raw_rows <= 0:
        for value in raw.values():
            if isinstance(value, list):
                raw_rows += sum(int(item.get("rows_count") or 0) for item in value if isinstance(item, dict))
            elif isinstance(value, dict):
                raw_rows += int(value.get("rows_count") or 0)

    normalized_rows = normalized.get("rows") or []
    normalized_fields = normalized.get("fields") or {}
    core_fields = (render.get("visible_fields") or []) + (render.get("hidden_fields") or [])
    has_normalized_value = any(
        _has_effective_value(item.get("value") if isinstance(item, dict) else item)
        for item in normalized_fields.values()
    ) or any(
        _has_effective_value(v)
        for row in normalized_rows if isinstance(row, dict)
        for k, v in row.items() if not str(k).endswith("_source")
    )
    valid_fields_count = 0
    if normalized_fields:
        valid_fields_count = sum(
            1
            for item in normalized_fields.values()
            if _has_effective_value(item.get("value") if isinstance(item, dict) else item)
        )
    elif normalized_rows:
        valid_fields_count = sum(
            1
            for field in core_fields
            if any(isinstance(row, dict) and _has_effective_value(row.get(field)) for row in normalized_rows)
        )

    provider_attempts = [s for s in source_chain if s.get("provider") != "cache"]
    timeout_count = sum(1 for s in provider_attempts if s.get("error_code") == "PROVIDER_TIMEOUT" or s.get("status") == "timeout")
    success_count = sum(1 for s in provider_attempts if s.get("success"))
    empty_count = sum(1 for s in provider_attempts if s.get("error_code") == "PROVIDER_EMPTY" or s.get("status") == "empty")
    stale_cache_available = any(s.get("cache_stale") for s in source_chain) or bool(data.get("stale"))
    aggregate_available = any(s.get("endpoint") == "get_all_financial_indicators" and s.get("success") for s in source_chain)
    module_timeout = any(s.get("provider") == "module" and (s.get("status") == "timeout" or s.get("error_code") == "PROVIDER_TIMEOUT") for s in source_chain)

    evidence: list[str] = []
    recommended_fix: list[str] = []
    primary_issue = "OK"
    error_codes = {error.get("error_code") for error in errors if isinstance(error, dict)}
    tags: list[str] = []

    if module_key == "report_documents" and ("REPORT_PDF_NOT_FOUND" in error_codes or "PDF_NOT_FOUND" in error_codes):
        primary_issue = "REPORT_PDF_NOT_FOUND"
        evidence.append("documents_count=0, no confirmed report PDF documents indexed")
        recommended_fix.extend(["run PDF discovery", "manually enter PDF URL", "upload report PDF"])
    elif module_key == "report_rag" and ("REPORT_PDF_NOT_FOUND" in error_codes or "PDF_NOT_FOUND" in error_codes):
        primary_issue = "REPORT_PDF_NOT_FOUND"
        evidence.append("documents_count=0, RAG cannot run without report PDF")
        recommended_fix.extend(["run PDF discovery", "manually enter PDF URL", "upload report PDF"])
    elif module_key == "report_rag" and "REPORT_NOT_INGESTED" in error_codes:
        primary_issue = "REPORT_NOT_INGESTED"
        evidence.append("report PDF exists but chunks or embeddings are not indexed")
        recommended_fix.append("ingest report PDF into RAG index")
    elif provider_attempts and timeout_count == len(provider_attempts) and stale_cache_available:
        primary_issue = "PROVIDER_TIMEOUT_WITH_STALE_CACHE"
        evidence.append("all provider attempts timed out but stale cache is available")
        recommended_fix.append("display stale snapshot and keep provider hard timeout")
    elif aggregate_available and module_timeout:
        primary_issue = "AGGREGATE_REUSE_MISSING"
        evidence.append("BaoStock aggregate is available but module still timed out")
        recommended_fix.append("reuse aggregate context before per-module provider calls")
    elif provider_attempts and timeout_count == len(provider_attempts):
        primary_issue = "PROVIDER_TIMEOUT"
        evidence.append("all provider attempts timed out")
        recommended_fix.append("lower provider concurrency or increase provider-specific timeout")
    elif raw_rows > 0 and len(normalized_rows) == 0 and not has_normalized_value:
        primary_issue = "MAPPING_ERROR"
        evidence.append(f"raw rows_count={raw_rows}, normalized rows_count=0")
        recommended_fix.append("add field mapping")
    elif len(normalized_rows) > 0 and valid_fields_count == 0:
        primary_issue = "ALL_NULL_ROWS"
        evidence.append(f"normalized rows_count={len(normalized_rows)}, valid_fields_count=0")
        recommended_fix.append("inspect normalized values and do not render all-null rows")
    elif valid_fields_count > 0 and not render.get("renderable", False):
        primary_issue = "RENDER_RULE_ERROR"
        evidence.append("normalized contains effective values but renderable=false")
        recommended_fix.append("display fallback table")
    elif render.get("renderable", False) and frontend_visible is False:
        primary_issue = "FRONTEND_RENDER_ERROR"
        evidence.append("backend renderable=true but frontend reported not visible")
        recommended_fix.append("check frontend render")
    elif aggregate_available and not render.get("renderable", False):
        primary_issue = "MAPPING_OR_RENDER_ERROR"
        evidence.append("BaoStock aggregate succeeded but module is not renderable")
        recommended_fix.extend(["add field mapping", "check frontend render"])
    elif provider_attempts and success_count == 0 and empty_count == len(provider_attempts):
        primary_issue = "PROVIDER_EMPTY"
        evidence.append("providers succeeded structurally but returned empty rows")
        recommended_fix.append("verify symbol, reporting period, and provider coverage")
    elif not render.get("renderable", False) and data.get("partial"):
        primary_issue = "PROVIDER_EMPTY"
        evidence.append("module is partial and not renderable")
        recommended_fix.append("check source_chain and raw_sample for coverage")

    coverage_pct = float(coverage.get("coverage_pct", 0 if core_fields else 100) or 0)
    if primary_issue == "OK":
        if coverage_pct >= 90:
            tags.append("OK")
        elif coverage_pct >= 60:
            primary_issue = "OK_WITH_FALLBACK"
            tags.extend(["OK_WITH_FALLBACK", "PARTIAL_DATA"])
        elif coverage_pct >= 30:
            primary_issue = "LOW_COVERAGE"
            tags.append("LOW_COVERAGE")
        else:
            primary_issue = "VERY_LOW_COVERAGE"
            tags.append("VERY_LOW_COVERAGE")

    if primary_issue not in tags:
        tags.insert(0, primary_issue)
    if coverage_pct >= 60 and coverage_pct < 90 and "PARTIAL_DATA" not in tags:
        tags.append("PARTIAL_DATA")
    if any((item.get("computed") if isinstance(item, dict) else False) for item in normalized_fields.values()):
        tags.append("COMPUTED_FIELDS")
    missing_map = coverage.get("missing_field_map") or {}
    if any(field in missing_map for field in ("market_cap", "float_market_cap")):
        tags.append("MISSING_COMPUTED_FIELD")
        tags.append("MISSING_COMPUTABLE_FIELDS")
        if "Enable share capital provider or reuse BaoStock total_share for market_cap." not in recommended_fix:
            recommended_fix.append("Enable share capital provider or reuse BaoStock total_share for market_cap.")
    if module_key in ("quote_overview", "valuation"):
        metrics = normalized.get("metrics") or {}
        if metrics.get("price_data_status") == "historical_fallback":
            tags.append("PRICE_HISTORICAL_FALLBACK")
        elif metrics.get("price_data_status") == "unavailable":
            tags.append("REALTIME_PRICE_UNAVAILABLE")
    visible_fields = render.get("visible_fields") or []
    trace_missing = [field for field in visible_fields if field not in field_trace]
    if trace_missing:
        tags.append("TRACE_MISSING")
        evidence.append(f"field_trace missing for {','.join(trace_missing)}")
        recommended_fix.append("populate field_trace for every visible field")

    unique_tags: list[str] = []
    for tag in tags:
        if tag and tag not in unique_tags:
            unique_tags.append(tag)

    severity = "info"
    if primary_issue in {"LOW_COVERAGE", "VERY_LOW_COVERAGE", "PROVIDER_TIMEOUT", "MAPPING_ERROR", "RENDER_RULE_ERROR", "ALL_NULL_ROWS"}:
        severity = "warning"
    if primary_issue in {"PROVIDER_SCHEMA_CHANGED", "TRACE_MISSING"}:
        severity = "error"

    return {
        "module_key": module_key,
        "primary_issue": primary_issue,
        "tags": unique_tags,
        "severity": severity,
        "coverage_pct": coverage_pct,
        "raw_rows_count": raw_rows,
        "normalized_rows_count": len(normalized_rows),
        "valid_fields_count": valid_fields_count,
        "evidence": evidence,
        "recommended_fix": recommended_fix,
    }
