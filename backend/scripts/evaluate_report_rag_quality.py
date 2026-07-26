#!/usr/bin/env python3
"""
scripts/evaluate_report_rag_quality.py — Phase 6G RAG 检索质量评估

用法：
  cd backend
  python scripts/evaluate_report_rag_quality.py --symbols 600519,000725 --top-k 6

输出：
  docs/artifacts/report_rag_quality_results.json
  docs/artifacts/report_rag_quality_results.csv

说明：
  对已入库 report_chunks 执行预定义 query set，
  检查检索结果是否包含预期关键词（sanity check，非主观评分）。
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
import time
import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Query set ──────────────────────────────────────────────────────────────────

QUERIES = [
    {
        "id": "q1_business",
        "query": "公司的主营业务和收入来源是什么？",
        "expected_keywords": ["主营", "产品", "收入", "业务", "销售"],
    },
    {
        "id": "q2_profitability",
        "query": "公司的盈利能力变化如何？",
        "expected_keywords": ["毛利率", "净利率", "利润", "盈利", "毛利"],
    },
    {
        "id": "q3_cashflow",
        "query": "公司的经营活动现金流情况如何？",
        "expected_keywords": ["经营活动现金流", "现金流量", "收现", "现金"],
    },
    {
        "id": "q4_risk",
        "query": "公司面临哪些主要风险？",
        "expected_keywords": ["风险", "市场风险", "经营风险", "财务风险"],
    },
    {
        "id": "q5_strategy",
        "query": "公司未来发展战略或经营计划是什么？",
        "expected_keywords": ["战略", "计划", "展望", "发展", "目标"],
    },
    {
        "id": "q6_dividend",
        "query": "公司分红政策或利润分配情况如何？",
        "expected_keywords": ["分红", "利润分配", "股利", "派息", "现金分红"],
    },
]


def _check_keywords(content: str, keywords: list[str]) -> tuple[bool, list[str]]:
    """Check if any expected keywords appear in content."""
    found = [kw for kw in keywords if kw in content]
    return len(found) > 0, found


async def evaluate_symbol(
    symbol: str,
    top_k: int,
    db_session,
) -> list[dict]:
    """Run all queries for one symbol and return result rows."""
    from app.services.report_rag_service import report_rag_service
    from app.services.report_embedding_provider import get_report_embedding_provider

    provider = get_report_embedding_provider()
    provider_name = provider.provider_name
    ts_code = f"{symbol}.SH" if symbol.startswith(("6", "5")) else f"{symbol}.SZ"

    rows = []
    for q in QUERIES:
        t0 = time.time()
        try:
            result = await report_rag_service.query(
                ts_code=ts_code,
                query_text=q["query"],
                db=db_session,
                top_k=top_k,
            )
        except Exception as e:
            rows.append({
                "symbol": symbol,
                "query_id": q["id"],
                "query": q["query"],
                "provider": provider_name,
                "top_k": top_k,
                "retrieved_count": 0,
                "top_score": None,
                "top_section_title": None,
                "contains_expected_keywords": False,
                "matched_keywords": "",
                "fallback_used": True,
                "search_mode": "error",
                "elapsed_ms": round((time.time() - t0) * 1000, 1),
                "notes": f"ERROR: {e}",
            })
            continue

        chunks = result.get("chunks", [])
        fallback = result.get("fallback_used", False)
        search_mode = result.get("search_mode", "?")

        elapsed = round((time.time() - t0) * 1000, 1)

        if not chunks:
            rows.append({
                "symbol": symbol,
                "query_id": q["id"],
                "query": q["query"],
                "provider": provider_name,
                "top_k": top_k,
                "retrieved_count": 0,
                "top_score": None,
                "top_section_title": None,
                "contains_expected_keywords": False,
                "matched_keywords": "",
                "fallback_used": fallback,
                "search_mode": search_mode,
                "elapsed_ms": elapsed,
                "notes": "no chunks found — run rag/build first",
            })
            continue

        top = chunks[0]
        all_content = " ".join(c.get("content", "") for c in chunks)
        has_keywords, matched = _check_keywords(all_content, q["expected_keywords"])

        rows.append({
            "symbol": symbol,
            "query_id": q["id"],
            "query": q["query"],
            "provider": provider_name,
            "top_k": top_k,
            "retrieved_count": len(chunks),
            "top_score": top.get("score"),
            "top_section_title": top.get("section_title", ""),
            "contains_expected_keywords": has_keywords,
            "matched_keywords": "; ".join(matched),
            "fallback_used": fallback,
            "search_mode": search_mode,
            "elapsed_ms": elapsed,
            "notes": "" if has_keywords else f"Keywords not found: {q['expected_keywords']}",
        })

    return rows


async def main(symbols: list[str], top_k: int) -> None:
    from app.core.database import AsyncSessionLocal

    print(f"Phase 6G — RAG Quality Evaluation")
    print(f"Symbols: {', '.join(symbols)}")
    print(f"Queries: {len(QUERIES)}, top_k: {top_k}")
    print("=" * 70)

    all_rows = []

    async with AsyncSessionLocal() as db:
        for symbol in symbols:
            print(f"\nEvaluating {symbol}...")
            rows = await evaluate_symbol(symbol, top_k, db)
            for r in rows:
                kw_status = "✓" if r["contains_expected_keywords"] else "✗"
                fb_flag = " [KW]" if r["fallback_used"] else ""
                print(
                    f"  {kw_status} {r['query_id']:15s} retrieved={r['retrieved_count']} "
                    f"score={r['top_score'] or '—':>6}{fb_flag} "
                    f"section={str(r['top_section_title'] or '—')[:30]}"
                )
            all_rows.extend(rows)

    # Summary
    total = len(all_rows)
    hits = sum(1 for r in all_rows if r["contains_expected_keywords"])
    fallbacks = sum(1 for r in all_rows if r["fallback_used"])
    empty = sum(1 for r in all_rows if r["retrieved_count"] == 0)

    print("\n" + "=" * 70)
    print(f"Keyword hit rate : {hits}/{total} ({100*hits//total if total else 0}%)")
    print(f"Fallback (KW)    : {fallbacks}/{total}")
    print(f"Empty results    : {empty}/{total}")

    # Save outputs
    out_dir = Path("docs/artifacts")
    out_dir.mkdir(parents=True, exist_ok=True)
    datestamp = datetime.date.today().strftime("%Y%m%d")
    csv_path  = out_dir / f"report_rag_quality_results_{datestamp}.csv"
    json_path = out_dir / f"report_rag_quality_results_{datestamp}.json"

    fieldnames = [
        "symbol", "query_id", "query", "provider", "top_k",
        "retrieved_count", "top_score", "top_section_title",
        "contains_expected_keywords", "matched_keywords",
        "fallback_used", "search_mode", "elapsed_ms", "notes",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(all_rows)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "run_date": datestamp,
            "symbols": symbols,
            "top_k": top_k,
            "summary": {
                "total_queries": total,
                "keyword_hits": hits,
                "hit_rate_pct": round(100 * hits / total, 1) if total else 0,
                "fallback_count": fallbacks,
                "empty_count": empty,
            },
            "rows": all_rows,
        }, f, ensure_ascii=False, indent=2)

    print(f"\nCSV:  {csv_path}")
    print(f"JSON: {json_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RAG Quality Evaluation")
    parser.add_argument("--symbols", default="600519", help="Comma-separated stock codes")
    parser.add_argument("--top-k", type=int, default=6, help="Number of results per query")
    args = parser.parse_args()
    symbols = [s.strip() for s in args.symbols.split(",")]
    asyncio.run(main(symbols, args.top_k))
