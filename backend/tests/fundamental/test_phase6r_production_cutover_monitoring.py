from __future__ import annotations

import json
import importlib.util
from pathlib import Path

from app.core.structured_debug_logger import sanitize_debug_payload
from app.services.company_v2_debug_service import company_v2_debug_service


ROOT = Path(__file__).resolve().parents[3]


def _load_script(name: str):
    path = ROOT / f"backend/scripts/{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


smoke_script = _load_script("company_v2_production_smoke_test")
daily_script = _load_script("company_v2_daily_health_snapshot")
analyze_smoke_payload = smoke_script.analyze_smoke_payload
summarize_daily = daily_script.summarize_daily


def _payload(**summary_overrides):
    summary = {
        "providers_data_success": 8,
        "providers_timeout": 0,
        "modules_renderable": 9,
        "mapping_error_count": 0,
        "render_rule_error_count": 0,
        "trace_missing_count": 0,
        "cache_hit_count": 1,
        "fallback_to_legacy_count": 0,
    }
    summary.update(summary_overrides)
    return {
        "request_id": "rid",
        "schema_version": "2.0",
        "market": "CN",
        "symbol": "600519",
        "ts_code": "600519.SH",
        "partial": False,
        "summary": summary,
        "agent_summary": {"overall_coverage_pct": 66.21},
        "validation_summary": {
            "status": "warning",
            "data_quality_score": 89,
            "strong_failed_count": 0,
            "semantic_warning_count": 2,
            "weak_warning_count": 2,
            "critical_failures": 0,
        },
        "validation_checks": [],
        "modules": {},
    }


def test_production_monitoring_log_event_contains_required_fields():
    event = company_v2_debug_service._production_log_event(_payload(), latency_ms=1234)
    assert event["event_name"] == "company_v2_debug_full_completed"
    assert event["request_id"] == "rid"
    assert event["providers_data_success"] == 8
    assert event["modules_renderable"] == 9
    assert event["coverage_avg"] == 66.21
    assert event["validation_status"] == "warning"
    assert event["data_quality_score"] == 89
    assert event["strong_failed_count"] == 0
    assert event["semantic_warning_count"] == 2


def test_log_event_excludes_raw_and_sensitive_keys():
    payload = _payload()
    payload["raw_full"] = [{"secret": "x", "local_path": "/tmp/a"}]
    safe = sanitize_debug_payload(company_v2_debug_service._production_log_event(payload, latency_ms=1))
    text = json.dumps(safe, ensure_ascii=False)
    assert "raw_full" not in text
    assert "secret" not in text.lower()
    assert "local_path" not in text


def test_smoke_gate_passes_when_thresholds_satisfied_and_allows_semantic_warnings():
    result = analyze_smoke_payload(_payload(), symbol="600519")
    assert result["smoke_gate_pass"] is True
    assert result["semantic_warning_count"] == 2


def test_smoke_gate_fails_when_modules_renderable_low():
    payload = _payload(modules_renderable=7)
    result = analyze_smoke_payload(payload, symbol="600519")
    assert result["smoke_gate_pass"] is False
    assert "MODULES_RENDERABLE_LT_8" in result["failure_reasons"]


def test_smoke_gate_fails_when_provider_data_success_zero():
    result = analyze_smoke_payload(_payload(providers_data_success=0), symbol="600519")
    assert result["smoke_gate_pass"] is False
    assert "NO_PROVIDER_DATA_SUCCESS" in result["failure_reasons"]


def test_smoke_gate_fails_on_strong_validation_failure():
    payload = _payload()
    payload["validation_summary"]["strong_failed_count"] = 1
    result = analyze_smoke_payload(payload, symbol="600519")
    assert result["smoke_gate_pass"] is False
    assert "STRONG_VALIDATION_FAILURE" in result["failure_reasons"]


def test_daily_health_snapshot_summarizes_symbols():
    records = [
        analyze_smoke_payload(_payload(), symbol="600519"),
        analyze_smoke_payload(_payload(modules_renderable=7), symbol="000725"),
    ]
    summary = summarize_daily(records)
    assert summary["total_symbols"] == 2
    assert summary["pass_count"] == 1
    assert summary["fail_count"] == 1
    assert summary["total_semantic_warnings"] == 4


def test_rollout_monitoring_docs_exist_and_no_restricted_wording():
    paths = [
        ROOT / "backend/docs/artifacts/company_v2_production_monitoring_plan.md",
        ROOT / "backend/docs/artifacts/company_v2_production_cutover_monitoring_checklist.md",
    ]
    for path in paths:
        assert path.exists()
        text = path.read_text(encoding="utf-8")
        assert "company_v2_debug_full_completed" in text or "Rollback Triggers" in text
        assert "目标价" not in text
        assert "保证上涨" not in text
