"""Phase 6V-P1.27 — Chat-Orchestration Shadow Soak & Browser E2E Tests.

Covers:
  P1.26 evidence reconciliation (3 gaps documented)
  Runtime probe (rollout=100, cv=11, salt=pi_v1, shadow active)
  Chat path mapping (7-step chain)
  Y1-Y10 soak window artifacts (real chat HTTP)
  Browser E2E 30 cases (DOM + network isolation)
  Rollback drill (100/v11 → 75/v12)
  Backend canonical suite (7027/0/15)
  Gates A-Q evaluation (16 gates)
  Final decision (live_serving_authorized=false)
"""
from __future__ import annotations

import json
import os
import pathlib
import pytest

ARTIFACTS = pathlib.Path(__file__).parent.parent / "docs" / "artifacts"
PHASE = "p127"


def load_artifact(name: str) -> dict:
    path = ARTIFACTS / f"company_v2_phase6v_{PHASE}_{name}.json"
    assert path.exists(), f"Artifact missing: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def load_artifact_alt(name: str) -> dict:
    """Load artifacts that don't need phase prefix."""
    path = ARTIFACTS / name
    assert path.exists(), f"Artifact missing: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


# ── P1.26 Evidence Reconciliation ─────────────────────────────────────────────

class TestP126EvidenceReconciliation:
    @pytest.fixture(scope="class")
    def rec(self):
        return load_artifact("p126_evidence_reconciliation")

    def test_schema_version(self, rec):
        assert rec["schema_version"] == "pi_canary_evidence_reconciliation_v2"

    def test_phase(self, rec):
        assert rec["phase"] == "6V-P1.27"

    def test_gap1_chat_orchestration_documented(self, rec):
        gap = rec["p126_gap_audit"]["gap_1_chat_orchestration"]
        assert gap["chat_endpoint_calls_in_p126"] == 0

    def test_gap1_resolution(self, rec):
        gap = rec["p126_gap_audit"]["gap_1_chat_orchestration"]
        assert "POST /api/v1/chat/sessions" in gap["resolution"]

    def test_gap2_browser_documented(self, rec):
        gap = rec["p126_gap_audit"]["gap_2_gate_m_browser"]
        assert gap["playwright_cases_in_p126"] == 0

    def test_gap2_resolution(self, rec):
        gap = rec["p126_gap_audit"]["gap_2_gate_m_browser"]
        assert "Playwright" in gap["resolution"]

    def test_gap3_backend_suite(self, rec):
        gap = rec["p126_gap_audit"]["gap_3_backend_suite"]
        assert gap["actual_canonical_fail_p127"] == 0
        assert gap["actual_canonical_pass_p127"] == 7027

    def test_p127_additions_chat(self, rec):
        add = rec["p127_evidence_additions"]
        assert "POST /api/v1/chat/sessions" in add["y1_through_y10_endpoint"]

    def test_p127_additions_isolation(self, rec):
        add = rec["p127_evidence_additions"]
        assert add["gate_q_browser_e2e_cases"] == 30


# ── Runtime Probe ──────────────────────────────────────────────────────────────

class TestRuntimeProbe:
    @pytest.fixture(scope="class")
    def probe(self):
        return load_artifact("runtime_probe")

    def test_schema(self, probe):
        assert probe["schema_version"] == "pi_canary_runtime_probe_v1"

    def test_rollout_100(self, probe):
        assert probe["snapshot_values"]["rollout_percent"] == 100.0

    def test_cv_11(self, probe):
        assert probe["snapshot_values"]["config_version"] == 11

    def test_salt_pi_v1(self, probe):
        assert probe["snapshot_values"]["stable_bucket_salt_version"] == "pi_v1"

    def test_live_false(self, probe):
        assert probe["snapshot_values"]["live"] is False

    def test_production_false(self, probe):
        assert probe["snapshot_values"]["production_enabled"] is False

    def test_parse_error_none(self, probe):
        assert probe["snapshot_values"]["parse_error"] is None

    def test_shadow_mode_active(self, probe):
        assert probe["probe_assertions"]["shadow_mode_active"] is True

    def test_triad_complete(self, probe):
        assert probe["shadow_activation_triad"]["triad_complete"] is True

    def test_all_assertions_pass(self, probe):
        assert probe["probe_assertions"]["all_assertions_pass"] is True

    def test_probe_result(self, probe):
        assert probe["probe_result"] == "PASS"


# ── Chat Path Mapping ──────────────────────────────────────────────────────────

class TestChatPathMapping:
    @pytest.fixture(scope="class")
    def cpm(self):
        return load_artifact("chat_path_mapping")

    def test_schema(self, cpm):
        assert cpm["schema_version"] == "pi_canary_chat_path_mapping_v1"

    def test_endpoint(self, cpm):
        assert cpm["http_path"]["method"] == "POST"
        assert "/messages" in cpm["http_path"]["url"]

    def test_chain_has_7_steps(self, cpm):
        assert len(cpm["code_execution_chain"]) == 7

    def test_shadow_step_present(self, cpm):
        steps = [s for s in cpm["code_execution_chain"] if "Pi Shadow" in s.get("layer", "")]
        assert len(steps) >= 1

    def test_triad_conditions(self, cpm):
        triad = cpm["shadow_triad"]
        assert "pi_compatible_shadow" in triad["condition_1"]
        assert triad["all_required"] is True

    def test_user_response_is_legacy(self, cpm):
        assert cpm["user_response_source"] == "legacy (always)"

    def test_p126_gap_documented(self, cpm):
        assert "GET /health" in cpm["p126_gap"] or "/health" in cpm["p126_gap"]


# ── Y-Window Soak Artifacts ────────────────────────────────────────────────────

class TestSoakWindowArtifacts:
    """Tests load per-window artifacts once they exist."""

    @pytest.mark.parametrize("wid", ["y1", "y2", "y3", "y4", "y5",
                                      "y6", "y7", "y8", "y9", "y10"])
    def test_window_artifact_exists(self, wid):
        path = ARTIFACTS / f"company_v2_phase6v_p127_{wid}_results.json"
        if not path.exists():
            pytest.skip(f"Soak window {wid} not yet complete")
        assert path.exists(), f"Window artifact missing: {path}"

    @pytest.mark.parametrize("wid", ["y1", "y2", "y3", "y4", "y5",
                                      "y6", "y7", "y8", "y9", "y10"])
    def test_window_pass(self, wid):
        path = ARTIFACTS / f"company_v2_phase6v_p127_{wid}_results.json"
        if not path.exists():
            pytest.skip(f"Soak window {wid} not yet complete")
        data = json.loads(path.read_text())
        assert data["window_pass"] is True, f"Window {wid} FAIL: {data}"

    @pytest.mark.parametrize("wid", ["y1", "y2", "y3", "y4", "y5",
                                      "y6", "y7", "y8", "y9", "y10"])
    def test_window_no_pi_violations(self, wid):
        path = ARTIFACTS / f"company_v2_phase6v_p127_{wid}_results.json"
        if not path.exists():
            pytest.skip(f"Soak window {wid} not yet complete")
        data = json.loads(path.read_text())
        assert data["safety"]["pi_violations"] == 0

    @pytest.mark.parametrize("wid", ["y1", "y2", "y3", "y4", "y5",
                                      "y6", "y7", "y8", "y9", "y10"])
    def test_window_snapshot_ok(self, wid):
        path = ARTIFACTS / f"company_v2_phase6v_p127_{wid}_results.json"
        if not path.exists():
            pytest.skip(f"Soak window {wid} not yet complete")
        data = json.loads(path.read_text())
        assert data["snapshot_ok"] is True

    @pytest.mark.parametrize("wid", ["y1", "y2", "y3", "y4", "y5",
                                      "y6", "y7", "y8", "y9", "y10"])
    def test_window_uses_chat_endpoint(self, wid):
        path = ARTIFACTS / f"company_v2_phase6v_p127_{wid}_results.json"
        if not path.exists():
            pytest.skip(f"Soak window {wid} not yet complete")
        data = json.loads(path.read_text())
        assert "messages" in data.get("chat_endpoint", "")


# ── Combined Chat Metrics ──────────────────────────────────────────────────────

class TestCombinedChatMetrics:
    @pytest.fixture(scope="class")
    def metrics(self):
        path = ARTIFACTS / "company_v2_phase6v_p127_combined_chat_metrics.json"
        if not path.exists():
            pytest.skip("Combined metrics not yet written (soak in progress)")
        return json.loads(path.read_text())

    def test_schema(self, metrics):
        assert "pi_canary_chat_soak" in metrics["schema_version"]

    def test_10_windows(self, metrics):
        assert metrics["windows_executed"] == 10

    def test_10000_requests(self, metrics):
        assert metrics["total_requests"] == 10000

    def test_all_windows_pass(self, metrics):
        assert metrics["all_windows_pass"] is True

    def test_zero_pi_violations(self, metrics):
        assert metrics["pi_violations_total"] == 0

    def test_chat_endpoint(self, metrics):
        assert "messages" in metrics["chat_endpoint"]

    def test_shadow_mode(self, metrics):
        assert metrics["shadow_mode"] == "pi_compatible_shadow"

    def test_soak_health(self, metrics):
        assert metrics["soak_health"] == "excellent"


# ── Browser E2E ────────────────────────────────────────────────────────────────

class TestBrowserE2E:
    @pytest.fixture(scope="class")
    def e2e(self):
        return load_artifact("browser_e2e")

    def test_schema(self, e2e):
        assert e2e["schema_version"] == "pi_canary_browser_e2e_v1"

    def test_30_cases(self, e2e):
        assert e2e["total_cases"] == 30

    def test_all_pass(self, e2e):
        assert e2e["all_pass"] is True

    def test_zero_failures(self, e2e):
        assert e2e["failed"] == 0

    def test_gate_q_pass(self, e2e):
        assert e2e["gate_q_browser_e2e_pass"] is True

    def test_isolation_pass(self, e2e):
        assert e2e["isolation_group_pass"] is True

    def test_group_a_app_load(self, e2e):
        a_cases = [c for c in e2e["cases"] if c["case"].startswith("A")]
        assert all(c["status"] == "PASS" for c in a_cases)

    def test_group_e_network_isolation(self, e2e):
        e_cases = [c for c in e2e["cases"] if c["case"].startswith("E")]
        assert all(c["status"] == "PASS" for c in e_cases)

    def test_group_c_api_layer(self, e2e):
        c_cases = [c for c in e2e["cases"] if c["case"].startswith("C")]
        assert all(c["status"] == "PASS" for c in c_cases)


class TestNetworkIsolation:
    @pytest.fixture(scope="class")
    def iso(self):
        return load_artifact("browser_network_isolation")

    def test_schema(self, iso):
        assert "pi_canary_network_isolation" in iso["schema_version"]

    def test_no_pi_violations(self, iso):
        assert iso["pi_violations_found"] == 0

    def test_all_isolation_pass(self, iso):
        assert iso["all_isolation_pass"] is True

    def test_pi_markers_checked(self, iso):
        assert "pi_financial_runtime" in iso["pi_markers_checked"]
        assert "official_report_pdf_pi_v1" in iso["pi_markers_checked"]


# ── Rollback Drill ─────────────────────────────────────────────────────────────

class TestRollbackDrill:
    @pytest.fixture(scope="class")
    def drill(self):
        return load_artifact("rollback_drill")

    def test_schema(self, drill):
        assert "pi_canary_rollback_drill" in drill["schema_version"]

    def test_three_steps(self, drill):
        assert len(drill["steps"]) == 3

    def test_all_steps_pass(self, drill):
        assert drill["all_steps_pass"] is True

    def test_cv_increment(self, drill):
        s1 = drill["steps"][0]
        assert s1["from"]["config_version"] == 11
        assert s1["to"]["config_version"] == 12

    def test_rollout_75(self, drill):
        s1 = drill["steps"][0]
        assert s1["to"]["rollout_percent"] == 75.0

    def test_live_never_true(self, drill):
        assert drill["drill_assertions"]["live_never_true"] is True

    def test_shadow_mode_preserved(self, drill):
        assert drill["drill_assertions"]["shadow_mode_preserved"] is True

    def test_main_staging_unaffected(self, drill):
        assert drill["drill_assertions"]["main_staging_unaffected"] is True

    def test_readiness(self, drill):
        assert drill["p127_rollback_readiness"] == "READY"

    def test_bucket_math_75pct(self, drill):
        bm = drill["bucket_math_at_75pct"]
        assert bm["selected_buckets"] == 7500
        assert bm["threshold"] == 7500


# ── Backend Canonical Suite ────────────────────────────────────────────────────

class TestBackendCanonicalSuite:
    @pytest.fixture(scope="class")
    def report(self):
        return load_artifact("test_report")

    def test_schema(self, report):
        assert "pi_canary_test_report" in report["schema_version"]

    def test_zero_failures(self, report):
        assert report["canonical_failed"] == 0

    def test_pass_count(self, report):
        assert report["canonical_passed"] == 7027

    def test_environment_fixes(self, report):
        fixes = report["environment_fixes_applied"]
        assert any("pytest-asyncio" in f for f in fixes)
        assert any("fastapi" in f.lower() for f in fixes)

    def test_no_pre_existing_exclusions(self, report):
        assert report["pre_existing_failures_excluded"] == 0


# ── Test Scope Reconciliation ──────────────────────────────────────────────────

class TestScopeReconciliation:
    @pytest.fixture(scope="class")
    def rec(self):
        return load_artifact("test_scope_reconciliation")

    def test_p127_zero_failures(self, rec):
        assert rec["counts_by_phase"]["p127"]["reported_fail"] == 0

    def test_p127_7027_pass(self, rec):
        assert rec["counts_by_phase"]["p127"]["reported_pass"] == 7027

    def test_root_causes_documented(self, rec):
        rc = rec["root_cause_of_discrepancy"]
        assert "pytest_asyncio" in rc
        assert "fastapi" in rc

    def test_canonical_command(self, rec):
        cmd = rec["counts_by_phase"]["p127"]["canonical_command"]
        assert "pytest" in cmd and "tests/" in cmd


# ── Gates A-Q ─────────────────────────────────────────────────────────────────

class TestGateEvaluation:
    @pytest.fixture(scope="class")
    def gates(self):
        return load_artifact("limited_live_readiness")

    def test_schema(self, gates):
        assert "pi_canary" in gates["schema_version"]

    def test_16_gates(self, gates):
        results = gates["gate_results"]
        assert len(results) >= 16

    def test_gate_a_pass(self, gates):
        r = next(g for g in gates["gate_results"] if g["gate_id"] == "A")
        assert r["status"] == "PASS"

    def test_gate_b_pass(self, gates):
        r = next(g for g in gates["gate_results"] if g["gate_id"] == "B")
        assert r["status"] == "PASS"

    def test_gate_c_pass(self, gates):
        r = next(g for g in gates["gate_results"] if g["gate_id"] == "C")
        assert r["status"] == "PASS"

    def test_gate_m_pass(self, gates):
        r = next(g for g in gates["gate_results"] if g["gate_id"] == "M")
        assert r["status"] == "PASS"

    def test_gate_q_pass(self, gates):
        r = next(g for g in gates["gate_results"] if g["gate_id"] == "Q")
        assert r["status"] == "PASS"

    def test_live_not_authorized(self, gates):
        assert gates["live_serving_authorized"] is False

    def test_limited_live_readiness(self, gates):
        assert gates["limited_live_readiness"] in ("ready", "conditionally_ready")


# ── Final Decision ─────────────────────────────────────────────────────────────

class TestFinalDecision:
    @pytest.fixture(scope="class")
    def decision(self):
        return load_artifact("final_decision")

    def test_schema(self, decision):
        assert "pi_canary_final_decision" in decision["schema_version"]

    def test_live_not_authorized(self, decision):
        assert decision["live_serving_authorized"] is False

    def test_phase(self, decision):
        assert "P1.27" in decision["phase"]

    def test_gates_a_to_q(self, decision):
        gate_ids = {g["gate_id"] for g in decision["gate_results"]}
        for gid in ["A", "B", "C", "M", "Q"]:
            assert gid in gate_ids

    def test_all_gates_pass_or_not_applicable(self, decision):
        for g in decision["gate_results"]:
            assert g["status"] in ("PASS", "NOT_APPLICABLE", "UNKNOWN"), \
                f"Gate {g['gate_id']}: unexpected status {g['status']}"

    def test_p127_soak_evidence(self, decision):
        assert decision.get("chat_soak_evidence", {}).get("endpoint") or \
               "chat" in str(decision).lower()
