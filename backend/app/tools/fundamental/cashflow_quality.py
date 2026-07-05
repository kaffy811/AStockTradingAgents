"""
app/tools/fundamental/cashflow_quality.py — 现金流质量分析（M05 升级版）

数据源：Tushare cashflow + income（按 end_date + report_type 对齐）

金融口径：
  ocf              = 经营活动现金流净额（n_cashflow_act）
  net_profit_parent = 归母净利润（n_income_attr_p，来自 income 表）
  revenue          = 营业总收入（total_revenue，来自 income 表）
  ocf_to_np        = ocf / net_profit_parent（净现比；分母 ≤ 0 时返回 null）
  cash_sales_ratio = c_fr_sale_sg / revenue（收现比；revenue ≤ 0 时返回 null）
  core_profit_cash_ratio = ocf / (n_income_attr_p + 折旧摊销)（核心利润含金量，近似）
  fcf              = ocf - c_pay_acq_const_fiolta（自由现金流）
  cashflow_profile = 经/投/融 现金流符号组合 → 类型标签

  现金流画像（经营 / 投资 / 筹资 正负号）：
    (+, -, -)  → 奶牛型（成熟稳健，主业产钱、投资/偿债并举）
    (+, -, +)  → 扩张型（主业盈余+外部融资，加大投资）
    (+, +, -)  → 收缩型（经营正流+缩减投资，用于偿债）
    (+, +, +)  → 困惑型（三流均正，较少见）
    (-, -, +)  → 输血型（经营失血，依赖外部融资维持）
    (-, +, -)  → 调整型（出售资产偿债）
    (-, +, +)  → 危机型（出售资产+融资，经营持续亏损）
    (-, -, -)  → 衰退型（三流均负）

返回结构：
{
  "symbol":  "600519",
  "ts_code": "600519.SH",
  "periods": [
    {
      "end_date":             "2025-12-31",
      "ocf":                  8.5e10,
      "net_profit_parent":    8.6e10,
      "revenue":              1.7e11,
      "ocf_to_np":            0.99,
      "cash_sales_ratio":     1.02,
      "core_profit_cash_ratio": 0.97,
      "fcf":                  8.2e10,
      "cashflow_profile":     "奶牛型",
      "profile_signs":        ["+", "-", "-"],
      "comment":              "净现比 0.99，经营现金流质量良好。"
    }, ...
  ],
  "source": "tushare"
}
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from app.datasource.tushare_client import tushare_client, _to_ts_code
from app.tools.fundamental.base import BaseFundamentalTool, FundamentalToolError

log = logging.getLogger(__name__)

# 现金流画像映射 (OCF, ICF, FCF) → 标签
_PROFILE_MAP: dict[tuple[int, int, int], str] = {
    (1, -1, -1): "奶牛型",
    (1, -1,  1): "扩张型",
    (1,  1, -1): "收缩型",
    (1,  1,  1): "困惑型",
    (-1, -1,  1): "输血型",
    (-1,  1, -1): "调整型",
    (-1,  1,  1): "危机型",
    (-1, -1, -1): "衰退型",
}


def _sign(v: float | None) -> int | None:
    if v is None:
        return None
    return 1 if v > 0 else -1


def _safe(v: Any, ndigits: int = 4) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return None if f != f else round(f, ndigits)
    except (TypeError, ValueError):
        return None


def _cashflow_profile(ocf, icf, fnc) -> tuple[str, list[str]]:
    """根据三类现金流正负号返回画像标签和符号列表。"""
    signs_raw = (_sign(ocf), _sign(icf), _sign(fnc))
    if None in signs_raw:
        return "数据不足", [
            "+" if s == 1 else ("-" if s == -1 else "?")
            for s in signs_raw
        ]
    profile = _PROFILE_MAP.get(signs_raw, "其他")
    sign_strs = ["+" if s == 1 else "-" for s in signs_raw]
    return profile, sign_strs


def _ocf_comment(ocf_to_np: float | None, cash_sales: float | None) -> str:
    parts = []
    if ocf_to_np is not None:
        if ocf_to_np >= 1.0:
            parts.append(f"净现比 {ocf_to_np:.2f}，经营现金流质量良好（主业含金量高）")
        elif ocf_to_np >= 0.7:
            parts.append(f"净现比 {ocf_to_np:.2f}，经营现金流基本匹配利润")
        else:
            parts.append(f"净现比 {ocf_to_np:.2f}，经营现金流显著低于净利润（关注应收/存货）")
    if cash_sales is not None:
        if cash_sales >= 1.0:
            parts.append(f"收现比 {cash_sales:.2f}，销售回款充分")
        else:
            parts.append(f"收现比 {cash_sales:.2f}，销售回款低于营收（关注应收账款）")
    return "；".join(parts) + "。" if parts else "现金流数据不足，无法生成分析。"


class CashflowQualityTool(BaseFundamentalTool):
    module_key = "cashflow_quality"
    cache_ttl_seconds = 14400       # 4h
    stale_ttl_seconds = 172800      # 48h

    async def fetch(self, market: str, symbol: str) -> dict[str, Any]:
        """
        并发拉取 cashflow 和 income，按 end_date 对齐，计算现金流质量指标。
        单表失败时另一表仍可返回部分数据。
        """
        import asyncio
        ts_code = _to_ts_code(market, symbol)

        # 并发拉取两张表（return_exceptions=True 保证单表失败不崩溃）
        cf_task = tushare_client.get_cashflow(ts_code=ts_code, limit=8)
        inc_task = tushare_client.get_income(ts_code=ts_code, limit=8)
        cf_result, inc_result = await asyncio.gather(cf_task, inc_task, return_exceptions=True)

        partial_errors: list[str] = []

        if isinstance(cf_result, Exception):
            partial_errors.append(f"cashflow 表拉取失败: {cf_result}")
            cf_df = pd.DataFrame()
        else:
            cf_df = cf_result

        if isinstance(inc_result, Exception):
            partial_errors.append(f"income 表拉取失败: {inc_result}")
            inc_df = pd.DataFrame()
        else:
            inc_df = inc_result

        if cf_df.empty and inc_df.empty:
            raise FundamentalToolError(
                "cashflow 和 income 均无数据，无法计算现金流质量"
            )

        # 只保留合并报表（report_type=1）
        def _filter_annual(df: pd.DataFrame) -> pd.DataFrame:
            if "report_type" in df.columns:
                merged = df[df["report_type"].astype(str) == "1"]
                return merged if not merged.empty else df
            return df

        cf_df = _filter_annual(cf_df)
        inc_df = _filter_annual(inc_df)

        # 按 end_date 降序取最近 8 期
        if not cf_df.empty and "end_date" in cf_df.columns:
            cf_df = cf_df.sort_values("end_date", ascending=False).head(8)
        if not inc_df.empty and "end_date" in inc_df.columns:
            inc_df = inc_df.sort_values("end_date", ascending=False).head(8)

        # 构建 end_date → row 的快速查找
        inc_by_date: dict[str, Any] = {}
        if not inc_df.empty and "end_date" in inc_df.columns:
            for _, row in inc_df.iterrows():
                inc_by_date[str(row["end_date"])] = row

        cf_by_date: dict[str, Any] = {}
        if not cf_df.empty and "end_date" in cf_df.columns:
            for _, row in cf_df.iterrows():
                cf_by_date[str(row["end_date"])] = row

        # 合并所有出现过的 end_date
        all_dates = sorted(
            set(list(inc_by_date.keys()) + list(cf_by_date.keys())),
            reverse=True,
        )[:8]

        periods: list[dict[str, Any]] = []
        for date_str in all_dates:
            cf_row = cf_by_date.get(date_str)
            inc_row = inc_by_date.get(date_str)

            # 格式化日期
            if len(date_str) == 8:
                end_date_fmt = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
            else:
                end_date_fmt = date_str

            # 从 cashflow 表提取
            ocf      = _safe(cf_row.get("n_cashflow_act") if cf_row is not None else None)
            icf      = _safe(cf_row.get("n_cashflow_inv_act") if cf_row is not None else None)
            fnc      = _safe(cf_row.get("n_cash_flows_fnc_act") if cf_row is not None else None)
            c_sale   = _safe(cf_row.get("c_fr_sale_sg") if cf_row is not None else None)   # 销售回款
            capex    = _safe(cf_row.get("c_pay_acq_const_fiolta") if cf_row is not None else None)  # 购固资
            depr     = _safe(cf_row.get("depr_fa_coga_dpba") if cf_row is not None else None)  # 折旧摊销

            # 从 income 表提取
            net_p_parent = _safe(inc_row.get("n_income_attr_p") if inc_row is not None else None)
            revenue  = _safe(inc_row.get("total_revenue") if inc_row is not None else None)

            # 派生指标
            # 净现比：ocf / 归母净利润（归母净利润 ≤ 0 时无意义）
            if ocf is not None and net_p_parent is not None and net_p_parent > 0:
                ocf_to_np = round(ocf / net_p_parent, 4)
            else:
                ocf_to_np = None

            # 收现比：销售回款 / 营业总收入（revenue ≤ 0 时无意义）
            if c_sale is not None and revenue is not None and revenue > 0:
                cash_sales_ratio = round(c_sale / revenue, 4)
            else:
                cash_sales_ratio = None

            # 核心利润含金量（近似）：ocf / (归母净利润 + 折旧摊销)
            core_base = None
            if net_p_parent is not None and depr is not None:
                core_base = net_p_parent + depr
            elif net_p_parent is not None:
                core_base = net_p_parent
            if ocf is not None and core_base is not None and core_base > 0:
                core_ratio = round(ocf / core_base, 4)
            else:
                core_ratio = None

            # 自由现金流 = 经营现金流 - 购建固定资产
            if ocf is not None and capex is not None:
                fcf = round(ocf - abs(capex), 2)   # capex 在 Tushare 通常为正数
            elif ocf is not None:
                fcf = ocf
            else:
                fcf = None

            # 现金流画像
            profile, sign_strs = _cashflow_profile(ocf, icf, fnc)
            comment = _ocf_comment(ocf_to_np, cash_sales_ratio)

            periods.append({
                "end_date":               end_date_fmt,
                "ocf":                    ocf,
                "net_profit_parent":      net_p_parent,
                "revenue":                revenue,
                "ocf_to_np":              ocf_to_np,
                "cash_sales_ratio":       cash_sales_ratio,
                "core_profit_cash_ratio": core_ratio,
                "fcf":                    fcf,
                "cashflow_profile":       profile,
                "profile_signs":          sign_strs,   # ["+"/"-"/...]  经/投/融
                "comment":                comment,
            })

        result: dict[str, Any] = {
            "symbol":  symbol,
            "ts_code": ts_code,
            "periods": periods,
            "source":  "tushare",
        }
        if partial_errors:
            result["_partial_errors"] = partial_errors
        return result

    async def fetch_akshare(self, market: str, symbol: str) -> dict[str, Any]:
        """AkShare 备用：仅能提供经营现金流净额（单期）。"""
        from app.datasource.akshare_client import akshare_fs_client
        raw = await akshare_fs_client.get_cash_flow(symbol=symbol)
        return {
            "symbol":  symbol,
            "ts_code": _to_ts_code(market, symbol),
            "periods": [{
                "end_date":               raw.get("report_date"),
                "ocf":                    raw.get("operating_cashflow"),
                "net_profit_parent":      None,
                "revenue":                None,
                "ocf_to_np":              None,
                "cash_sales_ratio":       None,
                "core_profit_cash_ratio": None,
                "fcf":                    None,
                "cashflow_profile":       "数据不足",
                "profile_signs":          ["?", "?", "?"],
                "comment":                "AkShare 备用：仅有经营活动现金流净额。",
            }],
            "source": "akshare_fallback",
            "_partial_errors": ["AkShare 备用：缺少 income 表数据，多数指标不可用"],
        }
