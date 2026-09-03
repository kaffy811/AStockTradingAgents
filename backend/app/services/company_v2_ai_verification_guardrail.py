"""Deterministic guardrails for AI-assisted official disclosure verification."""
from __future__ import annotations

from typing import Any

from app.services.company_v2_financial_field_definition_registry import (
    build_field_definition_match,
    get_field_definition,
)


AMOUNT_FIELDS = {
    "revenue",
    "net_profit_parent",
    "net_profit",
    "operating_cashflow",
    "total_assets",
    "equity_parent",
}
EPS_FIELDS = {"eps_basic"}
ROE_FIELDS = {"roe_weighted"}
SHARE_FIELDS = {"total_share", "float_share"}

FIELD_STATUSES = {
    "verified",
    "likely_match",
    "conflict",
    "structured_field_missing",
    "official_field_not_found",
    "insufficient_evidence",
    "definition_mismatch",
    "period_basis_mismatch",
    "unit_scale_suspected",
    "needs_human_review",
    "skipped",
}

COUNT_KEYS = [
    "verified_count",
    "likely_match_count",
    "true_conflict_count",
    "structured_field_missing_count",
    "official_field_not_found_count",
    "definition_mismatch_count",
    "period_basis_mismatch_count",
    "unit_scale_suspected_count",
    "insufficient_evidence_count",
    "needs_human_review_count",
]


def _float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except Exception:
        return None


def _relative_diff(a: float, b: float) -> float:
    return abs(a - b) / max(abs(a), abs(b), 1e-12) * 100


def _diff_exceeds_tolerance(field: str, official: float | None, structured: float | None) -> tuple[bool, float | None, str | None]:
    if official is None or structured is None:
        return False, None, None
    rel = _relative_diff(official, structured)
    if field in EPS_FIELDS:
        if abs(official - structured) > 0.01 and rel > 0.5:
            return True, rel, "EPS_DIFF_EXCEEDS_TOLERANCE"
    elif field in ROE_FIELDS:
        abs_diff = abs(official - structured)
        # Values are expected as ratios, e.g. 0.0654 for 6.54%.
        if abs_diff > 0.005:
            return True, abs_diff * 100, "ROE_DIFF_EXCEEDS_TOLERANCE"
    elif field in SHARE_FIELDS:
        if rel > 0.1:
            return True, rel, "SHARE_DIFF_EXCEEDS_TOLERANCE"
    else:
        if rel > 1.0:
            return True, rel, "VALUE_DIFF_EXCEEDS_TOLERANCE"
    return False, rel, None


def _unit_scale_suspected(official: float | None, structured: float | None) -> bool:
    if official is None or structured is None:
        return False
    low = min(abs(official), abs(structured))
    high = max(abs(official), abs(structured))
    if low <= 0:
        return False
    ratio = high / low
    return any(abs(ratio - scale) / scale <= 0.05 for scale in (10_000, 100_000_000))


def _queue_entry(field: str, entry: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "field": field,
        "status": entry.get("status"),
        "reason": reason,
        "confidence": entry.get("confidence"),
        "official_value": entry.get("official_value"),
        "structured_value": entry.get("structured_value"),
        "provider_definition": entry.get("provider_definition"),
        "matched_label": entry.get("matched_label"),
        "field_definition_match": entry.get("field_definition_match"),
        "evidence_page": entry.get("evidence_page"),
        "evidence_excerpt": entry.get("evidence_excerpt"),
    }


def _finding_entry(field: str, entry: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "field": field,
        "status": entry.get("status"),
        "reason": reason,
        "confidence": entry.get("confidence"),
        "official_value": entry.get("official_value"),
        "structured_value": entry.get("structured_value"),
        "provider_definition": entry.get("provider_definition"),
        "matched_label": entry.get("matched_label"),
        "field_definition_match": entry.get("field_definition_match"),
        "evidence_page": entry.get("evidence_page"),
    }


def _has_evidence(entry: dict[str, Any]) -> bool:
    return entry.get("evidence_page") is not None and bool(entry.get("evidence_excerpt"))


def _period_end(report_year: int | None, report_type: str | None) -> str | None:
    if not report_year:
        return None
    suffix = {
        "annual": "12-31",
        "semi_annual": "06-30",
        "q1": "03-31",
        "q3": "09-30",
    }.get(report_type or "annual")
    return f"{report_year}-{suffix}" if suffix else str(report_year)


def _same_report_period(entry: dict[str, Any], report_year: int | None, report_type: str | None) -> bool:
    entry_report_year = _int(entry.get("report_year"))
    if entry_report_year is not None and report_year and entry_report_year != int(report_year):
        return False
    if entry.get("report_type") and report_type and entry["report_type"] != report_type:
        return False
    period = str(entry.get("period") or entry.get("structured_period") or "")
    expected_period = _period_end(report_year, report_type)
    if expected_period and period and period not in {expected_period, str(report_year)} and not period.startswith(str(report_year)):
        return False
    return True


def _share_period_matches(entry: dict[str, Any], report_year: int | None, report_type: str | None) -> bool:
    if report_type != "annual" or not report_year:
        return True
    expected = f"{report_year}-12-31"
    candidates = [
        entry.get("as_of_date"),
        entry.get("structured_as_of_date"),
        entry.get("official_as_of_date"),
        entry.get("period"),
        entry.get("structured_period"),
    ]
    return any(str(value).startswith(expected) for value in candidates if value)


def _definition_match(field: str, entry: dict[str, Any]) -> dict[str, Any]:
    reason = str(entry.get("reason") or "")
    provider_definition = str(entry.get("provider_definition") or "")
    explicit_mismatch: dict[str, Any] | None = None
    if field == "revenue" and ("主营业务收入" in reason or provider_definition in {"main_business_revenue", "total_operating_revenue"}):
        explicit_mismatch = {
            "status": "definition_mismatch",
            "match_type": "incompatible",
            "provider_definition": provider_definition or "main_business_revenue",
            "reason": "structured value appears to be main business revenue, not operating revenue",
        }
    if field == "net_profit_parent" and (
        "含少数股东" in reason
        or "净利润（含少数股东）" in reason
        or provider_definition in {"net_profit", "net_profit_parent_excl_nonrecurring"}
    ):
        explicit_mismatch = {
            "status": "definition_mismatch",
            "match_type": "incompatible",
            "provider_definition": provider_definition or "net_profit",
            "reason": "structured value appears to be net profit, not parent-company net profit",
        }
    structured_name = str(entry.get("structured_field_name") or "")
    if field == "roe_weighted" and (structured_name in {"roe", "ROE"} or provider_definition in {"roe", "unknown_roe", "roe_diluted"}):
        explicit_mismatch = {
            "status": "definition_mismatch",
            "match_type": "incompatible" if provider_definition != "unknown_roe" else "unknown",
            "provider_definition": provider_definition or "unknown_roe",
            "reason": "structured field is generic ROE, not confirmed weighted average ROE",
        }
    if explicit_mismatch:
        base = build_field_definition_match(field, entry)
        return {**base, **explicit_mismatch}
    existing = entry.get("field_definition_match")
    if isinstance(existing, dict) and existing.get("status"):
        return existing
    match = build_field_definition_match(field, entry)
    return match


def _normalize_status(status: Any) -> str:
    if status == "mismatch":
        return "conflict"
    if status == "not_found":
        return "official_field_not_found"
    if status in FIELD_STATUSES:
        return str(status)
    return "insufficient_evidence"


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        key = (str(item.get("field")), str(item.get("status")), str(item.get("reason")))
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _counts(fields: dict[str, Any], human_review_queue: list[dict[str, Any]]) -> dict[str, int]:
    counts = {key: 0 for key in COUNT_KEYS}
    for entry in fields.values():
        if not isinstance(entry, dict):
            continue
        status = entry.get("status")
        if status == "verified":
            counts["verified_count"] += 1
        elif status == "likely_match":
            counts["likely_match_count"] += 1
        elif status == "conflict":
            counts["true_conflict_count"] += 1
        elif status == "structured_field_missing":
            counts["structured_field_missing_count"] += 1
        elif status == "official_field_not_found":
            counts["official_field_not_found_count"] += 1
        elif status == "definition_mismatch":
            counts["definition_mismatch_count"] += 1
        elif status == "period_basis_mismatch":
            counts["period_basis_mismatch_count"] += 1
        elif status == "unit_scale_suspected":
            counts["unit_scale_suspected_count"] += 1
        elif status == "insufficient_evidence":
            counts["insufficient_evidence_count"] += 1
        elif status == "needs_human_review":
            counts["needs_human_review_count"] += 1
    counts["needs_human_review_count"] = max(counts["needs_human_review_count"], len(human_review_queue))
    return counts


def _aggregate_status(counts: dict[str, int], fields: dict[str, Any]) -> str:
    if counts["true_conflict_count"] > 0:
        return "conflict"
    matched = counts["verified_count"] + counts["likely_match_count"]
    if not fields or matched == 0:
        if counts["needs_human_review_count"] > 0:
            return "needs_human_review"
        return "insufficient_evidence"
    if counts["needs_human_review_count"] > 0:
        return "needs_human_review"
    issue_count = sum(value for key, value in counts.items() if key not in {"verified_count", "likely_match_count", "true_conflict_count", "needs_human_review_count"})
    if issue_count > 0:
        return "partial"
    return "verified"


def apply_ai_verification_guardrail(
    ai_result: dict[str, Any],
    *,
    report_year: int | None = None,
    report_type: str | None = None,
    confidence_threshold: float = 0.75,
) -> dict[str, Any]:
    fields = ai_result.get("fields") or {}
    human_review_queue: list[dict[str, Any]] = []
    non_blocking_findings = list(ai_result.get("non_blocking_findings") or [])
    warnings = list(ai_result.get("warnings") or [])

    for field, entry in fields.items():
        if not isinstance(entry, dict):
            continue
        entry.setdefault("needs_human_review", False)
        official = _float(entry.get("official_value"))
        structured = _float(entry.get("structured_value"))
        confidence = _float(entry.get("confidence"))
        status = _normalize_status(entry.get("status"))
        reason = entry.get("reason") or status
        entry["field_definition_match"] = _definition_match(field, entry)

        definition = get_field_definition(field)
        if definition:
            entry.setdefault("field_definition", definition.canonical_name)

        same_period = _same_report_period(entry, report_year, report_type)
        if not same_period:
            status = "period_basis_mismatch"
            reason = "report period does not match requested verification period"

        if field in SHARE_FIELDS and structured is not None and not _share_period_matches(entry, report_year, report_type):
            status = "period_basis_mismatch"
            reason = "share capital lacks matching annual period-end as_of_date"
        if field in SHARE_FIELDS and structured is not None:
            share_reason = str(entry.get("reason") or "")
            if any(token in share_reason for token in ("期末", "当前", "时点", "无法确认")):
                status = "period_basis_mismatch"
                reason = entry.get("reason") or "share capital period basis mismatch"

        definition_status = entry["field_definition_match"].get("status")
        definition_match_type = entry["field_definition_match"].get("match_type")
        if status != "period_basis_mismatch" and (
            definition_status == "definition_mismatch"
            or definition_match_type == "incompatible"
            or (field == "roe_weighted" and entry["field_definition_match"].get("provider_definition") == "unknown_roe")
        ):
            status = "definition_mismatch"
            reason = entry["field_definition_match"].get("reason") or "field definition mismatch"

        if _unit_scale_suspected(official, structured):
            status = "unit_scale_suspected"
            reason = "UNIT_SCALE_SUSPECTED"
            entry.setdefault("warnings", []).append("UNIT_SCALE_SUSPECTED")
            warnings.append(f"{field}: UNIT_SCALE_SUSPECTED")

        has_evidence = _has_evidence(entry)
        if status in {"definition_mismatch", "period_basis_mismatch", "unit_scale_suspected"}:
            pass
        elif official is None and structured is None:
            status = "insufficient_evidence" if has_evidence else "skipped"
            reason = "no comparable official or structured value"
        elif official is not None and structured is None:
            status = "structured_field_missing"
            reason = entry.get("reason") or "official field exists but structured field is missing"
        elif official is None and structured is not None:
            status = "insufficient_evidence" if has_evidence else "official_field_not_found"
            reason = entry.get("reason") or ("candidate evidence is insufficient" if has_evidence else "official field not found in PDF evidence")

        if official is not None and structured is not None and status not in {"definition_mismatch", "period_basis_mismatch", "unit_scale_suspected"}:
            if not has_evidence:
                status = "official_field_not_found"
                reason = "missing evidence page or excerpt"
            else:
                exceeds, diff, reason_code = _diff_exceeds_tolerance(field, official, structured)
                if diff is not None:
                    entry["relative_diff_pct"] = diff
                if confidence is not None and confidence < confidence_threshold:
                    status = "likely_match" if not exceeds else "needs_human_review"
                    reason = entry.get("reason") or "low evidence confidence"
                elif exceeds:
                    status = "conflict"
                    reason = reason_code or "VALUE_DIFF_EXCEEDS_TOLERANCE"
                else:
                    status = "verified" if status == "verified" else "likely_match"
                    reason = entry.get("reason") or "within tolerance"

        entry["status"] = status
        entry["reason"] = reason
        entry["needs_human_review"] = status in {
            "conflict",
            "definition_mismatch",
            "unit_scale_suspected",
            "needs_human_review",
        }
        if confidence is not None and confidence < confidence_threshold and official is not None and structured is not None:
            entry["needs_human_review"] = True

        if entry["needs_human_review"]:
            human_review_queue.append(_queue_entry(field, entry, str(reason)))
        elif status not in {"verified", "likely_match", "skipped"}:
            non_blocking_findings.append(_finding_entry(field, entry, str(reason)))

    human_review_queue = _dedupe(human_review_queue)
    non_blocking_findings = _dedupe(non_blocking_findings)
    counts = _counts(fields, human_review_queue)

    deduped_warnings: list[str] = []
    seen_warnings: set[str] = set()
    for warning in warnings:
        if warning not in seen_warnings:
            seen_warnings.add(warning)
            deduped_warnings.append(warning)

    ai_result["verification_status"] = _aggregate_status(counts, fields)
    ai_result["human_review_queue"] = human_review_queue
    ai_result["non_blocking_findings"] = non_blocking_findings
    ai_result["warnings"] = deduped_warnings
    ai_result["summary_counts"] = counts
    ai_result.update(counts)
    return ai_result


company_v2_ai_verification_guardrail = apply_ai_verification_guardrail
