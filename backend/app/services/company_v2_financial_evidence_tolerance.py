"""Tolerance profiles for financial evidence fusion."""
from __future__ import annotations

from typing import Any

from app.services.company_v2_financial_field_definition_registry import get_field_definition


def get_financial_tolerance(field_name: str, provider_value: Any, official_value: Any) -> dict[str, Any]:
    definition = get_field_definition(field_name)
    expected_unit = definition.expected_unit if definition else None
    if expected_unit in {"%", "percentage points"} or field_name in {"roe", "roe_weighted"}:
        return {
            "field_name": field_name,
            "absolute_tolerance": 0.0005,
            "relative_tolerance": 0.005,
            "unit": "%",
            "basis": "percentage",
        }
    if expected_unit == "shares" or field_name in {"total_share", "float_share"}:
        return {
            "field_name": field_name,
            "absolute_tolerance": 1.0,
            "relative_tolerance": 0.001,
            "unit": "shares",
            "basis": "share_count",
        }
    if expected_unit == "CNY/share" or field_name == "eps_basic":
        return {
            "field_name": field_name,
            "absolute_tolerance": 0.01,
            "relative_tolerance": 0.005,
            "unit": "CNY/share",
            "basis": "eps",
        }
    return {
        "field_name": field_name,
        "absolute_tolerance": 1.0,
        "relative_tolerance": 0.005,
        "unit": "CNY",
        "basis": "monetary",
    }


def within_tolerance(field_name: str, provider_value: float | None, official_value: float | None) -> dict[str, Any]:
    profile = get_financial_tolerance(field_name, provider_value, official_value)
    if provider_value is None or official_value is None:
        profile.update({"within_tolerance": False, "absolute_diff": None, "relative_diff": None})
        return profile
    abs_diff = abs(float(provider_value) - float(official_value))
    denom = max(abs(float(provider_value)), abs(float(official_value)), 1e-12)
    rel_diff = abs_diff / denom
    if profile["basis"] == "percentage":
        within = abs_diff <= profile["absolute_tolerance"]
    elif profile["basis"] == "share_count":
        within = abs_diff <= profile["absolute_tolerance"] or rel_diff <= profile["relative_tolerance"]
    else:
        within = abs_diff <= profile["absolute_tolerance"] or rel_diff <= profile["relative_tolerance"]
    profile.update({
        "within_tolerance": within,
        "absolute_diff": abs_diff,
        "relative_diff": rel_diff,
    })
    return profile


company_v2_financial_evidence_tolerance = within_tolerance
