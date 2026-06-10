"""
yfinance stock data provider — secondary fallback for CN and HK markets.

Used when AkShare (eastmoney.com) is unreachable due to proxy/TUN mode.
Yahoo Finance is accessible through most proxy setups.

Symbol conversion:
  CN: 600519  → 600519.SS  (Shanghai: starts with 6)
      000001  → 000001.SZ  (Shenzhen: starts with 0/3)
      300xxx  → 300xxx.SZ
  HK: 00700   → 0700.HK
      700     → 0700.HK

Rate-limit protection:
  - Minimum 1 second between any two requests (same provider instance).
  - On 429 / "Too Many Requests": sleep 5 seconds then retry once.
  - If retry also fails, raise RuntimeError so the service can try the
    next fallback source.  No infinite retries.
"""

from __future__ import annotations

import logging
import math
import time
from datetime import datetime

import pandas as pd

from app.data.providers.base import BaseStockDataProvider, SUPPORTED_MARKETS

log = logging.getLogger(__name__)


# ── Symbol conversion ─────────────────────────────────────────────────────────

def _cn_to_yf(symbol: str) -> str:
    """
    Map A-share 6-digit code to Yahoo Finance ticker.
    Shanghai (SSE): 6xxxxx → 6xxxxx.SS
    Shenzhen (SZSE): 0/3xxxxx → 0/3xxxxx.SZ
    """
    if symbol.startswith("6"):
        return f"{symbol}.SS"
    return f"{symbol}.SZ"


def _hk_to_yf(symbol: str) -> str:
    """
    Map HK code (any digit length) to Yahoo Finance ticker.
    700     → 0700.HK
    00700   → 0700.HK
    00005   → 0005.HK
    """
    num = int(symbol)
    return f"{num:04d}.HK"


# ── Period mapping ────────────────────────────────────────────────────────────

_PERIOD_MAP = {
    "daily":   "1d",
    "weekly":  "1wk",
    "monthly": "1mo",
}


# ── Safe scalar conversion ────────────────────────────────────────────────────

def _safe(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    import datetime as dt
    if isinstance(v, (pd.Timestamp, datetime, dt.date)):
        if hasattr(v, "tz_localize"):
            v = v.tz_localize(None) if v.tzinfo is None else v.tz_convert(None)
        return v.strftime("%Y-%m-%d")
    if hasattr(v, "item"):
        return v.item()
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


# ── Provider ──────────────────────────────────────────────────────────────────

class YFinanceStockDataProvider(BaseStockDataProvider):
    """
    yfinance-backed provider for CN and HK markets (Yahoo Finance).

    Rate-limit protection:
      - ≥1 second between requests
      - 429 → sleep 5s → retry once

    CN quote circuit breaker:
      - 当 CN A股 quote 遭遇 429，冻结 CN quote 10 分钟。
      - 冻结期间 get_quote(CN) 立即抛出 RuntimeError，不发请求，不拖慢链路。
      - CN kline 不受影响（走 kline fallback 即可）。
    """

    # ── 类级熔断状态（所有实例共享，避免冻结期内重复请求）─────────────────────
    _cn_quote_frozen_until: float = 0.0
    _cn_freeze_minutes: int = 10

    def __init__(self) -> None:
        self._last_request_time: float = 0.0
        self._min_interval: float = 1.0   # seconds between requests

    # ── CN quote 熔断器 ───────────────────────────────────────────────────────

    @classmethod
    def _cn_is_frozen(cls) -> bool:
        return time.monotonic() < cls._cn_quote_frozen_until

    @classmethod
    def _cn_freeze(cls) -> None:
        cls._cn_quote_frozen_until = time.monotonic() + cls._cn_freeze_minutes * 60
        log.warning(
            "yfinance CN quote 熔断器已开启，冻结 %d 分钟（直到解除前不再请求 CN quote）。",
            cls._cn_freeze_minutes,
        )

    # ── Rate-limit helpers ────────────────────────────────────────────────────

    def _throttle(self) -> None:
        """Block until at least _min_interval seconds have elapsed since last call."""
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_time = time.monotonic()

    @staticmethod
    def _is_rate_limited(exc: Exception) -> bool:
        msg = str(exc).lower()
        return any(kw in msg for kw in ("too many requests", "429", "rate limit", "ratelimit"))

    def _call_with_retry(self, fn, *args, **kwargs):
        """
        Execute fn(*args, **kwargs) with:
          1. Pre-call throttle (≥1 s gap).
          2. On 429: sleep 5 s, throttle again, retry exactly once.
          3. All other exceptions propagate immediately.
        """
        self._throttle()
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            if self._is_rate_limited(exc):
                log.warning(
                    "yfinance rate-limited (%s). Sleeping 5 s then retrying once.", exc
                )
                time.sleep(5)
                self._throttle()
                try:
                    return fn(*args, **kwargs)
                except Exception as retry_exc:
                    raise RuntimeError(
                        f"yfinance 限流后重试仍失败: {retry_exc}"
                    ) from retry_exc
            raise

    # ── Quote ─────────────────────────────────────────────────────────────────

    def get_quote(self, market: str, symbol: str) -> dict:
        market = market.upper()
        if market not in SUPPORTED_MARKETS:
            raise ValueError(f"Unsupported market '{market}'. Use CN or HK.")
        if not symbol:
            raise ValueError("symbol must not be empty.")

        # CN A股 quote：熔断期内直接跳过，不发任何请求
        if market == "CN":
            if self._cn_is_frozen():
                frozen_secs = int(self._cn_quote_frozen_until - time.monotonic())
                raise RuntimeError(
                    f"yfinance CN quote 熔断器激活中，还需等待约 {frozen_secs} 秒。"
                )

        import yfinance as yf

        ticker_str = _cn_to_yf(symbol) if market == "CN" else _hk_to_yf(symbol)

        def _fetch():
            t = yf.Ticker(ticker_str)
            return t.fast_info

        try:
            fi = self._call_with_retry(_fetch)
            price = fi.last_price
        except RuntimeError as exc:
            # 如果是 429，对 CN quote 触发熔断
            if market == "CN" and self._is_rate_limited(exc):
                self._cn_freeze()
            raise
        except Exception as exc:
            if market == "CN" and self._is_rate_limited(exc):
                self._cn_freeze()
            raise RuntimeError(
                f"yfinance quote 获取失败 [{ticker_str}]: {exc}"
            ) from exc

        if price is None:
            raise ValueError(
                f"yfinance 未找到 '{ticker_str}'，请确认股票代码正确。"
            )

        return {
            "symbol":     symbol,
            "yf_ticker":  ticker_str,
            "price":      _safe(price),
            "open":       _safe(getattr(fi, "open", None)),
            "high":       _safe(getattr(fi, "day_high", None)),
            "low":        _safe(getattr(fi, "day_low", None)),
            "prev_close": _safe(getattr(fi, "previous_close", None)),
            "volume":     _safe(getattr(fi, "last_volume", None)),
            "market_cap": _safe(getattr(fi, "market_cap", None)),
        }

    # ── Kline ─────────────────────────────────────────────────────────────────

    def get_kline(
        self,
        market: str,
        symbol: str,
        period: str = "daily",
        adjust: str = "",
        limit: int = 120,
    ) -> list[dict]:
        market = market.upper()
        if market not in SUPPORTED_MARKETS:
            raise ValueError(f"Unsupported market '{market}'. Use CN or HK.")
        if not symbol:
            raise ValueError("symbol must not be empty.")

        import yfinance as yf

        ticker_str = _cn_to_yf(symbol) if market == "CN" else _hk_to_yf(symbol)
        interval = _PERIOD_MAP.get(period, "1d")

        # Fetch enough history to guarantee `limit` trading days
        fetch_period = f"{max(limit * 2, 365)}d"

        # yfinance: auto_adjust=True means forward-adjusted
        auto_adjust = adjust in ("qfq", "hfq", "")

        def _fetch():
            return yf.Ticker(ticker_str).history(
                period=fetch_period,
                interval=interval,
                auto_adjust=auto_adjust,
            )

        try:
            df = self._call_with_retry(_fetch)
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"yfinance kline 获取失败 [{ticker_str}]: {exc}"
            ) from exc

        if df is None or df.empty:
            raise ValueError(
                f"yfinance 未返回 '{ticker_str}' 的K线数据，请确认代码正确。"
            )

        # Normalise index (timezone-aware DatetimeIndex → plain date string)
        df = df.reset_index()
        date_col = "Date" if "Date" in df.columns else df.columns[0]
        df[date_col] = df[date_col].apply(
            lambda v: v.tz_convert(None).strftime("%Y-%m-%d")
            if hasattr(v, "tz_convert") and v.tzinfo is not None
            else (v.strftime("%Y-%m-%d") if hasattr(v, "strftime") else str(v))
        )

        df = df.rename(columns={
            date_col: "date",
            "Open":   "open",
            "High":   "high",
            "Low":    "low",
            "Close":  "close",
            "Volume": "volume",
        })

        keep = ["date", "open", "high", "low", "close", "volume"]
        df = df[[c for c in keep if c in df.columns]]
        df = df.sort_values("date", ascending=False).head(limit).sort_values("date")

        return [
            {col: _safe(val) for col, val in row.items()}
            for row in df.to_dict(orient="records")
        ]
