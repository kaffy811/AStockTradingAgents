"""
NewsCatalystSkill — Phase C6.

Handles questions about news catalysts and fundamental drivers:
  "有没有实质利好", "新闻有什么影响", "订单兑现了吗" …
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
    r"新闻.{0,10}影响|实质利好|催化剂|订单兑现|新闻.{0,10}有什么|有没有.*利好|消息.*影响",
    re.IGNORECASE,
)


class NewsCatalystSkill(BaseSkill):
    name = "news_catalyst_skill"
    description = "分析新闻催化剂，区分已发生事实与市场预期"
    intent_examples = [
        "有没有实质利好",
        "新闻有什么影响",
        "最新消息影响怎么样",
        "催化剂是什么",
        "订单兑现了吗",
    ]
    required_tools = ["resolve_stock_tool", "get_latest_news_tool", "get_quote_tool"]
    safety_level = "read_only"
    priority = 45

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
        if hint:
            resolve = await context.tool_registry.call(
                "resolve_stock_tool", context.db,
                event_callback=context.event_callback,
                query=hint.get("query", ""),
                market=hint.get("market", "CN"),
            )
            events.append(self._result_event(resolve))
            stock = resolve.data if resolve.ok and resolve.data else {
                "market": hint.get("market", "CN"),
                "symbol": hint.get("symbol", ""),
                "name": hint.get("name", "目标股票"),
            }
        else:
            stock = {"market": "CN", "symbol": "", "name": "目标股票"}

        has_symbol = bool(stock.get("symbol"))

        # 2. News (core data for this skill)
        news_items: list[dict] = []
        if has_symbol:
            news = await context.tool_registry.call(
                "get_latest_news_tool", context.db,
                event_callback=context.event_callback,
                market=stock["market"], symbol=stock["symbol"],
                hours_back=72, limit=8,
            )
            events.append(self._result_event(news))
            if news.ok and news.data and news.data.get("items"):
                news_items = news.data["items"]

        # 3. Quote (to cross-reference price reaction)
        if has_symbol:
            quote = await context.tool_registry.call(
                "get_quote_tool", context.db,
                event_callback=context.event_callback,
                market=stock["market"], symbol=stock["symbol"],
                name=stock.get("name", stock["symbol"]),
            )
            events.append(self._result_event(quote))
            if quote.ok:
                cards.extend(quote.cards)

        # ── Build answer ──────────────────────────────────────────────────────
        name_str = stock.get("name", "目标股票")
        market_sym = (
            f"{stock['market']}/{stock['symbol']}" if stock.get("symbol") else "未指定股票"
        )

        if not news_items:
            answer = (
                f"### 新闻催化摘要\n\n"
                f"**{name_str}（{market_sym}）**\n\n"
                "近72小时内暂无新闻数据，无法进行催化剂分析。\n\n"
                "### 后续观察\n\n"
                "建议关注公司公告渠道，获取最新事件信息。"
                + _DISCLAIMER
                + _coordinator.format_for_answer(rag_result)
            )
        else:
            # Separate fact vs expectation heuristically
            fact_lines: list[str] = []
            expect_lines: list[str] = []
            unfulfilled_lines: list[str] = []

            for it in news_items[:6]:
                title = it.get("title", "")
                pub = it.get("publish_time", "")[:10]
                if not title:
                    continue
                # Heuristic classification
                if re.search(r"公告|已|完成|签署|发布|披露|获批|中标", title):
                    fact_lines.append(f"- {title}（{pub}）")
                elif re.search(r"预计|有望|计划|预期|拟|将|可能", title):
                    expect_lines.append(f"- {title}（{pub}）— 注意：此为预期，尚未兑现")
                else:
                    unfulfilled_lines.append(f"- {title}（{pub}）")

            if not fact_lines:
                fact_lines.append("- 近期无明确已兑现事实性公告")
            if not expect_lines:
                expect_lines.append("- 暂无明确预期或计划性新闻")

            answer = (
                f"### 新闻催化摘要\n\n"
                f"**{name_str}（{market_sym}）**\n\n"
                "### 已发生事实\n\n"
                + "\n".join(fact_lines)
                + "\n\n### 市场预期\n\n"
                + "\n".join(expect_lines)
                + (
                    "\n\n### 未兑现风险\n\n"
                    + "\n".join(unfulfilled_lines)
                    if unfulfilled_lines else ""
                )
                + "\n\n### 后续观察\n\n"
                "以上分类基于标题关键词启发式判断，实际影响需结合公司基本面综合评估。"
                + _DISCLAIMER
                + _coordinator.format_for_answer(rag_result)
            )

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
