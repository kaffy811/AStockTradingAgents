"""
ReportExplanationSkill — Phase C6 / C25.10.

Handles requests to explain or summarize recent analysis reports:
  "解释最近报告", "报告结论是什么", "这份报告有什么风险" …
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

        # 1. Fetch recent reports
        reports = await context.tool_registry.call(
            "get_recent_reports_tool", context.db,
            event_callback=context.event_callback,
            user_id=context.user_id,
            market=hint.get("market", "CN") if hint else "CN",
            symbol=hint.get("symbol", "") if hint else "",
            limit=5,
        )
        events.append(self._result_event(reports))
        if reports.ok:
            cards.extend(reports.cards)

        # Extract date hint from message (e.g. "6.11" or "6月11日")
        _date_hint = ""
        _date_m = re.search(r"(\d{1,2})[./月]\s*(\d{1,2})", message)
        if _date_m:
            _date_hint = f"{_date_m.group(1)}月{_date_m.group(2)}日"

        # Compliance: if user asks about buy/sell decision, add disclaimer
        _has_buy_question = bool(_BUY_DECISION_PATTERN.search(message))

        # Empty state
        if not reports.ok or not reports.data or reports.data.get("count", 0) == 0:
            _no_report_msg = (
                f"当前未检索到{_date_hint + '关于' if _date_hint else ''}该股票的历史报告原文，"
                "因此无法准确概括报告内容。\n\n"
                "**建议：**\n"
                "- 请确认报告生成日期，或提供报告名称/来源\n"
                "- 可输入「帮我生成综合报告」生成新的分析报告"
                if _date_hint
                else "暂未找到历史报告。可以输入「帮我生成综合报告」来创建第一份分析报告。"
            )
            _buy_compliance = (
                "\n\n---\n"
                "**关于「继续买入」的问题：**\n"
                "我无法替您做买入/卖出决定。由于当前未检索到报告原文，缺乏关键基本面依据。"
                "建议您从以下条件自行评估：\n"
                "- 个人持仓成本与当前价格的差距\n"
                "- 投资周期（短线/长线）\n"
                "- 最新财报是否有业绩支撑\n"
                "- 行业景气度与竞争格局\n"
                "- 个人风险承受能力\n"
                if _has_buy_question
                else ""
            )
            answer = (
                "### 报告解释摘要\n\n"
                + _no_report_msg
                + _buy_compliance
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

        report_items = reports.data.get("items", [])
        first_report = report_items[0] if report_items else {}

        # 2. Optionally fetch detail for first report
        # ── Filter report_items by date hint and stock hint ──────────────────
        filtered_items = report_items
        if _date_hint:
            # e.g. _date_hint = "6月11日" → match "-06-11" in created_at
            _month_str = _date_m.group(1).zfill(2) if _date_m else ""
            _day_str   = _date_m.group(2).zfill(2) if _date_m else ""
            _date_substr = f"-{_month_str}-{_day_str}"
            date_filtered = [r for r in report_items if _date_substr in str(r.get("created_at", ""))]
            if date_filtered:
                filtered_items = date_filtered
        if hint and hint.get("symbol"):
            sym = hint["symbol"]
            sym_filtered = [r for r in filtered_items if r.get("symbol") == sym or r.get("stock_code") == sym]
            if sym_filtered:
                filtered_items = sym_filtered
        first_report = filtered_items[0] if filtered_items else (report_items[0] if report_items else {})

        # 2. Optionally fetch detail for first report
        report_detail: dict = {}
        report_id = first_report.get("id") or first_report.get("run_id")
        if report_id:
            detail = await context.tool_registry.call(
                "get_report_detail_tool", context.db,
                event_callback=context.event_callback,
                report_id=str(report_id),
                user_id=context.user_id,
            )
            events.append(self._result_event(detail))
            if detail.ok and detail.data:
                report_detail = detail.data

        # ── Build answer ──────────────────────────────────────────────────────
        stock_name = first_report.get("stock_name") or first_report.get("symbol") or first_report.get("name", "未知股票")
        report_date = str(first_report.get("created_at", ""))[:10]
        total_count = reports.data.get("count", len(report_items))

        # Extract and summarize report detail
        # GetReportDetailTool returns "preview" field (not "summary")
        raw_preview = ""
        detail_available = bool(report_detail)
        if report_detail:
            raw_preview = (
                report_detail.get("preview")
                or report_detail.get("summary")
                or report_detail.get("conclusion")
                or report_detail.get("report_summary")
                or ""
            )

        # Convert raw preview to plain-language summary (never paste raw Markdown)
        plain_summary = _summarize_report_plainly(raw_preview, stock_name)
        plain_risk    = _extract_risk_plainly(raw_preview)

        # Compliance block for buy/sell decision questions — more contextual
        _buy_compliance_found = (
            "\n\n---\n"
            "**关于「继续买入」的问题：**\n\n"
            "我无法替您做买入/卖出决定。根据这份报告，您可以从以下角度自行判断：\n\n"
            f"- **如果您是长期投资者**：重点看 {stock_name} 的盈利能力是否还能保持稳定，"
            "报告基本面章节有直接参考\n"
            f"- **如果您是短线投资者**：报告技术面章节指出了近期价格走势信号，"
            "不要仅凭品牌效应决策\n"
            "- **如果您已持仓**：结合您的成本价和仓位比例，避免单一个股占比过高\n"
            "- **如果您还没买**：建议先等最新财报和技术趋势更清晰后再评估\n"
            if _has_buy_question
            else ""
        )

        _detail_unavail = (
            "\n\n> ⚠️ 已找到报告记录，但报告详情读取失败，以下内容来自报告索引摘要。"
            if not detail_available else ""
        )

        answer = (
            f"### 报告解释摘要\n\n"
            f"找到 **{total_count}** 份历史报告"
            + (f"，其中符合您查询条件（{_date_hint}）的报告如下" if _date_hint else "，最新一份")
            + f"：\n"
            f"- 股票：**{stock_name}**\n"
            f"- 生成日期：{report_date}\n"
            + _detail_unavail
            + "\n\n### 这份报告用简单话讲了什么\n\n"
            + plain_summary
            + "\n\n### 主要风险与不确定性\n\n"
            + (
                plain_risk if plain_risk
                else "- 报告风险章节暂不可用，建议查看完整报告"
            )
            + "\n\n### 后续观察\n\n"
            "如需完整报告内容，可前往「历史报告」页面查看详情，"
            "或输入「帮我生成新的综合报告」获取最新分析。"
            + _buy_compliance_found
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
