"""Phase 6T-L acceptance runner for Company V2 financial fusion."""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import event, select

from app.core.database import AsyncSessionLocal, async_engine
from app.models.report_document import ReportDocument
from app.services.company_v2_financial_fusion_job_service import company_v2_financial_fusion_job_service
from app.services.company_v2_financial_fusion_singleflight import company_v2_financial_fusion_singleflight
from app.services.company_v2_report_rag_index_service import company_v2_report_rag_index_service
from scripts.company_v2_financial_fusion_stage2_soak import _run_cancel_test, _run_singleflight
from scripts.company_v2_financial_fusion_phase6tk_profile import profile_symbol

ARTIFACT_DIR = ROOT / "docs" / "artifacts"


async def _latest_annual(symbol: str) -> ReportDocument | None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ReportDocument).where(ReportDocument.ts_code.like(f"{symbol}.%")))
        docs = list(result.scalars().all())
        annuals = [doc for doc in docs if (doc.report_type or "").lower() == "annual"]
        pool = annuals or docs
        return sorted(pool, key=lambda item: ((item.report_year or 0), item.id), reverse=True)[0] if pool else None


async def _trace_job_create(symbol: str, fields: list[str]) -> dict[str, Any]:
    doc = await _latest_annual(symbol)
    if not doc:
        return {"ok": False, "error_code": "REPORT_NOT_FOUND", "symbol": symbol}

    query_count = 0

    def _count_query(*_args, **_kwargs):
        nonlocal query_count
        query_count += 1

    event.listen(async_engine.sync_engine, "before_cursor_execute", _count_query)
    started = perf_counter()
    try:
        async with AsyncSessionLocal() as db:
            created = await company_v2_financial_fusion_job_service.create_job(
                db=db,
                market="CN",
                symbol=symbol,
                report=doc,
                fields=fields,
                refresh=False,
                requester_scope="manual",
            )
    finally:
        event.remove(async_engine.sync_engine, "before_cursor_execute", _count_query)

    elapsed_ms = round((perf_counter() - started) * 1000, 2)
    return {
        "ok": bool(created.get("ok")),
        "job_id": created.get("job_id"),
        "status": created.get("status"),
        "cache_hit": bool(created.get("cache_hit")),
        "poll_after_ms": created.get("poll_after_ms"),
        "elapsed_ms": elapsed_ms,
        "sql_query_count": query_count,
        "report_id": doc.id,
        "report_year": doc.report_year,
    }


async def run_acceptance(args: argparse.Namespace) -> dict[str, Any]:
    symbols = [item.strip() for item in args.symbols.split(",") if item.strip()]
    cold_results: list[dict[str, Any]] = []
    warm_results: list[dict[str, Any]] = []
    job_traces: list[dict[str, Any]] = []
    singleflight_results: list[dict[str, Any]] = []
    cancel_results: list[dict[str, Any]] = []

    for symbol in symbols:
        cold_results.append(await profile_symbol(symbol, refresh=True))
        warm_results.append(await profile_symbol(symbol, refresh=False))
        job_traces.append(await _trace_job_create(symbol, list(args.fields)))
        singleflight_results.append(await _run_singleflight(symbol, args.singleflight_concurrency))
        cancel_results.append(await _run_cancel_test(symbol, force_enabled=bool(args.force_enabled_for_soak)))

    cold_latencies = [float(item["profile"]["total_ms"]) for item in cold_results if item.get("ok")]
    warm_latencies = [float(item["profile"]["total_ms"]) for item in warm_results if item.get("ok")]
    job_latencies = [float(item.get("elapsed_ms") or 0.0) for item in job_traces if item.get("ok")]
    steady_job_latencies = job_latencies[1:] if len(job_latencies) > 1 else job_latencies
    cold_job_trace = job_traces[0] if job_traces else {}

    payload = {
        "phase": "phase6tl_acceptance",
        "real_execution": True,
        "mock": False,
        "manual_only": bool(args.manual_only),
        "symbols": symbols,
        "job_create_trace": {
            "p50_ms": round(statistics.median(steady_job_latencies), 2) if steady_job_latencies else None,
            "p95_ms": round(statistics.quantiles(steady_job_latencies, n=20)[18], 2) if len(steady_job_latencies) >= 2 else (steady_job_latencies[0] if steady_job_latencies else None),
            "results": job_traces,
            "steady_state": {
                "p50_ms": round(statistics.median(steady_job_latencies), 2) if steady_job_latencies else None,
                "p95_ms": round(statistics.quantiles(steady_job_latencies, n=20)[18], 2) if len(steady_job_latencies) >= 2 else (steady_job_latencies[0] if steady_job_latencies else None),
                "sample_count": len(steady_job_latencies),
            },
            "connection_cold_create": {
                "elapsed_ms": cold_job_trace.get("elapsed_ms"),
                "sql_query_count": cold_job_trace.get("sql_query_count"),
                "report_id": cold_job_trace.get("report_id"),
                "report_year": cold_job_trace.get("report_year"),
            },
        },
        "cold_trace": {
            "p50_ms": round(statistics.median(cold_latencies), 2) if cold_latencies else None,
            "p95_ms": round(statistics.quantiles(cold_latencies, n=20)[18], 2) if len(cold_latencies) >= 2 else (cold_latencies[0] if cold_latencies else None),
            "results": cold_results,
        },
        "warm_trace": {
            "p50_ms": round(statistics.median(warm_latencies), 2) if warm_latencies else None,
            "p95_ms": round(statistics.quantiles(warm_latencies, n=20)[18], 2) if len(warm_latencies) >= 2 else (warm_latencies[0] if warm_latencies else None),
            "results": warm_results,
        },
        "singleflight": singleflight_results,
        "cancel": cancel_results,
        "repository_backend": getattr(company_v2_report_rag_index_service.repository, "backend", "database"),
        "persistent": bool(getattr(company_v2_report_rag_index_service.repository, "persistent", False)),
    }

    Path(args.out_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(args.out_md).write_text("# Phase 6T-L Acceptance\n\n```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```\n", encoding="utf-8")
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="601686,600519,300750,000725,000001")
    parser.add_argument(
        "--fields",
        default="revenue,net_profit,net_profit_parent,operating_cashflow,total_assets,equity_parent,eps_basic,roe_weighted,total_share,float_share",
    )
    parser.add_argument("--singleflight-concurrency", type=int, default=3)
    parser.add_argument("--manual-only", action="store_true")
    parser.add_argument("--force-enabled-for-soak", action="store_true")
    parser.add_argument("--out-json", default=str(ARTIFACT_DIR / "company_v2_financial_fusion_phase6tl_acceptance.json"))
    parser.add_argument("--out-md", default=str(ARTIFACT_DIR / "company_v2_financial_fusion_phase6tl_acceptance.md"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    payload = asyncio.run(run_acceptance(parse_args(argv)))
    print(json.dumps({"ok": True, "symbols": len(payload["symbols"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
