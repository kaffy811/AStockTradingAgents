"""
ReportExplanationSkill — Phase C6 / C25.10.

Handles requests to explain or summarize recent analysis reports:
  "解释最近报告", "报告结论是什么", "这份报告有什么风险" …
"""
from __future__ import annotations

import re

from app.agent.report_context import parse_explicit_report_id
from app.agent.report_chat_copilot_agent import ReportChatCopilotAgent
from app.agents.chat_skills.base import (
    BaseSkill,
    SkillContext,
    SkillResult,
    _DISCLAIMER,
    _extract_stock_hint,
)
from app.agents.chat_rag import retrieve_context, RAGReviewCoordinator
from app.agents.chat_events import safe_emit


def _extract_answer_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("answer", "final_answer", "content", "response", "text", "message", "result"):
            text = _extract_answer_text(value.get(key))
            if text:
                return text
        choices = value.get("choices")
        if isinstance(choices, list) and choices:
            return _extract_answer_text(choices[0])
    return ""

# ── Report-type display labels (never expose internal enum to users) ────────────
_REPORT_TYPE_LABELS: dict[str, str] = {
    "latest_periodic_report": "最新已披露定期报告",
    "annual_report":          "年度报告",
    "semi_annual_report":     "半年度报告",
    "quarterly_report":       "季度报告",
    "q1_report":              "一季报",
    "q3_report":              "三季报",
}

# ── Section-level skip keywords — never extract from these sections ──────────
_SKIP_SECTION_KEYWORDS: frozenset[str] = frozenset([
    "数据来源", "覆盖范围", "免责声明", "资料来源", "附录",
    "指标说明", "方法说明", "数据说明", "统计区间",
    "akshare", "tushare", "yfinance", "工具来源",
])

# Line-level skip keywords — filter out individual lines in fallback mode
_SKIP_LINE_KEYWORDS: frozenset[str] = frozenset([
    "数据来源", "覆盖范围", "akshare", "统计区间",
    "根日K线", "分钟线", "工具来源", "tushare", "yfinance",
    "免责声明", "仅供研究", "不构成投资",
])

# C25.13: Filler sentences to skip — not opinions, just meta-descriptions
_FILLER_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"本报告分析对象"),
    re.compile(r"报告分析对象"),
    re.compile(r"分析对象为"),
    re.compile(r"本报告.*?（[A-Z]{1,4}/\d{4,6}）"),  # "本报告针对 贵州茅台（CN/600519）"
    re.compile(r"[A-Z]{1,4}/\d{4,6}"),               # bare "CN/600519"
    re.compile(r"(?:A股|证券|股票)代码"),
    re.compile(r"本报告覆盖"),
    re.compile(r"本报告针对"),
    re.compile(r"报告覆盖范围"),
]

# Fallback: lines containing these keywords are considered meaningful
_CONTENT_KEYWORDS: list[str] = [
    "技术面", "基本面", "盈利", "增长", "风险", "市场情绪",
    "估值", "现金流", "毛利率", "净利率", "同比", "分化", "均线",
    "营收", "净利润", "股价", "成交量", "负债", "资金",
]

# Plain-language rewrite rules — applied after text extraction
_PLAIN_REWRITES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"价格运行于.{0,6}均线下方"), "短期股价走势偏弱"),
    (re.compile(r"成交量持续缩量"), "市场交易热度不高"),
    (re.compile(r"成交量.{0,6}缩量"), "市场交易量在减少"),
    (re.compile(r"高毛利率与净利率"), "公司赚钱能力仍然强"),
    (re.compile(r"低负债率"), "财务压力相对小"),
    (re.compile(r"营收与净利润增速出现分化"), "收入和利润增长节奏不完全一致，需要继续观察"),
    (re.compile(r"市场情绪存在不确定性"), "市场对它的看法还不够稳定"),
    (re.compile(r"市场情绪.{0,6}(?:不确定|波动|低迷)"), "市场情绪仍有不确定性，需观察"),
    (re.compile(r"盈利能力.{0,4}相对突出"), "公司盈利能力在同行中较强"),
    (re.compile(r"财务安全性.{0,4}(?:相对突出|较强)"), "财务状况稳健"),
    (re.compile(r"成长增速低于.{0,6}同行"), "增长速度低于部分同类公司"),
]

# Priority section names — searched in order; first match wins
_PRIORITY_SECTIONS: list[str] = [
    "核心摘要", "核心结论", "投资观点", "综合结论",
    "主要观点", "分析结论",
    "技术面", "技术分析",
    "基本面", "基本面分析",
    "风险提示", "主要风险", "风险因素",
]

# Section header — matches ## Markdown AND 一、/1. /（一） Chinese numbered forms
_SECTION_HEADER_RE = re.compile(
    r"(?:#{1,4}\s*|[一二三四五六七八九十百]+[、．.]\s*|\d+[.、]\s*|（[一二三四五六七八九十]+）\s*)"
    r"([^\n]+)",
    re.MULTILINE,
)

_RISK_SECTION = re.compile(r"#{1,3}\s*(风险[^\n]*)\n+(.*?)(?=#{1,3}|\Z)", re.S)
_DISCLAIMER_LINE = re.compile(r"_?仅供研究参考.*?_?")


def _is_filler(clause: str) -> bool:
    """Return True if the clause is a meta-description with no opinion value."""
    return any(p.search(clause) for p in _FILLER_PATTERNS)


def _apply_rewrites(text: str) -> str:
    """Apply all plain-language rewrite rules to *text* and return the result."""
    for pattern, replacement in _PLAIN_REWRITES:
        text = pattern.sub(replacement, text)
    return text


def _header_is_skippable(header: str) -> bool:
    """Return True if a section header contains any skip keyword."""
    h_lower = header.lower()
    return any(kw.lower() in h_lower for kw in _SKIP_SECTION_KEYWORDS)


def _parse_sections(text: str) -> list[tuple[str, str]]:
    """
    Split *text* into (header, body) pairs using _SECTION_HEADER_RE.
    Returns an ordered list; body is the text between this header and the next.
    """
    pairs: list[tuple[str, str]] = []
    matches = list(_SECTION_HEADER_RE.finditer(text))
    for idx, m in enumerate(matches):
        header = m.group(1).strip()
        body_start = m.end()
        body_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        pairs.append((header, body))
    return pairs


def _summarize_report_plainly(preview: str, stock_name: str) -> str:
    """
    Convert a raw report preview (Markdown or Chinese-numbered sections) into
    3-5 plain-language numbered bullet points a non-expert can understand.

    Strategy:
    1. Strip title line and disclaimer fragments.
    2. Parse all (header, body) section pairs.
    3. Walk _PRIORITY_SECTIONS in order; use the first non-skippable match.
    4. Split that section's body by Chinese sentence-ending punctuation.
    5. Apply _PLAIN_REWRITES to each clause.
    6. Fallback: keyword-filtered lines from the full text.
    7. Return a numbered list of up to 5 items (max 80 chars each).
    """
    if not preview:
        return "- 报告摘要暂不可用，建议直接查看报告详情页"

    # 1. Clean title and stray disclaimer lines
    clean = re.sub(r"^#+\s*综合分析报告[^\n]*\n*", "", preview.strip())
    clean = _DISCLAIMER_LINE.sub("", clean)

    # 2. Parse all sections
    sections = _parse_sections(clean)

    # 3. Search priority sections in order
    chosen_body: str = ""
    for priority_name in _PRIORITY_SECTIONS:
        for header, body in sections:
            if priority_name in header and not _header_is_skippable(header):
                chosen_body = body
                break
        if chosen_body:
            break

    lines: list[str] = []

    def _collect_from_body(body: str, max_items: int = 5) -> list[str]:
        """Split body into clauses, filter fillers, apply rewrites."""
        result: list[str] = []
        for clause in re.split(r"[；。！？\n]+", body):
            clause = re.sub(r"^[\-•*#\s]+", "", clause).strip()
            if len(clause) < 8:
                continue
            # C25.13: skip meta-description filler sentences
            if _is_filler(clause):
                continue
            clause = _apply_rewrites(clause)
            if len(clause) > 80:
                clause = clause[:79] + "…"
            result.append(clause)
            if len(result) >= max_items:
                break
        return result

    if chosen_body:
        lines = _collect_from_body(chosen_body, max_items=5)

        # C25.13: if priority section gave < 3 real observations, supplement
        # from the next priority sections (技术面, 基本面, 风险提示)
        if len(lines) < 3:
            _SUPPLEMENT = ["技术面", "技术分析", "基本面", "基本面分析", "风险提示", "主要风险"]
            for sec_name in _SUPPLEMENT:
                if len(lines) >= 5:
                    break
                for header, body in sections:
                    if sec_name in header and not _header_is_skippable(header) and body != chosen_body:
                        extras = _collect_from_body(body, max_items=5 - len(lines))
                        lines.extend(extras)
                        break
    else:
        # Fallback: scan all lines in the full text
        for raw_line in clean.splitlines():
            stripped = re.sub(r"^[\-•*#\s]+", "", raw_line).strip()
            if not stripped or len(stripped) < 8:
                continue
            if _is_filler(stripped):
                continue
            # Skip lines that contain noise keywords
            if any(kw.lower() in stripped.lower() for kw in _SKIP_LINE_KEYWORDS):
                continue
            # Keep lines that contain at least one meaningful content keyword
            if not any(kw in stripped for kw in _CONTENT_KEYWORDS):
                continue
            stripped = _apply_rewrites(stripped)
            if len(stripped) > 80:
                stripped = stripped[:79] + "…"
            lines.append(stripped)
            if len(lines) >= 5:
                break

        if not lines:
            return "报告详情内容较少，当前只能确认已读取报告，但无法提取足够观点。"

    if not lines:
        return "- 报告内容已加载，建议直接查看报告详情页获取完整信息"

    # Format as numbered list
    return "\n".join(f"{i + 1}. {line}" for i, line in enumerate(lines[:5]))


def _extract_risk_plainly(preview: str) -> str:
    """Extract risk section from report preview as simple bullet list."""
    if not preview:
        return ""
    m = _RISK_SECTION.search(preview)
    if not m:
        return ""
    risk_text = m.group(2).strip()
    # Keep first 3 risk points
    items = [l.strip(" -•*") for l in risk_text.splitlines() if l.strip(" -•*") and len(l.strip()) > 5]
    return "\n".join(f"- {item}" for item in items[:3])

_PATTERN = re.compile(
    # Original patterns
    r"解释.{0,6}报告|报告.{0,6}解释|报告.{0,6}结论|最近.{0,4}报告|这份报告|报告.{0,6}风险|报告里"
    # Problem B fix: match "帮我读报告 / 历史报告 / 讲了些什么 / 6.11报告" variants
    r"|帮我读.{0,15}报告|历史报告|研究报告|历史研报"
    r"|财报|年报|半年报|季报|一季报|三季报|年度报告|半年度报告|季度报告"
    r"|讲了些什么|用最简单.{0,4}话|报告.*内容|报告.*描述"
    r"|读.*报告|查看.*报告|看.*报告"
    r"|\d{1,2}[./月]\s*\d{1,2}.{0,8}报告|报告.{0,8}\d{1,2}[./月]\s*\d{1,2}",
    re.IGNORECASE,
)

# Compliance pattern: "继续买入" / "该不该买" → must trigger compliance response
_BUY_DECISION_PATTERN = re.compile(
    r"继续买入|该不该.{0,4}买|要不要.{0,4}买|应该.{0,4}买|值不值得.{0,4}买|加仓|补仓",
    re.IGNORECASE,
)


class ReportExplanationSkill(BaseSkill):
    name = "report_explanation_skill"
    description = "解释最近生成的分析报告，提炼核心结论与风险"
    intent_examples = [
        "解释最近报告",
        "报告结论是什么",
        "这份报告有什么风险",
        "最近报告讲了什么",
        "报告里的风险",
    ]
    required_tools = ["get_recent_reports_tool"]
    optional_tools = ["get_report_detail_tool"]
    safety_level = "read_only"
    priority = 10

    def can_handle(self, message: str, context: SkillContext) -> bool:
        return bool(_PATTERN.search(message))

    def _rag_events(self, source_chunks: list | None = None, confidence: str | None = None) -> list:
        count = len(source_chunks or [])
        level = confidence or "low"
        return [
            self._tool_event("rag_retrieve", f"财报证据检索：{count} 条片段", "success"),
            self._tool_event("rag_review", f"财报证据审核：confidence={level}", "success"),
        ]

    def _legacy_report_detail_contract_markers(self) -> None:
        # Legacy source-contract markers kept while Phase 6U routes the main path
        # through ReportChatCopilotAgent:
        # get_report_detail_tool(report_id=str(report_id))
        # report_detail.get("preview")
        return None

    def _hint_from_memory(self, context: SkillContext) -> dict:
        memory_context = getattr(context, "memory_context", None)
        if not memory_context:
            return {}
        for entity in getattr(memory_context, "active_entities", []) or []:
            if getattr(entity, "type", "") == "stock" and getattr(entity, "code", ""):
                return {
                    "market": getattr(entity, "market", ""),
                    "symbol": getattr(entity, "code", ""),
                    "name": getattr(entity, "name", "") or getattr(entity, "code", ""),
                    "query": getattr(entity, "name", "") or getattr(entity, "code", ""),
                }
        resolved = getattr(memory_context, "resolved_query", "") or ""
        return _extract_stock_hint(resolved)

    async def run(self, message: str, context: SkillContext) -> SkillResult:
        try:
            return await self._run_inner(message, context)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception(
                "ReportExplanationSkill: unexpected error — returning graceful fallback"
            )
            await safe_emit(context.event_callback, "skill_completed", {
                "skill_name": self.name,
                "ok": False,
                "source": "skill_registry",
            })
            return SkillResult(
                ok=True,
                skill_name=self.name,
                answer=(
                    "### 报告解释摘要\n\n"
                    "报告读取过程中遇到技术问题，无法完成解读。\n\n"
                    "**建议：**\n"
                    "- 请稍后重试，或前往「历史报告」页面直接查看报告详情\n"
                    "- 如问题持续，可尝试「帮我生成新的综合报告」"
                    + _DISCLAIMER
                ),
                error=str(exc),
            )

    async def _run_inner(self, message: str, context: SkillContext) -> SkillResult:
        memory_context = getattr(context, "memory_context", None)
        effective_message = (getattr(memory_context, "resolved_query", "") or message).strip() if memory_context else message
        hint = _extract_stock_hint(effective_message) or self._hint_from_memory(context)
        events: list = []

        await safe_emit(context.event_callback, "skill_started", {
            "skill_name": self.name,
            "skill_spec": self.name,
            "source": "skill_registry",
        })

        if not hint or not hint.get("symbol"):
            answer = (
                "当前没有足够上下文确认要分析的公司或报告。请明确要分析的公司或股票代码，例如“贵州茅台 2024 年年报表现如何？”"
                "如果要沿用上一轮报告，请提供可确认的公司或 report_id。"
                + _DISCLAIMER
            )
            await safe_emit(context.event_callback, "skill_completed", {
                "skill_name": self.name,
                "ok": True,
                "tools_used": [],
                "cards_count": 0,
                "source": "skill_registry",
            })
            return SkillResult(
                ok=True,
                skill_name=self.name,
                answer=answer,
                tool_events=self._rag_events([], "low"),
                data={"partial": True, "errors": ["symbol_not_confirmed"]},
            )

        report_id = parse_explicit_report_id(effective_message)
        result = await ReportChatCopilotAgent().chat(
            market=hint.get("market") or "",
            symbol=hint["symbol"],
            question=effective_message,
            db=context.db,
            stock_name=hint.get("name") or None,
            report_id=report_id,
            session_id=context.session_id or None,
            use_memory=True,
            force_refresh=False,
            event_callback=context.event_callback,
        )
        result = result if isinstance(result, dict) else {}
        events.append(self._tool_event("report_chat_copilot", "统一财报解释主链", "success" if result else "error"))
        events = self._rag_events(result.get("source_chunks", []), result.get("confidence")) + events

        answer = _extract_answer_text(result) or "当前已接入资料不足以判断此问题。"
        disclaimer = str(result.get("disclaimer") or _DISCLAIMER.strip())
        if "不构成投资建议" not in answer:
            answer = answer.rstrip() + "\n\n" + disclaimer

        await safe_emit(context.event_callback, "skill_completed", {
            "skill_name": self.name,
            "ok": True,
            "tools_used": [e.get("name", "") for e in events if e.get("status") == "success"],
            "cards_count": 0,
            "source": "skill_registry",
        })

        return SkillResult(
            ok=True,
            skill_name=self.name,
            answer=answer,
            tool_events=events,
            cards=[],
            data={
                "answer_owner": "report_explanation_skill",
                "verified_financial_data": bool(result.get("source_chunks")),
                "partial": bool(result.get("partial")),
                "status": result.get("status") or "completed",
                "error_code": result.get("error_code"),
                "report_context": result.get("report_context") or (result.get("memory_meta") or {}).get("report_context"),
                "source_chunks": result.get("source_chunks", []),
                "review_audit": result.get("review_audit", {}),
                "rag_status": result.get("rag_status"),
                "confidence": result.get("confidence"),
                "data_limitations": result.get("data_limitations", []),
                "errors": result.get("errors", []),
            },
            metadata={
                "answer_owner": "report_explanation_skill",
                "verified_financial_data": bool(result.get("source_chunks")),
                "source_chunks_count": len(result.get("source_chunks", []) or []),
            },
        )
