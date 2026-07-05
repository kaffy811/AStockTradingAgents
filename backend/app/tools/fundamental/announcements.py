"""
announcements.py — 近期公告摘要

数据源：Tushare forecast（业绩预告） + express（业绩快报）
聚合最近的业绩预告和快报信息，不爬取公告全文。
"""
from __future__ import annotations
import asyncio, logging
from typing import Any
import pandas as pd
from app.datasource.tushare_client import tushare_client, _to_ts_code
from app.tools.fundamental.base import BaseFundamentalTool, FundamentalToolError
from app.tools.fundamental._helpers import safe_float, fmt_date, row_get

log = logging.getLogger(__name__)


class AnnouncementsTool(BaseFundamentalTool):
    module_key = "announcements"
    cache_ttl_seconds = 1800
    stale_ttl_seconds = 7200

    def __init__(self, limit: int = 5):
        self.limit = limit

    async def fetch(self, market: str, symbol: str) -> dict[str, Any]:
        ts_code = _to_ts_code(market, symbol)
        partial_errors: list[str] = []

        forecast_task = tushare_client.get_forecast(ts_code=ts_code)
        express_task = tushare_client.get_express(ts_code=ts_code)
        forecast_result, express_result = await asyncio.gather(
            forecast_task, express_task, return_exceptions=True
        )

        forecasts = []
        if isinstance(forecast_result, Exception):
            partial_errors.append(f"forecast 获取失败: {forecast_result}")
        elif forecast_result is not None and not forecast_result.empty:
            df = forecast_result.sort_values("ann_date", ascending=False).head(self.limit)
            for _, row in df.iterrows():
                forecasts.append({
                    "ann_date": fmt_date(str(row_get(row, "ann_date") or "")),
                    "end_date": fmt_date(str(row_get(row, "end_date") or "")),
                    "type": str(row_get(row, "type") or ""),
                    "p_change_min": safe_float(row_get(row, "p_change_min")),
                    "p_change_max": safe_float(row_get(row, "p_change_max")),
                    "net_profit_min": safe_float(row_get(row, "net_profit_min")),
                    "net_profit_max": safe_float(row_get(row, "net_profit_max")),
                    "summary": str(row_get(row, "summary") or "")[:200],
                    "change_reason": str(row_get(row, "change_reason") or "")[:200],
                })

        expresses = []
        if isinstance(express_result, Exception):
            partial_errors.append(f"express 获取失败: {express_result}")
        elif express_result is not None and not express_result.empty:
            df = express_result.sort_values("ann_date", ascending=False).head(self.limit)
            for _, row in df.iterrows():
                expresses.append({
                    "ann_date": fmt_date(str(row_get(row, "ann_date") or "")),
                    "end_date": fmt_date(str(row_get(row, "end_date") or "")),
                    "revenue": safe_float(row_get(row, "revenue")),
                    "n_income": safe_float(row_get(row, "n_income")),
                    "yoy_net_profit": safe_float(row_get(row, "yoy_net_profit")),
                    "yoy_sales": safe_float(row_get(row, "yoy_sales")),
                    "diluted_eps": safe_float(row_get(row, "diluted_eps")),
                    "diluted_roe": safe_float(row_get(row, "diluted_roe")),
                })

        if not forecasts and not expresses:
            raise FundamentalToolError("业绩预告和业绩快报均无数据")

        result: dict[str, Any] = {
            "symbol": symbol,
            "ts_code": ts_code,
            "forecasts": forecasts,
            "expresses": expresses,
            "source": "tushare",
        }
        if partial_errors:
            result["_partial_errors"] = partial_errors
        return result
