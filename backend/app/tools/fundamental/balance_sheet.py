"""
app/tools/fundamental/balance_sheet.py — M04 资产负债表关键指标

数据源（优先）：Tushare balancesheet 接口（最近 8 期）

返回最近 8 期报告期的关键资产负债指标：
{
  "symbol":  "600519",
  "ts_code": "600519.SH",
  "periods": [
    {
      "end_date":      "20251231",
      "ann_date":      "20260328",
      "report_type":   "1",
      "total_assets":  3.2e11,          # 总资产（元）
      "total_liab":    5.8e10,          # 总负债（元）
      "total_hldr_eqy_exc_min_int": 2.5e11,  # 股东权益（不含少数股东）
      "total_hldr_eqy_inc_min_int": 2.6e11,  # 股东权益（含少数股东）
      "money_cap":     6.2e10,          # 货币资金（元）
      "accounts_receiv": 1.2e9,         # 应收账款（元）
      "inventories":   2.5e10,          # 存货（元）
      "total_cur_assets": 1.8e11,       # 流动资产合计（元）
      "total_nca":     1.4e11,          # 非流动资产合计（元）
      "total_cur_liab": 4.5e10,         # 流动负债合计（元）
      "total_ncl":     1.3e10,          # 非流动负债合计（元）
      "lt_borr":       0.0,             # 长期借款（元）
      "st_borr":       0.0,             # 短期借款（元）
      "goodwill":      0.0,             # 商誉（元）
    },
    ...
  ],
  "source": "tushare",
}
"""

from __future__ import annotations

import logging
from typing import Any

from app.tools.fundamental.base import BaseFundamentalTool
from app.datasource.tushare_client import tushare_client, _to_ts_code

log = logging.getLogger(__name__)

_NUM_COLS = [
    "total_assets", "total_liab",
    "total_hldr_eqy_exc_min_int", "total_hldr_eqy_inc_min_int",
    "money_cap", "accounts_receiv", "inventories",
    "total_cur_assets", "total_nca",
    "total_cur_liab", "total_ncl",
    "lt_borr", "st_borr", "goodwill",
    "fix_assets", "intan_assets",
    "notes_payable", "acct_payable", "undist_profit",
]

_STR_COLS = ["end_date", "ann_date", "f_ann_date", "report_type", "comp_type"]


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if f != f else round(f, 2)
    except (TypeError, ValueError):
        return None


class BalanceSheetTool(BaseFundamentalTool):
    module_key = "balance_sheet"
    cache_ttl_seconds = 14400
    stale_ttl_seconds = 172800

    async def fetch(self, market: str, symbol: str) -> dict[str, Any]:
        """从 Tushare balancesheet 获取最近 8 期关键资产负债指标。"""
        ts_code = _to_ts_code(market, symbol)
        df = await tushare_client.get_balancesheet(ts_code=ts_code, limit=8)

        # 只保留合并报表
        if "report_type" in df.columns:
            merged = df[df["report_type"].astype(str) == "1"]
            df = merged if not merged.empty else df

        df = df.sort_values("end_date", ascending=False).head(8)

        periods: list[dict[str, Any]] = []
        for _, row in df.iterrows():
            period: dict[str, Any] = {}
            for col in _STR_COLS:
                period[col] = str(row[col]) if row.get(col) is not None else None
            for col in _NUM_COLS:
                period[col] = _safe_float(row.get(col))
            periods.append(period)

        return {
            "symbol":  symbol,
            "ts_code": ts_code,
            "periods": periods,
            "source":  "tushare",
        }
