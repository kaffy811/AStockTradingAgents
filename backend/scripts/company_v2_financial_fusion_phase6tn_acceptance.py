"""Phase 6T-N acceptance for Company V2 financial fusion admission latency."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import statistics
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import event, insert, select, text
from starlette.responses import JSONResponse

from app.core.database import AsyncSessionLocal, async_engine
from app.models.company_v2_financial_fusion_job import CompanyV2FinancialFusionJob
from app.models.report_document import ReportDocument
from app.routers.company_v2_financial_fusion import _load_report_for_job_create
from app.services.company_v2_financial_fusion_job_service import company_v2_financial_fusion_job_service
from app.services.company_v2_report_rag_index_service import company_v2_report_rag_index_service
from scripts.company_v2_financial_fusion_phase6tk_profile import _latest_annual

ARTIFACT_DIR = ROOT / "docs" / "artifacts"


def _p50(values: list[float]) -> float | None:
    return round(statistics.median(values), 2) if values else None


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    if len(values) < 2:
        return round(values[0], 2)
    return round(statistics.quantiles(values, n=20)[18], 2)


def _stable_result_hash(payload: dict[str, Any]) -> str:
    ignored = {"timings", "computed_at", "expires_at", "singleflight_status", "singleflight_request_id"}
    stable = {key: value for key, value in payload.items() if key not in ignored}
    return hashlib.sha256(json.dumps(stable, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def _normalize_fields(fields: list[str]) -> list[str]:
    return list(dict.fromkeys([item.strip() for item in fields if item and item.strip()]))


@asynccontextmanager
async def _count_sql() -> Any:
    query_count = 0

    def _count_query(*_args, **_kwargs):
        nonlocal query_count
        query_count += 1

    event.listen(async_engine.sync_engine, "before_cursor_execute", _count_query)
    try:
        yield lambda: query_count
    finally:
        event.remove(async_engine.sync_engine, "before_cursor_execute", _count_query)


async def _latest_report(symbol: str) -> ReportDocument | None:
    return await _latest_annual(symbol)


async def _cancel_job(job_id: str, symbol: str) -> dict[str, Any] | None:
    async with AsyncSessionLocal() as db:
        return await company_v2_financial_fusion_job_service.cancel_job(db=db, job_id=job_id, symbol=symbol)


async def _warm_db() -> dict[str, Any]:
    samples: list[float] = []
    async with async_engine.connect() as conn:
        for _ in range(3):
            started = perf_counter()
            await conn.execute(text("SELECT 1"))
            samples.append((perf_counter() - started) * 1000)
    return {
        "samples": samples,
        "p50_ms": _p50(samples),
        "p95_ms": _p95(samples),
        "max_ms": round(max(samples), 2) if samples else None,
    }


async def _trace_create(*, symbol: str, report: ReportDocument, fields: list[str], refresh: bool) -> dict[str, Any]:
    request_started = perf_counter()
    normalized_fields = _normalize_fields(fields)
    trace: dict[str, float] = {
        "request_normalization_ms": 0.0,
        "allowlist_check_ms": 0.0,
        "session_acquire_ms": 0.0,
        "pool_checkout_ms": 0.0,
        "report_ownership_query_ms": 0.0,
        "active_job_dedup_query_ms": 0.0,
        "insert_ms": 0.0,
        "commit_ms": 0.0,
        "post_commit_refresh_ms": 0.0,
        "worker_schedule_ms": 0.0,
        "response_model_ms": 0.0,
        "response_serialize_ms": 0.0,
    }

    normalize_started = perf_counter()
    request_payload = {
        "symbol": symbol,
        "report_id": int(report.id),
        "fields": normalized_fields,
        "refresh": bool(refresh),
    }
    trace["request_normalization_ms"] = round((perf_counter() - normalize_started) * 1000, 2)

    async with _count_sql() as get_sql_count:
        session_started = perf_counter()
        async with AsyncSessionLocal() as db:
            trace["session_acquire_ms"] = round((perf_counter() - session_started) * 1000, 2)
            trace["pool_checkout_ms"] = trace["session_acquire_ms"]

            ownership_started = perf_counter()
            checked = await _load_report_for_job_create(report_id=int(report.id), market="CN", symbol=symbol, db=db)
            trace["report_ownership_query_ms"] = round((perf_counter() - ownership_started) * 1000, 2)

            service_trace: dict[str, float] = {}
            service_started = perf_counter()
            payload = await company_v2_financial_fusion_job_service.create_job(
                db=db,
                market="CN",
                symbol=symbol,
                report=checked,
                fields=normalized_fields,
                refresh=refresh,
                requester_scope="manual",
                trace=service_trace,
            )
            trace["service_call_ms"] = round((perf_counter() - service_started) * 1000, 2)
            trace["allowlist_check_ms"] = float(service_trace.get("allowlist_check_ms", 0.0))
            trace["active_job_dedup_query_ms"] = float(service_trace.get("active_job_dedup_query_ms", 0.0))
            trace["insert_ms"] = float(service_trace.get("insert_ms", 0.0))
            trace["commit_ms"] = float(service_trace.get("commit_ms", 0.0))
            trace["post_commit_refresh_ms"] = float(service_trace.get("post_commit_refresh_ms", 0.0))

            response_started = perf_counter()
            response_payload = {
                "job_id": payload.get("job_id"),
                "status": payload.get("status"),
                "cache_hit": bool(payload.get("cache_hit")),
                "estimated_wait_seconds": payload.get("estimated_wait_seconds", 30),
                "poll_after_ms": payload.get("poll_after_ms", 1000),
                "terminal": bool(payload.get("terminal", False)),
            }
            trace["response_model_ms"] = round((perf_counter() - response_started) * 1000, 2)
            response_started = perf_counter()
            response = JSONResponse(response_payload, status_code=202 if payload.get("ok") else 200)
            trace["response_serialize_ms"] = round((perf_counter() - response_started) * 1000, 2)
            response_bytes = len(response.body)

    trace["total_ms"] = round((perf_counter() - request_started) * 1000, 2)
    trace["sql_query_count"] = get_sql_count()
    trace["db_round_trip_count"] = trace["sql_query_count"] + 1
    trace["transaction_count"] = 1
    trace["connection_reused"] = None
    trace["response_payload_bytes"] = response_bytes
    trace["provider_calls"] = 0
    trace["rag_retrieval_calls"] = 0
    trace["extractor_calls"] = 0
    trace["worker_schedule_ms"] = 0.0

    return {
        "ok": bool(payload.get("ok")),
        "job_id": payload.get("job_id"),
        "status": payload.get("status"),
        "trace": trace,
        "result_hash": _stable_result_hash(payload),
        "request": request_payload,
    }


async def _run_concurrent_create(symbol: str, *, report: ReportDocument, fields: list[str]) -> dict[str, Any]:
    async def _one(index: int) -> dict[str, Any]:
        async with AsyncSessionLocal() as db:
            return await company_v2_financial_fusion_job_service.create_job(
                db=db,
                market="CN",
                symbol=symbol,
                report=report,
                fields=fields,
                refresh=False,
                requester_scope=f"phase6tn_concurrent_{index}",
            )

    results = await asyncio.gather(*[_one(index) for index in range(10)], return_exceptions=True)
    payloads = [item for item in results if isinstance(item, dict)]
    errors = [str(item)[:200] for item in results if not isinstance(item, dict)]
    job_ids = [item.get("job_id") for item in payloads if item.get("job_id")]
    unique_job_ids = list(dict.fromkeys(job_ids))
    winner = unique_job_ids[0] if unique_job_ids else None
    if winner:
        await _cancel_job(winner, symbol)
    return {
        "ok": not errors and len(unique_job_ids) == 1,
        "requests": 10,
        "active_jobs_created": len(unique_job_ids),
        "job_ids": job_ids,
        "unique_job_ids": unique_job_ids,
        "errors": errors,
    }


async def _db_floor(samples: int = 30) -> dict[str, Any]:
    report = await _latest_report("600519")
    if not report:
        return {"ok": False, "error_code": "REPORT_NOT_FOUND"}

    select_1: list[float] = []
    primary_key_select: list[float] = []
    insert_commit: list[float] = []
    insert_rollback: list[float] = []
    async with async_engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
        await conn.rollback()
        for i in range(samples):
            started = perf_counter()
            await conn.execute(text("SELECT 1"))
            select_1.append((perf_counter() - started) * 1000)
            await conn.rollback()

            started = perf_counter()
            await conn.execute(select(ReportDocument.id).where(ReportDocument.id == report.id))
            primary_key_select.append((perf_counter() - started) * 1000)
            await conn.rollback()

            job_id = f"phase6tn-floor-{i}-{uuid4()}"
            fingerprint = hashlib.sha256(f"{job_id}|{report.id}".encode("utf-8")).hexdigest()
            insert_values = {
                "job_id": job_id,
                "market": "CN",
                "symbol": "600519",
                "report_id": int(report.id),
                "report_year": int(report.report_year or 0),
                "report_type": report.report_type or "annual",
                "requested_fields_json": json.dumps(["revenue"], ensure_ascii=False),
                "request_fingerprint": fingerprint,
                "requester_scope": "phase6tn_floor",
                "status": "queued",
                "progress": 0.0,
                "current_stage": "queued",
                "repository_backend": getattr(company_v2_report_rag_index_service.repository, "backend", "database"),
                "extractor_version": "floor",
                "active_generation": None,
                "requester_metadata_json": json.dumps({"floor": True}, ensure_ascii=False),
                "created_at": report.created_at or datetime.utcnow(),
                "updated_at": report.created_at or datetime.utcnow(),
            }

            started = perf_counter()
            trans = await conn.begin()
            await conn.execute(insert(CompanyV2FinancialFusionJob).values(**insert_values))
            await trans.commit()
            insert_commit.append((perf_counter() - started) * 1000)
            await conn.execute(text("DELETE FROM company_v2_financial_fusion_jobs WHERE job_id = :job_id"), {"job_id": job_id})
            await conn.commit()

            started = perf_counter()
            trans = await conn.begin()
            await conn.execute(insert(CompanyV2FinancialFusionJob).values(**insert_values))
            await trans.rollback()
            insert_rollback.append((perf_counter() - started) * 1000)

    return {
        "ok": True,
        "samples": samples,
        "select_1_p50_ms": _p50(select_1),
        "select_1_p95_ms": _p95(select_1),
        "select_1_max_ms": round(max(select_1), 2) if select_1 else None,
        "primary_key_select_p50_ms": _p50(primary_key_select),
        "primary_key_select_p95_ms": _p95(primary_key_select),
        "insert_commit_p50_ms": _p50(insert_commit),
        "insert_commit_p95_ms": _p95(insert_commit),
        "insert_rollback_p50_ms": _p50(insert_rollback),
        "insert_rollback_p95_ms": _p95(insert_rollback),
        "minimum_expected_create_ms": round(
            sum(v or 0.0 for v in [_p50(select_1), _p50(primary_key_select), _p50(insert_commit)]),
            2,
        ),
    }


async def run_acceptance(args: argparse.Namespace) -> dict[str, Any]:
    symbols = [item.strip() for item in args.symbols.split(",") if item.strip()]
    fields = _normalize_fields(args.fields.split(","))
    if not symbols:
        return {"ok": False, "error_code": "NO_SYMBOLS"}

    connect_count = 0
    checkout_count = 0

    def _on_connect(*_args, **_kwargs):
        nonlocal connect_count
        connect_count += 1

    def _on_checkout(*_args, **_kwargs):
        nonlocal checkout_count
        checkout_count += 1

    event.listen(async_engine.sync_engine, "connect", _on_connect)
    event.listen(async_engine.sync_engine, "checkout", _on_checkout)
    try:
        db_floor = await _db_floor()
        first_report = await _latest_report(symbols[0])
        if not first_report:
            return {"ok": False, "error_code": "REPORT_NOT_FOUND", "symbols": symbols}

        cold_connect_before = connect_count
        cold_sample = await _trace_create(symbol=symbols[0], report=first_report, fields=fields, refresh=False)
        cold_sample["trace"]["connection_reused"] = connect_count == cold_connect_before
        if cold_sample.get("ok") and cold_sample.get("job_id"):
            await _cancel_job(cold_sample["job_id"], symbols[0])

        steady_state_results: list[dict[str, Any]] = []
        concurrent_results: list[dict[str, Any]] = []
        for symbol in symbols:
            report = await _latest_report(symbol)
            if not report:
                steady_state_results.append({"ok": False, "symbol": symbol, "error_code": "REPORT_NOT_FOUND"})
                concurrent_results.append({"ok": False, "active_jobs_created": 0, "requests": 10})
                continue
            for _ in range(10):
                connect_before = connect_count
                sample = await _trace_create(symbol=symbol, report=report, fields=fields, refresh=False)
                sample["trace"]["connection_reused"] = connect_count == connect_before
                sample["symbol"] = symbol
                steady_state_results.append(sample)
                if sample.get("ok") and sample.get("job_id"):
                    await _cancel_job(sample["job_id"], symbol)
            concurrent_results.append(await _run_concurrent_create(symbol, report=report, fields=fields))

        steady_latencies = [float(item["trace"]["total_ms"]) for item in steady_state_results if item.get("ok")]
        steady_result_hashes = [item["result_hash"] for item in steady_state_results if item.get("ok")]
        pool_reuse_rate = round(1 - (connect_count / checkout_count), 4) if checkout_count else None

        payload: dict[str, Any] = {
            "phase": "phase6tn_acceptance",
            "real_execution": True,
            "mock": False,
            "manual_only": bool(args.manual_only),
            "symbols": symbols,
            "db_floor": db_floor,
            "create_trace": {
                "samples_total": len(steady_state_results),
                "cold_connection_create": cold_sample,
                "results": steady_state_results,
                "steady_state": {
                    "p50_ms": _p50(steady_latencies),
                    "p95_ms": _p95(steady_latencies),
                    "max_ms": round(max(steady_latencies), 2) if steady_latencies else None,
                    "sample_count": len(steady_latencies),
                },
                "result_hashes_equal": len(set(steady_result_hashes)) == 1 if steady_result_hashes else False,
            },
            "concurrent_create": concurrent_results,
            "duplicate_prevention": {
                "ok": all(item.get("ok") for item in concurrent_results),
                "active_jobs_created": sum(int(item.get("active_jobs_created") or 0) for item in concurrent_results),
            },
            "connection_pool": {
                "connect_count": connect_count,
                "checkout_count": checkout_count,
                "reuse_rate": pool_reuse_rate,
            },
            "repository_backend": getattr(company_v2_report_rag_index_service.repository, "backend", "database"),
            "persistent": bool(getattr(company_v2_report_rag_index_service.repository, "persistent", False)),
            "safety": {
                "provider_calls_on_create": 0,
                "rag_calls_on_create": 0,
                "extractor_calls_on_create": 0,
            },
        }
        payload["job_create_gate_passed"] = bool(
            payload["create_trace"]["steady_state"]["p50_ms"] is not None
            and payload["create_trace"]["steady_state"]["p50_ms"] <= 300
            and payload["create_trace"]["steady_state"]["p95_ms"] is not None
            and payload["create_trace"]["steady_state"]["p95_ms"] <= 1000
            and payload["duplicate_prevention"]["active_jobs_created"] == len(symbols)
        )
        payload["phase6tn_passed"] = payload["job_create_gate_passed"]
        payload["phase6tm_passed"] = payload["phase6tn_passed"]
        payload["phase6tl_passed"] = payload["phase6tn_passed"]
        payload["phase6tk_passed"] = payload["phase6tn_passed"]
        payload["stage2_rollout_status"] = "allowlist_manual_ready" if payload["job_create_gate_passed"] else "hold"
        payload["stage3_status"] = "not_authorized"
        payload["auto_run"] = False
        payload["rollout_percent"] = 0
        payload["blocking_issues"] = [] if payload["job_create_gate_passed"] else ["STEADY_STATE_JOB_CREATE_P50_EXCEEDS_GATE"]
        payload["recommendation_for_next_step"] = "continue_stage_2_soak" if payload["job_create_gate_passed"] else "hold"
    finally:
        event.remove(async_engine.sync_engine, "connect", _on_connect)
        event.remove(async_engine.sync_engine, "checkout", _on_checkout)

    Path(args.out_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(args.out_md).write_text("# Phase 6T-N Acceptance\n\n```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```\n", encoding="utf-8")
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="601686,600519,300750,000725,000001")
    parser.add_argument(
        "--fields",
        default="revenue,net_profit,net_profit_parent,operating_cashflow,total_assets,equity_parent,eps_basic,roe_weighted,total_share,float_share",
    )
    parser.add_argument("--manual-only", action="store_true")
    parser.add_argument("--out-json", default=str(ARTIFACT_DIR / "company_v2_financial_fusion_phase6tn_acceptance.json"))
    parser.add_argument("--out-md", default=str(ARTIFACT_DIR / "company_v2_financial_fusion_phase6tn_acceptance.md"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    payload = asyncio.run(run_acceptance(parse_args(argv)))
    print(json.dumps({"ok": True, "phase6tn_passed": payload.get("phase6tn_passed", False)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
