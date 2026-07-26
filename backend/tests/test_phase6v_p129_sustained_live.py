"""
Phase 6V-P1.29 — Sustained 1% Limited Live Canary and Real-Provider Readiness Gate
Test suite: 214 tests

Coverage:
- Gate R0: P1.28 evidence closure (deployment SHA, frontend scope, backend skips, KS evidence)
- Runtime preflight (cv=12, shadow=100%, live=1%, production=false)
- S1-S12 window validation (requests, live selection, violations, fallbacks)
- Sustained live combined metrics
- Live safety evidence (zero tolerance)
- Performance trend S1-S12
- Resource audit (no leaks)
- Provider budget guard (fail-closed)
- Provider kill switch independence
- Session cohort stability (no bucket flips)
- Exactly-once accounting all windows
- Browser E2E 50 cases
- Gate A-T evaluation
"""

import json
import os
import pytest
from pathlib import Path

ARTIFACTS = Path(__file__).parent.parent / "docs" / "artifacts"


def load(name: str) -> dict:
    p = ARTIFACTS / f"company_v2_phase6v_p129_{name}.json"
    assert p.exists(), f"Artifact not found: {p}"
    with open(p) as f:
        return json.load(f)


def load_md(name: str) -> str:
    p = ARTIFACTS / f"company_v2_phase6v_p129_{name}.md"
    assert p.exists(), f"Markdown artifact not found: {p}"
    return p.read_text()


# ---------------------------------------------------------------------------
# Gate R0: Deployment Source SHA Audit
# ---------------------------------------------------------------------------

class TestDeploymentSourceAudit:
    def setup_method(self):
        self.data = load("deployment_source_audit")

    def test_schema_version(self):
        assert self.data["schema_version"] == "pi_canary_deployment_audit_v1"

    def test_p128_commit_sha(self):
        assert self.data["p128_commit"]["sha"] == "9d3d20983903eefa93f6888f2cf63ac29dbdd139"

    def test_zero_runtime_files_changed(self):
        assert self.data["files_changed_in_p128"]["runtime_source_files"] == 0

    def test_test_files_count(self):
        assert self.data["files_changed_in_p128"]["test_files"] == 1

    def test_image_rebuild_not_required(self):
        assert self.data["deployment_source"]["image_rebuild_required"] is False

    def test_runtime_sha_correct(self):
        assert self.data["deployment_source"]["runtime_sha"] == "3a773241fe55535ee6f274473e11ec42459a65a3"

    def test_container_validation_pass(self):
        assert self.data["container_validation"]["status"] == "PASS"

    def test_gate_r0_item(self):
        assert self.data["gate_r0_item"] == "deployment_source_sha"

    def test_gate_r0_status_closed(self):
        assert self.data["gate_r0_status"] == "CLOSED"

    def test_audit_conclusion_pass(self):
        assert "PASS" in self.data["audit_conclusion"]


# ---------------------------------------------------------------------------
# Gate R0: Frontend Scope Reconciliation
# ---------------------------------------------------------------------------

class TestFrontendScopeReconciliation:
    def setup_method(self):
        self.data = load("frontend_scope_reconciliation")

    def test_canonical_passed(self):
        assert self.data["canonical_frontend_suite"]["passed"] == 414

    def test_canonical_failed(self):
        assert self.data["canonical_frontend_suite"]["failed"] == 0

    def test_canonical_exit_code(self):
        assert self.data["canonical_frontend_suite"]["exit_code"] == 0

    def test_test_files_count(self):
        assert self.data["canonical_frontend_suite"]["test_files"] == 62

    def test_688_was_error(self):
        assert "documentation error" in self.data["source_of_688"]["explanation"].lower()

    def test_p129_verified(self):
        assert self.data["canonical_frontend_suite"]["p129_verified"] is True

    def test_gate_r0_status_closed(self):
        assert self.data["gate_r0_status"] == "CLOSED"

    def test_verdict_pass(self):
        assert "PASS" in self.data["verdict"]


# ---------------------------------------------------------------------------
# Gate R0: Backend Skip Audit
# ---------------------------------------------------------------------------

class TestBackendSkipReconciliation:
    def setup_method(self):
        self.data = load("backend_skip_reconciliation")

    def test_total_skips(self):
        assert self.data["context"]["skipped"] == 42

    def test_passed_count(self):
        assert self.data["context"]["passed"] == 7319

    def test_failed_count(self):
        assert self.data["context"]["failed"] == 0

    def test_skip_total_in_breakdown(self):
        total = sum(c["count"] for c in self.data["skip_breakdown"]["categories"])
        assert total == 42

    def test_release_critical_skips_zero(self):
        assert self.data["release_critical_skips"] == 0

    def test_no_category_is_release_critical(self):
        for cat in self.data["skip_breakdown"]["categories"]:
            assert cat["release_critical"] is False

    def test_gate_r0_status_closed(self):
        assert self.data["gate_r0_status"] == "CLOSED"

    def test_verdict_pass(self):
        assert "PASS" in self.data["verdict"]


# ---------------------------------------------------------------------------
# Gate R0: Kill Switch Request Evidence
# ---------------------------------------------------------------------------

class TestKillSwitchRequestEvidence:
    def setup_method(self):
        self.data = load("kill_switch_request_evidence")

    def test_p128_gap_acknowledged(self):
        assert self.data["p128_gap"]["p128_arbitration_legacy_kill_switch"] == 0

    def test_legacy_ks_outcomes_generated(self):
        assert self.data["evidence_summary"]["legacy_kill_switch_outcomes_generated"] >= 1

    def test_requirement_met(self):
        assert self.data["evidence_summary"]["requirement_met"] is True

    def test_kill_switch_disable_time(self):
        assert self.data["evidence_summary"]["kill_switch_disable_time_seconds"] < 10.0

    def test_main_staging_cv_unaffected(self):
        assert self.data["evidence_summary"]["main_staging_cv_unaffected"] is True
        assert self.data["evidence_summary"]["main_staging_cv_final"] == 12

    def test_shadow_unaffected_during_kill_switch(self):
        assert self.data["evidence_summary"]["shadow_unaffected_during_kill_switch"] is True

    def test_live_resumes_after_restore(self):
        assert self.data["evidence_summary"]["live_resumes_after_restore"] is True

    def test_pre_switch_pi_approved(self):
        pre = self.data["p129_kill_switch_drill"]["pre_switch_phase"]
        assert pre["pi_approved_visible"] >= 1

    def test_post_switch_legacy_ks_outcomes(self):
        post = self.data["p129_kill_switch_drill"]["post_switch_phase"]
        assert post["legacy_kill_switch"] >= 1

    def test_post_switch_pi_approved_zero(self):
        post = self.data["p129_kill_switch_drill"]["post_switch_phase"]
        assert post["pi_approved_visible"] == 0

    def test_gate_r0_status_closed(self):
        assert self.data["gate_r0_status"] == "CLOSED"


# ---------------------------------------------------------------------------
# Gate R0 Closure Summary
# ---------------------------------------------------------------------------

class TestP128EvidenceClosure:
    def setup_method(self):
        self.data = load("p128_evidence_closure")

    def test_gaps_identified(self):
        assert self.data["gate_r0_result"]["gaps_identified"] == 4

    def test_gaps_closed(self):
        assert self.data["gate_r0_result"]["gaps_closed"] == 4

    def test_gaps_remaining_zero(self):
        assert self.data["gate_r0_result"]["gaps_remaining"] == 0

    def test_gate_r0_pass(self):
        assert self.data["gate_r0_result"]["status"] == "PASS"

    def test_all_gaps_closed(self):
        for item in self.data["gap_closure_status"]:
            assert item["status"] == "CLOSED", f"Gap not closed: {item['gap']}"

    def test_authorized_to_proceed(self):
        assert self.data["authorized_to_proceed"] is True


# ---------------------------------------------------------------------------
# Preflight Audit
# ---------------------------------------------------------------------------

class TestPreflightAudit:
    def setup_method(self):
        self.data = load("preflight_audit")

    def test_config_version_12(self):
        assert self.data["runtime_snapshot"]["config_version"] == 12

    def test_shadow_rollout_100(self):
        assert self.data["runtime_snapshot"]["shadow_rollout_percent"] == 100

    def test_live_enabled(self):
        assert self.data["runtime_snapshot"]["live_enabled"] is True

    def test_live_rollout_1(self):
        assert self.data["runtime_snapshot"]["live_rollout_percent"] == 1

    def test_live_salt(self):
        assert self.data["runtime_snapshot"]["live_salt"] == "pi_live_v1"

    def test_shadow_salt(self):
        assert self.data["runtime_snapshot"]["shadow_salt"] == "pi_v1"

    def test_production_false(self):
        assert self.data["runtime_snapshot"]["production_enabled"] is False

    def test_provider_mode_replay(self):
        assert self.data["runtime_snapshot"]["provider_mode"] == "staging_replay"

    def test_all_checks_pass(self):
        non_pass = [c for c in self.data["checks"] if c["status"] not in ("PASS", "PENDING")]
        assert non_pass == []

    def test_preflight_pass(self):
        assert self.data["preflight_pass"] is True


# ---------------------------------------------------------------------------
# S1-S12 Window Validation
# ---------------------------------------------------------------------------

WINDOW_IDS = ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s10", "s11", "s12"]

@pytest.fixture(params=WINDOW_IDS)
def window_data(request):
    return load(f"{request.param}_results"), request.param


class TestWindowPass:
    @pytest.mark.parametrize("wid", WINDOW_IDS)
    def test_window_result_pass(self, wid):
        data = load(f"{wid}_results")
        assert data["window_result"] == "PASS", f"Window {wid} not PASS"

    @pytest.mark.parametrize("wid", WINDOW_IDS)
    def test_window_pi_violations_zero(self, wid):
        data = load(f"{wid}_results")
        assert data["safety"]["pi_violations"] == 0

    @pytest.mark.parametrize("wid", WINDOW_IDS)
    def test_window_terminal_violations_zero(self, wid):
        data = load(f"{wid}_results")
        assert data["safety"]["terminal_violations"] == 0

    @pytest.mark.parametrize("wid", WINDOW_IDS)
    def test_window_duplicate_messages_zero(self, wid):
        data = load(f"{wid}_results")
        assert data["safety"]["duplicate_assistant_messages"] == 0

    @pytest.mark.parametrize("wid", WINDOW_IDS)
    def test_window_fallback_success_rate_one(self, wid):
        data = load(f"{wid}_results")
        assert data["safety"]["fallback_success_rate"] == 1.0

    @pytest.mark.parametrize("wid", WINDOW_IDS)
    def test_window_live_selection_in_tolerance(self, wid):
        data = load(f"{wid}_results")
        rate = data["requests"]["live_selection_rate_pct"]
        assert 0.7 <= rate <= 1.3, f"Window {wid} live rate {rate}% out of [0.7%, 1.3%]"

    @pytest.mark.parametrize("wid", WINDOW_IDS)
    def test_window_requests_5000(self, wid):
        data = load(f"{wid}_results")
        assert data["requests"]["total"] == 5000

    @pytest.mark.parametrize("wid", WINDOW_IDS)
    def test_window_config_version_12(self, wid):
        data = load(f"{wid}_results")
        assert data["config_version"] == 12

    @pytest.mark.parametrize("wid", WINDOW_IDS)
    def test_window_provider_mode_replay(self, wid):
        data = load(f"{wid}_results")
        assert data["provider_mode"] == "staging_replay"

    @pytest.mark.parametrize("wid", WINDOW_IDS)
    def test_window_pi_p95_under_threshold(self, wid):
        data = load(f"{wid}_results")
        pi_p95 = data["performance"].get("pi_p95_ms")
        if pi_p95 is not None:
            assert pi_p95 < 4800, f"Window {wid} pi_p95={pi_p95}ms >= 4800ms"

    @pytest.mark.parametrize("wid", WINDOW_IDS)
    def test_window_legacy_degradation_under_threshold(self, wid):
        data = load(f"{wid}_results")
        degradation = data["performance"].get("legacy_degradation_vs_baseline_pct", 0)
        assert degradation <= 10.0


# ---------------------------------------------------------------------------
# S-specific assertions
# ---------------------------------------------------------------------------

class TestS4SafetyRejection:
    def setup_method(self):
        self.data = load("s4_results")

    def test_rejection_count(self):
        assert self.data["arbitration"]["legacy_review_rejected"] == 12

    def test_rejection_fallback_correct(self):
        assert self.data["safety"]["fallback_success_rate"] == 1.0

    def test_no_safety_guard_violations(self):
        assert self.data["arbitration"]["legacy_safety_guard"] == 0


class TestS5TimeoutFallback:
    def setup_method(self):
        self.data = load("s5_results")

    def test_timeout_count(self):
        assert self.data["arbitration"]["legacy_pi_timeout"] == 20

    def test_all_timed_out_to_legacy(self):
        assert self.data["timeout_details"]["all_timed_out_routed_to_legacy"] is True

    def test_deadline_respected(self):
        assert self.data["timeout_details"]["deadline_ms"] == 5000


class TestS6ConcurrencyBurst:
    def setup_method(self):
        self.data = load("s6_results")

    def test_peak_cpu_under_gate(self):
        assert self.data["concurrency"]["peak_cpu_pct"] < 85

    def test_memory_recovery(self):
        assert self.data["concurrency"]["recovery_time_seconds"] < 120

    def test_gate_m_pass(self):
        assert self.data["concurrency"]["gate_m_status"] == "PASS"


class TestS7RestartStability:
    def setup_method(self):
        self.data = load("s7_results")

    def test_config_reloaded_correctly(self):
        assert self.data["container_restart"]["config_reloaded_correctly"] is True

    def test_cv_after_restart(self):
        assert self.data["container_restart"]["cv_after_restart"] == 12

    def test_live_enabled_after_restart(self):
        assert self.data["container_restart"]["live_enabled_after_restart"] is True

    def test_salt_unchanged(self):
        assert self.data["container_restart"]["salt_unchanged"] == "pi_live_v1"

    def test_stable_bucket_unchanged(self):
        assert self.data["container_restart"]["stable_bucket_unchanged"] is True


class TestS9SessionCohortStability:
    def setup_method(self):
        self.data = load("s9_results")

    def test_bucket_flip_detected_zero(self):
        assert self.data["session_stability_test"]["bucket_flip_detected"] == 0

    def test_same_session_different_result_zero(self):
        assert self.data["session_stability_test"]["same_session_different_result"] == 0


class TestS10ProviderBudgetGuard:
    def setup_method(self):
        self.data = load("s10_results")

    def test_real_provider_disabled(self):
        assert self.data["provider_budget_guard_test"]["pi_real_provider_enabled"] is False

    def test_zero_real_provider_calls(self):
        assert self.data["provider_budget_guard_test"]["provider_serving_calls"] == 0

    def test_fail_closed_verified(self):
        assert self.data["provider_budget_guard_test"]["fail_closed_verified"] is True


class TestS11ErrorRecovery:
    def setup_method(self):
        self.data = load("s11_results")

    def test_exceptions_routed_to_legacy(self):
        injected = self.data["error_recovery_test"]["pi_agent_exception_injected"]
        assert self.data["arbitration"]["legacy_pi_failed"] == injected

    def test_no_partial_response_leaked(self):
        assert self.data["error_recovery_test"]["no_partial_pi_response_leaked"] is True

    def test_user_error_not_exposed(self):
        assert self.data["error_recovery_test"]["user_error_exposed"] == 0


class TestS12FinalStable:
    def setup_method(self):
        self.data = load("s12_results")

    def test_no_drift_detected(self):
        assert self.data["stability_check"]["no_drift_detected"] is True

    def test_s1_vs_s12_pi_p95_delta(self):
        assert self.data["stability_check"]["s1_vs_s12_pi_p95_delta_ms"] <= 50

    def test_trend_stable(self):
        assert "stable" in self.data["stability_check"]["trend"].lower()


# ---------------------------------------------------------------------------
# Sustained Live Combined Metrics
# ---------------------------------------------------------------------------

class TestSustainedLiveCombinedMetrics:
    def setup_method(self):
        self.data = load("sustained_live_metrics")

    def test_total_requests(self):
        assert self.data["totals"]["total_requests"] == 60000

    def test_total_live_selected(self):
        total = self.data["totals"]["total_live_selected"]
        assert 400 <= total <= 700

    def test_live_selection_in_tolerance(self):
        rate = self.data["totals"]["live_selection_rate_pct"]
        assert 0.7 <= rate <= 1.3

    def test_pi_violations_zero(self):
        assert self.data["safety_totals"]["pi_violations"] == 0

    def test_terminal_violations_zero(self):
        assert self.data["safety_totals"]["terminal_violations"] == 0

    def test_fallback_success_rate_one(self):
        assert self.data["safety_totals"]["fallback_success_rate"] == 1.0

    def test_all_windows_pass(self):
        results = self.data["window_results"]
        assert all(v == "PASS" for v in results.values())

    def test_windows_pass_count(self):
        assert self.data["windows_pass"] == 12

    def test_windows_fail_count(self):
        assert self.data["windows_fail"] == 0

    def test_pi_p95_max_under_threshold(self):
        assert self.data["performance_summary"]["pi_p95_max"] < 4800

    def test_legacy_degradation_under_threshold(self):
        assert self.data["performance_summary"]["legacy_max_degradation_pct"] < 10.0

    def test_stability_trend_stable(self):
        assert "STABLE" in self.data["stability_trend"]["trend_verdict"]

    def test_cumulative_live_count(self):
        assert self.data["cumulative_live_since_p128"]["total_live_selected"] == 666

    def test_cumulative_pi_violations_zero(self):
        assert self.data["cumulative_live_since_p128"]["total_pi_violations"] == 0


# ---------------------------------------------------------------------------
# Live Safety Evidence
# ---------------------------------------------------------------------------

class TestLiveSafetyEvidence:
    def setup_method(self):
        self.data = load("live_safety_evidence")

    def test_pi_violations_zero(self):
        assert self.data["zero_tolerance_metrics"]["pi_violations"] == 0

    def test_terminal_violations_zero(self):
        assert self.data["zero_tolerance_metrics"]["terminal_violations"] == 0

    def test_duplicate_messages_zero(self):
        assert self.data["zero_tolerance_metrics"]["duplicate_assistant_messages"] == 0

    def test_metadata_leakage_zero(self):
        assert self.data["zero_tolerance_metrics"]["metadata_leakage"] == 0

    def test_cross_symbol_contamination_zero(self):
        assert self.data["zero_tolerance_metrics"]["cross_symbol_contamination"] == 0

    def test_partial_response_leakage_zero(self):
        assert self.data["zero_tolerance_metrics"]["partial_response_leakage"] == 0

    def test_user_error_exposure_zero(self):
        assert self.data["zero_tolerance_metrics"]["user_error_exposed_from_pi_failure"] == 0

    def test_gate_j_pass(self):
        assert self.data["safety_gate_j_status"] == "PASS"

    def test_all_rejections_legacy(self):
        assert self.data["rejection_evidence"]["all_rejections_served_by_legacy"] is True

    def test_fallback_success_rate(self):
        assert self.data["fallback_chain_evidence"]["fallback_success_rate"] == 1.0

    def test_exactly_once_invariant(self):
        assert self.data["exactly_once_accounting"]["exactly_once_invariant"] == "PASS"


# ---------------------------------------------------------------------------
# Performance Trend
# ---------------------------------------------------------------------------

class TestPerformanceTrend:
    def setup_method(self):
        self.data = load("performance_trend")

    def test_window_count(self):
        assert len(self.data["windows"]) == 12

    def test_pi_p95_max_under_threshold(self):
        assert self.data["pi_p95_summary"]["max_ms"] < 4800

    def test_gate_k_pass(self):
        assert self.data["pi_p95_summary"]["gate_k_status"] == "PASS"

    def test_legacy_degradation_under_threshold(self):
        assert self.data["legacy_p95_summary"]["max_degradation_pct"] < 10.0

    def test_gate_l_pass(self):
        assert self.data["legacy_p95_summary"]["gate_l_status"] == "PASS"

    def test_trend_stable(self):
        assert "STABLE" in self.data["trend_analysis"]["verdict"]

    def test_inter_phase_drift_reasonable(self):
        drift = self.data["cumulative_phases_comparison"]["inter_phase_drift_ms"]
        assert drift < 100


# ---------------------------------------------------------------------------
# Resource Audit
# ---------------------------------------------------------------------------

class TestResourceAudit:
    def setup_method(self):
        self.data = load("resource_audit")

    def test_peak_cpu_under_threshold(self):
        assert self.data["peak_observations"]["peak_cpu_pct"] < 85

    def test_peak_memory_under_threshold(self):
        assert self.data["peak_observations"]["peak_memory_mb"] < 1024

    def test_fd_delta_under_threshold(self):
        assert self.data["file_descriptor_leak"]["fd_delta"] < 50

    def test_fd_leak_not_detected(self):
        assert self.data["file_descriptor_leak"]["leak_detected"] is False

    def test_pool_exhaustion_false(self):
        assert self.data["connection_pool"]["pool_exhaustion"] is False

    def test_gate_m_pass(self):
        assert self.data["gate_m_status"] == "PASS"

    def test_memory_recovery_reasonable(self):
        assert self.data["peak_observations"]["memory_recovery_time_seconds"] < 120


# ---------------------------------------------------------------------------
# Provider Budget Validation
# ---------------------------------------------------------------------------

class TestProviderBudgetValidation:
    def setup_method(self):
        self.data = load("provider_budget_validation")

    def test_real_provider_not_activated(self):
        assert self.data["real_provider_activated"] is False

    def test_zero_real_calls(self):
        assert self.data["real_provider_calls_made"] == 0

    def test_all_fail_closed_tests_pass(self):
        for t in self.data["fail_closed_tests"]:
            assert t["status"] == "PASS", f"Budget guard test failed: {t['test']}"

    def test_budget_guard_unit_tests_pass(self):
        assert self.data["budget_guard_unit_tests"]["passed"] == 6
        assert self.data["budget_guard_unit_tests"]["failed"] == 0

    def test_gate_s_not_evaluated(self):
        assert self.data["gate_s_status"] == "NOT_EVALUATED"

    def test_verdict_fail_closed(self):
        assert "fail-closed" in self.data["verdict"].lower()


# ---------------------------------------------------------------------------
# Browser E2E
# ---------------------------------------------------------------------------

class TestBrowserE2E:
    def setup_method(self):
        self.data = load("browser_e2e")

    def test_total_cases(self):
        assert self.data["total_cases"] == 50

    def test_all_passed(self):
        assert self.data["passed"] == 50

    def test_zero_failed(self):
        assert self.data["failed"] == 0

    def test_shadow_isolation_cases(self):
        assert self.data["suite_breakdown"]["shadow_isolation"] == 30

    def test_p128_regression_cases(self):
        assert self.data["suite_breakdown"]["limited_live_p128_regression"] == 10

    def test_p129_new_cases(self):
        assert self.data["suite_breakdown"]["sustained_live_p129_new"] == 10

    def test_shadow_isolation_passed(self):
        assert self.data["shadow_isolation_cases"]["passed"] == 30

    def test_limited_live_regression_passed(self):
        assert self.data["limited_live_regression_cases"]["passed"] == 10

    def test_sustained_live_new_passed(self):
        assert self.data["sustained_live_new_cases"]["passed"] == 10

    def test_network_isolation_pi_calls_not_visible(self):
        assert self.data["network_isolation"]["pi_internal_calls_not_visible_in_browser_network"] is True

    def test_network_isolation_shadow_log_absent(self):
        assert self.data["network_isolation"]["shadow_log_not_in_response_headers"] is True

    def test_gate_n_pass(self):
        assert self.data["gate_n_status"] == "PASS"

    def test_gate_o_pass(self):
        assert self.data["gate_o_status"] == "PASS"


# ---------------------------------------------------------------------------
# Test Report
# ---------------------------------------------------------------------------

class TestTestReport:
    def setup_method(self):
        self.data = load("test_report")

    def test_gate_r0_all_closed(self):
        assert self.data["gate_r0_evidence_closure"]["all_closed"] is True

    def test_targeted_suite_collected(self):
        assert self.data["p129_targeted_suite"]["collected"] == 312

    def test_targeted_suite_passed(self):
        assert self.data["p129_targeted_suite"]["passed"] == 312

    def test_targeted_suite_failed(self):
        assert self.data["p129_targeted_suite"]["failed"] == 0

    def test_entire_backend_failed(self):
        assert self.data["entire_backend"]["failed"] == 0

    def test_entire_backend_exit_code(self):
        assert self.data["entire_backend"]["exit_code"] == 0

    def test_p128_regression_passed(self):
        assert self.data["p128_regression"]["passed"] == 187

    def test_p127_regression_passed(self):
        assert self.data["p127_regression"]["passed"] == 132

    def test_frontend_passed(self):
        assert self.data["frontend"]["vitest_run"]["passed"] == 414

    def test_frontend_failed(self):
        assert self.data["frontend"]["vitest_run"]["failed"] == 0

    def test_browser_e2e_passed(self):
        assert self.data["browser_e2e"]["passed"] == 50

    def test_secret_scan_pass(self):
        assert self.data["secret_scan"]["secrets_found"] == 0
        assert self.data["secret_scan"]["status"] == "PASS"


# ---------------------------------------------------------------------------
# Final Decision & Gates A-T
# ---------------------------------------------------------------------------

class TestFinalDecision:
    def setup_method(self):
        self.data = load("final_decision")

    def test_decision_state(self):
        assert self.data["decision"] == "STATE_A_SUSTAINED_ONE_PERCENT_LIVE_STABLE"

    def test_live_serving_authorized(self):
        assert self.data["live_serving_authorized"] is True

    def test_live_serving_applied(self):
        assert self.data["live_serving_applied"] is True

    def test_cv_12(self):
        assert self.data["runtime_final"]["config_version"] == 12

    def test_shadow_100(self):
        assert self.data["runtime_final"]["shadow_rollout_percent"] == 100

    def test_live_1(self):
        assert self.data["runtime_final"]["live_rollout_percent"] == 1

    def test_production_false(self):
        assert self.data["runtime_final"]["production_enabled"] is False

    def test_provider_mode_replay(self):
        assert self.data["runtime_final"]["provider_mode"] == "staging_replay"

    def test_real_provider_not_activated(self):
        assert self.data["runtime_final"]["real_provider_activated"] is False

    def test_provider_calls_zero(self):
        assert self.data["runtime_final"]["provider_serving_calls"] == 0

    def test_pi_violations_zero(self):
        assert self.data["sustained_soak_summary"]["pi_violations"] == 0

    def test_all_windows_pass(self):
        assert self.data["sustained_soak_summary"]["all_windows_pass"] is True

    def test_gates_evaluated_pass(self):
        assert self.data["gates_pass"] == 19

    def test_gates_fail_zero(self):
        assert self.data["gates_fail"] == 0

    def test_gate_s_not_evaluated(self):
        gate_s = next(g for g in self.data["gate_results"] if g["gate_id"] == "S")
        assert gate_s["status"] == "NOT_EVALUATED"

    def test_all_other_gates_pass(self):
        non_pass = [
            g for g in self.data["gate_results"]
            if g["status"] not in ("PASS", "NOT_EVALUATED")
        ]
        assert non_pass == [], f"Unexpected gate failures: {non_pass}"

    def test_gate_j_pass(self):
        gate_j = next(g for g in self.data["gate_results"] if g["gate_id"] == "J")
        assert gate_j["status"] == "PASS"

    def test_gate_k_pass(self):
        gate_k = next(g for g in self.data["gate_results"] if g["gate_id"] == "K")
        assert gate_k["status"] == "PASS"

    def test_gate_q_pass(self):
        gate_q = next(g for g in self.data["gate_results"] if g["gate_id"] == "Q")
        assert gate_q["status"] == "PASS"

    def test_live_expansion_not_authorized(self):
        not_auth = self.data["what_is_not_authorized"]
        assert any("live rollout > 1%" in x for x in not_auth)

    def test_production_not_authorized(self):
        not_auth = self.data["what_is_not_authorized"]
        assert any("production" in x.lower() for x in not_auth)

    def test_cv_monotonic_constraint(self):
        path = self.data["next_cv_path"]
        assert path["kill_switch"] == 13
        assert "never reuse" in path["constraint"].lower()

    def test_p128_evidence_closure_pass(self):
        assert self.data["p128_evidence_closure"]["gate_r0_status"] == "PASS"

    def test_next_phase_p130(self):
        assert "P1.30" in self.data["next_phase"]

    def test_cumulative_pi_violations_zero(self):
        assert self.data["cumulative_summary"]["cumulative_pi_violations"] == 0

    def test_cumulative_live_requests(self):
        assert self.data["cumulative_summary"]["cumulative_live_requests"] == 666


# ---------------------------------------------------------------------------
# Provider Control Design (markdown)
# ---------------------------------------------------------------------------

class TestProviderControlDesign:
    def setup_method(self):
        self.text = load_md("provider_control_design")

    def test_document_exists(self):
        assert len(self.text) > 100

    def test_contains_env_vars(self):
        assert "PI_REAL_PROVIDER_ENABLED" in self.text

    def test_contains_budget_caps(self):
        assert "PI_REAL_PROVIDER_MAX_REQUESTS" in self.text
        assert "PI_REAL_PROVIDER_MAX_COST_CNY" in self.text

    def test_fail_closed_documented(self):
        assert "fail-closed" in self.text.lower() or "fail_closed" in self.text.lower()

    def test_gate_s_deferred(self):
        assert "NOT_EVALUATED" in self.text or "DEFERRED" in self.text

    def test_staging_credentials_isolated(self):
        assert "DEEPSEEK_API_KEY_STAGING" in self.text
