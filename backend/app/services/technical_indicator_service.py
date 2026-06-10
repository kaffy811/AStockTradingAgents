"""
TechnicalIndicatorService — 纯 Python 技术指标计算。

输入：list[dict]，每条为一根 K线（date, open, close, high, low, volume, ...）
输出：JSON 可序列化 dict，所有值均为 Python 原生类型（int / float / str / None）。

设计原则：
  - 不依赖 pandas / numpy，避免序列化类型问题。
  - 数据不足时优雅降级（返回 None），不抛出异常。
  - 调用者不需要关心字段是否存在，所有键始终存在。
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return None if f != f else f   # NaN guard
    except (TypeError, ValueError):
        return None


def _round2(v: float | None) -> float | None:
    return round(v, 2) if v is not None else None


def _pct_change(new: float | None, old: float | None) -> float | None:
    """涨跌幅 (%)，old=0 时返回 None。"""
    if new is None or old is None or old == 0:
        return None
    return _round2((new - old) / old * 100)


def _mean(values: list[float]) -> float | None:
    return _round2(sum(values) / len(values)) if values else None


def _moving_average(closes: list[float], window: int) -> float | None:
    """返回最近 window 根收盘价的均值；数据不足时返回 None。"""
    if len(closes) < window:
        return None
    return _mean(closes[-window:])


# ── 主服务 ────────────────────────────────────────────────────────────────────

class TechnicalIndicatorService:
    """
    从 K线列表计算技术指标，返回 JSON 可序列化 dict。

    Usage:
        svc = TechnicalIndicatorService()
        result = svc.calculate(kline_bars)
    """

    def calculate(self, kline: list[dict]) -> dict:
        """
        计算全部技术指标。

        Args:
            kline: list of bar dicts，按日期升序排列（最老在前，最新在后）。
                   每条 bar 至少含 close；volume、high、low 若缺失则相关指标返回 None。

        Returns:
            JSON 可序列化 dict，字段说明见下方。
        """
        if not kline:
            return self._empty_result()

        # ── 提取基础序列 ──────────────────────────────────────────────────────
        closes  = [c for b in kline if (c := _safe_float(b.get("close"))) is not None]
        highs   = [h for b in kline if (h := _safe_float(b.get("high")))  is not None]
        lows    = [l for b in kline if (l := _safe_float(b.get("low")))   is not None]
        volumes = [v for b in kline if (v := _safe_float(b.get("volume"))) is not None]

        n = len(closes)
        if n == 0:
            return self._empty_result()

        latest_close  = closes[-1]
        latest_volume = volumes[-1] if volumes else None

        # ── 均线 ──────────────────────────────────────────────────────────────
        ma5  = _moving_average(closes, 5)
        ma10 = _moving_average(closes, 10)
        ma20 = _moving_average(closes, 20)
        ma60 = _moving_average(closes, 60)

        # ── 涨跌幅 ───────────────────────────────────────────────────────────
        ret_1d  = _pct_change(closes[-1], closes[-2])  if n >= 2  else None
        ret_5d  = _pct_change(closes[-1], closes[-6])  if n >= 6  else None
        ret_20d = _pct_change(closes[-1], closes[-21]) if n >= 21 else None

        # ── 区间极值（支撑/压力参考） ─────────────────────────────────────────
        high_20d = _round2(max(highs[-20:])) if len(highs) >= 20 else (
            _round2(max(highs)) if highs else None
        )
        low_20d  = _round2(min(lows[-20:]))  if len(lows)  >= 20 else (
            _round2(min(lows)) if lows else None
        )
        high_60d = _round2(max(highs[-60:])) if len(highs) >= 60 else (
            _round2(max(highs)) if highs else None
        )
        low_60d  = _round2(min(lows[-60:]))  if len(lows)  >= 60 else (
            _round2(min(lows)) if lows else None
        )

        # ── 成交量分析 ────────────────────────────────────────────────────────
        vol_avg5  = _mean(volumes[-5:])  if len(volumes) >= 5  else None
        vol_avg20 = _mean(volumes[-20:]) if len(volumes) >= 20 else None

        # 量比：最近5日均量 / 最近20日均量
        vol_ratio_5_20 = _round2(vol_avg5 / vol_avg20) if (
            vol_avg5 is not None and vol_avg20 and vol_avg20 > 0
        ) else None

        # 今日量 vs 5日均量
        vol_ratio_today = _round2(latest_volume / vol_avg5) if (
            latest_volume is not None and vol_avg5 and vol_avg5 > 0
        ) else None

        # ── 价格相对于均线的位置 (%) ──────────────────────────────────────────
        price_vs_ma20 = _pct_change(latest_close, ma20) if ma20 else None
        price_vs_ma60 = _pct_change(latest_close, ma60) if ma60 else None

        # ── 趋势判断 ──────────────────────────────────────────────────────────
        short_term_trend  = self._price_trend(ma5,  ma10, "短期")
        medium_term_trend = self._price_trend(ma10, ma20, "中期")
        volume_signal     = self._volume_signal(vol_ratio_5_20, vol_ratio_today)

        return {
            # 基本信息
            "bar_count":      n,
            "latest_date":    str(kline[-1].get("date", "")),
            "latest_close":   _round2(latest_close),

            # 均线（当前值）
            "ma5":  ma5,
            "ma10": ma10,
            "ma20": ma20,
            "ma60": ma60,

            # 价格相对均线位置
            "price_vs_ma20_pct": price_vs_ma20,   # 正 = 价格在 MA20 之上
            "price_vs_ma60_pct": price_vs_ma60,

            # 涨跌幅
            "return_1d_pct":  ret_1d,
            "return_5d_pct":  ret_5d,
            "return_20d_pct": ret_20d,

            # 区间极值
            "high_20d": high_20d,
            "low_20d":  low_20d,
            "high_60d": high_60d,
            "low_60d":  low_60d,

            # 成交量
            "volume_latest":      _round2(latest_volume),
            "volume_avg_5d":      vol_avg5,
            "volume_avg_20d":     vol_avg20,
            "volume_ratio_5_20":  vol_ratio_5_20,    # >1 近期放量，<1 近期缩量
            "volume_ratio_today": vol_ratio_today,   # 今日量 vs 5日均

            # 综合判断（中文描述，供 LLM 直接引用）
            "short_term_trend":  short_term_trend,
            "medium_term_trend": medium_term_trend,
            "volume_signal":     volume_signal,
        }

    # ── 内部判断逻辑 ──────────────────────────────────────────────────────────

    @staticmethod
    def _price_trend(fast_ma: float | None, slow_ma: float | None, label: str) -> str:
        """
        比较快慢均线，返回趋势描述字符串。
        fast > slow → 上升；fast < slow → 下降；相差 < 0.3% → 横盘。
        """
        if fast_ma is None or slow_ma is None or slow_ma == 0:
            return "数据不足"
        diff_pct = (fast_ma - slow_ma) / slow_ma * 100
        if diff_pct > 0.3:
            return "上升"
        if diff_pct < -0.3:
            return "下降"
        return "横盘"

    @staticmethod
    def _volume_signal(ratio_5_20: float | None, ratio_today: float | None) -> str:
        """
        量能信号：
        - ratio_5_20 > 1.2 → 近期放量
        - ratio_5_20 < 0.8 → 近期缩量
        - 否则            → 量能平稳
        今日量比叠加：ratio_today > 1.5 → 单日明显放量
        """
        if ratio_5_20 is None:
            return "数据不足"
        if ratio_today is not None and ratio_today > 1.5:
            return "单日明显放量"
        if ratio_5_20 > 1.2:
            return "近期放量"
        if ratio_5_20 < 0.8:
            return "近期缩量"
        return "量能平稳"

    @staticmethod
    def _empty_result() -> dict:
        keys = [
            "bar_count", "latest_date", "latest_close",
            "ma5", "ma10", "ma20", "ma60",
            "price_vs_ma20_pct", "price_vs_ma60_pct",
            "return_1d_pct", "return_5d_pct", "return_20d_pct",
            "high_20d", "low_20d", "high_60d", "low_60d",
            "volume_latest", "volume_avg_5d", "volume_avg_20d",
            "volume_ratio_5_20", "volume_ratio_today",
            "short_term_trend", "medium_term_trend", "volume_signal",
        ]
        result: dict = {k: None for k in keys}
        result["bar_count"] = 0
        result["short_term_trend"]  = "数据不足"
        result["medium_term_trend"] = "数据不足"
        result["volume_signal"]     = "数据不足"
        return result


# ── 模块级单例 ────────────────────────────────────────────────────────────────
technical_indicator_service = TechnicalIndicatorService()
