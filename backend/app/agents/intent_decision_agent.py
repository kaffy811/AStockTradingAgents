"""
C30.1 — Intent Decision Agent

Rule-based classifier that determines what kind of request the user is making
BEFORE routing to a heavy agent or generating a confirmation card.

Intent types:
  direct_answer        — plain Q&A, no tools needed
  tool_answer          — lightweight tool calls (quote, news, kline)
  report_generation    — explicit request to generate + save a full report
  historical_report_read — read an existing report
  compare_stocks       — explicit multi-stock comparison (≥2 stocks + compare signal)
  industry_research    — industry hotspot / sector / company-within-industry
  portfolio_or_watchlist — watchlist / portfolio related
  unknown              — fallback

Key design:
  - compare_stocks requires EXPLICIT multi-entity compare signal
    ("对比" or "vs"). "比较火" is an adjective, not compare intent.
  - report_generation requires explicit save / generate / 综合报告 keywords.
  - industry_research catches "行业", "板块", "热门", "哪些公司", "热点" etc.
  - order: compare_stocks checked before industry_research to avoid conflict,
    but compare uses strict patterns so industry falls through correctly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Patterns
# ─────────────────────────────────────────────────────────────────────────────

# C30.5: compare requires explicit "对比" / "vs" / multi-entity "比较"
_RE_COMPARE = re.compile(
    r"对比|vs\.?\b|versus"
    r"|比较.{0,30}[、,，和].{0,30}"   # "比较A和B" pattern
    r"|[、,，].{0,30}比较",            # "A、B比较" pattern
    re.IGNORECASE,
)
# EXCEPT when "比较" is used as adjective: 比较火/热/好/多/高/...
_RE_COMPARE_ADJECTIVE = re.compile(r"比较[火热冷强弱好差高低多少大小贵便宜]")

_RE_REPORT_GEN = re.compile(
    r"生成.*报告|保存.*报告|综合报告|综合分析.*保存|深度报告"
    r"|帮我跑.*分析|跑一次.*报告|生成.*研报|保存到历史"
    r"|分析.*并保存|创建.*报告",
    re.IGNORECASE,
)

_RE_HISTORICAL_REPORT = re.compile(
    r"历史报告|之前.*报告|上次.*报告|查.*报告|读.*报告"
    r"|解读.*报告|报告.*解读|最近.*报告|我的报告|上一份报告",
    re.IGNORECASE,
)

_RE_INDUSTRY = re.compile(
    r"行业|热点|板块|哪些值得|哪些.*公司|热门.*行业|行业.*热|行业.*火"
    r"|该行业|这个行业|主题.*股|概念.*股|赛道",
    re.IGNORECASE,
)

_RE_PORTFOLIO = re.compile(
    r"自选股|持仓|组合|我的股票|我买的|我的仓位|仓位",
    re.IGNORECASE,
)

_RE_TOOL_ANSWER = re.compile(
    r"现在多少|当前价|股价|最新价|报价|今天涨跌"
    r"|最新.*新闻|最近.*公告|最新.*消息|今日.*资讯"
    r"|K线|技术面|MACD|RSI|均线|今日行情",
    re.IGNORECASE,
)

_RE_TRADING = re.compile(
    r"买入|卖出|持有|目标价|抄底|止损|仓位建议|何时买|何时卖",
    re.IGNORECASE,
)


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class IntentDecision:
    intent:           str            # one of the 7 intent types
    need_agent:       bool           # True → route to heavy agent / tool chain
    need_confirmation: bool          # True → show confirmation card before action
    target_entities:  list[str]     = field(default_factory=list)  # stocks / industries extracted
    reason:           str            = ""
    confidence:       float          = 0.9


# ─────────────────────────────────────────────────────────────────────────────
# Classifier
# ─────────────────────────────────────────────────────────────────────────────

def classify_intent(query: str) -> IntentDecision:
    """
    Rule-based intent classifier.

    Called BEFORE routing to the orchestrator's action / read intent table.
    The orchestrator's existing matcher functions remain unchanged for
    backward compatibility; this function is advisory for callers that want
    a structured intent result.

    Returns:
        IntentDecision with intent, need_agent, need_confirmation.
    """
    q = query.strip()

    # ── Safety / trading block ────────────────────────────────────────────────
    if _RE_TRADING.search(q):
        return IntentDecision(
            intent            = "direct_answer",
            need_agent        = False,
            need_confirmation = False,
            reason            = "trading directive — safety block applies",
            confidence        = 1.0,
        )

    # ── Report generation (explicit save / generate) ──────────────────────────
    if _RE_REPORT_GEN.search(q):
        entities = _extract_stock_entities(q)
        return IntentDecision(
            intent            = "report_generation",
            need_agent        = True,
            need_confirmation = True,
            target_entities   = entities,
            reason            = "explicit report generation / save request",
            confidence        = 0.95,
        )

    # ── Historical report read ────────────────────────────────────────────────
    if _RE_HISTORICAL_REPORT.search(q):
        return IntentDecision(
            intent            = "historical_report_read",
            need_agent        = True,
            need_confirmation = False,
            reason            = "reading an existing historical report",
            confidence        = 0.92,
        )

    # ── Multi-stock compare (must have explicit compare signal, not adjective) ─
    if _is_compare_intent(q):
        entities = _extract_stock_entities(q)
        return IntentDecision(
            intent            = "compare_stocks",
            need_agent        = True,
            need_confirmation = False,
            target_entities   = entities,
            reason            = "explicit multi-stock comparison",
            confidence        = 0.90,
        )

    # ── Portfolio / watchlist ─────────────────────────────────────────────────
    if _RE_PORTFOLIO.search(q):
        return IntentDecision(
            intent            = "portfolio_or_watchlist",
            need_agent        = True,
            need_confirmation = False,
            reason            = "portfolio or watchlist query",
            confidence        = 0.88,
        )

    # ── Industry research ─────────────────────────────────────────────────────
    if _RE_INDUSTRY.search(q):
        return IntentDecision(
            intent            = "industry_research",
            need_agent        = True,
            need_confirmation = False,
            reason            = "industry / sector / hotspot research",
            confidence        = 0.88,
        )

    # ── Tool answer (real-time data needed but no full report) ───────────────
    if _RE_TOOL_ANSWER.search(q):
        return IntentDecision(
            intent            = "tool_answer",
            need_agent        = True,
            need_confirmation = False,
            reason            = "real-time market data or news query",
            confidence        = 0.85,
        )

    # ── Default: direct answer (LLM Q&A, no heavy agent) ────────────────────
    return IntentDecision(
        intent            = "direct_answer",
        need_agent        = False,
        need_confirmation = False,
        reason            = "general financial Q&A — direct LLM answer",
        confidence        = 0.75,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _is_compare_intent(query: str) -> bool:
    """
    True only for EXPLICIT multi-stock comparison.
    'vs', '对比' → always True.
    '比较' → True only when NOT used as adjective AND has multi-entity context.
    """
    # Explicit non-adjective compare signals
    if re.search(r"对比|vs\.?\b|versus", query, re.IGNORECASE):
        return True
    # "比较" used as adjective (比较火, 比较热, ...) → NOT compare
    if _RE_COMPARE_ADJECTIVE.search(query):
        return False
    # "比较" as a verb with multi-entity separators
    if re.search(r"比较", query) and re.search(r"[、,，和]|还是", query):
        return True
    return False


# Six-digit A-share / HK codes, or Chinese company name patterns
_RE_STOCK_CODE = re.compile(r"\b\d{5,6}\b")
_RE_COMPANY_NAME = re.compile(
    r"宁德时代|比亚迪|茅台|五粮液|紫金矿业|华为|阿里|腾讯|京东|百度"
    r"|中芯国际|华大九天|中船特气|工商银行|建设银行|招商银行",
)


def _extract_stock_entities(query: str) -> list[str]:
    """Extract recognisable stock codes or well-known company names."""
    entities: list[str] = []
    for m in _RE_STOCK_CODE.finditer(query):
        entities.append(m.group())
    for m in _RE_COMPANY_NAME.finditer(query):
        name = m.group()
        if name not in entities:
            entities.append(name)
    return entities
