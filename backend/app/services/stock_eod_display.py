"""Deterministic user-facing projection for request-local stock EOD evidence.

This module never fetches or calculates financial facts.  It only converts the
display representation of evidence already accepted by the stock EOD evidence
builder.  Canonical values, units, dates, sources and evidence identifiers are
retained unchanged.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from app.services.stock_eod_numeric_validation import make_request_local_evidence


_TWO_PLACES = Decimal("0.01")
_DISPLAY_POLICIES: dict[tuple[str, str], dict[str, Any]] = {
    ("quote", "close"): {"factor": "1", "unit": "元", "conversion": "identity"},
    ("quote", "change"): {"factor": "1", "unit": "元", "conversion": "identity"},
    ("quote", "pct_chg"): {"factor": "1", "unit": "%", "conversion": "identity"},
    ("quote", "vol"): {"factor": "0.0001", "unit": "万手", "conversion": "lot_to_10k_lot"},
    ("quote", "amount"): {"factor": "0.00001", "unit": "亿元", "conversion": "CNY_thousand_to_CNY_100M"},
    ("valuation", "pe_ttm"): {"factor": "1", "unit": "倍", "conversion": "identity"},
    ("valuation", "pb"): {"factor": "1", "unit": "倍", "conversion": "identity"},
    ("valuation", "ps_ttm"): {"factor": "1", "unit": "倍", "conversion": "identity"},
    ("valuation", "turnover_rate"): {"factor": "1", "unit": "%", "conversion": "identity"},
    ("valuation", "total_mv"): {"factor": "0.0001", "unit": "亿元", "conversion": "CNY_10k_to_CNY_100M"},
    ("valuation", "circ_mv"): {"factor": "0.0001", "unit": "亿元", "conversion": "CNY_10k_to_CNY_100M"},
    ("financial", "roe"): {"factor": "1", "unit": "%", "conversion": "identity"},
    ("financial", "roe_waa"): {"factor": "1", "unit": "%", "conversion": "identity"},
    ("financial", "roa"): {"factor": "1", "unit": "%", "conversion": "identity"},
    ("financial", "grossprofit_margin"): {"factor": "1", "unit": "%", "conversion": "identity"},
    ("financial", "netprofit_margin"): {"factor": "1", "unit": "%", "conversion": "identity"},
    ("financial", "debt_to_assets"): {"factor": "1", "unit": "%", "conversion": "identity"},
    ("financial", "netprofit_yoy"): {"factor": "1", "unit": "%", "conversion": "identity"},
}


def _display_number(value: Decimal) -> str:
    rounded = value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
    return format(rounded, ",.2f")


def project_stock_eod_display(
    *,
    module: str,
    metric: str,
    fact: dict[str, Any],
) -> dict[str, Any]:
    """Return a display projection or a controlled unavailable result."""
    policy = _DISPLAY_POLICIES.get((module, metric))
    if policy is None:
        return {"status": "unavailable", "reason_code": "DISPLAY_POLICY_NOT_DEFINED", "evidence": None}

    evidence = make_request_local_evidence(module=module, metric=metric, fact=fact)
    if evidence is None:
        return {"status": "unavailable", "reason_code": "DISPLAY_CANONICAL_FACT_REJECTED", "evidence": None}

    try:
        canonical = Decimal(evidence["canonical_value"])
        display = canonical * Decimal(policy["factor"])
    except (InvalidOperation, ValueError, TypeError, KeyError):
        return {"status": "unavailable", "reason_code": "DISPLAY_VALUE_INVALID", "evidence": None}

    projected = dict(evidence)
    projected.update({
        "canonical_unit": fact.get("unit"),
        "display_value": _display_number(display),
        "display_unit": policy["unit"],
        "rounding_policy": "ROUND_HALF_UP_2_DECIMALS",
        "evidence_id": evidence["request_local_evidence_id"],
        "format_rule": {
            "conversion": policy["conversion"],
            "factor": policy["factor"],
            "decimal_places": 2,
            "rounding": "ROUND_HALF_UP",
            "thousands_separator": True,
        },
    })
    return {"status": "fulfilled", "reason_code": None, "evidence": projected}
