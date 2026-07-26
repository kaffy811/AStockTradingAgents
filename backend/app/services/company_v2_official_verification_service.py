"""Verify CompanyV2 structured fields against CNINFO official fields."""
from __future__ import annotations

from typing import Any

STRUCTURED_ANNUAL_ROW_NOT_FOUND = "STRUCTURED_ANNUAL_ROW_NOT_FOUND"
ANNUAL_PERIOD_REQUIRED = "ANNUAL_PERIOD_REQUIRED"
PERIOD_MISMATCH = "PERIOD_MISMATCH"
STRUCTURED_FIELD_MISSING = "STRUCTURED_FIELD_MISSING"
OFFICIAL_FIELD_NOT_FOUND = "OFFICIAL_FIELD_NOT_FOUND"
VALUE_UNIT_UNCERTAIN = "VALUE_UNIT_UNCERTAIN"
LOW_CONFIDENCE_EXTRACTION = "LOW_CONFIDENCE_EXTRACTION"
UNIT_SCALE_MISMATCH = "UNIT_SCALE_MISMATCH"
FIELD_EXTRACTION_LOW_CONFIDENCE = "FIELD_EXTRACTION_LOW_CONFIDENCE"
PROVIDER_VALUE_CONFLICT = "PROVIDER_VALUE_CONFLICT"
FIELD_DEFINITION_MISMATCH = "FIELD_DEFINITION_MISMATCH"
ROUNDING_DIFFERENCE = "ROUNDING_DIFFERENCE"

VERIFY_FIELD_MAP = {
    "revenue": "revenue",
    "net_profit": "net_profit",
    "net_profit_parent": "net_profit_parent",
    "operating_cashflow": "operating_cashflow",
    "eps_basic": "eps_basic",
    "roe": "roe_weighted",
    "total_share": "total_share",
    "float_share": "float_share",
}

_REVIEW_HIGH = {
    PROVIDER_VALUE_CONFLICT,
    FIELD_DEFINITION_MISMATCH,
    PERIOD_MISMATCH,
    UNIT_SCALE_MISMATCH,
}
_REVIEW_MEDIUM = {
    STRUCTURED_ANNUAL_ROW_NOT_FOUND,
    ANNUAL_PERIOD_REQUIRED,
    STRUCTURED_FIELD_MISSING,
    OFFICIAL_FIELD_NOT_FOUND,
    VALUE_UNIT_UNCERTAIN,
    LOW_CONFIDENCE_EXTRACTION,
    FIELD_EXTRACTION_LOW_CONFIDENCE,
}


def _value(item: Any) -> float | None:
    if isinstance(item, dict):
        item = item.get("value", item.get("raw_value"))
    try:
        if item is None or item == "":
            return None
        return float(item)
    except Exception:
        return None


def _relative_diff(a: float, b: float) -> float:
    denom = max(abs(a), abs(b), 1e-12)
    return abs(a - b) / denom * 100


def _status(field: str, structured: float | None, official: float | None) -> tuple[str, float | None, float]:
    if official is None:
        return "unverified", None, 0.0
    if structured is None:
        return "unverified", None, 0.0
    if field == "eps_basic":
        abs_diff = abs(structured - official)
        rel = _relative_diff(structured, official)
        return ("verified" if abs_diff <= 0.01 or rel <= 0.5 else "conflict"), rel, 0.5
    if field == "roe":
        abs_pp = abs(structured - official)
        return ("verified" if abs_pp <= 0.005 else "conflict"), abs_pp * 100, 0.5
    if field in {"total_share", "float_share"}:
        rel = _relative_diff(structured, official)
        return ("verified" if rel <= 0.1 else "conflict"), rel, 0.1
    rel = _relative_diff(structured, official)
    return ("verified" if rel <= 1.0 else "conflict"), rel, 1.0


def _period_value(row: dict[str, Any]) -> str:
    for key in ("period", "stat_date", "statDate", "end_date", "report_period", "date"):
        value = row.get(key)
        if value:
            return str(value)
    value = row.get("report_year") or row.get("year")
    return str(value) if value else ""


def _row_matches_year(row: dict[str, Any], report_year: int | None) -> bool:
    if not report_year:
        return False
    for key in ("period", "stat_date", "statDate", "report_year", "year"):
        value = row.get(key)
        if value is None:
            continue
        if str(value).startswith(str(report_year)):
            return True
    return False


def _row_matches_annual_report(row: dict[str, Any], report_year: int | None) -> bool:
    if not report_year:
        return False
    period = _period_value(row)
    if period == f"{report_year}-12-31":
        return True
    if str(row.get("report_year") or row.get("year") or "") == str(report_year) and not period.endswith(("-03-31", "-06-30", "-09-30")):
        return True
    return False


def _same_year_non_annual(row: dict[str, Any], report_year: int | None) -> bool:
    if not report_year:
        return False
    period = _period_value(row)
    return period.startswith(str(report_year)) and not _row_matches_annual_report(row, report_year)


def _iter_module_rows(module: dict[str, Any]) -> list[dict[str, Any]]:
    normalized = module.get("normalized") or {}
    candidates = [
        module.get("latest") or {},
        *(module.get("history") or []),
        normalized.get("latest") or {},
        *(normalized.get("rows") or []),
        *(normalized.get("history") or []),
    ]
    return [row for row in candidates if isinstance(row, dict) and row]


def _missing_placeholders(reason: str, *, report_year: int | None, row_period: str | None = None) -> dict[str, Any]:
    return {
        field: {
            "value": None,
            "reason": reason,
            "structured_period": row_period,
            "official_report_year": report_year,
            "source": "company_v2_annual_history",
        }
        for field in VERIFY_FIELD_MAP
    }


def extract_structured_fields(
    debug_data: dict[str, Any],
    *,
    report_year: int | None = None,
    report_type: str | None = None,
    annual_required: bool = False,
) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for module in (debug_data.get("modules") or {}).values():
        module = module or {}
        if not annual_required:
            normalized_fields = (module.get("normalized") or {}).get("fields") or {}
            for key, item in normalized_fields.items():
                fields.setdefault(key, item)
        rows = _iter_module_rows(module)
        if annual_required or report_type == "annual":
            matching_rows = [row for row in rows if _row_matches_annual_report(row, report_year)]
            if not rows:
                fields.update({k: v for k, v in _missing_placeholders(STRUCTURED_ANNUAL_ROW_NOT_FOUND, report_year=report_year).items() if k not in fields})
                continue
            if rows and not matching_rows:
                reason = ANNUAL_PERIOD_REQUIRED if any(_same_year_non_annual(row, report_year) for row in rows) else STRUCTURED_ANNUAL_ROW_NOT_FOUND
                fields.update({k: v for k, v in _missing_placeholders(reason, report_year=report_year, row_period=_period_value(rows[0])).items() if k not in fields})
                continue
            preferred_rows = matching_rows
        else:
            preferred_rows = [r for r in rows if _row_matches_year(r, report_year)] or rows[:1]
        for row in preferred_rows:
            if not isinstance(row, dict):
                continue
            for key, value in row.items():
                if key not in VERIFY_FIELD_MAP and key not in {"roe_weighted"}:
                    continue
                row_field = {
                    "value": value,
                    "source": "company_v2_annual_history" if annual_required else "company_v2_normalized_row",
                    "structured_period": _period_value(row),
                    "official_report_year": report_year,
                    "report_period": _period_value(row),
                    "provider_period": _period_value(row),
                    "provider_source": row.get(f"{key}_source") or row.get("source") or ("company_v2_annual_history" if annual_required else "company_v2_normalized_row"),
                    "provider_field_name": (row.get("source_field_map") or {}).get(key) or key,
                    "provider_unit": row.get(f"{key}_unit"),
                    "provider_definition": row.get(f"{key}_provider_definition") or row.get("provider_definition"),
                    "matched_label": row.get(f"{key}_matched_label") or row.get("matched_label"),
                    "field_definition_match": row.get(f"{key}_field_definition_match") or row.get("field_definition_match"),
                    "value_basis": row.get(f"{key}_value_basis") or row.get("value_basis") or "unknown",
                }
                if _row_matches_annual_report(row, report_year) or _row_matches_year(row, report_year):
                    fields[key] = row_field
                else:
                    fields.setdefault(key, row_field)
    return fields


def _classify_conflict(field: str, structured: float | None, official: float | None, diff: float | None, official_entry: Any) -> str | None:
    if structured is None or official is None:
        return None
    confidence = official_entry.get("confidence") if isinstance(official_entry, dict) else None
    if confidence is not None and confidence < 0.75:
        return FIELD_EXTRACTION_LOW_CONFIDENCE
    low = min(abs(structured), abs(official))
    high = max(abs(structured), abs(official))
    if low > 0:
        ratio = high / low
        for scale in (10_000, 100_000_000):
            if abs(ratio - scale) / scale <= 0.05:
                return UNIT_SCALE_MISMATCH
    if field in {"net_profit", "net_profit_parent"} and diff is not None and diff > 10:
        return FIELD_DEFINITION_MISMATCH
    if diff is not None and diff <= 2.0:
        return ROUNDING_DIFFERENCE
    return PROVIDER_VALUE_CONFLICT


def _review_policy(status: str, reason_code: str | None) -> dict[str, Any]:
    if status == "verified":
        return {
            "requires_manual_review": False,
            "review_priority": "low",
            "review_reason": "verified against official annual disclosure within tolerance",
            "safe_for_rag": True,
            "rag_usage_policy": {
                "can_quote_as_fact": True,
                "requires_caveat": False,
                "suggested_caveat": "",
            },
        }
    reason = reason_code or STRUCTURED_FIELD_MISSING
    priority = "high" if reason in _REVIEW_HIGH else "medium" if reason in _REVIEW_MEDIUM else "low"
    return {
        "requires_manual_review": True,
        "review_priority": priority,
        "review_reason": f"{reason} requires manual review before use as a confirmed disclosure fact",
        "safe_for_rag": False,
        "rag_usage_policy": {
            "can_quote_as_fact": False,
            "requires_caveat": True,
            "suggested_caveat": "该字段尚未完成官方披露核验或存在口径差异，仅可作为待复核信息展示。",
        },
    }


def _official_meta(official_entry: Any, official_key: str, report_year: int | None, report_type: str | None) -> dict[str, Any]:
    if not isinstance(official_entry, dict):
        return {
            "official_source": "cninfo_pdf",
            "official_report_id": None,
            "official_report_year": report_year,
            "official_report_type": report_type,
            "official_period": f"{report_year}-12-31" if report_year and report_type == "annual" else None,
            "official_field_name": official_key,
            "official_unit": None,
            "matched_alias": None,
            "official_table": None,
            "official_row_label": None,
            "official_column_label": None,
            "evidence_note": "official field not extracted from parsed annual report",
        }
    return {
        "official_source": official_entry.get("source") or "cninfo_pdf",
        "official_report_id": official_entry.get("report_id"),
        "official_report_year": report_year,
        "official_report_type": report_type,
        "official_period": f"{report_year}-12-31" if report_year and report_type == "annual" else None,
        "official_field_name": official_entry.get("official_field_name") or official_key,
        "official_unit": official_entry.get("unit"),
        "matched_alias": official_entry.get("matched_alias"),
        "official_table": official_entry.get("official_table"),
        "official_row_label": official_entry.get("official_row_label"),
        "official_column_label": official_entry.get("official_column_label"),
        "evidence_note": official_entry.get("evidence_note"),
    }


def verify_official_fields(
    structured_fields: dict[str, Any],
    official_fields: dict[str, Any],
    *,
    report_year: int | None = None,
    report_type: str | None = None,
) -> dict[str, Any]:
    results: dict[str, Any] = {}
    verified = conflict = unverified = 0
    period_mismatch = unit_mismatch = low_confidence = provider_conflict = 0
    structured_periods: set[str] = set()
    for structured_key, official_key in VERIFY_FIELD_MAP.items():
        structured_entry = structured_fields.get(structured_key)
        structured_value = _value(structured_entry)
        official_entry = official_fields.get(official_key)
        official_value = _value(official_entry)
        structured_period = structured_entry.get("structured_period") if isinstance(structured_entry, dict) else None
        provider_source = structured_entry.get("provider_source") or structured_entry.get("source") if isinstance(structured_entry, dict) else None
        provider_field_name = structured_entry.get("provider_field_name") or structured_entry.get("raw_field") if isinstance(structured_entry, dict) else None
        provider_unit = structured_entry.get("provider_unit") or structured_entry.get("unit") if isinstance(structured_entry, dict) else None
        if structured_period:
            structured_periods.add(str(structured_period))
        reason = structured_entry.get("reason") if isinstance(structured_entry, dict) else None
        conflict_type = None
        if reason in {STRUCTURED_ANNUAL_ROW_NOT_FOUND, ANNUAL_PERIOD_REQUIRED, PERIOD_MISMATCH}:
            status, diff, tolerance = "unverified", None, 0.0
            if reason in {ANNUAL_PERIOD_REQUIRED, PERIOD_MISMATCH}:
                period_mismatch += 1
        else:
            status, diff, tolerance = _status(structured_key, structured_value, official_value)
            if status == "unverified" and official_value is None and reason is None:
                reason = OFFICIAL_FIELD_NOT_FOUND
            if status == "unverified" and official_value is not None and structured_value is None and reason is None:
                reason = STRUCTURED_FIELD_MISSING
            if status == "conflict":
                conflict_type = _classify_conflict(structured_key, structured_value, official_value, diff, official_entry)
                if conflict_type == UNIT_SCALE_MISMATCH:
                    unit_mismatch += 1
                elif conflict_type == FIELD_EXTRACTION_LOW_CONFIDENCE:
                    low_confidence += 1
                elif conflict_type == PROVIDER_VALUE_CONFLICT:
                    provider_conflict += 1
        reason_code = conflict_type or reason or ("VERIFIED" if status == "verified" else None)
        review = _review_policy(status, reason_code)
        official_meta = _official_meta(official_entry, official_key, report_year, report_type)
        if status == "verified":
            verified += 1
        elif status == "conflict":
            conflict += 1
        else:
            unverified += 1
        results[structured_key] = {
            "field": structured_key,
            "provider_value": structured_value,
            "provider_source": provider_source,
            "provider_period": structured_period,
            "provider_field_name": provider_field_name or structured_key,
            "provider_unit": provider_unit,
            "structured_value": structured_value,
            "official_value": official_value,
            "structured_period": structured_period,
            "official_report_year": report_year,
            "relative_diff_pct": diff,
            "status": status,
            "tolerance_pct": tolerance,
            "source": "cninfo_pdf" if official_entry else None,
            "evidence_page": official_entry.get("page") if isinstance(official_entry, dict) else None,
            "reason": reason,
            "reason_code": reason_code,
            "conflict_type": conflict_type,
            **official_meta,
            **review,
        }
    overall = "unverified"
    if conflict:
        overall = "conflict"
    elif verified and unverified:
        overall = "partial"
    elif verified:
        overall = "verified"
    return {
        "status": overall,
        "report_year": report_year,
        "report_type": report_type,
        "structured_period_matched": sorted(structured_periods),
        "verified_fields_count": verified,
        "conflict_fields_count": conflict,
        "unverified_fields_count": unverified,
        "period_mismatch_count": period_mismatch,
        "unit_mismatch_count": unit_mismatch,
        "extraction_low_confidence_count": low_confidence,
        "provider_value_conflict_count": provider_conflict,
        "fields": results,
    }


company_v2_official_verification_service = verify_official_fields
