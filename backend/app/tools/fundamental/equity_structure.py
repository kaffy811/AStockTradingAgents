"""
equity_structure.py — 股权结构快照

数据源：Tushare daily_basic (total_share / float_share / free_share / total_mv / circ_mv)
提供最新交易日的股本结构：总股本、流通股本、自由流通股本及市值。
"""
from __future__ import annotations
import logging
from typing import Any
from app.datasource.tushare_client import tushare_client, _to_ts_code
from app.tools.fundamental.base import BaseFundamentalTool, FundamentalToolError
from app.tools.fundamental._helpers import safe_float, fmt_date, row_get

log = logging.getLogger(__name__)


class EquityStructureTool(BaseFundamentalTool):
    module_key = "equity_structure"
    cache_ttl_seconds = 86400
    stale_ttl_seconds = 172800

    async def fetch(self, market: str, symbol: str) -> dict[str, Any]:
        ts_code = _to_ts_code(market, symbol)
        try:
            df = await tushare_client.get_daily_basic(ts_code=ts_code)
        except Exception as exc:
            raise FundamentalToolError(f"daily_basic 获取失败: {exc}") from exc

        if df is None or df.empty:
            raise FundamentalToolError("daily_basic 数据为空")

        row = df.sort_values("trade_date", ascending=False).iloc[0]

        total_share = safe_float(row_get(row, "total_share"))  # 万股
        float_share = safe_float(row_get(row, "float_share"))  # 万股
        free_share = safe_float(row_get(row, "free_share"))    # 万股
        total_mv = safe_float(row_get(row, "total_mv"))        # 万元
        circ_mv = safe_float(row_get(row, "circ_mv"))          # 万元

        # 计算流通比例
        float_ratio_pct = round(float_share / total_share * 100, 2) if (float_share and total_share) else None
        free_ratio_pct = round(free_share / total_share * 100, 2) if (free_share and total_share) else None

        trade_date_fmt = fmt_date(str(row_get(row, "trade_date") or ""))
        snapshot_row = {
            "trade_date": trade_date_fmt,
            "total_share_wan": total_share,
            "float_share_wan": float_share,
            "free_share_wan": free_share,
            "float_ratio_pct": float_ratio_pct,
            "free_ratio_pct": free_ratio_pct,
        }
        return {
            "symbol": symbol,
            "ts_code": ts_code,
            "rows": [snapshot_row],
            "trade_date": trade_date_fmt,
            "total_share_wan": total_share,    # 总股本（万股）
            "float_share_wan": float_share,    # 流通股本（万股）
            "free_share_wan": free_share,      # 自由流通股本（万股）
            "total_mv_wan": total_mv,          # 总市值（万元）
            "circ_mv_wan": circ_mv,            # 流通市值（万元）
            "float_ratio_pct": float_ratio_pct,
            "free_ratio_pct": free_ratio_pct,
            "summary": {
                "trade_date": trade_date_fmt,
                "total_share_wan": total_share,
                "float_share_wan": float_share,
                "free_share_wan": free_share,
                "float_ratio_pct": float_ratio_pct,
                "free_ratio_pct": free_ratio_pct,
            },
            "reasons": [],
            "source": "tushare",
        }
