"""
chat_rag/retriever.py — Phase C11 Lightweight RAG Retriever.

Retrieves relevant context from existing internal data sources using
the ToolRegistry (no new dependencies, no external vector DB).

Limits:
  - Max 8 documents total
  - News: max 5 documents
  - Reports: max 3 documents
  - Industry: max 2 documents
  - Failure: returns RAGResult(ok=False), never raises
"""
from __future__ import annotations

import logging
import re
import uuid

from app.agents.chat_rag.base import RAGDocument, RAGResult
from app.agents.chat_skills.base import SkillContext
from app.agents.chat_events import safe_emit

log = logging.getLogger(__name__)

# Max documents per type
_MAX_NEWS = 5
_MAX_REPORTS = 3
_MAX_INDUSTRY = 2
_MAX_TOTAL = 8

# Stock hint extraction (mirrors orchestrator pattern)
_SYMBOL_RE = re.compile(r"\b(\d{5,6})\b")
_STOCK_NAMES = {
    "茅台": ("CN", "600519", "贵州茅台"),
    "贵州茅台": ("CN", "600519", "贵州茅台"),
    "宁德": ("CN", "300750", "宁德时代"),
    "宁德时代": ("CN", "300750", "宁德时代"),
    "中船特气": ("CN", "688146", "中船特气"),
    "688146": ("CN", "688146", "中船特气"),
    "紫金矿业": ("CN", "601899", "紫金矿业"),
    "华大九天": ("CN", "301269", "华大九天"),
    "平安银行": ("CN", "000001", "平安银行"),
    "腾讯": ("HK", "00700", "腾讯控股"),
}
_INDUSTRY_WORDS = re.compile(r"行业|板块|热点|半导体|电子|新能源|医药|消费")


def _extract_hint(query: str) -> dict | None:
    """Extract market/symbol/name from query string."""
    q_lower = query.lower()
    # Explicit symbol
    m = _SYMBOL_RE.search(q_lower)
    if m:
        sym = m.group(1)
        if sym in _STOCK_NAMES:
            mkt, symbol, name = _STOCK_NAMES[sym]
            return {"market": mkt, "symbol": symbol, "name": name, "query": sym}
        return {"market": "CN", "symbol": sym, "name": sym, "query": sym}
    # Named stock
    for name, (mkt, symbol, full_name) in _STOCK_NAMES.items():
        if name in q_lower or name in query:
            return {"market": mkt, "symbol": symbol, "name": full_name, "query": name}
    return None


async def retrieve_context(query: str, context: SkillContext) -> RAGResult:
    """
    Retrieve relevant context documents using existing ToolRegistry tools.

    Returns RAGResult with up to 8 RAGDocuments from:
    - News (external_content=True)
    - Reports (internal_content=True)
    - Industry data (internal_content=True)
    """
    docs: list[RAGDocument] = []

    try:
        hint = _extract_hint(query)
        is_industry_query = bool(_INDUSTRY_WORDS.search(query))
        is_report_query = bool(re.search(r"历史报告|最近报告|上次报告|报告解释|解释报告", query))
        is_watchlist_query = bool(re.search(r"自选股|自选", query))

        await safe_emit(context.event_callback, "rag_retrieve_started", {
            "query": query[:100],
            "max_docs": _MAX_TOTAL,
            "source": "rag_retriever",
        })

        # ── 1. News retrieval ─────────────────────────────────────────────────
        if hint and not is_report_query:
            news_result = await context.tool_registry.call(
                "get_latest_news_tool", context.db,
                event_callback=context.event_callback,
                market=hint["market"], symbol=hint["symbol"],
                hours_back=168, limit=_MAX_NEWS,
            )
            if news_result.ok and news_result.data and news_result.data.get("items"):
                for i, item in enumerate(news_result.data["items"][:_MAX_NEWS]):
                    docs.append(RAGDocument(
                        doc_id=f"news_{i}",
                        source_type="news",
                        title=item.get("title", ""),
                        summary=item.get("summary", item.get("title", ""))[:200],
                        source=item.get("source", "内部新闻数据"),
                        published_at=item.get("publish_time", ""),
                        market=hint["market"],
                        symbol=hint["symbol"],
                        external_content=True,
                        internal_content=False,
                        confidence=0.7,
                    ))

        # ── 2. Reports retrieval ──────────────────────────────────────────────
        if (hint or is_report_query) and len(docs) < _MAX_TOTAL:
            report_result = await context.tool_registry.call(
                "get_recent_reports_tool", context.db,
                event_callback=context.event_callback,
                user_id=context.user_id, limit=_MAX_REPORTS,
            )
            if report_result.ok and report_result.data and report_result.data.get("items"):
                items = report_result.data["items"]
                if hint:
                    # Prioritize reports for the same stock
                    items = [
                        it for it in items
                        if it.get("symbol") == hint.get("symbol")
                    ] + [
                        it for it in items
                        if it.get("symbol") != hint.get("symbol")
                    ]
                for i, item in enumerate(items[:_MAX_REPORTS]):
                    if len(docs) >= _MAX_TOTAL:
                        break
                    docs.append(RAGDocument(
                        doc_id=f"report_{i}",
                        source_type="report",
                        title=item.get("title", f"研究报告 #{item.get('id', i)}"),
                        summary=item.get("summary", "")[:200] or "历史研究报告",
                        source="TradingAgents 内部报告",
                        published_at=item.get("created_at", ""),
                        market=item.get("market"),
                        symbol=item.get("symbol"),
                        external_content=False,
                        internal_content=True,
                        confidence=0.9,
                        metadata={"report_id": item.get("id"), "scope": item.get("scope")},
                    ))

        # ── 3. Industry data ──────────────────────────────────────────────────
        if (is_industry_query or not hint) and len(docs) < _MAX_TOTAL:
            industry_result = await context.tool_registry.call(
                "get_industry_hot_tool", context.db,
                event_callback=context.event_callback,
            )
            if industry_result.ok and industry_result.data:
                items = industry_result.data.get("industries", [])[:_MAX_INDUSTRY]
                for i, item in enumerate(items):
                    if len(docs) >= _MAX_TOTAL:
                        break
                    docs.append(RAGDocument(
                        doc_id=f"industry_{i}",
                        source_type="industry",
                        title=f"{item.get('name', '行业')} 热度数据",
                        summary=f"热度评分：{item.get('hot_score', 0):.1f}，近期涨跌幅：{item.get('avg_change_pct', 0):.1f}%",
                        source="申万行业数据",
                        external_content=False,
                        internal_content=True,
                        confidence=0.85,
                    ))

        source_types = list({d.source_type for d in docs[:_MAX_TOTAL]})
        await safe_emit(context.event_callback, "rag_retrieve_completed", {
            "ok": True,
            "documents_count": len(docs[:_MAX_TOTAL]),
            "source_types": source_types,
            "source": "rag_retriever",
        })
        return RAGResult(
            ok=True,
            query=query,
            documents=docs[:_MAX_TOTAL],
        )

    except Exception as exc:
        log.warning("RAG retriever failed for query %r: %s", query, exc)
        await safe_emit(context.event_callback, "rag_retrieve_completed", {
            "ok": False,
            "error": "retriever_failed",
            "source": "rag_retriever",
        })
        return RAGResult(
            ok=False,
            query=query,
            documents=[],
            error=str(exc),
        )
