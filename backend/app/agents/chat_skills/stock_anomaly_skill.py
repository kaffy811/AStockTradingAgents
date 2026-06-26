"""
StockAnomalySkill — Phase C6.

Handles questions about why a stock moved recently:
  "中船特气最近为什么涨这么多", "688146 异动分析", "近期表现怎么样" …
"""
from __future__ import annotations

import re

from app.agents.chat_skills.base import (
    BaseSkill,
    SkillContext,
    SkillResult,
    _DISCLAIMER,
    _extract_stock_hint,
)
from app.agents.chat_rag import retrieve_context, RAGReviewCoordinator
from app.agents.chat_events import safe_emit

_PATTERN = re.compile(
    r"为什么.{0,20}(涨|跌|异动|波动)"
    r"|(涨|跌|异动|波动).{0,20}(原因|为什么|怎么了)"
    r"|异动分析|近期表现|中船特气|688146",
    re.IGNORECASE,
)


class StockAnomalySkill(BaseSkill):
    name = "stock_anomaly_skill"
    description = "分析股票近期异动原因，结合技术面与新闻面"
    intent_examples = [
        "中船特气最近为什么涨这么多",
        "688146 异动分析",
        "这只股票为什么跌",
        "近期表现怎么样",
    ]
    required_tools = ["resolve_stock_tool", "get_quote_tool", "get_kline_summary_tool", "get_latest_news_tool"]
    safety_level = "read_only"
    priority = 40

    def can_handle(self, message: str, context: SkillContext) -> bool:
        return bool(_PATTERN.search(message))

    async def run(self, message: str, context: SkillContext) -> SkillResult:
        hint = _extract_stock_hint(message)
        events: list = []
        cards: list = []

        await safe_emit(context.event_callback, "skill_started", {
            "skill_name": self.name,
            "skill_spec": self.name,
            "source": "skill_registry",
        })

        # 0. RAG retrieval + review
        rag_result = await retrieve_context(message, context)
        _coordinator = RAGReviewCoordinator()
        await safe_emit(context.event_callback, "rag_review_started", {"source": "rag_review_coordinator"})
        _coordinator.review(rag_result)
        await safe_emit(context.event_callback, "rag_review_completed", {
            "overall_confidence": rag_result.overall_confidence,
            "documents_count": len(rag_result.documents),
            "approved_for_answer": rag_result.approved,
            "source": "rag_review_coordinator",
        })
        events.append(self._tool_event("rag_retrieve", f"检索到 {len(rag_result.documents)} 份参考资料", "success" if rag_result.ok else "error"))
        events.append(self._tool_event("rag_review", f"可信度：{rag_result.overall_confidence}", "success"))

        # 1. Resolve stock
        resolve = await context.tool_registry.call(
            "resolve_stock_tool", context.db,
            event_callback=context.event_callback,
            query=hint.get("query", "688146"),
            market=hint.get("market", "CN"),
        )
        events.append(self._result_event(resolve))
        if resolve.ok and resolve.data:
            stock = resolve.data
        else:
            stock = {
                "market": hint.get("market", "CN"),
                "symbol": hint.get("symbol", "688146"),
                "name": hint.get("name", "未知股票"),
            }

        # 2. Quote
        quote = await context.tool_registry.call(
            "get_quote_tool", context.db,
            event_callback=context.event_callback,
            market=stock["market"], symbol=stock["symbol"],
            name=stock.get("name", stock["symbol"]),
        )
        events.append(self._result_event(quote))
        if quote.ok:
            cards.extend(quote.cards)

        # 3. Kline summary
        kline = await context.tool_registry.call(
            "get_kline_summary_tool", context.db,
            event_callback=context.event_callback,
            market=stock["market"], symbol=stock["symbol"],
        )
        events.append(self._result_event(kline))

        # 4. News
        news = await context.tool_registry.call(
            "get_latest_news_tool", context.db,
            event_callback=context.event_callback,
            market=stock["market"], symbol=stock["symbol"],
            hours_back=72, limit=6,
        )
        events.append(self._result_event(news))

        # ── Build answer ──────────────────────────────────────────────────────
        name_str = stock.get("name", stock["symbol"])
        market_sym = f"{stock['market']}/{stock['symbol']}"

        # Technical summary
        tech_lines: list[str] = []
        if quote.ok and quote.data:
            tech_lines.append(
                f"- 当前价 **{quote.data['price']}**，涨跌幅 {quote.data['change_pct']}"
            )
        else:
            tech_lines.append("- 行情数据暂不可用")

        if kline.ok and kline.data:
            chg = kline.data.get("period_change_pct", 0)
            sign = "+" if chg >= 0 else ""
            tech_lines.append(f"- 近20日区间涨跌幅：**{sign}{chg:.2f}%**")
        else:
            tech_lines.append("- K线数据暂不可用，无法获取近期涨跌幅区间")

        # News summary
        news_lines: list[str] = []
        if news.ok and news.data and news.data.get("items"):
            for it in news.data["items"][:3]:
                title = it.get("title", "")
                pub = it.get("publish_time", "")[:10]
                if title:
                    news_lines.append(f"- {title}（{pub}）")
        if not news_lines:
            news_lines.append("- 近72小时内暂无新闻数据")

        answer = (
            f"### 异动研究摘要\n\n"
            f"**{name_str}（{market_sym}）**\n\n"
            f"### 关键发现\n\n"
            f"**技术面：**\n"
            + "\n".join(tech_lines)
            + "\n\n**新闻面：**\n"
            + "\n".join(news_lines)
            + "\n\n**风险点：**\n"
            "- 短期涨幅较大需关注高位回调风险\n"
            "- 新闻面信息的真实性与持续性有待观察\n\n"
            "### 后续观察\n\n"
            "如需深度分析，可输入「帮我生成综合报告」获取基本面与技术面完整报告。"
            + _DISCLAIMER
            + _coordinator.format_for_answer(rag_result)
        )

        # Card: stock_summary with links
        if not cards:
            cards.append(self._card("stock_summary", {
                "name": name_str,
                "market": stock["market"],
                "symbol": stock["symbol"],
                "price": quote.data.get("price", "—") if quote.ok and quote.data else "—",
                "changePct": quote.data.get("change_pct", "—") if quote.ok and quote.data else "—",
                "changeDir": quote.data.get("change_dir", "flat") if quote.ok and quote.data else "flat",
                "summary": "异动研究摘要",
                "links": [
                    {"label": "查看股票详情", "path": f"/stocks/{stock['market']}/{stock['symbol']}"},
                    {
                        "label": "生成综合报告 →",
                        "action": "generate_report",
                        "symbol": stock["symbol"],
                        "market": stock["market"],
                        "name": name_str,
                    },
                ],
            }))

        await safe_emit(context.event_callback, "skill_completed", {
            "skill_name": self.name,
            "ok": True,
            "tools_used": [e.get("name", "") for e in events if e.get("status") == "success"],
            "cards_count": len(cards),
            "source": "skill_registry",
        })

        return SkillResult(
            ok=True,
            skill_name=self.name,
            answer=answer,
            tool_events=events,
            cards=cards,
        )
