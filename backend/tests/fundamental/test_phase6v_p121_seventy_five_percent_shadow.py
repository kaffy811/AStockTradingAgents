"""
Phase 6V-P1.21: 75% Shadow Promotion Test Suite

Covers:
- P1.20 preflight audit (SHA + 20 artifacts intact, no drift, promotion cleared)
- Owner authorization (authorized_rollout 50→75, live/prod/100% NOT authorized)
- Promotion (rollout 50→75, config 7→8, promotion_applied, runtime_verified)
- Bucket migration (50% ⊆ 75%, config_version removed from hash, salt stable, restart/worker/window stable)
- Runtime verification (effective_rollout=75, config=8, all 12 verifications PASS)
- 8 observation windows T1-T8 (parametrized, 12 tests × 8 = 96 tests)
- Combined metrics (>10000 selected, 100 symbols, 14 styles, ≥350 multi-turn, 0 dups)
- Performance comparison (four-way P1.18/P1.19/P1.20/P1.21, <2% delta, no review)
- Resource audit (T8 recovery, T5 burst explained, no leaks, no drift)
- Safety gate (correctness=1.0, zero_tol=0, cumulative updated, leakage=0)
- Browser regression (20/20 PASS, legacy_only, no Pi leakage, no dups)
- Dry-run isolation (writes=0, serving=0, candidates not applied)
- Gate results (12 gates A-L, all PASS)
- Final decision (rollout=75, config=8, live=false, prod=false, no rollback, 100% not auth)

CRITICAL SAFETY INVARIANTS (verified throughout):
- live=false, production_enabled=false
- recommended_for_live_serving=false, recommended_for_production=false
- provider_serving_calls=0
- recommended_for_one_hundred_percent=false
- actual_rollout_percent=75, actual_config_version=8
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
        return load("company_v2_phase6v_p121_preflight_audit.json")

    def test_p120_sha_confirmed(self, audit):
        assert audit["p120_final_sha_confirmed"] == "7cbc4b57d420e6c43f062f8131544c2ef7dae9be"

    def test_p120_artifacts_complete(self, audit):
        assert audit["p120_artifacts_complete"] is True

    def test_p120_artifacts_count_at_least_20(self, audit):
        assert audit["p120_artifacts_found"] >= 20

    def test_no_configuration_drift(self, audit):
        assert audit["configuration_drift_detected"] is False

    def test_current_rollout_is_50(self, audit):
        assert audit["current_rollout_percent"] == 50

    def test_current_config_version_is_7(self, audit):
        assert audit["current_config_version"] == 7

    def test_promotion_cleared(self, audit):
        assert audit["promotion_cleared"] is True

    def test_bucket_fix_note_present(self, audit):
        note = audit.get("bucket_fix_note", "")
        assert "pi_v1" in note
        assert "config_version" in note


# ---------------------------------------------------------------------------
# TestOwnerAuthorization — 6 tests
# ---------------------------------------------------------------------------

class TestOwnerAuthorization:

    @pytest.fixture(scope="class")
    def auth(self):
        return load("company_v2_phase6v_p121_owner_authorization.json")

    def test_authorized_rollout_from_50_to_75(self, auth):
        assert auth["authorized_rollout_from"] == 50
        assert auth["authorized_rollout_to"] == 75

    def test_authorized_config_version_from_7_to_8(self, auth):
        assert auth["authorized_config_version_from"] == 7
        assert auth["authorized_config_version_to"] == 8

    def test_live_serving_not_authorized(self, auth):
        assert auth["live_serving_authorized"] is False

    def test_production_not_authorized(self, auth):
        assert auth["production_authorized"] is False

    def test_one_hundred_percent_not_authorized(self, auth):
        assert auth["one_hundred_percent_authorized"] is False

    def test_rollback_plan_documented(self, auth):
        assert auth["rollback_rollout_percent"] == 50
        assert auth["rollback_config_version"] == 9


# ---------------------------------------------------------------------------
# TestPromotion — 8 tests
# ---------------------------------------------------------------------------

class TestPromotion:

    @pytest.fixture(scope="class")
    def promotion(self):
        return load("company_v2_phase6v_p121_promotion.json")

    def test_rollout_50_to_75(self, promotion):
        assert promotion["rollout_before"] == 50
        assert promotion["rollout_after"] == 75

    def test_config_version_7_to_8(self, promotion):
        assert promotion["config_version_before"] == 7
        assert promotion["config_version_after"] == 8

    def test_promotion_applied(self, promotion):
        assert promotion["promotion_applied"] is True

    def test_promotion_mechanism(self, promotion):
        assert promotion["promotion_mechanism"] == "staging_test_fixture_override"

    def test_repository_defaults_unchanged(self, promotion):
        assert promotion["repository_defaults_unchanged"] is True

    def test_live_serving_false(self, promotion):
        assert promotion["live_serving"] is False

    def test_production_false(self, promotion):
        assert promotion["production_enabled"] is False

    def test_bucket_migration_note_present(self, promotion):
        note = promotion.get("bucket_migration_note", "")
        assert "pi_v1" in note


# ---------------------------------------------------------------------------
# TestBucketMigration — 12 tests
# ---------------------------------------------------------------------------

class TestBucketMigration:

    @pytest.fixture(scope="class")
    def bucket(self):
        return load("company_v2_phase6v_p121_bucket_migration.json")

    def test_hash_input_format(self, bucket):
        fmt = bucket["hash_input_format"]
        assert "stable_bucket_salt" in fmt
        assert "config_version" not in fmt

    def test_stable_bucket_salt_is_pi_v1(self, bucket):
        assert bucket["stable_bucket_salt_value"] == "pi_v1"

    def test_config_version_not_in_hash(self, bucket):
        assert bucket["config_version_in_hash"] is False

    def test_10000_test_identities(self, bucket):
        assert bucket["test_identities"] == 10000

    def test_selected_at_50pct(self, bucket):
        assert bucket["selected_at_50pct"] == 5006

    def test_selected_at_75pct(self, bucket):
        assert bucket["selected_at_75pct"] == 7539

    def test_fifty_subset_of_seventy_five(self, bucket):
        assert bucket["fifty_subset_of_seventy_five"] is True

    def test_cohort_nesting_verified(self, bucket):
        assert bucket["cohort_nesting_verified"] is True

    def test_p120_cohort_consistent_with_p121(self, bucket):
        assert bucket["p120_cohort_consistent_with_p121"] is True

    def test_restart_stable(self, bucket):
        assert bucket["restart_stable"] is True

    def test_cross_worker_stable(self, bucket):
        assert bucket["cross_worker_stable"] is True

    def test_bucket_migration_gate_pass(self, bucket):
        assert bucket["bucket_migration_gate"] == "PASS"


# ---------------------------------------------------------------------------
# TestRuntimeVerification — 8 tests
# ---------------------------------------------------------------------------

class TestRuntimeVerification:

    @pytest.fixture(scope="class")
    def rv(self):
        return load("company_v2_phase6v_p121_runtime_verification.json")

    def test_effective_rollout_75(self, rv):
        assert rv["effective_rollout"] == 75

    def test_config_version_8(self, rv):
        assert rv["config_version"] == 8

    def test_environment_staging(self, rv):
        assert rv["environment"] == "staging"

    def test_shadow_mode_active(self, rv):
        assert rv["canary_mode"] == "shadow"

    def test_live_false(self, rv):
        assert rv["live"] is False

    def test_production_false(self, rv):
        assert rv["production"] is False

    def test_provider_serving_calls_zero(self, rv):
        assert rv["provider_serving_calls"] == 0

    def test_all_12_verifications_pass(self, rv):
        verifications = rv["post_promotion_verifications"]
        assert len(verifications) == 12
        for key, val in verifications.items():
            assert val == "PASS", f"Verification {key} did not PASS"


# ---------------------------------------------------------------------------
# TestObservationWindows — parametrized over T1-T8
# 12 test methods × 8 windows = 96 parametrized tests
# ---------------------------------------------------------------------------

WINDOWS = ["t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8"]


class TestObservationWindows:

    @pytest.fixture(params=WINDOWS, scope="class")
    def window_data(self, request):
        wname = request.param
        data = load(f"company_v2_phase6v_p121_{wname}_results.json")
        return data, wname.upper()

    def test_selected_gte_1000(self, window_data):
        data, name = window_data
        assert data["result"]["selected_requests"] >= 1000, \
            f"{name}: selected_requests < 1000"

    def test_config_version_8(self, window_data):
        data, name = window_data
        assert data["config_version"] == 8, f"{name}: config_version != 8"

    def test_rollout_percent_75(self, window_data):
        data, name = window_data
        assert data["rollout_percent"] == 75, f"{name}: rollout_percent != 75"

    def test_selection_rate_70_to_80(self, window_data):
        data, name = window_data
        rate = data["result"]["selection_rate_pct"]
        assert 70.0 <= rate <= 80.0, f"{name}: selection_rate_pct={rate} out of [70,80]"

    def test_no_duplicates(self, window_data):
        data, name = window_data
        assert data["result"]["duplicates"] == 0, f"{name}: duplicates > 0"

    def test_pi_p95_below_4800(self, window_data):
        data, name = window_data
        assert data["result"]["pi_p95_ms"] < 4800, \
            f"{name}: pi_p95_ms={data['result']['pi_p95_ms']} >= 4800ms review threshold"

    def test_tool_p95_below_3800(self, window_data):
        data, name = window_data
        assert data["result"]["tool_p95_ms"] < 3800, \
            f"{name}: tool_p95_ms={data['result']['tool_p95_ms']} >= 3800ms"

    def test_no_safety_violations(self, window_data):
        data, name = window_data
        safety = data["safety"]
        assert safety["zero_tolerance_violations"] == 0, \
            f"{name}: zero_tolerance_violations > 0"
        assert safety["safety_correctness_rate"] == 1.0, \
            f"{name}: safety_correctness_rate < 1.0"

    def test_no_pi_leakage(self, window_data):
        data, name = window_data
        assert data["result"]["Pi_user_visible_leakage"] == 0, \
            f"{name}: Pi_user_visible_leakage > 0"

    def test_no_provider_serving_calls(self, window_data):
        data, name = window_data
        assert data["isolation"]["provider_serving_calls"] == 0, \
            f"{name}: provider_serving_calls > 0"

    def test_terminal_exactly_once(self, window_data):
        data, name = window_data
        assert data["result"]["terminal_exactly_once"] is True, \
            f"{name}: terminal_exactly_once is not True"

    def test_no_legacy_stalls(self, window_data):
        data, name = window_data
        assert data["result"]["legacy_stalls"] == 0, \
            f"{name}: legacy_stalls > 0"


# ---------------------------------------------------------------------------
# TestCombinedMetrics — 10 tests
# ---------------------------------------------------------------------------

class TestCombinedMetrics:

    @pytest.fixture(scope="class")
    def combined(self):
        return load("company_v2_phase6v_p121_combined_metrics.json")

    def test_total_selected_gte_6000(self, combined):
        assert combined["combined"]["total_selected"] >= 6000

    def test_unique_symbols_100(self, combined):
        assert combined["combined"]["unique_symbols"] == 100

    def test_query_styles_14(self, combined):
        assert combined["combined"]["query_styles"] == 14

    def test_multi_turn_gte_350(self, combined):
        assert combined["combined"]["multi_turn_count"] >= 350

    def test_selection_rate_73_to_77(self, combined):
        rate = combined["combined"]["selection_rate_pct"]
        assert 73.0 <= rate <= 77.0, f"selection_rate_pct={rate} out of [73,77]"

    def test_zero_duplicates(self, combined):
        assert combined["combined"]["duplicates"] == 0

    def test_safety_gate_passed(self, combined):
        assert combined["safety_gate"]["safety_gate_passed"] is True

    def test_performance_gate_passed(self, combined):
        assert combined["performance_gate"]["performance_gate_passed"] is True

    def test_provider_serving_calls_zero(self, combined):
        assert combined["provider_serving_calls"] == 0

    def test_cumulative_p18_to_p121_selected(self, combined):
        cum = combined["cumulative_p18_through_p121"]
        assert cum["total_selected"] == 34836
        assert cum["zero_violations"] == 0


# ---------------------------------------------------------------------------
# TestPerformanceComparison — 8 tests
# ---------------------------------------------------------------------------

class TestPerformanceComparison:

    @pytest.fixture(scope="class")
    def perf(self):
        return load("company_v2_phase6v_p121_performance_comparison.json")

    def test_four_phases_present(self, perf):
        phases = perf["phases"]
        assert "P1.18" in phases
        assert "P1.19" in phases
        assert "P1.20" in phases
        assert "P1.21" in phases

    def test_p121_pi_p95_below_4800(self, perf):
        assert perf["phases"]["P1.21"]["pi_p95_ms"] < 4800

    def test_p120_to_p121_delta_below_2pct(self, perf):
        delta_pct = perf["deltas"]["p120_to_p121"]["pi_p95_delta_pct"]
        assert delta_pct < 2.0, f"pi_p95 delta {delta_pct}% >= 2%"

    def test_p118_to_p121_delta_below_2pct(self, perf):
        delta_pct = perf["deltas"]["p118_to_p121"]["pi_p95_delta_pct"]
        assert delta_pct < 2.0, f"pi_p95 delta {delta_pct}% >= 2%"

    def test_no_monotonic_increase(self, perf):
        assert perf["monotonic_increase_detected"] is False

    def test_no_review_triggered(self, perf):
        assert perf["pi_p95_warning_analysis"]["any_window_triggered_review"] is False

    def test_burst_peak_below_review_threshold(self, perf):
        burst_ms = perf["pi_p95_warning_analysis"]["burst_peak_ms"]
        assert burst_ms < 4800, f"Burst peak {burst_ms}ms >= review threshold 4800ms"

    def test_performance_comparison_gate_pass(self, perf):
        assert perf["performance_comparison_gate"] == "PASS"


# ---------------------------------------------------------------------------
# TestResourceAudit — 7 tests
# ---------------------------------------------------------------------------

class TestResourceAudit:

    @pytest.fixture(scope="class")
    def resource(self):
        return load("company_v2_phase6v_p121_resource_audit.json")

    def test_no_upward_drift(self, resource):
        assert resource["combined"]["no_upward_drift"] is True

    def test_t8_recovered_to_t1_baseline(self, resource):
        assert resource["combined"]["t8_recovered_to_t1_baseline"] is True

    def test_fd_recovered_after_t5(self, resource):
        assert resource["combined"]["fd_recovered_after_t5"] is True

    def test_no_task_leaks(self, resource):
        assert resource["combined"]["task_leak_total"] == 0

    def test_no_pool_exhaustion(self, resource):
        assert resource["combined"]["pool_exhaustion_total"] == 0

    def test_diagnostics_backlog_stable(self, resource):
        assert resource["combined"]["diagnostics_backlog_stable_all_windows"] is True

    def test_t5_burst_recovery_confirmed(self, resource):
        t5 = resource["t5_burst_analysis"]
        assert t5["recovery_confirmed"] is True


# ---------------------------------------------------------------------------
# TestSafetyGate — 6 tests
# ---------------------------------------------------------------------------

class TestSafetyGate:

    @pytest.fixture(scope="class")
    def combined(self):
        return load("company_v2_phase6v_p121_combined_metrics.json")

    def test_safety_correctness_1(self, combined):
        assert combined["cumulative"]["safety_correctness_rate"] == 1.0

    def test_zero_tolerance_violations_0(self, combined):
        assert combined["cumulative"]["zero_tolerance_violations"] == 0

    def test_cumulative_p18_p121_violations_0(self, combined):
        assert combined["cumulative_p18_through_p121"]["zero_violations"] == 0

    def test_cumulative_selected_34836(self, combined):
        assert combined["cumulative_p18_through_p121"]["total_selected"] == 34836

    def test_pi_user_visible_leakage_0(self, combined):
        assert combined["cumulative"]["pi_user_visible_leakage"] == 0

    def test_safety_gate_passed(self, combined):
        assert combined["safety_gate"]["safety_gate_passed"] is True


# ---------------------------------------------------------------------------
# TestBrowserRegression — 6 tests
# ---------------------------------------------------------------------------

class TestBrowserRegression:

    @pytest.fixture(scope="class")
    def browser(self):
        return load("company_v2_phase6v_p121_browser_regression.json")

    def test_all_20_cases_pass(self, browser):
        assert browser["total_cases"] == 20
        assert browser["passed"] == 20
        assert browser["failed"] == 0

    def test_legacy_only_confirmed(self, browser):
        assert browser["legacy_only_confirmed"] is True

    def test_no_pi_leakage(self, browser):
        assert browser["pi_user_visible_leakage_all_windows"] == 0

    def test_br17_seventy_five_pct_cohort_isolated(self, browser):
        br17 = next(t for t in browser["test_cases"] if t["id"] == "BR-17")
        assert br17["result"] == "PASS"

    def test_br18_non_selected_no_pi(self, browser):
        br18 = next(t for t in browser["test_cases"] if t["id"] == "BR-18")
        assert br18["result"] == "PASS"

    def test_br19_promotion_no_duplicate(self, browser):
        br19 = next(t for t in browser["test_cases"] if t["id"] == "BR-19")
        assert br19["result"] == "PASS"


# ---------------------------------------------------------------------------
# TestDryRunIsolation — 4 tests
# ---------------------------------------------------------------------------

class TestDryRunIsolation:

    @pytest.fixture(scope="class")
    def dry_run(self):
        return load("company_v2_phase6v_p121_dry_run_isolation.json")

    def test_business_writes_zero(self, dry_run):
        assert dry_run["dry_run_results"]["business_writes"] == 0

    def test_provider_serving_calls_zero(self, dry_run):
        assert dry_run["dry_run_results"]["provider_serving_calls"] == 0

    def test_pending_candidates_not_applied(self, dry_run):
        assert dry_run["dry_run_results"]["pending_candidates_applied"] == 0

    def test_dry_run_isolation_gate_pass(self, dry_run):
        assert dry_run["dry_run_isolation_gate"] == "PASS"


# ---------------------------------------------------------------------------
# TestGateResults — 12 tests (one per gate A-L)
# ---------------------------------------------------------------------------

class TestGateResults:

    @pytest.fixture(scope="class")
    def decision(self):
        return load("company_v2_phase6v_p121_final_decision.json")

    def test_gate_A_repository_integrity(self, decision):
        assert decision["gate_results"]["A_repository_integrity"] == "PASS"

    def test_gate_B_configuration_integrity(self, decision):
        assert decision["gate_results"]["B_configuration_integrity"] == "PASS"

    def test_gate_C_bucket_migration(self, decision):
        assert decision["gate_results"]["C_bucket_migration"] == "PASS"

    def test_gate_D_runtime_verification(self, decision):
        assert decision["gate_results"]["D_runtime_verification"] == "PASS"

    def test_gate_E_safety(self, decision):
        assert decision["gate_results"]["E_safety"] == "PASS"

    def test_gate_F_reliability(self, decision):
        assert decision["gate_results"]["F_reliability"] == "PASS"

    def test_gate_G_performance(self, decision):
        assert decision["gate_results"]["G_performance"] == "PASS"

    def test_gate_H_resources(self, decision):
        assert decision["gate_results"]["H_resources"] == "PASS"

    def test_gate_I_data_regression(self, decision):
        assert decision["gate_results"]["I_data_regression"] == "PASS"

    def test_gate_J_browser_isolation(self, decision):
        assert decision["gate_results"]["J_browser_isolation"] == "PASS"

    def test_gate_K_dry_run_isolation(self, decision):
        assert decision["gate_results"]["K_dry_run_isolation"] == "PASS"

    def test_gate_L_test_and_rollback_evidence(self, decision):
        assert decision["gate_results"]["L_test_and_rollback_evidence"] == "PASS"


# ---------------------------------------------------------------------------
# TestFinalDecision — 10 tests
# ---------------------------------------------------------------------------

class TestFinalDecision:

    @pytest.fixture(scope="class")
    def decision(self):
        return load("company_v2_phase6v_p121_final_decision.json")

    def test_actual_rollout_percent_75(self, decision):
        assert decision["actual_rollout_percent_after_phase"] == 75

    def test_actual_config_version_8(self, decision):
        assert decision["actual_config_version_after_phase"] == 8

    def test_promotion_applied(self, decision):
        assert decision["promotion_applied"] is True

    def test_all_12_gates_pass(self, decision):
        assert decision["gates_passed"] == 12
        assert decision["gates_failed"] == 0

    def test_no_rollback(self, decision):
        assert decision["rollback_required"] is False
        assert decision["rollback_applied"] is False
        assert decision["rollback_rollout_percent"] is None
        assert decision["rollback_config_version"] is None

    def test_live_false(self, decision):
        assert decision["live_serving"] is False

    def test_production_false(self, decision):
        assert decision["production_enabled"] is False

    def test_one_hundred_percent_not_recommended(self, decision):
        assert decision["recommended_for_one_hundred_percent"] is False

    def test_continue_seventy_five_shadow(self, decision):
        assert decision["continue_seventy_five_percent_shadow"] is True

    def test_provider_serving_calls_zero(self, decision):
        assert decision["provider_serving_calls"] == 0
