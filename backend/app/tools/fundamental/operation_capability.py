"""
operation_capability.py — 营运能力分析

数据源：Tushare fina_indicator（主） + income + balancesheet（辅，计算周转率）

金融口径：
  ar_turn / inv_turn / assets_turn / op_cycle → fina_indicator 官方字段（优先）
  ca_turn = total_revenue / total_cur_assets（income + balancesheet）
  fa_turn = total_revenue / fix_assets（income + balancesheet）
  payable_turn = oper_cost / acct_payable（简化：期末口径）
  inventory_days = 360 / inv_turn
  receivable_days = 360 / ar_turn
  payable_days = 360 / payable_turn
  cash_conversion_cycle = inventory_days + receivable_days - payable_days
    （payable_days 缺失 → CCC 返回 null + reason）
"""
from __future__ import annotations
import asyncio, logging
from typing import Any
import pandas as pd
from app.datasource.tushare_client import tushare_client, _to_ts_code
from app.tools.fundamental.base import BaseFundamentalTool, FundamentalToolError
from app.tools.fundamental._helpers import (
    safe_float, safe_div, fmt_date, filter_report_type, filter_annual, row_get
)
log = logging.getLogger(__name__)


def _days(turn: float | None) -> float | None:
    if turn is None or turn <= 0: return None
    return round(360.0 / turn, 2)


def _comment(series: list[dict]) -> str:
    if not series: return "数据不足。"
    l = series[0]
    parts = []
    at = l.get("assets_turn"); ccc = l.get("cash_conversion_cycle")
    if at is not None: parts.append(f"总资产周转率 {at:.2f}次")
    if ccc is not None: parts.append(f"现金转换周期 {ccc:.0f}天")
    return f"{l.get('end_date','')} {'; '.join(parts)}。" if parts else "营运能力数据暂缺。"


class OperationCapabilityTool(BaseFundamentalTool):
    module_key = "operation_capability"
    cache_ttl_seconds = 14400
    stale_ttl_seconds = 172800

    def __init__(self, limit: int = 8, annual: bool = True):
        self.limit = limit
        self.annual = annual

    async def fetch(self, market: str, symbol: str) -> dict[str, Any]:
        ts_code = _to_ts_code(market, symbol)
        api_limit = self.limit * 4 if self.annual else self.limit

        fi_task  = tushare_client.get_fina_indicator(ts_code=ts_code)
        inc_task = tushare_client.get_income(ts_code=ts_code, limit=api_limit)
        bs_task  = tushare_client.get_balancesheet(ts_code=ts_code, limit=api_limit)
        fi_result, inc_result, bs_result = await asyncio.gather(
            fi_task, inc_task, bs_task, return_exceptions=True
        )

        partial_errors: list[str] = []
        fi_df = pd.DataFrame()
        inc_by_date: dict[str, Any] = {}
        bs_by_date: dict[str, Any] = {}

        if isinstance(fi_result, Exception):
            partial_errors.append(f"fina_indicator 失败: {fi_result}")
        else:
            fi_df = fi_result.copy()
            if self.annual: fi_df = filter_annual(fi_df)
            fi_df = fi_df.sort_values("end_date", ascending=False).head(self.limit)

        if isinstance(inc_result, Exception):
            partial_errors.append(f"income 失败，ca_turn/fa_turn 将为 null: {inc_result}")
        else:
            tmp = filter_report_type(inc_result)
            if self.annual: tmp = filter_annual(tmp)
            for _, r in tmp.iterrows():
                inc_by_date[str(row_get(r, "end_date") or "")] = r

        if isinstance(bs_result, Exception):
            partial_errors.append(f"balancesheet 失败，payable_turn 将为 null: {bs_result}")
        else:
            tmp = filter_report_type(bs_result)
            if self.annual: tmp = filter_annual(tmp)
            for _, r in tmp.iterrows():
                bs_by_date[str(row_get(r, "end_date") or "")] = r

        if fi_df.empty:
            raise FundamentalToolError("fina_indicator 无数据")

        series = []
        for _, row in fi_df.iterrows():
            date_raw = str(row_get(row, "end_date") or "")
            inc_row = inc_by_date.get(date_raw, {})
            bs_row  = bs_by_date.get(date_raw, {})

            ar_turn    = safe_float(row_get(row, "ar_turn"))
            inv_turn   = safe_float(row_get(row, "inv_turn"))
            assets_turn= safe_float(row_get(row, "assets_turn"))
            op_cycle   = safe_float(row_get(row, "op_cycle"))

            rev  = safe_float(row_get(inc_row, "total_revenue"))
            cost = safe_float(row_get(inc_row, "oper_cost"))
            ca   = safe_float(row_get(bs_row, "total_cur_assets"))
            fa   = safe_float(row_get(bs_row, "fix_assets"))
            ap   = safe_float(row_get(bs_row, "acct_payable"))

            ca_turn  = safe_div(rev, ca)
            fa_turn  = safe_div(rev, fa)
            pay_turn = safe_div(cost, ap)

            inv_days = _days(inv_turn)
            ar_days  = _days(ar_turn)
            pay_days = _days(pay_turn)

            ccc: float | None = None
            ccc_reason: str | None = None
            if inv_days is not None and ar_days is not None:
                if pay_days is not None:
                    ccc = round(inv_days + ar_days - pay_days, 2)
                else:
                    ccc_reason = "payable_days 不可用（acct_payable 或 oper_cost 缺失），CCC 无法计算"

            series.append({
                "end_date":             fmt_date(date_raw),
                "inv_turn":             inv_turn,
                "ar_turn":              ar_turn,
                "ca_turn":              ca_turn,
                "fa_turn":              fa_turn,
                "assets_turn":          assets_turn,
                "payable_turn":         pay_turn,
                "inventory_days":       inv_days,
                "receivable_days":      ar_days,
                "payable_days":         pay_days,
                "cash_conversion_cycle": ccc,
                "ccc_reason":           ccc_reason,
                "op_cycle":             op_cycle,
            })

        result: dict[str, Any] = {
            "symbol": symbol, "ts_code": ts_code,
            "annual": self.annual, "series": series,
            "comment": _comment(series), "source": "tushare",
        }
        if partial_errors:
            result["_partial_errors"] = partial_errors
        return result
