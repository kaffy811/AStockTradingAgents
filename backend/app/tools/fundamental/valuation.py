"""
app/tools/fundamental/valuation.py — 估值分位分析（M06 升级版）

数据源：Tushare daily_basic 区间接口（默认近 10 年）

金融口径：
- 日频数据降采样为月末序列（避免日内噪声干扰分位计算）
- PE_TTM / PS_TTM <= 0 的历史样本剔除（亏损/负营收期不参与分位）
- 当前 PE_TTM / PS_TTM <= 0 时 percentile 返回 null，不强行计算
- 上市不足 10 年时自动使用全部可用历史
- 字段缺失时返回 null + reason，不抛出异常

返回结构：
{
  "symbol": "600519", "ts_code": "600519.SH",
  "trade_date": "2026-07-04",
  "history_start": "2016-07",
  "history_end": "2026-07",
  "years_covered": 9.8,
  "monthly_samples": 118,
  "metrics": {
    "pe_ttm": {
      "current": 28.3, "percentile": 35.2,
      "min": 14.1, "p30": 22.4, "median": 28.9, "p70": 36.5, "max": 68.7, "mean": 30.1,
      "samples": 112, "note": null
    },
    "pb": { ... },
    "ps_ttm": { ... },
    "dv_ttm": { ... }
  },
  "source": "tushare"
}
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from app.datasource.tushare_client import tushare_client, _to_ts_code
from app.tools.fundamental.base import BaseFundamentalTool, FundamentalToolError

log = logging.getLogger(__name__)

# 估值指标：仅 PE_TTM / PS_TTM 要求 > 0 才计分位；PB / DV 通常不排除
_METRICS_POSITIVE_ONLY = {"pe_ttm", "ps_ttm"}  # <= 0 时 percentile=null

_METRIC_NAMES = {
    "pe_ttm":  "市盈率TTM",
    "pb":      "市净率",
    "ps_ttm":  "市销率TTM",
    "dv_ttm":  "股息率TTM%",
}


def _percentile_rank(series: pd.Series, current: float) -> float | None:
    """计算 current 在 series 中的百分位排名（0~100），保留 1 位小数。"""
    if len(series) == 0 or current is None:
        return None
    return round(float(np.mean(series.values <= current)) * 100, 1)


def _metric_stats(monthly_series: pd.Series, current: float | None, metric: str) -> dict:
    """计算单个估值指标的统计结果。"""
    # 过滤非正数样本（PE_TTM / PS_TTM 专用）
    if metric in _METRICS_POSITIVE_ONLY:
        hist = monthly_series[monthly_series > 0].dropna()
    else:
        hist = monthly_series.dropna()

    note: str | None = None
    percentile: float | None = None

    if current is not None and metric in _METRICS_POSITIVE_ONLY and current <= 0:
        note = f"当前 {metric}={current:.2f} ≤ 0（亏损/负值），百分位无意义"
        percentile = None
    elif current is not None and len(hist) > 0:
        percentile = _percentile_rank(hist, current)

    if len(hist) == 0:
        return {
            "current": round(current, 4) if current is not None else None,
            "percentile": None,
            "min": None, "p30": None, "median": None,
            "p70": None, "max": None, "mean": None,
            "samples": 0,
            "note": "历史样本为空（可能为新上市或数据缺失）",
        }

    return {
        "current":    round(current, 4) if current is not None else None,
        "percentile": percentile,
        "min":        round(float(hist.min()), 4),
        "p30":        round(float(hist.quantile(0.30)), 4),
        "median":     round(float(hist.quantile(0.50)), 4),
        "p70":        round(float(hist.quantile(0.70)), 4),
        "max":        round(float(hist.max()), 4),
        "mean":       round(float(hist.mean()), 4),
        "samples":    int(len(hist)),
        "note":       note,
    }


class ValuationTool(BaseFundamentalTool):
    module_key = "valuation"
    cache_ttl_seconds = 3600       # 1h（月末数据变化慢，但当日估值需要刷新）
    stale_ttl_seconds = 86400      # 24h

    async def fetch(self, market: str, symbol: str) -> dict[str, Any]:
        """从 Tushare daily_basic 获取近 10 年估值历史，计算分位数。"""
        ts_code = _to_ts_code(market, symbol)

        # 日期范围：近 10 年（或全部历史）
        today = datetime.now()
        end_date = today.strftime("%Y%m%d")
        start_date = (today - timedelta(days=365 * 10)).strftime("%Y%m%d")

        df = await tushare_client.get_daily_basic_range(
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
        )

        # 解析日期列，排序
        df["trade_date"] = pd.to_datetime(df["trade_date"].astype(str), format="%Y%m%d")
        df = df.sort_values("trade_date").reset_index(drop=True)

        if df.empty:
            raise FundamentalToolError(f"daily_basic 返回空数据 [{ts_code}]")

        # 转换估值列为数值
        for col in _METRIC_NAMES:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # 月末降采样：取每月最后一个交易日
        df_indexed = df.set_index("trade_date")
        monthly = df_indexed.resample("ME")[list(_METRIC_NAMES.keys())].last()
        monthly = monthly.dropna(how="all")

        # 当前值 = 最新一行的原始数据（日频）
        latest = df.iloc[-1]
        latest_date = latest["trade_date"]

        def _safe(col: str) -> float | None:
            v = latest.get(col)
            if v is None:
                return None
            try:
                f = float(v)
                return None if f != f else f   # NaN check
            except (TypeError, ValueError):
                return None

        # 覆盖年限
        if len(monthly) >= 2:
            hist_start = monthly.index[0].strftime("%Y-%m")
            hist_end = monthly.index[-1].strftime("%Y-%m")
            years_covered = round((monthly.index[-1] - monthly.index[0]).days / 365, 1)
        else:
            hist_start = hist_end = latest_date.strftime("%Y-%m")
            years_covered = 0.0

        # 计算各指标分位
        metrics: dict[str, dict] = {}
        for metric in _METRIC_NAMES:
            try:
                current = _safe(metric)
                if metric in monthly.columns:
                    series = monthly[metric].dropna()
                else:
                    series = pd.Series(dtype=float)
                metrics[metric] = _metric_stats(series, current, metric)
            except Exception as exc:
                log.warning("valuation metric %s 计算失败 [%s]: %s", metric, symbol, exc)
                metrics[metric] = {
                    "current": None, "percentile": None,
                    "min": None, "p30": None, "median": None,
                    "p70": None, "max": None, "mean": None,
                    "samples": 0,
                    "note": f"计算失败: {exc}",
                }

        return {
            "symbol":          symbol,
            "ts_code":         ts_code,
            "trade_date":      latest_date.strftime("%Y-%m-%d"),
            "history_start":   hist_start,
            "history_end":     hist_end,
            "years_covered":   years_covered,
            "monthly_samples": int(len(monthly)),
            "metrics":         metrics,
            "source":          "tushare",
        }
