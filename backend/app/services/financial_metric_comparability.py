"""Deterministic metric normalization and comparability checks for Chat comparisons."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.company_v2_field_metadata import get_field_metadata
from app.services.provider_field_registry import get_provider_field_definition


FLOW_METRICS = {"revenue", "parent_net_profit", "operating_cashflow"}
STOCK_METRICS = {"total_assets", "parent_equity"}
RATIO_METRICS = {"roe", "gross_margin", "net_margin"}
PER_SHARE_METRICS = {"eps"}
MONETARY_UNITS = {"元": 1.0, "CNY": 1.0, "万元": 1e4, "亿元": 1e8}
PERCENT_UNITS = {"%", "percent", "percentage_points"}


def infer_period_type(period_end: str | None) -> str:
    period = str(period_end or "")
    if period.endswith("-12-31"):
        return "annual"
    if period.endswith("-06-30"):
        return "semi_annual"
    if period.endswith("-03-31"):
        return "q1"
    if period.endswith("-09-30"):
        return "q3"
    return "unknown" if not period else "point_in_time"


def period_label(metric: dict[str, Any]) -> str:
    period_end = str(metric.get("period_end") or "")
    year = period_end[:4] if len(period_end) >= 4 else str(metric.get("report_year") or "")
    period_type = str(metric.get("period_type") or infer_period_type(period_end))
    if not year:
        return "期间待确认"
    labels = {
        "annual": f"{year}年度口径",
        "semi_annual": f"{year}年中报口径",
        "q1": f"{year}年一季报口径",
        "q3": f"{year}年三季报口径",
        "point_in_time": f"{period_end}时点",
    }
    return labels.get(period_type, f"{period_end}口径" if period_end else "期间待确认")


def value_type_for(metric: str) -> str:
    if metric in FLOW_METRICS:
        return "flow"
    if metric in STOCK_METRICS:
        return "stock"
    if metric in RATIO_METRICS:
        return "ratio"
    if metric in PER_SHARE_METRICS:
        return "per_share"
    return "unknown"


def accounting_scope_for(metric: str) -> str:
    if metric in {"parent_net_profit", "parent_equity"}:
        return "parent"
    return "consolidated"


def _report_year(period_end: str | None) -> int | None:
    try:
        return int(str(period_end or "")[:4])
    except (TypeError, ValueError):
        return None


def _source_type(source: str) -> str:
    if source.startswith("company_v2_history"):
        return "company_history"
    if source.startswith("company_snapshot"):
        return "company_snapshot"
    if source.startswith("rag"):
        return "rag"
    return "official_report_field"


@dataclass(frozen=True)
class MetricNormalizer:
    """Normalize values using source schema/field metadata, never by value size."""

    def normalize(self, item: dict[str, Any] | None, metric: str) -> dict[str, Any] | None:
        if not item:
            return None
        raw_value = item.get("raw_value", item.get("normalized_value"))
        value = self._float(raw_value if raw_value not in (None, "") else item.get("normalized_value"))
        period_end = item.get("period_end") or item.get("period")
        source = str(item.get("source") or "")
        source_type = item.get("source_type") or _source_type(source)
        raw_unit = item.get("raw_unit")
        if raw_unit is None:
            raw_unit = self._raw_unit_from_schema(metric, item)

        warnings: list[str] = list(item.get("warnings") or [])
        validation_status = "normalized"
        normalized_value = None
        normalized_unit = None
        currency = None
        scale = None

        if value is None:
            validation_status = "unverified"
            warnings.append("VALUE_MISSING")
        elif metric in RATIO_METRICS:
            if raw_unit == "ratio":
                normalized_value = value * 100.0
                normalized_unit = "percent"
            elif raw_unit in PERCENT_UNITS:
                normalized_value = value
                normalized_unit = "percent"
            else:
                normalized_value = value
                normalized_unit = "percent" if raw_unit in {"%"} else None
                validation_status = "unverified"
                warnings.append("UNIT_UNKNOWN")
        elif metric in PER_SHARE_METRICS:
            if raw_unit in {"元/股", "CNY/share"}:
                normalized_value = value
                normalized_unit = "CNY/share"
                currency = "CNY"
                scale = 1.0
            else:
                normalized_value = value
                normalized_unit = None
                validation_status = "unverified"
                warnings.append("UNIT_UNKNOWN")
        elif metric in FLOW_METRICS or metric in STOCK_METRICS:
            if raw_unit in MONETARY_UNITS:
                scale = MONETARY_UNITS[str(raw_unit)]
                normalized_value = value * scale
                normalized_unit = "CNY"
                currency = "CNY"
            else:
                normalized_value = value
                normalized_unit = None
                validation_status = "unverified"
                warnings.append("UNIT_UNKNOWN")
        else:
            normalized_value = value
            normalized_unit = item.get("normalized_unit") or item.get("unit")

        if not period_end:
            validation_status = "unverified"
            warnings.append("PERIOD_UNKNOWN")

        metric_id = f"{source_type}:{metric}:{period_end or 'unknown'}:{item.get('source_id') or item.get('evidence_id') or item.get('source_chunk_id') or ''}"
        normalized = {
            **item,
            "metric_id": metric_id,
            "metric": metric,
            "raw_value": raw_value,
            "raw_unit": raw_unit,
            "normalized_value": normalized_value,
            "normalized_unit": normalized_unit,
            "currency": currency,
            "scale": scale,
            "period_start": item.get("period_start"),
            "period_end": period_end,
            "period_type": item.get("period_type") or infer_period_type(period_end),
            "report_year": item.get("report_year") or _report_year(period_end),
            "accounting_scope": item.get("accounting_scope") or accounting_scope_for(metric),
            "value_type": item.get("value_type") or value_type_for(metric),
            "source_id": item.get("source_id") or item.get("evidence_id") or item.get("source_chunk_id"),
            "source_type": source_type,
            "as_of": item.get("as_of") or period_end,
            "validation_status": item.get("validation_status") or validation_status,
            "warnings": sorted(set(warnings)),
        }
        if normalized["validation_status"] == "normalized" and not normalized["warnings"]:
            normalized["validation_status"] = "verified"
        return normalized

    def _raw_unit_from_schema(self, metric: str, item: dict[str, Any]) -> str | None:
        source_key = str(item.get("source_key") or item.get("source_field") or metric)
        source = str(item.get("source") or "")
        provider = str(item.get("source_provider") or "").strip()
        endpoint = str(item.get("source_endpoint") or "").strip()
        if not provider and str(item.get("source_system") or "").startswith("baostock."):
            provider = "baostock"
        if not endpoint and str(item.get("source_system") or "").startswith("baostock."):
            endpoint = str(item.get("source_system")).split(".", 1)[1]
        if provider and endpoint and source_key:
            definition = get_provider_field_definition(provider, endpoint, source_key)
            if definition:
                return definition.raw_unit
        if item.get("unit") in {"元/股", "CNY/share"}:
            return "CNY/share"
        if item.get("unit") in {"元", "万元", "亿元", "CNY"}:
            return str(item.get("unit"))
        if item.get("unit") in {"%", "percent"} and not source.startswith("company_v2_history"):
            return "percent"
        if source.startswith("company_v2_history"):
            meta = get_field_metadata(source_key) or get_field_metadata(metric)
            if meta and meta.semantic_type == "percentage_fraction":
                return "ratio"
            if meta and meta.semantic_type == "percentage_points":
                return "percent"
            if meta and meta.semantic_type == "currency":
                return meta.unit or "CNY"
            if meta and meta.semantic_type in {"ratio", "multiple"}:
                return "ratio"
        if metric in FLOW_METRICS or metric in STOCK_METRICS:
            return "CNY" if item.get("normalized_value") is not None else None
        if metric in PER_SHARE_METRICS:
            return "CNY/share"
        return None

    def _float(self, value: Any) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(str(value).replace(",", "").replace("，", ""))
        except (TypeError, ValueError):
            return None


class FinancialMetricComparabilityService:
    usable_statuses = {"verified", "normalized"}

    def compare(self, left: dict[str, Any] | None, right: dict[str, Any] | None) -> dict[str, Any]:
        reasons: list[str] = []
        if not left or not right:
            return {"comparable": False, "reason_codes": ["MISSING_VALUE"]}
        for side, metric in (("LEFT", left), ("RIGHT", right)):
            if metric.get("normalized_value") is None:
                reasons.append(f"{side}_VALUE_MISSING")
            if metric.get("validation_status") not in self.usable_statuses:
                reasons.append(f"{side}_UNIT_UNVERIFIED" if "UNIT_UNKNOWN" in (metric.get("warnings") or []) else f"{side}_UNVERIFIED")
            if "UNIT_UNKNOWN" in (metric.get("warnings") or []):
                reasons.append(f"{side}_UNIT_UNKNOWN")
        if left.get("metric") != right.get("metric"):
            reasons.append("METRIC_MISMATCH")
        if left.get("normalized_unit") != right.get("normalized_unit"):
            reasons.append("UNIT_MISMATCH")
        if (left.get("currency") or "") != (right.get("currency") or ""):
            reasons.append("CURRENCY_MISMATCH")
        if left.get("period_type") != right.get("period_type"):
            reasons.append("PERIOD_TYPE_MISMATCH")
        if left.get("period_end") != right.get("period_end"):
            reasons.append("PERIOD_END_MISMATCH")
        if left.get("accounting_scope") != right.get("accounting_scope"):
            reasons.append("ACCOUNTING_SCOPE_MISMATCH")
        if left.get("value_type") != right.get("value_type"):
            reasons.append("VALUE_TYPE_MISMATCH")
        if "conflict" in {left.get("validation_status"), right.get("validation_status")}:
            reasons.append("UNRESOLVED_CONFLICT")
        return {"comparable": not reasons, "reason_codes": sorted(set(reasons))}


metric_normalizer = MetricNormalizer()
financial_metric_comparability_service = FinancialMetricComparabilityService()
