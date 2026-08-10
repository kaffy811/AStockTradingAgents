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
from app.datasource.tushare_client import tushare_client, _to_ts_code, TushareAuthError
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
            if isinstance(inc_result, TushareAuthError):
                partial_errors.append("income 暂不可用（权限不足）")
            else:
                partial_errors.append(f"income 表失败: {inc_result}")
        else:
            inc_df = filter_report_type(inc_result)
            if self.annual: inc_df = filter_annual(inc_df)
            inc_df = inc_df.sort_values("end_date", ascending=False).head(self.limit)

        fi_df = pd.DataFrame()
        fi_by_date: dict[str, Any] = {}
        if isinstance(fi_result, Exception):
            if isinstance(fi_result, TushareAuthError):
                partial_errors.append("fina_indicator 暂不可用（权限不足）")
            else:
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

    async def fetch_baostock(self, market: str, symbol: str) -> dict[str, Any]:
        """
        BaoStock 备用：成长能力（YOYNI / YOYEPSBasic / YOYEquity）。
        BaoStock 字段无营收/归母净利润绝对值，revenue/net_profit_parent 返回 null。
        """
        from app.datasource.baostock_client import baostock_client
        from app.datasource.tushare_client import _to_ts_code as _ts
        ts_code = _ts(market, symbol)
        rows = await baostock_client.get_growth_data(ts_code, n=self.limit)
        if not rows:
            raise RuntimeError("BaoStock get_growth_data 无数据")

        def _pct(v):
            """BaoStock 成长率为小数 (0.156)，转为百分比 (15.6)。"""
            if v is None:
                return None
            try:
                return round(float(v) * 100, 4)
            except (TypeError, ValueError):
                return None

        series = []
        for r in rows:
            stat_date = r.get("stat_date") or ""
            if len(stat_date) == 8 and "-" not in stat_date:
                stat_date = f"{stat_date[:4]}-{stat_date[4:6]}-{stat_date[6:]}"
            # BaoStock YOYNI/YOYEPSBasic 是小数 YoY 增长率，乘 100 得百分比
            # 注意: yoy_eps 是 EPS 同比增长率，而非绝对 EPS 值，故 eps 字段置 null
            series.append({
                "end_date":                stat_date,
                "revenue":                 None,   # BaoStock 无绝对值
                "revenue_yoy_pct":         None,   # BaoStock 无营收同比
                "net_profit_parent":       None,
                "net_profit_yoy_pct":      _pct(r.get("yoy_ni")),   # YOYNI → %
                "deduct_net_profit":       None,
                "deduct_net_profit_yoy_pct": None,
                "roe_pct":                 None,
                "eps":                     None,   # BaoStock growth 表无绝对 EPS
            })
        series.sort(key=lambda x: x.get("end_date") or "", reverse=True)
        series = series[:self.limit]

        return {
            "symbol": symbol, "ts_code": ts_code,
            "annual": self.annual,
            "series": series,
            "comment": _comment(series),
            "source": "baostock",
            "_partial_errors": [
                "BaoStock 备用：营收/归母净利润绝对值不可用，营收同比/扣非净利润同比为 null"
            ],
        }
