"""Unit normalization helpers for Company V2 financial fusion."""
from __future__ import annotations

from dataclasses import dataclass
from dataclasses import asdict
from typing import Any


MONETARY_UNITS = {
    "元": 1.0,
    "千元": 1e3,
    "万元": 1e4,
    "百万元": 1e6,
    "亿元": 1e8,
    "CNY": 1.0,
}

SHARE_UNITS = {
    "股": 1.0,
    "shares": 1.0,
    "万股": 1e4,
    "亿股": 1e8,
}

PERCENT_UNITS = {"%": 1.0, "percentage points": 1.0}
EPS_UNITS = {"CNY/share": 1.0, "元/股": 1.0, "元/每股": 1.0}


@dataclass(slots=True)
class NormalizedValue:
    original_value: Any
    original_unit: str | None
    normalized_value: Any
    normalized_unit: str | None
    conversion_factor: float | None
    conversion_trace: str | None
    status: str
    warnings: list[str]


def _is_number(value: Any) -> bool:
    try:
        return value is not None and value != "" and float(value) == float(value)
    except Exception:
        return False


def _canonical_unit(unit: str | None) -> str | None:
    if unit is None:
        return None
    unit = str(unit).strip()
    if unit in {"元", "千元", "万元", "百万元", "亿元", "CNY"}:
        return "CNY"
    if unit in EPS_UNITS:
        return "CNY/share"
    if unit in {"股", "shares", "万股", "亿股"}:
        return "shares"
    if unit in {"%", "percentage points"}:
        return "%"
    return unit or None


def _factor(unit: str | None) -> float | None:
    if unit is None:
        return None
    if unit in MONETARY_UNITS:
        return MONETARY_UNITS[unit]
    if unit in SHARE_UNITS:
        return SHARE_UNITS[unit]
    if unit in PERCENT_UNITS:
        return PERCENT_UNITS[unit]
    return None


def normalize_financial_value(
    value: Any,
    unit: str | None,
    *,
    target_unit: str | None = None,
) -> dict[str, Any]:
    warnings: list[str] = []
    if value is None:
        return asdict(NormalizedValue(value, unit, None, _canonical_unit(target_unit or unit), None, None, "missing", warnings))

    if not _is_number(value):
        return asdict(NormalizedValue(value, unit, value, _canonical_unit(target_unit or unit), None, None, "unknown_value", ["non_numeric_value"]))

    numeric = float(value)
    canonical = _canonical_unit(unit)
    target = _canonical_unit(target_unit or unit)
    if canonical is None:
        return asdict(NormalizedValue(value, unit, numeric, target, None, None, "unknown_unit", ["unknown_unit"]))

    if target and canonical != target and {canonical, target} in [{"CNY", "CNY"}, {"shares", "shares"}]:
        # Canonical units already match; this branch remains for explicit requests.
        pass

    if canonical == "CNY":
        factor = _factor(unit)
        if factor is None:
            return asdict(NormalizedValue(value, unit, numeric, "CNY", None, None, "unknown_unit", ["unknown_unit"]))
        normalized = numeric * factor
        return asdict(NormalizedValue(value, unit, normalized, "CNY", factor, f"{unit}→CNY", "normalized", warnings))

    if canonical == "shares":
        factor = _factor(unit)
        if factor is None:
            return asdict(NormalizedValue(value, unit, numeric, "shares", None, None, "unknown_unit", ["unknown_unit"]))
        normalized = numeric * factor
        return asdict(NormalizedValue(value, unit, normalized, "shares", factor, f"{unit}→shares", "normalized", warnings))

    if canonical == "%":
        if target and target not in {"%", "percentage points"}:
            return asdict(NormalizedValue(value, unit, numeric, target, None, None, "unit_mismatch", ["unit_not_convertible"]))
        return asdict(NormalizedValue(value, unit, numeric, "%", 1.0, f"{unit}→%", "normalized", warnings))

    if canonical == "CNY/share":
        if target and target not in {"CNY/share"}:
            return asdict(NormalizedValue(value, unit, numeric, target, None, None, "unit_mismatch", ["unit_not_convertible"]))
        return asdict(NormalizedValue(value, unit, numeric, "CNY/share", 1.0, f"{unit}→CNY/share", "normalized", warnings))

    return asdict(NormalizedValue(value, unit, numeric, canonical, None, None, "unknown_unit", ["unknown_unit"]))


def units_compatible(left_unit: str | None, right_unit: str | None) -> bool:
    left = _canonical_unit(left_unit)
    right = _canonical_unit(right_unit)
    if left is None or right is None:
        return False
    return left == right


company_v2_financial_unit_normalizer = normalize_financial_value
