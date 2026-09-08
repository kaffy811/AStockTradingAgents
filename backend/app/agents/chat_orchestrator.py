"""
Chat Orchestrator — Phase C9.

C4: Real read-only tools for data queries.
C5: Real action tools (add_watchlist, create_analysis_run, create_compare)
    executed after user confirmation. ConfirmationManager tracks lifecycle.
C6: Financial Skills Layer — SkillRegistry intercepts intent before C4 fallbacks.
C7: Controlled Planner — compound multi-step research task orchestration.
    RuleBasedPlanner detects compound tasks; PlannerExecutor runs them.
C8: Memory + Audit — structured session memory, ToolResult audit fields.
C9: OpenClaw-style Skill Registry — SkillSpec JSON files, skill discovery API.

Intent classification → tool calls → answer synthesis.

Financial safety rules: no 买入/卖出/持有/目标价 language in any output.
All answers carry _DISCLAIMER.
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.agents.chat_confirmation import make_confirmation
from app.agents.chat_tools.action_tools import (
    ActionResult,
    execute_add_to_watchlist,
    execute_create_analysis_run,
    execute_create_compare_selection,
)
from app.agents.chat_tools.industry_tools import GetIndustryHotTool, GetIndustryNewsTool, GetIndustryStocksTool
from app.agents.chat_tools.realtime_search_tools import SearchRealtimeNewsTool, UniversalMarketSearchTool
from app.agents.chat_tools.registry import ToolRegistry
from app.agents.chat_tools.report_tools import GetRecentReportsTool, GetReportDetailTool
from app.agents.chat_tools.stock_tools import (
    GetKlineSummaryTool,
    GetLatestNewsTool,
    GetQuoteTool,
    ResolveStockTool,
)
from app.agents.chat_tools.tool_result import ToolResult
from app.agents.chat_tools.watchlist_tools import GetWatchlistTool
from app.agents.chat_skills.base import SkillContext
from app.agents.chat_skills.registry import SkillRegistry
from app.agents.chat_skills.stock_anomaly_skill import StockAnomalySkill
from app.agents.chat_skills.risk_first_skill import RiskFirstSkill
from app.agents.chat_skills.news_catalyst_skill import NewsCatalystSkill
from app.agents.chat_skills.watchlist_review_skill import WatchlistReviewSkill
from app.agents.chat_skills.industry_hotspot_skill import IndustryHotspotSkill
from app.agents.chat_skills.report_explanation_skill import ReportExplanationSkill
from app.agents.chat_skills.general_financial_answer_skill import GeneralFinancialAnswerSkill
from app.agents.chat_planner.rule_based_planner import RuleBasedPlanner
from app.agents.chat_planner.executor import PlannerExecutor
from app.agents.intent_decision_agent import classify_intent
from app.agents.central_planning_agent import CentralPlanningAgent as _CentralPlanningAgent
from app.services.security_entity_resolver import security_entity_resolver
from app.services.official_report_entity_hints import unambiguous_official_report_entity_hint
from app.services.official_company_event_service import official_company_event_service
from app.services.tushare_eod_gateway import tushare_eod_gateway
from app.services.stock_eod_numeric_validation import (
    claim_from_evidence,
    make_request_local_evidence,
    validate_stock_eod_numeric_claims,
)
import app.agents.chat_memory as _mem

_central_planner = _CentralPlanningAgent()

log = logging.getLogger(__name__)

_DISCLAIMER = "\n\n_仅供研究参考，不构成投资建议。_"
_EMPTY_FINAL_ANSWER_TEXT = "报告数据已获取，但本次回答生成失败，请重新尝试。"
_CHAT_ENTITY_PIPELINE_VERSION = "d6_4"
_OFFICIAL_REPORT_PDF_SHADOW_PATTERN = re.compile(
    r"pdf|PDF|官方.{0,6}(链接|原文|PDF|pdf)|年报|年度报告|中报|半年报|季报|一季报|三季报|这份报告|那份报告|报告原文|报告.*在哪"
    r"|报告.*哪一份|哪一份.*报告",  # R1.1-B: "最新报告是哪一份" locator pattern
    re.IGNORECASE,
)
# R1.1-B: Analysis-intent override — prevents analysis queries that mention "年报" etc.
# from being hijacked by the PDF early-return path.
# When a query matches both the PDF pattern AND this pattern, it is routed to SkillRegistry
# (ReportExplanationSkill) instead of _handle_official_report_pdf_direct.
# Example: "分析茅台最新年报的盈利能力" → has "年报" (PDF pattern) + "分析/盈利能力" (here)
#          → SkillRegistry (analysis intent wins).
_PDF_ANALYSIS_OVERRIDE_RE = re.compile(
    r"分析|如何|怎么样|表现|情况|盈利能力|净利|毛利|增长|同比|业绩|解读|研究|评价|走势|趋势",
    re.IGNORECASE,
)
_LATEST_REPORT_SETUP_PATTERN = re.compile(
    r"(最新|最近|当前|这份|那份).{0,8}(财报|报告|定期报告).{0,12}(表现|情况|如何|怎么样|解读|分析)"
    r"|(.{0,8}(财报|报告|定期报告).{0,8}(表现|情况|如何|怎么样))",
    re.IGNORECASE,
)

_OFFICIAL_EVENT_TERMS_RE = re.compile(
    r"公告|官方披露|披露事件|"
    r"(?:年报|年度报告|半年报|半年度报告|季报|季度报告|财报).{0,12}(?:披露|重点|官方)|"
    r"(?:披露|官方).{0,12}(?:年报|年度报告|半年报|半年度报告|季报|季度报告|财报)|"
    r"分红|派息|回购|增持|减持|股东变动|权益变动|并购|重组|管理层变动|监管公告|诉讼公告|风险公告"
)
_OFFICIAL_REPORT_ANALYSIS_RE = re.compile(
    r"年报|年度报告|半年报|半年度报告|季报|季度报告|财报|业绩"
)
_UNAPPROVED_NEWS_SCOPE_RE = re.compile(
    r"行业.{0,16}(新闻|资讯|消息|动态)|"
    r"(新闻|资讯|消息|动态).{0,16}(行业|板块)|"
    r"市场.{0,12}(热点|新闻|资讯|消息)|"
    r"(热点|新闻|资讯|消息).{0,12}市场|"
    r"产业链|供应链|直接受益|受益.{0,8}(公司|股票)|带动.{0,10}(公司|股票)|"
    r"AI\s*热潮|新能源.{0,8}(重要新闻|行业新闻)"
)
_UNAPPROVED_THEME_SCOPE_RE = re.compile(
    r"(?:行业|主题|概念|板块|产业链|供应链).{0,16}(?:问题|影响|新闻|资讯|消息|动态|"
    r"公司|股票|上市公司|标的|机会|有哪些|是什么)|"
    r"(?:哪些|什么|相关|受益|影响).{0,12}(?:行业|主题|概念|板块|产业链|供应链|上市公司)|"
    r"(?:AI|人工智能|半导体设备|算力|机器人|新能源).{0,12}(?:主题|概念|产业链|受益公司|"
    r"相关公司|上市公司|行业消息|行业新闻)"
)
_STOCK_EOD_RESEARCH_RE = re.compile(
    r"近期情况|最近情况|近期表现|最近表现|近期估值|最近估值|"
    r"财务指标|ROE|roe|盘后|收盘|交易日|估值与财务"
)
_REQUESTED_OFFICIAL_EVENT_TYPES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("分红", re.compile(r"分红|派息|利润分配|权益分派")),
    ("回购", re.compile(r"回购")),
    ("股东增减持", re.compile(r"增持|减持|股东变动|权益变动")),
    ("并购重组", re.compile(r"并购|重组")),
    ("治理与管理层", re.compile(r"治理|管理层|董事|监事|高管")),
    ("业务进展", re.compile(r"业务进展|项目|合同|中标|投产")),
    ("监管/诉讼/风险", re.compile(r"监管|诉讼|仲裁|风险|处罚|立案")),
)
# ── Build registry ─────────────────────────────────────────────────────────────

def _build_registry() -> ToolRegistry:
    reg = ToolRegistry()
    for tool in [
        ResolveStockTool(),
        GetQuoteTool(),
        GetKlineSummaryTool(),
        GetLatestNewsTool(),
        GetRecentReportsTool(),
        GetReportDetailTool(),
        GetWatchlistTool(),
        GetIndustryHotTool(),
        GetIndustryStocksTool(),
        GetIndustryNewsTool(),
        SearchRealtimeNewsTool(),
        UniversalMarketSearchTool(),
    ]:
        reg.register(tool)
    return reg

_registry = _build_registry()


# ── Build skill registry ────────────────────────────────────────────────────────

def _build_skill_registry() -> SkillRegistry:
    sreg = SkillRegistry()
    for skill in [
        ReportExplanationSkill(),          # priority=10 (highest — specific intent)
        WatchlistReviewSkill(),            # priority=20
        IndustryHotspotSkill(),            # priority=30
        RiskFirstSkill(),                  # priority=35
        StockAnomalySkill(),               # priority=40
        NewsCatalystSkill(),               # priority=45
        GeneralFinancialAnswerSkill(),     # priority=100 (lowest — RAG+DeepSeek catchall)
    ]:
        sreg.register(skill)
    return sreg

_skill_registry = _build_skill_registry()


# ── Build planner + executor (C7) ─────────────────────────────────────────────

_planner  = RuleBasedPlanner()
_executor = PlannerExecutor(_skill_registry)


# ── C9 Skill discovery ─────────────────────────────────────────────────────────

def get_skills_list() -> list[dict]:
    """
    Return public skill spec metadata for the skill discovery API.
    Used by GET /chat/skills. Does NOT expose internal prompts.
    """
    return _skill_registry.list_skill_specs()


# ── Return types (same as C3 for router compatibility) ─────────────────────────

@dataclass
class OrchestratorResult:
    answer: str
    tool_events: list = field(default_factory=list)
    cards: list = field(default_factory=list)
    confirmation: dict | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ConfirmResult:
    answer: str
    tool_events: list = field(default_factory=list)
    cards: list = field(default_factory=list)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _tool_event(name: str, detail: str, status: str = "success") -> dict:
    return {"name": name, "status": status, "detail": detail}


def _card(card_type: str, data: dict) -> dict:
    return {"type": card_type, "data": data}


def _result_tool_event(r: ToolResult) -> dict:
    """Build a C8-compliant audit tool event from a ToolResult.
    Backward-compatible: always includes name/status/detail for ChatToolTrace.
    """
    event = _tool_event(r.tool_name, r.summary, "success" if r.ok else "error")
    # C8 audit fields (additive — frontend ignores unknown keys)
    event["event_type"]       = "tool_completed"
    event["permission_level"] = r.permission_level
    event["ok"]               = r.ok
    if r.duration_ms is not None:
        event["duration_ms"] = r.duration_ms
    if r.started_at is not None:
        event["started_at"] = r.started_at
    if r.error is not None:
        event["error"] = r.error
    return event


# ── Intent matchers ────────────────────────────────────────────────────────────

# Safety-first: explicit trading/prediction requests must be intercepted before
# any other handler.  These patterns never reach write-operation tools.
_TRADING_PATTERN = re.compile(
    r"帮我.{0,6}(交易|买入|卖出|下单|购买|清仓)"
    r"|价格预测|未来走势|明天.*涨|明天.*跌|后天.*涨|预测.*股价"
    r"|目标价.{0,4}多少|稳赚|必涨|抄底|追涨",
    re.IGNORECASE,
)

def _match_trading_request(msg: str) -> bool:
    return bool(_TRADING_PATTERN.search(msg))


def _match_official_report_pdf_shadow_candidate(msg: str) -> bool:
    return bool(_OFFICIAL_REPORT_PDF_SHADOW_PATTERN.search(msg or ""))


def _match_latest_report_setup_candidate(msg: str) -> bool:
    return bool(_LATEST_REPORT_SETUP_PATTERN.search(msg or ""))


def _unambiguous_report_entity_hint(message: str) -> dict:
    return unambiguous_official_report_entity_hint(message)


def _entity_payload_from_hint(hint: dict, *, source: str) -> dict:
    return {
        "entity_type": "equity",
        "market": hint.get("market") or "CN",
        "symbol": hint.get("symbol") or "",
        "short_name": hint.get("name") or hint.get("symbol") or "",
        "name": hint.get("name") or hint.get("symbol") or "",
        "source": source,
    }


def _report_type_from_query(query: str) -> str:
    text = query or ""
    if re.search(r"一季报|第一季度|q1", text, re.IGNORECASE):
        return "q1"
    if re.search(r"三季报|第三季度|q3", text, re.IGNORECASE):
        return "q3"
    if re.search(r"中报|半年报|半年度", text, re.IGNORECASE):
        return "semi"
    return "annual"


def _ts_code_for_hint(hint: dict) -> str:
    symbol = str(hint.get("symbol") or "")
    market = str(hint.get("market") or "CN").upper()
    if market == "CN" and symbol:
        return f"{symbol}.SH" if symbol.startswith(("6", "9")) else f"{symbol}.SZ"
    return symbol


def _match_report(msg: str) -> bool:
    return bool(re.search(r"生成.{0,10}报告|综合报告|分析报告|帮我分析", msg))


def _match_watchlist_add(msg: str) -> bool:
    # Only match explicit add intent — "加入自选" / "添加到自选" — NOT bare "自选股" queries
    return bool(re.search(r"加入自选|添加到自选|添加自选", msg))


def _match_watchlist_view(msg: str) -> bool:
    return bool(re.search(r"查看自选股|自选股列表|我的自选|看看.*自选|自选股.*有哪些", msg))


def _match_compare(msg: str) -> bool:
    """
    C30.5 / C32.2.2: Explicit multi-stock comparison intent.
    '对比' is always explicit. 'vs/versus' is explicit.
    '相比' with ≥2 entities is explicit (handles "那它和五粮液相比呢？").
    '比较' must NOT be an adjective modifier (比较火/热/好/…) and must appear
    with multi-entity separators (、,，和/还是) suggesting ≥2 stocks.
    This prevents '最近哪些行业比较火' from routing to compare.
    """
    # Unambiguously explicit compare words
    if re.search(r"对比|vs\.?\b|versus", msg, re.IGNORECASE):
        return True
    # "相比" as comparison verb: "A和B相比" / "A与B相比" / "A跟B相比"
    if re.search(r"相比", msg) and re.search(r"[和与跟、,，]", msg):
        return True
    # "比较" as adjective/adverb is NOT a compare trigger
    if re.search(r"比较[火热冷强弱好差高低多少大小贵便]", msg):
        return False
    # "比较" as verb only when separators suggest multiple entities
    if re.search(r"比较", msg) and re.search(r"[、,，和]|还是", msg):
        return True
    return False


def _match_industry(msg: str) -> bool:
    return bool(re.search(r"行业|热点|板块|哪些值得|热门", msg))


def _match_anomaly(msg: str) -> bool:
    return bool(
        re.search(r"中船特气|688146", msg)
        or (re.search(r"为什么|原因|涨|跌|异动", msg) and re.search(r"股票|股", msg))
    )


def _match_quote(msg: str) -> bool:
    return bool(re.search(r"现在多少|当前价|股价|最新价|报价", msg))


def _match_news(msg: str) -> bool:
    return bool(re.search(r"新闻|消息|公告|资讯", msg))


def _match_recent_report(msg: str) -> bool:
    return bool(re.search(
        r"历史报告|之前的报告|上次报告|查报告|最近.*报告|上一份报告|解释.*报告|报告.*解释|最新报告|我的报告",
        msg,
    ))


# ── Stock extraction helper ────────────────────────────────────────────────────

def _extract_stock_hint(msg: str) -> dict:
    """
    Best-effort extraction of {market, symbol, name_query} from user message.
    C32.2.3: expanded A-share name mapping.
    """
    ts_code = re.search(r"(?<!\d)(\d{6})\.(SH|SZ|BJ)(?![A-Z0-9])", msg, re.IGNORECASE)
    if ts_code:
        symbol = ts_code.group(1)
        return {"market": "CN", "symbol": symbol, "name": symbol, "query": ts_code.group(0)}
    # Generic CN code: 6-digit number
    m = re.search(r"(?<!\d)(\d{6})(?!\d)", msg)
    if m:
        return {"market": "CN", "symbol": m.group(1), "name": m.group(1), "query": m.group(1)}
    # HK code: 5-digit or 4-digit
    m = re.search(r"(?<!\d)0?(\d{4,5})(?!\d)", msg)
    if m:
        return {"market": "HK", "symbol": m.group(1).zfill(5), "name": m.group(1), "query": m.group(1)}
    m = re.search(r"\b([A-Z]{1,5}(?:[.-][A-Z])?)\b", msg)
    if m:
        return {"market": "US", "symbol": m.group(1).upper(), "name": m.group(1).upper(), "query": m.group(1)}
    return {}


def _memory_entity_hints(memory_context: object | None) -> list[dict]:
    entities: list[dict] = []
    for entity in getattr(memory_context, "active_entities", []) or []:
        if getattr(entity, "type", "") != "stock" or not getattr(entity, "code", ""):
            continue
        entities.append({
            "entity_type": "equity",
            "market": getattr(entity, "market", "") or "CN",
            "symbol": getattr(entity, "code", ""),
            "short_name": getattr(entity, "name", "") or getattr(entity, "code", ""),
            "name": getattr(entity, "name", "") or getattr(entity, "code", ""),
            "source": "conversation_context",
        })
    return entities


async def _resolve_current_query_entities(
    db: AsyncSession,
    *,
    raw_query: str,
    effective_query: str,
    memory_context: object | None,
) -> dict:
    """Resolve explicit entities from the current user query before skill routing."""
    context_entities = _memory_entity_hints(memory_context)
    debug: dict = {
        "chat_entity_pipeline_version": _CHAT_ENTITY_PIPELINE_VERSION,
        "raw_query": raw_query,
        "effective_query": effective_query,
        "resolver_called": False,
        "resolver_result_count": 0,
        "resolved_entities": [],
        "primary_entity": None,
        "context_source": "none",
        "failure_reason": "",
    }
    try:
        debug["resolver_called"] = True
        resolved = await security_entity_resolver.resolve(
            db,
            raw_query,
            context_entities=context_entities,
            min_confidence=0.72,
        )
        entities = [entity.to_dict() for entity in (resolved.get("entities") or [])]
        context_source = "raw_query_explicit"
        if not entities and effective_query and effective_query != raw_query:
            resolved = await security_entity_resolver.resolve(
                db,
                effective_query,
                context_entities=context_entities,
                min_confidence=0.72,
            )
            entities = [entity.to_dict() for entity in (resolved.get("entities") or [])]
            context_source = "effective_query"
        primary = entities[0] if entities else None
        debug.update({
            "resolver_result_count": len(entities),
            "resolved_entities": entities,
            "primary_entity": primary,
            "context_source": context_source if primary else "none",
            "ambiguity": bool(resolved.get("ambiguity")),
            "resolver_candidates": resolved.get("candidates", [])[:8],
            "record_count_by_market": resolved.get("record_count_by_market", {}),
            "index_version": resolved.get("index_version"),
            "failure_reason": "" if primary else "ENTITY_NOT_RESOLVED",
        })
        return debug
    except Exception as exc:
        debug.update({
            "failure_reason": f"RESOLVER_ERROR:{type(exc).__name__}",
            "resolver_error": str(exc)[:160],
        })
        return debug


async def _recent_unambiguous_report_entity_hint(
    db: AsyncSession,
    *,
    session_id: uuid.UUID | None,
    current_query: str,
) -> dict:
    if session_id is None:
        return {}
    try:
        from app.core.database import AsyncSessionLocal  # noqa: PLC0415
        from sqlalchemy import desc, select  # noqa: PLC0415
        from app.models.chat import ChatMessage  # noqa: PLC0415

        stmt = (
            select(ChatMessage.content)
            .where(ChatMessage.session_id == session_id, ChatMessage.role == "user")
            .order_by(desc(ChatMessage.created_at))
            .limit(6)
        )
        async with AsyncSessionLocal() as recent_db:
            result = await asyncio.wait_for(recent_db.execute(stmt), timeout=10.0)
            rows = result.scalars().all()
            await asyncio.wait_for(recent_db.rollback(), timeout=3.0)
        current = (current_query or "").strip()
        for content in rows:
            text = str(content or "").strip()
            if text == current:
                continue
            hint = _unambiguous_report_entity_hint(text)
            if hint:
                return {**hint, "source": "recent_session_user_message"}
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "official_report_pdf recent entity hint unavailable session=%s error_class=%s",
            session_id,
            type(exc).__name__,
        )
    return {}


def _entity_hint_from_payload_or_memory(entity_payload: dict, memory_context: object | None, raw_query: str) -> dict:
    primary = entity_payload.get("primary_entity") if isinstance(entity_payload, dict) else None
    if isinstance(primary, dict) and primary.get("symbol"):
        return {
            "market": primary.get("market") or "CN",
            "symbol": primary.get("symbol"),
            "name": primary.get("short_name") or primary.get("name") or primary.get("symbol"),
            "source": "resolver_primary_entity",
        }
    for entity in getattr(memory_context, "active_entities", []) or []:
        if getattr(entity, "type", "") == "stock" and getattr(entity, "code", ""):
            return {
                "market": getattr(entity, "market", "") or "CN",
                "symbol": getattr(entity, "code", ""),
                "name": getattr(entity, "name", "") or getattr(entity, "code", ""),
                "source": "memory_context",
            }
    return _unambiguous_report_entity_hint(raw_query)


async def _handle_official_report_pdf_direct(
    msg: str,
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    entity_hint: dict,
    session_id: uuid.UUID | None,
) -> OrchestratorResult:
    report_type = _report_type_from_query(msg)
    if report_type != "annual":
        return OrchestratorResult(
            answer="当前官方报告 PDF 工具仅支持年度报告；未返回其他期间链接。" + _DISCLAIMER,
            metadata={
                "status": "unavailable",
                "error_code": "REPORT_TYPE_UNSUPPORTED",
                "skill_name": "official_report_pdf_direct",
                "skill_data": {
                    "status": "unavailable",
                    "error_code": "REPORT_TYPE_UNSUPPORTED",
                    "report_context": {
                        "symbol": entity_hint.get("symbol"),
                        "market": entity_hint.get("market") or "CN",
                        "report_type": report_type,
                    },
                },
            },
        )
    try:
        from app.core.database import AsyncSessionLocal  # noqa: PLC0415
        from app.services.official_report_domain_service import official_report_domain_service  # noqa: PLC0415

        async with AsyncSessionLocal() as report_db:
            reports = await asyncio.wait_for(
                official_report_domain_service.list_official_annual_reports(
                    report_db,
                    ts_code=_ts_code_for_hint(entity_hint),
                    limit=1,
                ),
                timeout=10.0,
            )
            await asyncio.wait_for(report_db.rollback(), timeout=3.0)
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "official_report_pdf direct lookup failed session=%s error_class=%s",
            session_id,
            type(exc).__name__,
        )
        return OrchestratorResult(
            answer="暂未能读取官方报告索引，请稍后重试。" + _DISCLAIMER,
            metadata={"status": "failed", "error_code": "OFFICIAL_REPORT_LOOKUP_FAILED"},
        )
    if not reports:
        return OrchestratorResult(
            answer="暂未找到该公司的官方年度报告 PDF。" + _DISCLAIMER,
            metadata={"status": "unavailable", "error_code": "OFFICIAL_REPORT_NOT_FOUND"},
        )
    report = reports[0]
    pdf_url = report.get("pdf_url") or ""
    title = report.get("title") or "官方年度报告"
    year = report.get("report_year")
    answer = (
        f"{entity_hint.get('name') or entity_hint.get('symbol')}的{year or ''}年度报告官方 PDF：{pdf_url}\n\n"
        f"来源：{title}"
        + _DISCLAIMER
    )
    report_context = {
        "report_id": report.get("report_id"),
        "symbol": entity_hint.get("symbol"),
        "market": entity_hint.get("market") or "CN",
        "stock_name": entity_hint.get("name") or entity_hint.get("symbol"),
        "report_year": year,
        "report_type": "annual",
        "pdf_url": pdf_url,
        "source_url": report.get("source_url"),
    }
    return OrchestratorResult(
        answer=answer,
        tool_events=[_tool_event("get_official_reports", "已读取官方年度报告索引", "success")],
        metadata={
            "status": "completed",
            "skill_name": "official_report_pdf_direct",
            "tools_used": ["get_official_reports"],
            "skill_data": {
                "status": "completed",
                "report_context": report_context,
            },
        },
    )


async def _handle_latest_report_setup_direct(
    msg: str,
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    entity_hint: dict,
    session_id: uuid.UUID | None,
) -> OrchestratorResult:
    try:
        from app.core.database import AsyncSessionLocal  # noqa: PLC0415
        from app.agent.report_context import resolve_report_selection  # noqa: PLC0415

        async with AsyncSessionLocal() as report_db:
            selection = await asyncio.wait_for(
                resolve_report_selection(
                    db=report_db,
                    market=entity_hint.get("market") or "CN",
                    symbol=entity_hint["symbol"],
                    stock_name=entity_hint.get("name") or None,
                    question=msg,
                    report_id=None,
                ),
                timeout=10.0,
            )
            await asyncio.wait_for(report_db.rollback(), timeout=3.0)
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "latest_report_setup direct lookup failed session=%s error_class=%s",
            session_id,
            type(exc).__name__,
        )
        return OrchestratorResult(
            answer="暂未能读取最新正式报告索引，请稍后重试。" + _DISCLAIMER,
            metadata={"status": "failed", "error_code": "LATEST_REPORT_SETUP_LOOKUP_FAILED"},
        )

    if not selection.ok:
        return OrchestratorResult(
            answer="暂未找到该公司的最新正式报告上下文。" + _DISCLAIMER,
            metadata={"status": "unavailable", "error_code": selection.error or selection.selection_reason or "LATEST_REPORT_NOT_FOUND"},
        )

    report_context = selection.metadata()
    report_label = report_context.get("title") or "最新正式财报"
    year_label = f"{report_context.get('report_year')}年" if report_context.get("report_year") else ""
    answer = (
        f"已定位到{entity_hint.get('name') or entity_hint['symbol']}的{year_label}{report_label}。"
        "这轮先基于已索引的正式报告建立上下文；如果需要原文，请继续问这份报告的官方 PDF。"
        + _DISCLAIMER
    )
    return OrchestratorResult(
        answer=answer,
        tool_events=[_tool_event("resolve_report_selection", "已定位最新正式报告", "success")],
        metadata={
            "status": "partial_success",
            "skill_name": "latest_report_setup_direct",
            "tools_used": ["resolve_report_selection"],
            "skill_data": {
                "status": "partial_success",
                "report_context": report_context,
            },
            "report_context": report_context,
        },
    )


async def _record_pi_shadow_skipped(
    *,
    content: str,
    session_id: uuid.UUID | None,
    user_id: uuid.UUID,
    entity_payload: dict,
    shadow_result_callback: Callable | None = None,
) -> None:
    try:
        from app.agent_runtime.contracts import new_id  # noqa: PLC0415
        from app.agent_runtime.shadow_correlation import current_correlation  # noqa: PLC0415
        from app.agent_runtime.shadow_diagnostics import pi_shadow_diagnostics_sink  # noqa: PLC0415

        correlation = current_correlation()
        skipped_result = {
            "schema_version": "pi_financial_runtime_v1",
            "trace_id": correlation.get("request_trace_id") or new_id("trace"),
            "run_id": correlation.get("shadow_run_id") or new_id("run"),
            "status": "skipped",
            "reason": "intent_not_official_report_pdf",
            "agent_id": "official_report_pdf_pi_v1",
            "turn_count": 0,
            "tool_call_count": 0,
            "events": [],
            "findings": [],
            "evidence_ids": [],
            "error": {"code": "PI_SHADOW_SKIPPED"},
            "metrics": {"latency_ms": 0, "model_calls": 0, "tool_calls": 0, "input_tokens": 0, "output_tokens": 0},
            "shadow_input": {
                "conversation_id": str(session_id) if session_id else "",
                "message_snapshot": [],
                "financial_context_snapshot": {},
                "resolved_entity_snapshot": entity_payload,
            },
        }
        pi_shadow_diagnostics_sink.record(
            raw_query=content,
            conversation_id=str(session_id) if session_id else "",
            user_id=str(user_id),
            result=skipped_result,
            correlation=correlation,
        )
        if shadow_result_callback is not None:
            maybe_awaitable = shadow_result_callback(skipped_result)
            if hasattr(maybe_awaitable, "__await__"):
                await maybe_awaitable
    except Exception as exc:  # noqa: BLE001
        log.debug("pi-compatible skipped diagnostics failed: %s", exc)


def _schedule_pi_official_report_shadow(
    *,
    content: str,
    effective_content: str,
    session_id: uuid.UUID | None,
    user_id: uuid.UUID,
    entity_payload: dict,
    output_language: str,
    shadow_result_callback: Callable | None = None,
) -> None:
    try:
        from app.agent_runtime.contracts import new_id  # noqa: PLC0415
        from app.agent_runtime.shadow_correlation import current_correlation  # noqa: PLC0415
        from app.agent_runtime.shadow_runner import pi_compatible_shadow_runner  # noqa: PLC0415

        if not pi_compatible_shadow_runner.enabled():
            raise RuntimeError("pi-compatible shadow is not enabled or agent is not allowed")

        correlation = current_correlation()
        shadow_trace_id = correlation.get("request_trace_id") or new_id("trace")
        shadow_run_id = correlation.get("shadow_run_id") or new_id("run")

        async def _pi_shadow_run() -> None:
            result: dict | None = None
            try:
                result = await pi_compatible_shadow_runner.run_official_report_pdf_shadow_with_new_session(
                    raw_query=content,
                    normalized_query=effective_content,
                    user_id=str(user_id),
                    conversation_id=str(session_id) if session_id else "",
                    page_context={},
                    memory_context=None,
                    resolved_entity_snapshot=entity_payload,
                    output_language=output_language,
                    correlation=correlation,
                )
                log.debug("pi-compatible shadow result: %s", result.get("status"))
            except asyncio.CancelledError:
                result = {
                    "trace_id": shadow_trace_id,
                    "run_id": shadow_run_id,
                    "status": "cancelled",
                    "agent_id": "official_report_pdf_pi_v1",
                    "metrics": {"latency_ms": 0, "model_calls": 0, "tool_calls": 0},
                    "error": {"code": "PI_SHADOW_CANCELLED"},
                    "events": [],
                    "findings": [],
                    "evidence_ids": [],
                    "shadow_input": {"conversation_id": str(session_id) if session_id else ""},
                }
                raise
            except Exception as exc:  # noqa: BLE001
                result = {
                    "trace_id": shadow_trace_id,
                    "run_id": shadow_run_id,
                    "status": "failed",
                    "agent_id": "official_report_pdf_pi_v1",
                    "metrics": {"latency_ms": 0, "model_calls": 0, "tool_calls": 0},
                    "error": {"code": f"PI_SHADOW_{type(exc).__name__.upper()}"},
                    "events": [],
                    "findings": [],
                    "evidence_ids": [],
                    "shadow_input": {"conversation_id": str(session_id) if session_id else ""},
                }
                log.debug("pi-compatible shadow task failed: %s", exc)
            finally:
                if result is not None:
                    try:
                        from app.agent_runtime.shadow_diagnostics import pi_shadow_diagnostics_sink  # noqa: PLC0415

                        pi_shadow_diagnostics_sink.record(
                            raw_query=content,
                            conversation_id=str(session_id) if session_id else "",
                            user_id=str(user_id),
                            result=result,
                            correlation=correlation,
                        )
                    except Exception as exc:  # noqa: BLE001
                        log.debug("pi-compatible shadow diagnostics failed: %s", exc)
            if shadow_result_callback is not None:
                maybe_awaitable = shadow_result_callback(result)
                if hasattr(maybe_awaitable, "__await__"):
                    await maybe_awaitable

        task = asyncio.create_task(_pi_shadow_run())

        def _consume_pi_shadow_error(done_task: asyncio.Task) -> None:
            try:
                done_task.exception()
            except asyncio.CancelledError:
                log.debug("pi-compatible shadow task cancelled")
            except Exception as exc:  # noqa: BLE001
                log.debug("pi-compatible shadow task failed: %s", exc)

        task.add_done_callback(_consume_pi_shadow_error)
    except Exception as exc:  # noqa: BLE001
        log.debug("pi-compatible shadow scheduling failed: %s", exc)


# ── Intent handlers (async, use real tools) ────────────────────────────────────

async def _handle_anomaly(msg: str, db: AsyncSession, user_id: uuid.UUID) -> OrchestratorResult:
    hint = _extract_stock_hint(msg)
    events: list = []
    cards: list  = []

    # 1. Resolve stock
    resolve = await _registry.call("resolve_stock_tool", db,
                                   query=hint.get("query", "688146"),
                                   market=hint.get("market", "CN"))
    events.append(_result_tool_event(resolve))
    if resolve.ok:
        stock = resolve.data
    else:
        stock = {"market": hint.get("market", "CN"),
                 "symbol": hint.get("symbol", "688146"),
                 "name":   hint.get("name", "未知股票")}

    # 2. Quote
    quote = await _registry.call("get_quote_tool", db,
                                  market=stock["market"], symbol=stock["symbol"],
                                  name=stock.get("name", stock["symbol"]))
    events.append(_result_tool_event(quote))
    if quote.ok:
        cards.extend(quote.cards)

    # 3. Kline summary
    kline = await _registry.call("get_kline_summary_tool", db,
                                  market=stock["market"], symbol=stock["symbol"])
    events.append(_result_tool_event(kline))

    # 4. News
    news = await _registry.call("get_latest_news_tool", db,
                                 market=stock["market"], symbol=stock["symbol"],
                                 hours_back=72, limit=6)
    events.append(_result_tool_event(news))

    # Synthesize answer from real tool data
    name_str = stock.get("name", stock["symbol"])
    market_sym = f"{stock['market']}/{stock['symbol']}"

    price_line = ""
    if quote.ok and quote.data:
        price_line = (
            f"当前价 **{quote.data['price']}**（{quote.data['change_pct']}），"
        )

    kline_line = ""
    if kline.ok and kline.data:
        chg = kline.data.get("period_change_pct", 0)
        sign = "+" if chg >= 0 else ""
        kline_line = f"近20日涨跌幅约 **{sign}{chg:.2f}%**。"

    news_count = news.data.get("count", 0) if news.ok and news.data else 0
    news_titles = ""
    if news.ok and news.data:
        items = news.data.get("items", [])
        if items:
            news_titles = "\n".join(f"- {it['title']}" for it in items[:3] if it.get("title"))

    answer = (
        f"**{name_str}（{market_sym}）近期行情观察：**\n\n"
        + (f"**行情：** {price_line}{kline_line}\n\n" if price_line or kline_line else "")
        + (f"**近期新闻（{news_count} 条）：**\n{news_titles}\n\n" if news_titles else "")
        + "如需深度分析，可输入「帮我生成综合报告」。"
        + _DISCLAIMER
    )

    # If quote card already added via real tool, use it; otherwise build fallback
    if not cards:
        cards.append(_card("stock_summary", {
            "name":       name_str,
            "market":     stock["market"],
            "symbol":     stock["symbol"],
            "price":      quote.data.get("price", "—") if quote.ok and quote.data else "—",
            "changePct":  quote.data.get("change_pct", "—") if quote.ok and quote.data else "—",
            "changeDir":  quote.data.get("change_dir", "flat") if quote.ok and quote.data else "flat",
            "summary":    "技术面数据获取中",
            "links": [
                {"label": "查看股票详情", "path": f"/stocks/{stock['market']}/{stock['symbol']}"},
                {"label": "生成综合报告 →", "action": "generate_report",
                 "symbol": stock["symbol"], "market": stock["market"], "name": name_str},
            ],
        }))

    return OrchestratorResult(answer=answer, tool_events=events, cards=cards)


async def _handle_industry(msg: str, db: AsyncSession, user_id: uuid.UUID) -> OrchestratorResult:
    events: list = []
    cards:  list = []

    hot = await _registry.call("get_industry_hot_tool", db, market="CN", limit=8)
    events.append(_result_tool_event(hot))
    if hot.ok:
        cards.extend(hot.cards)

    if hot.ok and hot.data and hot.data.get("items"):
        items = hot.data["items"]
        rows  = "\n".join(
            f"- **{it['name']}**：热度 {it['hotScore']:.2f}，涨跌 {it['changePct']}"
            for it in items
        )
        answer = (
            "以下为当前申万行业热度排行（基于成交额 × 涨跌幅综合评分），"
            "仅作研究线索，不代表投资价值判断。\n\n"
            + rows
            + _DISCLAIMER
        )
    else:
        answer = "行业热度数据暂不可用，请稍后再试。" + _DISCLAIMER

    return OrchestratorResult(answer=answer, tool_events=events, cards=cards)


async def _handle_watchlist_view(msg: str, db: AsyncSession, user_id: uuid.UUID) -> OrchestratorResult:
    events: list = []
    cards:  list = []

    wl = await _registry.call("get_watchlist_tool", db, user_id=str(user_id))
    events.append(_result_tool_event(wl))
    if wl.ok:
        cards.extend(wl.cards)

    if wl.ok and wl.data:
        count = wl.data["count"]
        if count == 0:
            answer = "你的自选股列表目前为空。可以说「把 688146 加入自选」来添加。" + _DISCLAIMER
        else:
            answer = f"你的自选股共 **{count}** 只。" + _DISCLAIMER
    else:
        answer = "自选股数据暂不可用，请稍后再试。" + _DISCLAIMER

    return OrchestratorResult(answer=answer, tool_events=events, cards=cards)


async def _handle_quote(msg: str, db: AsyncSession, user_id: uuid.UUID) -> OrchestratorResult:
    hint = _extract_stock_hint(msg)
    events: list = []
    cards:  list = []

    if not hint:
        return OrchestratorResult(
            answer="请告诉我您想查询哪只股票的行情，例如：688146 现在多少钱？" + _DISCLAIMER,
        )

    resolve = await _registry.call("resolve_stock_tool", db,
                                   query=hint.get("query", ""),
                                   market=hint.get("market", "CN"))
    events.append(_result_tool_event(resolve))
    stock = resolve.data if resolve.ok else {
        "market": hint.get("market", "CN"),
        "symbol": hint.get("symbol", ""),
        "name":   hint.get("name", ""),
    }

    quote = await _registry.call("get_quote_tool", db,
                                  market=stock["market"], symbol=stock["symbol"],
                                  name=stock.get("name", stock["symbol"]))
    events.append(_result_tool_event(quote))
    if quote.ok:
        cards.extend(quote.cards)
        answer = (
            f"**{stock.get('name', stock['symbol'])}（{stock['market']}/{stock['symbol']}）**"
            f" 当前价 **{quote.data['price']}**，涨跌幅 {quote.data['change_pct']}。"
            + _DISCLAIMER
        )
    else:
        answer = f"行情数据暂不可用（{stock['market']}/{stock['symbol']}），请稍后再试。" + _DISCLAIMER

    return OrchestratorResult(answer=answer, tool_events=events, cards=cards)


async def _handle_news(msg: str, db: AsyncSession, user_id: uuid.UUID) -> OrchestratorResult:
    hint = _extract_stock_hint(msg)
    events: list = []
    cards:  list = []

    if not hint:
        return OrchestratorResult(
            answer="请告诉我您想查询哪只股票的新闻，例如：688146 最新新闻？" + _DISCLAIMER,
        )

    resolve = await _registry.call("resolve_stock_tool", db,
                                   query=hint.get("query", ""),
                                   market=hint.get("market", "CN"))
    events.append(_result_tool_event(resolve))
    stock = resolve.data if resolve.ok else {
        "market": hint.get("market", "CN"),
        "symbol": hint.get("symbol", ""),
        "name":   hint.get("name", ""),
    }

    news = await _registry.call("get_latest_news_tool", db,
                                 market=stock["market"], symbol=stock["symbol"],
                                 hours_back=72, limit=8)
    events.append(_result_tool_event(news))

    if news.ok and news.data and news.data.get("items"):
        items = news.data["items"]
        rows  = "\n".join(
            f"- **{it['title']}**（{it.get('source', '')} · {it.get('publish_time', '')[:10]}）"
            for it in items[:6] if it.get("title")
        )
        answer = (
            f"**{stock.get('name', stock['symbol'])}** 近72小时新闻（{news.data['count']} 条）：\n\n"
            + rows
            + _DISCLAIMER
        )
    else:
        answer = "暂无近期新闻，请稍后再试。" + _DISCLAIMER

    return OrchestratorResult(answer=answer, tool_events=events, cards=cards)


def _unavailable_official_news_result(*, reason_code: str, message: str, route: str) -> OrchestratorResult:
    answer = (
        "## 结论摘要\n\n"
        f"{message}\n\n"
        "## 近期官方事件\n\n"
        "暂无可展示事件。\n\n"
        "## 事件可能影响与已知事实\n\n"
        "没有已批准来源支持该问题，因此不进行影响推断。\n\n"
        "## 数据范围与局限\n\n"
        "仅允许使用已持久化的 CNINFO 官方披露与已索引官方报告；"
        "未使用财经媒体、网页新闻聚合或模型记忆补充事实。\n\n"
        "## 来源\n\n"
        "无可用的已批准来源。"
        + _DISCLAIMER
    )
    return OrchestratorResult(
        answer=answer,
        metadata={
            "route": route,
            "fulfillment": "unavailable",
            "reason_code": reason_code,
            "scope": "unapproved_industry_theme_research" if route == "industry_news" else route,
            "sources": [],
            "as_of": None,
            "limitations": ["当前没有已批准的行业、市场或主题新闻来源。"],
            "requires_symbol": False,
            "coverage": "approved_cninfo_only",
            "quality": "unavailable",
        },
    )


async def _handle_official_company_research(
    msg: str,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> OrchestratorResult:
    """Answer from persisted CNINFO metadata only; no provider or LLM call."""
    route = "official_report_analysis" if _OFFICIAL_REPORT_ANALYSIS_RE.search(msg) else "official_company_events"
    resolved = await security_entity_resolver.resolve(db, msg, market_hint="CN", min_confidence=0.72)
    if resolved.get("ambiguity"):
        return _unavailable_official_news_result(
            reason_code="AMBIGUOUS_COMPANY",
            message="无法唯一确认目标公司，未查询或生成官方事件。",
            route=route,
        )
    entities = resolved.get("entities") or []
    if not entities:
        return _unavailable_official_news_result(
            reason_code="COMPANY_NOT_RESOLVED",
            message="无法从已持久化证券主数据确认目标公司，未查询或生成官方事件。",
            route=route,
        )

    entity = entities[0]
    market = str(getattr(entity, "market", "") or "CN").upper()
    symbol = str(getattr(entity, "symbol", "") or "")
    company_name = str(
        getattr(entity, "short_name", "")
        or getattr(entity, "full_name", "")
        or symbol
    )
    result = await official_company_event_service.list_persisted_events(
        db,
        market=market,
        symbol=symbol,
        company_name=company_name,
        limit=8,
    )
    events = result.get("events") or []
    fulfillment = result.get("fulfillment") or "unavailable"
    reason_code = result.get("reason_code")
    requested_event_types = {
        event_type
        for event_type, pattern in _REQUESTED_OFFICIAL_EVENT_TYPES
        if pattern.search(msg)
    }
    if requested_event_types and events:
        events = [event for event in events if event.get("event_type") in requested_event_types]
        if not events:
            return _unavailable_official_news_result(
                reason_code="NO_MATCHING_PERSISTED_CNINFO_EVENTS",
                message=(
                    f"已持久化 CNINFO 数据中未找到 {company_name} 与所询问事件类型匹配的官方披露，"
                    "未使用其它公告或新闻替代。"
                ),
                route=route,
            )
    if not events:
        return _unavailable_official_news_result(
            reason_code=reason_code or "NO_PERSISTED_CNINFO_EVENTS",
            message=f"未找到 {company_name} 可公开展示的已持久化 CNINFO 官方事件，未补充或编造事件。",
            route=route,
        )

    event_lines = "\n".join(
        f"- **公告标题：** {event['title']}  \n"
        f"  **发布日期：** {event['published_at']}  \n"
        f"  **事件类型：** {event['event_type']}  \n"
        f"  **官方来源链接：** {event['source_url']}"
        for event in events
    )
    fact_lines = "\n".join(
        f"- {event['published_at']}：已确认 CNINFO 披露《{event['title']}》；"
        "仅确认公告元数据，不从标题推断确定性市场影响。"
        for event in events[:5]
    )
    as_of_text = result.get("as_of") or "unavailable"
    coverage_note = (
        "本回答仅覆盖系统中已持久化且同时具有披露日期和 CNINFO 官方链接的记录。"
        "未触发任何实时抓取。"
    )
    if route == "official_report_analysis":
        fulfillment = "partial"
        reason_code = "REPORT_RAG_EVIDENCE_NOT_RENDERED"
        coverage_note += (
            " 当前确定性路径展示官方报告事件元数据；报告正文重点仅在既有 Report RAG "
            "具备可引用证据时由原有报告分析链路提供，本回答不以标题代替正文分析。"
        )

    answer = (
        "## 结论摘要\n\n"
        f"找到 {company_name} {len(events)} 项可核验的近期官方披露。"
        f"当前履约状态为 `{fulfillment}`。\n\n"
        "## 近期官方事件\n\n"
        f"{event_lines}\n\n"
        "## 事件可能影响与已知事实\n\n"
        f"{fact_lines}\n\n"
        "## 数据范围与局限\n\n"
        f"{coverage_note} 数据快照时间：{as_of_text}。不对事件作投资建议或确定性影响判断。\n\n"
        "## 来源\n\n"
        "上述每项事件均来自 CNINFO 官方来源链接，发布日期随事件逐项列示。"
        + _DISCLAIMER
    )
    public_events = [dict(event) for event in events]
    return OrchestratorResult(
        answer=answer,
        tool_events=[{
            "name": route,
            "status": "success" if fulfillment == "fulfilled" else "partial",
            "detail": f"读取 {len(events)} 项已持久化 CNINFO 官方事件",
            "event_type": "tool_completed",
            "permission_level": "read_only",
            "ok": True,
            "source": "CNINFO",
        }],
        metadata={
            "route": route,
            "fulfillment": fulfillment,
            "reason_code": reason_code,
            "coverage": result.get("coverage"),
            "quality": "partial" if route == "official_report_analysis" else result.get("quality"),
            "as_of": result.get("as_of"),
            "events": public_events,
        },
    )


def _format_grounded_fact(
    label: str,
    fact: dict,
    *,
    module: str,
    metric: str,
) -> tuple[str, dict, dict] | None:
    evidence = make_request_local_evidence(module=module, metric=metric, fact=fact)
    if evidence is None:
        return None
    unit = evidence.get("unit") or ""
    as_of = evidence["as_of"]
    display_value = evidence["display_value"]
    report_period = module == "financial"
    period_label = "报告期" if report_period else "数据日期"
    line = f"- **{label}：** {display_value}{unit}（{period_label}：{as_of}；来源：Tushare）"
    claim = claim_from_evidence(evidence)
    claim["rendered_text"] = line
    return line, evidence, claim


async def _handle_stock_eod_research(
    msg: str,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> OrchestratorResult:
    """Deterministic EOD research; no LLM numeric completion or news fallback."""
    resolved = await security_entity_resolver.resolve(db, msg, market_hint="CN", min_confidence=0.72)
    if resolved.get("ambiguity"):
        return OrchestratorResult(
            answer="无法唯一确认目标公司，未查询或生成盘后事实。" + _DISCLAIMER,
            metadata={"route": "stock_eod_research", "fulfillment": "unavailable", "reason_code": "AMBIGUOUS_COMPANY"},
        )
    entities = resolved.get("entities") or []
    if not entities:
        return OrchestratorResult(
            answer="无法从证券主数据可靠确认目标公司，未查询或生成盘后事实。" + _DISCLAIMER,
            metadata={"route": "stock_eod_research", "fulfillment": "unavailable", "reason_code": "COMPANY_NOT_RESOLVED"},
        )
    entity = entities[0]
    market = str(getattr(entity, "market", "") or "CN").upper()
    symbol = str(getattr(entity, "symbol", "") or "")
    company_name = str(getattr(entity, "short_name", "") or getattr(entity, "full_name", "") or symbol)
    snapshot = await tushare_eod_gateway.get_company_snapshot(market, symbol)
    modules = snapshot.get("modules") or {}
    quote = modules.get("quote") or {}
    valuation = modules.get("valuation") or {}
    financial = modules.get("financial") or {}

    quote_labels = {
        "close": "最近交易日收盘", "change": "涨跌额", "pct_chg": "涨跌幅",
        "vol": "成交量", "amount": "成交额",
    }
    valuation_labels = {
        "pe_ttm": "市盈率 TTM", "pb": "市净率", "ps_ttm": "市销率 TTM",
        "turnover_rate": "换手率", "total_mv": "总市值", "circ_mv": "流通市值",
    }
    financial_labels = {
        "roe": "ROE", "roe_waa": "加权 ROE", "roa": "ROA",
        "grossprofit_margin": "毛利率", "netprofit_margin": "净利率",
        "debt_to_assets": "资产负债率", "netprofit_yoy": "净利润同比",
    }
    rendered = []
    for module_key, module_data, labels in (
        ("quote", quote, quote_labels),
        ("valuation", valuation, valuation_labels),
        ("financial", financial, financial_labels),
    ):
        for key, label in labels.items():
            item = _format_grounded_fact(
                label, (module_data.get("fields") or {}).get(key, {}), module=module_key, metric=key
            )
            if item is not None:
                rendered.append((module_key, *item))
    quote_lines = [line for module_key, line, _, _ in rendered if module_key == "quote"]
    valuation_lines = [line for module_key, line, _, _ in rendered if module_key == "valuation"]
    financial_lines = [line for module_key, line, _, _ in rendered if module_key == "financial"]
    evidence_basis = [evidence for _, _, evidence, _ in rendered]
    checked_claims = [claim for _, _, _, claim in rendered]

    official = await official_company_event_service.list_persisted_events(
        db, market=market, symbol=symbol, company_name=company_name, limit=5
    )
    event_lines = [
        f"- {event['published_at']}：《{event['title']}》（[CNINFO 官方来源]({event['source_url']}））"
        for event in (official.get("events") or [])
    ]
    eod_fact_lines = quote_lines + valuation_lines + financial_lines
    factual_sections = eod_fact_lines + event_lines
    fulfillment = snapshot.get("fulfillment") if eod_fact_lines else ("partial" if event_lines else "unavailable")
    reason_code = snapshot.get("reason_code") if fulfillment == "unavailable" else (
        "PARTIAL_EOD_COVERAGE" if fulfillment == "partial" else None
    )
    answer = (
        "## 结论摘要\n\n"
        + (f"{company_name}（{symbol}）已取得可追溯的最近交易日或财务披露数据；当前状态为 `{fulfillment}`。"
           if factual_sections else f"{company_name}（{symbol}）当前没有已验证的盘后或财务事实。")
        + "\n\n## 最近交易日表现\n\n" + ("\n".join(quote_lines) or "暂缺已验证的最近交易日行情。")
        + "\n\n## 估值与交易活跃度（仅可用字段）\n\n" + ("\n".join(valuation_lines) or "暂缺已验证的估值与交易活跃度数据。")
        + "\n\n## 最近已披露财务指标\n\n" + ("\n".join(financial_lines) or "暂缺已验证的财务指标。")
        + "\n\n## 近期官方公告/报告事实\n\n" + ("\n".join(event_lines) or "已持久化 CNINFO 数据中暂无可展示事件。")
        + "\n\n## 数据范围与限制\n\n数据为最近可取得的盘后 EOD 或已披露报告期数据，不是实时行情；"
          "未调用 Tushare news、公开网页新闻源或模型记忆补充数字。"
        + f"\n\n## 来源与 as_of\n\nTushare EOD 数据截至 {snapshot.get('as_of') or 'unavailable'}；"
          f"CNINFO 快照截至 {official.get('as_of') or 'unavailable'}。"
        + _DISCLAIMER
    )
    numeric_validation = validate_stock_eod_numeric_claims(
        answer,
        evidence_basis,
        checked_claims,
        symbol=symbol,
        allowed_metadata_dates=[
            value for value in (snapshot.get("as_of"), official.get("as_of")) if isinstance(value, str)
        ],
    )
    if not numeric_validation["valid"]:
        fulfillment = "partial"
        reason_code = "NUMERIC_EVIDENCE_VALIDATION_FAILED"
        answer = (
            f"## 结论摘要\n\n{company_name}（{symbol}）的部分结构化数据未通过本次请求的数值证据校验，"
            "未经验证的数字未展示。\n\n## 数据范围与限制\n\n当前仅保留安全降级结果，请稍后重试。"
            + _DISCLAIMER
        )
    return OrchestratorResult(
        answer=answer,
        tool_events=[{
            "name": "stock_eod_research", "status": fulfillment, "event_type": "tool_completed",
            "permission_level": "read_only", "ok": fulfillment in {"fulfilled", "partial"}, "source": "tushare+CNINFO",
        }],
        metadata={
            "route": "stock_eod_research", "fulfillment": fulfillment, "reason_code": reason_code,
            "market": market, "symbol": symbol, "company_name": company_name,
            "as_of": snapshot.get("as_of"), "source": ["tushare", "CNINFO"],
            "eod": snapshot, "official_events": official.get("events") or [],
            "numeric_validation": numeric_validation,
        },
    )


async def _handle_recent_report(msg: str, db: AsyncSession, user_id: uuid.UUID) -> OrchestratorResult:
    events: list = []
    cards:  list = []

    hint = _extract_stock_hint(msg)
    rpt = await _registry.call("get_recent_reports_tool", db,
                                user_id=str(user_id),
                                market=hint.get("market", "CN") if hint else "CN",
                                symbol=hint.get("symbol", "") if hint else "",
                                limit=5)
    events.append(_result_tool_event(rpt))
    if rpt.ok:
        cards.extend(rpt.cards)

    if rpt.ok and rpt.data and rpt.data.get("count", 0) > 0:
        answer = f"找到 **{rpt.data['count']}** 份历史报告。" + _DISCLAIMER
    else:
        answer = "暂未找到历史报告。可输入「帮我生成综合报告」创建新报告。" + _DISCLAIMER

    return OrchestratorResult(answer=answer, tool_events=events, cards=cards)


# ── Write intent handlers (confirmation flow, no real side effects) ────────────

async def _handle_report(msg: str, db: AsyncSession, user_id: uuid.UUID) -> OrchestratorResult:
    """Generate-report intent: resolve stock then ask for confirmation."""
    hint = _extract_stock_hint(msg)
    events: list = []

    resolve = await _registry.call("resolve_stock_tool", db,
                                   query=hint.get("query", "688146") if hint else "688146",
                                   market=hint.get("market", "CN") if hint else "CN")
    events.append(_result_tool_event(resolve))
    stock = resolve.data if resolve.ok else {
        "market": hint.get("market", "CN") if hint else "CN",
        "symbol": hint.get("symbol", "688146") if hint else "688146",
        "name":   hint.get("name", "未知股票") if hint else "未知股票",
    }

    return OrchestratorResult(
        answer="",
        tool_events=events,
        cards=[],
        confirmation=make_confirmation(
            action_type="create_analysis_run",
            text=(
                f"我将为 **{stock['name']}（{stock['market']}/{stock['symbol']}）**"
                " 生成综合分析报告，预计需要 30~60 秒。是否确认？"
            ),
            params=stock,
        ),
    )


async def _handle_watchlist_add(msg: str, db: AsyncSession, user_id: uuid.UUID) -> OrchestratorResult:
    """Add-to-watchlist intent: resolve stock, check duplicate, then confirm."""
    hint = _extract_stock_hint(msg)
    events: list = []

    resolve = await _registry.call("resolve_stock_tool", db,
                                   query=hint.get("query", "688146") if hint else "688146",
                                   market=hint.get("market", "CN") if hint else "CN")
    events.append(_result_tool_event(resolve))
    stock = resolve.data if resolve.ok else {
        "market": hint.get("market", "CN") if hint else "CN",
        "symbol": hint.get("symbol", "688146") if hint else "688146",
        "name":   hint.get("name", "未知股票") if hint else "未知股票",
    }

    # Check duplicate
    wl = await _registry.call("get_watchlist_tool", db,
                               user_id=str(user_id), symbol=stock["symbol"])
    events.append(_result_tool_event(wl))
    already_in = wl.ok and wl.data and wl.data.get("already_in", False)

    if already_in:
        return OrchestratorResult(
            answer=(
                f"**{stock['name']}（{stock['market']}/{stock['symbol']}）**"
                " 已在你的自选股中。" + _DISCLAIMER
            ),
            tool_events=events,
        )

    return OrchestratorResult(
        answer="",
        tool_events=events,
        cards=[],
        confirmation=make_confirmation(
            action_type="add_watchlist",
            text=(
                f"我将把 **{stock['name']}（{stock['market']}/{stock['symbol']}）**"
                " 加入你的自选股，是否确认？"
            ),
            params=stock,
        ),
    )


def _extract_compare_candidates(msg: str, memory_context=None) -> list[str]:
    """
    Extract candidate stock names/codes from a compare query.
    Returns up to 4 candidates (names or 5-6-digit codes).

    C32.2.2/C32.2.3: handles:
    - A follow-up comparison after coreference has injected the prior entity
    - "请对比五粮液和贵州茅台的股票" (with "的股票" suffix noise)
    - Numeric code extraction

    C32.3.1: When text has stock pronouns AND memory has active_entities, inject
    the entity as a candidate even if coreference resolution didn't fire.
    """
    # Step 1: extract codes from coreference-injected parentheticals.
    paren_codes = re.findall(r'[（(](?:CN|HK)[:/](\d{4,6})[）)]', msg)
    # Also extract bare 5-6-digit codes
    bare_codes = re.findall(r'\b(\d{5,6})\b', msg)
    all_codes = list(dict.fromkeys(paren_codes + bare_codes))  # dedup, preserve order
    if len(all_codes) >= 2:
        return all_codes[:4]

    # Step 2: clean noise words (keep names, remove intent/trailing noise)
    cleaned = re.sub(
        r"对比|比较|帮我|请|还是|vs\.?\s*|versus\s*|相比|之间|进行|那|吗|呢|啊|啦"
        r"|的\s*股票|的\s*研究",
        " ", msg, flags=re.IGNORECASE,
    )
    # Remove coreference parentheticals; the name is already kept before them.
    cleaned = re.sub(r'[（(](?:CN|HK)[:/]\d{4,6}[）)]', ' ', cleaned)

    # Step 3: split on all separators including "和"/"与" (treated as delimiters)
    parts = re.split(r"[、，,和与\s]+", cleaned.strip())
    result = list(dict.fromkeys(  # dedup while preserving order
        p.strip() for p in parts if 2 <= len(p.strip()) <= 20
    ))

    # C32.3.1: Fallback — if still < 2 candidates AND the message contains a
    # stock pronoun, inject the most recent active entity from memory.
    # This handles cases where coreference resolution didn't fire (empty memory
    # at build time) but the intent is clearly a compare with a prior stock.
    if len(result) < 2 and memory_context is not None:
        _STOCK_PRONOUNS = re.compile(
            r"它(?:的|们)?|这只|这支|该股|这家公司|这家|这个股票"
            r"|这只股|此股|那只|那支|该公司",
            re.IGNORECASE,
        )
        if _STOCK_PRONOUNS.search(msg):
            stocks = [
                e for e in (getattr(memory_context, "active_entities", None) or [])
                if getattr(e, "type", "") == "stock"
            ]
            for ent in stocks:
                code = getattr(ent, "code", "")
                name = getattr(ent, "name", "")
                # Only inject if not already in result
                if code and code not in result and name not in result:
                    result.insert(0, code)
                    break

    return result[:4]


async def _handle_compare(msg: str, db: AsyncSession, user_id: uuid.UUID, **kw) -> OrchestratorResult:
    """
    Compare intent: extract stocks dynamically from user message then confirm.
    C32.1.4: replaced hardcoded stub with real ResolveStockTool resolution.
    C32.3.1: accepts memory_context kwarg to enable entity fallback injection.
    """
    events: list = []
    candidates = _extract_compare_candidates(msg, memory_context=kw.get("memory_context"))

    if len(candidates) < 2:
        return OrchestratorResult(
            answer=(
                "抱歉，我需要至少 2 只股票才能进行对比。"
                "请提供股票名称或代码，例如：「对比贵州茅台和五粮液」。"
                + _DISCLAIMER
            ),
            tool_events=events,
        )

    stocks: list = []
    for cand in candidates[:4]:
        resolve = await _registry.call("resolve_stock_tool", db, query=cand)
        events.append(_result_tool_event(resolve))
        if resolve.ok and resolve.data:
            stocks.append({
                "name":   resolve.data.get("name", cand),
                "market": resolve.data.get("market", "CN"),
                "symbol": resolve.data.get("symbol", ""),
            })

    if len(stocks) < 2:
        return OrchestratorResult(
            answer=(
                f"我尝试识别了以下关键词：{'、'.join(candidates[:4])}，"
                "但未能找到足够的股票信息。"
                "请提供完整名称或标准股票代码后再比较。"
                + _DISCLAIMER
            ),
            tool_events=events,
        )

    compare_url = "/compare?stocks=" + ",".join(
        f"{s['market']}:{s['symbol']}" for s in stocks if s["symbol"]
    )
    stock_desc = "、".join(
        (f"{s['name']}（{s['symbol']}）" if s["symbol"] else s["name"])
        for s in stocks
    )
    events.append(_tool_event("create_compare_selection_tool", f"已准备 {len(stocks)} 只股票对比"))

    return OrchestratorResult(
        answer="",
        tool_events=events,
        cards=[],
        confirmation=make_confirmation(
            action_type="create_compare",
            text=f"我将打开对比页，从研究维度对比 **{stock_desc}**，是否确认？",
            params={"stocks": stocks, "compare_url": compare_url},
        ),
    )


def _match_analysis_save_report(msg: str) -> bool:
    return bool(re.search(
        r"分析.{0,20}(并|然后|同时).{0,20}(保存|存|生成).{0,10}(历史报告|报告)"
        r"|保存.{0,10}(到|至).{0,10}(历史报告|报告)"
        r"|生成.{0,10}报告.{0,10}(并|然后).{0,10}保存"
        r"|分析完.{0,10}(保存|存|入库)",
        msg,
    ))


async def _handle_analysis_save_report(
    msg: str, db: AsyncSession, user_id: uuid.UUID
) -> OrchestratorResult:
    """
    'Analyze and save to history report' intent.
    Resolves the stock, determines scope, then asks confirmation before
    running the full analysis pipeline + persisting the report.
    """
    hint = _extract_stock_hint(msg)
    events: list = []

    if hint:
        resolve = await _registry.call(
            "resolve_stock_tool", db,
            query=hint.get("query", "688146"),
            market=hint.get("market", "CN"),
        )
        events.append(_result_tool_event(resolve))
        stock = resolve.data if resolve.ok else {
            "market": hint.get("market", "CN"),
            "symbol": hint.get("symbol", "688146"),
            "name":   hint.get("name", "未知股票"),
        }
    else:
        stock = {"market": "CN", "symbol": "688146", "name": "未知股票"}

    # Infer scope from message
    if re.search(r"基本面", msg):
        scope = "fundamental"
    elif re.search(r"技术面", msg):
        scope = "technical"
    else:
        scope = "comprehensive"

    params = {**stock, "scope": scope, "save_to_history": True, "requested_from": "chat_agent"}

    return OrchestratorResult(
        answer="",
        tool_events=events,
        cards=[],
        confirmation=make_confirmation(
            action_type="create_analysis_run",
            text=(
                f"我将对 **{stock['name']}（{stock['market']}/{stock['symbol']}）**"
                f" 执行 {scope} 分析并自动保存至历史报告，预计需要 30~60 秒。是否确认？"
            ),
            params=params,
        ),
    )


def _match_external_channel(msg: str) -> bool:
    return bool(re.search(
        r"发(到|给|至).{0,10}(邮箱|邮件|email|mail|微信|wechat|钉钉|飞书|slack|telegram)"
        r"|(邮箱|邮件|email|mail|微信|wechat|钉钉|飞书|slack|telegram).{0,10}(发送|推送|通知|分享)",
        msg,
        re.IGNORECASE,
    ))


async def _handle_external_channel(
    msg: str, db: AsyncSession, user_id: uuid.UUID
) -> OrchestratorResult:
    """
    External channel push intent (email/WeChat/etc.).
    Politely declines — external sending is not supported in this version.
    """
    return OrchestratorResult(
        answer=(
            "目前系统暂不支持向外部渠道（邮件、微信、钉钉等）推送报告。\n\n"
            "你可以在「历史报告」页面查看完整报告，并通过页面「导出」功能下载 Markdown 文件后自行分享。"
            + _DISCLAIMER
        ),
    )


async def _handle_default(msg: str, db: AsyncSession, user_id: uuid.UUID) -> OrchestratorResult:
    return OrchestratorResult(
        answer=(
            "你好！我是 TradingAgents Chat Copilot，可以帮你完成以下研究任务：\n\n"
            "- **股票行情查询**：例如：688146 现在多少钱\n"
            "- **股票异动分析**：例如：中船特气最近为什么涨这么多\n"
            "- **最新新闻**：例如：688146 最新消息\n"
            "- **生成研究报告**：例如：帮我生成 688146 的综合报告\n"
            "- **加入自选股**：例如：把中船特气加入自选\n"
            "- **查看自选股**：例如：我的自选股\n"
            "- **多股对比**：例如：对比宁德时代、紫金矿业\n"
            "- **行业热点**：例如：今天哪些行业值得关注\n"
            + _DISCLAIMER
        ),
    )


async def _handle_trading_request(
    msg: str, db: AsyncSession, user_id: uuid.UUID
) -> OrchestratorResult:
    """
    Safety handler: intercept explicit trading / price-prediction requests.
    Returns a clear boundary statement without any write-tool side effects.
    """
    return OrchestratorResult(
        answer=(
            "系统不提供交易指令或价格预测，仅支持研究辅助、风险拆解和数据解释。\n\n"
            "可以帮你做的研究工作：\n"
            "- **异动分析**：近期行情原因梳理\n"
            "- **新闻解读**：最新公告与事件影响\n"
            "- **综合研究报告**：基本面 / 技术面 / 同行对比\n"
            "- **行业热度研究**：板块整体研究线索"
            + _DISCLAIMER
        ),
    )


# ── Scenario tables (split for C6 ordering) ───────────────────────────────────

# Action intents: write-side operations that require confirmation
_ACTION_INTENTS: list[tuple[Callable[[str], bool], Callable]] = [
    (_match_analysis_save_report, _handle_analysis_save_report),  # C11: analyze+save must come before _match_report
    (_match_report,               _handle_report),
    (_match_watchlist_add,        _handle_watchlist_add),
    (_match_compare,              _handle_compare),
    (_match_external_channel,     _handle_external_channel),
]

# Direct read-only fallbacks (C4 handlers, used when no Skill matches)
_DIRECT_INTENTS: list[tuple[Callable[[str], bool], Callable]] = [
    (_match_recent_report,  _handle_recent_report),
    (_match_watchlist_view, _handle_watchlist_view),
    (_match_news,           _handle_news),
    (_match_quote,          _handle_quote),
    (_match_industry,       _handle_industry),
    (_match_anomaly,        _handle_anomaly),
]

# Legacy alias kept for backwards-compat (C4/C5 tests import _INTENTS)
_INTENTS: list[tuple[Callable[[str], bool], Callable]] = [
    (_match_trading_request, _handle_trading_request),
    *_ACTION_INTENTS,
    *_DIRECT_INTENTS,
]


# ── Public API ─────────────────────────────────────────────────────────────────

async def process_message(
    content: str,
    db: AsyncSession,
    user_id: uuid.UUID,
    output_language: str = "zh-CN",
    session_id: uuid.UUID | None = None,
    event_callback: Callable | None = None,
    shadow_result_callback: Callable | None = None,
) -> OrchestratorResult:
    """
    Route user message to appropriate intent handler with real tool calls.

    Priority order (C7/C8):
      1. Safety guard — always first
      2. Action intents (write ops → confirmation)
      3. Controlled Planner — compound multi-step research tasks
      4. SkillRegistry — Financial Research Skills (single-step)
      5. C4 direct fallback intents
      6. Default greeting

    C8: session_id (optional) enables structured memory writes at key nodes.
    C13-a: event_callback (optional) async callable(event_type, payload) for
           streaming fine-grained events.  Never raises.
    """
    msg = content.strip().lower()

    async def _emit(event_type: str, payload: dict) -> None:
        """Safe wrapper — callback failures never block the main flow."""
        if event_callback is None:
            return
        try:
            await event_callback(event_type, payload)
        except Exception:
            log.debug("process_message: event_callback raised for %s", event_type)

    # 1. Safety guard — always first
    if _match_trading_request(msg):
        await _emit("intent_detected", {"intent": "safety_blocked", "handler": "_handle_trading_request"})
        return await _handle_trading_request(msg, db, user_id)

    # Phase 7C1 source-governance gate.  These checks run before memory,
    # entity resolution, skills, and tools so unapproved news requests cannot
    # fall through to AKShare/Eastmoney/Sina/Tencent-backed paths.
    if _UNAPPROVED_NEWS_SCOPE_RE.search(content) or _UNAPPROVED_THEME_SCOPE_RE.search(content):
        await _emit("intent_detected", {
            "intent": "industry_news",
            "handler": "source_governance_unavailable",
        })
        return _unavailable_official_news_result(
            reason_code="NO_APPROVED_INDUSTRY_NEWS_SOURCE",
            message="当前没有已批准的行业、市场或主题新闻来源，无法完成该问题。",
            route="industry_news",
        )

    if _OFFICIAL_EVENT_TERMS_RE.search(content):
        route = "official_report_analysis" if _OFFICIAL_REPORT_ANALYSIS_RE.search(content) else "official_company_events"
        await _emit("intent_detected", {"intent": route, "handler": "_handle_official_company_research"})
        return await _handle_official_company_research(content, db, user_id)

    if _STOCK_EOD_RESEARCH_RE.search(content):
        await _emit("intent_detected", {"intent": "stock_eod_research", "handler": "_handle_stock_eod_research"})
        return await _handle_stock_eod_research(content, db, user_id)

    # C31.3 — Emit problem_analysis thinking event BEFORE intent classification
    # so the frontend can show the first step immediately while we compute.
    # The content is a lightweight query analysis; full plan follows below.
    await _emit("thinking_event", {
        "phase":      "problem_analysis",
        "title":      "问题分析",
        "content":    f"正在理解用户问题：{content[:80].strip()}",
        "status":     "running",
        "agent":      "",
        "importance": "high",
    })

    # Fast deterministic official-report setup/PDF paths must not wait on
    # memory/entity resolver DB work; A01 follow-up can recover entity from
    # persisted recent user messages using an independent short transaction.
    _early_entity_hint = _unambiguous_report_entity_hint(content)
    if not _early_entity_hint and _match_official_report_pdf_shadow_candidate(content):
        _early_entity_hint = await _recent_unambiguous_report_entity_hint(
            db,
            session_id=session_id,
            current_query=content,
        )
    # P0-C fix: queries matching _LATEST_REPORT_SETUP_PATTERN are analysis intents
    # ("最新财报表现如何", "最近年报怎么样") and must reach ReportExplanationSkill
    # via the SkillRegistry.  The former early-return path returned partial_success
    # after only resolving the report context, without invoking any analysis agent.
    # These queries now fall through to the full orchestrator / SkillRegistry path.
    if (
        db is not None
        and _early_entity_hint
        and _match_official_report_pdf_shadow_candidate(content)
        # R1.1-B: do NOT route to PDF locator when query expresses analysis intent.
        # "分析茅台年报盈利能力" contains "年报" (PDF pattern) but the dominant intent
        # is financial analysis, which belongs to ReportExplanationSkill.
        and not _PDF_ANALYSIS_OVERRIDE_RE.search(content)
    ):
        _early_entity = _entity_payload_from_hint(_early_entity_hint, source=_early_entity_hint.get("source") or "early_recent_session_hint")
        _early_entity_payload = {
            "chat_entity_pipeline_version": _CHAT_ENTITY_PIPELINE_VERSION,
            "raw_query": content,
            "effective_query": content,
            "resolver_called": False,
            "resolver_result_count": 1,
            "resolved_entities": [_early_entity],
            "primary_entity": _early_entity,
            "context_source": _early_entity["source"],
            "failure_reason": "",
        }
        if (getattr(settings, "agent_executor_mode", "legacy") or "legacy").strip().lower() == "pi_compatible_shadow":
            _schedule_pi_official_report_shadow(
                content=content,
                effective_content=content,
                session_id=session_id,
                user_id=user_id,
                entity_payload=_early_entity_payload,
                output_language=output_language,
                shadow_result_callback=shadow_result_callback,
            )
        await _emit("intent_detected", {"intent": "official_report_pdf_direct", "handler": "_handle_official_report_pdf_direct"})
        return await _handle_official_report_pdf_direct(
            content,
            db,
            user_id,
            entity_hint=_early_entity_hint,
            session_id=session_id,
        )

    # C32.1: Build memory context (fire-and-forget on failure; returns empty ctx on error)
    from app.services.conversation_memory_service import MemoryContext, build_memory_context  # noqa: PLC0415
    try:
        _memory_ctx = await asyncio.wait_for(
            build_memory_context(db, session_id, user_id, content),
            timeout=4.0,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "process_message: memory context unavailable session=%s error_class=%s",
            session_id,
            type(exc).__name__,
        )
        try:
            await asyncio.wait_for(db.rollback(), timeout=3.0)
        except Exception as rollback_exc:  # noqa: BLE001
            log.warning(
                "process_message: memory context rollback unavailable session=%s error_class=%s",
                session_id,
                type(rollback_exc).__name__,
            )
            pass
        _memory_ctx = MemoryContext(resolved_query=content)
    # Use the coreference-resolved query for routing when available
    _effective_content = _memory_ctx.resolved_query or content
    try:
        _entity_payload = await asyncio.wait_for(
            _resolve_current_query_entities(
                db,
                raw_query=content,
                effective_query=_effective_content,
                memory_context=_memory_ctx,
            ),
            timeout=6.0,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "process_message: entity resolver unavailable session=%s error_class=%s",
            session_id,
            type(exc).__name__,
        )
        try:
            await asyncio.wait_for(db.rollback(), timeout=3.0)
        except Exception as rollback_exc:  # noqa: BLE001
            log.warning(
                "process_message: entity resolver rollback unavailable session=%s error_class=%s",
                session_id,
                type(rollback_exc).__name__,
            )
            pass
        _entity_payload = {
            "chat_entity_pipeline_version": _CHAT_ENTITY_PIPELINE_VERSION,
            "raw_query": content,
            "effective_query": _effective_content,
            "resolver_called": True,
            "resolver_result_count": 0,
            "resolved_entities": [],
            "primary_entity": None,
            "context_source": "none",
            "failure_reason": f"RESOLVER_TIMEOUT_OR_ERROR:{type(exc).__name__}",
        }
    _is_official_report_shadow_query = (
        _match_official_report_pdf_shadow_candidate(_effective_content)
        or _match_official_report_pdf_shadow_candidate(content)
    )
    _official_report_entity_hint = _entity_hint_from_payload_or_memory(_entity_payload, _memory_ctx, content)
    if _is_official_report_shadow_query and not _official_report_entity_hint:
        _official_report_entity_hint = await _recent_unambiguous_report_entity_hint(
            db,
            session_id=session_id,
            current_query=content,
        )
        if _official_report_entity_hint:
            entity = _entity_payload_from_hint(
                _official_report_entity_hint,
                source=_official_report_entity_hint.get("source") or "recent_session_user_message",
            )
            _entity_payload.update({
                "resolver_result_count": 1,
                "resolved_entities": [entity],
                "primary_entity": entity,
                "context_source": entity["source"],
                "failure_reason": "",
            })

    if (getattr(settings, "agent_executor_mode", "legacy") or "legacy").strip().lower() == "pi_compatible_shadow":
        try:
            from app.agent_runtime.shadow_runner import pi_compatible_shadow_runner  # noqa: PLC0415
            from app.agent_runtime.contracts import new_id  # noqa: PLC0415
            from app.agent_runtime.shadow_correlation import current_correlation  # noqa: PLC0415

            if not pi_compatible_shadow_runner.enabled():
                raise RuntimeError("pi-compatible shadow is not enabled or agent is not allowed")

            _shadow_correlation = current_correlation()
            _shadow_trace_id = _shadow_correlation.get("request_trace_id") or new_id("trace")
            _shadow_run_id = _shadow_correlation.get("shadow_run_id") or new_id("run")
            if not _is_official_report_shadow_query:
                skipped_result = {
                    "schema_version": "pi_financial_runtime_v1",
                    "trace_id": _shadow_trace_id,
                    "run_id": _shadow_run_id,
                    "status": "skipped",
                    "reason": "intent_not_official_report_pdf",
                    "agent_id": "official_report_pdf_pi_v1",
                    "turn_count": 0,
                    "tool_call_count": 0,
                    "events": [],
                    "findings": [],
                    "evidence_ids": [],
                    "error": {"code": "PI_SHADOW_SKIPPED"},
                    "metrics": {"latency_ms": 0, "model_calls": 0, "tool_calls": 0, "input_tokens": 0, "output_tokens": 0},
                    "shadow_input": {
                        "conversation_id": str(session_id) if session_id else "",
                        "message_snapshot": [],
                        "financial_context_snapshot": {},
                        "resolved_entity_snapshot": _entity_payload,
                    },
                }
                try:
                    from app.agent_runtime.shadow_diagnostics import pi_shadow_diagnostics_sink  # noqa: PLC0415

                    pi_shadow_diagnostics_sink.record(
                        raw_query=content,
                        conversation_id=str(session_id) if session_id else "",
                        user_id=str(user_id),
                        result=skipped_result,
                        correlation=_shadow_correlation,
                    )
                except Exception as exc:  # noqa: BLE001
                    log.debug("pi-compatible skipped diagnostics failed: %s", exc)
                if shadow_result_callback is not None:
                    maybe_awaitable = shadow_result_callback(skipped_result)
                    if hasattr(maybe_awaitable, "__await__"):
                        await maybe_awaitable
            else:

                async def _pi_shadow_run() -> None:
                    result: dict | None = None
                    try:
                        result = await pi_compatible_shadow_runner.run_official_report_pdf_shadow_with_new_session(
                            raw_query=content,
                            normalized_query=_effective_content,
                            user_id=str(user_id),
                            conversation_id=str(session_id) if session_id else "",
                            page_context={},
                            memory_context=_memory_ctx,
                            resolved_entity_snapshot=_entity_payload,
                            output_language=output_language,
                            correlation=_shadow_correlation,
                        )
                        log.debug("pi-compatible shadow result: %s", result.get("status"))
                    except asyncio.CancelledError:
                        result = {
                            "trace_id": _shadow_trace_id,
                            "run_id": _shadow_run_id,
                            "status": "cancelled",
                            "agent_id": "official_report_pdf_pi_v1",
                            "metrics": {"latency_ms": 0, "model_calls": 0, "tool_calls": 0},
                            "error": {"code": "PI_SHADOW_CANCELLED"},
                            "events": [],
                            "findings": [],
                            "evidence_ids": [],
                            "shadow_input": {"conversation_id": str(session_id) if session_id else ""},
                        }
                        raise
                    except Exception as exc:  # noqa: BLE001
                        result = {
                            "trace_id": _shadow_trace_id,
                            "run_id": _shadow_run_id,
                            "status": "failed",
                            "agent_id": "official_report_pdf_pi_v1",
                            "metrics": {"latency_ms": 0, "model_calls": 0, "tool_calls": 0},
                            "error": {"code": f"PI_SHADOW_{type(exc).__name__.upper()}"},
                            "events": [],
                            "findings": [],
                            "evidence_ids": [],
                            "shadow_input": {"conversation_id": str(session_id) if session_id else ""},
                        }
                        log.debug("pi-compatible shadow task failed: %s", exc)
                    finally:
                        from app.agent_runtime.shadow_diagnostics import pi_shadow_diagnostics_sink  # noqa: PLC0415

                        if result is not None:
                            try:
                                pi_shadow_diagnostics_sink.record(
                                    raw_query=content,
                                    conversation_id=str(session_id) if session_id else "",
                                    user_id=str(user_id),
                                    result=result,
                                    correlation=_shadow_correlation,
                                )
                            except Exception as exc:  # noqa: BLE001
                                log.debug("pi-compatible shadow diagnostics failed: %s", exc)
                    if shadow_result_callback is not None:
                        maybe_awaitable = shadow_result_callback(result)
                        if hasattr(maybe_awaitable, "__await__"):
                            await maybe_awaitable

                task = asyncio.create_task(_pi_shadow_run())

                def _consume_pi_shadow_error(done_task: asyncio.Task) -> None:
                    try:
                        done_task.exception()
                    except asyncio.CancelledError:
                        log.debug("pi-compatible shadow task cancelled")
                    except Exception as exc:  # noqa: BLE001
                        log.debug("pi-compatible shadow task failed: %s", exc)

                task.add_done_callback(_consume_pi_shadow_error)
        except Exception as exc:  # noqa: BLE001
            log.debug("pi-compatible shadow scheduling failed: %s", exc)

    # P0-C fix: do NOT short-circuit here for analysis queries.
    # _match_latest_report_setup_candidate matches "最新财报如何", "最近年报怎么样" etc.
    # which are financial analysis intents, not PDF-find intents.
    # These must reach ReportExplanationSkill via the SkillRegistry path below.

    runtime_mode = (settings.chat_runtime_mode or "legacy").strip().lower()
    if runtime_mode in {"layered_v1", "shadow"}:
        try:
            from app.agents.financial_runtime.runtime import financial_agent_runtime  # noqa: PLC0415

            if runtime_mode == "shadow":
                async def _shadow_run() -> None:
                    result = await financial_agent_runtime.shadow_with_new_session(
                        raw_query=content,
                        user_id=str(user_id),
                        conversation_id=str(session_id) if session_id else "",
                        page_context={},
                        memory_context=_memory_ctx,
                    )
                    log.debug("layered runtime shadow result: %s", result.get("status"))

                asyncio.create_task(_shadow_run())
            else:
                layered = await financial_agent_runtime.run(
                    raw_query=content,
                    db=db,
                    user_id=str(user_id),
                    conversation_id=str(session_id) if session_id else "",
                    page_context={},
                    memory_context=_memory_ctx,
                    event_callback=event_callback,
                )
                if layered.status in {"success", "partial_success", "clarification_required", "failed"}:
                    return OrchestratorResult(
                        answer=layered.answer,
                        tool_events=layered.tool_events,
                        cards=layered.cards,
                        metadata={
                            **(layered.metadata or {}),
                            "status": layered.status,
                            "error_code": layered.error_code,
                            "runtime": "layered_v1",
                        },
                    )
        except Exception as exc:  # noqa: BLE001
            log.warning("layered runtime failed; falling back to legacy: %s", exc)

    # 1.5. C30.2.3: IntentDecisionAgent — classify intent, emit telemetry, drive routing.
    _intent_decision = classify_intent(_effective_content, memory_context=_memory_ctx)
    await _emit("intent_detected", {
        "intent":     _intent_decision.intent,
        "confidence": _intent_decision.confidence,
        "reason":     _intent_decision.reason,
        "handler":    "intent_decision_agent",
    })

    # C31.3 — CentralPlanningAgent: generate entity-aware plan for all 9 phases.
    # Pure computation (no LLM/DB). Used only for thinking_event emission.
    _central_plan = _central_planner.create_plan(
        _effective_content, _intent_decision, memory_context=_memory_ctx
    )

    # C31.3 — Emit problem_analysis (completed, entity-aware content)
    await _emit("thinking_event", _central_plan.get_phase_event("problem_analysis"))

    # C31.3 — Emit intent_decision
    await _emit("thinking_event", _central_plan.get_phase_event("intent_decision"))

    # C31.3 — Emit planning
    await _emit("thinking_event", _central_plan.get_phase_event("planning"))

    # C31.3 — Emit task_decomposition (only if agents are needed)
    if _central_plan.tasks:
        await _emit("thinking_event", _central_plan.get_phase_event("task_decomposition"))

    # C30.2.3: direct_answer → skip report-generation action intents.
    # "帮我分析茅台基本面" is a Q&A request, NOT a report-generation trigger.
    # _handle_report / _handle_analysis_save_report both start a 30-60s pipeline
    # and show a confirmation card — wrong for plain analysis questions.
    # Watchlist, compare, and external-channel intents still run normally.
    _REPORT_ACTION_HANDLERS = frozenset({"_handle_report", "_handle_analysis_save_report"})
    _skip_report_actions = (_intent_decision.intent == "direct_answer")

    # 2. Action intents (write ops → confirmation)
    # C32.2.2: check both original msg AND resolved _effective_content so that
    # pronoun-resolved queries (e.g. "那贵州茅台和五粮液相比呢？") route correctly.
    for matcher, handler in _ACTION_INTENTS:
        if _skip_report_actions and handler.__name__ in _REPORT_ACTION_HANDLERS:
            continue
        if matcher(msg) or (msg != _effective_content.strip().lower() and matcher(_effective_content)):
            try:
                await _emit("intent_detected", {"intent": "action", "handler": handler.__name__})
                # C32.1.2: use resolved query so handlers receive de-pronominalized content.
                # C32.3.1: compare handler also receives memory_context for entity fallback.
                if handler.__name__ == "_handle_compare":
                    result = await handler(_effective_content, db, user_id, memory_context=_memory_ctx)
                else:
                    result = await handler(_effective_content, db, user_id)
                # C8: write memory (fire-and-forget)
                await _write_memory_from_result(db, session_id, user_id, msg, result, output_language)
                return result
            except Exception:
                log.exception("Orchestrator: handler %s failed", handler.__name__)
                return OrchestratorResult(
                    answer="处理请求时发生内部错误，请稍后重试。" + _DISCLAIMER,
                )

    # 2.5 Multi-Agent Orchestrator (Phase 2E-1) — opt-in, default disabled
    # Runs AFTER safety guard and action intents, BEFORE the Planner/Skill path.
    # Only activated when ENABLE_MULTI_AGENT_ORCHESTRATOR=true.
    # Catches all exceptions and falls back to the existing path.
    try:
        from app.agents.orchestrator.financial_orchestrator import (  # noqa: PLC0415
            FinancialOrchestrator, is_orchestrator_enabled,
        )
        from app.agents.orchestrator.schemas import (  # noqa: PLC0415
            build_task_intent, is_complex_financial_query,
        )
        from app.agents.official_report_search import parse_financial_analysis_intent  # noqa: PLC0415

        if is_orchestrator_enabled():
            _base_intent = parse_financial_analysis_intent(content)
            _task_intent = build_task_intent(_base_intent, content)

            if is_complex_financial_query(_task_intent):
                await _emit("intent_detected", {
                    "intent": "multi_agent_orchestrator",
                    "handler": "FinancialOrchestrator",
                })
                _request_id = str(uuid.uuid4())
                _collected_events: list[dict] = []

                async def _orch_callback(event_type: str, payload: dict) -> None:
                    _collected_events.append({"event_type": event_type, **payload})
                    await _emit(event_type, payload)

                _orchestrator = FinancialOrchestrator(
                    db, output_language=output_language
                )
                _orch_result  = await _orchestrator.run_stream(
                    content, _request_id, _orch_callback
                )
                result = OrchestratorResult(
                    answer=_orch_result.get("answer_text", ""),
                    tool_events=_collected_events,
                    cards=[],
                    confirmation=None,
                    metadata={"orchestrator": "multi_agent", "request_id": _request_id},
                )
                await _write_memory_from_result(db, session_id, user_id, msg, result, output_language)
                return result
    except Exception as _orch_exc:
        log.warning(
            "Multi-Agent Orchestrator failed (%s) — falling back to existing path",
            _orch_exc,
        )
        # Fall through to existing Planner / SkillRegistry path

    if _is_official_report_shadow_query and _official_report_entity_hint:
        await _emit("intent_detected", {"intent": "official_report_pdf_direct", "handler": "_handle_official_report_pdf_direct"})
        result = await _handle_official_report_pdf_direct(
            _effective_content,
            db,
            user_id,
            entity_hint=_official_report_entity_hint,
            session_id=session_id,
        )
        await _write_memory_from_result(db, session_id, user_id, msg, result, output_language)
        return result

    # 3. Controlled Planner — compound multi-step research tasks (C7)
    if _planner.is_compound(msg):
        plan = _planner.plan(msg)
        if plan is not None and plan.steps:
            await _emit("planner_started", {"steps": len(plan.steps)})
            context = SkillContext(
                db=db,
                user_id=str(user_id),
                session_id=str(session_id) if session_id else "",
                output_language=output_language,
                tool_registry=_registry,
                metadata={
                    "raw_query": content,
                    "effective_query": _effective_content,
                    "context_update_mode": "transactional",
                    "intent": _intent_decision.intent,
                    **_entity_payload,
                },
                event_callback=event_callback,
                memory_context=_memory_ctx,  # C32.1.1
            )
            try:
                # C32.1.2: use resolved query
                exec_result = await _executor.execute(plan, _effective_content, context)
                result = OrchestratorResult(
                    answer=exec_result.answer,
                    tool_events=exec_result.tool_events,
                    cards=exec_result.cards,
                    confirmation=exec_result.confirmation,
                    metadata=exec_result.metadata,
                )
                # C8: write memory (fire-and-forget)
                await _write_memory_from_result(db, session_id, user_id, msg, result, output_language)
                return result
            except Exception:
                log.exception("Orchestrator: Planner execution failed, falling through to SkillRegistry")

    # 4. SkillRegistry — Financial Research Skills (C6)
    await _emit("intent_detected", {"intent": "skill_registry"})

    # C31.3 — Emit agent_dispatch before SkillRegistry executes
    await _emit("thinking_event", _central_plan.get_agent_dispatch_event(status="running"))

    context = SkillContext(
        db=db,
        user_id=str(user_id),
        session_id=str(session_id) if session_id else "",
        output_language=output_language,
        tool_registry=_registry,
        metadata={
            "raw_query": content,
            "effective_query": _effective_content,
            "context_update_mode": "transactional",
            "intent": _intent_decision.intent,
            **_entity_payload,
        },
        event_callback=event_callback,
        memory_context=_memory_ctx,  # C32.1.1
    )
    await _emit("skill_started", {"source": "skill_registry"})
    # C32.1.2: use resolved query so skills receive de-pronominalized content
    skill_result = await _skill_registry.run(_effective_content, context)
    if skill_result is not None:
        skill_data = getattr(skill_result, "data", None) or {}
        await _emit("skill_completed", {"skill_name": skill_result.skill_name})

        # C31.3 — Emit agent_observation, deep_reasoning, risk_review, synthesis
        await _emit("thinking_event", _central_plan.get_agent_observation_event(
            agent   = skill_result.skill_name or "",
            summary = f"已通过「{skill_result.skill_name or '智能技能'}」获取分析数据，正在综合评估。",
        ))
        await _emit("thinking_event", _central_plan.get_phase_event("deep_reasoning"))
        await _emit("thinking_event", _central_plan.get_phase_event("risk_review"))
        await _emit("thinking_event", _central_plan.get_phase_event("synthesis"))

        result = OrchestratorResult(
            answer=(skill_result.answer or "").strip() or _EMPTY_FINAL_ANSWER_TEXT,
            tool_events=skill_result.tool_events,
            cards=skill_result.cards,
            metadata={
                "skill_name":        skill_result.skill_name,
                "source":            "skill_registry",
                "tools_used":        [e["name"] for e in skill_result.tool_events],
                "safety_flags":      skill_result.safety_flags,
                "skill_data":        skill_data,
                # C9: spec metadata injected by SkillRegistry
                **skill_result.metadata,
            },
        )
        if not (skill_result.answer or "").strip():
            result.metadata["status"] = "failed"
            result.metadata["error_code"] = "EMPTY_FINAL_ANSWER"
        elif skill_data.get("status"):
            result.metadata["status"] = skill_data.get("status")
            if skill_data.get("error_code"):
                result.metadata["error_code"] = skill_data.get("error_code")
        # P1.6.8: hoist structured clarification so sync/SSE payloads and
        # message persistence carry it without digging into skill_data.
        if isinstance(skill_data.get("clarification"), dict):
            from app.services.entity_clarification import compact_clarification_for_metadata  # noqa: PLC0415

            compact_clar = compact_clarification_for_metadata(skill_data.get("clarification"))
            if compact_clar is not None:
                result.metadata["response_kind"] = "clarification"
                result.metadata["clarification"] = compact_clar
        # C8: write memory (fire-and-forget)
        await _write_memory_from_result(db, session_id, user_id, msg, result, output_language)
        return result

    # 5. C4 direct fallback intents
    # C31.3 — Emit agent_dispatch (no heavy agents needed here)
    await _emit("thinking_event", _central_plan.get_phase_event("agent_dispatch"))

    for matcher, handler in _DIRECT_INTENTS:
        if matcher(msg):
            try:
                await _emit("intent_detected", {"intent": "direct", "handler": handler.__name__})
                result = await handler(msg, db, user_id)
                # C8: write memory (fire-and-forget)
                await _write_memory_from_result(db, session_id, user_id, msg, result, output_language)
                return result
            except Exception:
                log.exception("Orchestrator: handler %s failed", handler.__name__)
                return OrchestratorResult(
                    answer="处理请求时发生内部错误，请稍后重试。" + _DISCLAIMER,
                )

    await _emit("intent_detected", {"intent": "default_greeting"})
    return await _handle_default(msg, db, user_id)


async def _write_memory_from_result(
    db: AsyncSession,
    session_id: uuid.UUID | None,
    user_id: uuid.UUID,
    msg: str,
    result: OrchestratorResult,
    output_language: str,
) -> None:
    """
    C8: Write structured memory from orchestrator result (fire-and-forget).
    Never raises — failures are logged as warnings, never block the main flow.
    """
    if session_id is None:
        return
    try:
        meta = result.metadata or {}
        skill_data = meta.get("skill_data") or {}
        skill_status = str(skill_data.get("status") or meta.get("status") or "").lower()
        context_commit_allowed = skill_status in {"completed", "partial_success"} or not skill_status
        pending_confirmation = result.confirmation.get("id") if result.confirmation else _mem._UNSET
        memory_symbols: list[dict] = []
        last_report_id: str | None = None

        # 1. Recent symbols — extracted from user message
        hint = _extract_stock_hint(msg) if context_commit_allowed else None
        if hint and hint.get("symbol"):
            memory_symbols.append(hint)
        report_context = skill_data.get("report_context") if isinstance(skill_data, dict) else None
        if context_commit_allowed and isinstance(report_context, dict):
            report_symbol = str(report_context.get("symbol") or "").strip()
            report_market = str(report_context.get("market") or "CN").strip() or "CN"
            if report_symbol:
                memory_symbols.append({
                    "market": report_market,
                    "symbol": report_symbol,
                    "name": report_context.get("stock_name") or report_symbol,
                })
            if report_context.get("report_id"):
                last_report_id = str(report_context.get("report_id"))
        comparison_input = skill_data.get("comparison_input") if isinstance(skill_data, dict) else None
        if context_commit_allowed and isinstance(comparison_input, dict):
            for entity in comparison_input.get("entities") or []:
                symbol = str(entity.get("symbol") or "").strip()
                if not symbol:
                    continue
                memory_symbols.append({
                    "market": str(entity.get("market") or "CN").strip() or "CN",
                    "symbol": symbol,
                    "name": entity.get("name") or entity.get("short_name") or symbol,
                })

        # 3. Intent — from metadata
        intent = (
            meta.get("plan_intent_type")
            or meta.get("skill_name")
            or ("action" if result.confirmation else None)
        )

        # 4. Task state — Planner metadata
        task_state = None
        if meta.get("planner_used"):
            task_state = {
                "planner_used":      True,
                "plan_intent_type":  meta.get("plan_intent_type"),
                "steps":             meta.get("steps", []),
                "skills_used":       meta.get("skills_used", []),
                "tools_used":        meta.get("tools_used", []),
                "failed_steps":      [
                    s for s in meta.get("steps", []) if s.get("status") == "failed"
                ],
            }
        elif meta.get("skill_name"):
            task_state = {
                "planner_used": False,
                "skill_name":   meta.get("skill_name"),
                "tools_used":   meta.get("tools_used", []),
            }

        # 5. Single per-turn context commit.
        if context_commit_allowed or result.confirmation:
            await _mem.apply_memory_updates(
                db,
                session_id,
                user_id,
                symbols=memory_symbols,
                intent=intent if context_commit_allowed else None,
                output_language=output_language if context_commit_allowed else None,
                last_report_id=last_report_id,
                task_state=task_state if context_commit_allowed else None,
                pending_confirmation_id=pending_confirmation,
            )

        # C32.1: update extended memory (active_entities, trigger summarization)
        try:
            from app.services.conversation_memory_service import update_memory_after_message  # noqa: PLC0415
            await update_memory_after_message(
                db, session_id, user_id,
                user_msg=msg,
                assistant_answer=result.answer or "",
            )
        except Exception:
            pass  # fire-and-forget

    except Exception:
        log.warning("Orchestrator: C8 memory write failed for session %s (non-fatal)", session_id)


async def process_confirm(
    confirmation_type: str,
    params: dict,
    db: AsyncSession,
    user_id: uuid.UUID,
    output_language: str = "zh-CN",
) -> ConfirmResult:
    """
    Execute confirmed action with real side effects (C5).
    Routes to the appropriate action tool and converts ActionResult → ConfirmResult.
    """
    try:
        if confirmation_type == "add_watchlist":
            result: ActionResult = await execute_add_to_watchlist(params, db, user_id)
        elif confirmation_type == "create_analysis_run":
            result = await execute_create_analysis_run(params, db, user_id, output_language)
        elif confirmation_type == "create_compare":
            result = execute_create_compare_selection(params)
        else:
            return ConfirmResult(answer="操作已完成。" + _DISCLAIMER)
    except Exception:
        log.exception("process_confirm: action %s failed", confirmation_type)
        return ConfirmResult(
            answer="操作执行时发生错误，请稍后重试。" + _DISCLAIMER,
        )

    return ConfirmResult(
        answer=result.answer,
        tool_events=result.tool_events,
        cards=result.cards,
    )
