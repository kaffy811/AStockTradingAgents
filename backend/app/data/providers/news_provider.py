"""
EastmoneyNewsProvider — 东方财富个股新闻 provider。

数据源：
  ak.stock_news_em(symbol) — 东方财富个股新闻关键词搜索，固定返回最近 10 条。
  使用 curl_cffi 发起请求，内部绕过系统代理（Clash），无需额外 _direct_connect()。

字段映射：
  新闻标题 → title
  新闻内容 → summary（截断至 500 字符）
  新闻链接 → url
  文章来源 → source
  发布时间 → publish_time（ISO 8601）
  type     → 固定 "news"
  symbols  → [symbol]

Symbol 规范化：
  CN：保留原始 6 位代码（含前导 0），如 "000001"、"600519"。
  HK：不足 5 位补前导 0，如 "700" → "00700"、"9988" → "09988"。

异常：
  provider 调用失败时抛出 RuntimeError，由 NewsDataService 捕获，不在此处静默。
"""

from __future__ import annotations

import logging
from datetime import datetime

log = logging.getLogger(__name__)

_SUMMARY_MAX_CHARS = 500
_PUBLISH_TIME_FMT  = "%Y-%m-%d %H:%M:%S"


def _normalize_symbol(market: str, symbol: str) -> str:
    """
    规范化 symbol 供 AkShare 调用。

    CN：原样返回（不加交易所后缀，不修改前导 0）。
    HK：补全至 5 位前导零（"700" → "00700"，"9988" → "09988"）。
    """
    if market == "HK":
        return symbol.zfill(5)
    return symbol


def _parse_publish_time(raw: str) -> str | None:
    """
    将 AkShare 返回的 "YYYY-MM-DD HH:MM:SS" 转为 ISO 8601 字符串。
    解析失败返回原始字符串（不丢弃该字段）。
    """
    if not raw or not isinstance(raw, str):
        return None
    try:
        dt = datetime.strptime(raw.strip(), _PUBLISH_TIME_FMT)
        return dt.isoformat()
    except ValueError:
        return raw.strip() or None


def _to_item(row: dict, symbol: str) -> dict | None:
    """
    将 AkShare DataFrame 的一行（已转 dict）标准化为统一 NewsItem dict。
    title 缺失时返回 None（调用方跳过）。
    """
    title = (row.get("新闻标题") or "").strip()
    if not title:
        return None

    raw_summary = row.get("新闻内容") or ""
    summary: str | None = raw_summary.strip()[:_SUMMARY_MAX_CHARS] if raw_summary.strip() else None

    url      = (row.get("新闻链接") or "").strip() or None
    source   = (row.get("文章来源") or "").strip() or None
    pub_raw  = row.get("发布时间")
    pub_time = _parse_publish_time(str(pub_raw)) if pub_raw is not None else None

    return {
        "title":        title,
        "summary":      summary,
        "url":          url,
        "source":       source,
        "publish_time": pub_time,
        "type":         "news",
        "symbols":      [symbol],
    }


class EastmoneyNewsProvider:
    """
    东方财富个股新闻 provider。

    调用 ak.stock_news_em(symbol) 拉取最近 10 条新闻，标准化后返回。
    不做时间过滤和 limit 截断（由 NewsDataService 处理）。

    Args:
        limit: 最多返回条数（在 AkShare 返回结果上截断，不能超过 10）。
               默认 20，实际受 AkShare 固定返回 10 条限制。
    """

    def get_stock_news(
        self,
        market:  str,
        symbol:  str,
        limit:   int = 20,
    ) -> list[dict]:
        """
        获取个股新闻列表。

        Args:
            market:  "CN" 或 "HK"
            symbol:  股票代码（调用方已做大写 / strip）
            limit:   最多返回条数（在 AkShare 层无效，由调用方截断）

        Returns:
            标准化 NewsItem list，顺序与 AkShare 一致（最新在前）。

        Raises:
            RuntimeError: AkShare 调用失败（网络、解析、空数据等）。
        """
        import akshare as ak

        query_symbol = _normalize_symbol(market, symbol)
        log.info(
            "EastmoneyNewsProvider: fetching news [%s/%s] query_symbol=%s",
            market, symbol, query_symbol,
        )

        try:
            df = ak.stock_news_em(symbol=query_symbol)
        except Exception as exc:
            raise RuntimeError(
                f"ak.stock_news_em({query_symbol!r}) failed: {exc}"
            ) from exc

        if df is None or df.empty:
            log.warning(
                "EastmoneyNewsProvider: empty result [%s/%s]", market, symbol
            )
            return []

        items: list[dict] = []
        for row in df.to_dict(orient="records"):
            item = _to_item(row, symbol)
            if item is not None:
                items.append(item)

        log.info(
            "EastmoneyNewsProvider: fetched %d items [%s/%s]",
            len(items), market, symbol,
        )
        return items
