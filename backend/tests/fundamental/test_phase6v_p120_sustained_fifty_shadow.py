"""
Phase 6V-P1.20: Sustained 50% Shadow Soak & 75% Readiness Evaluation Test Suite

Covers:
- P1.19 preflight audit (SHA + artifacts intact, no drift)
- 8 observation windows S1-S8 (parametrized): >=800 selected, safety, performance, resources
- Combined metrics: >=5100 selected (sustained), 100 symbols, 14 styles, >=300 multi-turn, 0 duplicates
- Bucket stability: deterministic algorithm, restart/worker/cross-window/P1.19 cohort consistent
- Performance trend: three-way P1.18/P1.19/P1.20 comparison, no monotonic increase, S8 recovery
- Resource audit: no drift, S8 recovers to S1 baseline, S5 burst temporary, no leaks
- Safety gate: correctness=1.0, zero_tolerance=0, cumulative updated (P1.8-P1.20 = 24299)
- Browser regression: 16/16 pass (expanded from P1.19's 14)
- Dry-run isolation: business_writes=0, serving=0, candidates not applied, attribution isolated
- 75% readiness: 10/10 gates PASS, ready_for_decision=true, NOT authorized, NOT applied
- Final decision: actual_rollout=50, actual_config=7, no rollback, 75% NOT authorized, decision pending

CRITICAL SAFETY INVARIANTS (verified throughout):
- live=false, production_enabled=false
- recommended_for_live_serving=false, recommended_for_production=false
- provider_calls_serving=0
- seventy_five_percent_authorized=false, seventy_five_percent_applied=false
- actual_rollout_percent=50, actual_config_version=7
"""

import json
import os
import pytest

ARTIFACTS_DIR = os.path.join(
    os.path.dirname(__file__),
    "../../docs/artifacts"
)


def load(name):
    path = os.path.join(ARTIFACTS_DIR, name)
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# TestPreflightAudit — 8 tests
# ---------------------------------------------------------------------------

class TestPreflightAudit:

    @pytest.fixture(scope="class")
    def audit(self):
        return load("company_v2_phase6v_p120_preflight_audit.json")

    def test_p119_sha_confirmed(self, audit):
        assert audit["p119_final_sha_confirmed"] == "bbaa7e568a81316edd467d7e7dfd8837a368f2ac"

    def test_p119_artifacts_complete(self, audit):
        assert audit["p119_artifacts_complete"] is True

    def test_p119_artifacts_count_at_least_16(self, audit):
        assert audit["p119_artifacts_found"] >= 16

    def test_p119_commits_verified(self, audit):
        commits = audit["p119_commits_verified"]
        assert isinstance(commits, list)
        assert len(commits) >= 4

    def test_current_rollout_is_50(self, audit):
        assert audit["current_rollout_percent"] == 50

    def test_current_config_version_is_7(self, audit):
        assert audit["current_config_version"] == 7

    def test_no_configuration_drift(self, audit):
        assert audit["configuration_drift_detected"] is False

    def test_soak_cleared(self, audit):
        assert audit["soak_cleared"] is True


# ---------------------------------------------------------------------------
# TestObservationWindows — parametrized over S1-S8
# 12 test methods × 8 windows = 96 parametrized tests
# ---------------------------------------------------------------------------

WINDOWS = ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8"]


class TestObservationWindows:

    @pytest.fixture(params=WINDOWS, scope="class")
    def window_data(self, request):
        wname = request.param
        data = load(f"company_v2_phase6v_p120_{wname}_results.json")
        return data, wname.upper()

    def test_selected_gte_800(self, window_data):
        data, name = window_data
        assert data["result"]["selected_requests"] >= 800, f"{name}: selected_requests < 800"

    def test_config_version_7(self, window_data):
        data, name = window_data
        assert data["config_version"] == 7, f"{name}: config_version != 7"

    def test_rollout_percent_50(self, window_data):
        data, name = window_data
        assert data["rollout_percent"] == 50, f"{name}: rollout_percent != 50"

    def test_no_duplicates(self, window_data):
        data, name = window_data
        assert data["result"]["duplicates"] == 0, f"{name}: duplicates != 0"

    def test_safety_correctness_1(self, window_data):
        data, name = window_data
        assert data["safety"]["safety_correctness_rate"] == 1.0, f"{name}: safety_correctness != 1.0"

    def test_zero_tolerance_violations_0(self, window_data):
        data, name = window_data
        assert data["safety"]["zero_tolerance_violations"] == 0, f"{name}: zero_tolerance_violations != 0"

    def test_pi_p95_below_review_threshold(self, window_data):
        data, name = window_data
        assert data["result"]["pi_p95_ms"] < 4800, f"{name}: pi_p95 >= 4800ms (review threshold)"

    def test_tool_p95_below_limit(self, window_data):
        data, name = window_data
        assert data["result"]["tool_p95_ms"] < 3800, f"{name}: tool_p95 >= 3800ms"

    def test_no_pi_user_visible_leakage(self, window_data):
        data, name = window_data
        assert data["result"]["Pi_user_visible_leakage"] == 0, f"{name}: Pi_user_visible_leakage != 0"

    def test_terminal_exactly_once(self, window_data):
        data, name = window_data
        assert data["result"]["terminal_exactly_once"] is True, f"{name}: terminal_exactly_once != True"

    def test_provider_serving_zero(self, window_data):
        data, name = window_data
        assert data["provider_serving_calls"] == 0, f"{name}: provider_serving_calls != 0"

    def test_legacy_stalls_zero(self, window_data):
        data, name = window_data
        assert data["result"]["legacy_stalls"] == 0, f"{name}: legacy_stalls != 0"


# ---------------------------------------------------------------------------
# TestCombinedMetrics — 8 tests
# ---------------------------------------------------------------------------

class TestCombinedMetrics:

    @pytest.fixture(scope="class")
    def combined(self):
        return load("company_v2_phase6v_p120_combined_metrics.json")

    def test_total_selected_gte_5100_sustained(self, combined):
        assert combined["cumulative"]["total_selected"] >= 5100

    def test_unique_request_ids_equals_selected(self, combined):
        c = combined["cumulative"]
        assert c["unique_request_ids"] == c["total_selected"]

    def test_duplicates_zero(self, combined):
        assert combined["cumulative"]["duplicates"] == 0

    def test_unique_symbols_100(self, combined):
        assert combined["cumulative"]["unique_symbols"] == 100

    def test_query_styles_14(self, combined):
        assert combined["cumulative"]["query_styles"] == 14

    def test_multi_turn_gte_300(self, combined):
        assert combined["cumulative"]["multi_turn_count"] >= 300

    def test_all_gates_passed(self, combined):
        assert combined["combined_gate_passed"] is True

    def test_selection_rate_near_50pct(self, combined):
        rate = combined["cumulative"]["selection_rate_pct"]
        assert 48.0 <= rate <= 52.0, f"selection_rate_pct={rate} outside 48-52% window"


# ---------------------------------------------------------------------------
# TestBucketStability — 6 tests
# ---------------------------------------------------------------------------

class TestBucketStability:

    @pytest.fixture(scope="class")
    def bucket(self):
        return load("company_v2_phase6v_p120_bucket_stability.json")

    def test_algorithm_uses_sha256(self, bucket):
        assert "sha256" in bucket["algorithm"]

    def test_restart_consistent(self, bucket):
        assert bucket["restart_consistency"] is True

    def test_multi_worker_consistent(self, bucket):
        assert bucket["multi_worker_consistency"] is True

    def test_cross_window_consistent(self, bucket):
        assert bucket["cross_window_consistency"] is True

    def test_p119_cohort_consistent(self, bucket):
        assert bucket["p119_to_p120_cohort_consistent"] is True

    def test_deterministic_not_random(self, bucket):
        assert bucket["deterministic_not_random"] is True


# ---------------------------------------------------------------------------
# TestPerformanceTrend — 7 tests
# ---------------------------------------------------------------------------

class TestPerformanceTrend:

    @pytest.fixture(scope="class")
    def trend(self):
        return load("company_v2_phase6v_p120_performance_trend.json")

    def test_three_way_comparison_present(self, trend):
        cmp = trend["three_way_comparison"]
        assert "p118_25pct_baseline" in cmp
        assert "p119_initial_50pct" in cmp
        assert "p120_sustained_50pct" in cmp

    def test_p120_pi_p95_stable_vs_p119(self, trend):
        cmp = trend["three_way_comparison"]
        delta = abs(cmp["p120_sustained_50pct"]["pi_p95_ms"] - cmp["p119_initial_50pct"]["pi_p95_ms"])
        assert delta <= 20, f"P1.20 vs P1.19 pi_p95 delta={delta}ms exceeds 20ms tolerance"

    def test_no_monotonic_increase(self, trend):
        assert trend["p120_window_trend"]["monotonic_increase_detected"] is False

    def test_s8_recovers_close_to_s1(self, trend):
        s8_vs_s1_delta = trend["p120_window_trend"]["s8_vs_s1_delta_ms"]
        assert abs(s8_vs_s1_delta) <= 20, f"S8 vs S1 pi_p95 delta={s8_vs_s1_delta}ms exceeds 20ms"

    def test_warning_is_non_blocking_stable(self, trend):
        assert trend["warning_analysis"]["warning_is_non_blocking_stable"] is True

    def test_no_review_triggered(self, trend):
        assert trend["warning_analysis"]["no_review_triggered"] is True

    def test_no_hard_rollback_triggered(self, trend):
        assert trend["warning_analysis"]["no_hard_rollback_triggered"] is True


# ---------------------------------------------------------------------------
# TestResourceAudit — 6 tests
# ---------------------------------------------------------------------------

class TestResourceAudit:

    @pytest.fixture(scope="class")
    def resource(self):
        return load("company_v2_phase6v_p120_resource_audit.json")

    def test_no_upward_drift(self, resource):
        assert resource["combined"]["no_upward_drift"] is True

    def test_s8_recovers_to_s1_baseline(self, resource):
        assert resource["combined"]["s8_recovered_to_s1_baseline"] is True

    def test_burst_recovered_after_s5(self, resource):
        assert resource["combined"]["fd_recovered_after_s5"] is True

    def test_no_task_leaks(self, resource):
        assert resource["combined"]["task_leak_total"] == 0

    def test_no_pool_exhaustion(self, resource):
        assert resource["combined"]["pool_exhaustion_total"] == 0

    def test_diagnostics_backlog_stable(self, resource):
        assert resource["combined"]["diagnostics_backlog_stable_all_windows"] is True


# ---------------------------------------------------------------------------
# TestSafetyGate — 5 tests
# ---------------------------------------------------------------------------

class TestSafetyGate:

    @pytest.fixture(scope="class")
    def combined(self):
        return load("company_v2_phase6v_p120_combined_metrics.json")

    def test_safety_correctness_1(self, combined):
        assert combined["cumulative"]["safety_correctness_rate"] == 1.0

    def test_zero_tolerance_violations_0(self, combined):
        assert combined["cumulative"]["zero_tolerance_violations"] == 0

    def test_cumulative_p18_p120_violations_0(self, combined):
        assert combined["cumulative_p18_through_p120"]["zero_violations"] == 0

    def test_cumulative_selected_24299(self, combined):
        assert combined["cumulative_p18_through_p120"]["total_selected"] == 24299

    def test_pi_user_visible_leakage_0(self, combined):
        # Check via combined safety gate
        assert combined["safety_gate"]["safety_gate_passed"] is True


# ---------------------------------------------------------------------------
# TestBrowserRegression — 5 tests
# ---------------------------------------------------------------------------

class TestBrowserRegression:

    @pytest.fixture(scope="class")
    def browser(self):
        return load("company_v2_phase6v_p120_browser_regression.json")

    def test_all_16_cases_pass(self, browser):
        assert browser["total_cases"] == 16
        assert browser["passed"] == 16
        assert browser["failed"] == 0

    def test_legacy_only_confirmed(self, browser):
        assert browser["legacy_only_confirmed"] is True

    def test_no_pi_leakage(self, browser):
        assert browser["pi_user_visible_leakage_all_windows"] == 0

    def test_br15_restart_isolation_pass(self, browser):
        br15 = next(t for t in browser["test_cases"] if t["id"] == "BR-15")
        assert br15["result"] == "PASS"

    def test_br16_concurrency_isolation_pass(self, browser):
        br16 = next(t for t in browser["test_cases"] if t["id"] == "BR-16")
        assert br16["result"] == "PASS"


# ---------------------------------------------------------------------------
# TestDryRunIsolation — 4 tests
# ---------------------------------------------------------------------------

class TestDryRunIsolation:

    @pytest.fixture(scope="class")
    def dry_run(self):
        return load("company_v2_phase6v_p120_dry_run_isolation.json")

    def test_business_writes_zero(self, dry_run):
        assert dry_run["dry_run_results"]["business_writes"] == 0

    def test_provider_serving_calls_zero(self, dry_run):
        assert dry_run["dry_run_results"]["provider_serving_calls"] == 0

    def test_pending_candidates_not_applied(self, dry_run):
        assert dry_run["dry_run_results"]["pending_candidates_applied"] == 0

    def test_attribution_isolated(self, dry_run):
        assert dry_run["dry_run_results"]["etl_attribution_isolated"] is True
        assert dry_run["dry_run_results"]["pi_attribution_isolated"] is True


# ---------------------------------------------------------------------------
# TestSeventyFiveReadiness — 10 tests
# ---------------------------------------------------------------------------

class TestSeventyFiveReadiness:

    @pytest.fixture(scope="class")
    def readiness(self):
        return load("company_v2_phase6v_p120_seventy_five_readiness.json")

    def test_all_10_gates_passed(self, readiness):
        gates = readiness["gate_results"]
        expected_gates = [
            "repository_integrity", "configuration_integrity", "sustained_observation",
            "bucket_stability", "safety", "reliability", "performance",
            "resources", "browser_isolation", "test_and_rollback_evidence"
        ]
        for gate in expected_gates:
            assert gates[gate]["status"] == "PASS", f"Gate {gate} did not PASS"

    def test_readiness_summary_10_of_10(self, readiness):
        summary = readiness["readiness_summary"]
        assert summary["total_gates"] == 10
        assert summary["gates_passed"] == 10
        assert summary["gates_failed"] == 0

    def test_ready_for_decision_true(self, readiness):
        assert readiness["decision"]["ready_for_seventy_five_percent_decision"] is True

    def test_decision_required_from_owner(self, readiness):
        assert readiness["decision"]["decision_required_from_project_owner"] is True

    def test_seventy_five_not_authorized(self, readiness):
        assert readiness["decision"]["seventy_five_percent_authorized"] is False

    def test_seventy_five_not_applied(self, readiness):
        assert readiness["decision"]["seventy_five_percent_applied"] is False

    def test_actual_rollout_still_50(self, readiness):
        assert readiness["safety_constraints"]["actual_rollout_percent"] == 50

    def test_actual_config_still_7(self, readiness):
        assert readiness["safety_constraints"]["actual_config_version"] == 7

    def test_live_false(self, readiness):
        assert readiness["safety_constraints"]["live"] is False

    def test_production_false(self, readiness):
        assert readiness["safety_constraints"]["production_enabled"] is False


# ---------------------------------------------------------------------------
# TestFinalDecision — 8 tests
# ---------------------------------------------------------------------------

class TestFinalDecision:

    @pytest.fixture(scope="class")
    def decision(self):
        return load("company_v2_phase6v_p120_final_decision.json")

    def test_actual_rollout_percent_50(self, decision):
        assert decision["actual_rollout_percent_after_phase"] == 50

    def test_actual_config_version_7(self, decision):
        assert decision["actual_config_version_after_phase"] == 7

    def test_all_gates_in_gate_summary(self, decision):
        summary = decision["gate_summary"]
        assert summary["s1_s8_all_completed"] is True
        assert summary["safety_gate_passed"] is True
        assert summary["performance_gate_passed"] is True
        assert summary["resource_gate_passed"] is True
        assert summary["browser_regression_16_16"] is True
        assert summary["seventy_five_readiness_10_10_gates_passed"] is True

    def test_no_rollback(self, decision):
        assert decision["rollback_required"] is False
        assert decision["rollback_applied"] is False

    def test_seventy_five_not_authorized(self, decision):
        assert decision["seventy_five_percent_authorized"] is False

    def test_seventy_five_not_applied(self, decision):
        assert decision["seventy_five_percent_applied"] is False

    def test_decision_pending_owner(self, decision):
        assert decision["decision_required_from_project_owner"] is True
        assert decision["ready_for_seventy_five_percent_decision"] is True

    def test_live_and_production_false(self, decision):
        assert decision["live"] is False
        assert decision["production_enabled"] is False
        assert decision["provider_calls_serving"] == 0
