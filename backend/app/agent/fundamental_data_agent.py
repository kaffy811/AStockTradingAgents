"""
app/agent/fundamental_data_agent.py — Data Agent (Phase 3)

职责：
- 调用 FundamentalsAggregator 收集多个财报模块
- 压缩数据为 compressed_facts（事实列表）
- 计算数据质量评分
- 不调用 LLM，全部确定性逻辑
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

log = logging.getLogger(__name__)

# 核心收集模块列表（按重要性排序）
_CORE_MODULES = [
    "snapshot",
    "financial_summary",
    "valuation",
    "growth",
    "profitability",
    "cashflow_quality",
    "dupont",
    "asset_structure",
    "solvency",
    "operation_capability",
    "capital_occupation",
    "main_business",
    "dividend_history",
    "major_holders",
    "industry_rank",
    "announcements",
    "analyst_ratings",
]

# 摘要模式只收集最核心模块（减少 token）
_SUMMARY_MODULES = [
    "snapshot", "financial_summary", "valuation",
    "growth", "profitability", "cashflow_quality",
    "dupont", "solvency",
]


def _sf(v: Any) -> float | None:
    """Safe float conversion."""
    if v is None or v == "":
        return None
    try:
        f = float(v)
        import math
        return None if math.isnan(f) or math.isinf(f) else f
    except (TypeError, ValueError):
        return None


def _fmt_period(p: str | None) -> str:
    if not p:
        return ""
    s = str(p)
    if len(s) == 8:
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return s


def _extract_facts_from_series(module_key: str, series: list[dict], fields: list[str], labels: dict[str, str]) -> list[dict]:
    """Extract facts from a time series (most recent N periods)."""
    facts = []
    recent = series[:5]  # max 5 periods
    for i, row in enumerate(recent):
        period = row.get("end_date") or row.get("trade_date") or row.get("ann_date") or ""
        for j, field in enumerate(fields):
            v = _sf(row.get(field))
            if v is None:
                continue
            label = labels.get(field, field)
            fact_id = f"{module_key}_{(i * len(fields) + j):03d}"
            # Simple fact text
            period_str = _fmt_period(period)
            text = f"{period_str} {label}：{v:.2f}" if period_str else f"{label}：{v:.2f}"
            facts.append({
                "fact_id": fact_id,
                "module_key": module_key,
                "metric": field,
                "value": v,
                "period": period,
                "text": text,
            })
    return facts


def _summarize_module(module_key: str, data: dict, field_labels: dict) -> dict:
    """Build a compact summary of module data for data_pack.module_summaries."""
    summary: dict = {}
    if not data:
        return summary

    # Extract the main series
    series = (
        data.get("series") or
        data.get("records") or
        data.get("rankings") or
        data.get("holder_num_series") or
        []
    )

    if series and isinstance(series, list):
        summary["latest_period"] = (series[0] or {}).get("end_date") or (series[0] or {}).get("trade_date") or ""
        summary["period_count"] = len(series)
        # Add first row's numeric fields as scalars
        row0 = series[0] if series else {}
        for k, v in (row0 or {}).items():
            fv = _sf(v)
            if fv is not None and k not in ("ts_code", "symbol"):
                summary[k] = fv
    else:
        # Try scalar fields
        for k, v in data.items():
            if not isinstance(v, (list, dict)):
                fv = _sf(v)
                if fv is not None:
                    summary[k] = fv

    return summary


def _extract_module_facts(module_key: str, data: dict, field_labels: dict) -> list[dict]:
    """Route to appropriate fact extractor based on module structure."""
    if not data:
        return []

    facts = []

    if module_key == "valuation":
        series = data.get("series", [])[:5]
        fields = ["pe_ttm", "pb", "ps_ttm", "pe_percentile", "pb_percentile"]
        facts = _extract_facts_from_series(module_key, series, fields, field_labels)

    elif module_key == "growth":
        series = data.get("series", [])[:5]
        fields = ["revenue_yoy_pct", "net_profit_yoy_pct", "deduct_net_profit_yoy_pct"]
        facts = _extract_facts_from_series(module_key, series, fields, field_labels)

    elif module_key == "profitability":
        series = data.get("series", [])[:5]
        fields = ["gross_margin", "net_margin", "roe", "roa"]
        facts = _extract_facts_from_series(module_key, series, fields, field_labels)

    elif module_key == "cashflow_quality":
        series = data.get("series", [])[:5]
        fields = ["ocf", "net_profit", "cash_cover_ratio", "free_cashflow"]
        facts = _extract_facts_from_series(module_key, series, fields, field_labels)

    elif module_key == "dupont":
        series = data.get("series", [])[:5]
        fields = ["roe", "net_margin", "asset_turnover", "equity_multiplier"]
        facts = _extract_facts_from_series(module_key, series, fields, field_labels)

    elif module_key == "solvency":
        series = data.get("series", [])[:5]
        fields = ["debt_to_assets", "current_ratio", "quick_ratio", "interest_coverage"]
        facts = _extract_facts_from_series(module_key, series, fields, field_labels)

    elif module_key == "asset_structure":
        series = data.get("series", [])[:3]
        fields = ["total_assets", "current_assets", "non_current_assets", "current_asset_ratio_pct"]
        facts = _extract_facts_from_series(module_key, series, fields, field_labels)

    elif module_key == "operation_capability":
        series = data.get("series", [])[:5]
        fields = ["accounts_receivable_turnover", "inventory_turnover", "total_asset_turnover"]
        facts = _extract_facts_from_series(module_key, series, fields, field_labels)

    elif module_key == "industry_rank":
        rankings = data.get("rankings", [])
        for i, r in enumerate(rankings[:8]):
            metric = r.get("metric", "")
            percentile = _sf(r.get("percentile"))
            rank = r.get("rank")
            peer_count = r.get("peer_count")
            if percentile is not None:
                label = field_labels.get(metric, metric)
                text = f"{label} 行业分位：{percentile*100:.0f}%（第 {rank}/{peer_count} 名）"
                facts.append({
                    "fact_id": f"{module_key}_{i:03d}",
                    "module_key": module_key,
                    "metric": metric,
                    "value": round(percentile * 100, 1),
                    "period": "",
                    "text": text,
                })

    elif module_key in ("snapshot", "financial_summary"):
        # Scalar fields
        skip = {"ts_code", "symbol", "name", "_partial_errors"}
        for i, (k, v) in enumerate(data.items()):
            if k in skip or isinstance(v, (list, dict)):
                continue
            fv = _sf(v)
            if fv is not None and i < 10:
                label = field_labels.get(k, k)
                facts.append({
                    "fact_id": f"{module_key}_{i:03d}",
                    "module_key": module_key,
                    "metric": k,
                    "value": fv,
                    "period": "",
                    "text": f"{label}：{fv:.4g}",
                })

    elif module_key == "dividend_history":
        records = data.get("records", [])[:3]
        for i, r in enumerate(records):
            cash_div = _sf(r.get("cash_div"))
            if cash_div is not None:
                period = _fmt_period(r.get("end_date", ""))
                facts.append({
                    "fact_id": f"{module_key}_{i:03d}",
                    "module_key": module_key,
                    "metric": "cash_div",
                    "value": cash_div,
                    "period": r.get("end_date", ""),
                    "text": f"{period} 每股现金分红：{cash_div:.4f} 元",
                })

    elif module_key == "major_holders":
        holder_series = data.get("holder_num_series", [])[:3]
        for i, r in enumerate(holder_series):
            num = _sf(r.get("holder_num"))
            if num is not None:
                period = _fmt_period(r.get("end_date", ""))
                facts.append({
                    "fact_id": f"{module_key}_{i:03d}",
                    "module_key": module_key,
                    "metric": "holder_num",
                    "value": num,
                    "period": r.get("end_date", ""),
                    "text": f"{period} 股东户数：{int(num):,} 户",
                })

    elif module_key == "analyst_ratings":
        summary = data.get("sentiment_summary", {})
        if summary:
            for i, (k, v) in enumerate(summary.items()):
                fv = _sf(v)
                if fv is not None:
                    facts.append({
                        "fact_id": f"{module_key}_{i:03d}",
                        "module_key": module_key,
                        "metric": k,
                        "value": fv,
                        "period": "",
                        "text": f"业绩预告情绪 {k}：{fv:.0f}",
                    })

    else:
        # Generic fallback — try series first
        series = data.get("series") or data.get("records") or []
        if series:
            numeric_keys = [k for k, v in (series[0] or {}).items()
                           if _sf(v) is not None and k not in ("ts_code", "end_date", "trade_date", "ann_date")][:4]
            facts = _extract_facts_from_series(module_key, series[:4], numeric_keys, field_labels)

    return facts


def _compute_quality(
    collected: list[str],
    missing: list[dict],
    partial: list[str],
    stale: list[str],
) -> dict:
    """Compute a data quality score 0-100."""
    total = len(_CORE_MODULES)
    collected_count = len(collected)
    score = int(collected_count / total * 100)
    # Penalize partial (-3 each) and stale (-1 each)
    score -= len(partial) * 3
    score -= len(stale) * 1
    score = max(0, min(100, score))

    if score >= 75:
        level = "high"
    elif score >= 50:
        level = "medium"
    else:
        level = "low"

    issues = []
    for m in missing:
        issues.append(f"缺失模块：{m['module_key']}（{m['reason']}）")
    for k in partial:
        issues.append(f"数据不完整：{k}")

    return {"score": score, "level": level, "issues": issues}


# RAG 查询列表（全量模式用 6 条，摘要模式用前 4 条）
_RAG_QUERIES_FULL = [
    "公司主营业务和收入来源是什么？",
    "公司盈利能力变化如何？",
    "经营活动现金流情况如何？",
    "公司面临哪些主要风险？",
    "公司未来发展战略或经营计划是什么？",
    "公司分红政策或利润分配情况如何？",
]
_RAG_QUERIES_SUMMARY = _RAG_QUERIES_FULL[:4]


async def _collect_rag_context(ts_code: str, db, mode: str) -> tuple[list[dict], list[int], dict]:
    """
    Query ReportRagService with mode-appropriate query set.
    Returns (chunks_list, allowed_chunk_ids, rag_meta).
    Deduplicates by chunk_id. Returns at most 8 chunks (4 for summary).
    Never raises — returns ([], [], {}) on any error.
    """
    from app.services.report_rag_service import report_rag_service

    queries = _RAG_QUERIES_SUMMARY if mode == "summary" else _RAG_QUERIES_FULL
    max_chunks = 4 if mode == "summary" else 8

    seen_ids: set = set()
    all_chunks: list[dict] = []
    last_provider = "mock"
    any_fallback = False

    for query in queries:
        try:
            result = await report_rag_service.query(
                ts_code=ts_code,
                query_text=query,
                db=db,
                top_k=3,
            )
            last_provider = result.get("provider", "mock")
            if result.get("fallback_used"):
                any_fallback = True
            for chunk in result.get("chunks", []):
                cid = chunk.get("chunk_id")
                if cid and cid not in seen_ids:
                    seen_ids.add(cid)
                    content = chunk.get("content", "")
                    all_chunks.append({
                        **chunk,
                        "content": content[:1000],
                    })
            if len(all_chunks) >= max_chunks:
                break
        except Exception as e:
            log.debug("RAG query failed for '%s': %s", query[:30], e)
            continue

    chunks = all_chunks[:max_chunks]
    allowed_ids = [c["chunk_id"] for c in chunks]
    rag_meta = {
        "provider": last_provider,
        "fallback_used": any_fallback,
        "search_mode": "keyword" if any_fallback else "vector",
        "chunk_count": len(chunks),
    }
    return chunks, allowed_ids, rag_meta


class FundamentalDataAgent:
    """
    数据层 Agent — 仅做确定性数据整理，不调用 LLM。
    """

    async def collect(self, market: str, symbol: str, mode: str = "summary", db=None) -> dict:
        """
        Collect fundamentals data and return structured data_pack.

        mode="summary" → collect only _SUMMARY_MODULES
        mode="full"    → collect all _CORE_MODULES
        """
        from app.aggregator.fundamentals_aggregator import get_aggregator
        from app.tools.fundamental import MODULE_CATALOG

        # Build field_labels lookup from MODULE_CATALOG
        catalog_map = {m["key"]: m for m in MODULE_CATALOG}

        agg = get_aggregator()
        target_modules = _SUMMARY_MODULES if mode == "summary" else _CORE_MODULES

        # Collect modules concurrently
        tasks = [agg.fetch_module(market, symbol, key) for key in target_modules]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        ts_code = f"{symbol}.SH"  # simplified; real code available in snapshot data

        collected = []
        missing = []
        stale_mods = []
        partial_mods = []
        module_summaries = {}
        compressed_facts = []

        for module_key, result in zip(target_modules, results):
            meta = catalog_map.get(module_key, {})
            field_labels = meta.get("field_labels", {})

            if isinstance(result, Exception):
                missing.append({"module_key": module_key, "reason": str(result)})
                continue

            envelope = result  # DataEnvelope

            if not envelope.get("ok") or envelope.get("data") is None:
                reason = (envelope.get("partial_errors") or [envelope.get("reason") or "未知错误"])[0]
                missing.append({"module_key": module_key, "reason": str(reason)})
                continue

            collected.append(module_key)
            if envelope.get("stale"):
                stale_mods.append(module_key)
            if envelope.get("partial_errors"):
                partial_mods.append(module_key)

            data = envelope["data"]

            # Try to get ts_code from snapshot data
            if module_key == "snapshot" and isinstance(data, dict):
                ts_code = data.get("ts_code") or ts_code

            # Build summary
            module_summaries[module_key] = _summarize_module(module_key, data, field_labels)

            # Extract facts
            facts = _extract_module_facts(module_key, data, field_labels)
            compressed_facts.extend(facts)

        data_quality = _compute_quality(collected, missing, partial_mods, stale_mods)

        # Collect RAG context if db available
        report_rag_context: list[dict] = []
        allowed_chunk_ids: list[int] = []
        rag_meta: dict = {}
        if db is not None:
            try:
                from app.datasource.tushare_client import _to_ts_code
                ts_code_for_rag = _to_ts_code(market, symbol)
                report_rag_context, allowed_chunk_ids, rag_meta = await _collect_rag_context(
                    ts_code_for_rag, db, mode
                )
                log.info("RAG context: %d chunks for %s", len(report_rag_context), ts_code_for_rag)
            except Exception as e:
                log.warning("RAG context collection failed: %s", e)

        from app.agent.schemas import make_data_pack
        return make_data_pack(
            ts_code=ts_code,
            market=market,
            symbol=symbol,
            collected=collected,
            missing=missing,
            stale=stale_mods,
            partial=partial_mods,
            data_quality=data_quality,
            module_summaries=module_summaries,
            compressed_facts=compressed_facts,
            report_rag_context=report_rag_context,
            allowed_chunk_ids=allowed_chunk_ids,
            rag_meta=rag_meta,
        )
