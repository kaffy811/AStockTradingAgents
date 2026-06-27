"""
orchestrator/synthesis_agent.py — Phase 2E-2: LLM Synthesis + Robust Fallback.

Changes from Phase 2E-1
-----------------------
* Full LLM synthesis via DeepSeek when llm_fn available.
  parse_synthesis_llm_output() handles raw JSON + Markdown JSON blocks.
* Source validation: URLs not present in EvidencePack are stripped.
* data_quality inherited from EvidencePack — LLM cannot remove warnings.
* Template-based synthesis preserved as CI-safe fallback.
* make_synthesis_llm_fn() exported for FinancialOrchestrator default wiring.

Design constraints
------------------
* ALWAYS includes disclaimer.
* ALWAYS applies required_edits from RiskReviewResult.
* NEVER outputs blocked responses (orchestrator guards this).
* data_quality.report_verified reflects FundamentalAgent finding.
* LLM cannot invent source URLs — only EvidencePack-sourced URLs pass.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Callable

from app.agents.orchestrator.schemas import (
    make_orchestrator_response,
    _DISCLAIMER,
)
from app.agents.financial_safety_postprocessor import sanitize_financial_answer

log = logging.getLogger(__name__)

AGENT_NAME      = "synthesis_agent"
TIMEOUT_SECONDS = 60.0

# ── Violation replacement table ────────────────────────────────────────────────
_REPLACEMENTS: list[tuple[str, str]] = [
    ("买入",     "关注"),
    ("卖出",     "观察"),
    ("做多",     "看涨研究"),
    ("做空",     "看跌研究"),
    ("持有",     "持续观察"),
    ("必涨",     "存在上行研究线索"),
    ("必跌",     "存在下行研究线索"),
    ("稳赚",     "具有参考价值"),
    ("目标价",   "参考价区间"),
    ("强烈推荐", "研究关注"),
    ("buy now",  "research focus"),
    ("strong buy", "positive research signal"),
]

# ── System prompt for LLM synthesis ──────────────────────────────────────────

_SYNTHESIS_SYSTEM_PROMPT = (
    "你是一个金融研究报告生成 Agent。"
    "你只能基于输入的 EvidencePack 生成结构化分析，不得编造财务数据、行情数据、新闻或来源。\n\n"
    "你必须遵守：\n"
    "1. 只能使用 EvidencePack 中已有证据。\n"
    "2. 不得编造财报、公告、新闻、行情数据。\n"
    "3. 如果某个子 Agent 状态为 failed 或 partial，"
    "必须在 data_quality 或 risk_points 中说明限制。\n"
    "4. 不得输出买入、卖出、持有建议。\n"
    "5. 不得使用[必涨][稳赚][确定上涨][保证收益]等表述。\n"
    "6. 必须包含免责声明：[仅供研究参考，不构成投资建议。]\n"
    "7. 必须输出 JSON，不要输出 Markdown 正文。\n"
    "8. JSON 必须包含：\n"
    "   summary, business_analysis, market_analysis, news_analysis,\n"
    "   linkage_analysis, data_points (array), risk_points (array),\n"
    "   sources (array of {title,source,url,published_at}),\n"
    "   data_quality (object), disclaimer (string)。\n"
    "9. sources 只允许包含 EvidencePack 中已有来源，禁止编造 URL。"
)


# ── Source safety helpers ──────────────────────────────────────────────────────

def _get_known_source_urls(evidence_pack: dict) -> set[str]:
    """Return all known source URLs found in EvidencePack."""
    urls: set[str] = set()
    for src in evidence_pack.get("sources", []):
        url = src.get("url", "")
        if url:
            urls.add(url)
    for finding in evidence_pack.get("findings", []):
        for src in finding.get("sources", []):
            url = src.get("url", "")
            if url:
                urls.add(url)
    return urls


def _filter_sources(llm_sources: list, evidence_pack: dict) -> list:
    """
    Strip LLM-invented URLs.  Only keep sources whose URL appears in
    EvidencePack, or sources that have no URL (title-only citations).

    If the result is empty, fall back to the raw EvidencePack sources.
    """
    known_urls = _get_known_source_urls(evidence_pack)
    ep_sources = evidence_pack.get("sources", [])

    filtered: list[dict] = []
    for src in (llm_sources or []):
        url = src.get("url", "")
        if not url:
            filtered.append(src)        # no URL → allow
        elif url in known_urls:
            filtered.append(src)        # known URL → allow
        # else: invented URL → silently drop

    return (filtered or ep_sources)[:15]


def _merge_data_quality(llm_dq: dict, ep_dq: dict) -> dict:
    """
    EvidencePack data_quality is the authoritative baseline.
    LLM may add new keys but cannot remove existing warnings or
    override boolean flags set by sub-agents.
    """
    merged = dict(ep_dq)
    for k, v in llm_dq.items():
        if k not in merged:
            merged[k] = v
        elif k == "warnings":
            ep_warnings  = set(ep_dq.get("warnings", []))
            llm_warnings = set(v) if isinstance(v, list) else set()
            merged["warnings"] = list(ep_warnings | llm_warnings)
        # All other existing keys preserved (report_verified, etc.)
    return merged


# ── LLM output parser ─────────────────────────────────────────────────────────

def parse_synthesis_llm_output(text: str, evidence_pack: dict) -> dict | None:
    """
    Parse LLM synthesis output into an OrchestratorResponse dict.

    Handles:
    - Raw JSON
    - Markdown ```json...``` blocks
    - Missing fields → safe defaults
    - Invented source URLs → filtered out
    - data_quality → merged with EvidencePack (warnings always preserved)
    - disclaimer → auto-restored if missing

    Returns None on total parse failure (triggers template fallback).
    """
    if not text or not text.strip():
        return None

    json_text = text.strip()

    # Strip Markdown code fence if present
    md_match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", json_text)
    if md_match:
        json_text = md_match.group(1).strip()

    # Try direct JSON parse
    data: dict | None = None
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError:
        # Try to extract first JSON object from messy output
        obj_match = re.search(r"\{[\s\S]*\}", json_text)
        if obj_match:
            try:
                data = json.loads(obj_match.group())
            except json.JSONDecodeError:
                pass

    if not isinstance(data, dict):
        return None

    ep_dq = evidence_pack.get("data_quality", {})

    disclaimer = data.get("disclaimer", "") or ""
    if "仅供研究参考" not in disclaimer and "不构成投资建议" not in disclaimer:
        disclaimer = _DISCLAIMER

    return {
        "summary":           data.get("summary", ""),
        "business_analysis": data.get("business_analysis", ""),
        "market_analysis":   data.get("market_analysis", ""),
        "news_analysis":     data.get("news_analysis", ""),
        "linkage_analysis":  data.get("linkage_analysis", ""),
        "data_points":       list(data.get("data_points", [])),
        "risk_points":       list(data.get("risk_points", [])),
        "sources":           _filter_sources(data.get("sources", []), evidence_pack),
        "data_quality":      _merge_data_quality(
                                 dict(data.get("data_quality", {})), ep_dq
                             ),
        "disclaimer":        disclaimer,
    }


# ── Default LLM function builder ──────────────────────────────────────────────

def make_synthesis_llm_fn() -> Callable | None:
    """
    Build an async callable suitable for SynthesisAgent(llm_fn=...) using
    the project's DeepSeek client.

    Returns None if DEEPSEEK_API_KEY is not configured (CI-safe).
    """
    try:
        from app.core.config import settings  # noqa: PLC0415
        from app.llm.factory import get_llm_client  # noqa: PLC0415

        if not settings.deepseek_api_key:
            return None

        def _llm_fn_sync(prompt: str) -> str:
            llm = get_llm_client()
            messages = [
                {"role": "system", "content": _SYNTHESIS_SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ]
            return llm.chat(messages, temperature=0.2)

        async def _llm_fn_async(prompt: str) -> str:
            return await asyncio.to_thread(_llm_fn_sync, prompt)

        return _llm_fn_async

    except Exception as exc:
        log.debug("make_synthesis_llm_fn: unavailable (%s)", exc)
        return None


# ── SynthesisAgent ────────────────────────────────────────────────────────────

class SynthesisAgent:
    """
    Synthesis agent — assembles structured final answer from evidence.

    Parameters
    ----------
    llm_fn : optional async callable(prompt: str) → str
             When provided (or auto-detected), used for full LLM synthesis.
             When None, template-based synthesis is used (CI-safe).
    """

    def __init__(self, llm_fn: Any = None) -> None:
        self._llm_fn = llm_fn

    async def run(
        self,
        evidence_pack: dict,
        risk_review: dict,
        *,
        event_callback: Callable | None = None,
    ) -> dict:
        """
        Generate OrchestratorResponse from EvidencePack + RiskReviewResult.
        Never raises; returns a safe fallback response on any error.
        """
        try:
            result = await self._synthesize(evidence_pack, risk_review, event_callback)
            return sanitize_financial_answer(result)  # C26
        except Exception as exc:
            log.error("SynthesisAgent: synthesis failed: %s", exc)
            return sanitize_financial_answer(make_orchestrator_response(  # C26
                summary="综合分析生成时发生内部错误，请稍后重试。",
                risk_points=["synthesis_error"],
                data_quality=evidence_pack.get("data_quality", {}),
                disclaimer=_DISCLAIMER,
            ))

    async def _synthesize(
        self,
        evidence_pack: dict,
        risk_review: dict,
        event_callback: Callable | None,
    ) -> dict:
        intent           = evidence_pack.get("intent", {})
        findings         = evidence_pack.get("findings", [])
        sources          = evidence_pack.get("sources", [])
        dq               = evidence_pack.get("data_quality", {})
        warnings         = evidence_pack.get("warnings", [])
        required_edits   = risk_review.get("required_edits", [])
        compliance_notes = risk_review.get("compliance_notes", [])
        query            = evidence_pack.get("query", "")
        symbol           = intent.get("symbol", "")
        company          = intent.get("company_name", "") or symbol

        # ── LLM synthesis (preferred path) ───────────────────────────────────
        if self._llm_fn:
            try:
                llm_result = await self._run_llm_synthesis(
                    evidence_pack, risk_review, company, query
                )
                if llm_result:
                    return _apply_edits_to_response(llm_result, required_edits)
            except Exception as exc:
                log.warning(
                    "SynthesisAgent: LLM synthesis failed (%s) — falling back to template",
                    exc,
                )

        # ── Template fallback ─────────────────────────────────────────────────
        return await self._template_synthesis(
            findings, sources, dq, warnings,
            required_edits, compliance_notes,
            query, company, risk_review,
        )

    async def _run_llm_synthesis(
        self,
        evidence_pack: dict,
        risk_review: dict,
        company: str,
        query: str,
    ) -> dict | None:
        """Call LLM and parse its JSON output.  Returns None on failure."""
        prompt = _build_synthesis_user_prompt(evidence_pack, risk_review, company, query)
        raw    = await self._llm_fn(prompt)
        if not raw:
            return None
        return parse_synthesis_llm_output(raw, evidence_pack)

    async def _template_synthesis(
        self,
        findings: list,
        sources: list,
        dq: dict,
        warnings: list,
        required_edits: list,
        compliance_notes: list,
        query: str,
        company: str,
        risk_review: dict,
    ) -> dict:
        """Template-based synthesis — Phase 2E-1 logic, preserved as fallback."""
        fund_finding   = _find_by_agent(findings, "fundamental_agent")
        market_finding = _find_by_agent(findings, "market_agent")
        news_finding   = _find_by_agent(findings, "news_agent")

        business_analysis = _build_business_analysis(fund_finding, company, dq, required_edits)
        market_analysis   = _build_market_analysis(market_finding, company)
        news_analysis     = _build_news_analysis(news_finding)
        linkage_analysis  = _build_linkage_analysis(fund_finding, market_finding, company)
        summary           = _build_summary(
            query, company, fund_finding, market_finding, news_finding, warnings
        )

        risk_points: list[str] = list(risk_review.get("issues", []))
        for finding in findings:
            for flag in finding.get("risk_flags", []):
                risk_points.append(_flag_to_text(flag))
        for note in compliance_notes:
            risk_points.append(note)
        risk_points = list(dict.fromkeys(p for p in risk_points if p))

        business_analysis = _apply_edits(business_analysis, required_edits)
        market_analysis   = _apply_edits(market_analysis,   required_edits)
        summary           = _apply_edits(summary,           required_edits)

        return make_orchestrator_response(
            summary=summary,
            business_analysis=business_analysis,
            market_analysis=market_analysis,
            news_analysis=news_analysis,
            linkage_analysis=linkage_analysis,
            risk_points=risk_points[:10],
            sources=sources[:15],
            data_quality=dq,
            disclaimer=_DISCLAIMER,
        )


# ── LLM prompt builder ────────────────────────────────────────────────────────

def _build_synthesis_user_prompt(
    evidence_pack: dict,
    risk_review: dict,
    company: str,
    query: str,
) -> str:
    """Build the user prompt string for LLM synthesis."""
    intent   = evidence_pack.get("intent", {})
    findings = evidence_pack.get("findings", [])
    sources  = evidence_pack.get("sources", [])
    dq       = evidence_pack.get("data_quality", {})
    warnings = evidence_pack.get("warnings", [])

    finding_blocks: list[str] = []
    for f in findings:
        name    = f.get("agent_name", "")
        status  = f.get("status", "")
        summary = f.get("summary", "")
        dp      = f.get("data_points", [])
        flags   = f.get("risk_flags", [])
        block   = f"[{name}] status={status}\n摘要: {summary}"
        if dp:
            block += "\n数据点: " + "; ".join(str(p) for p in dp[:5])
        if flags:
            block += "\n风险标志: " + ", ".join(flags)
        finding_blocks.append(block)

    sources_brief = [
        f"{s.get('title', '')} ({s.get('source', '')} {s.get('published_at', '')})"
        for s in sources[:8]
    ]
    compliance_notes = risk_review.get("compliance_notes", [])

    return (
        f"用户研究问题：{query}\n"
        f"分析标的：{company}（{intent.get('market', '')} {intent.get('symbol', '')}）\n\n"
        "== EvidencePack 子 Agent 研究结果 ==\n"
        + "\n\n".join(finding_blocks)
        + "\n\n== 已有数据来源 ==\n"
        + ("\n".join(sources_brief) or "（无来源）")
        + "\n\n== 数据质量状态 ==\n"
        + f"report_verified={dq.get('report_verified')}, "
        f"market_data_available={dq.get('market_data_available')}, "
        f"warnings={warnings}\n"
        + "\n== 合规要求 ==\n"
        + ("\n".join(compliance_notes) or "（无额外合规要求）")
        + "\n\n请基于以上 EvidencePack 生成 JSON 格式的结构化研究报告。"
        "严格遵守系统提示中的所有规则，sources 只能包含上述已有来源。"
    )


# ── Response-level edit applier ───────────────────────────────────────────────

def _apply_edits_to_response(response: dict, required_edits: list[str]) -> dict:
    """Apply violation replacement to all text fields of a response dict."""
    text_fields = [
        "summary", "business_analysis", "market_analysis",
        "news_analysis", "linkage_analysis",
    ]
    result = dict(response)
    for field in text_fields:
        if result.get(field):
            result[field] = _apply_edits(result[field], required_edits)
    return result


# ── Text-level helpers ────────────────────────────────────────────────────────

def _apply_edits(text: str, required_edits: list[str]) -> str:
    """Apply required_edits violation replacements to text."""
    if not required_edits:
        return text
    for phrase, replacement in _REPLACEMENTS:
        text = text.replace(phrase, replacement)
    return text


def _find_by_agent(findings: list[dict], agent_name: str) -> dict | None:
    for f in findings:
        if f.get("agent_name") == agent_name:
            return f
    return None


# ── Template section builders (Phase 2E-1, preserved as fallback) ─────────────

def _build_business_analysis(
    finding: dict | None,
    company: str,
    dq: dict,
    required_edits: list[str],
) -> str:
    if finding is None:
        return f"未执行 {company} 基本面分析。"
    if finding.get("status") == "failed":
        return f"{company} 基本面数据获取失败：{finding.get('summary', '未知原因')}。"
    parts: list[str] = []
    if not dq.get("report_verified"):
        parts.append("⚠️ 以下分析基于非官方数据，仅供参考，不作为投资依据。")
    parts.append(finding.get("summary", ""))
    dp = finding.get("data_points", [])
    if dp:
        parts.append("\n主要数据点：")
        for p in dp[:5]:
            parts.append(f"• {p[:200]}")
    flags = finding.get("risk_flags", [])
    if flags:
        flag_texts = [_flag_to_text(f) for f in flags if f]
        if flag_texts:
            parts.append(f"\n注意事项：{'; '.join(flag_texts[:3])}")
    return "\n".join(p for p in parts if p)


def _build_market_analysis(finding: dict | None, company: str) -> str:
    if finding is None:
        return f"未执行 {company} 行情数据分析。"
    if finding.get("status") == "failed":
        return f"{company} 行情数据获取失败：{finding.get('summary', '未知原因')}。"
    parts = [finding.get("summary", "")]
    dp    = finding.get("data_points", [])
    if dp:
        parts.append("\n关键行情指标：")
        for p in dp[:6]:
            parts.append(f"• {p}")
    return "\n".join(p for p in parts if p)


def _build_news_analysis(finding: dict | None) -> str:
    if finding is None or finding.get("status") == "failed":
        return ""
    parts = [finding.get("summary", "")]
    dp    = finding.get("data_points", [])
    if dp:
        parts.append("\n近期新闻：")
        for p in dp[:5]:
            parts.append(f"• {p}")
    return "\n".join(p for p in parts if p)


def _build_linkage_analysis(
    fund: dict | None,
    market: dict | None,
    company: str,
) -> str:
    if fund is None or market is None:
        return ""
    fund_ok   = fund.get("status") in ("success", "partial")
    market_ok = market.get("status") == "success"
    if not (fund_ok and market_ok):
        return ""
    return (
        f"{company} 基本面与市场行情综合来看：基本面数据显示"
        f"「{fund.get('summary', '')[:100]}」；"
        f"行情数据显示「{market.get('summary', '')[:100]}」。"
        "建议综合两个维度进行持续跟踪研究。"
    )


def _build_summary(
    query: str,
    company: str,
    fund: dict | None,
    market: dict | None,
    news: dict | None,
    warnings: list[str],
) -> str:
    parts = [f"关于「{query[:80]}」的综合研究分析："]
    if fund:
        status_str = {"success": "✅", "partial": "⚠️", "failed": "❌"}.get(
            fund.get("status", ""), ""
        )
        parts.append(f"{status_str} 基本面：{fund.get('summary', '')[:100]}")
    if market:
        status_str = {"success": "✅", "partial": "⚠️", "failed": "❌"}.get(
            market.get("status", ""), ""
        )
        parts.append(f"{status_str} 行情：{market.get('summary', '')[:100]}")
    if news and news.get("status") == "success":
        parts.append(f"📰 新闻：{news.get('summary', '')[:100]}")
    if "agent_timeout" in warnings:
        parts.append("⚠️ 部分分析因超时未完成，结果可能不完整。")
    return "\n".join(parts)


def _flag_to_text(flag: str) -> str:
    _FLAG_MAP = {
        "official_report_not_found": "未找到官方披露财报，分析基于非官方数据",
        "rag_search_failed":         "知识库检索失败",
        "no_rag_data":               "知识库无相关数据",
        "quote_failed":              "实时行情获取失败",
        "kline_failed":              "K线数据获取失败",
        "news_fetch_failed":         "新闻数据获取失败",
        "missing_symbol":            "缺少股票信息",
        "agent_timeout":             "分析超时，部分结果不完整",
    }
    return _FLAG_MAP.get(flag, flag)
