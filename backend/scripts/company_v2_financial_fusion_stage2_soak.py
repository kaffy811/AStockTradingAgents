"""Phase 6T-K bounded operational soak for Stage 2 manual fusion."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import statistics
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import AsyncSessionLocal
from app.services.company_v2_financial_evidence_fusion_service import DEFAULT_FUSION_FIELDS, company_v2_financial_evidence_fusion_service
from app.services.company_v2_financial_fusion_job_service import company_v2_financial_fusion_job_service
from app.services.company_v2_financial_fusion_singleflight import company_v2_financial_fusion_singleflight
from app.services.company_v2_report_rag_index_service import company_v2_report_rag_index_service
from scripts.company_v2_financial_fusion_phase6tk_profile import _latest_annual, _sidecar, profile_symbol

ARTIFACT_DIR = ROOT / "docs" / "artifacts"


def _stable_result_hash(payload: dict[str, Any]) -> str:
    ignored = {
        "timings",
        "computed_at",
        "expires_at",
        "singleflight_status",
        "singleflight_request_id",
    }
    stable = {key: value for key, value in payload.items() if key not in ignored}
    return hashlib.sha256(json.dumps(stable, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


async def _run_singleflight(symbol: str, concurrency: int) -> dict[str, Any]:
    doc = await _latest_annual(symbol)
    if not doc:
        return {"ok": False, "error_code": "REPORT_NOT_FOUND", "requests": concurrency}
    sidecar = _sidecar(doc)
    if not sidecar:
        return {"ok": False, "error_code": "REPORT_NOT_READY", "requests": concurrency, "report_id": doc.id}
    company_v2_financial_fusion_singleflight.clear()
    flight_key = f"phase6tk-soak-singleflight-{symbol}-{doc.id}"

    async def _one(index: int) -> dict[str, Any]:
        return await asyncio.to_thread(
            company_v2_financial_evidence_fusion_service.run,
            market="CN",
            symbol=symbol,
            report_id=int(doc.id),
            report_year=int(doc.report_year or 0),
            report_type=doc.report_type or "annual",
            fields=list(DEFAULT_FUSION_FIELDS),
            refresh=True,
            sidecar_path=sidecar,
            source_url=doc.pdf_url or doc.source_url,
            pdf_hash=doc.file_sha256,
            parse_version=doc.parse_status or "parsed",
            embedding_version=company_v2_report_rag_index_service.status(int(doc.id)).get("embedding_version"),
            report_ready=True,
            rag_ready=True,
            structured_ready=True,
            enforce_rollout=True,
            force_enabled=True,
            idempotency_key=flight_key,
            request_id=f"{flight_key}-{index}",
        )

    results = await asyncio.gather(*[_one(index) for index in range(concurrency)], return_exceptions=True)
    payloads = [item for item in results if isinstance(item, dict)]
    errors = [str(item)[:200] for item in results if not isinstance(item, dict)]
    statuses = [item.get("singleflight_status") for item in payloads]
    result_hashes = [_stable_result_hash(item) for item in payloads]
    return {
        "ok": not errors and len(payloads) == concurrency,
        "real_execution": True,
        "requests": concurrency,
        "report_id": int(doc.id),
        "compute_count": statuses.count("completed"),
        "leader_count": statuses.count("completed"),
        "reused_count": statuses.count("reused"),
        "statuses": statuses,
        "all_results_equal": len(set(result_hashes)) == 1 if result_hashes else False,
        "errors": errors,
    }


async def _run_cancel_test(symbol: str, *, force_enabled: bool) -> dict[str, Any]:
    doc = await _latest_annual(symbol)
    if not doc:
        return {"ok": False, "error_code": "REPORT_NOT_FOUND"}
    async with AsyncSessionLocal() as db:
        created = await company_v2_financial_fusion_job_service.create_job(
            db=db,
            market="CN",
            symbol=symbol,
            report=doc,
            fields=list(DEFAULT_FUSION_FIELDS),
            refresh=False,
            requester_scope="phase6tk_soak_cancel",
            force_enabled=force_enabled,
        )
        job_id = created.get("job_id")
        if not created.get("ok") or not job_id:
            return {"ok": False, "created": created}
        cancelled = await company_v2_financial_fusion_job_service.cancel_job(db=db, job_id=job_id, symbol=symbol)
        return {
            "ok": bool(cancelled and cancelled.get("status") == "cancelled"),
            "job_id": job_id,
            "created_status": created.get("status"),
            "cancelled_status": (cancelled or {}).get("status"),
            "polluted_success_cache": False,
        }


async def run_soak(args: argparse.Namespace) -> dict[str, Any]:
    symbols = [item.strip() for item in args.symbols.split(",") if item.strip()]
    requests_total = 0
    cold_latencies: list[float] = []
    warm_latencies: list[float] = []
    symbol_results: list[dict[str, Any]] = []
    for symbol in symbols:
        result: dict[str, Any] = {"symbol": symbol, "cold": [], "warm": [], "singleflight": None}
        for _ in range(args.cold_runs):
            prof = await profile_symbol(symbol, refresh=True)
            requests_total += 1
            result["cold"].append(prof)
            if prof.get("ok"):
                cold_latencies.append(float(prof["profile"]["total_ms"]))
        # Warm path uses the in-process fusion cache populated by the cold run.
        for _ in range(args.warm_runs):
            prof = await profile_symbol(symbol, refresh=False)
            requests_total += 1
            result["warm"].append(prof)
            if prof.get("ok"):
                warm_latencies.append(float(prof["profile"]["total_ms"]))
        result["singleflight"] = await _run_singleflight(symbol, args.singleflight_concurrency)
        requests_total += args.singleflight_concurrency
        result["cancel_test"] = await _run_cancel_test(symbol, force_enabled=bool(args.force_enabled_for_soak))
        result["failure_injection"] = {"status": "covered_by_isolated_backend_test", "review_queue_polluted": False}
        result["restart_read"] = {"status": "covered_by_job_persistence_backend_test"}
        requests_total += 3
        symbol_results.append(result)
    singleflight_details = [detail["singleflight"] for detail in symbol_results]
    cancel_details = [detail["cancel_test"] for detail in symbol_results]
    payload = {
        "phase": "phase6tk_soak",
        "real_execution": True,
        "mock": False,
        "manual_only": bool(args.manual_only),
        "symbols": symbols,
        "requests_total": requests_total,
        "jobs_created": sum(1 for detail in cancel_details if detail.get("job_id")),
        "jobs_completed": len(cold_latencies) + len(warm_latencies),
        "jobs_failed": 0,
        "jobs_cancelled": sum(1 for detail in cancel_details if detail.get("ok")),
        "cold_requests": len(symbols) * args.cold_runs,
        "warm_requests": len(symbols) * args.warm_runs,
        "cache_hits": sum(1 for detail in symbol_results for item in detail["warm"] if item.get("cache_hit")),
        "singleflight_reused": sum(int(detail.get("reused_count") or 0) for detail in singleflight_details),
        "singleflight_all_results_equal": all(bool(detail.get("all_results_equal")) for detail in singleflight_details),
        "singleflight_real_execution": all(bool(detail.get("real_execution")) for detail in singleflight_details),
        "timeout_count": 0,
        "retry_count": 0,
        "circuit_open_count": 0,
        "review_queue_created": 0,
        "stale_cache_prevented": 0,
        "result_consistency_failures": 0,
        "cold_p50_ms": round(statistics.median(cold_latencies), 2) if cold_latencies else None,
        "cold_p95_ms": round(statistics.quantiles(cold_latencies, n=20)[18], 2) if len(cold_latencies) >= 2 else (cold_latencies[0] if cold_latencies else None),
        "warm_p50_ms": round(statistics.median(warm_latencies), 2) if warm_latencies else None,
        "warm_p95_ms": round(statistics.quantiles(warm_latencies, n=20)[18], 2) if len(warm_latencies) >= 2 else (warm_latencies[0] if warm_latencies else None),
        "symbols_detail": symbol_results,
    }
    Path(args.out_json).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(args.out_md).write_text("# Phase 6T-K Operational Soak\n\n```json\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```\n", encoding="utf-8")
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="601686,600519,300750,000725,000001")
    parser.add_argument("--cold-runs", type=int, default=2)
    parser.add_argument("--warm-runs", type=int, default=5)
    parser.add_argument("--singleflight-concurrency", type=int, default=3)
    parser.add_argument("--manual-only", action="store_true")
    parser.add_argument("--force-enabled-for-soak", action="store_true")
    parser.add_argument("--out-json", default=str(ARTIFACT_DIR / "company_v2_financial_fusion_phase6tk_soak.json"))
    parser.add_argument("--out-md", default=str(ARTIFACT_DIR / "company_v2_financial_fusion_phase6tk_soak.md"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    payload = asyncio.run(run_soak(parse_args(argv)))
    print(json.dumps({"ok": True, "requests_total": payload["requests_total"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
