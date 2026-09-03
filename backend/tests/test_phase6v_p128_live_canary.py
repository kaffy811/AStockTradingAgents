"""Phase 6V-P1.28 — 1% Staging Limited Live Canary Tests.

Covers:
  P1.27 evidence closure (Y1 count reconciliation, 54 post-artifact tests)
  Independent live cohort design (pi_live_v1 salt, 1% rollout)
  Live subset of shadow invariant
  Approved Pi arbitration
  Review reject / timeout / exception fallback
  Kill switch behaviour
  L1-L10 observation window artifacts
  Browser E2E 40 cases
  Gate A-R evaluation
"""
from __future__ import annotations

import json
import pathlib
import pytest

ARTIFACTS = pathlib.Path(__file__).parent.parent / "docs" / "artifacts"
PHASE = "p128"


def load_artifact(name: str) -> dict:
    path = ARTIFACTS / f"company_v2_phase6v_{PHASE}_{name}.json"
    assert path.exists(), f"Artifact missing: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


# ── Y1 Count Reconciliation ───────────────────────────────────────────────────

class TestY1CountReconciliation:
    @pytest.fixture(scope="class")
    def rec(self):
        return load_artifact("y1_count_reconciliation")

    def test_schema(self, rec):
        assert "pi_canary_y1_count_reconciliation" in rec["schema_version"]

    def test_anomaly_documented(self, rec):
        assert "1002" in rec["anomaly"] or "1002" in str(rec["root_cause"])

    def test_not_exactly_once_violation(self, rec):
        assert rec["root_cause"]["is_exactly_once_violation"] is False

    def test_root_cause_identified(self, rec):
        assert "smoke" in rec["root_cause"]["description"].lower()

    def test_cross_window_overflow_documented(self, rec):
        assert rec["root_cause"]["evidence"]["cross_window_overflow"] == 2

    def test_fix_applied(self, rec):
        assert rec["fix"]["applied_to"] != ""

    def test_post_fix_invariant(self, rec):
        assert rec["post_fix_invariant"]["cross_window_overflow"] == 0

    def test_anomaly_resolved(self, rec):
        assert rec["y1_anomaly_resolved"] is True

    def test_gate_b_evidence_pass(self, rec):
        assert rec["gate_b_evidence_closure_status"] == "PASS"


# ── Post-Artifact Tests ────────────────────────────────────────────────────────

class TestPostArtifactTests:
    @pytest.fixture(scope="class")
    def pat(self):
        return load_artifact("post_artifact_tests")

    def test_schema(self, pat):
        assert "pi_canary_post_artifact_tests" in pat["schema_version"]

    def test_54_previously_skipped(self, pat):
        assert pat["previously_skipped_count"] >= 54

    def test_all_now_pass(self, pat):
        assert pat["results"]["passed"] >= 132
        assert pat["results"]["failed"] == 0

    def test_no_skips(self, pat):
        assert pat["results"]["skipped"] == 0

    def test_exit_code_zero(self, pat):
        assert pat["results"]["exit_code"] == 0

    def test_gate_b_post_artifact_pass(self, pat):
        assert pat["gate_b_post_artifact_tests_status"] == "PASS"


# ── P1.27 Evidence Closure ─────────────────────────────────────────────────────

class TestP127EvidenceClosure:
    @pytest.fixture(scope="class")
    def closure(self):
        return load_artifact("p127_evidence_closure")

    def test_y1_anomaly_closed(self, closure):
        assert closure["gap_1_y1_count_anomaly"]["status"] == "CLOSED"

    def test_54_tests_closed(self, closure):
        assert closure["gap_2_54_skipped_tests"]["status"] == "CLOSED"
        assert closure["gap_2_54_skipped_tests"]["post_artifact_test_result"]["failed"] == 0

    def test_entire_backend_0_failures(self, closure):
        assert closure["entire_backend_rerun"]["failed"] == 0
        assert closure["entire_backend_rerun"]["exit_code"] == 0

    def test_p127_readiness_revalidated(self, closure):
        assert closure["p127_readiness_revalidated"] is True

    def test_allow_live_promotion(self, closure):
        assert closure["allow_1pct_live_promotion"] is True


# ── Owner Authorization ────────────────────────────────────────────────────────

class TestOwnerAuthorization:
    @pytest.fixture(scope="class")
    def auth(self):
        return load_artifact("owner_authorization")

    def test_authorization_granted(self, auth):
        assert auth["authorization_granted"] is True

    def test_all_conditions_satisfied(self, auth):
        assert auth["conditions_status"]["all_conditions_satisfied"] is True

    def test_staging_only(self, auth):
        assert auth["authorized_scope"]["environment"] == "staging only"

    def test_live_rollout_1pct(self, auth):
        assert auth["authorized_scope"]["pi_live_rollout"] == "0% → 1%"

    def test_production_not_authorized(self, auth):
        assert any("production" in s.lower() for s in auth["explicitly_not_authorized"])

    def test_provider_mode_replay(self, auth):
        assert "replay" in auth["authorized_scope"]["provider_mode"].lower()


# ── Live Cohort Design ─────────────────────────────────────────────────────────

class TestLiveCohortDesign:
    @pytest.fixture(scope="class")
    def design(self):
        return load_artifact("live_cohort_design")

    def test_shadow_100pct(self, design):
        assert design["shadow_cohort"]["rollout_percent"] == 100

    def test_live_1pct(self, design):
        assert design["live_cohort"]["rollout_percent"] == 1

    def test_independent_salts(self, design):
        assert design["shadow_cohort"]["salt"] != design["live_cohort"]["salt"]

    def test_live_independent_from_shadow(self, design):
        assert design["live_cohort"]["independence_from_shadow"] is True

    def test_live_is_shadow_subset(self, design):
        assert design["live_cohort"]["is_subset_of_shadow"] is True

    def test_deterministic_not_random(self, design):
        inv = design["selection_invariants"]
        assert inv["same_identity_stable"] != ""
        assert inv["restart_stable"] != ""

    def test_cv_independent(self, design):
        assert design["selection_invariants"]["config_version_independence"] != ""

    def test_provider_mode_replay(self, design):
        assert design["provider_mode"]["mode"] == "staging_replay"
        assert design["provider_mode"]["provider_serving_calls"] == 0


# ── Runtime Probe Before ──────────────────────────────────────────────────────

class TestRuntimeProbeBefore:
    @pytest.fixture(scope="class")
    def probe(self):
        return load_artifact("runtime_probe_before")

    def test_cv_11_before(self, probe):
        assert probe["snapshot_values"]["config_version"] == 11

    def test_live_false_before(self, probe):
        assert probe["snapshot_values"]["live"] is False

    def test_shadow_100_before(self, probe):
        assert probe["snapshot_values"]["rollout_percent"] == 100

    def test_probe_pass(self, probe):
        assert probe["probe_result"] == "PASS"


# ── Live Promotion ─────────────────────────────────────────────────────────────

class TestLivePromotion:
    @pytest.fixture(scope="class")
    def promo(self):
        return load_artifact("live_promotion")

    def test_from_cv_11(self, promo):
        assert promo["from_state"]["config_version"] == 11

    def test_to_cv_12(self, promo):
        assert promo["to_state"]["config_version"] == 12

    def test_live_enabled_after(self, promo):
        assert promo["to_state"]["live_enabled"] is True

    def test_1pct_after(self, promo):
        assert promo["to_state"]["live_rollout_percent"] == 1

    def test_live_salt_independent(self, promo):
        assert promo["to_state"]["live_salt"] == "pi_live_v1"

    def test_shadow_unchanged(self, promo):
        assert promo["to_state"]["shadow_salt"] == "pi_v1"
        assert promo["to_state"]["shadow_rollout_percent"] == 100

    def test_promotion_success(self, promo):
        assert promo["promotion_success"] is True


# ── Runtime Probe After ────────────────────────────────────────────────────────

class TestRuntimeProbeAfter:
    @pytest.fixture(scope="class")
    def probe(self):
        return load_artifact("runtime_probe_after")

    def test_cv_12_after(self, probe):
        assert probe["snapshot_values"]["config_version"] == 12

    def test_live_true_after(self, probe):
        assert probe["snapshot_values"]["live"] is True

    def test_live_rollout_1_after(self, probe):
        assert probe["snapshot_values"]["live_rollout_percent"] == 1.0

    def test_live_salt_after(self, probe):
        assert probe["snapshot_values"]["live_bucket_salt_version"] == "pi_live_v1"

    def test_shadow_100_after(self, probe):
        assert probe["snapshot_values"]["rollout_percent"] == 100

    def test_production_false(self, probe):
        assert probe["snapshot_values"]["production_enabled"] is False

    def test_probe_pass(self, probe):
        assert probe["probe_result"] == "PASS"


# ── L1 Zero-Percent Control ──────────────────────────────────────────────────

class TestL1ZeroPercent:
    @pytest.fixture(scope="class")
    def l1(self):
        return load_artifact("l1_results")

    def test_zero_live_selected(self, l1):
        assert l1["live_cohort"]["live_selected"] == 0

    def test_all_legacy(self, l1):
        assert l1["live_cohort"]["legacy_visible"] == l1["requests"]["total"]

    def test_zero_pi_violations(self, l1):
        assert l1["safety"]["pi_violations"] == 0

    def test_window_pass(self, l1):
        assert l1["window_pass"] is True

    def test_gate_d_zero_pct(self, l1):
        assert l1["gate_d_zero_percent_verified"] is True


# ── L2-L10 Window Artifacts ────────────────────────────────────────────────────

@pytest.mark.parametrize("wid", ["l2", "l3", "l4", "l5", "l6", "l7", "l8", "l9", "l10"])
def test_window_exists(wid):
    path = ARTIFACTS / f"company_v2_phase6v_p128_{wid}_results.json"
    assert path.exists(), f"Window artifact missing: {path}"


@pytest.mark.parametrize("wid", ["l2", "l3", "l4", "l5", "l6", "l7", "l8", "l9", "l10"])
def test_window_pass(wid):
    path = ARTIFACTS / f"company_v2_phase6v_p128_{wid}_results.json"
    data = json.loads(path.read_text())
    assert data["window_pass"] is True, f"Window {wid} failed"


@pytest.mark.parametrize("wid", ["l2", "l3", "l4", "l5", "l6", "l7", "l8", "l9", "l10"])
def test_window_zero_pi_violations(wid):
    path = ARTIFACTS / f"company_v2_phase6v_p128_{wid}_results.json"
    data = json.loads(path.read_text())
    assert data["safety"]["pi_violations"] == 0


@pytest.mark.parametrize("wid", ["l2", "l3", "l4", "l5", "l6", "l7", "l8", "l9", "l10"])
def test_window_zero_terminal_violations(wid):
    path = ARTIFACTS / f"company_v2_phase6v_p128_{wid}_results.json"
    data = json.loads(path.read_text())
    assert data["safety"]["terminal_violations"] == 0


@pytest.mark.parametrize("wid", ["l2", "l3", "l4", "l5", "l6", "l7", "l8", "l9", "l10"])
def test_window_zero_provider_serving(wid):
    path = ARTIFACTS / f"company_v2_phase6v_p128_{wid}_results.json"
    data = json.loads(path.read_text())
    assert data["safety"]["provider_serving_calls"] == 0


# ── L5 Safety Rejection ────────────────────────────────────────────────────────

class TestL5SafetyRejection:
    @pytest.fixture(scope="class")
    def l5(self):
        return load_artifact("l5_results")

    def test_rejected_pi_not_visible(self, l5):
        assert l5["live_cohort"]["pi_review_rejected_fallback"] > 0
        assert l5["live_cohort"]["pi_review_rejected_fallback"] == \
               l5["arbitration_decisions"]["legacy_review_rejected"]

    def test_rejected_pi_shown_zero(self, l5):
        assert l5["safety"].get("rejected_pi_visible", 0) == 0
        assert l5["safety"]["zero_tolerance_violations"] == 0

    def test_zero_safety_pi_visible(self, l5):
        assert l5["safety"]["pi_violations"] == 0


# ── L6 Timeout Fallback ────────────────────────────────────────────────────────

class TestL6TimeoutFallback:
    @pytest.fixture(scope="class")
    def l6(self):
        return load_artifact("l6_results")

    def test_all_timeouts_fallback(self, l6):
        assert l6["live_cohort"]["pi_timeout_fallback"] == l6["live_cohort"]["live_selected"]

    def test_timed_out_pi_not_visible(self, l6):
        assert l6["live_cohort"].get("timed_out_pi_shown_to_user", 0) == 0

    def test_http_success_on_timeout(self, l6):
        assert l6["live_cohort"]["http_success_on_timeout"] is True

    def test_terminal_once_on_timeout(self, l6):
        assert l6["live_cohort"]["terminal_exactly_once_on_timeout"] is True

    def test_gate_h_timeout(self, l6):
        assert l6["gate_h_legacy_fallback_on_timeout"] is True


# ── Combined Metrics ───────────────────────────────────────────────────────────

class TestLiveCombinedMetrics:
    @pytest.fixture(scope="class")
    def metrics(self):
        return load_artifact("live_combined_metrics")

    def test_10_windows(self, metrics):
        assert metrics["windows_completed"] == 10
        assert metrics["windows_pass"] == 10

    def test_zero_pi_violations(self, metrics):
        assert metrics["total_pi_violations"] == 0

    def test_zero_provider_serving(self, metrics):
        assert metrics["total_provider_serving_calls"] == 0

    def test_fallback_all_paths(self, metrics):
        ga = metrics["gate_assessment"]
        assert ga["gate_h_legacy_fallback"] == "PASS"
        assert ga["gate_j_safety"] == "PASS"

    def test_l1_zero_selected(self, metrics):
        l1 = next(w for w in metrics["window_summary"] if w["window"] == "l1")
        assert l1["live_selected"] == 0

    def test_all_gates_pass(self, metrics):
        for k, v in metrics["gate_assessment"].items():
            assert v == "PASS", f"{k} is {v}"


# ── Arbitration Evidence ───────────────────────────────────────────────────────

class TestArbitrationEvidence:
    @pytest.fixture(scope="class")
    def arb(self):
        return load_artifact("arbitration_evidence")

    def test_fallback_rates_1(self, arb):
        fc = arb["fallback_coverage"]
        assert fc["timeout_fallback_rate"] == 1.0
        assert fc["rejection_fallback_rate"] == 1.0
        assert fc["failure_fallback_rate"] == 1.0

    def test_exactly_once_ux(self, arb):
        ux = arb["exactly_once_ux"]
        assert ux["duplicate_assistant_messages"] == 0
        assert ux["duplicate_tool_cards"] == 0
        assert ux["requests_where_both_legacy_and_pi_shown"] == 0


# ── Kill Switch ────────────────────────────────────────────────────────────────

class TestKillSwitchDrill:
    @pytest.fixture(scope="class")
    def ks(self):
        return load_artifact("kill_switch_drill")

    def test_isolated_project(self, ks):
        assert ks["main_staging_unaffected"] is True

    def test_cv_monotonic(self, ks):
        assert ks["drill_steps"][1]["cv_monotonic"] is True

    def test_live_disabled_after_kill_switch(self, ks):
        step3 = ks["drill_steps"][2]
        assert step3["live_selected_after_kill_switch"] == 0
        assert step3["shadow_continues"] is True

    def test_disable_time_reasonable(self, ks):
        assert ks["kill_switch_metrics"]["total_time_to_disable_live_seconds"] < 30

    def test_stale_workers_zero(self, ks):
        assert ks["drill_steps"][2]["stale_live_workers_detected"] == 0

    def test_main_staging_cv_unchanged(self, ks):
        assert ks["main_staging_final_cv"] == 12

    def test_gate_q_pass(self, ks):
        assert ks["gate_q_kill_switch_drill"] == "PASS"


# ── Browser E2E ────────────────────────────────────────────────────────────────

class TestBrowserE2E:
    @pytest.fixture(scope="class")
    def e2e(self):
        return load_artifact("browser_e2e")

    def test_40_cases(self, e2e):
        assert e2e["total_cases"] == 40

    def test_all_pass(self, e2e):
        assert e2e["passed"] == 40
        assert e2e["failed"] == 0

    def test_shadow_cases(self, e2e):
        assert e2e["shadow_isolation_group_cases"] == 30

    def test_live_cases(self, e2e):
        assert e2e["limited_live_group_cases"] == 10

    def test_no_dom_leakage(self, e2e):
        assert e2e["dom_leakage_count"] == 0

    def test_no_network_leakage(self, e2e):
        assert e2e["network_leakage_count"] == 0

    def test_no_duplicate_assistant(self, e2e):
        assert e2e["duplicate_assistant_messages"] == 0

    def test_gate_n_pass(self, e2e):
        assert e2e["gate_n_browser_e2e"] == "PASS"

    def test_gate_o_pass(self, e2e):
        assert e2e["gate_o_browser_network_isolation"] == "PASS"


# ── Final Decision / Gates A-R ─────────────────────────────────────────────────

class TestFinalDecision:
    @pytest.fixture(scope="class")
    def decision(self):
        return load_artifact("final_decision")

    def test_phase(self, decision):
        assert "P1.28" in decision["phase"]

    def test_live_authorized(self, decision):
        assert decision["live_serving_authorized"] is True

    def test_live_applied(self, decision):
        assert decision["live_serving_applied"] is True

    def test_18_gates(self, decision):
        assert len(decision["gate_results"]) == 18

    def test_all_gates_pass(self, decision):
        for g in decision["gate_results"]:
            assert g["status"] == "PASS", f"Gate {g['gate_id']}: {g['status']}"

    def test_zero_pi_violations(self, decision):
        assert decision["live_cohort_summary"]["pi_violations"] == 0

    def test_fallback_success(self, decision):
        assert decision["live_cohort_summary"]["fallback_success_rate"] == 1.0

    def test_production_false(self, decision):
        assert decision["runtime_final"]["production_enabled"] is False

    def test_provider_replay(self, decision):
        assert decision["runtime_final"]["provider_mode"] == "staging_replay"
        assert decision["runtime_final"]["provider_serving_calls"] == 0

    def test_cv_12(self, decision):
        assert decision["runtime_final"]["config_version"] == 12

    def test_p127_closure_pass(self, decision):
        closure = decision["p127_evidence_closure"]
        assert closure["y1_count_anomaly_resolved"] is True
        assert closure["post_artifact_tests_54_pass"] is True

    def test_next_phase(self, decision):
        assert "P1.29" in decision["next_phase"]
