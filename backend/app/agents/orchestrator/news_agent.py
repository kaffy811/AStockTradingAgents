"""
orchestrator/news_agent.py — Phase 2E-1: News / Events Sub-Agent.

Responsibilities
----------------
* Fetch recent news for the target stock.
* Summarise sentiment / key events.
* Return AgentFinding with source attribution.

Reuses
------
* GetLatestNewsTool (app.agents.chat_tools.stock_tools)

Safety rules
------------
* Source / published_at / url are always preserved in findings.sources.
* Never attributes sentiment without referencing specific news items.
* Only executed when intent.need_news is True.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator.schemas import make_agent_finding

log = logging.getLogger(__name__)

AGENT_NAME      = "news_agent"
TIMEOUT_SECONDS = 15.0


class NewsAgent:
    """
    Sub-agent for news and event-driven analysis.

    Accepts an injectable `news_tool` for unit testing.
    """

    def __init__(self, *, news_tool: Any = None) -> None:
        self._news_tool = news_tool

    def _get_news_tool(self) -> Any:
        if self._news_tool is not None:
            return self._news_tool
        from app.agents.chat_tools.stock_tools import GetLatestNewsTool  # noqa: PLC0415
        return GetLatestNewsTool()

    async def run(
        self,
        intent: dict,
        db: AsyncSession,
        *,
        event_callback: Callable | None = None,
    ) -> dict:
        """
        Fetch and summarise news. Never raises.
        """
        symbol = intent.get("symbol", "")
        market = intent.get("market", "")

        if not symbol or not market:
            return make_agent_finding(
                AGENT_NAME,
                status="failed",
                summary="缺少股票代码或市场信息，无法获取新闻数据。",
                risk_flags=["missing_symbol"],
            )

        sources:     list[dict] = []
        data_points: list[str]  = []
        risk_flags:  list[str]  = []
        news_items:  list[dict] = []

        try:
            tool   = self._get_news_tool()
            result = await tool.run(db, market=market, symbol=symbol, hours_back=72, limit=6)
            if result.ok and result.data:
                news_items = result.data.get("items", [])
                for item in news_items:
                    title        = item.get("title", "")
                    summary_text = item.get("summary", "")[:200]
                    publish_time = item.get("publish_time", "")
                    source_name  = item.get("source", "")
                    url          = item.get("url", "")

                    if title:
                        data_points.append(f"[{publish_time}] {title}")
                    sources.append({
                        "title":        title,
                        "source_type":  "news",
                        "source":       source_name,
                        "published_at": publish_time,
                        "url":          url,
                        "verified":     False,
                        "source_level": "authoritative_media",
                        "authority_score": 0.6,
                    })
            else:
                risk_flags.append("news_fetch_failed")
        except Exception as exc:
            log.warning("NewsAgent: news tool failed: %s", exc)
            risk_flags.append("news_fetch_failed")

        if not news_items:
            return make_agent_finding(
                AGENT_NAME,
                status="partial",
                summary=f"未找到 {symbol} 最近 72 小时内的新闻信息。",
                risk_flags=risk_flags,
            )

        summary = (
            f"找到 {len(news_items)} 条 {symbol} 相关新闻。"
            f"最新：{news_items[0].get('title', '')}"
        )

        return make_agent_finding(
            AGENT_NAME,
            status="success",
            summary=summary,
            data_points=data_points[:10],
            risk_flags=risk_flags,
            sources=sources[:10],
        )
