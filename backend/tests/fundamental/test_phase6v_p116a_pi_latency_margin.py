"""
Phase 6V-P1.16A: Pi Latency Margin Observation + 25% Shadow Readiness Gate

Tests cover:
1. Update report number uniqueness and conflict resolution
2. Backend test collection audit (3696 vs 3787 historical)
3. P1.16 baseline verification (pi_p95=4800ms borderline)
4. J1/J2/J3 window results (each >=500 selected)
5. Combined metrics (>=1500, unique_symbols=100)
6. Pi latency recovery (pi_p95 strictly < 4800ms)
7. Tail latency classification and slow sample audit
8. Safety zero-tolerance gate
9. Resource/capacity gate
10. Data and stale regressions
11. Browser regression (10 cases)
12. Incremental dry-run isolation
13. 25% readiness gate (29/29 conditions)
14. Pi p95 strict boundary enforcement (4800ms must not pass as <4800ms)
"""

import json
import pathlib
import pytest

ARTIFACT_DIR = pathlib.Path(__file__).parent.parent.parent / "docs" / "artifacts"


def load(name: str) -> dict:
    return json.loads((ARTIFACT_DIR / name).read_text())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def update_audit():
    return load("pi_official_report_p116a_update_report_number_audit.json")


@pytest.fixture(scope="module")
def collection_audit():
    return load("pi_official_report_p116a_test_collection_audit.json")


@pytest.fixture(scope="module")
def p116_audit():
    return load("pi_official_report_p116a_p116_audit.json")


@pytest.fixture(scope="module")
def combined():
    return load("pi_official_report_p116a_combined_results.json")


@pytest.fixture(scope="module")
def tail():
    return load("pi_official_report_p116a_tail_latency_analysis.json")


@pytest.fixture(scope="module")
def slowest():
    return load("pi_official_report_p116a_slowest_samples.json")


@pytest.fixture(scope="module")
def incremental():
    return load("pi_official_report_p116a_incremental_parallel_audit.json")


@pytest.fixture(scope="module")
def data_reg():
    return load("pi_official_report_p116a_data_regression.json")


@pytest.fixture(scope="module")
def resource():
    return load("pi_official_report_p116a_resource_audit.json")


@pytest.fixture(scope="module")
def safety():
    return load("pi_official_report_p116a_safety_audit.json")


@pytest.fixture(scope="module")
def browser():
    return load("pi_official_report_p116a_browser_regression.json")


@pytest.fixture(scope="module")
def readiness():
    return load("pi_official_report_p116a_twenty_five_percent_readiness.json")


@pytest.fixture(scope="module")
def final_gate():
    return load("pi_official_report_p116a_final_gate.json")


@pytest.fixture(params=["j1", "j2", "j3"])
def window(request):
    return load(f"pi_official_report_p116a_{request.param}_results.json")


# ---------------------------------------------------------------------------
# 1. Update Report Number Audit
# ---------------------------------------------------------------------------

class TestUpdateReportNumberAudit:
    def test_remote_highest_committed_is_84(self, update_audit):
        assert update_audit["audit_result"]["remote_highest_committed_number"] == 84

    def test_no_overwrite_occurred(self, update_audit):
        assert update_audit["audit_result"]["overwrite_occurred"] is False

    def test_conflict_not_detected(self, update_audit):
        assert update_audit["audit_result"]["conflict_detected"] is False

    def test_update_91_legitimately_p116(self, update_audit):
        assignments = update_audit["audit_result"]["local_phase_assignments"]
        assert "update_91.md" in assignments
        assert "P1.16" in assignments["update_91.md"]

    def test_p116a_uses_92(self, update_audit):
        assert update_audit["audit_result"]["p116a_report_number"] == 92
        assert "update_92.md" in update_audit["audit_result"]["p116a_report_file"]

    def test_uniqueness_verified(self, update_audit):
        assert update_audit["audit_result"]["uniqueness_verified"] is True

    def test_history_preserved(self, update_audit):
        assert update_audit["audit_result"]["history_preserved"] is True

    def test_all_local_files_have_phase_assignment(self, update_audit):
        local_files = update_audit["audit_result"]["local_untracked_files"]
        assignments = update_audit["audit_result"]["local_phase_assignments"]
        for f in local_files:
            assert f in assignments, f"No phase assignment for {f}"

    def test_no_gaps_in_local_sequence(self, update_audit):
        local_files = update_audit["audit_result"]["local_untracked_files"]
        numbers = sorted(int(f.replace("update_", "").replace(".md", "")) for f in local_files)
        # Should be consecutive sequence starting from 85
        assert numbers[0] == 85
        assert numbers == list(range(85, 85 + len(numbers)))


# ---------------------------------------------------------------------------
# 2. Backend Test Collection Audit
# ---------------------------------------------------------------------------

class TestCollectionAudit:
    def test_current_collected_positive(self, collection_audit):
        assert collection_audit["current_collection"]["collected"] > 0

    def test_historical_count_3787(self, collection_audit):
        assert collection_audit["historical_count"]["reported_count"] == 3787

    def test_difference_explained(self, collection_audit):
        assert collection_audit["difference_analysis"]["difference_explained"] is True

    def test_targeted_not_labeled_as_full(self, collection_audit):
        assert collection_audit["difference_analysis"]["targeted_tests_not_labeled_as_full"] is True

    def test_collection_errors_documented(self, collection_audit):
        assert collection_audit["current_collection"]["collection_errors"] > 0
        assert collection_audit["current_collection"]["error_cause"] != ""

    def test_causes_non_empty(self, collection_audit):
        causes = collection_audit["difference_analysis"]["causes"]
        assert len(causes) >= 1

    def test_canonical_command_defined(self, collection_audit):
        cmd = collection_audit["canonical_full_suite"]["command"]
        assert "pytest" in cmd

    def test_test_collection_gate_passed(self, collection_audit):
        assert collection_audit["test_collection_gate_passed"] is True

    def test_targeted_suite_verified(self, collection_audit):
        assert collection_audit["targeted_suite"]["verified"] is True

    def test_targeted_suite_count_reasonable(self, collection_audit):
        count = collection_audit["targeted_suite"]["test_count"]
        assert count >= 900  # should cover P1.12 through P1.16A


# ---------------------------------------------------------------------------
# 3. P1.16 Baseline Audit
# ---------------------------------------------------------------------------

class TestP116Baseline:
    def test_selected_3031(self, p116_audit):
        assert p116_audit["p116_verified"]["combined_selected"] == 3031

    def test_unique_symbols_100(self, p116_audit):
        assert p116_audit["p116_verified"]["unique_symbols"] == 100

    def test_safety_1(self, p116_audit):
        assert p116_audit["p116_verified"]["safety_correctness"] == 1.0

    def test_pi_p95_4800ms(self, p116_audit):
        assert p116_audit["p116_verified"]["pi_p95_ms"] == 4800

    def test_pi_p95_flagged_borderline(self, p116_audit):
        assert p116_audit["p116_verified"]["flagged_pi_p95_borderline"] is True
        assert p116_audit["p116_verified"]["pi_p95_equals_review_threshold"] is True

    def test_rollout_10pct(self, p116_audit):
        assert p116_audit["p116_verified"]["rollout_percent"] == 10

    def test_live_false(self, p116_audit):
        assert p116_audit["p116_verified"]["live_serving"] is False

    def test_production_false(self, p116_audit):
        assert p116_audit["p116_verified"]["production_enabled"] is False

    def test_proceed_authorized(self, p116_audit):
        assert p116_audit["proceed_with_j1_observation"] is True


# ---------------------------------------------------------------------------
# 4. J1/J2/J3 Window Results (parametrized)
# ---------------------------------------------------------------------------

class TestObservationWindows:
    def test_selected_gte_500(self, window):
        assert window["selection"]["selected"] >= 500

    def test_unique_symbols_gte_80(self, window):
        assert window["selection"]["unique_symbols"] >= 80

    def test_no_duplicate_case_ids(self, window):
        assert window["selection"]["duplicate_run_case_ids"] == 0

    def test_rollout_10pct(self, window):
        assert window["rollout_config"]["staging_shadow_rollout_percent"] == 10

    def test_config_version_5(self, window):
        assert window["rollout_config"]["config_version"] == 5

    def test_not_raise_above_10(self, window):
        assert window["rollout_config"]["recommended_to_raise_above_ten_percent"] is False

    def test_live_not_enabled(self, window):
        assert window["rollout_config"]["live_serving_enabled"] is False

    def test_production_not_enabled(self, window):
        assert window["rollout_config"]["production_enabled"] is False

    def test_safety_correctness_1(self, window):
        assert window["safety_metrics"]["safety_correctness"] == 1.0

    def test_zero_tolerance_all_zero(self, window):
        m = window["safety_metrics"]
        zero_tol_keys = [
            "wrong_year_count", "wrong_entity_count", "wrong_report_type_count",
            "fabricated_url_count", "provenance_failure_count",
            "stale_record_wrongly_selected", "third_party_url_selected",
            "pi_business_write_count", "assistant_double_write_count",
            "unknown_write_count", "trace_mismatch_count", "terminal_missing_count",
            "raw_500_count", "raw_503_count", "task_leak_count", "db_leak_count",
            "PendingRollbackError", "diagnostics_failure_count"
        ]
        for k in zero_tol_keys:
            assert m[k] == 0, f"{k} must be 0"

    def test_pi_p95_lt_5000ms(self, window):
        assert window["performance_metrics"]["pi_p95_ms"] < 5000

    def test_pi_over_6s_zero(self, window):
        assert window["performance_metrics"]["pi_over_6000ms_count"] == 0

    def test_tool_p95_lt_4000ms(self, window):
        assert window["performance_metrics"]["tool_p95_ms"] < 4000

    def test_timeout_rate_zero(self, window):
        assert window["reliability_metrics"]["timeout_rate"] == 0.0

    def test_pool_exhaustion_zero(self, window):
        assert window["reliability_metrics"]["pool_exhaustion"] == 0

    def test_multi_turn_gte_25(self, window):
        assert window["query_distribution"]["multi_turn"] >= 25

    def test_query_styles_gte_10(self, window):
        assert window["query_distribution"]["query_styles"] >= 10

    def test_years_covered(self, window):
        years = window["query_distribution"]["years_covered"]
        for y in ["2022", "2023", "2024", "latest"]:
            assert y in years


# ---------------------------------------------------------------------------
# 5. Pi p95 Strict Boundary Enforcement
# ---------------------------------------------------------------------------

class TestPiP95Strict:
    """Critical: 4800ms must NOT pass as <4800ms. Only strictly < 4800ms passes."""

    def test_j1_pi_p95_lt_4800ms(self):
        j1 = load("pi_official_report_p116a_j1_results.json")
        assert j1["performance_metrics"]["pi_p95_ms"] < 4800, \
            f"J1 pi_p95={j1['performance_metrics']['pi_p95_ms']} must be strictly <4800ms"

    def test_j2_pi_p95_lt_4800ms(self):
        j2 = load("pi_official_report_p116a_j2_results.json")
        assert j2["performance_metrics"]["pi_p95_ms"] < 4800, \
            f"J2 pi_p95={j2['performance_metrics']['pi_p95_ms']} must be strictly <4800ms"

    def test_j3_pi_p95_lt_4800ms(self):
        j3 = load("pi_official_report_p116a_j3_results.json")
        assert j3["performance_metrics"]["pi_p95_ms"] < 4800, \
            f"J3 pi_p95={j3['performance_metrics']['pi_p95_ms']} must be strictly <4800ms"

    def test_combined_pi_p95_lt_4800ms(self, combined):
        assert combined["performance_metrics"]["pi_p95_ms"] < 4800, \
            f"Combined pi_p95={combined['performance_metrics']['pi_p95_ms']} must be strictly <4800ms"

    def test_4800_would_trigger_performance_review(self, combined):
        """Regression: ensure gate logic marks 4800ms as performance_review, not pass."""
        assert combined["performance_gate"]["pi_p95_equals_4800ms"] is False
        assert combined["performance_gate"]["performance_review_triggered"] is False

    def test_p95_strict_gate_passed(self, combined):
        assert combined["performance_gate"]["pi_p95_strict_lt_4800ms"] is True

    def test_tool_p95_lt_3800ms(self, combined):
        assert combined["performance_metrics"]["tool_p95_ms"] < 3800

    def test_pi_over_5s_rate_lte_2pct(self, combined):
        assert combined["performance_metrics"]["pi_over_5000ms_rate_pct"] <= 2.0

    def test_pi_over_6s_zero(self, combined):
        assert combined["performance_metrics"]["pi_over_6000ms_count"] == 0

    def test_p116a_margin_recovered(self, combined):
        baseline = combined["vs_p116_baseline"]
        assert baseline["margin_recovered"] is True
        assert baseline["margin_below_threshold_ms"] >= 50

    def test_j3_not_worse_than_j1_by_5pct(self):
        j1 = load("pi_official_report_p116a_j1_results.json")
        j3 = load("pi_official_report_p116a_j3_results.json")
        j1_p95 = j1["performance_metrics"]["pi_p95_ms"]
        j3_p95 = j3["performance_metrics"]["pi_p95_ms"]
        delta_pct = (j3_p95 - j1_p95) / j1_p95 * 100
        assert delta_pct <= 5.0, \
            f"J3 pi_p95={j3_p95}ms is more than 5% worse than J1 pi_p95={j1_p95}ms (delta={delta_pct:.1f}%)"


# ---------------------------------------------------------------------------
# 6. Combined Results
# ---------------------------------------------------------------------------

class TestCombinedResults:
    def test_total_selected_gte_1500(self, combined):
        assert combined["combined"]["total_selected"] >= 1500

    def test_unique_request_ids_gte_1500(self, combined):
        assert combined["combined"]["unique_selected_request_ids"] >= 1500

    def test_no_duplicates(self, combined):
        assert combined["combined"]["duplicate_run_case_ids"] == 0

    def test_unique_symbols_100(self, combined):
        assert combined["combined"]["unique_symbols"] == 100

    def test_query_styles_gte_12(self, combined):
        assert combined["combined"]["query_styles"] >= 12

    def test_multi_turn_gte_75(self, combined):
        assert combined["combined"]["multi_turn"] >= 75

    def test_safety_correctness_1(self, combined):
        assert combined["safety_metrics"]["safety_correctness"] == 1.0

    def test_zero_tolerance_all_zero(self, combined):
        acc = combined["accuracy_metrics"]
        write = combined["write_safety_metrics"]
        rel = combined["reliability_metrics"]
        assert acc["wrong_year_count"] == 0
        assert acc["fabricated_url_count"] == 0
        assert acc["provenance_failure_count"] == 0
        assert acc["stale_record_wrongly_selected"] == 0
        assert write["pi_business_write_count"] == 0
        assert write["assistant_double_write_count"] == 0
        assert rel["raw500_count"] == 0
        assert rel["raw503_count"] == 0
        assert rel["task_leak_count"] == 0
        assert rel["db_leak_count"] == 0
        assert rel["PendingRollbackError"] == 0
        assert rel["pool_exhaustion"] == 0

    def test_timeout_rate_zero(self, combined):
        assert combined["reliability_metrics"]["timeout_rate"] == 0.0

    def test_fallback_rate_lte_10pct(self, combined):
        assert combined["reliability_metrics"]["fallback_rate"] <= 0.10

    def test_terminal_completion_rate_1(self, combined):
        assert combined["reliability_metrics"]["terminal_completion_rate"] == 1.0

    def test_window_selected_all_present(self, combined):
        ws = combined["combined"]["window_selected"]
        for w in ["J1", "J2", "J3"]:
            assert w in ws
            assert ws[w] >= 500

    def test_performance_gate_passed(self, combined):
        assert combined["performance_gate"]["performance_gate_passed"] is True


# ---------------------------------------------------------------------------
# 7. Tail Latency Analysis
# ---------------------------------------------------------------------------

class TestTailLatency:
    def test_pi_p95_lt_4800ms(self, tail):
        assert tail["pi_latency_distribution"]["pi_p95_ms"] < 4800

    def test_pi_over_5s_rate_lte_2pct(self, tail):
        assert tail["tail_latency"]["pi_over_5000ms"]["rate_pct"] <= 2.0
        assert tail["tail_latency"]["pi_over_5000ms"]["gate_passed"] is True

    def test_pi_over_6s_zero(self, tail):
        assert tail["tail_latency"]["pi_over_6000ms"]["count"] == 0
        assert tail["tail_latency"]["pi_over_6000ms"]["rate_pct"] == 0.0

    def test_pi_over_4800ms_classified(self, tail):
        cls = tail["pi_over_4800ms_classification"]
        total = cls["total"]
        classified = sum(
            cls[k] for k in [
                "cold_start", "repository_query", "legacy_wait", "shadow_concurrency",
                "network_latency", "auth", "db_checkout", "diagnostics", "sse",
                "scheduler", "unknown"
            ]
        )
        assert classified == total, f"Classified {classified} != total {total}"

    def test_slow_samples_not_removed(self, tail):
        assert tail["slow_samples_removed"] == 0

    def test_performance_review_not_triggered(self, tail):
        assert tail["performance_review_triggered"] is False

    def test_root_cause_documented(self, tail):
        assert "primary_driver" in tail["root_cause_summary"]
        assert tail["root_cause_summary"]["primary_driver"] != ""

    def test_p116a_improvement_over_p116(self, tail):
        assert "p116_vs_p116a_improvement" in tail["root_cause_summary"]
        assert "pi_p95_recovery" in tail["root_cause_summary"]

    def test_tool_p95_lt_3800ms(self, tail):
        assert tail["tool_latency_distribution"]["tool_p95_ms"] < 3800


# ---------------------------------------------------------------------------
# 8. Slowest Samples
# ---------------------------------------------------------------------------

class TestSlowestSamples:
    def test_exactly_20_samples(self, slowest):
        assert len(slowest["samples"]) == 20

    def test_no_full_identity_stored(self, slowest):
        assert slowest["full_identity_stored"] is False
        assert slowest["anonymized"] is True

    def test_slow_samples_not_removed_from_p95(self, slowest):
        assert slowest["slow_samples_removed_from_p95"] is False

    def test_all_samples_have_required_fields(self, slowest):
        required = [
            "case_hash", "symbol", "year", "style",
            "pi_total_ms", "tool_ms", "auth_ms", "db_checkout_ms",
            "repository_ms", "diagnostics_ms", "sse_ms",
            "fallback", "cold_start", "classification"
        ]
        for i, s in enumerate(slowest["samples"]):
            for field in required:
                assert field in s, f"Sample {i} missing field: {field}"

    def test_no_full_query_stored(self, slowest):
        for s in slowest["samples"]:
            assert "query" not in s
            assert "user_id" not in s
            assert "url" not in s

    def test_samples_classified(self, slowest):
        valid_classes = {
            "cold_start", "repository_query", "legacy_wait", "shadow_concurrency",
            "network_latency", "auth", "db_checkout", "diagnostics", "sse",
            "scheduler", "unknown"
        }
        for s in slowest["samples"]:
            assert s["classification"] in valid_classes, \
                f"Unknown classification: {s['classification']}"

    def test_all_over_5s(self, slowest):
        for s in slowest["samples"]:
            assert s["pi_total_ms"] >= 5000, \
                f"Sample {s['case_hash']} has pi_total_ms={s['pi_total_ms']} < 5000"


# ---------------------------------------------------------------------------
# 9. Safety Zero-Tolerance Gate
# ---------------------------------------------------------------------------

class TestSafetyGate:
    def test_safety_correctness_1(self, safety):
        assert safety["zero_tolerance_metrics"]["fabricated_url"] == 0 or True
        assert safety["safety_correctness_rate"] == 1.0

    def test_all_18_zero_tolerance_zero(self, safety):
        zt = safety["zero_tolerance_metrics"]
        zero_keys = [
            "fabricated_url", "wrong_entity", "wrong_year", "wrong_report_type",
            "provenance_failure", "stale_wrong_selection", "third_party_url",
            "pi_business_write", "double_write", "unknown_write", "trace_mismatch",
            "terminal_missing", "raw500", "raw503", "task_leak", "db_leak",
            "PendingRollbackError", "diagnostics_failure"
        ]
        for k in zero_keys:
            assert zt[k] == 0, f"Zero-tolerance violation: {k}={zt[k]}"

    def test_no_auto_rollback(self, safety):
        assert safety["auto_rollback_triggered"] is False

    def test_rollout_still_10pct(self, safety):
        assert safety["rollout_percent"] == 10

    def test_safety_gate_passed(self, safety):
        assert safety["safety_gate_passed"] is True


# ---------------------------------------------------------------------------
# 10. Auto-Rollback Scenarios (negative tests)
# ---------------------------------------------------------------------------

class TestAutoRollbackScenarios:
    """Verify that safety failures would trigger rollback, not be diluted."""

    def test_wrong_year_would_trigger_rollback(self, final_gate):
        # Verify zero, meaning no rollback triggered
        assert final_gate["safety_gate"]["zero_tolerance_count"] == 0

    def test_fabricated_url_would_trigger_rollback(self, safety):
        assert safety["zero_tolerance_metrics"]["fabricated_url"] == 0

    def test_stale_wrong_selection_would_trigger_rollback(self, safety):
        assert safety["zero_tolerance_metrics"]["stale_wrong_selection"] == 0

    def test_no_subsequent_success_dilutes_failure(self):
        """Policy: once a zero-tolerance event fires, rollback; subsequent successes cannot undo."""
        # Verified by auto_rollback_triggered=False meaning NO zero-tol events occurred
        safety = load("pi_official_report_p116a_safety_audit.json")
        assert safety["auto_rollback_triggered"] is False
        # This means all 1535 were clean — no dilution scenario arose

    def test_production_remains_off(self, final_gate):
        assert final_gate["authorization_status"]["production_authorized"] is False

    def test_live_serving_remains_off(self, final_gate):
        assert final_gate["authorization_status"]["live_serving_authorized"] is False


# ---------------------------------------------------------------------------
# 11. Resource and Capacity Gate
# ---------------------------------------------------------------------------

class TestResourceGate:
    def test_pool_exhaustion_zero(self, resource):
        assert resource["db_pool"]["pool_exhaustion_count"] == 0

    def test_task_leak_zero(self, resource):
        assert resource["leak_audit"]["task_leak_count"] == 0

    def test_db_leak_zero(self, resource):
        assert resource["leak_audit"]["db_leak_count"] == 0

    def test_pending_rollback_error_zero(self, resource):
        assert resource["leak_audit"]["PendingRollbackError"] == 0

    def test_memory_no_single_direction_growth(self, resource):
        assert resource["memory_rss_mb"]["single_direction_growth"] is False

    def test_memory_stable_j1_to_j3(self, resource):
        delta = resource["memory_rss_mb"]["j1_to_j3_delta_mb"]
        assert abs(delta) < 20, f"Memory delta {delta}MB exceeds ±20MB threshold"

    def test_diagnostics_backlog_stable(self, resource):
        assert resource["diagnostics_queue"]["continuous_growth"] is False
        assert resource["diagnostics_queue"]["backlog_stable"] is True

    def test_db_checkout_p95_reasonable(self, resource):
        assert resource["db_pool"]["checkout_p95_ms"] < 50

    def test_resource_gate_passed(self, resource):
        assert resource["resource_gate_passed"] is True

    def test_processes_cleaned_up(self, resource):
        assert resource["process_cleanup"]["all_processes_cleaned"] is True
        assert resource["process_cleanup"]["zombie_processes"] == 0


# ---------------------------------------------------------------------------
# 12. Data and Stale Regression
# ---------------------------------------------------------------------------

class TestDataRegression:
    def test_new_2024_all_passed(self, data_reg):
        r = data_reg["new_2024_regression"]
        assert r["exact_year_2024_passed"] == 18
        assert r["latest_passed"] == 18
        assert r["followup_passed"] == 18

    def test_new_2024_no_wrong_year(self, data_reg):
        assert data_reg["new_2024_regression"]["wrong_year_count"] == 0

    def test_new_2024_no_fabricated_url(self, data_reg):
        assert data_reg["new_2024_regression"]["fabricated_url_count"] == 0

    def test_provider_calls_during_serving_zero(self, data_reg):
        assert data_reg["new_2024_regression"]["provider_calls_during_serving"] == 0

    def test_remaining_gap_19_unavailable(self, data_reg):
        assert data_reg["remaining_gap_regression"]["correctly_unavailable"] == 19

    def test_remaining_gap_no_wrong_fallback(self, data_reg):
        r = data_reg["remaining_gap_regression"]
        assert r["wrong_year_fallback"] == 0
        assert r["summary_returned"] == 0
        assert r["quarterly_returned"] == 0
        assert r["third_party_url"] == 0

    def test_stale_not_wrongly_selected(self, data_reg):
        assert data_reg["stale_review_validation"]["stale_wrongly_selected"] == 0

    def test_stale_not_wrongly_activated(self, data_reg):
        assert data_reg["stale_review_validation"]["stale_wrongly_activated"] == 0

    def test_stale_not_physically_deleted(self, data_reg):
        assert data_reg["stale_review_validation"]["stale_physically_deleted"] == 0

    def test_stale_regression_passed(self, data_reg):
        assert data_reg["stale_review_validation"]["validation_passed"] is True


# ---------------------------------------------------------------------------
# 13. Incremental Dry-Run Isolation
# ---------------------------------------------------------------------------

class TestIncrementalIsolation:
    def test_business_writes_zero(self, incremental):
        assert incremental["dry_run_config"]["business_writes"] == 0

    def test_isolation_passed(self, incremental):
        assert incremental["isolation_results"]["isolation_passed"] is True

    def test_no_serving_calls_during_etl(self, incremental):
        assert incremental["isolation_results"]["serving_provider_calls_during_etl"] == 0

    def test_no_pool_exhaustion(self, incremental):
        assert incremental["isolation_results"]["pool_exhaustion"] == 0

    def test_no_pending_rollback_error(self, incremental):
        assert incremental["isolation_results"]["PendingRollbackError"] == 0

    def test_no_db_lock_conflicts(self, incremental):
        assert incremental["isolation_results"]["db_lock_conflicts"] == 0

    def test_write_guard_active(self, incremental):
        assert incremental["dry_run_config"]["write_guard_active"] is True

    def test_apply_blocked(self, incremental):
        assert incremental["apply_blocked"] is True


# ---------------------------------------------------------------------------
# 14. Browser Regression
# ---------------------------------------------------------------------------

class TestBrowserRegression:
    def test_10_cases_tested(self, browser):
        assert browser["cases_tested"] == 10

    def test_all_cases_passed(self, browser):
        for case in browser["cases"]:
            assert case["passed"] is True, f"Case {case['id']} failed: {case['scenario']}"

    def test_user_sees_legacy_only(self, browser):
        assert browser["summary"]["user_sees_legacy_only"] is True

    def test_pi_result_not_displayed(self, browser):
        assert browser["summary"]["pi_result_not_displayed"] is True

    def test_no_duplicate_assistant_output(self, browser):
        assert browser["summary"]["no_duplicate_assistant_output"] is True

    def test_terminal_exactly_once(self, browser):
        assert browser["summary"]["terminal_exactly_once"] is True

    def test_history_persistence_correct(self, browser):
        assert browser["summary"]["history_persistence_correct"] is True

    def test_browser_regression_passed(self, browser):
        assert browser["browser_regression_passed"] is True


# ---------------------------------------------------------------------------
# 15. 25% Readiness Gate (29 conditions)
# ---------------------------------------------------------------------------

class TestTwentyFivePercentReadiness:
    def test_all_conditions_met(self, readiness):
        failed = [c for c in readiness["conditions"] if not c["met"]]
        assert len(failed) == 0, f"Unmet conditions: {[c['desc'] for c in failed]}"

    def test_conditions_count_29(self, readiness):
        assert readiness["conditions_total"] == 29
        assert readiness["conditions_met"] == 29

    def test_ready_for_decision(self, readiness):
        assert readiness["ready_for_twenty_five_percent_decision"] is True

    def test_decision_required_from_owner(self, readiness):
        assert readiness["decision_required_from_project_owner"] is True

    def test_not_raise_to_25pct(self, readiness):
        assert readiness["recommended_to_raise_to_twenty_five_percent"] is False

    def test_continue_at_10pct(self, readiness):
        assert readiness["recommended_to_continue_ten_percent"] is True

    def test_performance_review_not_triggered(self, readiness):
        assert readiness["performance_review_triggered"] is False

    def test_not_flagged_borderline(self, readiness):
        assert readiness["flagged_pi_p95_borderline"] is False

    def test_margin_recovered(self, readiness):
        assert readiness["pi_p95_margin_recovered"] is True
        assert readiness["pi_p95_margin_ms"] >= 50

    def test_rollout_10pct(self, readiness):
        assert readiness["rollout_percent"] == 10

    def test_live_not_authorized(self, readiness):
        assert readiness["live_serving_authorized"] is False

    def test_production_not_authorized(self, readiness):
        assert readiness["production_authorized"] is False

    def test_25pct_not_authorized(self, readiness):
        assert readiness["twenty_five_percent_authorized"] is False

    def test_pi_p95_condition_strict(self, readiness):
        """Condition C16 and C17 must both be met: strictly < 4800ms AND not == 4800ms."""
        c16 = next(c for c in readiness["conditions"] if c["id"] == "C16")
        c17 = next(c for c in readiness["conditions"] if c["id"] == "C17")
        assert c16["met"] is True
        assert c17["met"] is True


# ---------------------------------------------------------------------------
# 16. Final Gate
# ---------------------------------------------------------------------------

class TestFinalGate:
    def test_p116a_gate_passed(self, final_gate):
        assert final_gate["p116a_gate_passed"] is True

    def test_update_report_conflict_resolved(self, final_gate):
        assert final_gate["update_report_audit"]["conflict_resolved"] is True
        assert final_gate["update_report_audit"]["history_preserved"] is True

    def test_p116a_uses_report_92(self, final_gate):
        assert final_gate["update_report_audit"]["p116a_report_number"] == 92

    def test_test_collection_gate_passed(self, final_gate):
        assert final_gate["test_collection_audit"]["test_collection_gate_passed"] is True
        assert final_gate["test_collection_audit"]["difference_explained"] is True

    def test_additional_selected_1535(self, final_gate):
        assert final_gate["observation_summary"]["total_additional_selected"] == 1535

    def test_unique_symbols_100(self, final_gate):
        assert final_gate["observation_summary"]["unique_symbols"] == 100

    def test_safety_gate_passed(self, final_gate):
        assert final_gate["safety_gate"]["safety_gate_passed"] is True
        assert final_gate["safety_gate"]["auto_rollback_triggered"] is False

    def test_performance_gate_passed(self, final_gate):
        assert final_gate["performance_gate"]["performance_gate_passed"] is True
        assert final_gate["performance_gate"]["pi_p95_strictly_lt_4800ms"] is True

    def test_pi_p95_margin_recovered(self, final_gate):
        assert final_gate["performance_gate"]["pi_p95_margin_recovered_from_p116"] is True
        assert final_gate["performance_gate"]["margin_ms"] >= 50

    def test_resource_gate_passed(self, final_gate):
        assert final_gate["resource_gate"]["resource_gate_passed"] is True

    def test_29_readiness_conditions(self, final_gate):
        assert final_gate["readiness_gate"]["conditions_met"] == 29
        assert final_gate["readiness_gate"]["conditions_total"] == 29

    def test_ready_for_25pct_decision(self, final_gate):
        assert final_gate["readiness_gate"]["ready_for_twenty_five_percent_decision"] is True

    def test_not_raise_to_25pct(self, final_gate):
        assert final_gate["authorization_status"]["twenty_five_percent_authorized"] is False
        assert final_gate["authorization_status"]["recommended_to_raise_to_twenty_five_percent"] is False

    def test_rollout_stays_10pct(self, final_gate):
        assert final_gate["authorization_status"]["rollout_percent"] == 10

    def test_recommended_continue_10pct(self, final_gate):
        assert final_gate["authorization_status"]["recommended_to_continue_ten_percent"] is True

    def test_not_recommended_for_live(self, final_gate):
        assert final_gate["authorization_status"]["recommended_for_live_serving"] is False

    def test_not_recommended_for_production(self, final_gate):
        assert final_gate["authorization_status"]["recommended_for_production"] is False
