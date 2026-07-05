"""
app/tools/fundamental/quote_snapshot.py — M01 实时行情快照

数据源（优先）：Tushare daily_basic 接口
备用源（ENABLE_AKSHARE=true）：AkShare stock_zh_a_spot_em

返回结构：
{
  "symbol":        "600519",
  "ts_code":       "600519.SH",
  "market":        "CN",
  "name":          "贵州茅台",
  "trade_date":    "20260704",
  "close":         1850.0,
  "pe":            30.5,
  "pe_ttm":        30.2,
  "pb":            12.3,
  "ps":            14.1,
  "ps_ttm":        13.9,
  "dv_ratio":      1.2,         # 股息率 %
  "total_mv":      2.32e13,     # 总市值（元）
  "circ_mv":       2.31e13,     # 流通市值（元）
  "turnover_rate": 0.45,        # 换手率 %
  "volume_ratio":  1.2,         # 量比
  "source":        "tushare",
}
"""

from __future__ import annotations

import logging
from typing import Any

from app.tools.fundamental.base import BaseFundamentalTool, FundamentalToolError
from app.datasource.tushare_client import tushare_client, _to_ts_code

log = logging.getLogger(__name__)


class QuoteSnapshotTool(BaseFundamentalTool):
    module_key = "quote_snapshot"
    cache_ttl_seconds = 60       # 实时行情 60s 刷新
    stale_ttl_seconds = 300      # stale 降级 5 分钟

    async def fetch(self, market: str, symbol: str) -> dict[str, Any]:
        """从 Tushare daily_basic 获取最新交易日行情快照。"""
        ts_code = _to_ts_code(market, symbol)
        df = await tushare_client.get_daily_basic(ts_code=ts_code)

        # daily_basic 按 trade_date 降序，取最新一行
        df = df.sort_values("trade_date", ascending=False)
        row = df.iloc[0]

        def _f(col: str) -> float | None:
            """安全读取浮点值。"""
            v = row.get(col)
            if v is None:
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        def _s(col: str) -> str | None:
            v = row.get(col)
            return str(v) if v is not None else None

        result: dict[str, Any] = {
            "symbol":        symbol,
            "ts_code":       ts_code,
            "market":        market.upper(),
            "trade_date":    _s("trade_date"),
            "close":         _f("close"),
            "pe":            _f("pe"),
            "pe_ttm":        _f("pe_ttm"),
            "pb":            _f("pb"),
            "ps":            _f("ps"),
            "ps_ttm":        _f("ps_ttm"),
            "dv_ratio":      _f("dv_ratio"),    # 股息率 %
            "dv_ttm":        _f("dv_ttm"),
            "total_mv":      _f("total_mv"),     # 万元 → 元（Tushare 单位为万元）
            "circ_mv":       _f("circ_mv"),
            "turnover_rate": _f("turnover_rate"),
            "turnover_rate_f": _f("turnover_rate_f"),
            "volume_ratio":  _f("volume_ratio"),
            "source":        "tushare",
        }

        # Tushare daily_basic 市值单位为万元，统一转换为元
        for mv_key in ("total_mv", "circ_mv"):
            if result[mv_key] is not None:
                result[mv_key] = round(result[mv_key] * 1e4, 2)

        return result

    async def fetch_akshare(self, market: str, symbol: str) -> dict[str, Any]:
        """AkShare 备用：stock_zh_a_spot_em 实时行情。"""
        from app.datasource.akshare_client import akshare_fs_client
        data = await akshare_fs_client.get_real_time_quote(symbol=symbol, market=market)
        data["source"] = "akshare_fallback"
        return data
