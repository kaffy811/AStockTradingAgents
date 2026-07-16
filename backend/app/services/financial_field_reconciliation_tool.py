"""Financial field reconciliation for Company V2 and report chat."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


_SOURCE_PRIORITY = {
    "official_report_table": 1,
    "official_xbrl": 2,
    "baostock_verified": 3,
    "akshare_http": 4,
    "formula": 5,
}


@dataclass
class FinancialFieldCandidate:
    field: str
    value: float | int | None
    unit: str
    period_end: str
    source_type: str
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "value": self.value,
            "unit": self.unit,
            "period_end": self.period_end,
            "source_type": self.source_type,
            "provenance": self.provenance,
        }


class FinancialFieldReconciliationTool:
    def reconcile(
        self,
        *,
        symbol: str,
        period_end: str,
        field: str,
        candidates: list[FinancialFieldCandidate | dict[str, Any]],
        tolerance_ratio: float = 0.01,
    ) -> dict[str, Any]:
        normalized = [self._candidate(item) for item in candidates]
        normalized = [item for item in normalized if item.field == field and item.period_end == period_end and item.value is not None]
        normalized.sort(key=lambda item: _SOURCE_PRIORITY.get(item.source_type, 99))
        if not normalized:
            return {
                "symbol": symbol,
                "period_end": period_end,
                "field": field,
                "canonical_value": None,
                "unit": None,
                "source_type": None,
                "candidates": [],
                "conflict": False,
                "warnings": ["NO_CANDIDATES"],
            }
        canonical = normalized[0]
        warnings: list[str] = []
        conflict = False
        for item in normalized[1:]:
            if item.unit != canonical.unit:
                conflict = True
                warnings.append("UNIT_CONFLICT")
                continue
            diff = abs(float(item.value) - float(canonical.value))
            denominator = max(abs(float(canonical.value)), abs(float(item.value)), 1e-12)
            if diff / denominator > tolerance_ratio:
                conflict = True
                warnings.append("FIELD_CONFLICT")
        return {
            "symbol": symbol,
            "period_end": period_end,
            "field": field,
            "canonical_value": canonical.value,
            "unit": canonical.unit,
            "source_type": canonical.source_type,
            "provenance": canonical.provenance,
            "candidates": [item.to_dict() for item in normalized],
            "conflict": conflict,
            "warnings": sorted(set(warnings)),
        }

    def _candidate(self, value: FinancialFieldCandidate | dict[str, Any]) -> FinancialFieldCandidate:
        if isinstance(value, FinancialFieldCandidate):
            return value
        return FinancialFieldCandidate(
            field=str(value.get("field") or ""),
            value=value.get("value", value.get("normalized_value")),
            unit=str(value.get("unit") or ""),
            period_end=str(value.get("period_end") or ""),
            source_type=str(value.get("source_type") or value.get("source") or ""),
            provenance=dict(value.get("provenance") or value),
        )


financial_field_reconciliation_tool = FinancialFieldReconciliationTool()

