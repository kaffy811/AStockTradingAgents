"""
Industry read-only tools (Phase C4 + Phase 2E-4):
  - get_industry_hot_tool    — top industries by hot score
  - get_industry_stocks_tool — hot stocks within a specific industry
  - get_industry_news_tool   — recent news for an industry keyword (AKShare)

No investment advice output.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.chat_tools.base import BaseTool
from app.agents.chat_tools.tool_result import ToolResult
from app.models.industry import StockIndustryMap
from app.services.industry_hot_stock_service import industry_hot_stock_service

log = logging.getLogger(__name__)


def _card(card_type: str, data: dict) -> dict:
    return {"type": card_type, "data": data}


def _fmt_pct(val: float | None) -> str:
    if val is None:
        return "—"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.2f}%"


class GetIndustryHotTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_industry_hot_tool"

    async def run(self, db: AsyncSession, **kwargs: Any) -> ToolResult:
        market: str = kwargs.get("market", "CN").upper()
        limit: int  = int(kwargs.get("limit", 8))

        try:
            hot_summary = await industry_hot_stock_service.get_industry_hot_summary(db, market)
        except Exception as exc:
            log.warning("get_industry_hot_tool: failed [%s]: %s", market, exc)
            return ToolResult(ok=False, tool_name=self.name, summary="行业热度数据暂不可用", error=str(exc))

        if not hot_summary:
            return ToolResult(
                ok=True, tool_name=self.name,
                summary="暂无行业热度快照",
                data={"items": [], "market": market},
                source="db",
            )

        # Enrich with industry names from StockIndustryMap
        codes = list(hot_summary.keys())
        name_map: dict[str, str] = {}
        try:
            name_stmt = (
                select(StockIndustryMap.industry_code, StockIndustryMap.industry_name)
                .where(
                    StockIndustryMap.market == market,
                    StockIndustryMap.industry_code.in_(codes),
                )
                .distinct()
            )
            for row in (await db.execute(name_stmt)).all():
                name_map[row.industry_code] = row.industry_name
        except Exception as exc:
            log.warning("get_industry_hot_tool: name lookup failed: %s", exc)

        sorted_industries = sorted(
            hot_summary.items(),
            key=lambda kv: kv[1].get("hot_score") or 0,
            reverse=True,
        )[:limit]

        items = [
            {
                "name":       name_map.get(code, code),
                "code":       code,
                "hotScore":   round(float(info.get("hot_score") or 0), 2),
                "changePct":  _fmt_pct(info.get("avg_change_pct")),
                "stockCount": info.get("stock_count", 0),
            }
            for code, info in sorted_industries
        ]

        card = _card("industry_hot", {
            "items": items,
            "links": [{"label": "查看行业页", "path": "/industries"}],
        })

        return ToolResult(
            ok=True,
            tool_name=self.name,
            summary=f"行业热度排行（Top {len(items)}），基于成交额×涨跌幅综合评分",
            data={"market": market, "items": items},
            cards=[card],
            source="db",
        )


class GetIndustryStocksTool(BaseTool):
    @property
    def name(self) -> str:
        return "get_industry_stocks_tool"

    async def run(self, db: AsyncSession, **kwargs: Any) -> ToolResult:
        market: str        = kwargs.get("market", "CN").upper()
        industry_code: str = kwargs.get("industry_code", "").strip()
        industry_name: str = kwargs.get("industry_name", industry_code)
        limit: int         = int(kwargs.get("limit", 10))

        if not industry_code:
            return ToolResult(ok=False, tool_name=self.name, summary="缺少行业代码", error="industry_code missing")

        try:
            result = await industry_hot_stock_service.get_latest_hot_stocks(
                db, market, industry_code, limit=limit
            )
        except Exception as exc:
            log.warning("get_industry_stocks_tool: failed [%s/%s]: %s", market, industry_code, exc)
            return ToolResult(ok=False, tool_name=self.name, summary="行业热股数据暂不可用", error=str(exc))

        items = result.get("items", [])
        if not items:
            return ToolResult(
                ok=True, tool_name=self.name,
                summary=f"{industry_name} 暂无热股快照",
                data={"market": market, "industry_code": industry_code, "items": []},
                source="db",
            )

        display = [
            {
                "name":      it.get("stock_name") or it.get("symbol"),
                "symbol":    it.get("symbol"),
                "market":    market,
                "hotScore":  round(float(it.get("hot_score") or 0), 2),
                "changePct": _fmt_pct(it.get("change_pct")),
            }
            for it in items[:limit]
        ]

        return ToolResult(
            ok=True,
            tool_name=self.name,
            summary=f"{industry_name} 热门股 Top {len(display)}",
            data={"market": market, "industry_code": industry_code, "items": display},
            source="db",
        )


class GetIndustryNewsTool(BaseTool):
    """
    Fetch recent news articles for an industry keyword (e.g. "新能源", "半导体")
    via AKShare / Eastmoney keyword search.

    Returns up to `limit` news items sorted by publish_time descending.
    Results are real-time (no cache) — do NOT expose raw article bodies in LLM prompts.
    """

    @property
    def name(self) -> str:
        return "get_industry_news_tool"

    async def run(self, db: AsyncSession, **kwargs: Any) -> ToolResult:
        import asyncio

        keyword: str = kwargs.get("keyword", "").strip()
        limit: int   = min(int(kwargs.get("limit", 8)), 20)

        if not keyword:
            return ToolResult(
                ok=False,
                tool_name=self.name,
                summary="缺少行业关键词",
                error="keyword parameter is required",
            )

        def _fetch() -> list[dict]:
            import akshare as ak
            df = ak.stock_news_em(symbol=keyword)
            items = []
            for _, row in df.head(limit).iterrows():
                title    = str(row.get("新闻标题", "")).strip()
                content  = str(row.get("新闻内容", "")).strip()
                pub_time = str(row.get("发布时间", "")).strip()
                source   = str(row.get("文章来源", "")).strip()
                url      = str(row.get("新闻链接", "")).strip()
                # Truncate content to 120 chars for safety — full text not exposed
                snippet = content[:120] + "…" if len(content) > 120 else content
                items.append({
                    "title":       title,
                    "snippet":     snippet,
                    "publish_time": pub_time,
                    "source":      source,
                    "url":         url,
                })
            return items

        try:
            items = await asyncio.to_thread(_fetch)
        except Exception as exc:
            log.warning("get_industry_news_tool: akshare fetch failed [%s]: %s", keyword, exc)
            return ToolResult(
                ok=False,
                tool_name=self.name,
                summary=f"行业新闻暂时无法获取（{exc}）",
                error=str(exc),
            )

        if not items:
            return ToolResult(
                ok=True,
                tool_name=self.name,
                summary=f'未找到关于"{keyword}"的最新新闻',
                data={"keyword": keyword, "items": []},
                source="akshare",
            )

        bullets = "\n".join(
            f"- [{it['publish_time']}] **{it['title']}**（{it['source']}）  {it['snippet']}"
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
