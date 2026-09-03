"""
capital_occupation.py — 资金占用分析

数据源：Tushare balancesheet + income（concurrent）

金融口径：
  receivable_side = accounts_receiv + notes_receiv + prepayment（缺失字段用 0，记入 reason）
  payable_side = accounts_payable + notes_payable + adv_receipts + contract_liab（同上）
  occupation_power = payable_side / receivable_side（receivable_side <= 0 → null）
  revenue 来自 income.total_revenue（<=0 → 比率 null）
  comment：occupation_power > 1 → 占用上下游资金能力强；<1 → 被上下游占用资金
"""
from __future__ import annotations
import asyncio, logging
from typing import Any
import pandas as pd
from app.datasource.tushare_client import tushare_client, _to_ts_code, TushareAuthError
from app.tools.fundamental.base import BaseFundamentalTool, FundamentalToolError
from app.tools.fundamental._helpers import (
    safe_float, safe_pct, safe_div, fmt_date,
    filter_report_type, filter_annual, row_get
)
log = logging.getLogger(__name__)


def _sum_nullable(*vals: float | None, missing: list, names: list[str]) -> float:
    """加总，None 用 0 代替，并记录缺失字段名。"""
    total = 0.0
    for name, v in zip(names, vals):
        if v is None:
            missing.append(name)
        else:
            total += v
    return total


def _comment(series: list[dict]) -> str:
    if not series: return "数据不足。"
    l = series[0]
    op = l.get("occupation_power")
    if op is None: return "资金占用数据暂缺。"
    if op >= 1.5:
        label = "占用上下游资金能力强（经营预收款 / 应付较高）"
    elif op >= 1.0:
        label = "略占上下游资金优势"
    elif op >= 0.5:
        label = "被上下游资金小幅占用"
    else:
        label = "被上下游大量占用资金（应收/预付占比高）"
    return f"{l.get('end_date','')} 资金占用系数 {op:.2f}，{label}。"


class CapitalOccupationTool(BaseFundamentalTool):
    module_key = "capital_occupation"
    cache_ttl_seconds = 14400
    stale_ttl_seconds = 172800

    def __init__(self, limit: int = 8, annual: bool = True):
        self.limit = limit
        self.annual = annual

    async def fetch(self, market: str, symbol: str) -> dict[str, Any]:
        ts_code = _to_ts_code(market, symbol)
        api_limit = self.limit * 4 if self.annual else self.limit

        bs_task  = tushare_client.get_balancesheet(ts_code=ts_code, limit=api_limit)
        inc_task = tushare_client.get_income(ts_code=ts_code, limit=api_limit)
        bs_result, inc_result = await asyncio.gather(bs_task, inc_task, return_exceptions=True)

        partial_errors: list[str] = []
        bs_df = pd.DataFrame()
        inc_by_date: dict[str, Any] = {}

        if isinstance(bs_result, Exception):
            if isinstance(bs_result, TushareAuthError):
                partial_errors.append("balancesheet 暂不可用（权限不足）")
            else:
                partial_errors.append(f"balancesheet 失败: {bs_result}")
        else:
            bs_df = filter_report_type(bs_result)
            if self.annual: bs_df = filter_annual(bs_df)
            bs_df = bs_df.sort_values("end_date", ascending=False).head(self.limit)

        if isinstance(inc_result, Exception):
            if isinstance(inc_result, TushareAuthError):
                partial_errors.append("income 暂不可用（权限不足），revenue 将为 null")
            else:
                partial_errors.append(f"income 失败，revenue 将为 null: {inc_result}")
        else:
            tmp = filter_report_type(inc_result)
            if self.annual: tmp = filter_annual(tmp)
            for _, r in tmp.iterrows():
                inc_by_date[str(row_get(r, "end_date") or "")] = r

        if bs_df.empty:
            raise FundamentalToolError("balancesheet 无数据")

        series = []
        all_missing: list[str] = []
        for _, row in bs_df.iterrows():
            date_raw = str(row_get(row, "end_date") or "")
            inc_row = inc_by_date.get(date_raw, {})

            ar   = safe_float(row_get(row, "accounts_receiv"))
            nr   = safe_float(row_get(row, "notes_receiv"))
            prep = safe_float(row_get(row, "prepayment"))
            ap   = safe_float(row_get(row, "acct_payable"))
            np_  = safe_float(row_get(row, "notes_payable"))
            adv  = safe_float(row_get(row, "adv_receipts"))
            cl_  = safe_float(row_get(row, "contract_liab"))  # 可能 None（旧数据）
            rev  = safe_float(row_get(inc_row, "total_revenue"))

            miss_r, miss_p = [], []
            recv_side = _sum_nullable(ar, nr, prep,
                                      missing=miss_r, names=["accounts_receiv", "notes_receiv", "prepayment"])
            pay_side  = _sum_nullable(ap, np_, adv, cl_,
                                      missing=miss_p, names=["acct_payable", "notes_payable", "adv_receipts", "contract_liab"])
            for m in miss_r + miss_p:
                if m not in all_missing: all_missing.append(m)

            period: dict[str, Any] = {
                "end_date":                fmt_date(date_raw),
                "accounts_receiv":         ar,
                "notes_receiv":            nr,
                "prepayment":              prep,
                "accounts_payable":        ap,
                "notes_payable":           np_,
                "adv_receipts":            adv,
                "contract_liab":           cl_,
                "revenue":                 rev,
                "receivable_to_revenue_pct": safe_pct(recv_side, rev),
                "payable_to_revenue_pct":    safe_pct(pay_side, rev),
                "advance_to_revenue_pct":    safe_pct((adv or 0) + (cl_ or 0), rev),
                "occupation_power":          safe_div(pay_side, recv_side) if recv_side > 0 else None,
            }
            series.append(period)

        latest = series[0] if series else {}
        result: dict[str, Any] = {
            "symbol": symbol, "ts_code": ts_code,
            "annual": self.annual,
            "rows": series,
            "series": series,
            "summary": {
                "occupation_power": latest.get("occupation_power"),
                "receivable_to_revenue_pct": latest.get("receivable_to_revenue_pct"),
                "payable_to_revenue_pct": latest.get("payable_to_revenue_pct"),
                "advance_to_revenue_pct": latest.get("advance_to_revenue_pct"),
                "end_date": latest.get("end_date"),
            },
            "reasons": [],
            "comment": _comment(series), "source": "tushare",
        }
        if all_missing:
            result["_partial_errors"] = [f"以下字段部分期间缺失（已用 0 代替）: {list(set(all_missing))}"]
        if partial_errors:
            result.setdefault("_partial_errors", []).extend(partial_errors)
        return result
