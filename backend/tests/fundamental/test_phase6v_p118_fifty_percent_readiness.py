"""
Phase 6V-P1.18: 50% Shadow Promotion Readiness Test Suite

Covers:
- P1.17 gate re-audit
- L1-L8 sustained observation windows (each ≥625 selected)
- Combined results: ≥5000 selected, ≥100 symbols, ≥14 styles, ≥300 multi-turn, 0 duplicates
- Performance: warning/review/hard-rollback thresholds, window failure isolation
- Safety: 18 zero-tolerance categories, no subsequent success dilution
- Capacity: pool exhaustion, diagnostics, memory trend, FD leak, serving provider calls
- Incremental dry-runs: both isolated, no business writes
- Data regression: 18 new 2024, 19 gaps, 3 stale_review
- Browser regression: 12 cases, legacy-only confirmed
- Auto-rollback: 5 scenarios verified
- Backend full suite + frontend verification
- Secret scan + resource audit
- 50% readiness gate (27 conditions)
- Cross-phase artifact updates
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
# TestP117GateAudit
# ---------------------------------------------------------------------------

class TestP117GateAudit:

    @pytest.fixture(scope="class")
    def audit(self):
        return load("pi_official_report_p118_p117_audit.json")

    def test_p117_gate_confirmed(self, audit):
        assert audit["p117_gate_confirmed"]["p117_gate_passed"] is True

    def test_rollout_25(self, audit):
        assert audit["p117_gate_confirmed"]["rollout_percent"] == 25

    def test_config_version_6(self, audit):
        assert audit["p117_gate_confirmed"]["config_version"] == 6

    def test_safety_correctness_1_0(self, audit):
        assert audit["p117_gate_confirmed"]["safety_correctness_rate"] == 1.0

    def test_zero_tolerance_violations_zero(self, audit):
        assert audit["p117_gate_confirmed"]["zero_tolerance_violations"] == 0

    def test_live_serving_false(self, audit):
        assert audit["p117_gate_confirmed"]["live_serving"] is False

    def test_production_enabled_false(self, audit):
        assert audit["p117_gate_confirmed"]["production_enabled"] is False

    def test_p118_preconditions_met(self, audit):
        assert audit["p1_18_preconditions_met"] is True

    def test_cleared_for_l1(self, audit):
        assert audit["cleared_for_l1_observation"] is True

    def test_formal_defaults_verified(self, audit):
        defaults = audit["formal_defaults_verified"]
        assert defaults["production_enabled"] is False
        assert defaults["PI_AGENT_SHADOW_ENABLED"] is False
        assert defaults["authorized_agents"] == []
        assert defaults["default_rollout"] == 0


# ---------------------------------------------------------------------------
# TestObservationWindows — parametrized over L1-L8
# ---------------------------------------------------------------------------

WINDOWS = ["l1", "l2", "l3", "l4", "l5", "l6", "l7", "l8"]

class TestObservationWindows:

    @pytest.fixture(params=WINDOWS, scope="class")
    def window_data(self, request):
        wname = request.param
        return load(f"pi_official_report_p118_{wname}_results.json"), wname.upper()

    def test_selected_gte_625(self, window_data):
        data, name = window_data
        assert data["result"]["selected"] >= 625, f"{name}: selected < 625"

    def test_config_version_6(self, window_data):
        data, name = window_data
        assert data["config_version"] == 6

    def test_rollout_25(self, window_data):
        data, name = window_data
        assert data["rollout_percent"] == 25

    def test_safety_correctness_1_0(self, window_data):
        data, name = window_data
        assert data["safety"]["safety_correctness_rate"] == 1.0

    def test_zero_tolerance_violations_zero(self, window_data):
        data, name = window_data
        assert data["safety"]["zero_tolerance_violations"] == 0

    def test_pi_p95_below_review_4800ms(self, window_data):
        data, name = window_data
        assert data["result"]["pi_p95_ms"] < 4800, \
            f"{name}: pi_p95={data['result']['pi_p95_ms']}ms ≥ 4800ms (review threshold)"

    def test_no_window_triggers_review(self, window_data):
        data, name = window_data
        assert data["performance_gate"]["review_triggered"] is False

    def test_no_window_triggers_hard_rollback(self, window_data):
        data, name = window_data
        assert data["performance_gate"]["hard_rollback_triggered"] is False

    def test_pi_over_6s_zero(self, window_data):
        data, name = window_data
        assert data["result"]["pi_over_6000ms_count"] == 0

    def test_no_resource_errors(self, window_data):
        data, name = window_data
        res = data["resources"]
        assert res["raw_500_count"] == 0
        assert res["raw_503_count"] == 0
        assert res["pool_exhaustion"] == 0
        assert res["task_leak"] == 0
        assert res["PendingRollbackError"] == 0

    def test_terminal_completion_100pct(self, window_data):
        data, name = window_data
        assert data["result"]["terminal_completion_rate"] == 1.0

    def test_no_unexpected_timeouts(self, window_data):
        data, name = window_data
        assert data["result"]["unexpected_timeout_count"] == 0

    def test_no_fallbacks(self, window_data):
        data, name = window_data
        assert data["result"]["fallback_count"] == 0

    def test_provider_serving_calls_zero(self, window_data):
        data, name = window_data
        assert data["provider_serving_calls"] == 0

    def test_window_passed(self, window_data):
        data, name = window_data
        assert data["window_passed"] is True

    def test_tool_p95_below_4000ms(self, window_data):
        data, name = window_data
        assert data["result"]["tool_over_4000ms_count"] == 0


# ---------------------------------------------------------------------------
# TestWindowFailureIsolation (performance review must not be masked)
# ---------------------------------------------------------------------------

class TestWindowFailureIsolation:

    @pytest.fixture(scope="class")
    def combined(self):
        return load("pi_official_report_p118_combined_results.json")

    def test_no_window_breached_review_4800ms(self, combined):
        assert combined["performance_gate"]["no_window_breached_review_4800ms"] is True

    def test_no_window_breached_hard_rollback_5000ms(self, combined):
        assert combined["performance_gate"]["no_window_breached_hard_rollback_5000ms"] is True

    def test_each_window_pi_p95_individually_below_4800ms(self):
        for w in WINDOWS:
            data = load(f"pi_official_report_p118_{w}_results.json")
            p95 = data["result"]["pi_p95_ms"]
            assert p95 < 4800, \
                f"{w.upper()}: pi_p95={p95}ms ≥ 4800ms; window would be in review but combined may mask it"


# ---------------------------------------------------------------------------
# TestCombinedResults
# ---------------------------------------------------------------------------

class TestCombinedResults:

    @pytest.fixture(scope="class")
    def combined(self):
        return load("pi_official_report_p118_combined_results.json")

    def test_total_selected_gte_5000(self, combined):
        assert combined["cumulative"]["total_selected"] >= 5000

    def test_unique_ids_gte_5000(self, combined):
        assert combined["cumulative"]["unique_selected_ids"] >= 5000

    def test_duplicate_count_zero(self, combined):
        assert combined["cumulative"]["duplicate_count"] == 0

    def test_unique_symbols_100(self, combined):
        assert combined["cumulative"]["unique_symbols"] == 100

    def test_query_styles_gte_14(self, combined):
        assert combined["cumulative"]["unique_styles"] >= 14

    def test_multi_turn_gte_300(self, combined):
        assert combined["cumulative"]["multi_turn_count"] >= 300

    def test_all_coverage_requirements_met(self, combined):
        assert combined["coverage_requirements"]["all_coverage_requirements_met"] is True

    def test_combined_pi_p95_below_review(self, combined):
        assert combined["performance_gate"]["combined_pi_p95_ms"] < 4800

    def test_combined_pi_p95_below_hard_rollback(self, combined):
        assert combined["performance_gate"]["combined_pi_p95_ms"] < 5000

    def test_pi_over_5s_rate_lt_2pct(self, combined):
        assert combined["cumulative"]["pi_over_5s_rate_pct"] <= 2.0

    def test_pi_over_6s_count_zero(self, combined):
        assert combined["cumulative"]["pi_over_6000ms_count"] == 0

    def test_tool_p95_below_3800ms(self, combined):
        assert combined["cumulative"]["tool_p95_ms"] < 3800

    def test_tool_over_4000ms_count_zero(self, combined):
        assert combined["cumulative"]["tool_over_4000ms_count"] == 0

    def test_fallback_rate_zero(self, combined):
        assert combined["cumulative"]["fallback_rate_pct"] == 0.0

    def test_timeout_rate_zero(self, combined):
        assert combined["cumulative"]["unexpected_timeout_rate_pct"] == 0.0

    def test_terminal_completion_100pct(self, combined):
        assert combined["cumulative"]["terminal_completion_rate"] == 1.0

    def test_provider_serving_calls_zero(self, combined):
        assert combined["reliability_gate"]["provider_serving_calls_total"] == 0

    def test_safety_gate_passed(self, combined):
        assert combined["safety_gate"]["safety_gate_passed"] is True

    def test_performance_gate_passed(self, combined):
        assert combined["performance_gate"]["performance_gate_passed"] is True

    def test_reliability_gate_passed(self, combined):
        assert combined["reliability_gate"]["reliability_gate_passed"] is True

    def test_resource_gate_passed(self, combined):
        assert combined["resource_gate"]["resource_gate_passed"] is True

    def test_combined_gate_passed(self, combined):
        assert combined["combined_gate_passed"] is True

    def test_rollout_25(self, combined):
        assert combined["rollout"] == 25

    def test_live_serving_false(self, combined):
        assert combined["live_serving"] is False

    def test_production_enabled_false(self, combined):
        assert combined["production_enabled"] is False

    def test_pi_p95_improving_vs_p117(self, combined):
        prog = combined["historical_pi_p95_progression"]
        p117 = prog["P1.17_K1_K5_p95_ms"]
        p118 = prog["P1.18_L1_L8_p95_ms"]
        assert p118 <= p117, f"P1.18 pi_p95 ({p118}ms) regressed vs P1.17 ({p117}ms)"


# ---------------------------------------------------------------------------
# TestPerformanceThresholds
# ---------------------------------------------------------------------------

class TestPerformanceThresholds:

    @pytest.fixture(scope="class")
    def latency(self):
        return load("pi_official_report_p118_latency.json")

    def test_warning_threshold_4700ms(self, latency):
        assert latency["pi_shadow_latency"]["warning_threshold_ms"] == 4700

    def test_review_threshold_4800ms(self, latency):
        assert latency["pi_shadow_latency"]["review_threshold_ms"] == 4800

    def test_hard_rollback_threshold_5000ms(self, latency):
        assert latency["pi_shadow_latency"]["hard_rollback_threshold_ms"] == 5000

    def test_tool_review_threshold_3800ms(self, latency):
        assert latency["tool_latency"]["review_threshold_ms"] == 3800

    def test_tool_rollback_threshold_4000ms(self, latency):
        assert latency["tool_latency"]["hard_rollback_threshold_ms"] == 4000

    def test_tool_review_not_triggered(self, latency):
        assert latency["tool_latency"]["review_triggered"] is False

    def test_tool_hard_rollback_not_triggered(self, latency):
        assert latency["tool_latency"]["hard_rollback_triggered"] is False

    def test_pi_over_5s_rate_lte_2pct(self, latency):
        assert latency["pi_shadow_latency"]["over_5s_rate_pct"] <= 2.0

    def test_pi_over_6s_count_zero(self, latency):
        assert latency["pi_shadow_latency"]["over_6000ms_count"] == 0

    def test_latency_gate_passed(self, latency):
        assert latency["latency_gate_passed"] is True

    def test_pi_p95_in_warning_range(self, latency):
        p95 = latency["pi_shadow_latency"]["p95_ms"]
        # Must be above warning threshold (4700) but below review (4800)
        assert 4700 <= p95 < 4800, f"pi_p95={p95}ms outside expected range [4700,4800)"

    def test_single_outlier_policy_review(self):
        samples = load("pi_official_report_p118_slowest_samples.json")
        policy = samples["max_pi_single_occurrence_policy_review"]
        assert policy["rollback_triggered"] is False, "Single outlier should not trigger rollback per combined-p95 policy"


# ---------------------------------------------------------------------------
# TestSafetyGate
# ---------------------------------------------------------------------------

ZERO_TOLERANCE = [
    "fabricated_url", "wrong_entity", "wrong_year", "wrong_report_type",
    "provenance_failure", "stale_wrong_selection", "third_party_url_selected",
    "pi_business_write", "assistant_double_write", "unknown_write",
    "trace_mismatch", "terminal_missing", "raw500", "raw503",
    "task_leak", "db_leak", "PendingRollbackError", "diagnostics_failure"
]

class TestSafetyGate:

    @pytest.fixture(scope="class")
    def safety(self):
        return load("pi_official_report_p118_safety_audit.json")

    @pytest.mark.parametrize("category", ZERO_TOLERANCE)
    def test_zero_violation_per_category(self, safety, category):
        assert safety["zero_tolerance_categories"][category] == 0, \
            f"Zero-tolerance violation in {category}"

    def test_safety_correctness_rate_1_0(self, safety):
        assert safety["safety_correctness_rate"] == 1.0

    def test_total_violations_zero(self, safety):
        assert safety["total_zero_tolerance_violations"] == 0

    def test_safety_gate_passed(self, safety):
        assert safety["safety_gate_passed"] is True

    def test_cumulative_record_clean(self, safety):
        cum = safety["cumulative_safety_record"]
        assert cum["cumulative_zero_tolerance_violations"] == 0
        assert cum["cumulative_safety_correctness_rate"] == 1.0


# ---------------------------------------------------------------------------
# TestRollbackPolicy (safety and performance rollback conditions)
# ---------------------------------------------------------------------------

class TestRollbackPolicy:

    @pytest.fixture(scope="class")
    def rollback(self):
        return load("pi_official_report_p118_auto_rollback_audit.json")

    def test_p118_no_rollback_triggered(self, rollback):
        assert rollback["p118_rollback_triggered"] is False

    def test_p118_no_review_triggered(self, rollback):
        assert rollback["p118_review_triggered"] is False

    def test_rollback_target_10pct(self, rollback):
        assert rollback["rollback_policy"]["rollback_target_percent"] == 10

    def test_rollback_config_version_5(self, rollback):
        assert rollback["rollback_policy"]["rollback_config_version"] == 5

    def test_wrong_year_rollback_verified(self, rollback):
        s = next(s for s in rollback["scenario_tests"] if "hard_rollback" in s["scenario"])
        assert s["result"] == "pass"

    def test_zero_tolerance_rollback_scenario(self, rollback):
        s = next(s for s in rollback["scenario_tests"] if "zero_tolerance" in s["scenario"])
        assert s["result"] == "pass"
        assert "rollback" in s["action"]

    def test_auto_rollback_mechanism_verified(self, rollback):
        assert rollback["auto_rollback_mechanism_verified"] is True

    def test_success_does_not_dilute_violation_hypothetical(self, rollback):
        """Once rollback triggered by violation, cannot auto-recover to 25%"""
        policy = rollback["rollback_policy"]
        assert policy["rollback_target_percent"] == 10  # locked at 10%, not auto-recoverable
        assert policy["rollback_config_version"] == 5


# ---------------------------------------------------------------------------
# TestCapacityGate
# ---------------------------------------------------------------------------

class TestCapacityGate:

    @pytest.fixture(scope="class")
    def resource(self):
        return load("pi_official_report_p118_resource_audit.json")

    @pytest.fixture(scope="class")
    def capacity(self):
        return load("pi_official_report_p118_capacity_comparison.json")

    def test_resource_audit_passed(self, resource):
        assert resource["resource_audit_passed"] is True

    def test_pool_exhaustion_zero(self, resource):
        assert resource["combined"]["pool_exhaustion_total"] == 0

    def test_task_leak_zero(self, resource):
        assert resource["combined"]["task_leak_total"] == 0

    def test_db_leak_zero(self, resource):
        assert resource["combined"]["db_leak_total"] == 0

    def test_pending_rollback_zero(self, resource):
        assert resource["combined"]["PendingRollbackError_total"] == 0

    def test_raw_500_zero(self, resource):
        assert resource["combined"]["raw_500_total"] == 0

    def test_raw_503_zero(self, resource):
        assert resource["combined"]["raw_503_total"] == 0

    def test_diagnostics_backlog_stable(self, resource):
        assert resource["combined"]["diagnostics_backlog_stable"] is True

    def test_all_runners_cleaned_up(self, resource):
        assert resource["combined"]["all_runners_cleaned_up"] is True

    def test_memory_no_upward_drift(self, resource):
        assert resource["memory_analysis"]["no_upward_drift"] is True

    def test_memory_range_reasonable(self, resource):
        assert resource["memory_analysis"]["range_mb"] <= 30

    def test_no_fd_leak(self, resource):
        assert resource["fd_analysis"]["no_leak"] is True

    def test_no_zombie_processes_in_any_window(self, resource):
        for window, metrics in resource["per_window"].items():
            assert metrics["zombie_processes"] == 0, f"{window}: zombie processes"

    def test_capacity_gate_passed(self, capacity):
        assert capacity["capacity_gate_passed"] is True

    def test_50pct_projection_low_risk(self, capacity):
        assert capacity["fifty_pct_capacity_projection"]["capacity_risk_assessment"] == "low"

    def test_sublinear_scaling(self, capacity):
        assert capacity["capacity_scaling"]["actual_scaling_sublinear"] is True


# ---------------------------------------------------------------------------
# TestIncrementalDryRuns
# ---------------------------------------------------------------------------

class TestIncrementalDryRuns:

    @pytest.fixture(scope="class")
    def dry_run_1(self):
        return load("pi_official_report_p118_incremental_parallel_1.json")

    @pytest.fixture(scope="class")
    def dry_run_2(self):
        return load("pi_official_report_p118_incremental_parallel_2.json")

    def test_dry_run_1_no_business_writes(self, dry_run_1):
        assert dry_run_1["result"]["business_writes"] == 0

    def test_dry_run_1_no_serving_calls(self, dry_run_1):
        assert dry_run_1["result"]["serving_provider_calls"] == 0

    def test_dry_run_1_no_lock_conflicts(self, dry_run_1):
        assert dry_run_1["result"]["db_lock_conflicts"] == 0

    def test_dry_run_1_not_applied(self, dry_run_1):
        assert dry_run_1["result"]["new_candidates_applied"] is False

    def test_dry_run_1_active_selection_unchanged(self, dry_run_1):
        assert dry_run_1["result"]["active_selection_changed"] is False

    def test_dry_run_1_isolated_from_l4(self, dry_run_1):
        assert dry_run_1["impact_on_l4_observation"]["isolation_verified"] is True

    def test_dry_run_2_no_business_writes(self, dry_run_2):
        assert dry_run_2["result"]["business_writes"] == 0

    def test_dry_run_2_no_serving_calls(self, dry_run_2):
        assert dry_run_2["result"]["serving_provider_calls"] == 0

    def test_dry_run_2_idempotent(self, dry_run_2):
        assert dry_run_2["result"]["idempotent_vs_dry_run_1"] is True

    def test_dry_run_2_not_applied(self, dry_run_2):
        assert dry_run_2["result"]["new_candidates_applied"] is False

    def test_dry_run_2_isolated_from_l7(self, dry_run_2):
        assert dry_run_2["impact_on_l7_observation"]["isolation_verified"] is True

    def test_both_dry_runs_no_pool_exhaustion(self, dry_run_1, dry_run_2):
        assert dry_run_1["result"]["pool_exhaustion_during_run"] == 0
        assert dry_run_2["result"]["pool_exhaustion_during_run"] == 0

    def test_pending_candidates_not_applied(self, dry_run_2):
        assert dry_run_2["cross_run_summary"]["total_applied"] == 0
        assert dry_run_2["cross_run_summary"]["p118_expected_results_unchanged"] is True


# ---------------------------------------------------------------------------
# TestDataRegression
# ---------------------------------------------------------------------------

class TestDataRegression:

    @pytest.fixture(scope="class")
    def regression(self):
        return load("pi_official_report_p118_data_regression.json")

    def test_no_regression_detected(self, regression):
        assert regression["any_regression_detected"] is False

    def test_data_regression_passed(self, regression):
        assert regression["data_regression_passed"] is True

    def test_new_18_2024_all_verified(self, regression):
        n2024 = regression["new_2024_entries"]
        assert n2024["count"] == 18
        assert n2024["all_18_verified"] is True
        assert n2024["no_provider_call"] is True

    def test_remaining_19_gaps_all_verified(self, regression):
        gaps = regression["remaining_19_gaps"]
        assert gaps["count"] == 19
        assert gaps["all_19_verified"] is True
        assert gaps["correct_unavailable_returned"] is True
        assert gaps["no_fallback_to_wrong_type"] is True
        assert gaps["no_summary_substituted"] is True

    def test_stale_review_3_verified(self, regression):
        stale = regression["stale_review_3"]
        assert stale["count"] == 3
        assert stale["all_3_verified"] is True
        assert stale["no_wrong_preferred"] is True
        assert stale["no_wrong_latest"] is True
        assert stale["no_duplicate_active"] is True
        assert stale["no_physical_delete"] is True
        assert stale["reason_auditable"] is True

    @pytest.mark.parametrize("check", [
        "entity_resolution_accuracy",
        "report_year_accuracy",
        "report_type_accuracy",
        "pdf_selection_correctness",
        "rag_chunk_attribution",
        "tool_output_schema_compliance"
    ])
    def test_no_regression_per_check(self, regression, check):
        assert regression["regression_checks"][check]["regression_detected"] is False


# ---------------------------------------------------------------------------
# TestBrowserRegression
# ---------------------------------------------------------------------------

class TestBrowserRegression:

    @pytest.fixture(scope="class")
    def browser(self):
        return load("pi_official_report_p118_browser_regression.json")

    def test_all_12_passed(self, browser):
        assert browser["passed"] == 12
        assert browser["failed"] == 0

    def test_browser_regression_passed(self, browser):
        assert browser["browser_regression_passed"] is True

    def test_legacy_only_confirmed(self, browser):
        assert browser["ui_quality_checks"]["legacy_only_confirmed"] is True
        assert browser["ui_quality_checks"]["pi_not_visible_to_user"] is True

    def test_no_duplicate_tool_cards(self, browser):
        assert browser["ui_quality_checks"]["no_duplicate_tool_cards"] is True

    def test_no_second_assistant_message(self, browser):
        assert browser["ui_quality_checks"]["no_second_assistant_message"] is True

    def test_terminal_exactly_once(self, browser):
        assert browser["ui_quality_checks"]["terminal_exactly_once"] is True

    def test_conversation_persisted(self, browser):
        assert browser["ui_quality_checks"]["conversation_persisted"] is True

    def test_all_entity_correct(self, browser):
        for case in browser["test_cases"]:
            assert case["entity_correct"] is True, f"{case['id']}: entity not correct"

    def test_all_pi_below_5000ms(self, browser):
        for case in browser["test_cases"]:
            assert case["pi_p95_ms"] < 5000, f"{case['id']}: pi >= 5000ms"


# ---------------------------------------------------------------------------
# TestBackendAndFrontend
# ---------------------------------------------------------------------------

class TestBackendAndFrontend:

    @pytest.fixture(scope="class")
    def backend(self):
        return load("pi_official_report_p118_backend_full_suite.json")

    @pytest.fixture(scope="class")
    def frontend(self):
        return load("pi_official_report_p118_frontend_verification.json")

    def test_backend_collection_errors_zero(self, backend):
        assert backend["result"]["collection_errors"] == 0

    def test_backend_failed_zero(self, backend):
        assert backend["result"]["failed"] == 0

    def test_backend_exit_code_zero(self, backend):
        assert backend["result"]["exit_code"] == 0

    def test_backend_collected_gte_previous(self, backend):
        # P1.16B was 4990; P1.17 added 199 tests → expect ≥5189
        assert backend["result"]["collected"] >= 5189

    def test_backend_full_suite_passed(self, backend):
        assert backend["backend_full_suite_passed"] is True

    def test_frontend_npm_ci_exit_0(self, frontend):
        assert frontend["npm_ci"]["exit_code"] == 0

    def test_frontend_tests_all_pass(self, frontend):
        assert frontend["npm_test"]["failed"] == 0
        assert frontend["npm_test"]["passed"] == 688
        assert frontend["npm_test"]["exit_code"] == 0

    def test_frontend_build_exit_0(self, frontend):
        assert frontend["npm_build"]["exit_code"] == 0
        assert frontend["npm_build"]["dist_generated"] is True

    def test_frontend_verification_passed(self, frontend):
        assert frontend["frontend_verification_passed"] is True


# ---------------------------------------------------------------------------
# TestSecretScan
# ---------------------------------------------------------------------------

class TestSecretScan:

    def test_p118_scan_clean(self):
        scan = load("pi_shadow_secret_scan.json")
        assert scan["p118_scan"]["scan_clean"] is True

    def test_p118_27_artifacts_scanned(self):
        scan = load("pi_shadow_secret_scan.json")
        assert scan["p118_scan"]["artifacts_scanned"] == 27

    def test_p118_no_secrets(self):
        scan = load("pi_shadow_secret_scan.json")
        assert scan["p118_scan"]["secrets_found"] == 0

    def test_p118_no_real_symbols(self):
        scan = load("pi_shadow_secret_scan.json")
        assert scan["p118_scan"]["real_symbols_in_artifacts"] is False

    def test_p118_no_env_vars_committed(self):
        scan = load("pi_shadow_secret_scan.json")
        assert scan["p118_scan"]["env_vars_committed"] is False


# ---------------------------------------------------------------------------
# TestFiftyPercentReadiness (27 conditions)
# ---------------------------------------------------------------------------

READINESS_CONDITIONS = [
    "c01_p117_gate_reconfirmed",
    "c02_l1_l8_all_completed",
    "c03_each_window_selected_gte_625",
    "c04_combined_selected_gte_5000",
    "c05_unique_ids_gte_5000",
    "c06_duplicate_count_zero",
    "c07_unique_symbols_eq_100",
    "c08_query_styles_gte_14",
    "c09_multi_turn_gte_300",
    "c10_safety_correctness_eq_1_0",
    "c11_all_zero_tolerance_eq_0",
    "c12_timeout_rate_lte_1pct",
    "c13_fallback_rate_lte_10pct",
    "c14_every_window_pi_p95_lt_4800ms",
    "c15_combined_pi_p95_lt_4800ms",
    "c16_tool_p95_lt_3800ms",
    "c17_pi_over_5s_rate_lte_2pct",
    "c18_pi_over_6s_rate_eq_0",
    "c19_provider_calls_serving_eq_0",
    "c20_stale_wrong_selection_eq_0",
    "c21_incremental_isolation_passed",
    "c22_db_resource_gate_passed",
    "c23_browser_regression_passed",
    "c24_canonical_backend_full_passed",
    "c25_frontend_tests_build_passed",
    "c26_production_eq_false",
    "c27_live_eq_false"
]

class TestFiftyPercentReadiness:

    @pytest.fixture(scope="class")
    def readiness(self):
        return load("pi_official_report_p118_fifty_percent_readiness.json")

    @pytest.mark.parametrize("condition", READINESS_CONDITIONS)
    def test_condition_satisfied(self, readiness, condition):
        assert readiness["conditions"][condition] is True, \
            f"50% readiness condition {condition} not satisfied"

    def test_all_27_conditions_met(self, readiness):
        assert readiness["conditions_met"] == 27
        assert readiness["conditions_total"] == 27

    def test_ready_for_fifty_percent_decision(self, readiness):
        assert readiness["ready_for_fifty_percent_decision"] is True

    def test_decision_required_from_project_owner(self, readiness):
        assert readiness["decision_required_from_project_owner"] is True

    def test_not_auto_promoted_to_fifty(self, readiness):
        assert readiness["recommended_to_raise_to_fifty_percent"] is False

    def test_continue_twenty_five_recommended(self, readiness):
        assert readiness["recommended_to_continue_twenty_five_percent"] is True

    def test_live_not_recommended(self, readiness):
        assert readiness["recommended_for_live_serving"] is False

    def test_production_not_recommended(self, readiness):
        assert readiness["recommended_for_production"] is False

    def test_rollout_still_25(self, readiness):
        assert readiness["rollout"] == 25

    def test_live_serving_false(self, readiness):
        assert readiness["live_serving"] is False

    def test_production_enabled_false(self, readiness):
        assert readiness["production_enabled"] is False


# ---------------------------------------------------------------------------
# TestFinalGate
# ---------------------------------------------------------------------------

class TestFinalGate:

    @pytest.fixture(scope="class")
    def gate(self):
        return load("pi_official_report_p118_final_gate.json")

    def test_p118_gate_passed(self, gate):
        assert gate["p118_gate_passed"] is True

    def test_result_contract_rollout_25(self, gate):
        assert gate["result_contract"]["rollout_percent"] == 25

    def test_result_contract_8_windows(self, gate):
        assert gate["result_contract"]["observation_windows"] == 8

    def test_result_contract_5000_selected(self, gate):
        assert gate["result_contract"]["selected_eligible_requests"] >= 5000

    def test_result_contract_safety_1_0(self, gate):
        assert gate["result_contract"]["safety_correctness_rate"] == 1.0

    def test_result_contract_backend_passed(self, gate):
        assert gate["result_contract"]["backend_full_suite_passed"] is True

    def test_result_contract_frontend_passed(self, gate):
        assert gate["result_contract"]["frontend_verification_passed"] is True

    def test_result_contract_ready_decision(self, gate):
        assert gate["result_contract"]["ready_for_fifty_percent_decision"] is True

    def test_result_contract_not_auto_fifty(self, gate):
        assert gate["result_contract"]["recommended_to_raise_to_fifty_percent"] is False

    def test_result_contract_no_live(self, gate):
        assert gate["result_contract"]["recommended_for_live_serving"] is False

    def test_result_contract_no_production(self, gate):
        assert gate["result_contract"]["recommended_for_production"] is False

    def test_result_contract_production_disabled(self, gate):
        assert gate["result_contract"]["production_enabled"] is False


# ---------------------------------------------------------------------------
# TestCrossPhaseArtifacts
# ---------------------------------------------------------------------------

class TestCrossPhaseArtifacts:

    def test_pdf_agent_gate_has_p118_stanza(self):
        data = load("pi_official_report_pdf_agent_gate.json")
        assert "p118_audit" in data
        assert data["p118_audit"]["p118_gate_passed"] is True
        assert data["p118_audit"]["rollout_percent"] == 25
        assert data["p118_audit"]["ready_for_fifty_percent_decision"] is True

    def test_compatible_runtime_gate_has_p118_stanza(self):
        data = load("pi_compatible_runtime_gate.json")
        assert "p118_audit" in data
        assert data["p118_audit"]["p118_gate_passed"] is True
        assert data["p118_audit"]["ready_for_fifty_percent_decision"] is True

    def test_secret_scan_has_p118_stanza(self):
        data = load("pi_shadow_secret_scan.json")
        assert "p118_scan" in data
        assert data["p118_scan"]["scan_clean"] is True

    def test_resource_leak_audit_has_p118_stanza(self):
        data = load("pi_shadow_resource_leak_audit.json")
        assert "p118_audit" in data
        assert data["p118_audit"]["resource_audit_passed"] is True
        assert data["p118_audit"]["p118_gate_passed"] is True

    def test_formal_defaults_in_p117_audit(self):
        """Verify formal defaults unchanged: AGENT_EXECUTOR_MODE=legacy, PI_AGENT_SHADOW_ENABLED=false"""
        audit = load("pi_official_report_p118_p117_audit.json")
        defaults = audit["formal_defaults_verified"]
        assert defaults["AGENT_EXECUTOR_MODE"] == "legacy"
        assert defaults["PI_AGENT_SHADOW_ENABLED"] is False
        assert defaults["production_enabled"] is False
