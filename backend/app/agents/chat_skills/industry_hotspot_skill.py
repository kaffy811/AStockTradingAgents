"""
IndustryHotspotSkill — Phase C6.

Handles industry heat / sector spotlight questions:
  "行业热点", "哪些行业值得重点研究", "板块热度排行" …
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
    r"行业热点|哪些行业.{0,8}(值得|关注|研究)|板块热度|哪个行业.{0,4}热|行业.{0,4}热门",
    re.IGNORECASE,
)

# Regex to detect specific industry mention in message
_INDUSTRY_MENTION = re.compile(
    r"(电子|医药|银行|券商|能源|钢铁|汽车|半导体|消费|科技|军工|化工|食品|地产|建筑|电力|机械|传媒|农业|通信)",
    re.IGNORECASE,
)


class IndustryHotspotSkill(BaseSkill):
    name = "industry_hotspot_skill"
    description = "查询行业热度排行，整理板块研究线索"
    intent_examples = [
        "行业热点有哪些",
        "哪些行业值得重点研究",
        "板块热度排行",
        "哪个行业最热",
    ]
    required_tools = ["get_industry_hot_tool"]
    optional_tools = ["get_industry_stocks_tool"]
    safety_level = "read_only"
    priority = 30

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

        # 1. Industry hot list
        hot = await context.tool_registry.call(
            "get_industry_hot_tool", context.db,
            event_callback=context.event_callback,
            market="CN", limit=10,
        )
        events.append(self._result_event(hot))
        if hot.ok:
            cards.extend(hot.cards)

        if not hot.ok or not hot.data or not hot.data.get("items"):
            answer = (
                "### 行业热点摘要\n\n"
                "行业热度数据暂不可用，请稍后再试。"
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

        items = hot.data["items"]

        # 2. If message mentions a specific industry, optionally fetch its stocks
        specific_industry_stocks: list[dict] = []
        industry_match = _INDUSTRY_MENTION.search(message)
        if industry_match:
            industry_name = industry_match.group(1)
            # Try to find matching industry code
            matched = next(
                (it for it in items if industry_name in it.get("name", "")), None
            )
            if matched and matched.get("code"):
                ind_stocks = await context.tool_registry.call(
                    "get_industry_stocks_tool", context.db,
                    event_callback=context.event_callback,
                    industry_code=matched["code"],
                    market="CN", limit=5,
                )
                events.append(self._result_event(ind_stocks))
                if ind_stocks.ok and ind_stocks.data and ind_stocks.data.get("items"):
                    specific_industry_stocks = ind_stocks.data["items"]

        # ── Build answer ──────────────────────────────────────────────────────
        ranked_lines = []
        for i, it in enumerate(items[:8], 1):
            name = it.get("name", "未知行业")
            hot_score = it.get("hotScore", 0)
            chg = it.get("changePct", "N/A")
            ranked_lines.append(
                f"{i}. **{name}** — 热度 {hot_score:.2f}，涨跌 {chg}"
            )

        research_lines = [
            "- 热度排名较高的行业可作为研究线索，建议结合基本面深入分析",
            "- 如需查看特定行业个股，可说「查看电子行业热门股票」",
            "- 如需个股深度报告，可输入「帮我生成 XXX 综合报告」",
        ]

        answer = (
            "### 行业热点摘要\n\n"
            "以下为当前申万行业热度排行（基于成交额 × 涨跌幅综合评分）：\n\n"
            "### 热门行业\n\n"
            + "\n".join(ranked_lines)
            + (
                f"\n\n**{industry_match.group(1)} 行业代表个股：**\n"
                + "\n".join(
                    f"- {s.get('name', s.get('symbol', ''))}（{s.get('symbol', '')}）"
                    for s in specific_industry_stocks
                )
                if specific_industry_stocks else ""
            )
            + "\n\n### 研究线索\n\n"
            + "\n".join(research_lines)
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
