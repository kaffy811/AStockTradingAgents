"""
WatchlistReviewSkill — Phase C6.

Handles watchlist review / patrol requests:
  "看看我的自选股", "帮我巡检自选股", "自选股研究线索" …

NOTE: This skill only matches "review watchlist" intent — NOT "add to watchlist".
"""
from __future__ import annotations

import re

from app.agents.chat_skills.base import (
    BaseSkill,
    SkillContext,
    SkillResult,
    _DISCLAIMER,
)
from app.agents.chat_events import safe_emit

_PATTERN = re.compile(
    r"看看.{0,4}自选|巡检.{0,4}自选|自选.{0,6}研究线索|帮我.{0,4}自选|自选股.*哪些",
    re.IGNORECASE,
)


class WatchlistReviewSkill(BaseSkill):
    name = "watchlist_review_skill"
    description = "巡检自选股列表，逐只拉取行情，整理研究线索"
    intent_examples = [
        "看看我的自选股",
        "帮我巡检自选股",
        "自选股研究线索",
        "自选股有哪些",
    ]
    required_tools = ["get_watchlist_tool", "get_quote_tool"]
    safety_level = "read_only"
    priority = 20

    def can_handle(self, message: str, context: SkillContext) -> bool:
        return bool(_PATTERN.search(message))

    async def run(self, message: str, context: SkillContext) -> SkillResult:
        events: list = []
        cards: list = []

        await safe_emit(context.event_callback, "skill_started", {
            "skill_name": self.name,
            "skill_spec": self.name,
            "source": "skill_registry",
        })

        # 1. Fetch watchlist
        wl = await context.tool_registry.call(
            "get_watchlist_tool", context.db,
            event_callback=context.event_callback,
            user_id=context.user_id,
        )
        events.append(self._result_event(wl))
        if wl.ok:
            cards.extend(wl.cards)

        # Empty state
        if not wl.ok or not wl.data or wl.data.get("count", 0) == 0:
            answer = (
                "### 自选股巡检摘要\n\n"
                "你的自选股列表目前为空。\n\n"
                "可以说「把 688146 加入自选」来添加第一只股票，"
                "然后我可以帮你进行定期巡检和研究线索整理。"
                + _DISCLAIMER
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

        # 2. Fetch quotes for up to 5 stocks (avoid timeout)
        items = wl.data.get("items", [])[:5]
        research_lines: list[str] = []
        anomaly_lines: list[str] = []

        for stock in items:
            market = stock.get("market", "CN")
            symbol = stock.get("symbol", "")
            name = stock.get("name", symbol)
            if not symbol:
                continue

            quote = await context.tool_registry.call(
                "get_quote_tool", context.db,
                event_callback=context.event_callback,
                market=market, symbol=symbol, name=name,
            )
            events.append(self._result_event(quote))

            if quote.ok and quote.data:
                price = quote.data.get("price", "—")
                chg = quote.data.get("change_pct", "—")
                chg_dir = quote.data.get("change_dir", "flat")
                direction = "↑" if chg_dir == "up" else ("↓" if chg_dir == "down" else "→")
                line = f"- **{name}（{market}/{symbol}）** 当前价 {price}，涨跌 {direction}{chg}"
                # Flag significant movers as research hints
                research_lines.append(line)
                # Heuristic: flag large moves as potential research focus
                try:
                    pct_val = float(str(chg).replace("%", "").replace("+", ""))
                    if abs(pct_val) > 5:
                        anomaly_lines.append(
                            f"- **{name}（{symbol}）** 涨跌幅 {chg}，建议关注异动原因"
                        )
                except (ValueError, TypeError):
                    pass
            else:
                research_lines.append(
                    f"- **{name}（{market}/{symbol}）** 行情数据暂不可用"
                )

        total = wl.data.get("count", len(items))
        shown = min(5, len(items))
        truncated = total > shown

        answer = (
            f"### 自选股巡检摘要\n\n"
            f"共 **{total}** 只自选股"
            + (f"，本次巡检前 {shown} 只：" if truncated else "：")
            + "\n\n"
            + "\n".join(research_lines)
            + "\n\n### 需要关注的研究线索\n\n"
            + (
                "\n".join(anomaly_lines)
                if anomaly_lines
                else "- 目前各只股票涨跌幅在正常范围内，暂无特别异动需关注"
            )
            + "\n\n### 数据不足或异常\n\n"
            "- 以上数据仅为实时行情快照，不包含基本面与技术面深度分析\n"
            "- 如需深度研究某只股票，可输入「帮我生成综合报告」"
            + _DISCLAIMER
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
