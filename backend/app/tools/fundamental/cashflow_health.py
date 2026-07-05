"""
app/tools/fundamental/cashflow_health.py — M05 现金流量健康度

数据源（优先）：Tushare cashflow 接口（最近 8 期）
备用源（ENABLE_AKSHARE=true）：AkShare stock_financial_cash_ths

返回最近 8 期的现金流核心指标，并计算：
  - 经营现金流净额（n_cashflow_act）
  - 经营现金流 / 归母净利润比值（cash_to_profit_ratio）
  - 自由现金流（free_cashflow）

{
  "symbol":  "600519",
  "ts_code": "600519.SH",
  "periods": [
    {
      "end_date":          "20251231",
      "ann_date":          "20260328",
      "report_type":       "1",
      "n_cashflow_act":    8.5e10,      # 经营活动现金流净额（元）
      "free_cashflow":     8.2e10,      # 自由现金流（元）
      "c_paid_goods_s":    1.0e10,      # 购买商品、接受劳务支付的现金（元）
      "c_inf_fr_operate_a": 9.5e10,     # 经营活动现金流入合计（元）
      "st_cash_out_act":   1.0e10,      # 经营活动现金流出合计（元）
      "n_cashflow_inv_act": -5.0e9,     # 投资活动现金流净额（元）
      "n_cash_flows_fnc_act": -3.0e10, # 筹资活动现金流净额（元）
      "n_incr_cash_cash_equ": 4.5e10,  # 现金及现金等价物净增加额（元）
      "cash_to_profit_ratio": 0.98,    # 经营现金流/归母净利润（由聚合层计算）
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
    "n_cashflow_act", "free_cashflow",
    "c_paid_goods_s", "c_inf_fr_operate_a", "st_cash_out_act",
    "n_cashflow_inv_act", "n_cash_flows_fnc_act",
    "n_incr_cash_cash_equ",
    "c_recp_borrow", "c_prepay_amt_borr",
    "c_pay_dist_dpcp_int_exp",
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


class CashflowHealthTool(BaseFundamentalTool):
    module_key = "cashflow_health"
    cache_ttl_seconds = 14400
    stale_ttl_seconds = 172800

    async def fetch(self, market: str, symbol: str) -> dict[str, Any]:
        """从 Tushare cashflow 获取最近 8 期现金流健康度指标。"""
        ts_code = _to_ts_code(market, symbol)
        df = await tushare_client.get_cashflow(ts_code=ts_code, limit=8)

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

    async def fetch_akshare(self, market: str, symbol: str) -> dict[str, Any]:
        """AkShare 备用：stock_financial_cash_ths 现金流。"""
        from app.datasource.akshare_client import akshare_fs_client
        raw = await akshare_fs_client.get_cash_flow(symbol=symbol)

        period: dict[str, Any] = {
            "end_date":         raw.get("report_date"),
            "ann_date":         None,
            "report_type":      None,
            "n_cashflow_act":   raw.get("operating_cashflow"),
            "free_cashflow":    None,
            "c_paid_goods_s":   None,
            "c_inf_fr_operate_a": None,
            "st_cash_out_act":  None,
            "n_cashflow_inv_act": None,
            "n_cash_flows_fnc_act": None,
            "n_incr_cash_cash_equ": None,
            "c_recp_borrow":    None,
            "c_prepay_amt_borr": None,
            "c_pay_dist_dpcp_int_exp": None,
        }

        return {
            "symbol":  symbol,
            "ts_code": _to_ts_code(market, symbol),
            "periods": [period],
            "source":  "akshare_fallback",
            "_partial_errors": ["AkShare 备用：仅有最新一期经营活动现金流净额"],
        }
