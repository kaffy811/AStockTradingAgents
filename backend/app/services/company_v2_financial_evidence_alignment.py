"""Alignment checks between structured and official financial evidence."""
from __future__ import annotations

import re
from typing import Any

from app.services.company_v2_financial_field_definition_registry import get_field_definition
from app.services.company_v2_financial_unit_normalizer import units_compatible


def _period_basis(period: str | None, field_name: str | None = None) -> str:
    field_name = field_name or ""
    if field_name in {"total_share", "float_share"}:
        return "point_in_time"
    period = str(period or "")
    if period.endswith(("03-31", "06-30", "09-30")):
        return "quarterly_cumulative"
    if period.endswith("12-31"):
        return "annual_cumulative"
    return "unknown"


def _same_definition(field_name: str, provider_definition: str | None, official_definition: str | None) -> bool:
    definition = get_field_definition(field_name)
    if not definition:
        return provider_definition == official_definition
    def _norm(text: str | None) -> str:
        return re.sub(r"\s+", "", str(text or "")).lower()

    provider = _norm(provider_definition)
    official = _norm(official_definition)
    field = _norm(field_name)
    canonical = _norm(definition.canonical_name)
    accepted = {
        _norm(definition.key),
        canonical,
        *(_norm(item) for item in definition.aliases),
        *(_norm(item) for item in definition.official_report_labels),
        *(_norm(item) for item in definition.provider_labels),
    }
    incompatible = {
        *(_norm(item) for item in definition.incompatible_definitions),
        *(_norm(item) for item in definition.incompatible_with),
    }
    if provider in incompatible or official in incompatible:
        return False
    if provider == official:
        return True
    if provider in accepted and official in accepted:
        return True
    if provider == field and official in accepted | {canonical}:
        return True
    if official == field and provider in accepted | {canonical}:
        return True
    return False


def align_financial_evidence(
    *,
    symbol: str,
    report_id: int,
    report_year: int | None,
    report_type: str | None,
    field_name: str,
    provider_definition: str | None,
    provider_period: str | None,
    provider_value_basis: str | None,
    provider_unit: str | None,
    official_definition: str | None,
    official_period: str | None,
    official_value_basis: str | None,
    official_unit: str | None,
) -> dict[str, Any]:
    same_symbol = bool(symbol)
    same_report = report_id is not None
    same_definition = _same_definition(field_name, provider_definition, official_definition)
    same_period = bool(provider_period and official_period and str(provider_period) == str(official_period))
    same_value_basis = str(provider_value_basis or "unknown") == str(official_value_basis or "unknown")
    unit_convertible = units_compatible(provider_unit, official_unit)
    comparable = same_symbol and same_report and same_definition and same_period and same_value_basis and unit_convertible

    if not same_symbol or not same_report:
        status = "failed"
    elif not same_definition:
        status = "definition_mismatch"
    elif not same_period:
        status = "period_basis_mismatch"
    elif not same_value_basis:
        status = "period_basis_mismatch"
    elif not unit_convertible:
        status = "unit_mismatch"
    else:
        status = "comparable"

    warnings: list[str] = []
    if same_definition and not same_period:
        warnings.append("period mismatch between structured and official evidence")
    if same_definition and same_period and not same_value_basis:
        warnings.append("value basis mismatch between structured and official evidence")
    if not unit_convertible:
        warnings.append("unit not safely convertible")

    return {
        "same_symbol": same_symbol,
        "same_report": same_report,
        "same_period": same_period,
        "same_definition": same_definition,
        "same_value_basis": same_value_basis,
        "unit_convertible": unit_convertible,
        "comparable": comparable,
        "status": status,
        "warnings": warnings,
        "structured_period_basis": _period_basis(provider_period, field_name),
        "official_period_basis": _period_basis(official_period, field_name),
    }


company_v2_financial_evidence_alignment = align_financial_evidence
