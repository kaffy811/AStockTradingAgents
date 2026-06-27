"""
Answer Metadata — C27.

Utilities for computing DataQuality and building SourceRef lists from
tool_events produced by skills. Pure functions, no I/O, no LLM calls.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.agents.schemas import DataQuality, SourceRef

# ---------------------------------------------------------------------------
# C27.1  Tool → source type mapping
# ---------------------------------------------------------------------------

# Maps tool_name → (source_type, display_name_zh)
TOOL_SOURCE_MAP: dict[str, tuple[str, str]] = {
    "get_stock_quote_tool":         ("market_quote",     "实时行情"),
    "get_quote_tool":               ("market_quote",     "实时行情"),
    "get_latest_news_tool":         ("news",             "财经新闻"),
    "get_news_tool":                ("news",             "财经新闻"),
    "search_realtime_news_tool":    ("news",             "实时新闻"),
    "financial_rag_search_tool":    ("rag",              "金融知识库"),
    "get_recent_reports_tool":      ("historical_report","历史报告"),
    "get_report_detail_tool":       ("historical_report","报告详情"),
    "official_report_search":       ("official_report",  "官方财报检索"),
    "universal_market_search_tool": ("tool_result",      "市场热点搜索"),
    "get_fundamental_data_tool":    ("financial_report", "基本面数据"),
    "get_financials_tool":          ("financial_report", "财务数据"),
    # financial_agent.py internal tool names (C28.1)
    "stock_quote_tool":             ("market_quote",      "实时行情"),
    "stock_kline_tool":             ("market_quote",      "行情K线"),
    "financial_news_tool":          ("news",              "财经新闻"),
    "financial_rag_search":         ("rag",               "金融知识库"),
    "verify_financial_report":      ("official_report",   "财报来源审核"),
    "financial_document_ingest":    ("official_report",   "财报知识库导入"),
    "get_industry_news_tool":       ("news",              "行业新闻"),
    "search_realtime_news":         ("news",              "实时新闻"),
    # Internal event names that sometimes leak into source refs (C28.1: Issue 5)
    "rag_retrieve":                 ("rag",               "金融知识库资料"),
    "rag_review":                   ("rag",               "资料质量审查"),
    "unknown":                      ("unknown",           "来源未标注"),
}

# Chinese labels for source_type categories (used in verified_data / missing_data)
_TYPE_LABEL: dict[str, str] = {
    "market_quote":     "实时行情",
    "news":             "财经新闻",
    "rag":              "金融知识库",
    "historical_report":"历史报告",
    "official_report":  "官方财报检索",
    "financial_report": "财务数据",
    "tool_result":      "市场热点搜索",
}

# Source types considered "critical" for financial analysis quality
_CRITICAL_SOURCE_TYPES = {"financial_report", "official_report", "historical_report", "rag"}
_MARKET_TYPES = {"market_quote", "news", "tool_result"}

# Types that must never appear in verified_data (uninformative / internal event names)
_SKIP_FROM_VERIFIED: set[str] = {"unknown"}

# ---------------------------------------------------------------------------
# C27.2  compute_data_quality
# ---------------------------------------------------------------------------

def compute_data_quality(
    tool_events: list[dict],
    rag_results: list | None = None,
    report_results: list | None = None,
) -> DataQuality:
    """
    Derive a DataQuality object from the tool_events list.

    Level rules:
      high        — ≥2 successful tools, no critical-type failures,
                    has (financial_report OR official_report OR historical_report
                         OR rag with ≥1 result)
      medium      — ≥1 successful tool, some missing data, can partially answer
      low         — only market_quote/news/tool_result succeeded, missing financials/reports
      insufficient — 0 successful tools, or all events failed
    """
    successful_types: set[str] = set()
    failed_types:     set[str] = set()
    failed_tool_names: list[str] = []

    for ev in tool_events:
        name   = ev.get("name", "")
        status = ev.get("status", "success")
        src_type, label = TOOL_SOURCE_MAP.get(name, ("unknown", name))

        if status == "success":
            successful_types.add(src_type)
        else:
            failed_types.add(src_type)
            failed_tool_names.append(label or name)

    # Remove duplicates from failed list while preserving order
    seen: set[str] = set()
    deduped_failed: list[str] = []
    for f in failed_tool_names:
        if f not in seen:
            deduped_failed.append(f)
            seen.add(f)

    # C28.2: exclude uninformative types (unknown) from verified_data
    verified_data = [
        _TYPE_LABEL.get(t, t)
        for t in sorted(successful_types)
        if t not in _SKIP_FROM_VERIFIED
    ]
    missing_data  = [_TYPE_LABEL.get(t, t) for t in sorted(failed_types)]

    # C28.1: rag counts as critical only if rag_results has items
    # (tool "success" with 0 results should not elevate level)
    effective_critical = _CRITICAL_SOURCE_TYPES.copy()
    if "rag" in successful_types and (rag_results is not None) and len(rag_results) == 0:
        effective_critical = effective_critical - {"rag"}

    has_critical_success = bool(successful_types & effective_critical)
    has_critical_failure = bool(failed_types     & _CRITICAL_SOURCE_TYPES)
    n_success = len(successful_types)

    # RAG result count (optional enrichment)
    rag_count = len(rag_results) if rag_results else 0

    # Compute level
    if n_success == 0:
        level = "insufficient"
        reason = "所有工具均未能获取数据，无法提供完整分析。"
    elif has_critical_success and n_success >= 2 and not has_critical_failure:
        if rag_results is not None:
            if rag_count >= 1:
                level = "high"
                reason = "已获取多维度数据（含知识库或财报），信息完整度高。"
            else:
                level = "medium"
                reason = "已获取行情/财务数据，但知识库检索无结果。"
        else:
            level = "high"
            reason = "已获取多维度数据，信息完整度高。"
    elif has_critical_success:
        level = "medium"
        reason = "已获取部分关键数据，但仍有数据缺失。"
    elif n_success >= 1:
        # Only market/news/tool_result
        level = "low"
        reason = "仅获取到行情或新闻数据，缺少财务及深度研究数据。"
    else:
        level = "insufficient"
        reason = "数据获取不足，无法提供完整分析。"

    # C28.1: append "最新已披露定期报告" to missing_data when level is low
    # and no financial/official/rag data was available
    if level == "low" and "最新已披露定期报告" not in missing_data:
        missing_data.append("最新已披露定期报告")

    # warning_flags
    warning_flags: list[str] = []
    if has_critical_failure:
        warning_flags.append("部分关键数据工具获取失败")
    if "news" in successful_types and "financial_report" not in successful_types:
        warning_flags.append("仅有新闻标题，无财务数据支撑")
    if level in ("low", "insufficient"):
        warning_flags.append("数据质量受限，分析结论仅供参考")

    return DataQuality(
        # Backward-compat fields
        report_verified        = has_critical_success,
        report_source_level    = "authoritative_media" if has_critical_success else "general",
        market_data_available  = "market_quote" in successful_types,
        warnings               = deduped_failed,
        # C27.1 new fields
        level          = level,
        reason         = reason,
        verified_data  = verified_data,
        missing_data   = missing_data,
        failed_tools   = deduped_failed,
        stale_data     = [],
        source_count   = n_success,
        tool_count     = len(tool_events),
        warning_flags  = warning_flags,
    )


# ---------------------------------------------------------------------------
# C27.3  build_source_refs
# ---------------------------------------------------------------------------

def build_source_refs(
    tool_events: list[dict],
    rag_results: list | None = None,
    report_results: list | None = None,
) -> list[SourceRef]:
    """
    Build SourceRef list from successful tool events.

    - Only successful tools generate a SourceRef.
    - Dedup by (source_type + title).
    - Confidence: market_quote→high, news→low, rag→medium,
                  historical_report→high, official_report→high, others→medium.
    """
    refs: list[SourceRef] = []
    seen_keys: set[str] = set()
    now_iso = datetime.now(timezone.utc).isoformat()

    _CONFIDENCE_MAP: dict[str, str] = {
        "market_quote":     "high",
        "news":             "low",
        "rag":              "medium",
        "historical_report":"high",
        "official_report":  "high",
        "financial_report": "high",
        "tool_result":      "medium",
    }

    for ev in tool_events:
        name   = ev.get("name", "")
        status = ev.get("status", "success")
        detail = ev.get("detail", "")

        if status != "success":
            continue  # failed tools do not generate a SourceRef

        src_type, display = TOOL_SOURCE_MAP.get(name, ("tool_result", None))
        # C28.1: never show raw snake_case as title; use friendly display name or generic label
        title = display or _TYPE_LABEL.get(src_type, "工具结果")
        dedup_key = f"{src_type}:{title}"
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        confidence = _CONFIDENCE_MAP.get(src_type, "medium")
        snippet: str | None = None
        if src_type == "news":
            snippet = "仅标题，需进一步核验"

        ref = SourceRef(
            title        = title,
            source_type  = src_type,
            source       = display or "",   # C28.1: use friendly display, not raw name
            provider     = display or "",
            retrieved_at = now_iso,
            confidence   = confidence,  # type: ignore[arg-type]
            snippet      = snippet,
            id           = str(uuid.uuid4()),
        )
        refs.append(ref)

    # Optionally append RAG results as SourceRef entries
    if rag_results:
        for item in rag_results:
            if not isinstance(item, dict):
                continue
            title = item.get("title") or item.get("source") or "金融知识库"
            dedup_key = f"rag:{title}"
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)
            refs.append(SourceRef(
                title        = title,
                source_type  = "rag",
                source       = item.get("source", ""),
                published_at = item.get("published_at", ""),
                url          = item.get("url", ""),
                confidence   = "medium",
                snippet      = item.get("content", "")[:120] if item.get("content") else None,
                retrieved_at = now_iso,
                id           = str(uuid.uuid4()),
            ))

    # Optionally append historical report results
    if report_results:
        for item in report_results:
            if not isinstance(item, dict):
                continue
            title = item.get("title") or item.get("stock_name") or "历史报告"
            dedup_key = f"historical_report:{title}"
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)
            refs.append(SourceRef(
                title        = title,
                source_type  = "historical_report",
                source       = item.get("source", ""),
                published_at = item.get("created_at", ""),
                confidence   = "high",
                retrieved_at = now_iso,
                id           = str(uuid.uuid4()),
            ))

    return refs


# ---------------------------------------------------------------------------
# C27.4  build_answer_metadata
# ---------------------------------------------------------------------------

def build_answer_metadata(
    tool_events: list[dict],
    rag_results: list | None = None,
    report_results: list | None = None,
    existing_dq: DataQuality | dict | None = None,
) -> dict:
    """
    Compute and return a combined metadata dict with 'data_quality' and 'sources'.

    If existing_dq is provided and already has level != "insufficient",
    the existing DataQuality is preserved (skill-computed metadata takes priority
    over generic tool-event inference).

    Returns:
        {
            "data_quality": dict (DataQuality.model_dump()),
            "sources":      list[dict] (SourceRef.model_dump()),
        }
    """
    dq = compute_data_quality(tool_events, rag_results, report_results)

    if existing_dq is not None:
        # Normalize to dict for uniform handling
        if isinstance(existing_dq, DataQuality):
            edq = existing_dq
        elif isinstance(existing_dq, dict):
            try:
                edq = DataQuality(**existing_dq)
            except Exception:
                edq = None
        else:
            edq = None

        if edq is not None and edq.level != "insufficient":
            # Existing quality is richer — keep it but merge new fields if missing
            if not edq.verified_data:
                edq = edq.model_copy(update={"verified_data": dq.verified_data})
            if not edq.failed_tools:
                edq = edq.model_copy(update={"failed_tools": dq.failed_tools})
            dq = edq

    sources = build_source_refs(tool_events, rag_results, report_results)

    return {
        "data_quality": dq.model_dump(),
        "sources":      [s.model_dump() for s in sources],
    }


# ---------------------------------------------------------------------------
# C27.5  add_data_boundary_declaration
# ---------------------------------------------------------------------------

_BOUNDARY_MESSAGES: dict[str, str] = {
    "low":          "本次数据有限，以下仅能作为初步参考。\n\n",
    "insufficient": "当前数据不足，无法对该问题做出完整判断。\n\n",
    "medium":       "本次数据部分完整，仍有部分关键数据缺失。\n\n",
}


def add_data_boundary_declaration(answer: str, dq: DataQuality | dict) -> str:
    """
    Prepend a data boundary declaration to the answer based on DataQuality level.

    - level="high"        → no change
    - level="medium"      → prepend medium boundary message
    - level="low"         → prepend low boundary message
    - level="insufficient"→ prepend insufficient boundary message

    Idempotent: does not prepend if the message is already present.
    """
    if not answer:
        return answer

    if isinstance(dq, dict):
        level = dq.get("level", "insufficient")
    elif isinstance(dq, DataQuality):
        level = dq.level
    else:
        level = "insufficient"

    prefix = _BOUNDARY_MESSAGES.get(level)
    if prefix is None:
        return answer  # "high" — no declaration needed

    # Idempotency check: strip leading whitespace for comparison
    stripped_prefix = prefix.strip()
    if stripped_prefix in answer[:len(stripped_prefix) + 10]:
        return answer  # already present

    return prefix + answer
