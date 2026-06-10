"""
Tencent Provider — 腾讯财经实时行情 + K线。

Quote 接口：https://qt.gtimg.cn/q=<symbol>
Kline 接口：https://web.ifzq.gtimg.cn/appstock/app/fqkline/get

Quote 支持市场：CN A股 / HK 港股
Kline 支持市场：CN A股 / HK 港股

编码：GB18030（quote 接口，K线接口为 UTF-8）

Symbol 转换规则：
  CN:  600519 → sh600519, 000001 → sz000001
  HK:  700 → hk00700, 9988 → hk09988, 5 → hk00005

已验证直连可用（proxies={'http':None,'https':None}）：
  qt.gtimg.cn       — quote (CN/HK)
  web.ifzq.gtimg.cn — kline (CN/HK)

Quote 字段（~ 分隔，0-indexed）：
  [1] 名称  [2] 代码  [3] 当前价  [4] 昨收  [5] 今开
  [6] 成交量(手)  [31] 涨跌额  [32] 涨跌幅  [33] 最高  [34] 最低
  [35] 成交额(万元)  [36] 换手率

Kline 字段（数组，0-indexed）：
  [0] date  [1] open  [2] close  [3] high  [4] low  [5] volume
  HK 部分条目有 [6] dict（除权信息），自动跳过
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import requests

from app.data.providers.base import BaseStockDataProvider, SUPPORTED_MARKETS

log = logging.getLogger(__name__)

_QUOTE_URL = "https://qt.gtimg.cn/q={}"
_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"

_HEADERS_QUOTE = {
    "Referer":    "https://finance.qq.com",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
}

_HEADERS_KLINE = {
    "Referer":    "https://finance.qq.com",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
}

# 强制直连，绕过 HTTP_PROXY / HTTPS_PROXY 环境变量
_DIRECT = {"http": None, "https": None}


# ── Symbol 转换 ───────────────────────────────────────────────────────────────

def _to_cn_symbol(symbol: str) -> str:
    return f"sh{symbol}" if symbol.startswith("6") else f"sz{symbol}"


def _to_hk_symbol(symbol: str) -> str:
    """700 → hk00700, 9988 → hk09988, 5 → hk00005"""
    num_str = symbol.lstrip("0") or "0"
    return f"hk{num_str.zfill(5)}"


def _tencent_symbol(market: str, symbol: str) -> str:
    return _to_cn_symbol(symbol) if market == "CN" else _to_hk_symbol(symbol)


# ── Kline adjust / period 映射 ─────────────────────────────────────────────────

# _var 前缀 = kline_{period}{adjust}
_PERIOD_KEY  = {"daily": "day",  "weekly": "week",  "monthly": "month"}
_ADJUST_SFXS = {"qfq": "qfq", "hfq": "hfq", "": "nfq"}

# 响应 data 中的键名：{period}{adjust}
_DATA_KEY    = {"qfq": "qfq", "hfq": "hfq", "": ""}   # nfq 对应 "day"/"week"/"month"


def _kline_var(period: str, adjust: str) -> str:
    """构造 _var 参数。daily + qfq → kline_dayqfq"""
    pk  = _PERIOD_KEY.get(period, "day")
    sfx = _ADJUST_SFXS.get(adjust, "nfq")
    return f"kline_{pk}{sfx}"


def _kline_data_key(period: str, adjust: str) -> str:
    """响应 JSON 中的数组键名。daily + qfq → qfqday"""
    pk = _PERIOD_KEY.get(period, "day")
    if adjust in ("qfq", "hfq"):
        return f"{adjust}{pk}"
    return pk  # no adjust: "day" / "week" / "month"


# ── 安全解析 ──────────────────────────────────────────────────────────────────

def _sf(fields: list[str], idx: int) -> float | None:
    try:
        v = fields[idx].strip().lstrip("+")
        if v.endswith("%"):
            v = v[:-1]
        return float(v) if v and v not in ("-", "--") else None
    except (IndexError, ValueError):
        return None


def _ss(fields: list[str], idx: int) -> str | None:
    try:
        v = fields[idx].strip()
        return v if v else None
    except IndexError:
        return None


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(str(v).strip())
        return f if not (f != f) else None  # nan guard
    except (ValueError, TypeError):
        return None


# ── 内部：Quote 解析 ──────────────────────────────────────────────────────────

def _parse_cn_amount(fields: list[str]) -> float | None:
    """
    CN quote field[35] 格式：'price/volume_lots/amount_yuan'
    第三段是当日真实成交额，单位：元。
    例：'1324.30/43255/5719170335' → 5719170335.0
    """
    try:
        raw = fields[35].strip()
        parts = raw.split("/")
        if len(parts) >= 3:
            v = parts[2].strip()
            return float(v) if v else None
    except (IndexError, ValueError):
        pass
    return None


def _parse_hk_amount(fields: list[str]) -> float | None:
    """
    HK quote field[37] 是当日真实成交额，单位：港元（直接使用，无需缩放）。
    例：'15552380252.510' → 15552380252.51
    字段布局与 CN 不同：field[35]=price, field[36]=volume, field[37]=amount。
    """
    try:
        raw = fields[37].strip()
        v = float(raw)
        return v if v > 0 else None
    except (IndexError, ValueError):
        return None


def _parse_quote(raw: str, symbol: str, market: str) -> dict:
    fields = raw.split("~")
    if len(fields) < 7:
        raise RuntimeError(
            f"Tencent quote 响应字段不足 [{market}/{symbol}]: {len(fields)} 字段"
        )

    price = _sf(fields, 3)
    if price is None or price == 0:
        raise ValueError(
            f"Tencent quote 无法解析价格 [{market}/{symbol}]，可能停牌或代码有误。"
        )

    prev_close = _sf(fields, 4)

    raw_vol = _sf(fields, 6)
    # CN: field[6] unit is 手(lot), 1手=100股 → multiply by 100 to get shares.
    # HK: field[6] unit is shares directly (HK lot sizes vary per stock).
    volume = int(raw_vol * 100) if (raw_vol is not None and market == "CN") else (
        int(raw_vol) if raw_vol is not None else None
    )

    # Real 成交额:
    #   CN → field[35] composite "price/vol/amount", third segment is 元
    #   HK → field[37] is 成交额 in HKD (港元), no scaling needed
    # field[36] is volume repeat (same as field[6]) — not used.
    amount = _parse_cn_amount(fields) if market == "CN" else _parse_hk_amount(fields)

    return {
        "symbol":     _ss(fields, 2) or symbol,
        "name":       _ss(fields, 1),
        "price":      price,
        "prev_close": prev_close,
        "open":       _sf(fields, 5),
        "high":       _sf(fields, 33),
        "low":        _sf(fields, 34),
        "volume":     volume,
        "amount":     amount,
        "change":     _sf(fields, 31),
        "change_pct": _sf(fields, 32),
    }


# ── TencentQuoteProvider ──────────────────────────────────────────────────────

class TencentQuoteProvider(BaseStockDataProvider):
    """
    腾讯财经实时行情。
    CN A股: qt.gtimg.cn/q=sh600519
    HK 港股: qt.gtimg.cn/q=hk00700
    直连，不走 HTTP_PROXY 环境变量代理。
    """

    def get_quote(self, market: str, symbol: str) -> dict:
        market = market.upper()
        if market not in SUPPORTED_MARKETS:
            raise ValueError(
                f"TencentQuoteProvider 不支持市场 '{market}'。支持 CN / HK。"
            )
        if not symbol:
            raise ValueError("symbol 不能为空。")

        t_sym = _tencent_symbol(market, symbol)
        url   = _QUOTE_URL.format(t_sym)

        try:
            resp = requests.get(
                url,
                headers=_HEADERS_QUOTE,
                proxies=_DIRECT,   # 直连，绕过 HTTPS_PROXY 等环境变量
                timeout=8,
            )
            resp.raise_for_status()
            text = resp.content.decode("gb18030", errors="replace")
        except Exception as exc:
            raise RuntimeError(
                f"Tencent quote 请求失败 [{market}/{symbol}]: {exc}"
            ) from exc

        match = re.search(r'"([^"]*)"', text)
        if not match:
            raise RuntimeError(
                f"Tencent quote 响应格式异常 [{market}/{symbol}]: {text[:120]!r}"
            )

        raw = match.group(1).strip()
        if not raw:
            raise ValueError(
                f"Tencent quote 返回空数据 [{market}/{symbol}]，可能停牌或代码有误。"
            )

        return _parse_quote(raw, symbol, market)

    def get_kline(self, *args, **kwargs) -> list[dict]:
        raise NotImplementedError(
            "请使用 TencentKlineProvider.get_kline()。"
        )


# ── TencentKlineProvider ──────────────────────────────────────────────────────

class TencentKlineProvider(BaseStockDataProvider):
    """
    腾讯财经历史 K 线。
    接口：web.ifzq.gtimg.cn/appstock/app/fqkline/get
    支持 CN A股 + HK 港股，支持 qfq / hfq / 无复权。
    直连，不走 HTTP_PROXY 环境变量代理。

    Kline 数据格式（每条为 list）：
      [0] date  [1] open  [2] close  [3] high  [4] low  [5] volume
      HK 条目可能有 [6] dict（除权信息），自动跳过。
    """

    def get_quote(self, *args, **kwargs) -> dict:
        raise NotImplementedError(
            "请使用 TencentQuoteProvider.get_quote()。"
        )

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
            raise ValueError(
                f"TencentKlineProvider 不支持市场 '{market}'。支持 CN / HK。"
            )
        if not symbol:
            raise ValueError("symbol 不能为空。")

        t_sym    = _tencent_symbol(market, symbol)
        var_name = _kline_var(period, adjust)
        data_key = _kline_data_key(period, adjust)

        # adjust_param: 腾讯接口用 qfq / hfq / nfq
        adjust_param = _ADJUST_SFXS.get(adjust, "nfq")
        period_param = _PERIOD_KEY.get(period, "day")

        params = {
            "_var":  var_name,
            "param": f"{t_sym},{period_param},,,{limit},{adjust_param}",
        }

        try:
            resp = requests.get(
                _KLINE_URL,
                params=params,
                headers=_HEADERS_KLINE,
                proxies=_DIRECT,   # 直连
                timeout=12,
            )
            resp.raise_for_status()
            # kline 接口返回 UTF-8 JSON（带 JS var 前缀）
            text = resp.content.decode("utf-8", errors="replace")
        except Exception as exc:
            raise RuntimeError(
                f"Tencent kline 请求失败 [{market}/{symbol}]: {exc}"
            ) from exc

        # 解析 JS 变量赋值：kline_dayqfq={...}
        eq_idx = text.find("=")
        if eq_idx == -1:
            raise RuntimeError(
                f"Tencent kline 响应格式异常 [{market}/{symbol}]: {text[:100]!r}"
            )
        try:
            payload = json.loads(text[eq_idx + 1:])
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Tencent kline JSON 解析失败 [{market}/{symbol}]: {exc}"
            ) from exc

        if payload.get("code") != 0:
            raise RuntimeError(
                f"Tencent kline 返回异常 [{market}/{symbol}]: code={payload.get('code')}, msg={payload.get('msg')}"
            )

        data = payload.get("data", {})
        sym_data = data.get(t_sym)
        if sym_data is None:
            raise ValueError(
                f"Tencent kline 未找到代码 [{market}/{symbol}]（key={t_sym}），请确认代码正确。"
            )

        raw_klines = sym_data.get(data_key)
        if not raw_klines:
            # 容错：部分调整类型可能使用不同键名
            for k in (data_key, "day", "qfqday", "hfqday"):
                raw_klines = sym_data.get(k)
                if raw_klines:
                    break

        if not raw_klines:
            raise ValueError(
                f"Tencent kline 无数据 [{market}/{symbol}]（key={data_key}）。"
            )

        bars: list[dict] = []
        for entry in raw_klines:
            if not isinstance(entry, list) or len(entry) < 5:
                continue
            high   = _safe_float(entry[3])
            low    = _safe_float(entry[4])
            volume = _safe_float(entry[5]) if len(entry) > 5 else None

            # Estimate 成交额: avg_price × volume_in_shares
            # CN: volume unit = 手(lot), 1 手 = 100 股 → volume_in_shares = volume * 100
            # HK: volume unit = 股(share) → volume_in_shares = volume
            if high is not None and low is not None and volume is not None:
                volume_in_shares = volume * 100 if market == "CN" else volume
                amount_estimated: float | None = round(
                    ((high + low) / 2) * volume_in_shares, 2
                )
                amount_est_method: str | None = "avg_price_high_low_x_volume"
            else:
                amount_estimated = None
                amount_est_method = None

            bar = {
                "date":                    str(entry[0]),
                "open":                    _safe_float(entry[1]),
                "close":                   _safe_float(entry[2]),
                "high":                    high,
                "low":                     low,
                "volume":                  volume,
                "amount":                  None,   # Tencent kline API 不返回真实成交额
                "amount_estimated":        amount_estimated,
                "amount_estimated_method": amount_est_method,
            }
            bars.append(bar)

        if not bars:
            raise ValueError(
                f"Tencent kline 解析后无有效数据 [{market}/{symbol}]。"
            )

        # Tencent API occasionally returns limit+1 bars; trim to exact count.
        return bars[-limit:]
