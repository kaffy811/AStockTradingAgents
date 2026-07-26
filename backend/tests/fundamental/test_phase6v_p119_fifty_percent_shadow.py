"""
Phase 6V-P1.19: 50% Shadow Promotion & Stability Test Suite

Covers:
- Owner authorization contract
- P1.18 preflight audit
- 25% → 50% promotion
- Config version 6 → 7
- F1-F6 observation windows (each ≥800 selected)
- Combined results: ≥5000 selected, 100 symbols, 14 styles, ≥300 multi-turn, 0 duplicates
- Performance comparison: 25% vs 50% baseline delta ≤2%
- Safety gate: 1.0 correctness, 0 zero-tolerance
- Reliability gate: 0% timeout, 0% fallback, 0% legacy stall, 1.0 terminal completion
- Resource gate: no leak, no drift, no pool exhaustion
- Browser isolation: 14/14 pass, legacy-only confirmed
- Hard rollback contract: config_version=8 (not 6) on rollback
- Production/live remain false
- Provider serving calls = 0
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
# TestOwnerAuthorization
# ---------------------------------------------------------------------------

class TestOwnerAuthorization:

    @pytest.fixture(scope="class")
    def auth(self):
        return load("company_v2_phase6v_p119_owner_authorization.json")

    def test_authorized_rollout_to_50(self, auth):
        assert auth["authorized_rollout_to"] == 50

    def test_live_serving_not_authorized(self, auth):
        assert auth["live_serving_authorized"] is False

    def test_production_not_authorized(self, auth):
        assert auth["production_authorized"] is False

    def test_provider_serving_calls_authorized_zero(self, auth):
        assert auth["provider_serving_calls_authorized"] == 0

    def test_rollback_config_version_is_8(self, auth):
        # Rollback must use config_version=8 (monotonic), never revert to 6
        assert auth["rollback_config_version"] == 8


# ---------------------------------------------------------------------------
# TestPreflightAudit
# ---------------------------------------------------------------------------

class TestPreflightAudit:

    @pytest.fixture(scope="class")
    def audit(self):
        return load("company_v2_phase6v_p119_preflight_audit.json")

    def test_p118_sha_confirmed(self, audit):
        assert audit["p118_sha_confirmed"] == "82c163028d546165d5197e81f61ce2328d5d2d2e"

    def test_p118_artifacts_complete(self, audit):
        assert audit["p118_artifacts_complete"] is True

    def test_p118_conditions_met_27(self, audit):
        assert audit["p118_conditions_met"] == 27

    def test_current_rollout_is_25(self, audit):
        assert audit["current_rollout_percent"] == 25

    def test_current_config_version_is_6(self, audit):
        assert audit["current_config_version"] == 6

    def test_all_p118_gates_confirmed(self, audit):
        assert audit["all_p118_gates_confirmed"] is True

    def test_no_config_drift(self, audit):
        assert audit["config_drift_detected"] is False

    def test_promotion_cleared(self, audit):
        assert audit["promotion_cleared"] is True


# ---------------------------------------------------------------------------
# TestPromotion
# ---------------------------------------------------------------------------

class TestPromotion:

    @pytest.fixture(scope="class")
    def promo(self):
        return load("company_v2_phase6v_p119_promotion.json")

    def test_rollout_before_25(self, promo):
        assert promo["rollout_before"] == 25

    def test_rollout_after_50(self, promo):
        assert promo["rollout_after"] == 50

    def test_config_version_before_6(self, promo):
        assert promo["config_version_before"] == 6

    def test_config_version_after_7(self, promo):
        assert promo["config_version_after"] == 7

    def test_repository_defaults_unchanged(self, promo):
        assert promo["repository_defaults_unchanged"] is True

    def test_production_config_unchanged(self, promo):
        assert promo["production_config_unchanged"] is True

    def test_live_serving_still_false(self, promo):
        assert promo["live_serving_value"] is False

    def test_artifact_runtime_consistent(self, promo):
        assert promo["artifact_runtime_consistent"] is True


# ---------------------------------------------------------------------------
# TestObservationWindows — parametrized over F1-F6
# ---------------------------------------------------------------------------

WINDOWS = ["f1", "f2", "f3", "f4", "f5", "f6"]

class TestObservationWindows:

    @pytest.fixture(params=WINDOWS, scope="class")
    def window_data(self, request):
        wname = request.param
        return load(f"company_v2_phase6v_p119_{wname}_results.json"), wname.upper()

    def test_selected_gte_800(self, window_data):
        data, name = window_data
        assert data["result"]["selected"] >= 800, f"{name}: selected < 800"

    def test_config_version_7(self, window_data):
        data, name = window_data
        assert data["config_version"] == 7

    def test_rollout_50(self, window_data):
        data, name = window_data
        assert data["rollout_percent"] == 50

    def test_safety_correctness_1_0(self, window_data):
        data, name = window_data
        assert data["safety"]["safety_correctness_rate"] == 1.0

    def test_zero_tolerance_violations_zero(self, window_data):
        data, name = window_data
        assert data["safety"]["zero_tolerance_violations"] == 0

    def test_pi_p95_below_review_4800ms(self, window_data):
        data, name = window_data
        assert data["result"]["pi_p95_ms"] < 4800, \
            f"{name}: pi_p95={data['result']['pi_p95_ms']}ms >= 4800ms (review threshold)"

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
# TestCombinedMetrics
# ---------------------------------------------------------------------------

class TestCombinedMetrics:

    @pytest.fixture(scope="class")
    def combined(self):
        return load("company_v2_phase6v_p119_combined_metrics.json")

    def test_total_selected_gte_5000(self, combined):
        assert combined["cumulative"]["total_selected"] >= 5000

    def test_selection_rate_near_50pct(self, combined):
        rate = combined["cumulative"]["selection_rate_pct"]
        assert 48.0 <= rate <= 52.0, f"Selection rate {rate}% not near 50%"

    def test_no_duplicates(self, combined):
        assert combined["cumulative"]["duplicates"] == 0

    def test_unique_symbols_100(self, combined):
        assert combined["cumulative"]["unique_symbols"] == 100

    def test_query_styles_gte_14(self, combined):
        assert combined["cumulative"]["query_styles"] >= 14

    def test_multi_turn_gte_300(self, combined):
        assert combined["cumulative"]["multi_turn_count"] >= 300

    def test_safety_gate_passed(self, combined):
        assert combined["safety_gate"]["safety_gate_passed"] is True

    def test_combined_gate_passed(self, combined):
        assert combined["combined_gate_passed"] is True


# ---------------------------------------------------------------------------
# TestSafetyGate
# ---------------------------------------------------------------------------

class TestSafetyGate:

    @pytest.fixture(scope="class")
    def combined(self):
        return load("company_v2_phase6v_p119_combined_metrics.json")

    def test_safety_correctness_rate_1_0(self, combined):
        assert combined["cumulative"]["safety_correctness_rate"] == 1.0

    def test_zero_tolerance_violations_zero(self, combined):
        assert combined["cumulative"]["zero_tolerance_violations"] == 0

    def test_provider_calls_serving_zero(self, combined):
        assert combined["cumulative"]["provider_calls_serving"] == 0

    def test_business_writes_zero(self, combined):
        assert combined["cumulative"]["business_writes"] == 0

    def test_all_safety_categories_zero(self, combined):
        assert combined["safety_gate"]["all_safety_categories_zero"] is True


# ---------------------------------------------------------------------------
# TestReliabilityGate
# ---------------------------------------------------------------------------

class TestReliabilityGate:

    @pytest.fixture(scope="class")
    def combined(self):
        return load("company_v2_phase6v_p119_combined_metrics.json")

    def test_timeout_rate_zero(self, combined):
        assert combined["cumulative"]["unexpected_timeout_rate"] == 0.0

    def test_fallback_rate_zero(self, combined):
        assert combined["cumulative"]["fallback_rate"] == 0.0

    def test_legacy_stall_rate_zero(self, combined):
        assert combined["cumulative"]["legacy_stall_rate"] == 0.0

    def test_terminal_completion_1_0(self, combined):
        assert combined["cumulative"]["terminal_completion_rate"] == 1.0

    def test_reliability_gate_passed(self, combined):
        assert combined["reliability_gate"]["reliability_gate_passed"] is True


# ---------------------------------------------------------------------------
# TestPerformanceComparison
# ---------------------------------------------------------------------------

class TestPerformanceComparison:

    @pytest.fixture(scope="class")
    def perf(self):
        return load("company_v2_phase6v_p119_performance_comparison.json")

    def test_tool_p95_delta_within_2pct(self, perf):
        assert perf["tool_latency"]["within_2pct_budget"] is True

    def test_tool_p95_delta_absolute_small(self, perf):
        delta = perf["tool_latency"]["absolute_delta"]["p95_ms"]
        assert delta <= 50, f"Tool p95 delta {delta}ms exceeds 50ms"

    def test_pi_p95_result_below_review(self, perf):
        p95 = perf["pi_latency"]["result_50pct"]["p95_ms"]
        assert p95 < 4800, f"Pi p95 {p95}ms >= 4800ms review threshold"

    def test_pi_over_5s_improved_or_zero(self, perf):
        count_50 = perf["pi_latency"]["result_50pct"]["pi_over_5s_count"]
        count_25 = perf["pi_latency"]["baseline_25pct"]["pi_over_5s_count"]
        assert count_50 <= count_25, f"pi_over_5s regressed: 50%={count_50} > 25%={count_25}"

    def test_pi_over_6s_zero(self, perf):
        assert perf["pi_latency"]["pi_over_6s_count"] == 0

    def test_hard_rollback_not_triggered(self, perf):
        assert perf["pi_latency"]["hard_rollback_triggered"] is False

    def test_performance_comparison_passed(self, perf):
        assert perf["performance_comparison_passed"] is True


# ---------------------------------------------------------------------------
# TestResourceAudit
# ---------------------------------------------------------------------------

class TestResourceAudit:

    @pytest.fixture(scope="class")
    def audit(self):
        return load("company_v2_phase6v_p119_resource_audit.json")

    def test_no_upward_drift(self, audit):
        assert audit["combined"]["no_upward_drift"] is True

    def test_pool_exhaustion_zero(self, audit):
        assert audit["combined"]["pool_exhaustion_total"] == 0

    def test_task_leak_zero(self, audit):
        assert audit["combined"]["task_leak_total"] == 0

    def test_fd_recovered_after_f5(self, audit):
        assert audit["combined"]["fd_recovered_after_f5"] is True

    def test_resource_audit_passed(self, audit):
        assert audit["resource_audit_passed"] is True


# ---------------------------------------------------------------------------
# TestBrowserRegression
# ---------------------------------------------------------------------------

class TestBrowserRegression:

    @pytest.fixture(scope="class")
    def browser(self):
        return load("company_v2_phase6v_p119_browser_regression.json")

    def test_14_cases_all_pass(self, browser):
        summary = browser["summary"]
        assert summary["total"] == 14
        assert summary["passed"] == 14
        assert summary["failed"] == 0

    def test_legacy_only_confirmed(self, browser):
        assert browser["global_invariants"]["legacy_only"] is True

    def test_no_pi_visible(self, browser):
        assert browser["global_invariants"]["no_pi_visible"] is True

    def test_provider_serving_calls_zero(self, browser):
        assert browser["global_invariants"]["provider_serving_calls"] == 0

    def test_browser_regression_passed(self, browser):
        assert browser["browser_regression_passed"] is True


# ---------------------------------------------------------------------------
# TestRollbackContract
# ---------------------------------------------------------------------------

class TestRollbackContract:

    @pytest.fixture(scope="class")
    def auth(self):
        return load("company_v2_phase6v_p119_owner_authorization.json")

    def test_rollback_target_rollout_is_25(self, auth):
        # Rollback reverts rollout to 25%, not 0%
        assert auth["rollback_target_rollout"] == 25

    def test_rollback_config_version_is_8_not_6(self, auth):
        # Config version is monotonic: rollback uses 8, never reverts to 6 or 7
        assert auth["rollback_config_version"] == 8
        assert auth["rollback_config_version"] != 6
        assert auth["rollback_config_version"] != 7

    def test_hard_rollback_conditions_remain_active(self, auth):
        assert auth["hard_rollback_conditions_remain_active"] is True


# ---------------------------------------------------------------------------
# TestFinalDecision
# ---------------------------------------------------------------------------

class TestFinalDecision:

    @pytest.fixture(scope="class")
    def decision(self):
        return load("company_v2_phase6v_p119_final_decision.json")

    def test_promotion_applied(self, decision):
        assert decision["promotion_applied"] is True

    def test_actual_rollout_50(self, decision):
        assert decision["actual_rollout_percent_after_phase"] == 50

    def test_actual_config_version_7(self, decision):
        assert decision["actual_config_version_after_phase"] == 7

    def test_selected_gte_5000(self, decision):
        assert decision["selected_eligible_requests"] >= 5000

    def test_safety_correctness_1_0(self, decision):
        assert decision["safety_correctness_rate"] == 1.0

    def test_zero_tolerance_event_count_zero(self, decision):
        assert decision["zero_tolerance_event_count"] == 0

    def test_pi_p95_below_review(self, decision):
        assert decision["pi_p95_ms"] < 4800

    def test_pi_over_5s_rate_zero(self, decision):
        assert decision["pi_over_5s_rate"] == 0.0

    def test_rollback_not_required(self, decision):
        assert decision["rollback_required"] is False

    def test_production_and_live_remain_false(self, decision):
        assert decision["production_enabled"] is False
        assert decision["live"] is False

    def test_provider_calls_serving_zero(self, decision):
        assert decision["provider_calls_serving"] == 0

    def test_no_blocking_reasons(self, decision):
        assert decision["blocking_reasons"] == []

    def test_all_gate_summaries_true(self, decision):
        for gate_key, gate_val in decision["gate_summary"].items():
            assert gate_val is True, f"Gate {gate_key} is not True"
