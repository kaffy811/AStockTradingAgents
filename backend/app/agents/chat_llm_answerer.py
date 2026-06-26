"""
Chat LLM Answerer — Phase C14.

DeepSeek-backed answer synthesis for Chat Copilot.
Takes user question + tool results + RAG documents → structured financial research answer.

Never raises to callers — returns a safe fallback string on any LLM failure.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

log = logging.getLogger(__name__)

_DISCLAIMER = "\n\n_仅供研究参考，不构成投资建议。_"

_BANNED_PHRASES: list[tuple[str, str]] = [
    ("买入", "关注"),
    ("卖出", "观察"),
    ("做多", "看涨研究"),
    ("做空", "看跌研究"),
    ("抄底", "低位研究"),
    ("目标价", "参考价区间"),
    ("稳赚", "有参考价值"),
    ("必涨", "存在上行研究线索"),
    ("追涨", "跟踪研究"),
    ("下单", "操作"),
    # Problem C: strip fabricated valuation patterns
    ("基于2024年利润推测", "（估值需来自工具数据）"),
    ("基于.*年利润推测", "（估值需来自工具数据）"),
    ("历史中等水平", "（请通过工具获取最新估值）"),
    # Problem D: ban "假设为" / "推测为" financial completions
    ("假设为年报分红", "工具未提供完整公告依据，无法确认分配年度"),
    ("假设为年报", "工具数据未明确报告年度"),
    ("假设为", "工具未提供该数据依据"),
    ("推测为", "工具数据显示"),
    ("可能是某年财报", "工具未返回具体报告类型"),
    # Also block internal report type enum strings from appearing in output
    ("latest_periodic_report", "最新已披露定期报告"),
    ("annual_report", "年度报告"),
    ("semi_annual_report", "半年度报告"),
    ("quarterly_report", "季度报告"),
    # Problem E: ban unconfirmed year-specific dividend claims from news titles
    # When news tool returns only headlines, the LLM must not add "20XX年度"
    ("2024年度分红", "近期实施分红（工具上下文未提供完整公告原文，无法确认分配年度）"),
    ("2023年度分红", "近期实施分红（工具上下文未提供完整公告原文，无法确认分配年度）"),
    ("2025年度分红", "近期实施分红（工具上下文未提供完整公告原文，无法确认分配年度）"),
    # Problem F: ban self-computed financial ratios — all ratios must come from tool fields
    ("对应约", "（工具未返回该比率字段，不自行计算）"),
    ("按当前价粗算", "（工具未返回股息率字段，不自行计算）"),
    ("粗算", "（工具未提供计算依据）"),
    ("股息率约", "（工具未返回股息率字段）"),
    ("派息率约", "（工具未返回派息率字段）"),
    ("分红率约", "（工具未返回分红率字段）"),
    ("简单计算", "（工具未提供计算依据）"),
    # Problem G: ban unconfirmed news list membership
    ("贵州茅台在列", "（工具上下文未提供完整名单，不能确认该股票是否在列）"),
    ("在该分红名单", "（工具上下文未提供完整名单正文）"),
    ("在名单中", "（工具上下文未提供完整名单正文，无法确认）"),
]

_SYSTEM_PROMPT = """你是 TradingAgents 金融研究助理，专注于 A 股和港股的数据解读与研究辅助。

核心原则：
1. 你只提供研究性观察，绝不给出投资建议或交易指令
2. 你不预测股价走势、不提供目标价
3. 数据来自实时 API，有延迟，仅供研究参考
4. 对数据缺失、不确定性保持透明
5. 【严禁编造财务数字】严禁根据训练知识推测或自行输出具体财务/估值数字，包括：
   市盈率（PE）、市净率（PB）、营收、净利润、增速、股息率、估值区间、目标价格。
   上述数字只能来自工具调用结果或参考资料。若工具和参考资料均未提供，
   必须说明"当前缺少财报/估值数据，无法给出具体数字"，
   禁止用"约X倍""基于推测""历史均值"等形式输出估计值。
6. 【历史报告缺失处理】若用户询问某份历史报告内容，但工具/参考资料中未检索到原文，
   必须明确说明"未检索到该报告原文，无法准确概括其内容"，不得用通用知识替代作答。
7. 【买入决策合规】对"继续买入""该不该买""是否加仓"类问题，
   必须以"我无法替您做买入/卖出决定"开头，然后列出用户可以自行评估的客观条件，
   不能给出任何倾向性的操作建议。
8. 【分红年度合规】若工具返回新闻标题中含分红信息但未含完整公告原文或明确年份字段，
   禁止补充"XXXX年度分红"等年份推断，应说明：
   "近期分红信息来自新闻标题，工具未提供完整公告原文，无法确认分配年度。"
9. 【严禁自行计算财务比率】若工具返回分红金额但未返回股息率字段，禁止自行计算股息率、
   派息率、分红率等比率。禁止使用"约X%的股息率""按当前价粗算""简单计算"等表述。
   正确做法：说明"工具提供每10股派X元，但未返回股息率字段，无法给出具体比率。"
10. 【新闻名单处理】若新闻标题提到"X只股即将分红（名单）"，但工具未返回名单正文，
    不得推断"某股票在列"等具体股票是否入围的结论。
    正确做法："另有新闻提到多只股票即将分红，但工具未提供完整名单，无法确认具体包含哪些股票。"

回答结构（必须遵守）：
### 研究摘要
[核心发现，2-3句]

### 关键依据
[基于工具数据的具体观察，逐条列出]

### 风险与不确定性
[已知数据缺口或需要进一步观察的点]

### 后续观察
[建议用户可以进一步探索的研究方向]

### 资料来源与可信度
[列出使用的数据来源及可信度评估]

严禁出现：买入、卖出、做多、做空、抄底、目标价、稳赚、必涨、追涨"""

_LANG_MAP: dict[str, str] = {
    "zh-CN": "请用简体中文回答。",
    "zh-TW": "請用繁體中文回答。",
    "en-US": "Please answer in English.",
    "ja-JP": "日本語で回答してください。",
    "ko-KR": "한국어로 답변해 주세요。",
    "es-ES": "Por favor responde en español.",
}


def _build_tool_summary(tool_results: list[dict]) -> str:
    if not tool_results:
        return "（无工具数据）"
    lines: list[str] = []
    for t in tool_results[:10]:
        name   = t.get("name", t.get("tool_name", "unknown"))
        status = t.get("status", "unknown")
        detail = t.get("detail", t.get("summary", ""))[:200]
        lines.append(f"- {name}: {status} — {detail}")
    return "\n".join(lines)


def _build_rag_summary(rag_documents: list[dict]) -> str:
    if not rag_documents:
        return "（无参考资料）"
    lines: list[str] = []
    for doc in rag_documents[:5]:
        source  = doc.get("source_type", "unknown")
        content = doc.get("content", doc.get("summary", ""))[:300]
        if content:
            lines.append(f"[{source}] {content}")
    return "\n\n".join(lines) or "（资料内容为空）"


def _filter_banned_phrases(text: str) -> str:
    for phrase, replacement in _BANNED_PHRASES:
        text = text.replace(phrase, replacement)
    return text


async def generate_answer(
    user_message: str,
    tool_results: list[dict],
    rag_documents: list[dict],
    output_language: str = "zh-CN",
    stock_context: dict | None = None,
    timeout_seconds: float = 30.0,
) -> str:
    """
    Generate a DeepSeek-backed financial research answer.

    Returns the answer string (always ends with _DISCLAIMER, never empty).
    Raises ValueError if DEEPSEEK_API_KEY is not set.
    Raises asyncio.TimeoutError if generation exceeds timeout_seconds.
    Raises RuntimeError on LLM API error or empty response.
    """
    from app.llm.factory import get_llm_client

    tool_summary = _build_tool_summary(tool_results)
    rag_summary  = _build_rag_summary(rag_documents)

    stock_ctx = ""
    if stock_context:
        name       = stock_context.get("name", "")
        market     = stock_context.get("market", "")
        symbol     = stock_context.get("symbol", "")
        price      = stock_context.get("price", "")
        change_pct = stock_context.get("change_pct", "")
        if name:
            stock_ctx = (
                f"\n标的：{name}（{market}/{symbol}），"
                f"当前价：{price}，涨跌幅：{change_pct}"
            )

    lang_instruction = _LANG_MAP.get(output_language, "请用简体中文回答。")

    user_prompt = (
        f"用户问题：{user_message}{stock_ctx}\n\n"
        f"工具调用结果：\n{tool_summary}\n\n"
        f"参考资料摘要：\n{rag_summary}\n\n"
        f"{lang_instruction}"
        "请基于以上数据生成研究报告，严格遵守系统提示中的回答结构和安全规则。"
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": user_prompt},
    ]

    llm = get_llm_client()

    def _call_llm() -> str:
        return llm.chat_flash(messages, temperature=0.3)

    answer = await asyncio.wait_for(
        asyncio.to_thread(_call_llm),
        timeout=timeout_seconds,
    )

    if not answer or not answer.strip():
        raise RuntimeError("DeepSeek returned an empty response")

    answer = _filter_banned_phrases(answer)
    if _DISCLAIMER.strip() not in answer:
        answer = answer + _DISCLAIMER
    return answer
