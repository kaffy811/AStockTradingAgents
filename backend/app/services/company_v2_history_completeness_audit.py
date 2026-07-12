"""
app/services/company_v2_history_completeness_audit.py — Phase 6T-E 历史数据完整性审计

对每只股票、每个模块的 history rows 做真实审计：
- period 合法性 / 升序 / 重复 / 未来报告期 / 早于上市日期
- annual 是否只保留年度口径；quarterly 是否为合法季度末日期
- latest 是否来自 history 中最新有效一期
- 无效值（空字符串 / NaN / Infinity）不得当成有效数据
- history_truncated 必须真实反映 provider 能力

不伪造数据；缺失即如实记录。
"""
from __future__ import annotations

import math
from datetime import date
from typing import Any

from app.services.company_v2_period_classifier import (
    classify_period_date,
    is_annual_end,
    is_quarter_end,
    is_valid_period,
)

_META_FIELDS = frozenset({
    "period", "source", "report_year", "quarter", "report_period_type",
    "value_basis", "publish_date", "source_provider",
})


def _is_invalid_value(v: Any) -> bool:
    """空字符串 / NaN / Infinity 视为无效值。"""
    if isinstance(v, str):
        return v.strip() == ""
    if isinstance(v, float):
        return math.isnan(v) or math.isinf(v)
    return False


def _row_has_any_valid_value(row: dict[str, Any]) -> bool:
    for k, v in row.items():
        if k in _META_FIELDS:
            continue
        if v is None or _is_invalid_value(v):
            continue
        if isinstance(v, (int, float)):
            return True
    return False


def _expected_periods(
    period_type: str,
    start_year: int,
    end_year: int,
    *,
    today: date,
) -> list[str]:
    """生成截至今天已应存在的报告期列表（不含未来期）。"""
    result: list[str] = []
    quarter_ends = ["03-31", "06-30", "09-30", "12-31"]
    for year in range(start_year, end_year + 1):
        if period_type == "annual":
            candidates = [f"{year}-12-31"]
        elif period_type == "quarterly":
            candidates = [f"{year}-{q}" for q in quarter_ends]
        else:
            candidates = []
        for p in candidates:
            # 报告期披露有滞后：只统计报告期结束早于今天的期数
            if p < today.isoformat():
                result.append(p)
    return result


def audit_module_history(
    module_key: str,
    module_data: dict[str, Any],
    *,
    list_date: str = "",
    requested_period: str = "quarterly",
    start_year: int | None = None,
    end_year: int | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """
    审计单个模块的 history。

    Returns（history_quality 契约）:
    {
      "rows_count", "start_period", "end_period",
      "expected_periods_count", "missing_periods",
      "duplicate_periods", "out_of_order_periods", "invalid_periods",
      "future_periods", "pre_listing_periods",
      "history_truncated", "completeness_pct",
      "latest_matches_history", "period_order_valid",
      "status": "pass"|"warning"|"fail",
      "warnings": [...],
    }
    """
    today = today or date.today()
    rows: list[dict[str, Any]] = module_data.get("history") or module_data.get("rows") or []
    latest: dict[str, Any] = module_data.get("latest") or {}
    period_type = module_data.get("period_type") or "unknown"

    periods = [str(r.get("period") or "") for r in rows]

    warnings: list[str] = []
    invalid_periods = [p for p in periods if not is_valid_period(p)]
    valid_periods = [p for p in periods if is_valid_period(p)]

    # 重复
    seen: set[str] = set()
    duplicate_periods: list[str] = []
    for p in valid_periods:
        if p in seen:
            duplicate_periods.append(p)
        seen.add(p)

    # 升序
    out_of_order: list[str] = []
    for i in range(1, len(valid_periods)):
        if valid_periods[i] < valid_periods[i - 1]:
            out_of_order.append(valid_periods[i])
    period_order_valid = not out_of_order

    # 未来报告期
    today_str = today.isoformat()
    future_periods = [p for p in valid_periods if p > today_str]

    # 早于上市日期（上市当季/当年允许，只有明显早于上市年份才计）
    pre_listing: list[str] = []
    if list_date and is_valid_period(list_date):
        list_year = int(list_date[:4])
        pre_listing = [p for p in valid_periods if int(p[:4]) < list_year]

    # 口径检查
    if requested_period == "annual":
        non_annual = [p for p in valid_periods if not is_annual_end(p)]
        if non_annual:
            warnings.append(f"annual_mode_contains_non_annual_periods:{len(non_annual)}")
    quarter_invalid = [p for p in valid_periods if classify_period_date(p) == "daily"]
    if requested_period in ("quarterly", "all") and quarter_invalid:
        warnings.append(f"quarterly_mode_contains_non_quarter_end:{len(quarter_invalid)}")

    # latest 一致性：latest.period 必须等于 history 中最新有效行的 period
    latest_matches_history = True
    if rows:
        valid_rows = [r for r in rows if is_valid_period(str(r.get("period") or "")) and _row_has_any_valid_value(r)]
        if valid_rows:
            newest = max(valid_rows, key=lambda r: str(r.get("period")))
            latest_matches_history = str(latest.get("period") or "") == str(newest.get("period") or "")
        else:
            latest_matches_history = not latest
    else:
        latest_matches_history = not latest

    # 无效值行
    rows_with_invalid_values = sum(
        1 for r in rows
        if any(_is_invalid_value(v) for k, v in r.items() if k not in _META_FIELDS)
    )
    if rows_with_invalid_values:
        warnings.append(f"rows_with_invalid_values:{rows_with_invalid_values}")

    # 期望期数与缺失
    sy = start_year
    if sy is None and list_date and is_valid_period(list_date):
        sy = int(list_date[:4])
    ey = end_year or today.year
    eff_type = requested_period if requested_period in ("annual", "quarterly") else (
        period_type if period_type in ("annual", "quarterly") else "quarterly"
    )
    expected: list[str] = _expected_periods(eff_type, sy, ey, today=today) if sy else []
    missing_periods = [p for p in expected if p not in seen] if expected else []
    expected_count = len(expected) if expected else len(valid_periods)

    completeness_pct = (
        round(len(set(valid_periods)) / expected_count * 100)
        if expected_count else 0
    )
    history_truncated = bool(missing_periods) or len(set(valid_periods)) < expected_count

    # status 判定
    if future_periods or pre_listing or duplicate_periods or not period_order_valid or not latest_matches_history:
        status = "fail"
    elif invalid_periods or warnings or (expected and completeness_pct < 60):
        status = "warning"
    elif not rows:
        status = "warning"
        warnings.append("no_history_rows")
    else:
        status = "pass"

    return {
        "module_key": module_key,
        "rows_count": len(rows),
        "start_period": valid_periods[0] if valid_periods else "",
        "end_period": valid_periods[-1] if valid_periods else "",
        "expected_periods_count": expected_count,
        "missing_periods": missing_periods[:40],
        "duplicate_periods": duplicate_periods,
        "out_of_order_periods": out_of_order,
        "invalid_periods": invalid_periods,
        "future_periods": future_periods,
        "pre_listing_periods": pre_listing,
        "history_truncated": history_truncated,
        "completeness_pct": completeness_pct,
        "period_order_valid": period_order_valid,
        "latest_matches_history": latest_matches_history,
        "duplicate_period_count": len(duplicate_periods),
        "invalid_period_count": len(invalid_periods),
        "status": status,
        "warnings": warnings,
    }


def audit_symbol_history(
    symbol: str,
    dashboard: dict[str, Any],
    *,
    today: date | None = None,
) -> dict[str, Any]:
    """
    对 build_company_history_dashboard 的输出做整体审计。
    """
    today = today or date.today()
    stock_basic = dashboard.get("stock_basic") or {}
    list_date = stock_basic.get("list_date") or ""
    requested_period = dashboard.get("period") or "quarterly"
    start_year = dashboard.get("start_year")
    end_year = dashboard.get("end_year")

    modules_audit: dict[str, Any] = {}
    statuses: list[str] = []
    for mk, mdata in (dashboard.get("modules") or {}).items():
        audit = audit_module_history(
            mk, mdata,
            list_date=list_date,
            requested_period=requested_period if requested_period != "all" else "quarterly",
            start_year=start_year,
            end_year=end_year,
            today=today,
        )
        modules_audit[mk] = audit
        statuses.append(audit["status"])

    if "fail" in statuses:
        overall = "fail"
    elif "warning" in statuses:
        overall = "warning"
    elif statuses:
        overall = "pass"
    else:
        overall = "fail"

    return {
        "symbol": symbol,
        "list_date": list_date,
        "requested_start_year": start_year,
        "requested_end_year": end_year,
        "period_type": requested_period,
        "modules": modules_audit,
        "overall_status": overall,
    }


def build_history_quality(module_audit: dict[str, Any]) -> dict[str, Any]:
    """从模块审计结果提取简化 history_quality 块（用于 API 响应）。"""
    return {
        "status": module_audit.get("status", "fail"),
        "completeness_pct": module_audit.get("completeness_pct", 0),
        "duplicate_period_count": module_audit.get("duplicate_period_count", 0),
        "invalid_period_count": module_audit.get("invalid_period_count", 0),
        "period_order_valid": module_audit.get("period_order_valid", False),
        "latest_matches_history": module_audit.get("latest_matches_history", False),
        "warnings": module_audit.get("warnings", []),
    }
