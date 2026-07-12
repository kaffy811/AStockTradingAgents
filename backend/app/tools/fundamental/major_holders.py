"""
major_holders.py — 大股东持股与股东户数趋势

数据源：
  - Tushare top10_floatholders (十大流通股东)
  - Tushare stk_holdernumber (股东户数趋势)
"""
from __future__ import annotations
import asyncio, logging
from typing import Any
import pandas as pd
from app.datasource.tushare_client import tushare_client, _to_ts_code
from app.tools.fundamental.base import BaseFundamentalTool, FundamentalToolError
from app.tools.fundamental._helpers import safe_float, fmt_date, row_get

log = logging.getLogger(__name__)


class MajorHoldersTool(BaseFundamentalTool):
    module_key = "major_holders"
    cache_ttl_seconds = 86400
    stale_ttl_seconds = 604800

    def __init__(self, holder_limit: int = 5):
        self.holder_limit = holder_limit

    async def fetch(self, market: str, symbol: str) -> dict[str, Any]:
        ts_code = _to_ts_code(market, symbol)
        partial_errors: list[str] = []

        # 并发拉取两个接口
        top10_task = tushare_client.get_top10_floatholders(ts_code=ts_code)
        holder_num_task = tushare_client.get_stk_holdernumber(ts_code=ts_code)
        top10_result, holder_num_result = await asyncio.gather(
            top10_task, holder_num_task, return_exceptions=True
        )

        # 十大流通股东
        top10_list = []
        latest_period = None
        if isinstance(top10_result, Exception):
            partial_errors.append(f"top10_floatholders 失败: {top10_result}")
        elif top10_result is not None and not top10_result.empty:
            df = top10_result.sort_values("end_date", ascending=False)
            latest_period = str(df["end_date"].iloc[0]) if not df.empty else None
            if latest_period:
                period_df = df[df["end_date"] == latest_period].head(self.holder_limit)
                for _, row in period_df.iterrows():
                    top10_list.append({
                        "holder_name": str(row_get(row, "holder_name") or ""),
                        "hold_amount": safe_float(row_get(row, "hold_amount")),
                        "hold_ratio_pct": safe_float(row_get(row, "hold_ratio")),
                        "end_date": fmt_date(latest_period),
                    })

        # 股东户数趋势
        holder_num_series = []
        if isinstance(holder_num_result, Exception):
            partial_errors.append(f"stk_holdernumber 失败: {holder_num_result}")
        elif holder_num_result is not None and not holder_num_result.empty:
            df_num = holder_num_result.sort_values("end_date", ascending=False).head(5)
            for _, row in df_num.iterrows():
                holder_num_series.append({
                    "end_date": fmt_date(str(row_get(row, "end_date") or "")),
                    "holder_num": int(row_get(row, "holder_num") or 0) or None,
                    "holder_num_change": safe_float(row_get(row, "holder_num_change")),
                })

        if not top10_list and not holder_num_series:
            raise FundamentalToolError("大股东和股东户数数据均为空")

        # 股东户数趋势点评
        comment = ""
        if holder_num_series and holder_num_series[0].get("holder_num"):
            latest_num = holder_num_series[0]["holder_num"]
            change = holder_num_series[0].get("holder_num_change")
            comment = f"最新股东户数 {latest_num:,} 户"
            if change is not None:
                direction = "增加" if change > 0 else "减少"
                comment += f"，较上期{direction} {abs(change):.0f} 户"

        result: dict[str, Any] = {
            "symbol": symbol,
            "ts_code": ts_code,
            "rows": top10_list,
            "top10_float_holders": top10_list,
            "latest_period": fmt_date(latest_period) if latest_period else None,
            "holder_number_trend": holder_num_series,
            "holder_num_series": holder_num_series,
            "reasons": [],
            "comment": comment or "持股数据已获取。",
            "source": "tushare",
        }
        if partial_errors:
            result["_partial_errors"] = partial_errors
        return result
