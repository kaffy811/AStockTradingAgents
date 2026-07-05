"""
app/tools/fundamental/dupont.py — 杜邦分析（年度序列）

数据源：Tushare fina_indicator（过滤保留年度报告，即 end_date 以 1231 结尾）

金融口径：
  ROE = 净利率 × 总资产周转率 × 权益乘数
  权益乘数 = 1 / (1 - 资产负债率/100)

  ⚠️ 注意：Tushare 披露的 ROE 基于实际净资产（可能为加权平均），
      三因子乘积基于期末资产负债率和当年收入计算，两者因平均口径不同
      可能存在差异。factor_product_pct 仅供参考。

  factor_product_pct = net_margin_pct/100 * assets_turn * equity_multiplier * 100
  任一因子缺失 → factor_product_pct = null

返回结构：
{
  "symbol":  "600519",
  "ts_code": "600519.SH",
  "series": [
    {
      "end_date":           "2025-12-31",
      "roe_pct":            40.2,    # Tushare 披露的 ROE（%）
      "net_margin_pct":     49.8,    # 净利率（%）
      "assets_turn":        0.45,    # 总资产周转率（次/年）
      "equity_multiplier":  2.08,    # 权益乘数（= 1/(1-负债率/100)）
      "factor_product_pct": 46.3,    # 三因子乘积（%），与 roe_pct 可能有差
      "debt_to_assets":     51.9,    # 资产负债率（%）
    }, ...
  ],
  "comment": "2025年ROE较2024年上升X.Xpp，主要驱动因子为净利率提升。",
  "disclaimer": "factor_product_pct 基于期末口径，与 Tushare 披露 roe_pct（加权平均）因平均口径不同可能存在差异。",
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

_DISCLAIMER = (
    "factor_product_pct 基于期末资产负债率计算权益乘数，"
    "与 Tushare 披露 roe_pct（加权平均净资产）因平均口径不同可能存在差异，仅供参考。"
)


def _safe_float(v: Any, ndigits: int = 4) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return None if f != f else round(f, ndigits)
    except (TypeError, ValueError):
        return None


def _equity_multiplier(debt_to_assets: float | None) -> float | None:
    """资产负债率 → 权益乘数。负债率必须在 (0, 100) 内。"""
    if debt_to_assets is None:
        return None
    d = debt_to_assets / 100.0
    if d <= 0 or d >= 1:
        return None
    return round(1.0 / (1.0 - d), 4)


def _factor_product(net_margin_pct, assets_turn, equity_mult) -> float | None:
    if any(v is None for v in [net_margin_pct, assets_turn, equity_mult]):
        return None
    try:
        return round((net_margin_pct / 100.0) * assets_turn * equity_mult * 100.0, 4)
    except (TypeError, ZeroDivisionError):
        return None


def _generate_comment(series: list[dict]) -> str:
    """
    生成最新年度 ROE 变化的驱动因子文字说明。
    比较最新两个年度的三因子变化幅度，找最大贡献因子。
    """
    if len(series) < 2:
        return "历史数据不足两年，无法进行因子对比。"

    latest = series[0]
    prev = series[1]

    roe_now = latest.get("roe_pct")
    roe_prev = prev.get("roe_pct")
    if roe_now is None or roe_prev is None:
        return "ROE 数据缺失，无法生成驱动因子说明。"

    roe_delta = round(roe_now - roe_prev, 2)
    direction = "上升" if roe_delta >= 0 else "下降"

    # 各因子变化（绝对值大的为主要驱动）
    factors = {}
    for key, label in [
        ("net_margin_pct", "净利率"),
        ("assets_turn",    "总资产周转率"),
        ("equity_multiplier", "权益乘数"),
    ]:
        v_now = latest.get(key)
        v_prev = prev.get(key)
        if v_now is not None and v_prev is not None:
            factors[label] = abs(v_now - v_prev)

    if not factors:
        return (
            f"{latest['end_date'][:4]} 年 ROE 较上年 {direction} {abs(roe_delta):.1f}pp，"
            "各因子数据不足，无法定位主要驱动因子。"
        )

    main_driver = max(factors, key=factors.get)
    return (
        f"{latest['end_date'][:4]} 年 ROE={roe_now:.1f}%，"
        f"较上年 {direction} {abs(roe_delta):.1f}pp，"
        f"主要驱动因子为{main_driver}变化（绝对变化最大）。"
    )


class DupontTool(BaseFundamentalTool):
    module_key = "dupont"
    cache_ttl_seconds = 14400      # 4h（财报频率）
    stale_ttl_seconds = 172800     # 48h

    async def fetch(self, market: str, symbol: str) -> dict[str, Any]:
        """从 Tushare fina_indicator 提取年度报表做杜邦拆解。"""
        ts_code = _to_ts_code(market, symbol)
        df = await tushare_client.get_fina_indicator(ts_code=ts_code)

        # 只保留年报（end_date 以 1231 结尾）
        if "end_date" in df.columns:
            annual = df[df["end_date"].astype(str).str.endswith("1231")].copy()
        else:
            annual = df.copy()

        if annual.empty:
            raise FundamentalToolError(f"fina_indicator 无年度数据 [{ts_code}]")

        annual = annual.sort_values("end_date", ascending=False).reset_index(drop=True)

        series: list[dict] = []
        for _, row in annual.iterrows():
            end_raw = str(row.get("end_date", ""))
            # 格式化为 YYYY-MM-DD
            if len(end_raw) == 8:
                end_date_fmt = f"{end_raw[:4]}-{end_raw[4:6]}-{end_raw[6:]}"
            else:
                end_date_fmt = end_raw

            roe      = _safe_float(row.get("roe"))
            nm       = _safe_float(row.get("netprofit_margin"))
            at       = _safe_float(row.get("assets_turn"))
            dta      = _safe_float(row.get("debt_to_assets"))
            em       = _equity_multiplier(dta)
            fp       = _factor_product(nm, at, em)

            series.append({
                "end_date":           end_date_fmt,
                "roe_pct":            roe,
                "net_margin_pct":     nm,
                "assets_turn":        at,
                "equity_multiplier":  em,
                "factor_product_pct": fp,
                "debt_to_assets":     dta,
            })

        comment = _generate_comment(series)

        return {
            "symbol":      symbol,
            "ts_code":     ts_code,
            "series":      series,
            "comment":     comment,
            "disclaimer":  _DISCLAIMER,
            "source":      "tushare",
        }
