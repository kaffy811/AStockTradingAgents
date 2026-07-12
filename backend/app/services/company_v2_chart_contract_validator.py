"""
app/services/company_v2_chart_contract_validator.py — Phase 6T-E 图表契约校验器

验证每个模块的 chart_contract 是否符合数据特征：
1. 单期/时点数据不得使用趋势图（应为 metric_cards）
2. series 字段必须真实存在于 history rows 中（不允许引用不存在字段）
3. 百分比字段量级合理（不允许 100 倍缩放错误）
4. 极端量级（>100x）必须启用副轴或拆分
5. mixed 周期不得直接连成一条趋势线
6. 估值分位需要足够样本（默认 >= 60 个有效点）
7. 金融行业不适用字段不计入契约缺失

不修改数据，只输出真实校验结果。
"""
from __future__ import annotations

from typing import Any

TREND_CHART_TYPES = frozenset({
    "multi_line", "line_chart", "bar_line_combo", "dual_axis_line",
    "grouped_bar", "positive_negative_bar", "zero_baseline_bar",
})

VALUATION_QUANTILE_MIN_SAMPLES = 60
_SCALE_THRESHOLD_DEFAULT = 100
# 百分比字段的合理绝对值上限（百分点）。超过则疑似 100 倍缩放错误。
_PERCENT_ABS_LIMIT = 1000.0


def _series_fields(contract: dict[str, Any]) -> list[dict[str, Any]]:
    return [s for s in (contract.get("series") or []) if isinstance(s, dict)]


def _field_values(rows: list[dict], field: str) -> list[float]:
    out: list[float] = []
    for r in rows:
        v = r.get(field)
        if isinstance(v, (int, float)) and v == v and abs(v) != float("inf"):
            out.append(float(v))
    return out


def _scale_ratio(values: list[float]) -> float:
    nz = [abs(v) for v in values if abs(v) > 1e-10]
    if len(nz) < 2:
        return 1.0
    return max(nz) / min(nz)


def validate_chart_contract(
    module_key: str,
    contract: dict[str, Any],
    *,
    rows: list[dict[str, Any]] | None = None,
    period_type: str = "unknown",
    not_applicable_fields: list[str] | None = None,
) -> dict[str, Any]:
    """
    校验单模块 chart_contract。

    Returns:
        {
          "module_key", "valid": bool,
          "effective_chart": str,     # 数据特征下实际应使用的图表
          "issues": [str],            # 违反契约的问题（导致 valid=False）
          "warnings": [str],          # 提示性问题
        }
    """
    rows = rows or []
    na_fields = set(not_applicable_fields or [])
    issues: list[str] = []
    warnings: list[str] = []

    preferred = str(contract.get("preferred_chart") or "")
    series = _series_fields(contract)
    effective_chart = preferred or "metric_cards"

    if not contract:
        return {
            "module_key": module_key,
            "valid": False,
            "effective_chart": "metric_cards",
            "issues": ["missing_chart_contract"],
            "warnings": [],
        }

    # 1. 单期 / 时点数据 → 必须 metric_cards
    if (len(rows) <= 1 or period_type == "point_in_time") and preferred in TREND_CHART_TYPES:
        effective_chart = "metric_cards"
        warnings.append("single_period_downgraded_to_metric_cards")

    # 2. series 字段必须存在于 rows（排除不适用字段）
    if rows:
        row_keys: set[str] = set()
        for r in rows:
            row_keys.update(r.keys())
        for s in series:
            field = s.get("field") or ""
            if field in na_fields:
                continue
            if field not in row_keys:
                issues.append(f"series_field_not_in_rows:{field}")

    # 3. 百分比量级检查（疑似 100 倍缩放错误）
    for s in series:
        if s.get("display_type") != "percent":
            continue
        field = s.get("field") or ""
        if field in na_fields:
            continue
        values = _field_values(rows, field)
        if values and max(abs(v) for v in values) > _PERCENT_ABS_LIMIT:
            issues.append(f"percent_field_scale_suspicious:{field}")

    # 4. 极端量级检查：>threshold 必须声明副轴/拆分
    threshold = float(contract.get("scale_threshold") or _SCALE_THRESHOLD_DEFAULT)
    applicable_series = [s for s in series if (s.get("field") or "") not in na_fields]
    if len(applicable_series) >= 2 and rows and preferred in TREND_CHART_TYPES:
        means: dict[str, float] = {}
        for s in applicable_series:
            f = s.get("field") or ""
            vals = _field_values(rows, f)
            nz = [abs(v) for v in vals if abs(v) > 1e-10]
            if nz:
                means[f] = sum(nz) / len(nz)
        if len(means) >= 2:
            mx, mn = max(means.values()), min(means.values())
            if mn > 0 and mx / mn > threshold:
                has_axis_split = (
                    contract.get("auto_secondary_axis")
                    or any(s.get("axis") == "secondary" for s in applicable_series)
                )
                if not has_axis_split:
                    issues.append(f"extreme_scale_without_secondary_axis:{round(mx / mn)}x")
                else:
                    warnings.append(f"extreme_scale_uses_secondary_axis:{round(mx / mn)}x")

    # 5. mixed 周期不允许连续趋势线
    if period_type == "mixed" and preferred in ("multi_line", "line_chart", "dual_axis_line"):
        issues.append("mixed_period_must_not_use_continuous_line")
        effective_chart = "grouped_bar"

    # 6. 估值分位样本量
    if module_key == "valuation":
        valid_points = sum(
            1 for r in rows
            if any(isinstance(r.get(s.get("field") or ""), (int, float)) for s in series)
        )
        quantiles_allowed = valid_points >= VALUATION_QUANTILE_MIN_SAMPLES
        if not quantiles_allowed:
            warnings.append(
                f"valuation_quantiles_disabled_insufficient_samples:{valid_points}"
            )
        result_extra = {"quantiles_allowed": quantiles_allowed}
    else:
        result_extra = {}

    # 7. 全部字段不适用 → 契约应降级为 N/A 展示
    if series and all((s.get("field") or "") in na_fields for s in series):
        effective_chart = "not_applicable"
        warnings.append("all_series_not_applicable_for_industry")

    return {
        "module_key": module_key,
        "valid": not issues,
        "effective_chart": effective_chart,
        "issues": issues,
        "warnings": warnings,
        **result_extra,
    }


def validate_all_chart_contracts(
    modules: dict[str, dict[str, Any]],
    *,
    accounting_type: str = "general_industrial",
) -> dict[str, Any]:
    """
    对 history dashboard 的全部模块做图表契约校验。
    """
    from app.services.company_v2_industry_metric_applicability import (
        build_module_applicability,
    )

    results: dict[str, Any] = {}
    invalid: list[str] = []
    for mk, mdata in modules.items():
        contract = mdata.get("chart_contract") or {}
        rows = mdata.get("history") or []
        fields = [s.get("field") or "" for s in contract.get("series") or [] if isinstance(s, dict)]
        applicability = build_module_applicability(mk, fields, accounting_type)
        result = validate_chart_contract(
            mk, contract,
            rows=rows,
            period_type=mdata.get("period_type") or "unknown",
            not_applicable_fields=applicability["not_applicable_fields"],
        )
        result["not_applicable_fields"] = applicability["not_applicable_fields"]
        results[mk] = result
        if not result["valid"]:
            invalid.append(mk)

    return {
        "modules": results,
        "all_valid": not invalid,
        "invalid_modules": invalid,
    }
