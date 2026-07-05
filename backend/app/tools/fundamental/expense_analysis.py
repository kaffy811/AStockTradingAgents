"""
expense_analysis.py — 收入费用分析

数据源：Tushare income（单表）

金融口径：
  gross_profit = total_revenue - oper_cost
  total_expense = sell_exp + admin_exp + rd_expense + fin_exp（缺失字段用 0，记入 reason）
  core_profit = total_revenue - oper_cost - biz_tax_surchg - sell_exp - admin_exp - rd_expense - fin_exp
  所有比率分母 = total_revenue；total_revenue <= 0 → null
  rd_expense 可能为 None（部分公司未单独披露，并入 admin_exp）
"""
from __future__ import annotations
import logging
from typing import Any
import pandas as pd
from app.datasource.tushare_client import tushare_client, _to_ts_code
from app.tools.fundamental.base import BaseFundamentalTool, FundamentalToolError
from app.tools.fundamental._helpers import (
    safe_float, safe_pct, fmt_date, filter_report_type, filter_annual, row_get
)
log = logging.getLogger(__name__)


class ExpenseAnalysisTool(BaseFundamentalTool):
    module_key = "expense_analysis"
    cache_ttl_seconds = 14400
    stale_ttl_seconds = 172800

    def __init__(self, limit: int = 8, annual: bool = True):
        self.limit = limit
        self.annual = annual

    async def fetch(self, market: str, symbol: str) -> dict[str, Any]:
        ts_code = _to_ts_code(market, symbol)
        api_limit = self.limit * 4 if self.annual else self.limit
        df = await tushare_client.get_income(ts_code=ts_code, limit=api_limit)

        df = filter_report_type(df)
        if self.annual: df = filter_annual(df)
        df = df.sort_values("end_date", ascending=False).head(self.limit)
        if df.empty:
            raise FundamentalToolError(f"income 无数据 [{ts_code}]")

        series = []
        for _, row in df.iterrows():
            date_raw = str(row_get(row, "end_date") or "")
            rev = safe_float(row_get(row, "total_revenue"))
            cost = safe_float(row_get(row, "oper_cost"))
            taxes = safe_float(row_get(row, "biz_tax_surchg"))
            sell = safe_float(row_get(row, "sell_exp"))
            admin = safe_float(row_get(row, "admin_exp"))
            rd   = safe_float(row_get(row, "rd_exp"))  # 可能为 None
            fin  = safe_float(row_get(row, "fin_exp"))

            # 毛利
            gross_profit = (
                round(rev - cost, 2)
                if rev is not None and cost is not None else None
            )

            # 三费 + 研发加总（缺失字段用 0，记录 reason）
            missing_in_expense = []
            expense_parts = []
            for name, val in [("sell_exp", sell), ("admin_exp", admin), ("fin_exp", fin)]:
                expense_parts.append(val if val is not None else 0.0)
                if val is None: missing_in_expense.append(name)
            rd_val = rd if rd is not None else 0.0
            if rd is None: missing_in_expense.append("rd_exp（可能并入管理费用）")
            total_expense = round(sum(expense_parts) + rd_val, 2)

            # 核心利润
            if all(v is not None for v in [rev, cost]):
                taxes_v   = taxes  if taxes is not None else 0.0
                sell_v    = sell   if sell  is not None else 0.0
                admin_v   = admin  if admin is not None else 0.0
                fin_v     = fin    if fin   is not None else 0.0
                core_profit = round(rev - cost - taxes_v - sell_v - admin_v - rd_val - fin_v, 2)
            else:
                core_profit = None

            period: dict[str, Any] = {
                "end_date":            fmt_date(date_raw),
                "total_revenue":       rev,
                "operating_cost":      cost,
                "gross_profit":        gross_profit,
                "gross_margin_pct":    safe_pct(gross_profit, rev),
                "sell_expense":        sell,
                "admin_expense":       admin,
                "rd_expense":          rd,
                "fin_expense":         fin,
                "total_expense":       total_expense,
                "total_expense_ratio_pct": safe_pct(total_expense, rev),
                "core_profit":         core_profit,
                "core_profit_margin_pct": safe_pct(core_profit, rev),
            }
            if missing_in_expense:
                period["_missing_in_expense"] = missing_in_expense
            series.append(period)

        # 汇总所有 _missing 字段
        all_missing: list[str] = []
        for p in series:
            for m in p.pop("_missing_in_expense", []):
                if m not in all_missing:
                    all_missing.append(m)

        result: dict[str, Any] = {
            "symbol": symbol, "ts_code": ts_code,
            "annual": self.annual,
            "series": series,
            "source": "tushare",
        }
        if all_missing:
            result["_partial_errors"] = [f"以下费用字段部分期间缺失（已用 0 代替）: {all_missing}"]
        return result
