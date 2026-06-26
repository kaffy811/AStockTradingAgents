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

import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Callable

from sqlalchemy.ext.asyncio import AsyncSession

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
import app.agents.chat_memory as _mem

log = logging.getLogger(__name__)

_DISCLAIMER = "\n\n_仅供研究参考，不构成投资建议。_"

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


def _match_report(msg: str) -> bool:
    return bool(re.search(r"生成.{0,10}报告|综合报告|分析报告|帮我分析", msg))


def _match_watchlist_add(msg: str) -> bool:
    # Only match explicit add intent — "加入自选" / "添加到自选" — NOT bare "自选股" queries
    return bool(re.search(r"加入自选|添加到自选|添加自选", msg))


def _match_watchlist_view(msg: str) -> bool:
    return bool(re.search(r"查看自选股|自选股列表|我的自选|看看.*自选|自选股.*有哪些", msg))


def _match_compare(msg: str) -> bool:
    return bool(re.search(r"对比|比较", msg))


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
    """Best-effort extraction of {market, symbol, name_query} from user message."""
    # Explicit code patterns
    if re.search(r"688146|中船特气", msg):
        return {"market": "CN", "symbol": "688146", "name": "中船特气", "query": "688146"}
    if re.search(r"600519|茅台", msg):
        return {"market": "CN", "symbol": "600519", "name": "贵州茅台", "query": "600519"}
    if re.search(r"300750|宁德时代", msg):
        return {"market": "CN", "symbol": "300750", "name": "宁德时代", "query": "300750"}
    if re.search(r"601899|紫金矿业", msg):
        return {"market": "CN", "symbol": "601899", "name": "紫金矿业", "query": "601899"}
    # Generic CN code: 6-digit number
    m = re.search(r"\b(\d{6})\b", msg)
    if m:
        return {"market": "CN", "symbol": m.group(1), "name": m.group(1), "query": m.group(1)}
    # HK code: 5-digit or 4-digit
    m = re.search(r"\b0?(\d{4,5})\b", msg)
    if m:
        return {"market": "HK", "symbol": m.group(1).zfill(5), "name": m.group(1), "query": m.group(1)}
    return {}


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


async def _handle_compare(msg: str, db: AsyncSession, user_id: uuid.UUID) -> OrchestratorResult:
    """Compare intent: build stock list from message then confirm."""
    stocks = [
        {"name": "宁德时代", "market": "CN", "symbol": "300750"},
        {"name": "紫金矿业", "market": "CN", "symbol": "601899"},
        {"name": "华大九天", "market": "CN", "symbol": "301269"},
    ]
    if re.search(r"600519|茅台", msg):
        stocks = [
            {"name": "贵州茅台", "market": "CN", "symbol": "600519"},
            {"name": "紫金矿业", "market": "CN", "symbol": "601899"},
        ]

    compare_url = "/compare?stocks=" + ",".join(
        f"{s['market']}:{s['symbol']}" for s in stocks
    )
    stock_desc = "、".join(f"{s['name']}（{s['symbol']}）" for s in stocks)
    events = [_tool_event("create_compare_selection_tool", f"已准备 {len(stocks)} 只股票对比")]

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

    # 2. Action intents (write ops → confirmation)
    for matcher, handler in _ACTION_INTENTS:
        if matcher(msg):
            try:
                await _emit("intent_detected", {"intent": "action", "handler": handler.__name__})
                result = await handler(msg, db, user_id)
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

    # 3. Controlled Planner — compound multi-step research tasks (C7)
    if _planner.is_compound(msg):
        plan = _planner.plan(msg)
        if plan is not None and plan.steps:
            await _emit("planner_started", {"steps": len(plan.steps)})
            context = SkillContext(
                db=db,
                user_id=str(user_id),
                output_language=output_language,
                tool_registry=_registry,
                event_callback=event_callback,
            )
            try:
                exec_result = await _executor.execute(plan, msg, context)
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
    context = SkillContext(
        db=db,
        user_id=str(user_id),
        output_language=output_language,
        tool_registry=_registry,
        event_callback=event_callback,
    )
    await _emit("skill_started", {"source": "skill_registry"})
    skill_result = await _skill_registry.run(msg, context)
    if skill_result is not None:
        await _emit("skill_completed", {"skill_name": skill_result.skill_name})
        result = OrchestratorResult(
            answer=skill_result.answer,
            tool_events=skill_result.tool_events,
            cards=skill_result.cards,
            metadata={
                "skill_name":        skill_result.skill_name,
                "source":            "skill_registry",
                "tools_used":        [e["name"] for e in skill_result.tool_events],
                "safety_flags":      skill_result.safety_flags,
                # C9: spec metadata injected by SkillRegistry
                **skill_result.metadata,
            },
        )
        # C8: write memory (fire-and-forget)
        await _write_memory_from_result(db, session_id, user_id, msg, result, output_language)
        return result

    # 5. C4 direct fallback intents
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

        # 1. Recent symbols — extracted from user message
        hint = _extract_stock_hint(msg)
        if hint and hint.get("symbol"):
            await _mem.update_symbols(db, session_id, user_id, hint)

        # 2. Output language
        if output_language:
            await _mem.update_output_language(db, session_id, user_id, output_language)

        # 3. Intent — from metadata
        intent = (
            meta.get("plan_intent_type")
            or meta.get("skill_name")
            or ("action" if result.confirmation else None)
        )
        if intent:
            await _mem.update_intents(db, session_id, user_id, intent)

        # 4. Task state — Planner metadata
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
            await _mem.update_task_state(db, session_id, user_id, task_state)
        elif meta.get("skill_name"):
            task_state = {
                "planner_used": False,
                "skill_name":   meta.get("skill_name"),
                "tools_used":   meta.get("tools_used", []),
            }
            await _mem.update_task_state(db, session_id, user_id, task_state)

        # 5. Pending confirmation
        if result.confirmation:
            await _mem.update_pending_confirmation(
                db, session_id, user_id,
                result.confirmation.get("id"),
            )

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
