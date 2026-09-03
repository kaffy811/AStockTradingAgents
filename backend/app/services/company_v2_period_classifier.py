"""
app/services/company_v2_period_classifier.py — Phase 6T-E 权威期间分类器

后端为期间/口径分类的权威来源；前端 companyV2PeriodClassifier.js 仅做兼容 fallback。

period_type（模块级）：
- annual | quarterly | daily | point_in_time | mixed | unknown

value_basis（行级）：
- annual_cumulative     年度报告累计值（YYYY-12-31 + 年报口径）
- quarterly_cumulative  季度累计值（如三季报 1-9 月累计）
- single_quarter        单季度值
- point_in_time         时点值（资产负债表类）
- ttm                   滚动 12 个月
- current_market        当前行情/日频（PE/PB 等）
- unknown

注意：
YYYY-12-31 可能同时存在年度报告和第四季度累计数据，
必须依靠 report_period_type / value_basis 区分，不能只看日期。

安全原则：
- 不把缺失值当 0
- 不提供投资建议
"""
from __future__ import annotations

from datetime import date
import re
from typing import Any

_RE_ANNUAL_END = re.compile(r"^\d{4}-12-31$")
_RE_QUARTER_END = re.compile(r"^\d{4}-(03-31|06-30|09-30|12-31)$")
_RE_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_QUARTER_BY_MONTH = {"03": 1, "06": 2, "09": 3, "12": 4}

VALID_PERIOD_TYPES = frozenset({
    "annual", "quarterly", "daily", "point_in_time", "mixed", "unknown",
})
VALID_VALUE_BASIS = frozenset({
    "annual_cumulative", "quarterly_cumulative", "single_quarter",
    "point_in_time", "ttm", "current_market", "unknown",
})

# 时点口径字段（资产负债表类），出现这些字段的行属于 point_in_time 口径
_POINT_IN_TIME_FIELDS = frozenset({
    "current_ratio", "quick_ratio", "cash_ratio", "debt_ratio", "equity_multiplier",
})
# TTM 口径字段
_TTM_FIELD_SUFFIXES = ("_ttm",)
# 当前行情口径字段
_CURRENT_MARKET_FIELDS = frozenset({
    "pe_ttm", "pb", "ps_ttm", "pcf_ncf_ttm", "market_cap", "float_market_cap",
    "latest_price", "recent_close",
})


def is_valid_period(period: str) -> bool:
    """period 是否为合法日期字符串（YYYY-MM-DD）。"""
    return bool(period) and bool(_RE_DATE.match(str(period)))


def is_quarter_end(period: str) -> bool:
    return bool(_RE_QUARTER_END.match(str(period or "")))


def is_annual_end(period: str) -> bool:
    return bool(_RE_ANNUAL_END.match(str(period or "")))


def resolve_quarterly_window(
    as_of_date: date,
    *,
    years: int = 5,
    latest_disclosed_period: str | None = None,
) -> dict[str, Any]:
    """
    Resolve the quarterly window used by Phase 6T-E2 Deep Acceptance.

    The default is the most recent complete financial years, independent of
    listing date. Future or not-yet-disclosed periods are reported separately
    and excluded from valid_quarters/expected_periods.
    """
    if years <= 0:
        raise ValueError("years must be positive")

    if latest_disclosed_period and is_quarter_end(latest_disclosed_period):
        end_year = int(latest_disclosed_period[:4])
        latest_allowed = latest_disclosed_period
    else:
        end_year = as_of_date.year - 1
        latest_allowed = f"{end_year}-12-31"

    start_year = end_year - years + 1
    quarter_ends = ("03-31", "06-30", "09-30", "12-31")
    expected_periods: list[str] = []
    excluded_future_periods: list[str] = []
    valid_quarters: list[tuple[int, int]] = []

    for year in range(start_year, end_year + 1):
        for quarter, suffix in enumerate(quarter_ends, start=1):
            period = f"{year}-{suffix}"
            if period <= latest_allowed and period < as_of_date.isoformat():
                expected_periods.append(period)
                valid_quarters.append((year, quarter))
            else:
                excluded_future_periods.append(period)

    return {
        "start_year": start_year,
        "end_year": end_year,
        "valid_quarters": valid_quarters,
        "expected_periods": expected_periods,
        "excluded_future_periods": excluded_future_periods,
        "latest_disclosed_period": latest_allowed,
    }


def classify_period_date(period: str) -> str:
    """
    单个 period 日期的类型：
    annual_end | quarter_end | daily | invalid
    （annual_end 同时也是 quarter_end；此处返回最具体的年末标记）
    """
    p = str(period or "")
    if not is_valid_period(p):
        return "invalid"
    if is_annual_end(p):
        return "annual_end"
    if is_quarter_end(p):
        return "quarter_end"
    return "daily"


def infer_report_period_type(period: str, *, requested_period: str = "") -> str:
    """
    从 period 日期推断 report_period_type：
    - YYYY-12-31 → annual（若请求口径为 quarterly，则记为 q4_cumulative 的季度口径，仍返回 annual 日期语义由 value_basis 区分）
    - 其他季度末 → quarterly
    - 其他合法日期 → daily
    - 非法 → unknown
    """
    kind = classify_period_date(period)
    if kind == "annual_end":
        return "annual"
    if kind == "quarter_end":
        return "quarterly"
    if kind == "daily":
        return "daily"
    return "unknown"


def infer_value_basis(
    period: str,
    *,
    module_key: str = "",
    source_table: str = "",
    requested_period: str = "",
) -> str:
    """
    推断行级 value_basis。

    BaoStock 季频指标接口（profit/growth/operation/cashflow/dupont）返回的是
    累计口径（Q1/半年/三季/年度累计）；balance 表为时点口径。
    valuation（PE/PB 等）为当前行情口径。
    """
    if module_key in ("valuation", "quote_overview"):
        return "current_market"
    if module_key == "solvency" or source_table == "balance":
        return "point_in_time"
    kind = classify_period_date(period)
    if kind == "annual_end":
        # 年末日期：BaoStock 季频接口的 12-31 行是年度累计（同时也是 Q4 累计）
        return "annual_cumulative"
    if kind == "quarter_end":
        return "quarterly_cumulative"
    if kind == "daily":
        return "current_market"
    return "unknown"


def classify_rows_period_type(rows: list[dict[str, Any]]) -> str:
    """
    模块级 period_type 权威分类。

    - 空 → unknown
    - 1 行 → point_in_time
    - 全部年末 → annual
    - 全部季度末 → quarterly
    - 年末+季度末混合但含非年末季度 → quarterly（季度序列天然包含 12-31）
    - 含日频与报告期混合 → mixed
    """
    if not rows:
        return "unknown"
    periods = [str(r.get("period") or "") for r in rows if r.get("period")]
    if not periods:
        return "unknown"
    if len(rows) == 1:
        return "point_in_time"

    kinds = {classify_period_date(p) for p in periods}
    kinds.discard("invalid")
    if not kinds:
        return "unknown"
    if kinds == {"annual_end"}:
        return "annual"
    if kinds <= {"annual_end", "quarter_end"}:
        # 季度序列包含年末季度，属正常 quarterly
        return "quarterly" if "quarter_end" in kinds else "annual"
    if kinds == {"daily"}:
        return "daily"
    return "mixed"


def enrich_row(
    row: dict[str, Any],
    *,
    module_key: str = "",
    source_table: str = "",
    source_provider: str = "baostock",
    requested_period: str = "",
    publish_date: str | None = None,
) -> dict[str, Any]:
    """
    为 history 行补充权威分类字段（就地更新并返回）：
    - report_year / quarter
    - report_period_type
    - value_basis
    - publish_date（可得时）
    - source_provider
    """
    period = str(row.get("period") or "")
    report_year: int | None = None
    quarter: int | None = None
    if is_valid_period(period):
        try:
            report_year = int(period[:4])
        except ValueError:
            report_year = None
        quarter = _QUARTER_BY_MONTH.get(period[5:7]) if is_quarter_end(period) else None

    row["report_year"] = report_year
    row["quarter"] = quarter
    row["report_period_type"] = infer_report_period_type(period, requested_period=requested_period)
    row["value_basis"] = infer_value_basis(
        period,
        module_key=module_key,
        source_table=source_table,
        requested_period=requested_period,
    )
    if publish_date is not None:
        row["publish_date"] = publish_date
    elif "publish_date" not in row:
        row["publish_date"] = row.get("pub_date") or None
    row["source_provider"] = source_provider
    return row
