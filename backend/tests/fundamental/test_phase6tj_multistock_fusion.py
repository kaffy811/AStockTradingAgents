from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path


def test_stage2_audit_summarizes_symbols_and_gates(monkeypatch, tmp_path):
    path = Path(__file__).resolve().parents[2] / "scripts" / "company_v2_financial_fusion_stage2_audit.py"
    spec = importlib.util.spec_from_file_location("company_v2_financial_fusion_stage2_audit", path)
    audit = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(audit)

    async def fake_run_symbol(symbol, timeout_seconds):
        return {
            "symbol": symbol,
            "report_id": 1,
            "report_year": 2024,
            "report_type": "annual",
            "report_title": f"{symbol} annual",
            "status": "passed",
            "final_status": "passed",
            "ok": True,
            "cache_hit": False,
            "elapsed_ms": 10.0,
            "timings": {"total_latency_ms": 10.0},
            "summary": {
                "verified": 1,
                "normalized_match": 0,
                "definition_mismatch": 0,
                "period_basis_mismatch": 0,
                "unit_mismatch": 0,
                "value_conflict": 0,
            },
            "fields": [{"field_name": "revenue"}],
            "warnings": [],
            "timeout": False,
            "blocking_issues": [],
            "citation_complete": True,
            "source_trace_complete": True,
        }

    monkeypatch.setattr(audit, "_run_symbol", fake_run_symbol)
    # Redirect artifact writes to tmp_path so mock test data never clobbers
    # the real Stage 2 audit / final gate artifacts in docs/artifacts/.
    monkeypatch.setattr(audit, "STAGE2_AUDIT_JSON", tmp_path / "stage2_audit.json")
    monkeypatch.setattr(audit, "STAGE2_AUDIT_MD", tmp_path / "stage2_audit.md")
    monkeypatch.setattr(audit, "FINAL_JSON", tmp_path / "final_gate.json")
    monkeypatch.setattr(audit, "FINAL_MD", tmp_path / "final_gate.md")
    monkeypatch.setattr(audit.company_v2_financial_fusion_metrics, "snapshot", lambda: {
        "fusion_false_conflict_suspected_total": 0,
        "fusion_cross_report_leakage_total": 0,
        "fusion_symbol_mismatch_total": 0,
        "fusion_missing_citation_total": 0,
        "fusion_incomplete_source_trace_total": 0,
        "fusion_unsupported_merge_total": 0,
        "cache_hit_ratio": 1.0,
    })
    monkeypatch.setattr(audit.company_v2_financial_fusion_health_service, "health", lambda window="24h": {"status": "healthy"})
    monkeypatch.setattr(audit.company_v2_financial_fusion_circuit_breaker, "snapshot", lambda: {"state": "closed"})

    payload = asyncio.run(audit.run_stage2_audit(["600519", "300750", "000725", "000001"], 180.0))
    assert payload["summary"]["reports_ready"] == 4
    assert payload["multistock_fusion_gate_passed"] is True
    assert payload["recommendation_for_production_fusion_rollout"] == "proceed_stage_2"
