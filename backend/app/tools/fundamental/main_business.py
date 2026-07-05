"""
main_business.py — 主营业务构成

数据源：Tushare fina_mainbz (type=P，按产品分类)
返回最近两期主营构成，含各业务线营收/利润/成本及占比。
"""
from __future__ import annotations
import logging
from typing import Any
import pandas as pd
from app.datasource.tushare_client import tushare_client, _to_ts_code
from app.tools.fundamental.base import BaseFundamentalTool, FundamentalToolError
from app.tools.fundamental._helpers import safe_float, fmt_date, row_get

log = logging.getLogger(__name__)


class MainBusinessTool(BaseFundamentalTool):
    module_key = "main_business"
    cache_ttl_seconds = 86400
    stale_ttl_seconds = 604800  # 7 days

    def __init__(self, limit_periods: int = 2):
        self.limit_periods = limit_periods

    async def fetch(self, market: str, symbol: str) -> dict[str, Any]:
        ts_code = _to_ts_code(market, symbol)
        try:
            df = await tushare_client.get_fina_mainbz(ts_code=ts_code)
        except Exception as exc:
            raise FundamentalToolError(f"fina_mainbz 获取失败: {exc}") from exc

        if df is None or df.empty:
            raise FundamentalToolError("主营业务数据为空")

        # 获取最近的 limit_periods 个报告期
        periods = sorted(df["end_date"].dropna().unique(), reverse=True)[:self.limit_periods]

        periods_data = []
        for period in periods:
            period_df = df[df["end_date"] == period].copy()
            # 计算总销售额
            total_sales = period_df["bz_sales"].apply(lambda x: safe_float(x) or 0).sum()
            items = []
            for _, row in period_df.iterrows():
                sales = safe_float(row_get(row, "bz_sales"))
                profit = safe_float(row_get(row, "bz_profit"))
                cost = safe_float(row_get(row, "bz_cost"))
                sales_ratio = round(sales / total_sales * 100, 2) if (sales and total_sales > 0) else None
                items.append({
                    "bz_item": str(row_get(row, "bz_item") or ""),
                    "bz_sales": sales,
                    "bz_profit": profit,
                    "bz_cost": cost,
                    "sales_ratio_pct": sales_ratio,
                    "curr_type": str(row_get(row, "curr_type") or "CNY"),
                })
            # sort by sales descending
            items.sort(key=lambda x: x["bz_sales"] or 0, reverse=True)
            periods_data.append({
                "end_date": fmt_date(period),
                "total_sales": round(total_sales, 4) if total_sales else None,
                "items": items,
            })

        return {
            "symbol": symbol,
            "ts_code": ts_code,
            "periods": periods_data,
            "source": "tushare",
        }
