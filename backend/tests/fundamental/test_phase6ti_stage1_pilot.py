from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path


class _FakeAsyncSessionFactory:
    def __call__(self):
        return self

    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


def test_stage1_pilot_writes_artifacts_and_summaries(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[2] / "scripts" / "company_v2_financial_fusion_stage1_pilot.py"
    spec = importlib.util.spec_from_file_location("company_v2_financial_fusion_stage1_pilot", path)
    pilot = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(pilot)

    monkeypatch.setattr(pilot, "ARTIFACT_DIR", tmp_path)
    monkeypatch.setattr(pilot, "STAGE1_JSON", tmp_path / "stage1.json")
    monkeypatch.setattr(pilot, "STAGE1_MD", tmp_path / "stage1.md")
    monkeypatch.setattr(pilot, "STAGE2_JSON", tmp_path / "stage2.json")
    monkeypatch.setattr(pilot, "STAGE2_MD", tmp_path / "stage2.md")
    monkeypatch.setattr(pilot, "AsyncSessionLocal", _FakeAsyncSessionFactory())

    async def fake_readiness(*args, **kwargs):
        return {
            "symbols": [
                {"symbol": "601686", "fusion_ready": True, "status": "ready", "report_year": 2024, "report_id": 1, "missing_prerequisites": [], "next_manual_action": "run_fusion"},
                {"symbol": "600519", "fusion_ready": False, "status": "pdf_not_downloaded", "report_year": 2024, "report_id": 2, "missing_prerequisites": ["pdf_download"], "next_manual_action": "download_report"},
                {"symbol": "300750", "fusion_ready": False, "status": "pdf_not_downloaded", "report_year": 2024, "report_id": 3, "missing_prerequisites": ["pdf_download"], "next_manual_action": "download_report"},
                {"symbol": "000725", "fusion_ready": False, "status": "pdf_not_downloaded", "report_year": 2024, "report_id": 4, "missing_prerequisites": ["pdf_download"], "next_manual_action": "download_report"},
                {"symbol": "000001", "fusion_ready": False, "status": "pdf_not_downloaded", "report_year": 2024, "report_id": 5, "missing_prerequisites": ["pdf_download"], "next_manual_action": "download_report"},
            ]
        }

    monkeypatch.setattr(pilot, "_load_readiness", fake_readiness)
    monkeypatch.setattr(pilot, "_maybe_fetch_report_title", lambda: asyncio.sleep(0, result="2024 annual"))
    monkeypatch.setattr(
        pilot,
        "_run_fusion_case",
        lambda name, **kwargs: {
            "name": name,
            "status": "passed",
            "ok": True,
            "cache_hit": kwargs.get("refresh") is False,
            "singleflight_status": "completed" if name != "warm_cache_run" else "reused",
            "singleflight_request_id": "req-1",
            "elapsed_ms": 111.0 if name == "cold_run" else 11.0,
            "timings": {"total_latency_ms": 111.0 if name == "cold_run" else 11.0},
            "summary": {},
            "timeout": False,
            "final_status": "passed",
        },
    )
    monkeypatch.setattr(
        pilot,
        "_run_concurrent_case",
        lambda: {
            "requests": 3,
            "compute_count": 1,
            "leader_count": 1,
            "reused_count": 2,
            "all_results_equal": True,
            "errors": [],
            "results": [],
        },
    )
    monkeypatch.setattr(
        pilot.company_v2_financial_fusion_metrics,
        "snapshot",
        lambda: {
            "fusion_requests_total": 4,
            "fusion_cache_hits_total": 2,
            "fusion_cache_misses_total": 2,
            "latency_sample_count": 4,
            "p50_latency_ms": 50.0,
            "p95_latency_ms": 120.0,
            "fusion_false_conflict_suspected_total": 0,
            "fusion_cross_report_leakage_total": 0,
            "fusion_missing_citation_total": 0,
            "fusion_incomplete_source_trace_total": 0,
        },
    )
    monkeypatch.setattr(pilot.company_v2_financial_fusion_health_service, "health", lambda window="24h": {"status": "healthy", "alerts": []})
    monkeypatch.setattr(pilot.company_v2_financial_fusion_circuit_breaker, "snapshot", lambda: {"state": "closed"})
    monkeypatch.setattr(pilot.company_v2_financial_fusion_circuit_breaker, "reset", lambda: {"state": "closed"})
    monkeypatch.setattr(
        pilot.company_v2_financial_fusion_report_readiness_service,
        "get_report_readiness",
        lambda market, symbol, report_id, db: asyncio.sleep(0, result={"ok": False, "error_code": "REPORT_SYMBOL_MISMATCH", "message": "report_id does not belong to this symbol"}),
    )
    monkeypatch.setattr(
        pilot.company_v2_financial_fusion_report_readiness_service,
        "get_symbol_readiness",
        lambda market, symbol, db: asyncio.sleep(0, result={"ok": True, "status": "pdf_not_downloaded", "reason": None, "fusion_ready": False, "missing_prerequisites": ["pdf_download"], "next_manual_action": "download_report"}),
    )

    report = asyncio.run(pilot.run_stage1_pilot())

    assert report["stage1_status"] == "ready"
    assert report["stage2_status"] == "partially_ready"
    assert report["recommendation_for_production_fusion_rollout"] == "continue_stage_1"
    assert json.loads((tmp_path / "stage1.json").read_text(encoding="utf-8"))["stage1_status"] == "ready"
    assert "Stage 1 Controlled Pilot" in (tmp_path / "stage1.md").read_text(encoding="utf-8")
