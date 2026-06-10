"""
Eastmoney 直连 provider — CN A股 quote 主数据源 + CN A股 kline 主数据源。

Quote 接口：push2.eastmoney.com/api/qt/stock/get
Kline 接口：push2his.eastmoney.com/api/qt/stock/kline/get

关键：session.trust_env = False
  requests.Session 的 trust_env 默认 True，会读取系统环境变量代理。
  proxies={} 只是"不传额外代理"，但 trust_env=True 时仍会被 urllib 接管读取系统代理。
  只有 trust_env=False 才能真正跳过环境代理，直连目标主机。

secid 规则（A股）：
  上交所 (600xxx / 601xxx / 603xxx / 605xxx / 688xxx) → 1.symbol
  深交所 (000xxx / 001xxx / 002xxx / 003xxx / 300xxx / 301xxx) → 0.symbol

Kline 字段解析（fields2=f51..f61）：
  [0] date   [1] open   [2] close  [3] high   [4] low
  [5] volume [6] amount [7] 振幅   [8] 涨跌幅 [9] 涨跌额 [10] 换手率
  值已是小数格式，不需要除以 100（与 quote f4x 字段不同）。
"""

from __future__ import annotations

import logging

import requests

from app.data.providers.base import BaseStockDataProvider

log = logging.getLogger(__name__)

# ── URL 常量 ──────────────────────────────────────────────────────────────────

_QUOTE_URL  = "https://push2.eastmoney.com/api/qt/stock/get"
_KLINE_URL  = "https://push2his.eastmoney.com/api/qt/stock/kline/get"

_QUOTE_FIELDS = "f43,f44,f45,f46,f47,f48,f57,f58,f60,f170"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Referer":    "https://quote.eastmoney.com/",
}

# ── secid 映射 ────────────────────────────────────────────────────────────────

def _to_secid(symbol: str) -> str:
    """
    A股 secid：上交所（以 6 开头）→ 1.xxx，深交所/创业板 → 0.xxx。
    示例：600519→1.600519  000001→0.000001  300750→0.300750
    """
    return f"1.{symbol}" if symbol.startswith("6") else f"0.{symbol}"


# ── Kline period / adjust 映射 ─────────────────────────────────────────────────

_KLT_MAP = {"daily": 101, "weekly": 102, "monthly": 103}
_FQT_MAP = {"qfq": 1, "hfq": 2, "": 0}


# ── 数值解析 ──────────────────────────────────────────────────────────────────

def _div100(v) -> float | None:
    """Quote 接口价格字段放大了 100 倍，需除以 100。"""
    if v is None:
        return None
    try:
        f = float(v)
        if f <= 0 or f == -9999999 or f < -999999:
            return None
        return round(f / 100, 3)
    except (TypeError, ValueError):
        return None


def _safe_float(v) -> float | None:
    """Kline 字段已是小数格式，直接转换。"""
    if v is None or str(v).strip() in ("", "-", "--"):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _make_session() -> requests.Session:
    """
    创建禁用环境代理的 Session。
    trust_env=False 确保不读取系统/环境变量代理（macOS scproxy 等）。
    """
    s = requests.Session()
    s.trust_env = False
    s.headers.update(_HEADERS)
    return s


# ── EastmoneyDirectProvider（Quote）─────────────────────────────────────────

class EastmoneyDirectProvider(BaseStockDataProvider):
    """直连东方财富实时行情接口，仅支持 CN A股 quote。"""

    def get_quote(self, market: str, symbol: str) -> dict:
        if market.upper() != "CN":
            raise ValueError(
                f"EastmoneyDirectProvider 仅支持 CN 市场，收到 '{market}'。"
            )
        if not symbol:
            raise ValueError("symbol 不能为空。")

        secid = _to_secid(symbol)
        session = _make_session()

        try:
            resp = session.get(
                _QUOTE_URL,
                params={"secid": secid, "fields": _QUOTE_FIELDS},
                timeout=8,
            )
            resp.raise_for_status()
            body = resp.json()
        except Exception as exc:
            raise RuntimeError(
                f"EastmoneyDirect quote 请求失败 [{symbol}]: {exc}"
            ) from exc

        rc   = body.get("rc")
        data = body.get("data")
        if rc != 0 or not data:
            raise RuntimeError(
                f"EastmoneyDirect quote 返回异常 [{symbol}]: rc={rc}, data={data}"
            )

        price      = _div100(data.get("f43"))
        prev_close = _div100(data.get("f60"))

        if price is None:
            raise ValueError(
                f"EastmoneyDirect 未能解析价格 [{symbol}]，股票可能已停牌或代码有误。"
            )

        change: float | None = None
        if price is not None and prev_close is not None:
            change = round(price - prev_close, 3)

        return {
            "symbol":     str(data.get("f57", symbol)),
            "name":       data.get("f58"),
            "price":      price,
            "high":       _div100(data.get("f44")),
            "low":        _div100(data.get("f45")),
            "open":       _div100(data.get("f46")),
            "prev_close": prev_close,
            "volume":     data.get("f47"),
            "amount":     data.get("f48"),
            "change_pct": _div100(data.get("f170")),
            "change":     change,
        }

    def get_kline(self, *args, **kwargs) -> list[dict]:
        raise NotImplementedError(
            "请使用 EastmoneyKlineProvider.get_kline()。"
        )


# ── EastmoneyKlineProvider（Kline）──────────────────────────────────────────

class EastmoneyKlineProvider(BaseStockDataProvider):
    """
    直连东方财富历史 K 线接口，支持 CN A股。
    HK kline 暂未实现（P2 阶段添加）。
    """

    def get_quote(self, *args, **kwargs) -> dict:
        raise NotImplementedError(
            "请使用 EastmoneyDirectProvider.get_quote()。"
        )

    def get_kline(
        self,
        market: str,
        symbol: str,
        period: str = "daily",
        adjust: str = "",
        limit: int = 120,
    ) -> list[dict]:
        if market.upper() != "CN":
            raise NotImplementedError(
                f"EastmoneyKlineProvider 暂不支持 '{market}' 市场 K线，HK kline 为 P2 阶段。"
            )
        if not symbol:
            raise ValueError("symbol 不能为空。")

        secid = _to_secid(symbol)
        klt   = _KLT_MAP.get(period, 101)
        fqt   = _FQT_MAP.get(adjust, 0)

        params = {
            "secid":   secid,
            "klt":     klt,
            "fqt":     fqt,
            "lmt":     limit,
            "end":     "20500101",    # 请求到未来日期，让接口返回最新数据
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        }

        session = _make_session()
        try:
            resp = session.get(_KLINE_URL, params=params, timeout=12)
            resp.raise_for_status()
            body = resp.json()
        except Exception as exc:
            raise RuntimeError(
                f"EastmoneyKline 请求失败 [{symbol}]: {exc}"
            ) from exc

        rc   = body.get("rc")
        data = body.get("data")
        if rc != 0 or not data:
            raise RuntimeError(
                f"EastmoneyKline 返回异常 [{symbol}]: rc={rc}, data={data}"
            )

        klines = data.get("klines")
        if not klines:
            raise ValueError(
                f"EastmoneyKline 未返回K线数据 [{symbol}]，请确认代码正确。"
            )

        bars: list[dict] = []
        for raw in klines:
            parts = raw.split(",")
            if len(parts) < 6:
                continue
            bar = {
                "date":       parts[0].strip(),
                "open":       _safe_float(parts[1]),
                "close":      _safe_float(parts[2]),
                "high":       _safe_float(parts[3]),
                "low":        _safe_float(parts[4]),
                "volume":     _safe_float(parts[5]),
                "amount":     _safe_float(parts[6]) if len(parts) > 6 else None,
                "change_pct": _safe_float(parts[8]) if len(parts) > 8 else None,
                "change":     _safe_float(parts[9]) if len(parts) > 9 else None,
            }
            bars.append(bar)

        if not bars:
            raise ValueError(
                f"EastmoneyKline 解析后无有效数据 [{symbol}]。"
            )

        return bars
