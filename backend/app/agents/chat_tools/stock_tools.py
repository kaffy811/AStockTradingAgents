"""
Stock-related read-only tools (Phase C4):
  - resolve_stock_tool     — name/code → {market, symbol, name}
  - get_quote_tool         — real-time quote
  - get_kline_summary_tool — 20-day kline stats
  - get_latest_news_tool   — recent news items

All tools return ToolResult.  None raise exceptions to callers.
Financial safety: no 买入/卖出/持有/目标价 in outputs.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.chat_tools.base import BaseTool
from app.agents.chat_tools.tool_result import ToolResult
from app.services.industry_classification_service import IndustryClassificationService
from app.services.news_data_service import news_data_service
from app.services.stock_data_service import stock_data_service

log = logging.getLogger(__name__)

_cls_svc = IndustryClassificationService()

# ── helpers ───────────────────────────────────────────────────────────────────

def _card(card_type: str, data: dict) -> dict:
    return {"type": card_type, "data": data}


def _pct(val: float) -> str:
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.2f}%"


# ── resolve_stock_tool ────────────────────────────────────────────────────────

class ResolveStockTool(BaseTool):
    @property
    def name(self) -> str:
        return "resolve_stock_tool"

    async def run(self, db: AsyncSession, **kwargs: Any) -> ToolResult:
        query: str = kwargs.get("query", "").strip()
        market: str = kwargs.get("market", "CN").upper()

        if not query:
            return ToolResult(ok=False, tool_name=self.name, summary="缺少查询词", error="query is empty")

        try:
            results = await _cls_svc.search_stocks(db, market, query, limit=5)
        except Exception as exc:
            log.warning("resolve_stock_tool: search failed [%s/%s]: %s", market, query, exc)
            return ToolResult(ok=False, tool_name=self.name, summary="股票解析失败", error=str(exc))

        if not results:
            # Fallback: treat the query itself as a symbol if it looks like a code
            if query.isdigit():
                return ToolResult(
                    ok=True,
                    tool_name=self.name,
                    summary=f"{market}/{query} → (名称未知，直接使用代码)",
                    data={"market": market, "symbol": query, "name": query},
                    source="fallback",
                )
            return ToolResult(ok=False, tool_name=self.name, summary=f"未找到股票：{query}", error="no results")

        top = results[0]
        return ToolResult(
            ok=True,
            tool_name=self.name,
            summary=f"{market}/{top['symbol']} → {top.get('name', top['symbol'])}",
            data={
                "market":  top.get("market", market),
                "symbol":  top["symbol"],
                "name":    top.get("name", top["symbol"]),
                "industry_name": top.get("industry_name"),
            },
            source="db",
        )


# ── get_quote_tool ────────────────────────────────────────────────────────────

class GetQuoteTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_quote_tool"

    async def run(self, db: AsyncSession, **kwargs: Any) -> ToolResult:
        market: str = kwargs.get("market", "CN").upper()
        symbol: str = kwargs.get("symbol", "").strip()
        name: str   = kwargs.get("name", symbol)

        if not symbol:
            return ToolResult(ok=False, tool_name=self.name, summary="缺少股票代码", error="symbol is empty")

        quote = stock_data_service.get_quote_optional(market, symbol)
        if quote is None:
            return ToolResult(
                ok=False, tool_name=self.name,
                summary=f"行情数据暂不可用（{market}/{symbol}）",
                error="quote unavailable",
            )

        price      = quote.get("current_price") or quote.get("price") or "—"
        change_pct = quote.get("pct_change") or quote.get("change_pct") or 0.0
        try:
            change_pct_f = float(change_pct)
            change_str   = _pct(change_pct_f)
            change_dir   = "up" if change_pct_f >= 0 else "down"
        except (TypeError, ValueError):
            change_str = str(change_pct)
            change_dir = "flat"

        card = _card("stock_summary", {
            "name":       name,
            "market":     market,
            "symbol":     symbol,
            "price":      str(price),
            "changePct":  change_str,
            "changeDir":  change_dir,
            "summary":    f"当前价 {price}，涨跌幅 {change_str}",
            "links": [
                {"label": "查看股票详情", "path": f"/stocks/{market}/{symbol}"},
            ],
        })

        return ToolResult(
            ok=True,
            tool_name=self.name,
            summary=f"当前价 {price}（{change_str}）",
            data={"market": market, "symbol": symbol, "name": name,
                  "price": str(price), "change_pct": change_str, "change_dir": change_dir,
                  "raw": quote},
            cards=[card],
            source=quote.get("source", "stock_data_service"),
        )


# ── get_kline_summary_tool ────────────────────────────────────────────────────

class GetKlineSummaryTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_kline_summary_tool"

    async def run(self, db: AsyncSession, **kwargs: Any) -> ToolResult:
        market: str = kwargs.get("market", "CN").upper()
        symbol: str = kwargs.get("symbol", "").strip()
        limit: int  = int(kwargs.get("limit", 20))

        if not symbol:
            return ToolResult(ok=False, tool_name=self.name, summary="缺少股票代码", error="symbol is empty")

        try:
            bars = stock_data_service.get_kline_for_agent(market, symbol, limit=limit)
        except Exception as exc:
            log.warning("get_kline_summary_tool: failed [%s/%s]: %s", market, symbol, exc)
            return ToolResult(ok=False, tool_name=self.name, summary="K线数据暂不可用", error=str(exc))

        if not bars:
            return ToolResult(ok=False, tool_name=self.name, summary="K线数据为空", error="empty bars")

        closes  = [b.get("close") or b.get("c") for b in bars if b.get("close") or b.get("c")]
        highs   = [b.get("high")  or b.get("h") for b in bars if b.get("high")  or b.get("h")]
        lows    = [b.get("low")   or b.get("l") for b in bars if b.get("low")   or b.get("l")]

        try:
            closes_f = [float(c) for c in closes if c is not None]
            first_c, last_c = closes_f[0], closes_f[-1]
            pct_chg = (last_c - first_c) / first_c * 100 if first_c else 0.0
            period_high = max(float(h) for h in highs if h is not None)
            period_low  = min(float(l) for l in lows  if l is not None)
            summary_txt = (
                f"近{limit}日涨幅 {_pct(pct_chg)}，"
                f"区间高 {period_high:.2f}，区间低 {period_low:.2f}"
            )
        except Exception:
            summary_txt = f"获取近{limit}日K线 {len(bars)} 条"
            pct_chg = 0.0

        return ToolResult(
            ok=True,
            tool_name=self.name,
            summary=summary_txt,
            data={
                "market": market, "symbol": symbol,
                "bars_count": len(bars),
                "period_change_pct": round(pct_chg, 2),
                "bars_sample": bars[-5:],   # last 5 bars for orchestrator
            },
            source="stock_data_service",
        )


# ── get_latest_news_tool ──────────────────────────────────────────────────────

class GetLatestNewsTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_latest_news_tool"

    async def run(self, db: AsyncSession, **kwargs: Any) -> ToolResult:
        market: str    = kwargs.get("market", "CN").upper()
        symbol: str    = kwargs.get("symbol", "").strip()
        hours_back: int = int(kwargs.get("hours_back", 72))
        limit: int      = int(kwargs.get("limit", 6))

        if not symbol:
            return ToolResult(ok=False, tool_name=self.name, summary="缺少股票代码", error="symbol is empty")

        try:
            result = news_data_service.get_stock_news(market, symbol, hours_back=hours_back, limit=limit)
        except Exception as exc:
            log.warning("get_latest_news_tool: failed [%s/%s]: %s", market, symbol, exc)
            return ToolResult(ok=False, tool_name=self.name, summary="新闻数据暂不可用", error=str(exc))

        items = result.get("items", [])
        count = result.get("count", len(items))
        summary_txt = f"获取近{hours_back}小时新闻 {count} 条"

        # Strip raw content — only pass title + summary + url (no full text as system instruction)
        safe_items = [
            {
                "title":        it.get("title", ""),
                "summary":      (it.get("summary") or "")[:200],
                "source":       it.get("source", ""),
                "publish_time": it.get("publish_time", ""),
                "url":          it.get("url", ""),
            }
            for it in items[:limit]
        ]

        return ToolResult(
            ok=True,
            tool_name=self.name,
            summary=summary_txt,
            data={"market": market, "symbol": symbol, "items": safe_items, "count": count},
            source=result.get("data_quality", {}).get("provider") or "news_data_service",
        )
