"""
solvency.py — 偿债能力分析

数据源：Tushare balancesheet + fina_indicator（concurrent）

金融口径：
  debt_to_assets → fina_indicator 字段（优先）
  current_ratio = total_cur_assets / total_cur_liab
  quick_ratio = (total_cur_assets - inventories) / total_cur_liab
  cash_ratio = money_cap / total_cur_liab
  equity_multiplier = total_assets / equity（期末口径）
  interest_coverage = ebit / fin_exp（fin_exp <= 0 → null + reason）
  ocf_to_debt → Phase 2A 暂不计算（需 cashflow 表），返回 null + reason
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


def _comment(series: list[dict]) -> str:
    if not series: return "数据不足。"
    l = series[0]
    parts = []
    cr = l.get("current_ratio"); dta = l.get("debt_to_assets_pct")
    if cr is not None:
        label = "充足" if cr >= 2 else ("一般" if cr >= 1 else "不足")
        parts.append(f"流动比率 {cr:.2f}（{label}）")
    if dta is not None: parts.append(f"资产负债率 {dta:.1f}%")
    return f"{l.get('end_date','')} {'; '.join(parts)}。" if parts else "偿债能力数据暂缺。"


class SolvencyTool(BaseFundamentalTool):
    module_key = "solvency"
    cache_ttl_seconds = 14400
    stale_ttl_seconds = 172800

    def __init__(self, limit: int = 8, annual: bool = True):
        self.limit = limit
        self.annual = annual

    async def fetch(self, market: str, symbol: str) -> dict[str, Any]:
        ts_code = _to_ts_code(market, symbol)
        api_limit = self.limit * 4 if self.annual else self.limit

        bs_task = tushare_client.get_balancesheet(ts_code=ts_code, limit=api_limit)
        fi_task = tushare_client.get_fina_indicator(ts_code=ts_code)
        bs_result, fi_result = await asyncio.gather(bs_task, fi_task, return_exceptions=True)

        partial_errors: list[str] = []
        bs_df = pd.DataFrame()
        fi_by_date: dict[str, Any] = {}

        if isinstance(bs_result, Exception):
            partial_errors.append(f"balancesheet 失败: {bs_result}")
        else:
            bs_df = filter_report_type(bs_result)
            if self.annual: bs_df = filter_annual(bs_df)
            bs_df = bs_df.sort_values("end_date", ascending=False).head(self.limit)

        if isinstance(fi_result, Exception):
            partial_errors.append(f"fina_indicator 失败: {fi_result}")
        else:
            fi_tmp = fi_result.copy()
            if self.annual: fi_tmp = filter_annual(fi_tmp)
            for _, r in fi_tmp.iterrows():
                fi_by_date[str(row_get(r, "end_date") or "")] = r

        if bs_df.empty:
            raise FundamentalToolError("balancesheet 无数据")

        series = []
        for _, row in bs_df.iterrows():
            date_raw = str(row_get(row, "end_date") or "")
            fi_row = fi_by_date.get(date_raw, {})

            ta   = safe_float(row_get(row, "total_assets"))
            tl   = safe_float(row_get(row, "total_liab"))
            eqy  = safe_float(row_get(row, "total_hldr_eqy_exc_min_int"))
            ca   = safe_float(row_get(row, "total_cur_assets"))
            cl   = safe_float(row_get(row, "total_cur_liab"))
            inv  = safe_float(row_get(row, "inventories"))
            cash = safe_float(row_get(row, "money_cap"))
            ebit = safe_float(row_get(fi_row, "ebit"))
            fin_exp = safe_float(row_get(fi_row, "ebitda"))  # 用 fin_exp 计算利息覆盖

            # interest_coverage: 需要 EBIT 和利息费用
            # Tushare fina_indicator 不直接有利息费用；Phase 2A 返回 null + reason
            interest_coverage = None
            ic_reason = "利息费用数据不在 fina_indicator，暂未计算"

            # quick ratio
            quick = safe_div(
                (ca - (inv or 0)) if ca is not None else None,
                cl
            )

            series.append({
                "end_date":          fmt_date(date_raw),
                "debt_to_assets_pct": safe_float(row_get(fi_row, "debt_to_assets")),
                "current_ratio":     safe_div(ca, cl),
                "quick_ratio":       quick,
                "cash_ratio":        safe_div(cash, cl),
                "equity_multiplier": safe_div(ta, eqy),
                "interest_coverage": interest_coverage,
                "interest_coverage_reason": ic_reason if interest_coverage is None else None,
                "ocf_to_debt":       None,
                "ocf_to_debt_reason": "Phase 2A 暂不拉取 cashflow 表，返回 null",
            })

        latest = series[0] if series else {}
        result: dict[str, Any] = {
            "symbol": symbol, "ts_code": ts_code,
            "annual": self.annual,
            "rows": series,
            "series": series,
            "summary": {
                "debt_to_assets_pct": latest.get("debt_to_assets_pct"),
                "current_ratio": latest.get("current_ratio"),
                "quick_ratio": latest.get("quick_ratio"),
                "cash_ratio": latest.get("cash_ratio"),
                "equity_multiplier": latest.get("equity_multiplier"),
                "end_date": latest.get("end_date"),
            },
            "reasons": [],
            "comment": _comment(series), "source": "tushare",
        }
        if partial_errors:
            result["_partial_errors"] = partial_errors
        return result

    async def fetch_baostock(self, market: str, symbol: str) -> dict[str, Any]:
        """
        BaoStock 备用：偿债能力（currentRatio / quickRatio / cashRatio / liabilityToAsset）。
        """
        from app.datasource.baostock_client import baostock_client
        from app.datasource.tushare_client import _to_ts_code as _ts
        ts_code = _ts(market, symbol)
        rows = await baostock_client.get_balance_data(ts_code, n=self.limit)
        if not rows:
            raise RuntimeError("BaoStock get_balance_data 无数据")

        series = []
        for r in rows:
            stat_date = r.get("stat_date") or ""
            if len(stat_date) == 8 and "-" not in stat_date:
                stat_date = f"{stat_date[:4]}-{stat_date[4:6]}-{stat_date[6:]}"
            # liabilityToAsset → debt_to_assets_pct (BaoStock 返回小数如 0.519，乘 100 转 %)
            liability_ratio = r.get("liability_to_asset")
            debt_to_assets_pct = round(float(liability_ratio) * 100, 2) if liability_ratio is not None else None
            series.append({
                "end_date":          stat_date,
                "debt_to_assets_pct": debt_to_assets_pct,
                "current_ratio":     r.get("current_ratio"),
                "quick_ratio":       r.get("quick_ratio"),
                "cash_ratio":        r.get("cash_ratio"),
                "equity_multiplier": None,   # BaoStock 不直接提供
                "interest_coverage": None,
                "interest_coverage_reason": "BaoStock 不提供利息费用数据",
                "ocf_to_debt":       None,
                "ocf_to_debt_reason": "BaoStock 不提供经营现金流数据",
            })
        series.sort(key=lambda x: x.get("end_date") or "", reverse=True)
        series = series[:self.limit]

        latest = series[0] if series else {}
        return {
            "symbol": symbol, "ts_code": ts_code,
            "annual": self.annual,
            "rows": series,
            "series": series,
            "summary": {
                "debt_to_assets_pct": latest.get("debt_to_assets_pct"),
                "current_ratio": latest.get("current_ratio"),
                "quick_ratio": latest.get("quick_ratio"),
                "cash_ratio": latest.get("cash_ratio"),
                "equity_multiplier": None,
                "end_date": latest.get("end_date"),
            },
            "reasons": [],
            "comment": _comment(series),
            "source": "baostock",
            "_partial_errors": ["BaoStock 备用：权益乘数/利息保障/OCF 相关字段不可用"],
        }
