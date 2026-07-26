from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _load_readiness():
    path = ROOT / "backend/scripts/company_v2_cutover_readiness_check.py"
    spec = importlib.util.spec_from_file_location("company_v2_cutover_readiness_check", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _smoke_record(**overrides):
    record = {
        "symbol": "600519",
        "providers_data_success": 8,
        "modules_renderable": 9,
        "strong_failed_count": 0,
        "critical_validation_failures": 0,
        "data_quality_score": 89,
        "mapping_error_count": 0,
        "render_rule_error_count": 0,
        "trace_missing_count": 0,
        "semantic_warning_count": 2,
    }
    record.update(overrides)
    return record


def _smoke(records=None):
    return {"smoke_gate_pass": True, "records": records or [_smoke_record(), _smoke_record(symbol="000725"), _smoke_record(symbol="601686")]}


def _daily(**overrides):
    summary = {
        "pass_count": 3,
        "fail_count": 0,
        "total_semantic_warnings": 6,
        "total_strong_failures": 0,
    }
    summary.update(overrides)
    return {"summary": summary, "records": []}


def test_readiness_check_passes_with_valid_smoke_daily_artifacts():
    readiness = _load_readiness()
    report = readiness.analyze_readiness(_smoke(), _daily(), docs=[])
    assert report["cutover_ready"] is True
    assert report["recommended_level"] == "Level 3 production default v2"
    assert report["required_env_change"] == "VITE_COMPANY_TAB_VERSION=v2"
    assert report["rollback_available"] is True
    assert report["legacy_available"] is True


def test_readiness_check_fails_if_strong_failed_count_positive():
    readiness = _load_readiness()
    report = readiness.analyze_readiness(_smoke([_smoke_record(strong_failed_count=1)]), _daily(), docs=[])
    assert report["cutover_ready"] is False
    assert any("strong_failed_count" in issue for issue in report["blocking_issues"])


def test_readiness_check_fails_if_modules_renderable_low():
    readiness = _load_readiness()
    report = readiness.analyze_readiness(_smoke([_smoke_record(modules_renderable=7)]), _daily(), docs=[])
    assert report["cutover_ready"] is False
    assert any("modules_renderable<8" in issue for issue in report["blocking_issues"])


def test_readiness_check_fails_if_provider_data_success_zero():
    readiness = _load_readiness()
    report = readiness.analyze_readiness(_smoke([_smoke_record(providers_data_success=0)]), _daily(), docs=[])
    assert report["cutover_ready"] is False
    assert any("providers_data_success=0" in issue for issue in report["blocking_issues"])


def test_readiness_check_allows_semantic_warnings():
    readiness = _load_readiness()
    report = readiness.analyze_readiness(_smoke([_smoke_record(semantic_warning_count=9)]), _daily(total_semantic_warnings=9), docs=[])
    assert report["cutover_ready"] is True
    assert any("semantic_warnings" in warning for warning in report["warnings"])


def test_phase6s_docs_exist_and_avoid_restricted_wording():
    docs = [
        "backend/docs/artifacts/company_v2_production_staged_cutover.md",
        "backend/docs/artifacts/company_v2_phase6s_pre_cutover_gate.md",
        "backend/docs/artifacts/company_v2_phase6s_rollback_verification.md",
        "backend/docs/artifacts/company_v2_phase6s_observation_window.md",
    ]
    for doc in docs:
        path = ROOT / doc
        assert path.exists()
        text = path.read_text(encoding="utf-8")
        assert "VITE_COMPANY_TAB_VERSION" in text or "Observation" in text
        for forbidden in ["目标价", "保证上涨"]:
            assert forbidden not in text
