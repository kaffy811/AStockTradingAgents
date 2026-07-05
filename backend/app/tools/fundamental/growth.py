"""
growth.py — 成长性分析

数据源：Tushare income + fina_indicator（concurrent）
  - yoy 同比优先用 fina_indicator 官方字段（or_yoy / netprofit_yoy / dt_netprofit_yoy）
  - 缺失时返回 null + reason，不强行编造
  - 支持 annual=True（年报）和 annual=False（所有累计口径）

返回：end_date / revenue / revenue_yoy_pct / net_profit_parent /
       net_profit_yoy_pct / deduct_net_profit / deduct_net_profit_yoy_pct /
       roe_pct / eps / comment
"""
from __future__ import annotations
import asyncio, logging
from typing import Any
import pandas as pd
from app.datasource.tushare_client import tushare_client, _to_ts_code
from app.tools.fundamental.base import BaseFundamentalTool, FundamentalToolError
from app.tools.fundamental._helpers import (
    safe_float, fmt_date, filter_report_type, filter_annual, row_get
)
log = logging.getLogger(__name__)


def _comment(series: list[dict]) -> str:
    if not series: return "数据不足。"
    latest = series[0]
    rev_yoy = latest.get("revenue_yoy_pct")
    np_yoy = latest.get("net_profit_yoy_pct")
    parts = []
    if rev_yoy is not None:
        trend = "增长" if rev_yoy >= 0 else "下滑"
        parts.append(f"营收同比{trend} {abs(rev_yoy):.1f}%")
    if np_yoy is not None:
        trend = "增长" if np_yoy >= 0 else "下滑"
        parts.append(f"归母净利润同比{trend} {abs(np_yoy):.1f}%")
    if not parts: return "同比数据暂缺，无法生成成长性点评。"
    return f"{latest.get('end_date','')} {'; '.join(parts)}。"


class GrowthTool(BaseFundamentalTool):
    module_key = "growth"
    cache_ttl_seconds = 14400
    stale_ttl_seconds = 172800

    def __init__(self, limit: int = 8, annual: bool = True):
        self.limit = limit
        self.annual = annual

    async def fetch(self, market: str, symbol: str) -> dict[str, Any]:
        ts_code = _to_ts_code(market, symbol)
        api_limit = self.limit * 4 if self.annual else self.limit

        inc_task = tushare_client.get_income(ts_code=ts_code, limit=api_limit)
        fi_task  = tushare_client.get_fina_indicator(ts_code=ts_code)
        inc_result, fi_result = await asyncio.gather(inc_task, fi_task, return_exceptions=True)

        partial_errors: list[str] = []

        inc_df = pd.DataFrame()
        if isinstance(inc_result, Exception):
            partial_errors.append(f"income 表失败: {inc_result}")
        else:
            inc_df = filter_report_type(inc_result)
            if self.annual: inc_df = filter_annual(inc_df)
            inc_df = inc_df.sort_values("end_date", ascending=False).head(self.limit)

        fi_df = pd.DataFrame()
        fi_by_date: dict[str, Any] = {}
        if isinstance(fi_result, Exception):
            partial_errors.append(f"fina_indicator 表失败: {fi_result}")
        else:
            fi_df = fi_result.copy()
            if self.annual: fi_df = filter_annual(fi_df)
            for _, row in fi_df.iterrows():
                fi_by_date[str(row.get("end_date", ""))] = row

        if inc_df.empty and not fi_by_date:
            raise FundamentalToolError("income 和 fina_indicator 均无数据")

        series = []
        for _, row in inc_df.iterrows():
            date_raw = str(row_get(row, "end_date") or "")
            fi_row = fi_by_date.get(date_raw, {})

            rev_yoy = safe_float(row_get(fi_row, "or_yoy") or row_get(fi_row, "tr_yoy"))
            np_yoy  = safe_float(row_get(fi_row, "netprofit_yoy"))
            dt_yoy  = safe_float(row_get(fi_row, "dt_netprofit_yoy") or row_get(fi_row, "dprofit_yoy"))

            series.append({
                "end_date":                fmt_date(date_raw),
                "revenue":                 safe_float(row_get(row, "total_revenue")),
                "revenue_yoy_pct":         rev_yoy,
                "net_profit_parent":       safe_float(row_get(row, "n_income_attr_p")),
                "net_profit_yoy_pct":      np_yoy,
                "deduct_net_profit":       safe_float(row_get(row, "profit_dedt")),
                "deduct_net_profit_yoy_pct": dt_yoy,
                "roe_pct":                 safe_float(row_get(fi_row, "roe")),
                "eps":                     safe_float(row_get(fi_row, "beps")),
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
