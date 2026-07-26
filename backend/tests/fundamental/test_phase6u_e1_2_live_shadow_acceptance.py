from __future__ import annotations

import json

from scripts import financial_agent_live_shadow_acceptance as live_shadow


def test_live_shadow_blocked_artifact_schema(tmp_path):
    paths = live_shadow.generate_blocked_artifacts(
        output_dir=tmp_path,
        reason="TEST_LIVE_NOT_CONFIGURED",
        default_full_local_passed=True,
    )
    results = json.loads(paths["results"].read_text(encoding="utf-8"))
    runtime_gate = json.loads(paths["runtime_gate"].read_text(encoding="utf-8"))
    intent_gates = json.loads(paths["intent_gates"].read_text(encoding="utf-8"))

    assert results["schema_version"] == "financial_agent_live_shadow.v1"
    assert results["requested_sample_count"] >= 50
    assert results["executed_sample_count"] == 0
    assert results["execution_status"] == "blocked"
    assert results["mode"] == "live_shadow_required_not_executed"
    assert set(live_shadow.FIRST_BATCH_INTENTS).issubset(results["intent_sample_counts"])
    assert runtime_gate["layered_enabled"] is False
    assert runtime_gate["authorized_intents"] == []
    assert runtime_gate["decision"] == "do_not_enable_layered_v1"
    assert intent_gates["authorized_intents"] == []
    assert all(not gate["passed"] for gate in intent_gates["intents"].values())


def test_live_shadow_artifact_sanitizes_sensitive_fields(tmp_path):
    paths = live_shadow.generate_blocked_artifacts(
        output_dir=tmp_path,
        reason="TEST_LIVE_NOT_CONFIGURED",
        default_full_local_passed=None,
    )
    payload = "\n".join(path.read_text(encoding="utf-8") for path in paths.values()).lower()
    forbidden = [
        "prompt",
        "chain-of-thought",
        "jwt",
        "database_url",
        "supabase.com",
        "api_key",
        "password",
        "贵州茅台最新财报表现如何",
        "五粮液最新价是多少",
    ]
    for token in forbidden:
        assert token not in payload


def test_live_shadow_blocked_run_has_no_side_effects(tmp_path):
    paths = live_shadow.generate_blocked_artifacts(
        output_dir=tmp_path,
        reason="TEST_LIVE_NOT_CONFIGURED",
        default_full_local_passed=True,
    )
    results = json.loads(paths["results"].read_text(encoding="utf-8"))
    assert results["side_effects"] == {
        "message_writes": 0,
        "context_writes": 0,
        "watchlist_writes": 0,
        "report_writes": 0,
        "job_writes": 0,
    }
    assert all(case["legacy"]["status"] == "not_run" for case in results["cases"])
    assert all(case["layered"]["status"] == "not_run" for case in results["cases"])
    assert all(case["comparison"]["decision"] == "blocked_live_not_executed" for case in results["cases"])


def test_live_shadow_intent_gates_are_independent_and_closed(tmp_path):
    paths = live_shadow.generate_blocked_artifacts(
        output_dir=tmp_path,
        reason="TEST_LIVE_NOT_CONFIGURED",
        default_full_local_passed=True,
    )
    intent_gates = json.loads(paths["intent_gates"].read_text(encoding="utf-8"))
    for intent in live_shadow.FIRST_BATCH_INTENTS:
        gate = intent_gates["intents"][intent]
        assert gate["passed"] is False
        assert gate["requested_samples"] > 0
        assert gate["executed_samples"] == 0
        assert "live_shadow_samples_not_executed" in gate["blockers"]
