"""
Phase 6V-P1.16: Sustained 10% Shadow Observation + 25% Readiness Gate
H1-H6 observation windows, tail latency analysis, capacity audit.
"""
import json
import pytest
from pathlib import Path

ARTIFACT_DIR = Path(__file__).parent.parent.parent / "docs" / "artifacts"


def load(name):
    return json.loads((ARTIFACT_DIR / name).read_text())


class TestCollectionAudit:
    @pytest.fixture
    def audit(self):
        return load("pi_official_report_p116_test_collection_audit.json")

    def test_difference_explained(self, audit):
        assert audit["difference_explained"] is True

    def test_targeted_not_full(self, audit):
        assert audit["targeted_tests_not_labeled_as_full"] is True

    def test_full_suite_available(self, audit):
        assert audit["true_full_suite_available"] is True

    def test_collection_gate_passed(self, audit):
        assert audit["collection_audit_gate_passed"] is True

    def test_current_collected_positive(self, audit):
        assert audit["current_collected_count"] > 0

    def test_historical_count(self, audit):
        assert audit["historical_full_count"] == 3787


class TestP115Audit:
    @pytest.fixture
    def audit(self):
        return load("pi_official_report_p116_p115_audit.json")

    def test_rollout_10(self, audit):
        assert audit["current_rollout_percent"] == 10

    def test_baseline_consistent(self, audit):
        assert audit["baseline_consistent"] is True

    def test_proceed(self, audit):
        assert audit["proceed_with_observation"] is True

    def test_p115_safety(self, audit):
        assert audit["p115_safety_correctness"] == 1.0

    def test_p115_zero_tolerance(self, audit):
        assert audit["p115_zero_tolerance_count"] == 0

    def test_p115_production_false(self, audit):
        assert audit["p115_production_enabled"] is False


class TestObservationWindows:
    @pytest.fixture(params=["h1", "h2", "h3", "h4", "h5", "h6"])
    def window(self, request):
        return load(f"pi_official_report_p116_{request.param}_results.json")

    def test_selected_gte_500(self, window):
        assert window["selection"]["selected"] >= 500

    def test_unique_symbols_gte_80(self, window):
        assert window["selection"]["unique_symbols"] >= 80

    def test_query_styles_gte_10(self, window):
        assert window["selection"]["query_styles"] >= 10

    def test_multi_turn_gte_25(self, window):
        assert window["selection"]["multi_turn"] >= 25

    def test_safety_1(self, window):
        assert window["safety_metrics"]["safety_correctness"] == 1.0

    def test_wrong_year_zero(self, window):
        assert window["accuracy_metrics"]["wrong_year_count"] == 0

    def test_fabricated_url_zero(self, window):
        assert window["accuracy_metrics"]["fabricated_url_count"] == 0

    def test_stale_wrong_zero(self, window):
        assert window["accuracy_metrics"]["stale_record_wrongly_selected"] == 0

    def test_pi_write_zero(self, window):
        assert window["write_safety_metrics"]["pi_business_write_count"] == 0

    def test_raw500_zero(self, window):
        assert window["reliability_metrics"]["raw500_count"] == 0

    def test_raw503_zero(self, window):
        assert window["reliability_metrics"]["raw503_count"] == 0

    def test_pool_exhaustion_zero(self, window):
        assert window["reliability_metrics"]["pool_exhaustion"] == 0

    def test_task_leak_zero(self, window):
        assert window["reliability_metrics"]["task_leak_count"] == 0

    def test_tool_p95_lte_4s(self, window):
        assert window["performance_metrics"]["tool_p95_ms"] <= 4000

    def test_pi_p95_lte_5s(self, window):
        assert window["performance_metrics"]["pi_p95_ms"] <= 5000

    def test_pi_over_6s_zero(self, window):
        assert window["performance_metrics"]["pi_over_6000ms_count"] == 0

    def test_slow_samples_not_removed(self, window):
        assert window["performance_metrics"]["slow_samples_removed"] == 0

    def test_rollout_10(self, window):
        assert window["rollout_config"]["staging_shadow_rollout_percent"] == 10

    def test_not_raise_25pct(self, window):
        assert window["rollout_config"]["recommended_to_raise_to_twenty_five_percent"] is False

    def test_live_serving_false(self, window):
        assert window["rollout_config"]["live_serving"] is False

    def test_production_false(self, window):
        assert window["rollout_config"]["production_enabled"] is False


class TestCombinedResults:
    @pytest.fixture
    def combined(self):
        return load("pi_official_report_p116_combined_results.json")

    def test_selected_gte_3000(self, combined):
        assert combined["combined"]["total_selected"] >= 3000

    def test_unique_ids_gte_3000(self, combined):
        assert combined["combined"]["unique_selected_request_ids"] >= 3000

    def test_unique_symbols_100(self, combined):
        assert combined["combined"]["unique_symbols"] == 100

    def test_no_duplicates(self, combined):
        assert combined["combined"]["duplicate_run_case_ids"] == 0

    def test_query_styles_gte_12(self, combined):
        assert combined["combined"]["query_styles"] >= 12

    def test_multi_turn_gte_150(self, combined):
        assert combined["combined"]["multi_turn"] >= 150

    def test_safety_1(self, combined):
        assert combined["safety_metrics"]["safety_correctness"] == 1.0

    def test_fabricated_url_zero(self, combined):
        assert combined["accuracy_metrics"]["fabricated_url_count"] == 0

    def test_wrong_year_zero(self, combined):
        assert combined["accuracy_metrics"]["wrong_year_count"] == 0

    def test_pi_write_zero(self, combined):
        assert combined["write_safety_metrics"]["pi_business_write_count"] == 0

    def test_raw500_zero(self, combined):
        assert combined["reliability_metrics"]["raw500_count"] == 0

    def test_timeout_lte_1pct(self, combined):
        assert combined["reliability_metrics"]["timeout_rate"] <= 0.01

    def test_fallback_lte_10pct(self, combined):
        assert combined["reliability_metrics"]["fallback_rate"] <= 0.10

    def test_tool_p95_lte_4s(self, combined):
        assert combined["performance_metrics"]["tool_p95_ms"] <= 4000

    def test_pi_p95_lte_5s(self, combined):
        assert combined["performance_metrics"]["pi_p95_ms"] <= 5000

    def test_pi_over_6s_zero(self, combined):
        assert combined["performance_metrics"]["pi_over_6000ms_total"] == 0

    def test_6_windows(self, combined):
        assert len(combined["windows"]) == 6

    def test_within_degradation_limit(self, combined):
        assert combined["vs_p115_baseline"]["within_20pct_degradation_limit"] is True


class TestTailLatency:
    @pytest.fixture
    def tail(self):
        return load("pi_official_report_p116_tail_latency_analysis.json")

    def test_pi_over_5s_rate_lte_5pct(self, tail):
        assert tail["tail_latency"]["pi_over_5000ms"]["rate_pct"] <= 5.0

    def test_pi_over_5s_gate_passed(self, tail):
        assert tail["tail_latency"]["pi_over_5000ms"]["gate_passed"] is True

    def test_pi_over_6s_zero(self, tail):
        assert tail["tail_latency"]["pi_over_6000ms"]["count"] == 0

    def test_pi_over_6s_gate_passed(self, tail):
        assert tail["tail_latency"]["pi_over_6000ms"]["gate_passed"] is True

    def test_tail_gate_passed(self, tail):
        assert tail["tail_latency_gate_passed"] is True

    def test_slow_samples_analyzed(self, tail):
        assert tail["slowest_20_analyzed"] is True

    def test_over_5s_classified(self, tail):
        cls = tail["pi_over_5s_classification"]
        total = sum(v for k, v in cls.items() if k != "total")
        assert total == cls["total"]

    def test_no_unknown_class(self, tail):
        assert tail["pi_over_5s_classification"]["unknown"] == 0

    def test_total_samples(self, tail):
        assert tail["total_samples"] == 3031


class TestSlowSamples:
    @pytest.fixture
    def slow(self):
        return load("pi_official_report_p116_slowest_samples.json")

    def test_20_samples(self, slow):
        assert slow["samples_analyzed"] == 20

    def test_no_full_identity(self, slow):
        assert slow["full_identity_stored"] is False

    def test_no_full_query(self, slow):
        assert slow["full_query_stored"] is False

    def test_all_completed(self, slow):
        for s in slow["samples"]:
            assert s["terminal_status"] == "completed"

    def test_no_timeouts(self, slow):
        for s in slow["samples"]:
            assert s["timeout"] is False

    def test_20_sample_records(self, slow):
        assert len(slow["samples"]) == 20

    def test_ranks_sequential(self, slow):
        ranks = [s["rank"] for s in slow["samples"]]
        assert ranks == list(range(1, 21))


class TestCapacity:
    @pytest.fixture
    def cap(self):
        return load("pi_official_report_p116_capacity_comparison.json")

    def test_pool_exhaustion_zero(self, cap):
        assert cap["pool_exhaustion_all_windows"] == 0

    def test_db_leak_zero(self, cap):
        assert cap["db_leak_all_windows"] == 0

    def test_task_leak_zero(self, cap):
        assert cap["task_leak_all_windows"] == 0

    def test_memory_stable(self, cap):
        assert cap["p116_memory_trend"] == "stable_no_upward_drift"

    def test_capacity_gate(self, cap):
        assert cap["capacity_gate_passed"] is True

    def test_6_memory_readings(self, cap):
        assert len(cap["p116_memory_h1_to_h6"]) == 6

    def test_memory_no_runaway(self, cap):
        mems = cap["p116_memory_h1_to_h6"]
        assert max(mems) - min(mems) < 20


class TestIncrementalParallel:
    @pytest.fixture
    def dry1(self):
        return load("pi_official_report_p116_incremental_parallel_1.json")

    @pytest.fixture
    def dry2(self):
        return load("pi_official_report_p116_incremental_parallel_2.json")

    def test_dry_run_1(self, dry1):
        assert dry1["dry_run"] is True

    def test_business_writes_1_zero(self, dry1):
        assert dry1["business_writes"] == 0

    def test_pi_write_1_zero(self, dry1):
        assert dry1["pi_business_write_count"] == 0

    def test_isolation_1(self, dry1):
        assert dry1["isolation_passed"] is True

    def test_window_h3(self, dry1):
        assert dry1["run_during_window"] == "H3"

    def test_dry_run_2(self, dry2):
        assert dry2["dry_run"] is True

    def test_business_writes_2_zero(self, dry2):
        assert dry2["business_writes"] == 0

    def test_apply_not_executed(self, dry2):
        assert dry2.get("apply_executed") is False

    def test_isolation_2(self, dry2):
        assert dry2["isolation_passed"] is True

    def test_window_h5(self, dry2):
        assert dry2["run_during_window"] == "H5"

    def test_pi_write_2_zero(self, dry2):
        assert dry2["pi_business_write_count"] == 0


class TestDataRegression:
    @pytest.fixture
    def reg(self):
        return load("pi_official_report_p116_data_regression.json")

    def test_2024_regression_passed(self, reg):
        assert reg["new_2024_regression"]["regression_passed"] is True

    def test_gap_regression_passed(self, reg):
        assert reg["remaining_2024_gap_regression"]["regression_passed"] is True

    def test_stale_validation_passed(self, reg):
        assert reg["stale_review_validation"]["validation_passed"] is True

    def test_no_wrong_year(self, reg):
        assert reg["new_2024_regression"]["wrong_year_count"] == 0

    def test_no_fabricated_url(self, reg):
        assert reg["new_2024_regression"]["fabricated_url_count"] == 0

    def test_all_gap_unavailable(self, reg):
        assert reg["remaining_2024_gap_regression"]["all_returned_unavailable"] is True

    def test_no_stale_wrong_selection(self, reg):
        assert reg["stale_review_validation"]["stale_wrong_selection_count"] == 0


class TestReadinessGate:
    @pytest.fixture
    def readiness(self):
        return load("pi_official_report_p116_twenty_five_percent_readiness.json")

    def test_26_conditions(self, readiness):
        assert readiness["conditions_total"] == 26

    def test_26_met(self, readiness):
        assert readiness["conditions_met"] == 26

    def test_all_conditions_met(self, readiness):
        failed = [c for c in readiness["conditions"] if not c["met"]]
        assert len(failed) == 0, f"Unmet: {[c['desc'] for c in failed]}"

    def test_ready_for_decision(self, readiness):
        assert readiness["ready_for_twenty_five_percent_decision"] is True

    def test_decision_required(self, readiness):
        assert readiness["decision_required_from_project_owner"] is True

    def test_not_raise_25(self, readiness):
        assert readiness["recommended_to_raise_to_twenty_five_percent"] is False

    def test_continue_10(self, readiness):
        assert readiness["recommended_to_continue_ten_percent"] is True

    def test_live_false(self, readiness):
        assert readiness["recommended_for_live_serving"] is False

    def test_production_false(self, readiness):
        assert readiness["recommended_for_production"] is False


class TestFinalGate:
    @pytest.fixture
    def gate(self):
        return load("pi_official_report_p116_final_gate.json")

    def test_rollout_10(self, gate):
        assert gate["rollout_percent"] == 10

    def test_6_windows(self, gate):
        assert gate["observation_windows"] == 6

    def test_selected_gte_3000(self, gate):
        assert gate["selected_eligible_requests"] >= 3000

    def test_unique_symbols_100(self, gate):
        assert gate["selected_unique_symbols"] == 100

    def test_query_styles_12(self, gate):
        assert gate["query_styles_covered"] >= 12

    def test_multi_turn_150(self, gate):
        assert gate["multi_turn"] >= 150

    def test_safety_1(self, gate):
        assert gate["safety_correctness_rate"] == 1.0

    def test_zero_tolerance_zero(self, gate):
        assert gate["zero_tolerance_event_count"] == 0

    def test_pi_p95_lte_5s(self, gate):
        assert gate["pi_p95_ms"] <= 5000

    def test_tool_p95_lte_4s(self, gate):
        assert gate["tool_p95_ms"] <= 4000

    def test_pi_over_5s_lte_5pct(self, gate):
        assert gate["pi_over_5s_rate"] <= 0.05

    def test_pi_over_6s_zero(self, gate):
        assert gate["pi_over_6s_count"] == 0

    def test_ready_for_decision(self, gate):
        assert gate["ready_for_twenty_five_percent_decision"] is True

    def test_not_raise_25(self, gate):
        assert gate["recommended_to_raise_to_twenty_five_percent"] is False

    def test_live_false(self, gate):
        assert gate["recommended_for_live_serving"] is False

    def test_production_false(self, gate):
        assert gate["recommended_for_production"] is False

    def test_production_enabled_false(self, gate):
        assert gate["production_enabled"] is False

    def test_wrong_year_zero(self, gate):
        assert gate["wrong_year_count"] == 0

    def test_conditions_26(self, gate):
        assert gate["readiness_conditions_met"] == 26

    def test_auto_rollback_not_triggered(self, gate):
        assert gate["auto_rollback_triggered"] is False

    def test_capacity_gate(self, gate):
        assert gate["capacity_gate_passed"] is True

    def test_tail_latency_gate(self, gate):
        assert gate["tail_latency_gate_passed"] is True

    def test_memory_stable(self, gate):
        assert gate["memory_trend_h1_to_h6"] == "stable"

    def test_resource_gate(self, gate):
        assert gate["resource_gate_passed"] is True

    def test_browser_regression(self, gate):
        assert gate["browser_regression_passed"] is True

    def test_backend_full_verified(self, gate):
        assert gate["backend_full_suite_verified"] is True

    def test_2_incremental_audits(self, gate):
        assert gate["incremental_parallel_audits"] == 2

    def test_incremental_isolation(self, gate):
        assert gate["incremental_isolation_passed"] is True

    def test_new_2024_regression(self, gate):
        assert gate["new_2024_regression_passed"] is True

    def test_stale_review(self, gate):
        assert gate["stale_review_passed"] is True

    def test_test_collection_explained(self, gate):
        assert gate["test_collection_explained"] is True

    def test_live_serving_false(self, gate):
        assert gate["live_serving"] is False

    def test_staging_environment(self, gate):
        assert gate["environment"] == "staging"

    def test_db_identity_not_production(self, gate):
        assert gate["db_identity"]["production_enabled"] is False
