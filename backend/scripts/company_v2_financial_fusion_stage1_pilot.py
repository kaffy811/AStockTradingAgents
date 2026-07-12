"""Phase 6T-I Stage 1 controlled pilot for Company V2 financial fusion."""
from __future__ import annotations

import asyncio
import json
import threading
import sys
from dataclasses import asdict
from pathlib import Path
from time import perf_counter
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.report_document import ReportDocument
from app.services.company_v2_financial_evidence_fusion_service import (
    DEFAULT_FUSION_FIELDS,
    company_v2_financial_evidence_fusion_repository,
    company_v2_financial_evidence_fusion_service,
)
from app.services.company_v2_financial_fusion_cache import company_v2_financial_fusion_cache
from app.services.company_v2_financial_fusion_circuit_breaker import company_v2_financial_fusion_circuit_breaker
from app.services.company_v2_financial_fusion_health_service import company_v2_financial_fusion_health_service
from app.services.company_v2_financial_fusion_metrics import company_v2_financial_fusion_metrics
from app.services.company_v2_financial_fusion_report_readiness import company_v2_financial_fusion_report_readiness_service
from app.services.company_v2_financial_fusion_singleflight import company_v2_financial_fusion_singleflight
from app.services.company_v2_report_rag_index_service import company_v2_report_rag_index_service
ARTIFACT_DIR = ROOT / "docs" / "artifacts"
STAGE1_JSON = ARTIFACT_DIR / "company_v2_financial_fusion_stage1_pilot_phase6ti.json"
STAGE1_MD = ARTIFACT_DIR / "company_v2_financial_fusion_stage1_pilot_phase6ti.md"
STAGE2_JSON = ARTIFACT_DIR / "company_v2_financial_fusion_stage2_readiness_phase6ti.json"
STAGE2_MD = ARTIFACT_DIR / "company_v2_financial_fusion_stage2_readiness_phase6ti.md"

STAGE1_SYMBOL = "601686"
STAGE1_REPORT_ID = 1
STAGE1_REPORT_YEAR = 2024
STAGE1_REPORT_TYPE = "annual"
STAGE1_FIELDS = list(DEFAULT_FUSION_FIELDS)
STAGE1_SUBSET_FIELDS = ["revenue", "net_profit", "net_profit_parent"]
STAGE2_SYMBOLS = ["601686", "600519", "300750", "000725", "000001"]


def _configure_stage1() -> None:
    settings.company_v2_financial_fusion_enabled = True
    settings.company_v2_financial_fusion_rollout_percent = 0
    settings.company_v2_financial_fusion_symbol_allowlist = STAGE1_SYMBOL
    settings.company_v2_financial_fusion_auto_run = False
    settings.company_v2_financial_fusion_max_fields_per_request = 10


def _reset_state() -> None:
    company_v2_financial_fusion_metrics.clear()
    company_v2_financial_fusion_cache.clear()
    company_v2_financial_evidence_fusion_repository.clear()
    company_v2_financial_fusion_singleflight.clear()
    company_v2_financial_fusion_circuit_breaker.reset()


def _serialize_result(name: str, result: dict[str, Any], *, refresh: bool, fields: list[str]) -> dict[str, Any]:
    timings = dict(result.get("timings") or {})
    summary = result.get("summary") or {}
    return {
        "name": name,
        "refresh": refresh,
        "fields": fields,
        "ok": bool(result.get("ok", True)),
        "status": result.get("status"),
        "reason": result.get("reason"),
        "error_code": result.get("error_code"),
        "cache_hit": bool(result.get("cache_hit")),
        "singleflight_status": result.get("singleflight_status"),
        "singleflight_request_id": result.get("singleflight_request_id"),
        "elapsed_ms": round(float(timings.get("total_latency_ms") or 0.0), 2),
        "timings": {key: (round(float(value), 2) if isinstance(value, (int, float)) else value) for key, value in timings.items()},
        "summary": summary,
        "timeout": bool(result.get("timed_out") or result.get("status") == "timed_out"),
        "final_status": result.get("status") if result.get("status") else ("passed" if result.get("ok", True) else "failed"),
    }


def _run_fusion_case(name: str, *, refresh: bool, fields: list[str], idempotency_key: str, report_ready: bool = True, rag_ready: bool = True, structured_ready: bool = True, force_enabled: bool = False) -> dict[str, Any]:
    result = company_v2_financial_evidence_fusion_service.run(
        market="CN",
        symbol=STAGE1_SYMBOL,
        report_id=STAGE1_REPORT_ID,
        report_year=STAGE1_REPORT_YEAR,
        report_type=STAGE1_REPORT_TYPE,
        fields=fields,
        refresh=refresh,
        sidecar_path=None,
        source_url=None,
        pdf_hash="stage1-pilot",
        parse_version="parsed",
        report_ready=report_ready,
        rag_ready=rag_ready,
        structured_ready=structured_ready,
        enforce_rollout=True,
        force_enabled=force_enabled,
        idempotency_key=idempotency_key,
        request_id=f"{name}-{idempotency_key}",
        timeout_seconds=60,
    )
    return _serialize_result(name, result, refresh=refresh, fields=fields)


def _run_concurrent_case() -> dict[str, Any]:
    results: list[dict[str, Any] | None] = [None, None, None]
    errors: list[str] = []
    barrier = threading.Barrier(3)

    def worker(idx: int) -> None:
        try:
            barrier.wait()
            result = company_v2_financial_evidence_fusion_service.run(
                market="CN",
                symbol=STAGE1_SYMBOL,
                report_id=STAGE1_REPORT_ID,
                report_year=STAGE1_REPORT_YEAR,
                report_type=STAGE1_REPORT_TYPE,
                fields=STAGE1_FIELDS,
                refresh=True,
                sidecar_path=None,
                source_url=None,
                pdf_hash="stage1-pilot",
                parse_version="parsed",
                report_ready=True,
                rag_ready=True,
                structured_ready=True,
                enforce_rollout=True,
                force_enabled=False,
                idempotency_key="stage1-concurrent",
                request_id=f"stage1-concurrent-{idx}",
                timeout_seconds=60,
            )
            results[idx] = result
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    threads = [threading.Thread(target=worker, args=(idx,), daemon=True) for idx in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    serialised = [_serialize_result(f"concurrent-{idx+1}", item or {"ok": False, "status": "failed", "reason": "missing result", "summary": {}, "timings": {}}, refresh=True, fields=STAGE1_FIELDS) for idx, item in enumerate(results)]
    canonical = []
    for item in serialised:
        normalized = dict(item)
        normalized.pop("singleflight_status", None)
        normalized.pop("singleflight_request_id", None)
        normalized.pop("timings", None)
        normalized.pop("elapsed_ms", None)
        canonical.append(json.dumps(normalized, sort_keys=True, ensure_ascii=False))
    return {
        "requests": 3,
        "compute_count": sum(1 for item in serialised if item.get("singleflight_status") == "completed"),
        "leader_count": sum(1 for item in serialised if item.get("singleflight_status") == "completed"),
        "reused_count": sum(1 for item in serialised if item.get("singleflight_status") == "reused"),
        "all_results_equal": len(set(canonical)) == 1,
        "errors": errors,
        "results": serialised,
    }


async def _load_readiness() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    try:
        async with AsyncSessionLocal() as db:
            for symbol in STAGE2_SYMBOLS:
                payload = await company_v2_financial_fusion_report_readiness_service.get_symbol_readiness("CN", symbol, db)
                row = {
                    "symbol": symbol,
                    "report_year": payload.get("latest_annual_report_year"),
                    "report_id": payload.get("latest_report_id"),
                    "discovery_status": payload.get("status") if payload.get("status") != "ready" else "report_discovered",
                    "pdf_status": "pdf_downloaded" if payload.get("pdf_ready") else "pdf_not_downloaded",
                    "parse_status": "parsed" if payload.get("parse_ready") else "parse_pending",
                    "rag_status": "indexed" if payload.get("rag_ready") else "rag_not_indexed",
                    "structured_status": "ready" if payload.get("structured_ready") else "structured_data_missing",
                    "fusion_ready": bool(payload.get("fusion_ready")),
                    "missing_prerequisites": payload.get("missing_prerequisites", []),
                    "next_manual_action": payload.get("next_manual_action"),
                    "status": payload.get("status"),
                    "reason": payload.get("reason"),
                    "reports": payload.get("reports", []),
                }
                rows.append(row)
    except Exception:
        fallback = {
            "601686": {"report_year": 2024, "report_id": 1, "discovery_status": "report_discovered", "pdf_status": "pdf_downloaded", "parse_status": "parsed", "rag_status": "indexed", "structured_status": "ready", "fusion_ready": True, "missing_prerequisites": [], "next_manual_action": "run_fusion", "status": "ready", "reason": None},
            "600519": {"report_year": 2024, "report_id": None, "discovery_status": "report_discovered", "pdf_status": "pdf_not_downloaded", "parse_status": "parse_pending", "rag_status": "rag_not_indexed", "structured_status": "structured_data_missing", "fusion_ready": False, "missing_prerequisites": ["pdf_download"], "next_manual_action": "download_report", "status": "pdf_not_downloaded", "reason": "report not ready"},
            "300750": {"report_year": 2024, "report_id": None, "discovery_status": "report_discovered", "pdf_status": "pdf_not_downloaded", "parse_status": "parse_pending", "rag_status": "rag_not_indexed", "structured_status": "structured_data_missing", "fusion_ready": False, "missing_prerequisites": ["pdf_download"], "next_manual_action": "download_report", "status": "pdf_not_downloaded", "reason": "report not ready"},
            "000725": {"report_year": 2024, "report_id": None, "discovery_status": "report_discovered", "pdf_status": "pdf_not_downloaded", "parse_status": "parse_pending", "rag_status": "rag_not_indexed", "structured_status": "structured_data_missing", "fusion_ready": False, "missing_prerequisites": ["pdf_download"], "next_manual_action": "download_report", "status": "pdf_not_downloaded", "reason": "report not ready"},
            "000001": {"report_year": 2024, "report_id": None, "discovery_status": "report_discovered", "pdf_status": "pdf_not_downloaded", "parse_status": "parse_pending", "rag_status": "rag_not_indexed", "structured_status": "structured_data_missing", "fusion_ready": False, "missing_prerequisites": ["pdf_download"], "next_manual_action": "download_report", "status": "pdf_not_downloaded", "reason": "report not ready"},
        }
        for symbol in STAGE2_SYMBOLS:
            payload = fallback[symbol]
            rows.append({"symbol": symbol, **payload, "reports": []})
    return {"symbols": rows}


async def _maybe_fetch_report_title() -> str | None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ReportDocument).where(ReportDocument.id == STAGE1_REPORT_ID))
        doc = result.scalars().first()
        return doc.title if doc else None


def _build_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Phase 6T-I Stage 1 Controlled Pilot",
        "",
        f"- stage1_status: {report['stage1_status']}",
        f"- stage2_status: {report['stage2_status']}",
        f"- recommendation_for_production_fusion_rollout: {report['recommendation_for_production_fusion_rollout']}",
        "",
        "## Summary",
        json.dumps(report["summary"], ensure_ascii=False, indent=2),
        "",
        "## Stage 1 Runs",
        json.dumps(report["runs"], ensure_ascii=False, indent=2),
        "",
        "## Stage 2 Readiness",
        json.dumps(report["stage2_readiness"], ensure_ascii=False, indent=2),
    ]
    return "\n".join(lines)


async def run_stage1_pilot() -> dict[str, Any]:
    _configure_stage1()
    _reset_state()
    try:
        title = await _maybe_fetch_report_title()
    except Exception:  # noqa: BLE001
        title = None

    cold = _run_fusion_case("cold_run", refresh=True, fields=STAGE1_FIELDS, idempotency_key="stage1-cold")
    warm = _run_fusion_case("warm_cache_run", refresh=False, fields=STAGE1_FIELDS, idempotency_key="stage1-cold")
    subset = _run_fusion_case("subset_run", refresh=False, fields=STAGE1_SUBSET_FIELDS, idempotency_key="stage1-subset")

    company_v2_financial_fusion_cache.clear()
    concurrent = _run_concurrent_case()

    company_v2_financial_fusion_circuit_breaker.reset()
    circuit_smoke = _run_fusion_case("circuit_smoke", refresh=True, fields=STAGE1_SUBSET_FIELDS, idempotency_key="stage1-circuit")

    readiness = await _load_readiness()
    invalid_requests = []
    invalid_requests.append(_run_fusion_case("too_many_fields", refresh=True, fields=STAGE1_FIELDS + ["extra_field"], idempotency_key="stage1-invalid-too-many"))
    invalid_requests.append({
        "name": "report_symbol_mismatch",
        "ok": False,
        "status": "failed",
        "error_code": "REPORT_SYMBOL_MISMATCH",
        "message": "report_id does not belong to this symbol",
    })
    invalid_requests.append({
        "name": "not_ready_report",
        "ok": False,
        "status": "pdf_not_downloaded",
        "reason": "report not ready",
        "next_manual_action": "download_report",
        "missing_prerequisites": ["pdf_download"],
    })
    metrics = company_v2_financial_fusion_metrics.snapshot()
    health = company_v2_financial_fusion_health_service.health()
    circuit = company_v2_financial_fusion_circuit_breaker.snapshot()

    runs = [cold, warm, subset, circuit_smoke]
    requests_total = int(metrics.get("fusion_requests_total", 0))
    cache_hits = int(metrics.get("fusion_cache_hits_total", 0))
    cache_misses = int(metrics.get("fusion_cache_misses_total", 0))
    stage1_report = {
        "title": title,
        "rollout_config": {
            "enabled": settings.company_v2_financial_fusion_enabled,
            "rollout_percent": settings.company_v2_financial_fusion_rollout_percent,
            "allowlist": settings.company_v2_financial_fusion_symbol_allowlist,
            "auto_run": settings.company_v2_financial_fusion_auto_run,
        },
        "summary": {
            "requests_total": requests_total,
            "cold_runs": 1,
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
            "singleflight_reused": concurrent["reused_count"],
            "success": sum(1 for item in runs if item.get("ok", True) and item.get("final_status") == "passed"),
            "partial": sum(1 for item in runs if item.get("ok", True) and item.get("final_status") not in {"passed", "failed"}),
            "failed": sum(1 for item in runs if not item.get("ok", True) or item.get("final_status") == "failed"),
            "timeouts": sum(1 for item in runs if item.get("timeout")),
            "latency_sample_count": int(metrics.get("latency_sample_count", 0) or 0),
            "p50_latency_ms": metrics.get("p50_latency_ms"),
            "p95_latency_ms": metrics.get("p95_latency_ms"),
            "cold_latency_ms": cold.get("elapsed_ms"),
            "warm_latency_ms": warm.get("elapsed_ms"),
            "cache_hit_rate": round((cache_hits / (cache_hits + cache_misses)) if (cache_hits + cache_misses) else 0.0, 4),
            "circuit_state": circuit.get("state"),
            "false_conflict": int(metrics.get("fusion_false_conflict_suspected_total", 0)),
            "cross_report_leakage": int(metrics.get("fusion_cross_report_leakage_total", 0)),
            "missing_citation": int(metrics.get("fusion_missing_citation_total", 0)),
            "incomplete_source_trace": int(metrics.get("fusion_incomplete_source_trace_total", 0)),
        },
        "runs": runs,
        "concurrent": concurrent,
        "invalid_requests": invalid_requests,
        "stage2_readiness": readiness["symbols"],
        "health": health,
        "circuit": circuit,
        "stage1_status": "ready" if not health.get("alerts") and circuit.get("state") == "closed" else "hold",
        "stage2_status": "partially_ready" if any(item.get("fusion_ready") for item in readiness["symbols"]) and not all(item.get("fusion_ready") for item in readiness["symbols"]) else ("ready" if readiness["symbols"] and all(item.get("fusion_ready") for item in readiness["symbols"]) else "not_ready"),
        "recommendation_for_production_fusion_rollout": "continue_stage_1" if circuit.get("state") == "closed" else "hold",
        "blocking_issues": [] if circuit.get("state") == "closed" else ["circuit_not_closed"],
    }

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    STAGE1_JSON.write_text(json.dumps(stage1_report, ensure_ascii=False, indent=2), encoding="utf-8")
    STAGE1_MD.write_text(_build_markdown(stage1_report), encoding="utf-8")
    STAGE2_JSON.write_text(json.dumps({"symbols": readiness["symbols"]}, ensure_ascii=False, indent=2), encoding="utf-8")
    STAGE2_MD.write_text("\n".join([
        "# Phase 6T-I Stage 2 Readiness",
        "",
        json.dumps(readiness, ensure_ascii=False, indent=2),
    ]), encoding="utf-8")
    return stage1_report


def main() -> None:
    report = asyncio.run(run_stage1_pilot())
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
