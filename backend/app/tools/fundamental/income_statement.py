"""
app/tools/fundamental/income_statement.py — M03 利润表营收利润趋势

数据源（优先）：Tushare income 接口（最近 8 期）

返回结构：
{
  "symbol":    "600519",
  "ts_code":   "600519.SH",
  "periods":   [
    {
      "end_date":      "20251231",
      "ann_date":      "20260328",
      "report_type":   "1",           # 1=合并报表，4=母公司
      "total_revenue": 1.73e11,       # 营业总收入（元）
      "revenue":       1.71e11,       # 营业收入（元）
      "operate_profit": 9.8e10,       # 营业利润（元）
      "total_profit":  9.9e10,        # 利润总额（元）
      "n_income":      8.7e10,        # 净利润（元）
      "n_income_attr_p": 8.6e10,     # 归母净利润（元）
      "ebit":          9.5e10,        # 息税前利润（元）
      "ebitda":        9.8e10,        # 息税折旧摊销前利润（元）
      "oper_cost":     1.4e10,        # 营业成本（元）
      "sell_exp":      2.3e9,         # 销售费用（元）
      "admin_exp":     1.8e9,         # 管理费用（元）
      "fin_exp":       -5.0e8,        # 财务费用（元，负值=利息收入）
    },
    ...  # 共最多 8 期
  ],
  "source": "tushare",
}
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from app.tools.fundamental.base import BaseFundamentalTool, FundamentalToolError
from app.datasource.tushare_client import tushare_client, _to_ts_code

log = logging.getLogger(__name__)

# 需要提取的数值列
_NUM_COLS = [
    "total_revenue", "revenue", "operate_profit", "total_profit",
    "n_income", "n_income_attr_p", "ebit", "ebitda",
    "oper_cost", "sell_exp", "admin_exp", "fin_exp",
    "non_oper_income", "non_oper_exp", "income_tax",
]

# 字符串列
_STR_COLS = ["end_date", "ann_date", "f_ann_date", "report_type", "comp_type"]


def _safe_float(val: Any) -> float | None:
    """安全转换为 float，None / NaN 返回 None。"""
    if val is None:
        return None
    try:
        f = float(val)
        return None if f != f else round(f, 2)  # NaN check
    except (TypeError, ValueError):
        return None


class IncomeStatementTool(BaseFundamentalTool):
    module_key = "income_statement"
    cache_ttl_seconds = 14400      # 4h
    stale_ttl_seconds = 172800     # 48h

    async def fetch(self, market: str, symbol: str) -> dict[str, Any]:
        """从 Tushare income 获取最近 8 期利润表数据。"""
        ts_code = _to_ts_code(market, symbol)
        df = await tushare_client.get_income(ts_code=ts_code, limit=8)

        # 过滤：只保留合并报表（report_type=1），按报告期降序
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
