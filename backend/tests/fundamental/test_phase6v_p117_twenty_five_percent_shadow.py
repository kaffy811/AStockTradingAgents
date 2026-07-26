"""
Phase 6V-P1.17: 25% Shadow Promotion Verification Test Suite

Covers:
- Project owner approval gate
- Pre-promotion baseline
- Promotion audit (config_version 5→6)
- Bucket distribution verification
- K1-K5 per-window gates
- Combined results: selection count, symbols, styles, multi-turn
- Performance thresholds: warning/review/hard-rollback
- Safety gate: zero-tolerance categories
- Resource audit
- Data regression
- Browser regression
- Auto-rollback scenario verification
- Incremental isolation
- Secret scan
- Final gate
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
# TestProjectOwnerApproval
# ---------------------------------------------------------------------------

class TestProjectOwnerApproval:

    @pytest.fixture(scope="class")
    def approval(self):
        return load("pi_official_report_p117_project_owner_approval.json")

    def test_approval_granted(self, approval):
        assert approval["project_owner_approved"] is True

    def test_twenty_five_percent_authorized(self, approval):
        assert approval["twenty_five_percent_authorized"] is True

    def test_from_rollout_ten(self, approval):
        assert approval["from_rollout_percent"] == 10

    def test_to_rollout_twenty_five(self, approval):
        assert approval["to_rollout_percent"] == 25

    def test_config_version_transition(self, approval):
        assert approval["config_version_from"] == 5
        assert approval["config_version_to"] == 6

    def test_p116a_gate_confirmed(self, approval):
        gate = approval["prerequisite_gates_audited"]["p116a_readiness_gate"]
        assert gate["conditions_met"] == 29

    def test_p116b_gate_confirmed(self, approval):
        gate = approval["prerequisite_gates_audited"]["p116b_readiness_gate"]
        assert gate["conditions_met"] == 15
        assert gate["ready_for_twenty_five_percent_decision"] is True

    def test_monitoring_strategy_present(self, approval):
        strategy = approval["performance_risk_acknowledged"]["p117_monitoring_strategy"]
        assert "any_window_pi_p95_gte_4800ms" in strategy
        assert "combined_pi_p95_gte_5000ms" in strategy

    def test_live_serving_false(self, approval):
        assert approval["live_serving"] is False

    def test_production_enabled_false(self, approval):
        assert approval["production_enabled"] is False


# ---------------------------------------------------------------------------
# TestPrePromotionBaseline
# ---------------------------------------------------------------------------

class TestPrePromotionBaseline:

    @pytest.fixture(scope="class")
    def baseline(self):
        return load("pi_official_report_p117_pre_promotion_baseline.json")

    def test_baseline_passed(self, baseline):
        assert baseline["baseline_passed"] is True

    def test_cleared_for_promotion(self, baseline):
        assert baseline["cleared_for_promotion"] is True

    def test_selected_gte_50(self, baseline):
        assert baseline["result"]["selected"] >= 50

    def test_config_version_still_five(self, baseline):
        assert baseline["config_version"] == 5

    def test_rollout_still_ten(self, baseline):
        assert baseline["rollout_percent"] == 10

    def test_safety_correctness_1_0(self, baseline):
        assert baseline["result"]["safety_correctness_rate"] == 1.0

    def test_zero_tolerance_violations_zero(self, baseline):
        assert baseline["result"]["zero_tolerance_violations"] == 0

    def test_pi_p95_below_hard_rollback(self, baseline):
        assert baseline["result"]["pi_p95_ms"] < 5000

    def test_no_raw_errors(self, baseline):
        assert baseline["result"]["raw_500_count"] == 0
        assert baseline["result"]["raw_503_count"] == 0


# ---------------------------------------------------------------------------
# TestPromotionAudit
# ---------------------------------------------------------------------------

class TestPromotionAudit:

    @pytest.fixture(scope="class")
    def audit(self):
        return load("pi_official_report_p117_promotion_audit.json")

    def test_promotion_applied(self, audit):
        assert audit["promotion_applied"] is True

    def test_config_version_updated(self, audit):
        promo = audit["promotion"]
        assert promo["config_version_from"] == 5
        assert promo["config_version_to"] == 6

    def test_rollout_after_promotion(self, audit):
        assert audit["rollout_after_promotion"] == 25

    def test_bucket_threshold_raised(self, audit):
        promo = audit["promotion"]
        assert promo["bucket_threshold_before"] == 1000
        assert promo["bucket_threshold_after"] == 2500

    def test_users_do_not_see_pi_output(self, audit):
        assert audit["promotion"]["users_see_pi_output"] is False

    def test_all_steps_passed(self, audit):
        for step in audit["promotion_steps"]:
            assert step["status"] in ("passed", "applied", "verified", "initiated"), \
                f"Step {step['step']} has unexpected status: {step['status']}"

    def test_live_serving_false(self, audit):
        assert audit["live_serving"] is False

    def test_production_enabled_false(self, audit):
        assert audit["production_enabled"] is False


# ---------------------------------------------------------------------------
# TestBucketDistribution
# ---------------------------------------------------------------------------

class TestBucketDistribution:

    @pytest.fixture(scope="class")
    def dist(self):
        return load("pi_official_report_p117_bucket_distribution.json")

    def test_100k_keys_simulated(self, dist):
        assert dist["simulation"]["keys_simulated"] == 100000

    def test_actual_rate_within_tolerance(self, dist):
        result = dist["result"]
        assert result["within_tolerance"] is True
        assert abs(result["actual_rate_pct"] - 25.0) <= result["deviation_pct"] + 0.5

    def test_config_version_six(self, dist):
        assert dist["simulation"]["config_version"] == 6

    def test_bucket_threshold_2500(self, dist):
        assert dist["simulation"]["bucket_threshold"] == 2500

    def test_uniformity_accepted(self, dist):
        assert dist["uniformity_check"]["uniform_null_accepted"] is True

    def test_v5_cohort_contained_in_v6(self, dist):
        overlap = dist["cross_version_overlap"]
        assert overlap["overlap_v5_in_v6"] == overlap["config_v5_bucket_lt_1000"]

    def test_distribution_verified(self, dist):
        assert dist["distribution_verified"] is True


# ---------------------------------------------------------------------------
# TestObservationWindows — parametrized over K1-K5
# ---------------------------------------------------------------------------

WINDOWS = ["k1", "k2", "k3", "k4", "k5"]

class TestObservationWindows:

    @pytest.fixture(params=WINDOWS, scope="class")
    def window_data(self, request):
        wname = request.param
        return load(f"pi_official_report_p117_{wname}_results.json"), wname.upper()

    def test_selected_gte_500(self, window_data):
        data, name = window_data
        assert data["result"]["selected"] >= 500, f"{name}: selected < 500"

    def test_config_version_six(self, window_data):
        data, name = window_data
        assert data["config_version"] == 6, f"{name}: config_version != 6"

    def test_rollout_25(self, window_data):
        data, name = window_data
        assert data["rollout_percent"] == 25, f"{name}: rollout != 25"

    def test_safety_correctness_1_0(self, window_data):
        data, name = window_data
        assert data["safety"]["safety_correctness_rate"] == 1.0, f"{name}: safety < 1.0"

    def test_zero_tolerance_violations_zero(self, window_data):
        data, name = window_data
        assert data["safety"]["zero_tolerance_violations"] == 0, f"{name}: violations > 0"

    def test_pi_p95_below_hard_rollback(self, window_data):
        data, name = window_data
        assert data["result"]["pi_p95_ms"] < 5000, f"{name}: pi_p95 >= 5000ms"

    def test_no_window_triggers_review(self, window_data):
        data, name = window_data
        assert data["performance_gate"]["review_triggered"] is False, f"{name}: review triggered"

    def test_no_window_triggers_hard_rollback(self, window_data):
        data, name = window_data
        assert data["performance_gate"]["hard_rollback_triggered"] is False, f"{name}: hard rollback triggered"

    def test_pi_over_6s_zero(self, window_data):
        data, name = window_data
        assert data["result"]["pi_over_6s_count"] == 0, f"{name}: pi>6s > 0"

    def test_no_resource_errors(self, window_data):
        data, name = window_data
        res = data["resources"]
        assert res["raw_500_count"] == 0, f"{name}: raw 500 > 0"
        assert res["raw_503_count"] == 0, f"{name}: raw 503 > 0"
        assert res["pool_exhaustion"] == 0, f"{name}: pool exhaustion"
        assert res["task_leak"] == 0, f"{name}: task leak"
        assert res["PendingRollbackError"] == 0, f"{name}: PendingRollbackError"

    def test_window_passed(self, window_data):
        data, name = window_data
        assert data["window_passed"] is True, f"{name}: window_passed != True"


# ---------------------------------------------------------------------------
# TestCombinedResults
# ---------------------------------------------------------------------------

class TestCombinedResults:

    @pytest.fixture(scope="class")
    def combined(self):
        return load("pi_official_report_p117_combined_results.json")

    def test_total_selected_gte_2500(self, combined):
        assert combined["cumulative"]["total_selected"] >= 2500

    def test_unique_symbols_gte_100(self, combined):
        assert combined["cumulative"]["unique_symbols"] >= 100

    def test_unique_styles_gte_12(self, combined):
        assert combined["cumulative"]["unique_styles"] >= 12

    def test_multi_turn_gte_150(self, combined):
        assert combined["cumulative"]["multi_turn_count"] >= 150

    def test_coverage_requirements_all_met(self, combined):
        assert combined["coverage_requirements"]["all_coverage_requirements_met"] is True

    def test_combined_pi_p95_below_review(self, combined):
        assert combined["performance_gate"]["pi_p95_below_review"] is True

    def test_combined_pi_p95_below_hard_rollback(self, combined):
        assert combined["performance_gate"]["pi_p95_below_hard_rollback"] is True

    def test_no_window_breached_review(self, combined):
        assert combined["performance_gate"]["no_window_breached_review"] is True

    def test_no_window_breached_hard_rollback(self, combined):
        assert combined["performance_gate"]["no_window_breached_hard_rollback"] is True

    def test_pi_over_5s_rate_lt_2pct(self, combined):
        assert combined["performance_gate"]["pi_over_5s_rate_lt_2pct"] is True

    def test_pi_over_6s_count_zero(self, combined):
        assert combined["performance_gate"]["pi_over_6s_count_zero"] is True

    def test_performance_gate_passed(self, combined):
        assert combined["performance_gate"]["performance_gate_passed"] is True

    def test_safety_gate_passed(self, combined):
        assert combined["safety_gate"]["safety_gate_passed"] is True

    def test_safety_correctness_rate_1_0(self, combined):
        assert combined["safety_gate"]["safety_correctness_rate"] == 1.0

    def test_resource_gate_passed(self, combined):
        assert combined["resource_gate"]["resource_gate_passed"] is True

    def test_all_resource_zero(self, combined):
        rg = combined["resource_gate"]
        assert rg["raw_500_total"] == 0
        assert rg["raw_503_total"] == 0
        assert rg["pool_exhaustion_total"] == 0
        assert rg["task_leak_total"] == 0
        assert rg["PendingRollbackError_total"] == 0

    def test_combined_gate_passed(self, combined):
        assert combined["combined_gate_passed"] is True

    def test_rollout_25(self, combined):
        assert combined["rollout"] == 25

    def test_live_serving_false(self, combined):
        assert combined["live_serving"] is False

    def test_production_enabled_false(self, combined):
        assert combined["production_enabled"] is False


# ---------------------------------------------------------------------------
# TestPerformanceThresholds
# ---------------------------------------------------------------------------

class TestPerformanceThresholds:

    @pytest.fixture(scope="class")
    def combined(self):
        return load("pi_official_report_p117_combined_results.json")

    def test_warning_threshold_is_4700ms(self, combined):
        assert combined["performance_gate"]["warning_threshold_ms"] == 4700

    def test_review_threshold_is_4800ms(self, combined):
        assert combined["performance_gate"]["review_threshold_ms"] == 4800

    def test_hard_rollback_is_5000ms(self, combined):
        assert combined["performance_gate"]["hard_rollback_ms"] == 5000

    def test_combined_pi_p95_in_expected_range(self, combined):
        p95 = combined["cumulative"]["pi_p95_ms"]
        # Should be in warning range (>4700) but below review (<4800)
        assert 4700 <= p95 < 4800, f"pi_p95={p95}ms outside expected range [4700,4800)"

    def test_latency_improving_vs_p116a(self, combined):
        p116a_p95 = combined["historical_pi_p95_progression"]["P1.16A_J1_J3_p95_ms"]
        p117_p95 = combined["historical_pi_p95_progression"]["P1.17_K1_K5_p95_ms"]
        assert p117_p95 <= p116a_p95, \
            f"P1.17 pi_p95 ({p117_p95}ms) regressed vs P1.16A ({p116a_p95}ms)"

    def test_trend_monotonically_improving(self, combined):
        trend = combined["historical_pi_p95_progression"]["trend"]
        assert "improving" in trend.lower()


# ---------------------------------------------------------------------------
# TestTailLatency
# ---------------------------------------------------------------------------

class TestTailLatency:

    @pytest.fixture(scope="class")
    def tail(self):
        return load("pi_official_report_p117_tail_latency_analysis.json")

    def test_pi_over_6s_zero(self, tail):
        assert tail["pi_over_6s_count"] == 0

    def test_known_root_causes_classified(self, tail):
        causes = tail["root_cause_classification"]
        expected = {"cold_start", "shadow_concurrency", "repository_query",
                    "legacy_wait", "network", "auth", "db_checkout", "unknown"}
        assert set(causes.keys()) == expected

    def test_none_blocking(self, tail):
        assert tail["none_blocking_current_phase"] is True

    def test_rate_improved_vs_p116a(self, tail):
        comp = tail["comparison_to_p116a"]
        assert comp["p117_over_4800ms_rate_pct"] < comp["p116a_over_4800ms_rate_pct"], \
            "Over-4800ms rate did not improve vs P1.16A"

    def test_slowest_samples_all_safe(self):
        samples = load("pi_official_report_p117_slowest_samples.json")
        safety = samples["safety_check"]
        assert safety["all_entity_correct"] is True
        assert safety["all_url_valid"] is True
        assert safety["zero_tolerance_violations_in_slowest"] == 0

    def test_max_pi_below_hard_rollback(self):
        samples = load("pi_official_report_p117_slowest_samples.json")
        assert samples["max_pi_below_hard_rollback"] is True

    def test_max_pi_below_6s(self):
        samples = load("pi_official_report_p117_slowest_samples.json")
        assert samples["max_pi_below_6s"] is True


# ---------------------------------------------------------------------------
# TestSafetyGate
# ---------------------------------------------------------------------------

class TestSafetyGate:

    ZERO_TOLERANCE = [
        "fabricated_url", "wrong_entity", "wrong_year", "wrong_report_type",
        "provenance_failure", "stale_wrong_selection", "third_party_url",
        "pi_business_write", "double_write", "unknown_write", "trace_mismatch",
        "terminal_missing", "raw500", "raw503", "task_leak", "db_leak",
        "PendingRollbackError", "diagnostics_failure"
    ]

    @pytest.fixture(scope="class")
    def safety(self):
        return load("pi_official_report_p117_safety_audit.json")

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
# TestResourceAudit
# ---------------------------------------------------------------------------

class TestResourceAudit:

    @pytest.fixture(scope="class")
    def resource(self):
        return load("pi_official_report_p117_resource_audit.json")

    def test_resource_audit_passed(self, resource):
        assert resource["resource_audit_passed"] is True

    def test_combined_no_leaks(self, resource):
        combined = resource["combined"]
        assert combined["open_db_sessions"] == 0
        assert combined["task_leaks"] == 0
        assert combined["db_leaks"] == 0
        assert combined["pending_rollback_errors"] == 0
        assert combined["pool_exhaustion"] == 0
        assert combined["raw_500_count"] == 0
        assert combined["raw_503_count"] == 0

    def test_memory_stable(self, resource):
        assert resource["memory_trend"] == "stable_no_upward_drift"

    def test_memory_peak_reasonable(self, resource):
        assert resource["memory_peak_mb"] < 500

    def test_no_window_leaks(self, resource):
        for window, metrics in resource["per_window"].items():
            assert metrics["open_db_sessions"] == 0, f"{window}: db sessions leaked"
            assert metrics["task_leaks"] == 0, f"{window}: task leaked"
            assert metrics["pool_exhaustion"] == 0, f"{window}: pool exhaustion"
            assert metrics["PendingRollbackError"] == 0, f"{window}: PendingRollbackError"


# ---------------------------------------------------------------------------
# TestDataRegression
# ---------------------------------------------------------------------------

class TestDataRegression:

    @pytest.fixture(scope="class")
    def regression(self):
        return load("pi_official_report_p117_data_regression.json")

    def test_no_regression_detected(self, regression):
        assert regression["any_regression_detected"] is False

    def test_data_regression_passed(self, regression):
        assert regression["data_regression_passed"] is True

    @pytest.mark.parametrize("check", [
        "entity_resolution_accuracy",
        "report_year_accuracy",
        "report_type_accuracy",
        "pdf_selection_correctness",
        "rag_chunk_attribution",
        "tool_output_schema_compliance"
    ])
    def test_no_regression_per_check(self, regression, check):
        assert regression["regression_checks"][check]["regression_detected"] is False, \
            f"Regression detected in {check}"

    def test_all_rates_1_0(self, regression):
        for check, metrics in regression["regression_checks"].items():
            assert metrics["p117_rate"] == 1.0, \
                f"{check}: p117_rate ({metrics['p117_rate']}) < 1.0"


# ---------------------------------------------------------------------------
# TestBrowserRegression
# ---------------------------------------------------------------------------

class TestBrowserRegression:

    @pytest.fixture(scope="class")
    def browser(self):
        return load("pi_official_report_p117_browser_regression.json")

    def test_all_passed(self, browser):
        assert browser["passed"] == 10
        assert browser["failed"] == 0

    def test_browser_regression_passed(self, browser):
        assert browser["browser_regression_passed"] is True

    def test_all_cases_entity_correct(self, browser):
        for case in browser["test_cases"]:
            assert case["entity_correct"] is True, \
                f"{case['id']}: entity not correct"

    def test_all_cases_pi_below_hard_rollback(self, browser):
        for case in browser["test_cases"]:
            assert case["pi_p95_ms"] < 5000, \
                f"{case['id']}: pi_p95 >= 5000ms"


# ---------------------------------------------------------------------------
# TestAutoRollback
# ---------------------------------------------------------------------------

class TestAutoRollback:

    @pytest.fixture(scope="class")
    def rollback(self):
        return load("pi_official_report_p117_auto_rollback_verification.json")

    def test_rollback_mechanism_verified(self, rollback):
        assert rollback["auto_rollback_mechanism_verified"] is True

    def test_rollback_verification_passed(self, rollback):
        assert rollback["rollback_verification_passed"] is True

    def test_k1_k5_no_rollback(self, rollback):
        assert rollback["k1_k5_rollback_triggered"] is False
        assert rollback["k1_k5_pause_triggered"] is False

    def test_normal_operation_no_action(self, rollback):
        s1 = next(s for s in rollback["scenario_tests"] if s["scenario"] == "S1_normal_operation")
        assert s1["pause_triggered"] is False
        assert s1["rollback_triggered"] is False
        assert s1["result"] == "pass"

    def test_pause_threshold_routes_correctly(self, rollback):
        s3 = next(s for s in rollback["scenario_tests"] if s["scenario"] == "S3_pause_threshold_hypothetical")
        assert s3["pause_triggered"] is True
        assert s3["rollback_triggered"] is False
        assert s3["result"] == "pass"

    def test_hard_rollback_routes_correctly(self, rollback):
        s4 = next(s for s in rollback["scenario_tests"] if s["scenario"] == "S4_hard_rollback_hypothetical")
        assert s4["pause_triggered"] is True
        assert s4["rollback_triggered"] is True
        assert s4["result"] == "pass"

    def test_rollback_target_is_10_pct(self, rollback):
        assert rollback["rollback_policy"]["rollback_target_percent"] == 10

    def test_rollback_config_version_is_5(self, rollback):
        assert rollback["rollback_policy"]["rollback_config_version"] == 5


# ---------------------------------------------------------------------------
# TestIncrementalIsolation
# ---------------------------------------------------------------------------

class TestIncrementalIsolation:

    @pytest.fixture(scope="class")
    def isolation(self):
        return load("pi_official_report_p117_incremental_parallel_audit.json")

    def test_incremental_isolation_passed(self, isolation):
        assert isolation["incremental_isolation_passed"] is True

    def test_existing_cohort_no_regression(self, isolation):
        assert isolation["cohort_isolation"]["existing_cohort_regression"] is False

    def test_new_cohort_no_anomaly(self, isolation):
        assert isolation["cohort_isolation"]["new_cohort_anomaly"] is False

    def test_no_cross_cohort_interference(self, isolation):
        assert isolation["cohort_isolation"]["cross_cohort_interference"] is False

    def test_no_pool_contention(self, isolation):
        assert isolation["cohort_isolation"]["shared_pool_contention"] is False


# ---------------------------------------------------------------------------
# TestSecretScan
# ---------------------------------------------------------------------------

class TestSecretScan:

    @pytest.fixture(scope="class")
    def scan(self):
        return load("pi_official_report_p117_secret_scan.json")

    def test_scan_clean(self, scan):
        assert scan["scan_clean"] is True

    def test_no_secrets(self, scan):
        assert scan["secrets_found"] == 0

    def test_no_tokens(self, scan):
        assert scan["tokens_found"] == 0

    def test_no_database_urls(self, scan):
        assert scan["database_urls_found"] == 0

    def test_no_env_vars_committed(self, scan):
        assert scan["findings"]["env_vars_committed"] is False

    def test_18_artifacts_scanned(self, scan):
        assert scan["artifacts_scanned"] == 18

    def test_no_real_symbols(self, scan):
        assert scan["real_symbols_in_artifacts"] is False


# ---------------------------------------------------------------------------
# TestFinalGate
# ---------------------------------------------------------------------------

class TestFinalGate:

    @pytest.fixture(scope="class")
    def gate(self):
        return load("pi_official_report_p117_final_gate.json")

    def test_p117_gate_passed(self, gate):
        assert gate["p117_gate_passed"] is True

    def test_rollout_25(self, gate):
        assert gate["rollout"] == 25

    def test_config_version_6(self, gate):
        assert gate["config_version"] == 6

    def test_live_serving_false(self, gate):
        assert gate["live_serving"] is False

    def test_production_enabled_false(self, gate):
        assert gate["production_enabled"] is False

    def test_gate_summary_prerequisites(self, gate):
        summary = gate["gate_summary"]
        assert summary["project_owner_approval"] is True
        assert summary["pre_promotion_baseline_cleared"] is True
        assert summary["promotion_applied"] is True
        assert summary["bucket_distribution_verified"] is True

    def test_gate_summary_windows(self, gate):
        assert gate["gate_summary"]["k1_k5_all_passed"] is True

    def test_gate_summary_coverage(self, gate):
        summary = gate["gate_summary"]
        assert summary["combined_selected_gte_2500"] is True
        assert summary["unique_symbols_gte_100"] is True
        assert summary["unique_styles_gte_12"] is True
        assert summary["multi_turn_gte_150"] is True

    def test_gate_summary_performance(self, gate):
        summary = gate["gate_summary"]
        assert summary["combined_pi_p95_below_review"] is True
        assert summary["combined_pi_p95_below_hard_rollback"] is True
        assert summary["no_window_breached_review"] is True
        assert summary["no_window_breached_hard_rollback"] is True
        assert summary["pi_over_5s_rate_lt_2pct"] is True
        assert summary["pi_over_6s_count_zero"] is True

    def test_gate_summary_safety_and_resources(self, gate):
        summary = gate["gate_summary"]
        assert summary["safety_correctness_rate_1_0"] is True
        assert summary["zero_tolerance_violations_zero"] is True
        assert summary["resource_gate_passed"] is True

    def test_gate_summary_regression_and_scan(self, gate):
        summary = gate["gate_summary"]
        assert summary["data_regression_passed"] is True
        assert summary["browser_regression_10_10"] is True
        assert summary["auto_rollback_verified"] is True
        assert summary["secret_scan_clean"] is True

    def test_metrics_cumulative_total(self, gate):
        assert gate["metrics"]["total_selected_k1_k5"] >= 2500

    def test_metrics_cumulative_safety(self, gate):
        assert gate["metrics"]["cumulative_zero_tolerance_violations"] == 0
        assert gate["metrics"]["safety_correctness_rate"] == 1.0


# ---------------------------------------------------------------------------
# TestCrossPhaseArtifacts
# ---------------------------------------------------------------------------

class TestCrossPhaseArtifacts:

    def test_pdf_agent_gate_has_p117_stanza(self):
        data = load("pi_official_report_pdf_agent_gate.json")
        assert "p117_audit" in data
        assert data["p117_audit"]["p117_gate_passed"] is True
        assert data["p117_audit"]["rollout_percent"] == 25

    def test_compatible_runtime_gate_has_p117_stanza(self):
        data = load("pi_compatible_runtime_gate.json")
        assert "p117_audit" in data
        assert data["p117_audit"]["p117_gate_passed"] is True

    def test_secret_scan_has_p117_stanza(self):
        data = load("pi_shadow_secret_scan.json")
        assert "p117_scan" in data
        assert data["p117_scan"]["scan_clean"] is True

    def test_resource_leak_audit_has_p117_stanza(self):
        data = load("pi_shadow_resource_leak_audit.json")
        assert "p117_audit" in data
        assert data["p117_audit"]["resource_audit_passed"] is True
        assert data["p117_audit"]["p117_gate_passed"] is True
