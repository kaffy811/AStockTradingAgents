"""
profitability.py — 盈利能力分析

数据源：Tushare fina_indicator（primary）+ income（费用率 fallback）
  - 优先使用 fina_indicator 的利润率字段（grossprofit_margin / netprofit_margin / roe / roa / roic）
  - 费用率从 income 自行计算（分母=total_revenue；<=0 → null）
  - 缺失字段返回 null
"""
from __future__ import annotations
import asyncio, logging
from typing import Any
import pandas as pd
from app.datasource.tushare_client import tushare_client, _to_ts_code
from app.tools.fundamental.base import BaseFundamentalTool, FundamentalToolError
from app.tools.fundamental._helpers import (
    safe_float, safe_pct, fmt_date, filter_report_type, filter_annual, row_get
)
log = logging.getLogger(__name__)


def _comment(series: list[dict]) -> str:
    if not series: return "数据不足。"
    l = series[0]
    parts = []
    roe = l.get("roe_pct")
    nm = l.get("net_margin_pct")
    if roe is not None: parts.append(f"ROE {roe:.1f}%")
    if nm is not None:  parts.append(f"净利率 {nm:.1f}%")
    return f"{l.get('end_date','')} {'; '.join(parts)}。" if parts else "盈利能力数据暂缺。"


class ProfitabilityTool(BaseFundamentalTool):
    module_key = "profitability"
    cache_ttl_seconds = 14400
    stale_ttl_seconds = 172800

    def __init__(self, limit: int = 8, annual: bool = True):
        self.limit = limit
        self.annual = annual

    async def fetch(self, market: str, symbol: str) -> dict[str, Any]:
        ts_code = _to_ts_code(market, symbol)
        api_limit = self.limit * 4 if self.annual else self.limit

        fi_task  = tushare_client.get_fina_indicator(ts_code=ts_code)
        inc_task = tushare_client.get_income(ts_code=ts_code, limit=api_limit)
        fi_result, inc_result = await asyncio.gather(fi_task, inc_task, return_exceptions=True)

        partial_errors: list[str] = []
        fi_df, inc_df = pd.DataFrame(), pd.DataFrame()

        if isinstance(fi_result, Exception):
            partial_errors.append(f"fina_indicator 失败: {fi_result}")
        else:
            fi_df = fi_result.copy()
            if self.annual: fi_df = filter_annual(fi_df)
            fi_df = fi_df.sort_values("end_date", ascending=False).head(self.limit)

        inc_by_date: dict[str, Any] = {}
        if isinstance(inc_result, Exception):
            partial_errors.append(f"income 失败: {inc_result}")
        else:
            inc_df_raw = filter_report_type(inc_result)
            if self.annual: inc_df_raw = filter_annual(inc_df_raw)
            for _, row in inc_df_raw.iterrows():
                inc_by_date[str(row_get(row, "end_date") or "")] = row

        if fi_df.empty:
            raise FundamentalToolError("fina_indicator 无数据")

        series = []
        for _, row in fi_df.iterrows():
            date_raw = str(row_get(row, "end_date") or "")
            inc_row = inc_by_date.get(date_raw, {})
            rev = safe_float(row_get(inc_row, "total_revenue"))

            # 费用率：从 income 计算
            sell_r = safe_pct(row_get(inc_row, "sell_exp"), rev)
            admin_r = safe_pct(row_get(inc_row, "admin_exp"), rev)
            fin_r   = safe_pct(row_get(inc_row, "fin_exp"), rev)
            expense_r: float | None = None
            if sell_r is not None and admin_r is not None and fin_r is not None:
                expense_r = round(sell_r + admin_r + fin_r, 2)

            series.append({
                "end_date":               fmt_date(date_raw),
                "gross_margin_pct":       safe_float(row_get(row, "grossprofit_margin")),
                "net_margin_pct":         safe_float(row_get(row, "netprofit_margin")),
                "roe_pct":                safe_float(row_get(row, "roe")),
                "roa_pct":                safe_float(row_get(row, "roa")),
                "roic_pct":               safe_float(row_get(row, "roic")),
                "expense_ratio_pct":      expense_r,
                "sales_expense_ratio_pct":  sell_r,
                "admin_expense_ratio_pct":  admin_r,
                "finance_expense_ratio_pct": fin_r,
            })

        result: dict[str, Any] = {
            "symbol": symbol, "ts_code": ts_code,
            "annual": self.annual,
            "series": series,
            "comment": _comment(series),
            "source": "tushare",
        }
        if partial_errors:
            result["_partial_errors"] = partial_errors
        return result
