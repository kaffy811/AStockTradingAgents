"""Request-local numeric evidence validation for deterministic stock EOD answers.

This module is intentionally independent from the Report RAG numeric validator.
It accepts only facts already normalized by the Tushare EOD gateway (or explicit
CNINFO structured facts) and never calls a provider.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


_NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?%?")
_MARKDOWN_URL_RE = re.compile(r"\]\([^)]*\)")
_APPROVED_SOURCES = frozenset({"tushare", "CNINFO"})
_FINANCIAL_MODULE = "financial"
_EXPECTED_UNITS: dict[tuple[str, str], str] = {
    ("quote", "close"): "CNY",
    ("quote", "change"): "CNY",
    ("quote", "pct_chg"): "%",
    ("quote", "vol"): "lot",
    ("quote", "amount"): "CNY_thousand",
    ("valuation", "pe_ttm"): "multiple",
    ("valuation", "pb"): "multiple",
    ("valuation", "ps_ttm"): "multiple",
    ("valuation", "turnover_rate"): "%",
    ("valuation", "total_mv"): "CNY_10k",
    ("valuation", "circ_mv"): "CNY_10k",
    ("financial", "roe"): "%",
    ("financial", "roe_waa"): "%",
    ("financial", "roa"): "%",
    ("financial", "grossprofit_margin"): "%",
    ("financial", "netprofit_margin"): "%",
    ("financial", "debt_to_assets"): "%",
    ("financial", "netprofit_yoy"): "%",
}
_UNIT_CONVERSIONS: dict[tuple[str, str], Decimal] = {
    ("CNY", "CNY_100M"): Decimal("0.00000001"),
    ("CNY_10k", "CNY_100M"): Decimal("0.0001"),
    ("CNY_thousand", "CNY_100M"): Decimal("0.00001"),
}


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def _display_decimal(value: Decimal, decimal_places: int | None) -> str:
    if decimal_places is None:
        text = format(value, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    quantum = Decimal(1).scaleb(-decimal_places)
    return format(value.quantize(quantum, rounding=ROUND_HALF_UP), f".{decimal_places}f")


def make_request_local_evidence(
    *,
    module: str,
    metric: str,
    fact: dict[str, Any],
    display_unit: str | None = None,
    decimal_places: int | None = None,
) -> dict[str, Any] | None:
    """Create one traceable fact; formatting/conversion must be explicit here."""
    canonical = _decimal(fact.get("value"))
    source = fact.get("source")
    as_of = fact.get("as_of")
    canonical_unit = fact.get("unit")
    if _EXPECTED_UNITS.get((module, metric)) != canonical_unit:
        return None
    if canonical is None or source not in _APPROVED_SOURCES or not isinstance(as_of, str) or not as_of:
        return None
    target_unit = display_unit or canonical_unit
    display_number = canonical
    conversion = "identity"
    if target_unit != canonical_unit:
        factor = _UNIT_CONVERSIONS.get((canonical_unit, target_unit))
        if factor is None:
            return None
        display_number = canonical * factor
        conversion = f"{canonical_unit}_to_{target_unit}"
    report_period = as_of if module == _FINANCIAL_MODULE else None
    return {
        "metric": metric,
        "canonical_value": str(canonical),
        "display_value": _display_decimal(display_number, decimal_places),
        "unit": target_unit,
        "as_of": as_of,
        "report_period": report_period,
        "source": source,
        "request_local_evidence_id": f"stock-eod:{module}:{metric}",
        "format_rule": {
            "conversion": conversion,
            "decimal_places": decimal_places,
            "rounding": "ROUND_HALF_UP" if decimal_places is not None else "none",
        },
    }


def claim_from_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        key: evidence.get(key)
        for key in (
            "metric", "display_value", "unit", "as_of", "report_period", "source",
            "request_local_evidence_id",
        )
    }


def validate_stock_eod_numeric_claims(
    answer: str,
    evidence_basis: list[dict[str, Any]],
    checked_claims: list[dict[str, Any]],
    *,
    symbol: str,
    allowed_metadata_dates: list[str],
) -> dict[str, Any]:
    """Validate claims and reject every unexplained numeric token in the answer."""
    by_id = {item.get("request_local_evidence_id"): item for item in evidence_basis}
    invalid_claims: list[str] = []
    for claim in checked_claims:
        evidence = by_id.get(claim.get("request_local_evidence_id"))
        if evidence is None:
            invalid_claims.append(str(claim.get("display_value") or "missing_evidence"))
            continue
        required = ("metric", "display_value", "unit", "as_of", "source", "request_local_evidence_id")
        if any(claim.get(key) != evidence.get(key) for key in required):
            invalid_claims.append(str(claim.get("display_value") or "claim_mismatch"))
            continue
        if evidence.get("source") not in _APPROVED_SOURCES:
            invalid_claims.append(str(claim.get("display_value") or "unapproved_source"))
            continue
        rendered_text = claim.get("rendered_text")
        if rendered_text is not None and (not isinstance(rendered_text, str) or rendered_text not in answer):
            invalid_claims.append(str(claim.get("display_value") or "rendered_claim_mismatch"))
            continue
        if str(evidence.get("request_local_evidence_id", "")).startswith("stock-eod:financial:"):
            if not evidence.get("report_period") or claim.get("report_period") != evidence.get("report_period"):
                invalid_claims.append(str(claim.get("display_value") or "invalid_report_period"))

    visible = _MARKDOWN_URL_RE.sub("]", answer)
    allowed_literals = [symbol, *allowed_metadata_dates]
    allowed_literals.extend(str(item.get("as_of")) for item in evidence_basis if item.get("as_of"))
    allowed_literals.extend(str(item.get("report_period")) for item in evidence_basis if item.get("report_period"))
    allowed_literals.extend(str(item.get("unit")) for item in evidence_basis if item.get("unit"))
    for literal in sorted(set(allowed_literals), key=len, reverse=True):
        visible = visible.replace(literal, " ")
    display_values = sorted(
        {str(item.get("display_value")) for item in evidence_basis if item.get("display_value")},
        key=len,
        reverse=True,
    )
    for display in display_values:
        if display:
            visible = visible.replace(f"{display}%", " ").replace(display, " ")
    unsupported = [match.group(0) for match in _NUMBER_RE.finditer(visible)]
    unsupported.extend(invalid_claims)
    unsupported = list(dict.fromkeys(unsupported))
    return {
        "valid": not unsupported and len(checked_claims) == len(evidence_basis),
        "checked_claims": checked_claims,
        "unsupported_tokens": unsupported,
        "evidence_basis": evidence_basis,
        "metadata_rules": {
            "symbol": symbol,
            "allowed_dates": sorted(set(allowed_metadata_dates)),
            "all_integers_exempt": False,
        },
    }
