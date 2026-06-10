"""
AkShare stock data provider.

Priority (as designed in project docs):
- A股: AkShare primary → Tushare / BaoStock fallback (future)
- 港股: AkShare primary → yfinance → Finnhub fallback (future)

Proxy note:
  AkShare uses `requests` which on macOS reads the system proxy via the
  `_scproxy` C-extension (System Configuration framework).  This happens even
  when no HTTP_PROXY env vars are set, so clearing env vars alone is not
  enough.  We monkeypatch `urllib.request.getproxies` to return an empty dict
  for the duration of every AkShare call, forcing direct connections to
  eastmoney.com / sina.com without going through any local proxy (Clash, etc.).
  DeepSeek uses the `openai` SDK which has its own proxy handling and is
  completely unaffected by this patch.
"""

from __future__ import annotations

import contextlib
import math
import os
import urllib.request
from datetime import datetime, timedelta

import pandas as pd

from app.data.providers.base import BaseStockDataProvider, SUPPORTED_MARKETS


# ── Proxy bypass ──────────────────────────────────────────────────────────────

_PROXY_ENV_VARS = [
    "http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
    "ALL_PROXY", "all_proxy", "SOCKS_PROXY", "socks_proxy",
]


@contextlib.contextmanager
def _direct_connect():
    """
    Force direct TCP connections for all code inside this block.

    Two-layer approach:
    1. Monkeypatch urllib.request.getproxies → {} so requests/urllib3 sees no
       proxy at all, even if macOS System Configuration reports one.
    2. Also clear proxy env vars (belt-and-suspenders) and set NO_PROXY=* as
       a fallback for any code that reads env vars directly.

    The patch is purely in-process and is fully restored in the finally block.
    Since AkShare calls are synchronous and run in the asyncio event-loop
    thread (not a thread pool), the patch window is effectively single-threaded.
    """
    # -- Layer 1: monkeypatch urllib.request.getproxies ----------------------
    _original_getproxies = urllib.request.getproxies
    urllib.request.getproxies = lambda: {}

    # -- Layer 2: env-var cleanup -------------------------------------------
    _saved_env: dict[str, str] = {}
    for var in _PROXY_ENV_VARS:
        val = os.environ.pop(var, None)
        if val is not None:
            _saved_env[var] = val

    _old_no_proxy = os.environ.get("NO_PROXY")
    _old_no_proxy_lc = os.environ.get("no_proxy")
    os.environ["NO_PROXY"] = "*"
    os.environ["no_proxy"] = "*"

    try:
        yield
    finally:
        # Restore urllib patch
        urllib.request.getproxies = _original_getproxies
        # Restore env vars
        for var, val in _saved_env.items():
            os.environ[var] = val
        if _old_no_proxy is None:
            os.environ.pop("NO_PROXY", None)
        else:
            os.environ["NO_PROXY"] = _old_no_proxy
        if _old_no_proxy_lc is None:
            os.environ.pop("no_proxy", None)
        else:
            os.environ["no_proxy"] = _old_no_proxy_lc


# ── Symbol helpers ────────────────────────────────────────────────────────────

def _normalize_hk_symbol(symbol: str) -> str:
    """Pad HK code to 5 digits: '700' → '00700', '9988' → '09988'."""
    return symbol.zfill(5)


def _hk_symbol_to_yfinance(symbol: str) -> str:
    """Convert HK 5-digit code to Yahoo Finance ticker: '00700' → '0700.HK'."""
    return symbol.lstrip("0").zfill(4) + ".HK"


# ── DataFrame → JSON helpers ──────────────────────────────────────────────────

def _safe_value(v):
    """Convert a single cell to a JSON-serialisable Python scalar."""
    import datetime as dt

    if v is None:
        return None
    # pandas / numpy NA
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    # pandas Timestamp / datetime / date
    if isinstance(v, (pd.Timestamp, datetime, dt.date)):
        return v.strftime("%Y-%m-%d")
    # numpy scalar → Python native
    if hasattr(v, "item"):
        return v.item()
    # plain float NaN / inf guard
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


def _df_to_records(df: pd.DataFrame) -> list[dict]:
    """Convert a DataFrame to a list of plain dicts with safe scalar types."""
    return [
        {col: _safe_value(val) for col, val in row.items()}
        for row in df.to_dict(orient="records")
    ]


# ── Column name normalisation ─────────────────────────────────────────────────

_KLINE_CN_COLS = {
    "日期": "date", "开盘": "open", "收盘": "close",
    "最高": "high", "最低": "low", "成交量": "volume",
    "成交额": "amount", "振幅": "amplitude",
    "涨跌幅": "change_pct", "涨跌额": "change", "换手率": "turnover",
}

_KLINE_HK_COLS = {
    "日期": "date", "开盘": "open", "收盘": "close",
    "最高": "high", "最低": "low", "成交量": "volume",
    "成交额": "amount", "振幅": "amplitude",
    "涨跌幅": "change_pct", "涨跌额": "change", "换手率": "turnover",
}

_QUOTE_CN_COLS = {
    "代码": "symbol", "名称": "name", "最新价": "price",
    "涨跌幅": "change_pct", "涨跌额": "change",
    "成交量": "volume", "成交额": "amount",
    "今开": "open", "最高": "high", "最低": "low",
    "昨收": "prev_close", "换手率": "turnover",
    "市盈率-动态": "pe", "市净率": "pb",
    "总市值": "market_cap",   # 元 CNY；AkShare spot 成功时一并返回
}

_QUOTE_HK_COLS = {
    "代码": "symbol", "名称": "name", "最新价": "price",
    "涨跌幅": "change_pct", "涨跌额": "change",
    "成交量": "volume", "成交额": "amount",
    "今开": "open", "最高": "high", "最低": "low",
    "昨收": "prev_close",
}


def _rename_and_filter(df: pd.DataFrame, col_map: dict) -> pd.DataFrame:
    existing = {k: v for k, v in col_map.items() if k in df.columns}
    return df[list(existing.keys())].rename(columns=existing)


# ── Provider implementation ───────────────────────────────────────────────────

class AkShareStockDataProvider(BaseStockDataProvider):
    """AkShare-backed provider for A-share (CN) and Hong Kong (HK) markets."""

    # ── Quote ─────────────────────────────────────────────────────────────────

    def get_quote(self, market: str, symbol: str) -> dict:
        market = market.upper()
        if market not in SUPPORTED_MARKETS:
            raise ValueError(f"Unsupported market '{market}'. Use CN or HK.")
        if not symbol:
            raise ValueError("symbol must not be empty.")
        return self._quote_cn(symbol) if market == "CN" else self._quote_hk(symbol)

    def _quote_cn(self, symbol: str) -> dict:
        import akshare as ak
        try:
            with _direct_connect():
                df = ak.stock_zh_a_spot_em()
        except Exception as exc:
            raise RuntimeError(
                f"AkShare A股实时行情获取失败: {exc}\n"
                "提示：如本地运行了代理工具（Clash 等），请确认东方财富域名已加入直连规则，或暂时关闭代理。"
            ) from exc

        row = df[df["代码"] == symbol]
        if row.empty:
            raise ValueError(f"A股代码 '{symbol}' 未找到，请确认代码正确。")

        row = _rename_and_filter(row.iloc[[0]], _QUOTE_CN_COLS)
        return _df_to_records(row)[0]

    def _quote_hk(self, symbol: str) -> dict:
        import akshare as ak
        symbol = _normalize_hk_symbol(symbol)
        try:
            with _direct_connect():
                df = ak.stock_hk_spot_em()
        except Exception as exc:
            raise RuntimeError(
                f"AkShare 港股实时行情获取失败: {exc}\n"
                "提示：如本地运行了代理工具（Clash 等），请确认东方财富域名已加入直连规则，或暂时关闭代理。"
            ) from exc

        row = df[df["代码"] == symbol]
        if row.empty:
            raise ValueError(f"港股代码 '{symbol}' 未找到，请确认代码正确。")

        row = _rename_and_filter(row.iloc[[0]], _QUOTE_HK_COLS)
        return _df_to_records(row)[0]

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

        end_date = datetime.today()
        calendar_days = max(int(limit * 1.8), 180)
        start_date = end_date - timedelta(days=calendar_days)
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")

        if market == "CN":
            return self._kline_cn(symbol, period, adjust, start_str, end_str, limit)
        return self._kline_hk(symbol, period, adjust, start_str, end_str, limit)

    def _kline_cn(self, symbol, period, adjust, start_str, end_str, limit):
        import akshare as ak
        try:
            with _direct_connect():
                df = ak.stock_zh_a_hist(
                    symbol=symbol, period=period,
                    start_date=start_str, end_date=end_str,
                    adjust=adjust,
                )
        except Exception as exc:
            raise RuntimeError(
                f"AkShare A股K线获取失败 [{symbol}]: {exc}\n"
                "提示：如本地运行了代理工具（Clash 等），请确认东方财富域名已加入直连规则，或暂时关闭代理。"
            ) from exc

        if df is None or df.empty:
            raise ValueError(f"A股 '{symbol}' 未返回K线数据，请确认代码正确。")

        df = _rename_and_filter(df, _KLINE_CN_COLS)
        df = df.sort_values("date", ascending=False).head(limit).sort_values("date")
        return _df_to_records(df)

    def _kline_hk(self, symbol, period, adjust, start_str, end_str, limit):
        import akshare as ak
        symbol = _normalize_hk_symbol(symbol)
        try:
            with _direct_connect():
                df = ak.stock_hk_hist(
                    symbol=symbol, period=period,
                    start_date=start_str, end_date=end_str,
                    adjust=adjust,
                )
        except Exception as exc:
            raise RuntimeError(
                f"AkShare 港股K线获取失败 [{symbol}]: {exc}\n"
                "提示：如本地运行了代理工具（Clash 等），请确认东方财富域名已加入直连规则，或暂时关闭代理。"
            ) from exc

        if df is None or df.empty:
            raise ValueError(f"港股 '{symbol}' 未返回K线数据，请确认代码正确。")

        df = _rename_and_filter(df, _KLINE_HK_COLS)
        df = df.sort_values("date", ascending=False).head(limit).sort_values("date")
        return _df_to_records(df)
