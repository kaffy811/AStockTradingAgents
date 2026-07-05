"""
dividend_history.py — 分红送股历史

数据源：Tushare dividend
返回历史分红记录，含每股现金分红（税前）、送股比例、除权日、登记日。
"""
from __future__ import annotations
import logging
from typing import Any
import pandas as pd
from app.datasource.tushare_client import tushare_client, _to_ts_code
from app.tools.fundamental.base import BaseFundamentalTool, FundamentalToolError
from app.tools.fundamental._helpers import safe_float, fmt_date, row_get

log = logging.getLogger(__name__)


class DividendHistoryTool(BaseFundamentalTool):
    module_key = "dividend_history"
    cache_ttl_seconds = 86400
    stale_ttl_seconds = 604800

    def __init__(self, limit: int = 10):
        self.limit = limit

    async def fetch(self, market: str, symbol: str) -> dict[str, Any]:
        ts_code = _to_ts_code(market, symbol)
        try:
            df = await tushare_client.get_dividend(ts_code=ts_code)
        except Exception as exc:
            raise FundamentalToolError(f"dividend 获取失败: {exc}") from exc

        if df is None or df.empty:
            return {
                "symbol": symbol,
                "ts_code": ts_code,
                "records": [],
                "summary": {"total_cash_div": None, "years_count": 0, "latest_cash_div": None},
                "comment": "暂无分红记录。",
                "source": "tushare",
            }

        # 只取已实施（div_proc == '实施'）的记录
        if "div_proc" in df.columns:
            implemented = df[df["div_proc"].str.contains("实施", na=False)].copy()
            if implemented.empty:
                implemented = df.copy()
        else:
            implemented = df.copy()

        implemented = implemented.sort_values("end_date", ascending=False).head(self.limit)

        records = []
        total_cash = 0.0
        years_seen: set = set()
        for _, row in implemented.iterrows():
            end_date = str(row_get(row, "end_date") or "")
            cash_div = safe_float(row_get(row, "cash_div"))
            cash_div_tax = safe_float(row_get(row, "cash_div_tax"))
            stk_div = safe_float(row_get(row, "stk_div"))
            stk_bo = safe_float(row_get(row, "stk_bo_rate"))
            stk_co = safe_float(row_get(row, "stk_co_rate"))
            if cash_div:
                total_cash += cash_div
            if end_date[:4]:
                years_seen.add(end_date[:4])
            records.append({
                "end_date": fmt_date(end_date),
                "ann_date": fmt_date(str(row_get(row, "ann_date") or "")),
                "ex_date": fmt_date(str(row_get(row, "ex_date") or "")),
                "pay_date": fmt_date(str(row_get(row, "pay_date") or "")),
                "cash_div": cash_div,           # 每股现金分红（税前，元）
                "cash_div_tax": cash_div_tax,   # 每股现金分红（税后，元）
                "stk_div": stk_div,             # 每股送股（股）
                "stk_bo_rate": stk_bo,          # 每股转增（股）
                "stk_co_rate": stk_co,          # 每股配股（股）
                "div_proc": str(row_get(row, "div_proc") or ""),
            })

        latest_cash = records[0]["cash_div"] if records else None
        comment_parts = []
        if records:
            comment_parts.append(f"最近 {len(records)} 次分红记录")
        if latest_cash:
            comment_parts.append(f"最新每股现金分红 {latest_cash:.4f} 元")

        return {
            "symbol": symbol,
            "ts_code": ts_code,
            "records": records,
            "summary": {
                "total_cash_div": round(total_cash, 4) if total_cash else None,
                "years_count": len(years_seen),
                "latest_cash_div": latest_cash,
            },
            "comment": "；".join(comment_parts) + "。" if comment_parts else "暂无分红记录。",
            "source": "tushare",
        }
