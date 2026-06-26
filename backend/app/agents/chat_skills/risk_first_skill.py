"""
RiskFirstSkill — Phase C6.

Handles risk-first analysis requests:
  "最大风险是什么", "重点看风险", "风险优先研究" …
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
    r"最大风险|重点看.{0,6}风险|主要风险|风险优先|风险.{0,6}研究|风险.{0,6}关注",
    re.IGNORECASE,
)


class RiskFirstSkill(BaseSkill):
    name = "risk_first_skill"
    description = "从风险优先视角分析股票，梳理技术面与新闻面风险"
    intent_examples = [
        "最大风险是什么",
        "重点看风险",
        "风险优先分析 688146",
        "主要风险有哪些",
    ]
    required_tools = ["resolve_stock_tool", "get_kline_summary_tool", "get_latest_news_tool"]
    optional_tools = ["get_recent_reports_tool"]
    safety_level = "read_only"
    priority = 35

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

        # 1. Resolve stock (best-effort)
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

        # 2. Kline (technical risk signals)
        kline_risk_lines: list[str] = []
        if has_symbol:
            kline = await context.tool_registry.call(
                "get_kline_summary_tool", context.db,
                event_callback=context.event_callback,
                market=stock["market"], symbol=stock["symbol"],
            )
            events.append(self._result_event(kline))
            if kline.ok and kline.data:
                chg = kline.data.get("period_change_pct", 0)
                sign = "+" if chg >= 0 else ""
                kline_risk_lines.append(
                    f"- 近20日涨跌幅 **{sign}{chg:.2f}%**，"
                    + ("短期涨幅显著，注意高位回调风险" if chg > 30 else "波动处于正常范围")
                )
            else:
                kline_risk_lines.append("- K线数据不可用（数据风险：无法评估技术面趋势）")
        else:
            kline_risk_lines.append("- 未识别到具体股票代码，无法评估技术面风险")

        # 3. News (news-side risks)
        news_risk_lines: list[str] = []
        if has_symbol:
            news = await context.tool_registry.call(
                "get_latest_news_tool", context.db,
                event_callback=context.event_callback,
                market=stock["market"], symbol=stock["symbol"],
                hours_back=72, limit=5,
            )
            events.append(self._result_event(news))
            if news.ok and news.data and news.data.get("items"):
                for it in news.data["items"][:3]:
                    title = it.get("title", "")
                    pub = it.get("publish_time", "")[:10]
                    if title:
                        news_risk_lines.append(f"- {title}（{pub}）— 需关注事件持续影响")
            if not news_risk_lines:
                news_risk_lines.append("- 近72小时内暂无新闻数据")
        else:
            news_risk_lines.append("- 未识别到具体股票代码，无法拉取新闻面风险")

        # 4. Recent reports (optional)
        report_lines: list[str] = []
        if has_symbol:
            reports = await context.tool_registry.call(
                "get_recent_reports_tool", context.db,
                event_callback=context.event_callback,
                user_id=context.user_id,
                market=stock["market"], symbol=stock["symbol"],
                limit=3,
            )
            events.append(self._result_event(reports))
            if reports.ok and reports.data and reports.data.get("count", 0) > 0:
                report_lines.append(
                    f"- 找到 {reports.data['count']} 份历史报告，建议结合报告中的风险章节综合评估"
                )
                cards.extend(reports.cards)
            else:
                report_lines.append("- 暂无历史报告（数据缺口：无法参照历史分析风险评估）")

        # ── Build answer ──────────────────────────────────────────────────────
        name_str = stock.get("name", "目标股票")
        market_sym = (
            f"{stock['market']}/{stock['symbol']}" if stock.get("symbol") else "未指定股票"
        )

        answer = (
            f"### 风险优先摘要\n\n"
            f"**{name_str}（{market_sym}）**\n\n"
            f"### 主要风险\n\n"
            "- 请结合具体股票和市场环境综合评估，以下为结构化风险拆解框架\n\n"
            "### 风险来源\n\n"
            "**技术面风险：**\n"
            + "\n".join(kline_risk_lines)
            + "\n\n**新闻面风险：**\n"
            + "\n".join(news_risk_lines)
            + (
                "\n\n**历史报告参考：**\n" + "\n".join(report_lines)
                if report_lines else ""
            )
            + "\n\n**数据缺口：**\n"
            "- 基本面财务数据、同行对比数据需通过完整报告获取\n\n"
            "### 后续观察\n\n"
            "如需完整风险评估，可输入「帮我生成综合报告」获取多维度分析。"
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
