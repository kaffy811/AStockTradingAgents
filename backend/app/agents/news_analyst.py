"""
NewsAnalystAgent — 新闻面分析师。

调用链路：
  analyze(market, symbol, hours_back, limit)
    → news_data_service.get_stock_news()   # 获取新闻快照（含缓存、降级）
    → _build_user_prompt()                  # 将新闻列表组装为结构化文本
    → BaseLLMClient.chat()                  # 调用 LLM 生成报告
    → 返回 Markdown 新闻面分析报告 (str)

设计原则：
  - 只分析 news items 中存在的新闻，不推断、不编造。
  - items=[] 时生成"暂无相关新闻数据"报告，不报错、不崩溃。
  - data_quality.message 注入 prompt，LLM 须据此说明数据质量。
  - HK keyword search 时报告须注明相关性可能较弱。
  - 不给确定性投资建议。
  - 输出为标准 Markdown，章节结构固定。
"""

from __future__ import annotations

import logging
import re

from app.llm.base import BaseLLMClient
from app.services.news_data_service import news_data_service
from app.agents.language_utils import build_output_language_instruction
from app.agents.specialist_analysis_utils import (
    build_boundary_instruction,
    detect_focus,
    sanitize_specialist_output,
)

log = logging.getLogger(__name__)

# prompt 层每条 summary 最大字符数
_PROMPT_SUMMARY_MAX = 300
# 传入 prompt 的最大新闻条数
_PROMPT_NEWS_MAX = 10

# ── System Prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
你是一位专业的股票新闻面分析师，负责基于用户提供的新闻标题、摘要、来源和发布时间，\
生成审慎、中性的新闻面分析报告。

【数据边界 — 严格执行】
1. 只能基于输入的 news items 分析，不得编造新闻标题、新闻内容、来源、发布时间。
2. 不得引用输入中不存在的新闻。若某条新闻未出现在输入列表中，不得提及。
3. 不得自行搜索或推断外部新闻。
4. items 为空（count=0）时，必须明确说明"暂无相关新闻数据"，不得假设或补充任何新闻。
5. summary 较短（低于 50 字）时，必须说明新闻内容有限，不能过度解读摘要片段。
6. 如果 data_quality.message 包含 "keyword search"，必须在报告中注明：
   "港股新闻通过关键词搜索获取，结果相关性可能较弱，分析结论需谨慎参考。"

【合规限制 — 严格执行】
1. 不得给出买入/卖出/持有建议。
   严禁使用：必涨、必跌、稳赚、强烈买入、强烈卖出、满仓、梭哈、保证收益、
   确定性机会、抄底、逃顶、一定利好、一定利空等表达。
2. 不得预测具体涨跌幅或目标价。
3. 不得说"该新闻一定利好/利空"，只能说"可能影响市场情绪"。
4. 只能使用中性表达：
   - 可能影响市场情绪
   - 需要继续观察
   - 对短期关注度可能有影响
   - 仍需结合价格、成交量和基本面判断
   - 事件发展方向尚不明确

【输出格式】
宽问题使用以下二级标题：
## 结论摘要
## 新闻范围
## 主要新闻主题
## 已确认事实
## 可能影响方向
## 潜在风险
## 后续观察
## 数据限制与来源

窄问题只输出相关章节，例如只问监管新闻时仅输出：
## 结论摘要
## 新闻范围
## 已确认事实
## 后续观察
## 数据限制与来源

每个结论段落需体现 observed_facts / analysis / limitations / watch_items 四层边界。
标题不能自动升级为已确认事实；只有公告/监管披露原文或明确来源时才写为已确认事实。
可能影响必须使用概率性语言，不得写确定性利好/利空。

## 数据限制与来源
仅供研究参考，不构成投资建议。新闻面分析仅反映特定时间窗口内的信息，\
市场存在不确定性，新闻解读存在主观局限，投资者需自行判断并承担投资风险。\
"""


# ── User Prompt 构建 ──────────────────────────────────────────────────────────

def _source_category(item: dict) -> str:
    text = f"{item.get('source') or ''} {item.get('title') or ''}".lower()
    if re.search(r"公告|披露|交易所|证监|监管|问询|处罚", text):
        return "公司公告/监管披露"
    if re.search(r"评论|观点|研报|分析师|市场", text):
        return "市场评论"
    return "正规媒体报道" if item.get("source") else "来源缺失，可信度降低"


def _dedupe_news_items(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for item in items:
        title = re.sub(r"\s+", "", (item.get("title") or "").lower())
        summary = re.sub(r"\s+", "", (item.get("summary") or "").lower())[:80]
        key = title or summary
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        out.append(item)
    return out

def _build_user_prompt(
    market:          str,
    symbol:          str,
    hours_back:      int,
    limit:           int,
    snapshot:        dict,
    output_language: str = "zh-CN",
    question:        str | None = None,
) -> str:
    """
    将 NewsDataService 返回的快照组装为结构化 user prompt。

    传入 prompt 的新闻条数上限 _PROMPT_NEWS_MAX=10，summary 截断至 _PROMPT_SUMMARY_MAX=300 字。
    """
    dq      = snapshot.get("data_quality", {})
    items   = _dedupe_news_items(snapshot.get("items", []) or [])
    count   = snapshot.get("count", 0)
    deduped_count = len(items)
    provider = dq.get("provider") or "unknown"
    cached   = dq.get("cached", False)
    dq_msg   = dq.get("message") or "无"

    # 新闻列表组装
    news_for_prompt = items[:_PROMPT_NEWS_MAX]
    if news_for_prompt:
        news_lines: list[str] = []
        for i, item in enumerate(news_for_prompt, 1):
            summary_raw = item.get("summary") or ""
            summary = summary_raw[:_PROMPT_SUMMARY_MAX]
            if len(summary_raw) > _PROMPT_SUMMARY_MAX:
                summary += "…（摘要已截断）"
            news_lines.append(
                f"[新闻 {i}]\n"
                f"  标题：{item.get('title', '')}\n"
                f"  摘要：{summary or '（无摘要）'}\n"
                f"  来源：{item.get('source') or '未知'}\n"
                f"  来源类型：{_source_category(item)}\n"
                f"  发布时间：{item.get('publish_time') or '未知'}\n"
                f"  链接：{item.get('url') or '无'}"
            )
        news_block = "\n\n".join(news_lines)
        news_section = (
            f"以下为原始 {count} 条新闻去重后的前 {len(news_for_prompt)} 条（去重后 {deduped_count} 条，按时间倒序）：\n\n"
            + news_block
        )
    else:
        news_section = "当前时间窗口内无可用新闻数据（items 为空）。"

    lang_instruction = build_output_language_instruction(output_language)
    focus = detect_focus(question)
    boundary_instruction = build_boundary_instruction(focus)

    return f"""\
请基于以下新闻数据，生成 {market}/{symbol} 的新闻面分析报告。
{boundary_instruction}

【用户问题与范围】
  question: {question or "未提供，按宽问题处理"}
  focus: {focus}

【分析参数】
  市场: {market}
  代码: {symbol}
  时间窗口: 最近 {hours_back} 小时
  请求上限: {limit} 条
  实际返回: {count} 条
  去重后: {deduped_count} 条

【数据质量】
  provider : {provider}
  cached   : {cached}
  message  : {dq_msg}

【新闻列表】
{news_section}

---
以上为全部可用新闻数据，请严格基于以上内容分析，不得引用未列出的新闻。\
请严格按 system prompt 规定的 Markdown 报告结构输出，标题名称不得更改。\
{lang_instruction}"""


# ── Agent ─────────────────────────────────────────────────────────────────────

class NewsAnalystAgent:
    """
    新闻面分析 Agent MVP。

    不依赖 LangGraph，直接调用 NewsDataService 获取新闻快照，
    再调用 LLM 生成 Markdown 新闻面分析报告。

    Args:
        llm: 实现了 BaseLLMClient.chat() 的 LLM 客户端。
    """

    def __init__(self, llm: BaseLLMClient) -> None:
        self._llm = llm

    def analyze(
        self,
        market:          str,
        symbol:          str,
        hours_back:      int = 72,
        limit:           int = 20,
        output_language: str = "zh-CN",
        question:        str | None = None,
    ) -> str:
        """
        生成新闻面分析报告。

        Args:
            market:     "CN" 或 "HK"（已大写）
            symbol:     股票代码（已 strip）
            hours_back: 分析最近 N 小时内的新闻
            limit:      最多使用的新闻条数

        Returns:
            Markdown 新闻面分析报告字符串。不会抛出异常。
        """
        market = market.upper()
        log.info("NewsAnalystAgent: start [%s/%s] hours_back=%d", market, symbol, hours_back)

        # ── Step 1: 获取新闻快照 ──────────────────────────────────────────
        try:
            snapshot = news_data_service.get_stock_news(
                market=market,
                symbol=symbol,
                hours_back=hours_back,
                limit=limit,
            )
        except Exception as exc:
            log.error("NewsAnalystAgent: news_data_service failed [%s/%s]: %s", market, symbol, exc)
            snapshot = {
                "market": market, "symbol": symbol,
                "items": [], "count": 0,
                "data_quality": {
                    "provider": None, "cached": False,
                    "message": "新闻数据获取异常：工具调用失败，不代表公司没有相关新闻数据。",
                },
            }

        log.info(
            "NewsAnalystAgent: news snapshot count=%d cached=%s [%s/%s]",
            snapshot.get("count", 0),
            snapshot.get("data_quality", {}).get("cached"),
            market, symbol,
        )

        # ── Step 2: 构建 User Prompt ─────────────────────────────────────
        user_prompt = _build_user_prompt(
            market, symbol, hours_back, limit, snapshot,
            output_language=output_language,
            question=question,
        )

        # ── Step 3: LLM 调用 ──────────────────────────────────────────────
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ]
        log.info("NewsAnalystAgent: calling LLM [%s/%s]", market, symbol)
        report = self._llm.chat(messages, temperature=0.3)
        report = sanitize_specialist_output(report, evidence_text=user_prompt)

        log.info(
            "NewsAnalystAgent: done [%s/%s] report_len=%d", market, symbol, len(report)
        )
        return report
