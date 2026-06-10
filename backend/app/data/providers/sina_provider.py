"""
SinaQuoteProvider — 新浪财经实时行情（CN A股 quote 第二备用）。

接口：https://hq.sinajs.cn/list=<sina_symbol>
编码：GB18030（响应为 GBK/GB18030，必须正确解码，否则中文乱码）

symbol 转换：
  上交所（6xxxxx）→ sh + symbol
  深交所（0/3xxxxx）→ sz + symbol

响应格式：
  var hq_str_sh600519="贵州茅台,1324.30,1323.00,1324.30,1325.00,1318.00,...,2024-01-01,15:00:00,...";

字段（逗号分隔，0-indexed）：
  [0]  股票名称
  [1]  今日开盘价
  [2]  昨日收盘价
  [3]  当前价格
  [4]  今日最高价
  [5]  今日最低价
  [8]  成交数量（手，100股/手）
  [9]  成交额（元）
  [30] 日期 YYYY-MM-DD
  [31] 时间 HH:MM:SS
"""

from __future__ import annotations

import logging
import re

import requests

from app.data.providers.base import BaseStockDataProvider

log = logging.getLogger(__name__)

_URL = "https://hq.sinajs.cn/list={}"

_HEADERS = {
    "Referer":    "https://finance.sina.com.cn",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
}


def _to_sina_symbol(symbol: str) -> str:
    return f"sh{symbol}" if symbol.startswith("6") else f"sz{symbol}"


def _safe_float(fields: list[str], idx: int) -> float | None:
    try:
        v = fields[idx].strip()
        return float(v) if v else None
    except (IndexError, ValueError):
        return None


def _safe_str(fields: list[str], idx: int) -> str | None:
    try:
        v = fields[idx].strip()
        return v if v else None
    except IndexError:
        return None


class SinaQuoteProvider(BaseStockDataProvider):
    """新浪财经实时行情，仅支持 CN A股 quote。"""

    def get_quote(self, market: str, symbol: str) -> dict:
        if market.upper() != "CN":
            raise ValueError(
                f"SinaQuoteProvider 仅支持 CN 市场，收到 '{market}'。"
            )
        if not symbol:
            raise ValueError("symbol 不能为空。")

        sina_sym = _to_sina_symbol(symbol)
        url = _URL.format(sina_sym)

        try:
            resp = requests.get(
                url,
                headers=_HEADERS,
                proxies={},       # 强制直连
                timeout=8,
            )
            resp.raise_for_status()
            # 新浪响应编码为 GB18030，必须手动解码
            text = resp.content.decode("gb18030", errors="replace")
        except Exception as exc:
            raise RuntimeError(
                f"Sina 请求失败 [{symbol}]: {exc}"
            ) from exc

        # 提取引号内数据：var hq_str_sh600519="...";
        match = re.search(r'"([^"]*)"', text)
        if not match:
            raise RuntimeError(
                f"Sina 响应格式异常 [{symbol}]: {text[:120]!r}"
            )

        raw = match.group(1).strip()
        if not raw:
            raise ValueError(
                f"Sina 返回空数据 [{symbol}]，股票可能已停牌或代码有误。"
            )

        fields = raw.split(",")
        if len(fields) < 10:
            raise RuntimeError(
                f"Sina 响应字段不足 [{symbol}]: 共 {len(fields)} 个字段，原文: {raw[:80]!r}"
            )

        price = _safe_float(fields, 3)
        if price is None or price == 0:
            raise ValueError(
                f"Sina 未能解析价格 [{symbol}]，可能停牌。"
            )

        prev_close = _safe_float(fields, 2)
        change: float | None = None
        change_pct: float | None = None
        if price is not None and prev_close is not None and prev_close != 0:
            change = round(price - prev_close, 3)
            change_pct = round((price - prev_close) / prev_close * 100, 3)

        # 成交量：新浪单位为"手"（100 股），转为股数
        raw_vol = _safe_float(fields, 8)
        volume = int(raw_vol * 100) if raw_vol is not None else None

        trade_date = _safe_str(fields, 30)
        trade_time = _safe_str(fields, 31)
        trade_dt = f"{trade_date} {trade_time}" if trade_date and trade_time else trade_date

        return {
            "symbol":     symbol,
            "name":       _safe_str(fields, 0),
            "price":      price,
            "open":       _safe_float(fields, 1),
            "prev_close": prev_close,
            "high":       _safe_float(fields, 4),
            "low":        _safe_float(fields, 5),
            "volume":     volume,
            "amount":     _safe_float(fields, 9),
            "change":     change,
            "change_pct": change_pct,
            "trade_time": trade_dt,
        }

    def get_kline(
        self,
        market: str,
        symbol: str,
        period: str = "daily",
        adjust: str = "",
        limit: int = 120,
    ) -> list[dict]:
        raise NotImplementedError(
            "SinaQuoteProvider 仅支持 quote，K线请使用 AkShareStockDataProvider。"
        )
