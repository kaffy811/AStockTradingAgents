"""
analyst_ratings.py — 研报评级汇总

数据源：Tushare forecast（业绩预告类型分布）+ express（快报净利润增速）
注意：Tushare 不提供机构评级（买/持/卖）原始数据，此工具聚合业绩预期信息代替。
不调用任何外部网页爬虫。
"""
from __future__ import annotations
import asyncio, logging
from typing import Any
import pandas as pd
from app.datasource.tushare_client import tushare_client, _to_ts_code
from app.tools.fundamental.base import BaseFundamentalTool, FundamentalToolError
from app.tools.fundamental._helpers import safe_float, fmt_date, row_get

log = logging.getLogger(__name__)

# 业绩预告类型映射（正面/负面/中性）
_FORECAST_SENTIMENT = {
    "预增": "positive",
    "续盈": "positive",
    "扭亏": "positive",
    "略增": "positive",
    "预减": "negative",
    "续亏": "negative",
    "首亏": "negative",
    "略减": "negative",
    "不确定": "neutral",
}


class AnalystRatingsTool(BaseFundamentalTool):
    module_key = "analyst_ratings"
    cache_ttl_seconds = 7200
    stale_ttl_seconds = 86400

    def __init__(self, limit: int = 8):
        self.limit = limit

    async def fetch(self, market: str, symbol: str) -> dict[str, Any]:
        ts_code = _to_ts_code(market, symbol)
        partial_errors: list[str] = []

        forecast_task = tushare_client.get_forecast(ts_code=ts_code)
        express_task = tushare_client.get_express(ts_code=ts_code)
        forecast_result, express_result = await asyncio.gather(
            forecast_task, express_task, return_exceptions=True
        )

        forecast_items = []
        sentiment_summary: dict[str, int] = {"positive": 0, "negative": 0, "neutral": 0}
        if isinstance(forecast_result, Exception):
            partial_errors.append(f"forecast 失败: {forecast_result}")
        elif forecast_result is not None and not forecast_result.empty:
            df = forecast_result.sort_values("ann_date", ascending=False).head(self.limit)
            for _, row in df.iterrows():
                ftype = str(row_get(row, "type") or "")
                sentiment = _FORECAST_SENTIMENT.get(ftype, "neutral")
                sentiment_summary[sentiment] = sentiment_summary.get(sentiment, 0) + 1
                p_min = safe_float(row_get(row, "p_change_min"))
                p_max = safe_float(row_get(row, "p_change_max"))
                forecast_items.append({
                    "ann_date": fmt_date(str(row_get(row, "ann_date") or "")),
                    "end_date": fmt_date(str(row_get(row, "end_date") or "")),
                    "type": ftype,
                    "sentiment": sentiment,
                    "p_change_min": p_min,
                    "p_change_max": p_max,
                    "net_profit_min": safe_float(row_get(row, "net_profit_min")),
                    "net_profit_max": safe_float(row_get(row, "net_profit_max")),
                    "summary": str(row_get(row, "summary") or "")[:200],
                })

        express_items = []
        if isinstance(express_result, Exception):
            partial_errors.append(f"express 失败: {express_result}")
        elif express_result is not None and not express_result.empty:
            df = express_result.sort_values("ann_date", ascending=False).head(self.limit)
            for _, row in df.iterrows():
                express_items.append({
                    "ann_date": fmt_date(str(row_get(row, "ann_date") or "")),
                    "end_date": fmt_date(str(row_get(row, "end_date") or "")),
                    "yoy_net_profit": safe_float(row_get(row, "yoy_net_profit")),
                    "yoy_sales": safe_float(row_get(row, "yoy_sales")),
                    "diluted_eps": safe_float(row_get(row, "diluted_eps")),
                    "diluted_roe": safe_float(row_get(row, "diluted_roe")),
                    "n_income": safe_float(row_get(row, "n_income")),
                })

        if not forecast_items and not express_items:
            raise FundamentalToolError("业绩预告和快报均无数据，无法生成评级汇总")

        # 生成点评
        comment_parts = []
        if forecast_items:
            dominant = max(sentiment_summary, key=lambda k: sentiment_summary[k])
            labels = {"positive": "偏正面", "negative": "偏负面", "neutral": "中性"}
            comment_parts.append(f"近期业绩预告情绪{labels.get(dominant, '未知')}")
            latest = forecast_items[0]
            if latest.get("p_change_min") is not None and latest.get("p_change_max") is not None:
                comment_parts.append(
                    f"最新预告净利润变化幅度 {latest['p_change_min']:.1f}%~{latest['p_change_max']:.1f}%"
                )

        result: dict[str, Any] = {
            "symbol": symbol,
            "ts_code": ts_code,
            "forecast_items": forecast_items,
            "express_items": express_items,
            "sentiment_summary": sentiment_summary,
            "comment": "；".join(comment_parts) + "。" if comment_parts else "暂无业绩预期数据。",
            "data_note": "本工具聚合业绩预告数据作为业绩预期参考，不含机构买卖评级。",
            "source": "tushare",
        }
        if partial_errors:
            result["_partial_errors"] = partial_errors
        return result
