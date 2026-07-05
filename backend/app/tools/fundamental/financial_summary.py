"""
app/tools/fundamental/financial_summary.py — M02 财务指标摘要

数据源（优先）：Tushare fina_indicator 接口
备用源（ENABLE_AKSHARE=true）：AkShare stock_financial_abstract_ths

返回最新报告期的核心财务比率：
{
  "symbol":              "600519",
  "ts_code":             "600519.SH",
  "end_date":            "20251231",
  "ann_date":            "20260328",
  "roe":                 40.2,       # 净资产收益率 %
  "roe_waa":             38.5,       # 加权平均 ROE %
  "roa":                 22.1,       # 总资产净利率 %
  "roic":                35.0,       # 投入资本回报率 %
  "grossprofit_margin":  91.5,       # 毛利率 %
  "netprofit_margin":    49.8,       # 净利率 %
  "debt_to_assets":      16.3,       # 资产负债率 %
  "current_ratio":       3.2,        # 流动比率
  "quick_ratio":         2.9,        # 速动比率
  "assets_turn":         0.45,       # 总资产周转率（次/年）
  "netprofit_yoy":       18.5,       # 净利润同比增长率 %
  "tr_yoy":              16.8,       # 营业总收入同比增长率 %
  "or_yoy":              15.2,       # 营业收入同比增长率 %
  "source":              "tushare",
}
"""

from __future__ import annotations

import logging
from typing import Any

from app.tools.fundamental.base import BaseFundamentalTool, FundamentalToolError
from app.datasource.tushare_client import tushare_client, _to_ts_code

log = logging.getLogger(__name__)

# 需要提取的字段（Tushare fina_indicator 列名 → 输出字段名）
_FIELD_MAP = {
    "roe":               "roe",
    "roe_waa":           "roe_waa",
    "roa":               "roa",
    "roic":              "roic",
    "grossprofit_margin": "grossprofit_margin",
    "netprofit_margin":  "netprofit_margin",
    "debt_to_assets":    "debt_to_assets",
    "current_ratio":     "current_ratio",
    "quick_ratio":       "quick_ratio",
    "assets_turn":       "assets_turn",
    "netprofit_yoy":     "netprofit_yoy",
    "tr_yoy":            "tr_yoy",
    "or_yoy":            "or_yoy",
    "ebit":              "ebit",
    "ebitda":            "ebitda",
    "beps":              "beps",       # 基本每股收益
    "ocfps":             "ocfps",     # 每股经营活动现金流
}


class FinancialSummaryTool(BaseFundamentalTool):
    module_key = "financial_summary"
    cache_ttl_seconds = 14400      # 4h（财报季度更新）
    stale_ttl_seconds = 172800     # 48h stale 降级

    async def fetch(self, market: str, symbol: str) -> dict[str, Any]:
        """从 Tushare fina_indicator 获取最新一期财务指标摘要。"""
        ts_code = _to_ts_code(market, symbol)
        df = await tushare_client.get_fina_indicator(ts_code=ts_code)

        # 按报告期降序，取最新
        df = df.sort_values("end_date", ascending=False)
        row = df.iloc[0]

        partial_errors: list[str] = []

        result: dict[str, Any] = {
            "symbol":   symbol,
            "ts_code":  ts_code,
            "end_date": str(row.get("end_date", "")),
            "ann_date": str(row.get("ann_date", "")),
            "source":   "tushare",
        }

        for ts_col, out_key in _FIELD_MAP.items():
            raw = row.get(ts_col)
            if raw is None or (isinstance(raw, float) and raw != raw):  # NaN check
                result[out_key] = None
                continue
            try:
                result[out_key] = round(float(raw), 4)
            except (TypeError, ValueError):
                result[out_key] = None
                partial_errors.append(f"{out_key}: 解析失败（原始值={raw!r}）")

        if partial_errors:
            log.debug("financial_summary partial_errors [%s]: %s", symbol, partial_errors)

        # 将 partial_errors 附加到 result，由聚合器读取后放入 envelope
        result["_partial_errors"] = partial_errors
        return result

    async def fetch_akshare(self, market: str, symbol: str) -> dict[str, Any]:
        """AkShare 备用：stock_financial_abstract_ths 财务摘要。"""
        from app.datasource.akshare_client import akshare_fs_client
        raw = await akshare_fs_client.get_financial_abstract(symbol=symbol)

        # AkShare 字段映射到标准字段
        result: dict[str, Any] = {
            "symbol":  symbol,
            "ts_code": _to_ts_code(market, symbol),
            "end_date": raw.get("report_date", ""),
            "ann_date": None,
            "roe":               raw.get("roe"),
            "roe_waa":           None,
            "roa":               None,
            "roic":              None,
            "grossprofit_margin": raw.get("gross_margin"),
            "netprofit_margin":  raw.get("net_margin"),
            "debt_to_assets":    raw.get("debt_ratio"),
            "current_ratio":     None,
            "quick_ratio":       None,
            "assets_turn":       None,
            "netprofit_yoy":     raw.get("net_profit_growth_yoy"),
            "tr_yoy":            raw.get("revenue_growth_yoy"),
            "or_yoy":            raw.get("revenue_growth_yoy"),
            "source": "akshare_fallback",
            "_partial_errors": ["AkShare 备用：部分字段不可用（roa/roic/current_ratio 等）"],
        }
        return result
