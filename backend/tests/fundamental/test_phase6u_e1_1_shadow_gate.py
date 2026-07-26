from __future__ import annotations

import json

from scripts import financial_agent_shadow_gate as gate


def test_shadow_gate_artifact_schema(tmp_path):
    results = gate._run_contract_shadow()
    runtime_gate = gate._gate_payload(results)
    assert results["schema_version"] == "financial_agent_shadow.v1"
    assert results["sample_count"] >= 20
    first = results["runs"][0]
    for key in ["trace_id", "intent", "entities", "legacy", "layered", "comparison"]:
        assert key in first
    assert "prompt" not in json.dumps(results).lower()
    assert "jwt" not in json.dumps(results).lower()
    assert "database_url" not in json.dumps(results).lower()
    assert runtime_gate["layered_enabled"] is False
    assert runtime_gate["authorized_intents"] == []
    assert runtime_gate["decision"] == "do_not_enable_layered_v1"


def test_shadow_gate_writes_all_artifacts(tmp_path):
    results = gate._run_contract_shadow()
    runtime_gate = gate._gate_payload(results)
    summary = gate._summary_markdown(results, runtime_gate)
    assert "Financial Agent Shadow Summary" in summary
    assert "real_legacy_vs_layered_shadow_not_run" in summary
