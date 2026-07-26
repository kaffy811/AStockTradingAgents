from __future__ import annotations

import argparse
import json

from scripts import (
    financial_agent_live_shadow_acceptance as live_shadow,
    live_db_pool_strategy,
    live_external_test_results,
    security_entity_live_sampling,
)


def test_db_pool_strategy_blocks_when_preflight_not_ready(tmp_path):
    preflight = tmp_path / "preflight.json"
    preflight.write_text(
        json.dumps({"environment_ready": False, "blockers": ["DNS_GAIERROR"], "environment": {"database_mode": "transaction_pooler"}}),
        encoding="utf-8",
    )
    payload = live_db_pool_strategy.build_payload(preflight_path=preflight)
    assert payload["schema_version"] == "live_db_pool_strategy.v1"
    assert payload["status"] == "blocked"
    assert payload["selected_strategy"] is None
    assert len(payload["strategies"]) == 2
    assert all(strategy["status"] == "not_run" for strategy in payload["strategies"])


def test_security_live_sampling_blocks_without_ready_environment(tmp_path):
    preflight = tmp_path / "preflight.json"
    preflight.write_text(json.dumps({"environment_ready": False, "blockers": ["POSTGRES_NOT_READY"]}), encoding="utf-8")
    payload = security_entity_live_sampling.build_payload(preflight_path=preflight)
    assert payload["schema_version"] == "security_entity_live_sampling.v1"
    assert payload["status"] == "blocked"
    assert payload["markets"]["CN"]["requested_active_full_scan"] == 5166
    assert payload["markets"]["HK"]["requested_active_full_scan"] == 30
    assert payload["markets"]["US"]["requested_active_full_scan"] == 0
    assert payload["success_rate"] is None


def test_live_external_result_artifact_classifies_failures():
    args = argparse.Namespace(
        environment_id="test",
        region="unknown",
        external_environment="unit",
        live_external_status="failed",
        live_external_passed=0,
        live_external_skipped=0,
        live_external_failed=15,
        live_external_duration_seconds=4.54,
        live_external_reason="DNS_RESOLUTION_FAILED",
        live_external_failure_classification="environment",
        soak_status="no_tests_collected",
        soak_passed=0,
        soak_skipped=0,
        soak_failed=0,
        soak_duration_seconds=1.09,
        soak_reason="NO_TESTS_MATCHED_SOAK_MARKER",
        soak_failure_classification="test_defect",
    )
    payload = live_external_test_results.build_payload(args)
    assert payload["schema_version"] == "live_external_test_results.v1"
    assert payload["passed"] is False
    assert payload["failures"][0]["classification"] == "environment"
    assert payload["suites"]["soak"]["status"] == "no_tests_collected"


def test_runtime_gate_keeps_recommendation_null_when_zero_executed(tmp_path):
    paths = live_shadow.generate_blocked_artifacts(
        output_dir=tmp_path,
        reason="TEST_ENV_NOT_READY",
        default_full_local_passed=True,
    )
    gate = json.loads(paths["runtime_gate"].read_text(encoding="utf-8"))
    results = json.loads(paths["results"].read_text(encoding="utf-8"))
    assert results["executed_sample_count"] == 0
    assert gate["recommended_next_intent"] is None
    assert gate["layered_enabled"] is False
    assert gate["authorized_intents"] == []
