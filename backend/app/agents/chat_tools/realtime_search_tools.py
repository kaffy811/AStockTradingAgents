"""
Realtime market search tools — Phase C25.

  SearchRealtimeNewsTool    — keyword-based realtime news (AKShare / Eastmoney)
  UniversalMarketSearchTool — concept / industry rank / fund-flow / news search

These are "no-symbol" tools used when the user asks about market hotspots,
trending sectors, or realtime news without referencing a specific stock.

Safety: content is capped to 120-char snippets; full article text is never
forwarded to the LLM.  All results carry the standard disclaimer.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.chat_tools.base import BaseTool
from app.agents.chat_tools.tool_result import ToolResult

log = logging.getLogger(__name__)


def _snippet(text: str, max_len: int = 120) -> str:
    text = (text or "").strip()
    return text[:max_len] + "…" if len(text) > max_len else text


# ── SearchRealtimeNewsTool ─────────────────────────────────────────────────────

class SearchRealtimeNewsTool(BaseTool):
    """
    Fetch recent news articles for any keyword (stock code, company name,
    industry term, macro topic) via AKShare / Eastmoney keyword search.

    Returns up to `limit` items sorted by publish_time descending.
    Never exposes raw article bodies — only 120-char snippets.
    """

    @property
    def name(self) -> str:
        return "search_realtime_news"

    async def run(self, db: AsyncSession, **kwargs: Any) -> ToolResult:
        keyword: str = str(kwargs.get("keyword", "")).strip()
        limit: int   = min(int(kwargs.get("limit", 8)), 20)

        if not keyword:
            return ToolResult(
                ok=False,
                tool_name=self.name,
                summary="缺少搜索关键词",
                error="keyword parameter is required",
            )

        def _fetch() -> list[dict]:
            import akshare as ak
            df = ak.stock_news_em(symbol=keyword)
            items: list[dict] = []
            for _, row in df.head(limit).iterrows():
                items.append({
                    "title":        str(row.get("新闻标题", "")).strip(),
                    "snippet":      _snippet(str(row.get("新闻内容", ""))),
                    "publish_time": str(row.get("发布时间", "")).strip(),
                    "source":       str(row.get("文章来源", "")).strip(),
                    "url":          str(row.get("新闻链接", "")).strip(),
                })
            return items

        try:
            items = await asyncio.to_thread(_fetch)
        except Exception as exc:
            log.warning("search_realtime_news: akshare fetch failed [%s]: %s", keyword, exc)
            return ToolResult(
                ok=False,
                tool_name=self.name,
                summary=f'实时新闻暂时无法获取（{exc}）',
                error=str(exc),
            )

        if not items:
            return ToolResult(
                ok=True,
                tool_name=self.name,
                summary=f'未找到关于"{keyword}"的最新新闻',
                data={"keyword": keyword, "items": [], "count": 0},
                source="akshare",
            )

        bullets = "\n".join(
            f'- [{it["publish_time"]}] **{it["title"]}**（{it["source"]}）  {it["snippet"]}'
            for it in items
        )
        summary = f'关于"{keyword}"的最新 {len(items)} 条新闻（东方财富，实时）'

        return ToolResult(
            ok=True,
            tool_name=self.name,
            summary=summary,
            data={"keyword": keyword, "items": items, "count": len(items)},
            text=bullets,
            source="akshare_eastmoney",
        )


# ── UniversalMarketSearchTool ─────────────────────────────────────────────────

_SEARCH_MODES = {"news", "concept", "industry_rank", "fund_flow", "hot_stocks"}

_MODE_LABELS: dict[str, str] = {
    "news":          "实时新闻",
    "concept":       "概念板块热度",
    "industry_rank": "行业涨跌排行",
    "fund_flow":     "主力资金流向",
    "hot_stocks":    "热门股排行",
}


class UniversalMarketSearchTool(BaseTool):
    """
    Universal market search — covers concept/industry/rank/fund_flow/news
    via AKShare.  Chooses the best data source based on `mode`.

    Modes:
      news          — keyword news (same as SearchRealtimeNewsTool)
      concept       — A-share concept board list with change_pct
      industry_rank — Eastmoney industry change-pct ranking
      fund_flow     — main-force fund-flow by sector (东方财富)
      hot_stocks    — realtime hot-stocks chart (东方财富人气榜)

    Returns a text summary suitable for LLM context injection.
    """

    @property
    def name(self) -> str:
        return "universal_market_search"

    async def run(self, db: AsyncSession, **kwargs: Any) -> ToolResult:
        mode: str    = str(kwargs.get("mode", "news")).strip().lower()
        keyword: str = str(kwargs.get("keyword", "")).strip()
        limit: int   = min(int(kwargs.get("limit", 10)), 30)

        if mode not in _SEARCH_MODES:
            mode = "news"

        if mode == "news":
            return await self._fetch_news(keyword, limit)
        elif mode == "concept":
            return await self._fetch_concept(keyword, limit)
        elif mode == "industry_rank":
            return await self._fetch_industry_rank(limit)
        elif mode == "fund_flow":
            return await self._fetch_fund_flow(limit)
        elif mode == "hot_stocks":
            return await self._fetch_hot_stocks(limit)
        else:
            return ToolResult(
                ok=False, tool_name=self.name,
                summary=f"不支持的搜索模式: {mode}",
                error=f"unknown mode={mode}",
            )

    # ── mode: news ─────────────────────────────────────────────────────────────

    async def _fetch_news(self, keyword: str, limit: int) -> ToolResult:
        if not keyword:
            return ToolResult(ok=False, tool_name=self.name, summary="news 模式需要提供 keyword",
                              error="keyword required for news mode")

        def _fetch() -> list[dict]:
            import akshare as ak
            df = ak.stock_news_em(symbol=keyword)
            items = []
            for _, row in df.head(limit).iterrows():
                items.append({
                    "title":        str(row.get("新闻标题", "")).strip(),
                    "snippet":      _snippet(str(row.get("新闻内容", ""))),
                    "publish_time": str(row.get("发布时间", "")).strip(),
                    "source":       str(row.get("文章来源", "")).strip(),
                })
            return items

        try:
            items = await asyncio.to_thread(_fetch)
        except Exception as exc:
            log.warning("universal_market_search/news [%s]: %s", keyword, exc)
            return ToolResult(ok=False, tool_name=self.name,
                              summary=f'新闻获取失败（{exc}）', error=str(exc))

        text = "\n".join(
            f'- [{it["publish_time"]}] {it["title"]}（{it["source"]}）'
            for it in items
        )
        return ToolResult(
            ok=True, tool_name=self.name,
            summary=f'"{keyword}" 相关新闻 {len(items)} 条',
            data={"mode": "news", "keyword": keyword, "items": items},
            text=text, source="akshare_eastmoney",
        )

    # ── mode: concept ──────────────────────────────────────────────────────────

    async def _fetch_concept(self, keyword: str, limit: int) -> ToolResult:
        def _fetch() -> list[dict]:
            import akshare as ak
            df = ak.stock_board_concept_name_em()
            if keyword:
                mask = df.apply(lambda r: keyword in str(r.values), axis=1)
                df = df[mask]
            cols = df.columns.tolist()
            items = []
            for _, row in df.head(limit).iterrows():
                name = str(row.get("板块名称", row.get(cols[1], ""))).strip()
                chg  = row.get("涨跌幅", row.get("涨跌额", None))
                items.append({
                    "name":       name,
                    "change_pct": f"{float(chg):+.2f}%" if chg is not None else "—",
                    "count":      int(row.get("公司家数", row.get("成分股数量", 0))),
                })
            return items

        try:
            items = await asyncio.to_thread(_fetch)
        except Exception as exc:
            log.warning("universal_market_search/concept: %s", exc)
            return ToolResult(ok=False, tool_name=self.name,
                              summary=f"概念板块数据暂不可用（{exc}）", error=str(exc))

        label = f'"{keyword}" 相关' if keyword else "全部"
        text = "\n".join(
            f'- {it["name"]} {it["change_pct"]}（{it["count"]} 只股）'
            for it in items
        )
        return ToolResult(
            ok=True, tool_name=self.name,
            summary=f'{label}概念板块 Top {len(items)}',
            data={"mode": "concept", "keyword": keyword, "items": items},
            text=text, source="akshare_eastmoney",
        )

    # ── mode: industry_rank ────────────────────────────────────────────────────

    async def _fetch_industry_rank(self, limit: int) -> ToolResult:
        def _fetch() -> list[dict]:
            import akshare as ak
            df = ak.stock_board_industry_name_em()
            cols = df.columns.tolist()
            chg_col = next((c for c in cols if "涨跌幅" in c), cols[2] if len(cols) > 2 else None)
            if chg_col:
                df = df.sort_values(chg_col, ascending=False)
            items = []
            for _, row in df.head(limit).iterrows():
                name = str(row.get("板块名称", row.get(cols[1], ""))).strip()
                chg  = row.get(chg_col) if chg_col else None
                items.append({
                    "name":       name,
                    "change_pct": f"{float(chg):+.2f}%" if chg is not None else "—",
                })
            return items

        try:
            items = await asyncio.to_thread(_fetch)
        except Exception as exc:
            log.warning("universal_market_search/industry_rank: %s", exc)
            return ToolResult(ok=False, tool_name=self.name,
                              summary=f"行业排行暂不可用（{exc}）", error=str(exc))

        text = "\n".join(f'- {it["name"]} {it["change_pct"]}' for it in items)
        return ToolResult(
            ok=True, tool_name=self.name,
            summary=f"行业涨跌幅排行 Top {len(items)}",
            data={"mode": "industry_rank", "items": items},
            text=text, source="akshare_eastmoney",
        )

    # ── mode: fund_flow ────────────────────────────────────────────────────────

    async def _fetch_fund_flow(self, limit: int) -> ToolResult:
        def _fetch() -> list[dict]:
            import akshare as ak
            df = ak.stock_sector_fund_flow_rank(indicator="今日")
            cols = df.columns.tolist()
            # Sort by main-force net inflow descending
            inflow_col = next((c for c in cols if "主力净流入" in c or "净额" in c), None)
            if inflow_col:
                df = df.sort_values(inflow_col, ascending=False)
            items = []
            for _, row in df.head(limit).iterrows():
                name   = str(row.get("名称", row.get(cols[0], ""))).strip()
                inflow = row.get(inflow_col) if inflow_col else None
                chg    = row.get("涨跌幅", None)
                items.append({
                    "name":    name,
                    "inflow":  f"{float(inflow)/1e8:.2f}亿" if inflow is not None else "—",
                    "change":  f"{float(chg):+.2f}%" if chg is not None else "—",
                })
            return items

        try:
            items = await asyncio.to_thread(_fetch)
        except Exception as exc:
            log.warning("universal_market_search/fund_flow: %s", exc)
            return ToolResult(ok=False, tool_name=self.name,
                              summary=f"资金流向暂不可用（{exc}）", error=str(exc))

        text = "\n".join(
            f'- {it["name"]} 主力净流入 {it["inflow"]} 涨跌 {it["change"]}'
            for it in items
        )
        return ToolResult(
            ok=True, tool_name=self.name,
            summary=f"主力资金净流入排行 Top {len(items)}",
            data={"mode": "fund_flow", "items": items},
            text=text, source="akshare_eastmoney",
        )

    # ── mode: hot_stocks ──────────────────────────────────────────────────────

    async def _fetch_hot_stocks(self, limit: int) -> ToolResult:
        def _fetch() -> list[dict]:
            import akshare as ak
            # 东方财富人气榜
            df = ak.stock_hot_rank_em()
            cols = df.columns.tolist()
            items = []
            for _, row in df.head(limit).iterrows():
                name   = str(row.get("股票名称", row.get(cols[1], ""))).strip()
                code   = str(row.get("股票代码", row.get(cols[0], ""))).strip()
                rank   = int(row.get("序号", row.get("排名", 0)))
                chg    = row.get("涨跌幅", None)
                items.append({
                    "rank":       rank,
                    "name":       name,
                    "code":       code,
                    "change_pct": f"{float(chg):+.2f}%" if chg is not None else "—",
                })
            return items

        try:
            items = await asyncio.to_thread(_fetch)
        except Exception as exc:
            log.warning("universal_market_search/hot_stocks: %s", exc)
            return ToolResult(ok=False, tool_name=self.name,
                              summary=f"热门股数据暂不可用（{exc}）", error=str(exc))

        text = "\n".join(
            f'- #{it["rank"]} {it["name"]}（{it["code"]}）{it["change_pct"]}'
            for it in items
        )
        return ToolResult(
            ok=True, tool_name=self.name,
            summary=f"东方财富人气榜 Top {len(items)}",
            data={"mode": "hot_stocks", "items": items},
            text=text, source="akshare_eastmoney",
        )
