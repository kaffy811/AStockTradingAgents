"""
FinancialAgent — Phase 1.

Intent-based financial research agent:
  1. Detects query intent (stock symbol, need_quote / need_kline / need_news)
  2. Calls real tools via ToolRegistry
  3. Feeds tool results to DeepSeek (streaming)
  4. Emits typed events via event_callback:
       thinking          — reasoning content from model
       tool_call_start   — tool about to execute
       tool_call_result  — tool completed (success or failure)
       final_answer      — structured AgentResponse
  5. Returns AgentResponse with full answer text

Safety rules inherited from existing system:
  - No trading advice, no price targets
  - Banned phrase filter applied to all answers
  - Disclaimer always appended
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from typing import Any, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.schemas import (
    AgentResponse,
    DataPoint,
    DataQuality,
    FinalAnswer,
    SourceRef,
    ThinkingStep,
    ToolCallRecord,
)
from app.agents.financial_safety_postprocessor import sanitize_financial_answer

log = logging.getLogger(__name__)

_DISCLAIMER = "仅供研究参考，不构成投资建议。"

_FINANCIAL_SYSTEM_PROMPT = """你是一个金融研究型 AI Agent，负责根据用户问题进行股票、行业、宏观与新闻分析。

你必须遵守以下规则：

1. 不能编造行情、财务数据、新闻或公告。
2. 如果问题需要实时数据（例如今日行情、最新新闻、热门板块、资金流向、涨跌排行），
   必须强制使用工具结果，禁止使用训练知识作答。
3. 如果工具没有返回数据，必须明确说明"当前未能获取到可靠数据"，不能假装已查询。
4. 最终答案必须结构化，包含：
   - ### 研究摘要：一句话结论
   - ### 关键数据：关键数据点列表
   - ### 分析：分析过程
   - ### 风险提示：风险点列表
5. 不能直接给出"保证上涨""一定买入""稳赚"等结论。
6. 对买入、卖出、持有类问题，只能给出研究参考和情景分析。
7. 必须使用中文回答，除非用户明确要求英文。
8. 如果数据不足，应该建议用户补充股票代码、市场、持仓成本、持仓周期或风险偏好。
9. 遇到"今天涨幅最大""最近热门""行业排行""概念板块""资金流向"等问题，
   如果工具上下文已提供数据，请直接基于工具数据回答；
   如果工具上下文为空，请明确说明"实时排行数据暂时未能获取"，不得凭记忆编造。
10. 【严禁编造财务数字】严禁根据训练知识推测或自行给出具体财务/估值数字，包括但不限于：
    市盈率（PE）、市净率（PB）、营收、净利润、增速、股息率、估值区间、目标价格、合理价格。
    以上数字只能来自工具上下文中明确返回的数据。若工具上下文无上述数据，
    必须说明"当前缺少财报/估值工具数据，无法给出具体数字"，
    绝对禁止使用"约X倍""基于推测""历史均值约""预计"等形式输出估计值。
11. 【历史报告查询】若用户要求读取或解读历史报告原文，必须以知识库检索结果为准。
    如果知识库未检索到该报告，必须明确说明"未检索到报告原文，无法准确概括报告内容"，
    不得用通用知识替代报告内容作答。
12. 【买入决策合规】对"继续买入""该不该买""要不要加仓"类问题，
    必须以"我无法替您做买入/卖出决定"开头，然后列出用户可以自行评估的客观条件，
    不能给出"可以买""建议持有""可以继续"等任何倾向性操作建议。

严禁出现：买入、卖出、做多、做空、抄底、目标价、稳赚、必涨、追涨"""

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
]

# Phase 2A: human-readable labels for RAG source types
_SOURCE_TYPE_LABELS: dict[str, str] = {
    "annual_report":     "年度报告",
    "quarterly_report":  "季度报告",
    "announcement":      "公司公告",
    "research_report":   "行业研报",
    "regulation":        "监管文件",
    "document":          "参考文档",
    "other":             "其他资料",
}

# Per-tool timeout budgets (seconds)
_TOOL_TIMEOUTS: dict[str, float] = {
    "stock_quote":          8.0,
    "stock_kline":         10.0,
    "financial_news":      12.0,
    "financial_rag_search": 15.0,   # Phase 2A: DB keyword search
}
_LLM_TIMEOUT = 60.0


# ── Intent detection ──────────────────────────────────────────────────────────

_QUOTE_PATTERN = re.compile(
    r"行情|报价|现价|股价|涨跌|涨了|跌了|price|quote|今日|今天|最新价", re.IGNORECASE
)
_KLINE_PATTERN = re.compile(
    r"k线|均线|技术面|macd|rsi|趋势|走势|chart|kline|近.*日|60日|30日|90日", re.IGNORECASE
)
_NEWS_PATTERN = re.compile(
    r"新闻|消息|公告|利好|利空|news|催化|最近.*发生|有什么.*消息", re.IGNORECASE
)
# C25: realtime market search triggers (no-symbol queries)
_REALTIME_PATTERN = re.compile(
    r"今[天日]|最新|最近|实时|当前|热门|热点|热股|涨幅|跌幅|排行|排名"
    r"|资金流|主力|板块|概念|行业动态|市场行情|今日|今年|本周|近期",
    re.IGNORECASE,
)
_FUND_FLOW_PATTERN = re.compile(r"资金流|主力|净流入|净流出|北向|南向|陆股通", re.IGNORECASE)
# C25.4: extended to catch "行业关键词 + 热门/涨幅/排名" compound queries
_HOT_STOCK_PATTERN = re.compile(
    r"热门股|热门个股|人气榜|热股排行|涨幅榜|跌幅榜|活跃股"
    r"|哪些.*热门|热门.*哪些|最近.*热门|热门.*最近"
    r"|最近.*涨幅|涨幅.*排名|领涨|龙头股|强势股",
    re.IGNORECASE,
)
_CONCEPT_PATTERN = re.compile(r"概念|题材|板块|炒作|风口", re.IGNORECASE)

# Phase 2A: financial knowledge-base RAG triggers
_RAG_PATTERN = re.compile(
    r"财报|年报|季报|公告|研报|基本面|估值|护城河|商业模式|风险因素|监管"
    r"|行业对比|长期持有|是否值得|长期投资|年度报告|季度报告|分析师报告"
    # Problem B fix: historical-report read / date-specific report queries
    r"|历史报告|历史研报|研究报告|帮我读.{0,10}报告|读.*报告|查看.*报告"
    r"|报告.*内容|报告.*讲|讲了些什么|报告.*描述|用最简单"
    r"|\d{1,2}[./月]\s*\d{1,2}.{0,8}报告|报告.{0,8}\d{1,2}[./月]\s*\d{1,2}"
    r"|fundamental|annual.?report|quarterly.?report|10-k|10-q",
    re.IGNORECASE,
)

# US market tickers: 1-5 uppercase letters optionally with .US suffix
_US_TICKER = re.compile(r"\b([A-Z]{1,5})(?:\.US)?\b")
# CN 6-digit code
_CN_CODE = re.compile(r"\b(\d{6})\b")

# Well-known US tickers to avoid false positives on common words
_KNOWN_US_TICKERS = {
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "NVDA", "META", "TSLA",
    "NFLX", "AMD", "INTC", "IBM", "ORCL", "QCOM", "AVGO", "TSM",
    "BRK", "JPM", "BAC", "GS", "MS", "WMT", "COST", "TGT",
    "SPY", "QQQ", "DIA", "IWM", "VTI",
}


def _detect_realtime_mode(query: str) -> str:
    """
    For no-symbol realtime queries, choose the best UniversalMarketSearchTool mode.
    Returns one of: 'fund_flow', 'hot_stocks', 'concept', 'industry_rank', 'news'.
    """
    if _FUND_FLOW_PATTERN.search(query):
        return "fund_flow"
    if _HOT_STOCK_PATTERN.search(query):
        return "hot_stocks"
    if _CONCEPT_PATTERN.search(query):
        return "concept"
    if re.search(r"行业|板块涨跌|板块排行", query):
        return "industry_rank"
    return "news"


def _detect_intent(query: str) -> dict:
    """
    Returns {
        symbol: str | None,
        market: "CN" | "HK" | "US" | None,
        need_quote: bool,
        need_kline: bool,
        need_news: bool,
        need_rag: bool,
        need_realtime: bool,   # C25: no-symbol realtime market query
    }
    """
    need_quote    = bool(_QUOTE_PATTERN.search(query))
    need_kline    = bool(_KLINE_PATTERN.search(query))
    need_news     = bool(_NEWS_PATTERN.search(query))
    need_rag      = bool(_RAG_PATTERN.search(query))
    need_realtime = bool(_REALTIME_PATTERN.search(query))

    # If no specific intent, default to quote + news for stock queries
    symbol = None
    market = None

    # Try CN code first
    m = _CN_CODE.search(query)
    if m:
        symbol = m.group(1)
        market = "CN"
        if not need_quote and not need_kline and not need_news:
            need_quote = True
            need_news  = True

    # Try known US ticker
    if not symbol:
        for tok in _US_TICKER.finditer(query.upper()):
            candidate = tok.group(1)
            if candidate in _KNOWN_US_TICKERS:
                symbol = candidate
                market = "US"
                if not need_quote and not need_kline and not need_news:
                    need_quote = True
                    need_news  = True
                break

    # Named CN/HK stocks
    _CN_NAMES = {
        "茅台": ("600519", "CN"),
        "贵州茅台": ("600519", "CN"),
        "中船特气": ("688146", "CN"),
        "宁德时代": ("300750", "CN"),
        "紫金矿业": ("601899", "CN"),
        "平安银行": ("000001", "CN"),
        "腾讯": ("00700", "HK"),
        "腾讯控股": ("00700", "HK"),
        "阿里巴巴": ("09988", "HK"),
        "美团": ("03690", "HK"),
        "比亚迪": ("002594", "CN"),
        "招商银行": ("600036", "CN"),
    }
    if not symbol:
        for name, (sym, mkt) in _CN_NAMES.items():
            if name in query:
                symbol = sym
                market = mkt
                if not need_quote and not need_kline and not need_news:
                    need_quote = True
                    need_news  = True
                break

    # Chinese names for US stocks
    _US_CN_NAMES = {
        "英伟达": "NVDA",
        "苹果": "AAPL",
        "苹果公司": "AAPL",
        "微软": "MSFT",
        "谷歌": "GOOGL",
        "亚马逊": "AMZN",
        "特斯拉": "TSLA",
        "脸书": "META",
        "英特尔": "INTC",
        "台积电": "TSM",
    }
    if not symbol:
        # Sort by length descending to match longer names first (e.g. 苹果公司 before 苹果)
        for cn_name, ticker in sorted(_US_CN_NAMES.items(), key=lambda x: -len(x[0])):
            if cn_name in query:
                symbol = ticker
                market = "US"
                if not need_quote and not need_kline and not need_news:
                    need_quote = True
                    need_news  = True
                break

    return {
        "symbol":        symbol,
        "market":        market,
        "need_quote":    need_quote,
        "need_kline":    need_kline,
        "need_news":     need_news,
        "need_rag":      need_rag,
        "need_realtime": need_realtime,   # C25
    }


def _filter_banned(text: str) -> str:
    for phrase, replacement in _BANNED_PHRASES:
        text = text.replace(phrase, replacement)
    return text


# C28.1: Strip model self-talk preamble that appears before the first section header
_PREAMBLE_RE = re.compile(r"^.+?(?=^#{2,3}\s)", re.DOTALL | re.MULTILINE)
_SELFREF_PREAMBLE = re.compile(
    r"^(?:我们?分析|我们?来分析|让我分析|根据工具数据[，,]|根据以上工具[，,]|"
    r"好的[，,]|以下是(?:针对)?[^#\n]{0,20}(?:的分析|的研究|结果)[：:。，,\n])"
    r".*?\n\n",
    re.DOTALL,
)


def _strip_model_preamble(text: str) -> str:
    """Remove model self-talk intro before the first markdown section header (###).

    E.g. "我们分析用户问题：茅台... 根据工具数据……\n\n### 研究摘要\n..."
    becomes "### 研究摘要\n..."
    """
    if "###" not in text:
        # No section headers — try stripping explicit self-reference openers
        cleaned = _SELFREF_PREAMBLE.sub("", text, count=1)
        return cleaned.strip() if cleaned.strip() else text
    # Has section headers — strip everything before the first ###
    m = _PREAMBLE_RE.match(text)
    if m:
        stripped = text[m.end():]
        # Safety: only keep the stripped version if substantial content remains
        if stripped.strip() and len(stripped) > len(text) * 0.3:
            return stripped.lstrip("\n")
    return text


# Industry keywords for news search (Phase 2E-4)
_INDUSTRY_KEYWORDS = [
    "新能源", "光伏", "储能", "风电", "核电",
    "半导体", "芯片", "集成电路",
    "人工智能", "AI", "大模型",
    "汽车", "新能源汽车", "电动车",
    "银行", "券商", "保险", "金融",
    "医药", "医疗", "生物科技", "创新药",
    "房地产", "地产",
    "消费", "白酒", "食品饮料",
    "军工", "国防",
    "云计算", "互联网",
    "化工", "材料",
    "有色", "矿业", "锂矿",
    "钢铁", "煤炭", "石油", "天然气",
    "农业", "农产品",
    "电子", "通信",
]


def _extract_industry_keyword(query: str) -> str | None:
    """
    Extract the most specific industry keyword from a query.
    Returns the longest match (prefer "新能源汽车" over "新能源").
    """
    found = [kw for kw in _INDUSTRY_KEYWORDS if kw in query]
    if not found:
        return None
    # Return the longest match to be most specific
    return max(found, key=len)


def _fmt_unix_ts(ts: Any) -> tuple[str, Any]:
    """Format a Unix timestamp (int/float) to 'YYYY-MM-DD HH:mm' (UTC).

    Returns (formatted_string, original_value).
    If ts is not a numeric timestamp, returns (str(ts), None) without raising.
    """
    if isinstance(ts, (int, float)):
        try:
            from datetime import datetime, timezone
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d %H:%M"), ts
        except Exception:
            pass
    return (str(ts) if ts else ""), None


# ── Tool adapters (thin wrappers around existing ToolRegistry tools) ──────────

async def _call_tool(registry: Any, tool_name: str, db: AsyncSession, **kwargs) -> dict:
    """Call a tool via registry, return serializable result dict."""
    result = await registry.call(tool_name, db, **kwargs)
    return {
        "tool_name": tool_name,
        "ok": result.ok,
        "summary": result.summary or "",
        "data": result.data or {},
        "text": getattr(result, "text", "") or "",  # optional long-form content
        "error": result.error,
    }


async def _run_tool_with_timeout(
    tool_name: str,
    coro: Any,
    timeout_seconds: float,
) -> dict:
    """Run a tool coroutine with timeout.

    Never raises — returns ok=False dict on timeout or any exception.
    Downstream code checks raw.get("ok") to distinguish success/failure.
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        log.warning("Tool %s timed out after %.1fs", tool_name, timeout_seconds)
        return {
            "ok": False,
            "error": f"{tool_name} 超时（{timeout_seconds:.0f}s），当前数据不可用",
        }
    except Exception as exc:
        log.warning("Tool %s failed: %s", tool_name, exc)
        return {"ok": False, "error": str(exc)}


async def _fetch_us_quote(symbol: str) -> dict:
    """Fetch US stock quote via yfinance (no DB dependency)."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        info = await asyncio.to_thread(lambda: ticker.fast_info)
        price = getattr(info, "last_price", None)
        prev  = getattr(info, "previous_close", None)
        if price and prev and prev != 0:
            change = price - prev
            change_pct = change / prev * 100
        else:
            change, change_pct = 0.0, 0.0
        return {
            "ok": price is not None,
            "symbol": symbol,
            "market": "US",
            "price": round(price, 2) if price else None,
            "change": round(change, 2),
            "change_pct": f"{change_pct:+.2f}%",
            "currency": "USD",
        }
    except Exception as exc:
        log.warning("_fetch_us_quote %s failed: %s", symbol, exc)
        return {"ok": False, "symbol": symbol, "market": "US", "error": str(exc)}


async def _fetch_us_kline(symbol: str, period: str = "3mo") -> dict:
    """Fetch US stock kline via yfinance."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        hist = await asyncio.to_thread(lambda: ticker.history(period=period))
        if hist.empty:
            return {"ok": False, "symbol": symbol, "error": "no data"}
        candles = []
        for idx, row in hist.tail(20).iterrows():
            candles.append({
                "date": str(idx.date()),
                "open":   round(float(row["Open"]), 2),
                "high":   round(float(row["High"]), 2),
                "low":    round(float(row["Low"]), 2),
                "close":  round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            })
        close_prices = hist["Close"].values
        if len(close_prices) >= 2:
            change_pct = (close_prices[-1] - close_prices[0]) / close_prices[0] * 100
        else:
            change_pct = 0.0
        return {
            "ok": True,
            "symbol": symbol,
            "market": "US",
            "period_change_pct": round(change_pct, 2),
            "candles_count": len(candles),
            "candles_sample": candles[-5:],
        }
    except Exception as exc:
        log.warning("_fetch_us_kline %s failed: %s", symbol, exc)
        return {"ok": False, "symbol": symbol, "error": str(exc)}


async def _fetch_us_news(symbol: str, limit: int = 5) -> dict:
    """Fetch US stock news via yfinance."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        raw_news = await asyncio.to_thread(lambda: ticker.news)
        items = []
        for item in (raw_news or [])[:limit]:
            raw_ts = item.get("providerPublishTime", "")
            pub_str, pub_raw = _fmt_unix_ts(raw_ts)
            items.append({
                "title":            item.get("title", ""),
                "source":           item.get("publisher", ""),
                "published_at":     pub_str,    # "YYYY-MM-DD HH:mm" UTC
                "published_at_raw": pub_raw,    # original Unix timestamp or None
                "url":              item.get("link", ""),
                "summary":          item.get("title", ""),
            })
        return {"ok": True, "symbol": symbol, "market": "US", "items": items, "count": len(items)}
    except Exception as exc:
        log.warning("_fetch_us_news %s failed: %s", symbol, exc)
        return {"ok": False, "symbol": symbol, "error": str(exc)}


# ── FinancialAgent ─────────────────────────────────────────────────────────────

class FinancialAgent:
    """
    Minimal financial research agent.

    run() is the async entry point:
      - Emits typed events via event_callback (if provided)
      - Returns AgentResponse with structured final_answer + answer_text
    """

    async def run(
        self,
        query: str,
        db: AsyncSession,
        tool_registry: Any,
        *,
        output_language: str = "zh-CN",
        event_callback: Callable | None = None,
        request_id: str | None = None,
        timeout_seconds: float = 45.0,
    ) -> AgentResponse:
        """
        Execute intent detection → tool calls → streaming LLM → structured response.
        """
        request_id = request_id or str(uuid.uuid4())
        # Phase 2B: use enhanced intent parser when report analysis is likely
        from app.agents.official_report_search import parse_financial_analysis_intent  # noqa: PLC0415
        intent = parse_financial_analysis_intent(query)

        thinking_steps: list[ThinkingStep] = []
        tool_calls: list[ToolCallRecord] = []
        tool_context_parts: list[str] = []
        rag_results: list[dict] = []     # Phase 2A: RAG chunks for citation
        data_quality = DataQuality()     # Phase 2B: provenance tracking

        async def _emit(event_type: str, payload: dict) -> None:
            if event_callback:
                try:
                    await event_callback(event_type, payload)
                except Exception:
                    pass

        symbol = intent["symbol"]
        market = intent["market"]

        # ── Tool phase ────────────────────────────────────────────────────────

        if symbol and market:
            # ── Quote ─────────────────────────────────────────────────────────
            if intent["need_quote"]:
                await _emit("tool_call_start", {
                    "tool_name":   "stock_quote_tool",
                    "display_name": f"查询 {symbol} 实时行情",
                    "arguments":   {"symbol": symbol, "market": market},
                })
                t0 = time.monotonic()
                coro = (
                    _fetch_us_quote(symbol)
                    if market == "US"
                    else _call_tool(tool_registry, "get_quote_tool", db,
                                    market=market, symbol=symbol, name=symbol)
                )
                raw = await _run_tool_with_timeout(
                    "stock_quote_tool", coro, _TOOL_TIMEOUTS["stock_quote"]
                )
                elapsed_ms = int((time.monotonic() - t0) * 1000)

                record = ToolCallRecord(
                    tool_name="stock_quote_tool",
                    display_name=f"查询 {symbol} 实时行情",
                    arguments={"symbol": symbol, "market": market},
                    status="success" if raw.get("ok") else "failed",
                    result_summary=raw.get("summary") or (
                        f"{symbol} 价格: {raw.get('price')} 涨跌: {raw.get('change_pct')}"
                        if raw.get("price") else "行情数据不可用"
                    ),
                    raw_result=raw,
                    error=raw.get("error"),
                )
                tool_calls.append(record)
                await _emit("tool_call_result", {
                    "tool_name":      "stock_quote_tool",
                    "display_name":   record.display_name,
                    "status":         record.status,
                    "result_summary": record.result_summary,
                    "duration_ms":    elapsed_ms,
                })
                if record.status == "success":
                    data_quality.market_data_available = True
                    tool_context_parts.append(f"【行情】{record.result_summary}")
                else:
                    data_quality.warnings.append("行情数据暂时无法获取，行情联动部分可靠性有限")
                    tool_context_parts.append(
                        f"【行情】获取失败（{raw.get('error', '未知错误')}）——分析将基于已有信息，可靠性有限"
                    )

            # ── K-line ────────────────────────────────────────────────────────
            if intent["need_kline"]:
                await _emit("tool_call_start", {
                    "tool_name":   "stock_kline_tool",
                    "display_name": f"获取 {symbol} K线数据",
                    "arguments":   {"symbol": symbol, "market": market},
                })
                t0 = time.monotonic()
                coro = (
                    _fetch_us_kline(symbol)
                    if market == "US"
                    else _call_tool(tool_registry, "get_kline_summary_tool", db,
                                    market=market, symbol=symbol)
                )
                raw = await _run_tool_with_timeout(
                    "stock_kline_tool", coro, _TOOL_TIMEOUTS["stock_kline"]
                )
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                ok = raw.get("ok", False)
                summary = (
                    f"{symbol} 近期涨跌幅: {raw.get('period_change_pct', raw.get('data', {}).get('period_change_pct', 'N/A'))}%"
                    if ok
                    else f"K线数据获取失败（{raw.get('error', '未知错误')}）——技术面分析数据不可用，结论可靠性有限"
                )
                record = ToolCallRecord(
                    tool_name="stock_kline_tool",
                    display_name=f"获取 {symbol} K线数据",
                    arguments={"symbol": symbol, "market": market},
                    status="success" if ok else "failed",
                    result_summary=summary,
                    raw_result=raw,
                    error=raw.get("error"),
                )
                tool_calls.append(record)
                await _emit("tool_call_result", {
                    "tool_name":      "stock_kline_tool",
                    "display_name":   record.display_name,
                    "status":         record.status,
                    "result_summary": record.result_summary,
                    "duration_ms":    elapsed_ms,
                })
                tool_context_parts.append(f"【K线】{summary}")

            # ── News ──────────────────────────────────────────────────────────
            if intent["need_news"]:
                await _emit("tool_call_start", {
                    "tool_name":   "financial_news_tool",
                    "display_name": f"检索 {symbol} 最新新闻",
                    "arguments":   {"symbol": symbol, "market": market},
                })
                t0 = time.monotonic()
                coro = (
                    _fetch_us_news(symbol)
                    if market == "US"
                    else _call_tool(tool_registry, "get_latest_news_tool", db,
                                    market=market, symbol=symbol, hours_back=72, limit=5)
                )
                raw = await _run_tool_with_timeout(
                    "financial_news_tool", coro, _TOOL_TIMEOUTS["financial_news"]
                )
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                ok = raw.get("ok", False)
                if ok:
                    items = raw.get("items", raw.get("data", {}).get("items", []))
                    count = raw.get("count", len(items))
                    summary = f"检索到 {count} 条新闻"
                    if items:
                        titles = "; ".join(
                            it.get("title", "") for it in items[:3] if it.get("title")
                        )
                        if titles:
                            summary += f"：{titles[:200]}"
                else:
                    summary = (
                        f"新闻获取失败（{raw.get('error', '未知错误')}）——新闻分析数据不可用，结论可靠性有限"
                    )

                record = ToolCallRecord(
                    tool_name="financial_news_tool",
                    display_name=f"检索 {symbol} 最新新闻",
                    arguments={"symbol": symbol, "market": market, "limit": 5},
                    status="success" if ok else "failed",
                    result_summary=summary,
                    raw_result=raw,
                    error=raw.get("error"),
                )
                tool_calls.append(record)
                await _emit("tool_call_result", {
                    "tool_name":      "financial_news_tool",
                    "display_name":   record.display_name,
                    "status":         record.status,
                    "result_summary": record.result_summary,
                    "duration_ms":    elapsed_ms,
                })
                tool_context_parts.append(f"【新闻】{summary}")

        # ── Industry news (Phase 2E-4): runs when need_news but no stock symbol ──
        # Covers queries like "新能源行业最近有什么新闻？" or "半导体行业动态"
        if not symbol and intent.get("need_news"):
            _industry_kw = _extract_industry_keyword(query)
            if _industry_kw:
                await _emit("tool_call_start", {
                    "tool_name":    "get_industry_news_tool",
                    "display_name": f"检索{_industry_kw}行业新闻",
                    "arguments":    {"keyword": _industry_kw},
                })
                t0_ind = time.monotonic()
                try:
                    import asyncio as _asyncio
                    raw_ind = await _asyncio.wait_for(
                        _call_tool(tool_registry, "get_industry_news_tool", db, keyword=_industry_kw, limit=8),
                        timeout=10.0,
                    )
                except Exception as _ind_exc:
                    raw_ind = {"ok": False, "summary": f"行业新闻获取失败: {_ind_exc}"}
                elapsed_ind = int((time.monotonic() - t0_ind) * 1000)

                _ind_summary = raw_ind.get("summary", "") if isinstance(raw_ind, dict) else ""
                _ind_text    = raw_ind.get("text", "")    if isinstance(raw_ind, dict) else ""
                tool_calls.append(ToolCallRecord(
                    tool_name="get_industry_news_tool",
                    display_name=f"检索{_industry_kw}行业新闻",
                    arguments={"keyword": _industry_kw},
                    status="success" if (isinstance(raw_ind, dict) and raw_ind.get("ok")) else "failed",
                    result_summary=_ind_summary,
                    raw_result=raw_ind if isinstance(raw_ind, dict) else {},
                ))
                await _emit("tool_call_result", {
                    "tool_name":      "get_industry_news_tool",
                    "display_name":   f"检索{_industry_kw}行业新闻",
                    "status":         "success" if (isinstance(raw_ind, dict) and raw_ind.get("ok")) else "failed",
                    "result_summary": _ind_summary,
                    "duration_ms":    elapsed_ind,
                })
                if _ind_text:
                    tool_context_parts.append(f"【行业新闻 — {_industry_kw}】\n{_ind_text}")
                elif _ind_summary:
                    tool_context_parts.append(f"【行业新闻 — {_industry_kw}】{_ind_summary}")

        # ── C25: Universal market search (no-symbol realtime queries) ───────────
        # Covers: "今天涨幅最大的是什么", "热门概念板块", "资金流向行业", etc.
        # Only fires when there is no stock symbol AND the query has realtime signals.
        if not symbol and intent.get("need_realtime") and not intent.get("need_news"):
            _rt_mode    = _detect_realtime_mode(query)
            _rt_keyword = _extract_industry_keyword(query) or ""
            _rt_display = {
                "fund_flow":     "查询主力资金流向",
                "hot_stocks":    "查询热门股排行",
                "concept":       f"搜索概念板块{('：' + _rt_keyword) if _rt_keyword else ''}",
                "industry_rank": "查询行业涨跌排行",
                "news":          f"搜索实时新闻{('：' + _rt_keyword) if _rt_keyword else ''}",
            }.get(_rt_mode, "搜索市场热点")

            await _emit("tool_call_start", {
                "tool_name":    "universal_market_search",
                "display_name": _rt_display,
                "arguments":    {"mode": _rt_mode, "keyword": _rt_keyword},
            })
            t0_rt = time.monotonic()
            try:
                raw_rt = await asyncio.wait_for(
                    _call_tool(
                        tool_registry, "universal_market_search", db,
                        mode=_rt_mode, keyword=_rt_keyword, limit=10,
                    ),
                    timeout=15.0,
                )
            except Exception as _rt_exc:
                raw_rt = {"ok": False, "summary": f"市场搜索失败: {_rt_exc}"}
            elapsed_rt = int((time.monotonic() - t0_rt) * 1000)

            _rt_ok      = isinstance(raw_rt, dict) and raw_rt.get("ok", False)
            _rt_summary = (raw_rt.get("summary", "") if isinstance(raw_rt, dict) else "")
            _rt_text    = (raw_rt.get("text", "")    if isinstance(raw_rt, dict) else "")
            tool_calls.append(ToolCallRecord(
                tool_name="universal_market_search",
                display_name=_rt_display,
                arguments={"mode": _rt_mode, "keyword": _rt_keyword},
                status="success" if _rt_ok else "failed",
                result_summary=_rt_summary,
                raw_result=raw_rt if isinstance(raw_rt, dict) else {},
            ))
            await _emit("tool_call_result", {
                "tool_name":      "universal_market_search",
                "display_name":   _rt_display,
                "status":         "success" if _rt_ok else "failed",
                "result_summary": _rt_summary,
                "duration_ms":    elapsed_rt,
            })
            if _rt_text:
                tool_context_parts.append(f"【市场热点 — {_rt_display}】\n{_rt_text}")
            elif _rt_summary:
                tool_context_parts.append(f"【市场热点 — {_rt_display}】{_rt_summary}")

            # Also fetch realtime news for keyword if any
            if _rt_keyword and _rt_mode != "news":
                await _emit("tool_call_start", {
                    "tool_name":    "search_realtime_news",
                    "display_name": f"搜索实时财经新闻：{_rt_keyword}",
                    "arguments":    {"keyword": _rt_keyword},
                })
                t0_rn = time.monotonic()
                try:
                    raw_rn = await asyncio.wait_for(
                        _call_tool(
                            tool_registry, "search_realtime_news", db,
                            keyword=_rt_keyword, limit=6,
                        ),
                        timeout=12.0,
                    )
                except Exception as _rn_exc:
                    raw_rn = {"ok": False, "summary": f"新闻搜索失败: {_rn_exc}"}
                elapsed_rn = int((time.monotonic() - t0_rn) * 1000)
                _rn_ok   = isinstance(raw_rn, dict) and raw_rn.get("ok", False)
                _rn_sum  = (raw_rn.get("summary", "") if isinstance(raw_rn, dict) else "")
                _rn_text = (raw_rn.get("text", "")    if isinstance(raw_rn, dict) else "")
                tool_calls.append(ToolCallRecord(
                    tool_name="search_realtime_news",
                    display_name=f"搜索实时财经新闻：{_rt_keyword}",
                    arguments={"keyword": _rt_keyword},
                    status="success" if _rn_ok else "failed",
                    result_summary=_rn_sum,
                    raw_result=raw_rn if isinstance(raw_rn, dict) else {},
                ))
                await _emit("tool_call_result", {
                    "tool_name":      "search_realtime_news",
                    "display_name":   f"搜索实时财经新闻：{_rt_keyword}",
                    "status":         "success" if _rn_ok else "failed",
                    "result_summary": _rn_sum,
                    "duration_ms":    elapsed_rn,
                })
                if _rn_text:
                    tool_context_parts.append(f"【实时新闻 — {_rt_keyword}】\n{_rn_text}")

        # ── Phase 2B: Official Financial Report Search + Verify + Ingest ─────
        if intent.get("need_report"):
            from app.agents.official_report_search import (   # noqa: PLC0415
                official_financial_report_search,
                verify_financial_report_candidate,
                download_document_text,
            )
            from app.agents.financial_document_ingest import ingest_financial_document  # noqa: PLC0415

            _company   = intent.get("company_name") or symbol or ""
            _rep_year  = intent.get("report_year")
            _rep_type  = intent.get("report_type", "annual_report")
            _exchange  = intent.get("exchange", "")

            # ── 2B-1: search official sources ────────────────────────────────
            await _emit("tool_call_start", {
                "tool_name":    "official_financial_report_search",
                "display_name": "搜索官方财报",
                "arguments": {
                    "company_name": _company,
                    "symbol":       symbol,
                    "market":       market,
                    "report_year":  _rep_year,
                    "report_type":  _rep_type,
                },
            })
            t0_report = time.monotonic()
            raw_search = await _run_tool_with_timeout(
                "official_financial_report_search",
                official_financial_report_search(
                    symbol or "",
                    market or "CN",
                    exchange=_exchange,
                    company_name=_company,
                    report_year=_rep_year,
                    report_type=_rep_type,
                ),
                20.0,
            )
            elapsed_report_ms = int((time.monotonic() - t0_report) * 1000)

            _candidates = raw_search.get("candidates", []) if raw_search.get("ok") else []
            _search_ok  = raw_search.get("ok", False)
            _search_summary = (
                f"检索到 {len(_candidates)} 个候选财报"
                + (f"，其中 {sum(1 for c in _candidates if c.get('source_level') == 'official_exchange')} 个来自交易所官方披露渠道"
                   if _candidates else "")
                if _search_ok and _candidates
                else raw_search.get("not_found_reason", "未检索到官方财报")
            )
            tool_calls.append(ToolCallRecord(
                tool_name="official_financial_report_search",
                display_name="搜索官方财报",
                arguments={"company_name": _company, "symbol": symbol,
                           "report_year": _rep_year, "report_type": _rep_type},
                status="success" if _search_ok else "failed",
                result_summary=_search_summary,
                raw_result=raw_search,
            ))
            await _emit("tool_call_result", {
                "tool_name":      "official_financial_report_search",
                "display_name":   "搜索官方财报",
                "status":         "success" if _search_ok else "failed",
                "result_summary": _search_summary,
                "duration_ms":    elapsed_report_ms,
            })

            if not _candidates:
                data_quality.report_verified = False
                data_quality.warnings.append(
                    raw_search.get("not_found_reason",
                                   f"未找到 {_company or symbol} {_rep_year or '最新'} 官方财报")
                )
                tool_context_parts.append(
                    f"【官方财报检索】未找到 {_company or symbol}"
                    f"{'（' + str(_rep_year) + '）' if _rep_year else ''} 的官方正式披露财报。"
                    "不得编造财报内容，以下分析不含财报数据。"
                )
            else:
                # ── 2B-2: verify top candidate ───────────────────────────────
                top_candidate = _candidates[0]
                _expected = {
                    "symbol":       symbol,
                    "company_name": _company,
                    "report_year":  _rep_year,
                    "report_type":  _rep_type,
                }
                await _emit("tool_call_start", {
                    "tool_name":    "verify_financial_report",
                    "display_name": "审核财报来源",
                    "arguments":    {"candidate_title": top_candidate.get("title", ""),
                                     "expected": _expected},
                })
                t0_verify = time.monotonic()
                verify_result = verify_financial_report_candidate(top_candidate, _expected)
                elapsed_verify_ms = int((time.monotonic() - t0_verify) * 1000)

                _verify_summary = (
                    f"财报来源审核{'通过' if verify_result['verified'] else '未通过'}：{verify_result['reason']}"
                )
                tool_calls.append(ToolCallRecord(
                    tool_name="verify_financial_report",
                    display_name="审核财报来源",
                    arguments={"candidate": top_candidate, "expected": _expected},
                    status="success" if verify_result["verified"] else "failed",
                    result_summary=_verify_summary,
                    raw_result=verify_result,
                ))
                await _emit("tool_call_result", {
                    "tool_name":      "verify_financial_report",
                    "display_name":   "审核财报来源",
                    "status":         "success" if verify_result["verified"] else "failed",
                    "result_summary": _verify_summary,
                    "duration_ms":    elapsed_verify_ms,
                })

                if not verify_result["verified"]:
                    data_quality.report_verified = False
                    data_quality.warnings.append(
                        f"财报来源审核未通过（{', '.join(verify_result.get('risk_flags', []))}）"
                        "，不能作为核心财报依据"
                    )
                    tool_context_parts.append(
                        f"【官方财报审核】检索到的财报来源未通过审核"
                        f"（{verify_result['reason']}），不得作为核心财报依据。"
                    )
                else:
                    # ── 2B-3: download + ingest if URL available ─────────────
                    data_quality.report_verified   = True
                    data_quality.report_source_level = verify_result.get(
                        "source_level", top_candidate.get("source_level", "official_exchange")
                    ) if hasattr(verify_result, "get") else top_candidate.get(
                        "source_level", "official_exchange"
                    )
                    # Resolve source_level from top_candidate since verify_result doesn't have it
                    data_quality.report_source_level = top_candidate.get(
                        "source_level", "official_exchange"
                    )

                    doc_url  = top_candidate.get("url", "")
                    ingest_result: dict = {}

                    if doc_url:
                        await _emit("tool_call_start", {
                            "tool_name":    "financial_document_ingest",
                            "display_name": "导入财报知识库",
                            "arguments":    {"url": doc_url, "title": top_candidate.get("title", "")},
                        })
                        t0_ingest = time.monotonic()

                        # Try to download HTML content (PDF download handled separately)
                        doc_text = await _run_tool_with_timeout(
                            "financial_document_ingest",
                            download_document_text(doc_url),
                            15.0,
                        )
                        if isinstance(doc_text, str) and doc_text:
                            ingest_result = await _run_tool_with_timeout(
                                "financial_document_ingest",
                                ingest_financial_document(
                                    db=db,
                                    raw_text=doc_text,
                                    url=doc_url,
                                    symbol=symbol,
                                    market=market,
                                    title=top_candidate.get("title", ""),
                                    source_type=_rep_type,
                                    source=top_candidate.get("source_name", ""),
                                    published_at=top_candidate.get("published_at", ""),
                                    metadata={
                                        "report_year":   _rep_year,
                                        "report_type":   _rep_type,
                                        "source_level":  top_candidate.get("source_level"),
                                        "verified":      True,
                                        "authority_score": verify_result.get("authority_score"),
                                        "official_url":  doc_url,
                                        "company_name":  _company,
                                        "exchange":      _exchange,
                                    },
                                ),
                                20.0,
                            )
                        else:
                            ingest_result = {"ok": False,
                                             "error": "PDF 下载需使用本地工具；HTML 内容为空"}

                        elapsed_ingest_ms = int((time.monotonic() - t0_ingest) * 1000)
                        _ingest_ok = isinstance(ingest_result, dict) and ingest_result.get("ok")
                        _ingest_summary = (
                            f"成功导入财报：{ingest_result.get('chunks_inserted', 0)} 个文本段"
                            if _ingest_ok
                            else f"导入失败：{(ingest_result or {}).get('error', '未知错误') if isinstance(ingest_result, dict) else ingest_result}"
                        )
                        tool_calls.append(ToolCallRecord(
                            tool_name="financial_document_ingest",
                            display_name="导入财报知识库",
                            arguments={"url": doc_url},
                            status="success" if _ingest_ok else "failed",
                            result_summary=_ingest_summary,
                            raw_result=ingest_result if isinstance(ingest_result, dict) else {},
                        ))
                        await _emit("tool_call_result", {
                            "tool_name":      "financial_document_ingest",
                            "display_name":   "导入财报知识库",
                            "status":         "success" if _ingest_ok else "failed",
                            "result_summary": _ingest_summary,
                            "duration_ms":    elapsed_ingest_ms,
                        })

                    # ── 2B-4: build verified report context for LLM ──────────
                    pub = top_candidate.get("published_at", "")
                    tool_context_parts.append(
                        f"【已审核官方财报】\n"
                        f"标题：{top_candidate.get('title', '')}\n"
                        f"来源：{top_candidate.get('source_name', '')}（{top_candidate.get('source_level', '')}）\n"
                        f"发布时间：{pub}\n"
                        f"URL：{doc_url}\n"
                        f"审核结果：通过（authority_score={verify_result.get('authority_score', 0):.2f}）\n"
                        "注意：如果知识库中未检索到完整财报内容，请基于以上元数据说明数据来源，不得编造具体财报数字。"
                    )

                    # Add kline period info
                    _period = intent.get("period_label", "近30个交易日")
                    if _period and intent.get("need_kline"):
                        tool_context_parts.append(
                            f"【分析框架】用户请求对比财报分析与{_period}行情联动，请在最终回答中分别提供：\n"
                            "1. 经营表现分析（基于财报）\n"
                            "2. 行情复盘（基于K线数据）\n"
                            "3. 基本面与行情联动解读"
                        )

        # ── Phase 2A: financial_rag_search ────────────────────────────────────
        if intent["need_rag"]:
            from app.agents.financial_rag_tool import financial_rag_search as _rag_search

            await _emit("tool_call_start", {
                "tool_name":    "financial_rag_search",
                "display_name": "检索金融知识库",
                "arguments": {
                    "query":  query,
                    "symbol": symbol,
                    "market": market,
                    "top_k":  5,
                },
            })
            t0 = time.monotonic()
            raw_rag = await _run_tool_with_timeout(
                "financial_rag_search",
                _rag_search(query, db, symbol=symbol, market=market, top_k=5),
                _TOOL_TIMEOUTS["financial_rag_search"],
            )
            elapsed_ms = int((time.monotonic() - t0) * 1000)

            rag_ok      = raw_rag.get("ok", False)
            rag_items   = raw_rag.get("results", []) if rag_ok else []
            rag_results = rag_items   # saved for final_answer.sources

            if rag_ok and rag_items:
                count = len(rag_items)
                # Build a type breakdown for result_summary
                from collections import Counter
                type_counts = Counter(r.get("source_type", "document") for r in rag_items)
                type_str = "、".join(
                    f"{_SOURCE_TYPE_LABELS.get(st, st)} {n} 条"
                    for st, n in type_counts.most_common()
                )
                rag_summary = f"检索到 {count} 条相关资料：{type_str}"
            elif rag_ok and not rag_items:
                rag_summary = "知识库中未检索到相关资料"
            else:
                rag_summary = f"知识库检索失败（{raw_rag.get('error', '未知错误')}）"

            rag_record = ToolCallRecord(
                tool_name="financial_rag_search",
                display_name="检索金融知识库",
                arguments={"query": query, "symbol": symbol, "market": market, "top_k": 5},
                status="success" if rag_ok else "failed",
                result_summary=rag_summary,
                raw_result=raw_rag,
                error=raw_rag.get("error"),
            )
            tool_calls.append(rag_record)
            await _emit("tool_call_result", {
                "tool_name":      "financial_rag_search",
                "display_name":   "检索金融知识库",
                "status":         rag_record.status,
                "result_summary": rag_summary,
                "duration_ms":    elapsed_ms,
            })

            # Feed RAG chunks to LLM context
            if rag_items:
                rag_parts = ["【知识库检索】"]
                for i, r in enumerate(rag_items[:5], 1):
                    title       = r.get("title", "")
                    source      = r.get("source", "")
                    pub         = r.get("published_at", "")
                    source_type = _SOURCE_TYPE_LABELS.get(r.get("source_type", ""), "文档")
                    chunk       = r.get("chunk", "")[:600]
                    meta_line   = f"{source_type}·{source}" + (f"·{pub}" if pub else "")
                    rag_parts.append(
                        f"{i}. 《{title}》（{meta_line}）\n   片段：{chunk}"
                    )
                tool_context_parts.append("\n".join(rag_parts))
            else:
                tool_context_parts.append("【知识库检索】当前知识库未检索到相关资料，以下分析基于模型通用知识，不保证与最新财报或公告一致。")

        # ── LLM synthesis phase ───────────────────────────────────────────────

        tool_context = (
            "\n".join(tool_context_parts)
            if tool_context_parts
            else "（本次未调用专项工具，以通用知识作答）"
        )

        lang_hint = {
            "zh-CN": "请用简体中文回答。",
            "zh-TW": "請用繁體中文回答。",
            "en-US": "Please answer in English.",
        }.get(output_language, "请用简体中文回答。")

        user_prompt = (
            f"用户问题：{query}\n\n"
            f"工具数据：\n{tool_context}\n\n"
            f"{lang_hint}"
            "请基于以上真实工具数据生成结构化金融研究回答。"
        )

        messages = [
            {"role": "system", "content": _FINANCIAL_SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ]

        answer_chunks: list[str] = []
        try:
            from app.llm.factory import get_llm_client
            llm = get_llm_client()
            gen = await llm.async_stream_chat(messages, temperature=0.4)

            async def _consume_stream() -> None:
                async for chunk in gen:
                    ctype   = chunk.get("type")
                    content = chunk.get("content", "")
                    if ctype == "thinking" and content:
                        thinking_steps.append(ThinkingStep(content=content))
                        # C28.2: sanitize before emitting; add source for structured display
                        from app.agents.thinking_sanitizer import sanitize_thinking_content  # noqa: PLC0415
                        sanitized = sanitize_thinking_content(content, source="deepseek_reasoning")
                        if sanitized:
                            await _emit("thinking", {
                                "content": sanitized,
                                "source":  "deepseek_reasoning",
                            })
                    elif ctype == "answer" and content:
                        answer_chunks.append(content)
                        await _emit("answer_delta", {"delta": content})
                    elif ctype == "error":
                        log.warning("FinancialAgent LLM stream error: %s", content)

            await asyncio.wait_for(_consume_stream(), timeout=_LLM_TIMEOUT)

        except asyncio.TimeoutError:
            log.warning("FinancialAgent: LLM timed out after %.0fs", _LLM_TIMEOUT)
            if not answer_chunks:
                _tm = (
                    "### 研究摘要\n\n当前 AI 响应超时，无法生成完整分析。\n\n"
                    "### 风险提示\n\n- 实时数据分析暂不可用，请稍后重试\n\n"
                    "_仅供研究参考，不构成任何投资建议。_"
                )
                answer_chunks.append(_tm)
                await _emit("answer_delta", {"delta": _tm})

        except Exception as exc:
            log.warning("FinancialAgent: LLM streaming failed: %s", exc)
            # Sync fallback
            try:
                from app.llm.factory import get_llm_client
                llm2 = get_llm_client()
                fallback_answer = await asyncio.to_thread(
                    lambda: llm2.chat_flash(messages, temperature=0.4)
                )
                answer_chunks = [fallback_answer]
                await _emit("answer_delta", {"delta": fallback_answer})
            except Exception as exc2:
                log.error("FinancialAgent: fallback also failed: %s", exc2)
                _fb = (
                    "### 研究摘要\n\n当前数据服务暂时不可用，请稍后重试。\n\n"
                    "### 风险提示\n\n- 服务临时不可用，结论不可信赖\n\n"
                    "_仅供研究参考，不构成任何投资建议。_"
                )
                answer_chunks = [_fb]

        # ── Assemble final answer ─────────────────────────────────────────────

        raw_answer = "".join(answer_chunks)
        # C28.1: strip model self-talk preamble before the first section header
        raw_answer = _strip_model_preamble(raw_answer)
        answer_text = _filter_banned(raw_answer)
        # C26: unified safety post-processing
        answer_text = sanitize_financial_answer(answer_text)
        if "仅供研究参考" not in answer_text:
            answer_text += f"\n\n_{_DISCLAIMER}_"

        # C28.1: compute proper C27-style DataQuality level from tool_calls
        from app.agents.answer_metadata import compute_data_quality as _compute_dq  # noqa: PLC0415
        _tool_events_for_dq = [
            {"name": tc.tool_name, "status": tc.status, "detail": tc.result_summary or ""}
            for tc in tool_calls
        ]
        _computed_dq = _compute_dq(_tool_events_for_dq, rag_results or [])
        data_quality.level         = _computed_dq.level
        data_quality.reason        = _computed_dq.reason
        data_quality.verified_data = _computed_dq.verified_data
        data_quality.missing_data  = _computed_dq.missing_data
        data_quality.failed_tools  = _computed_dq.failed_tools
        data_quality.warning_flags = _computed_dq.warning_flags
        data_quality.source_count  = _computed_dq.source_count
        data_quality.tool_count    = _computed_dq.tool_count

        # Parse structured sections from markdown answer
        final_answer = _parse_final_answer(answer_text, tool_calls, rag_results, data_quality)

        response = AgentResponse(
            request_id=request_id,
            query=query,
            thinking_steps=thinking_steps,
            tool_calls=tool_calls,
            final_answer=final_answer,
            answer_text=answer_text,
        )

        # Emit structured final_answer event with flat payload for frontend compatibility
        fa_dict = final_answer.model_dump()
        await _emit("final_answer", {
            "request_id":        request_id,
            "full_text":         answer_text,          # C28.1: sanitized preamble-free text
            "summary":           fa_dict.get("summary", ""),
            "analysis":          fa_dict.get("analysis", ""),
            "business_analysis": fa_dict.get("business_analysis", ""),
            "market_analysis":   fa_dict.get("market_analysis", ""),
            "linkage_analysis":  fa_dict.get("linkage_analysis", ""),
            "data_points":       fa_dict.get("data_points", []),
            "risk_points":       fa_dict.get("risk_points", []),
            "sources":           fa_dict.get("sources", []),
            "data_quality":      fa_dict.get("data_quality", {}),
            "disclaimer":        fa_dict.get("disclaimer", _DISCLAIMER),
        })

        return response


def _parse_final_answer(
    answer_text: str,
    tool_calls: list[ToolCallRecord],
    rag_results: list[dict] | None = None,
    data_quality: DataQuality | None = None,
) -> FinalAnswer:
    """Extract structured sections from the markdown answer."""
    import re as _re

    # Extract summary (first ### section or first 2 sentences)
    summary = ""
    m = _re.search(r"###\s*研究摘要\s*\n+(.*?)(?=\n###|\Z)", answer_text, _re.DOTALL)
    if m:
        summary = m.group(1).strip()[:300]
    if not summary:
        # Take first non-empty line
        for line in answer_text.split("\n"):
            line = line.strip().lstrip("#").strip()
            if line and len(line) > 10:
                summary = line[:200]
                break

    # Extract analysis section
    analysis = ""
    for section in ["分析", "关键数据", "关键依据", "分析过程"]:
        m = _re.search(rf"###\s*{section}\s*\n+(.*?)(?=\n###|\Z)", answer_text, _re.DOTALL)
        if m:
            analysis = m.group(1).strip()[:500]
            break
    if not analysis:
        analysis = answer_text[:500]

    # Extract risk points
    risk_points: list[str] = []
    m = _re.search(r"###\s*风险[^#\n]*\s*\n+(.*?)(?=\n###|\Z)", answer_text, _re.DOTALL)
    if m:
        for line in m.group(1).split("\n"):
            line = line.strip().lstrip("-*•·").strip()
            if line and len(line) > 5:
                risk_points.append(line[:150])
    if not risk_points:
        risk_points = ["数据存在延迟，以实盘数据为准", "市场存在不确定性风险"]

    # Build data_points from tool calls
    data_points: list[DataPoint] = []
    for tc in tool_calls:
        if tc.status == "success" and tc.result_summary:
            data_points.append(DataPoint(label=tc.display_name or tc.tool_name, value=tc.result_summary))

    # Phase 2A/2C: build SourceRef list from RAG results (with quality metadata)
    sources: list[SourceRef] = []
    for r in (rag_results or []):
        meta = r.get("metadata", {})
        sources.append(SourceRef(
            title=r.get("title", ""),
            source_type=r.get("source_type", "document"),
            source=r.get("source", ""),
            published_at=r.get("published_at", ""),
            url=meta.get("url", ""),
            page=meta.get("page"),
            # Phase 2C quality fields
            source_level=meta.get("source_level", ""),
            verified=bool(meta.get("verified", False)),
            authority_score=float(meta.get("authority_score", 0.0)),
            report_year=meta.get("report_year"),
            report_type=meta.get("report_type", ""),
            page_start=meta.get("page_start"),
            page_end=meta.get("page_end"),
            search_mode_used=meta.get("search_mode_used", ""),
        ))

    # Phase 2B: extract extended structured sections
    business_analysis = ""
    market_analysis   = ""
    linkage_analysis  = ""
    import re as _re2
    for label, attr in [
        ("经营表现", "business_analysis"),
        ("行情复盘", "market_analysis"),
        ("联动", "linkage_analysis"),
    ]:
        m = _re2.search(rf"###\s*.*{label}.*\s*\n+(.*?)(?=\n###|\Z)", answer_text, _re2.DOTALL)
        if m:
            val = m.group(1).strip()[:800]
            locals()[attr]  # just checking
    m = _re2.search(r"###\s*.*经营表现.*\s*\n+(.*?)(?=\n###|\Z)", answer_text, _re2.DOTALL)
    if m:
        business_analysis = m.group(1).strip()[:800]
    m = _re2.search(r"###\s*.*行情.*复盘.*\s*\n+(.*?)(?=\n###|\Z)", answer_text, _re2.DOTALL)
    if m:
        market_analysis = m.group(1).strip()[:800]
    m = _re2.search(r"###\s*.*联动.*\s*\n+(.*?)(?=\n###|\Z)", answer_text, _re2.DOTALL)
    if m:
        linkage_analysis = m.group(1).strip()[:800]

    return FinalAnswer(
        summary=summary or "分析完成，请查看详细内容。",
        data_points=data_points,
        analysis=analysis,
        business_analysis=business_analysis,
        market_analysis=market_analysis,
        linkage_analysis=linkage_analysis,
        risk_points=risk_points[:5],
        sources=sources[:10],
        data_quality=data_quality or DataQuality(),
        disclaimer=_DISCLAIMER,
    )
