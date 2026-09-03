"""
asset_structure.py — 资产结构分析

数据源：Tushare balancesheet（单表）

金融口径：
  current_asset_ratio = current_assets / total_assets
  liability_ratio = total_liab / total_assets
  goodwill_to_equity = goodwill / equity（商誉/净资产）
  cash_to_assets = money_cap / total_assets
  分母 <= 0 → null
  商誉占净资产 > 30% 时 comment 提示减值风险
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


def _comment(series: list[dict]) -> str:
    if not series: return "数据不足。"
    l = series[0]
    parts = []
    lr = l.get("liability_ratio_pct")
    gwr = l.get("goodwill_to_equity_pct")
    if lr is not None:
        parts.append(f"资产负债率 {lr:.1f}%")
    if gwr is not None and gwr > 30:
        parts.append(f"商誉占净资产 {gwr:.1f}%，存在较高商誉减值风险，请关注")
    elif gwr is not None:
        parts.append(f"商誉占净资产 {gwr:.1f}%")
    return f"{l.get('end_date','')} {'; '.join(parts)}。" if parts else "资产结构数据暂缺。"


class AssetStructureTool(BaseFundamentalTool):
    module_key = "asset_structure"
    cache_ttl_seconds = 14400
    stale_ttl_seconds = 172800

    def __init__(self, limit: int = 8, annual: bool = True):
        self.limit = limit
        self.annual = annual

    async def fetch(self, market: str, symbol: str) -> dict[str, Any]:
        ts_code = _to_ts_code(market, symbol)
        api_limit = self.limit * 4 if self.annual else self.limit
        df = await tushare_client.get_balancesheet(ts_code=ts_code, limit=api_limit)

        df = filter_report_type(df)
        if self.annual: df = filter_annual(df)
        df = df.sort_values("end_date", ascending=False).head(self.limit)
        if df.empty:
            raise FundamentalToolError(f"balancesheet 无数据 [{ts_code}]")

        series = []
        for _, row in df.iterrows():
            date_raw = str(row_get(row, "end_date") or "")
            ta    = safe_float(row_get(row, "total_assets"))
            tl    = safe_float(row_get(row, "total_liab"))
            eqy   = safe_float(row_get(row, "total_hldr_eqy_exc_min_int"))
            ca    = safe_float(row_get(row, "total_cur_assets"))
            nca   = safe_float(row_get(row, "total_nca"))
            cash  = safe_float(row_get(row, "money_cap"))
            ar    = safe_float(row_get(row, "accounts_receiv"))
            inv   = safe_float(row_get(row, "inventories"))
            fa    = safe_float(row_get(row, "fix_assets"))
            cip   = safe_float(row_get(row, "cip"))
            intan = safe_float(row_get(row, "intan_assets"))
            gw    = safe_float(row_get(row, "goodwill"))

            series.append({
                "end_date":               fmt_date(date_raw),
                "total_assets":           ta,
                "total_liab":             tl,
                "total_hldr_eqy_exc_min_int": eqy,
                "current_assets":         ca,
                "noncurrent_assets":      nca,
                "money_cap":              cash,
                "accounts_receiv":        ar,
                "inventories":            inv,
                "fixed_assets":           fa,
                "construction_in_process": cip,
                "intangible_assets":      intan,
                "goodwill":               gw,
                "current_asset_ratio_pct": safe_pct(ca, ta),
                "liability_ratio_pct":     safe_pct(tl, ta),
                "goodwill_to_equity_pct":  safe_pct(gw, eqy),
                "cash_to_assets_pct":      safe_pct(cash, ta),
            })

        latest = series[0] if series else {}
        return {
            "symbol": symbol, "ts_code": ts_code,
            "annual": self.annual,
            "rows": series,
            "series": series,
            "summary": {
                "total_assets": latest.get("total_assets"),
                "current_asset_ratio_pct": latest.get("current_asset_ratio_pct"),
                "liability_ratio_pct": latest.get("liability_ratio_pct"),
                "cash_to_assets_pct": latest.get("cash_to_assets_pct"),
                "goodwill_to_equity_pct": latest.get("goodwill_to_equity_pct"),
                "end_date": latest.get("end_date"),
            },
            "reasons": [],
            "comment": _comment(series), "source": "tushare",
        }
