"""
Phase 6V-P1.15: Ten-Percent Shadow Canary Gate Tests
Covers G1-G5 observation windows, combined results, promotion audit,
bucket distribution, data regression, rollback gate, and final gate.
"""
import json
import pytest
from pathlib import Path

ARTIFACT_DIR = Path(__file__).parent.parent.parent / "docs" / "artifacts"


def load(name):
    return json.loads((ARTIFACT_DIR / name).read_text())


class TestP114DeliveryAudit:
    @pytest.fixture
    def audit(self):
        return load("pi_official_report_p115_p114_delivery_audit.json")

    def test_backend_full_passed(self, audit):
        assert audit["backend_full_failed"] == 0

    def test_backend_exit_0(self, audit):
        assert audit["backend_full_exit_code"] == 0

    def test_secret_scan_clean(self, audit):
        assert audit["secret_scan_clean"] is True

    def test_resource_audit_passed(self, audit):
        assert audit["resource_audit_passed"] is True

    def test_default_config_production_false(self, audit):
        assert audit["formal_default_config"]["production_enabled"] is False

    def test_default_config_rollout_0(self, audit):
        assert audit["formal_default_config"]["default_rollout"] == 0

    def test_delivery_gate_passed(self, audit):
        assert audit["delivery_audit_gate_passed"] is True


class TestOwnerApproval:
    @pytest.fixture
    def appr(self):
        return load("pi_official_report_p115_project_owner_approval.json")

    def test_project_owner_self_approval(self, appr):
        assert appr["approval_type"] == "project_owner_self_approval"

    def test_from_5(self, appr):
        assert appr["from_rollout_percent"] == 5

    def test_to_10(self, appr):
        assert appr["to_rollout_percent"] == 10

    def test_max_10(self, appr):
        assert appr["max_rollout_allowed"] == 10

    def test_live_not_authorized(self, appr):
        assert appr["live_serving_authorized"] is False

    def test_production_not_authorized(self, appr):
        assert appr["production_authorized"] is False

    def test_25pct_not_authorized(self, appr):
        assert appr["twenty_five_percent_authorized"] is False

    def test_decision_ten_pct_only(self, appr):
        assert "ten_percent" in appr["decision"]

    def test_personal_project(self, appr):
        assert appr["project_type"] == "personal_project"

    def test_approved_by_owner(self, appr):
        assert appr["approved_by_role"] == "project_owner"


class TestPromotion:
    @pytest.fixture
    def promo(self):
        return load("pi_official_report_p115_promotion_audit.json")

    def test_from_5_to_10(self, promo):
        assert promo["from_rollout_percent"] == 5 and promo["to_rollout_percent"] == 10

    def test_config_version_5(self, promo):
        assert promo["config_version_after"] == 5

    def test_max_10_enforced(self, promo):
        assert promo["max_rollout_allowed"] == 10

    def test_above_max_rejected(self, promo):
        assert promo["above_max_rejected"] is True

    def test_live_false(self, promo):
        assert promo["live_serving"] is False

    def test_production_false(self, promo):
        assert promo["production"] is False

    def test_repo_default_unchanged(self, promo):
        assert promo["repository_default_config_unchanged"] is True

    def test_fail_closed(self, promo):
        assert promo["fail_closed_on_failure"] is True

    def test_rollout_verified_10(self, promo):
        assert promo["rollout_verified"] == 10

    def test_promotion_passed(self, promo):
        assert promo["promotion_audit_passed"] is True


class TestBucketDistribution:
    @pytest.fixture
    def bkt(self):
        return load("pi_official_report_p115_bucket_distribution.json")

    def test_100k_keys(self, bkt):
        assert bkt["sampled_keys"] == 100000

    def test_rate_in_range(self, bkt):
        rate = bkt["observed_selection_rate_pct"]
        assert 9.6 <= rate <= 10.4

    def test_within_range(self, bkt):
        assert bkt["within_expected_range"] is True

    def test_deterministic(self, bkt):
        assert bkt["deterministic"] is True

    def test_no_builtin_hash(self, bkt):
        assert bkt["uses_python_builtin_hash"] is False

    def test_identity_not_stored(self, bkt):
        assert bkt["full_identity_stored"] is False


class TestObservationWindows:
    @pytest.fixture(params=["g1", "g2", "g3", "g4", "g5"])
    def window(self, request):
        return load(f"pi_official_report_p115_{request.param}_results.json")

    def test_selected_gte_200(self, window):
        assert window["selection"]["selected"] >= 200

    def test_unique_symbols_gte_60(self, window):
        assert window["selection"]["unique_symbols"] >= 60

    def test_safety_1(self, window):
        assert window["safety_metrics"]["safety_correctness"] == 1.0

    def test_wrong_year_zero(self, window):
        assert window["accuracy_metrics"]["wrong_year_count"] == 0

    def test_fabricated_url_zero(self, window):
        assert window["accuracy_metrics"]["fabricated_url_count"] == 0

    def test_pi_write_zero(self, window):
        assert window["write_safety_metrics"]["pi_business_write_count"] == 0

    def test_raw500_zero(self, window):
        assert window["reliability_metrics"]["raw500_count"] == 0

    def test_raw503_zero(self, window):
        assert window["reliability_metrics"]["raw503_count"] == 0

    def test_tool_p95_lte_4s(self, window):
        assert window["performance_metrics"]["tool_p95_ms"] <= 4000

    def test_pi_p95_lte_5s(self, window):
        assert window["performance_metrics"]["pi_p95_ms"] <= 5000

    def test_slow_samples_not_removed(self, window):
        assert window["performance_metrics"]["slow_samples_removed"] == 0

    def test_rollout_10pct(self, window):
        assert window["rollout_config"]["staging_shadow_rollout_percent"] == 10

    def test_not_raise_above_10(self, window):
        assert window["rollout_config"]["recommended_to_raise_above_ten_percent"] is False


class TestCombinedResults:
    @pytest.fixture
    def combined(self):
        return load("pi_official_report_p115_combined_results.json")

    def test_selected_gte_1000(self, combined):
        assert combined["combined"]["total_selected"] >= 1000

    def test_unique_ids_gte_1000(self, combined):
        assert combined["combined"]["unique_selected_request_ids"] >= 1000

    def test_unique_symbols_100(self, combined):
        assert combined["combined"]["unique_symbols"] == 100

    def test_no_duplicates(self, combined):
        assert combined["combined"]["duplicate_run_case_ids"] == 0

    def test_query_styles_gte_10(self, combined):
        assert combined["combined"]["query_styles"] >= 10

    def test_multi_turn_gte_60(self, combined):
        assert combined["combined"]["multi_turn"] >= 60

    def test_safety_1(self, combined):
        assert combined["safety_metrics"]["safety_correctness"] == 1.0

    def test_fabricated_url_zero(self, combined):
        assert combined["accuracy_metrics"]["fabricated_url_count"] == 0

    def test_wrong_year_zero(self, combined):
        assert combined["accuracy_metrics"]["wrong_year_count"] == 0

    def test_stale_wrong_zero(self, combined):
        assert combined["accuracy_metrics"]["stale_record_wrongly_selected"] == 0

    def test_pi_write_zero(self, combined):
        assert combined["write_safety_metrics"]["pi_business_write_count"] == 0

    def test_double_write_zero(self, combined):
        assert combined["write_safety_metrics"]["assistant_double_write_count"] == 0

    def test_raw500_zero(self, combined):
        assert combined["reliability_metrics"]["raw500_count"] == 0

    def test_raw503_zero(self, combined):
        assert combined["reliability_metrics"]["raw503_count"] == 0

    def test_timeout_lte_1pct(self, combined):
        assert combined["reliability_metrics"]["timeout_rate"] <= 0.01

    def test_fallback_lte_10pct(self, combined):
        assert combined["reliability_metrics"]["fallback_rate"] <= 0.10

    def test_task_leak_zero(self, combined):
        assert combined["reliability_metrics"]["task_leak_count"] == 0

    def test_db_leak_zero(self, combined):
        assert combined["reliability_metrics"]["db_leak_count"] == 0

    def test_pending_rollback_zero(self, combined):
        assert combined["reliability_metrics"]["PendingRollbackError"] == 0

    def test_pool_exhaustion_zero(self, combined):
        assert combined["reliability_metrics"]["pool_exhaustion"] == 0

    def test_tool_p95_lte_4s(self, combined):
        assert combined["performance_metrics"]["tool_p95_ms"] <= 4000

    def test_pi_p95_lte_5s(self, combined):
        assert combined["performance_metrics"]["pi_p95_ms"] <= 5000

    def test_degradation_within_20pct(self, combined):
        assert combined["performance_metrics"]["vs_p114_tool_p95_delta_pct"] <= 20.0

    def test_no_slow_removal(self, combined):
        assert combined["performance_metrics"]["slow_samples_removed"] == 0


class TestRollbackAudit:
    @pytest.fixture
    def rb(self):
        return load("pi_official_report_p115_auto_rollback_audit.json")

    def test_no_rollback_triggered(self, rb):
        assert rb["auto_rollback_triggered"] is False

    def test_rollout_still_10(self, rb):
        assert rb["current_rollout_percent"] == 10

    def test_no_conditions_triggered(self, rb):
        for c in rb["rollback_conditions_tested"]:
            assert c["triggered"] is False

    def test_no_subsequent_dilution(self, rb):
        assert rb["subsequent_success_would_dilute_failure"] is False


class TestDataRegression:
    @pytest.fixture
    def new2024(self):
        return load("pi_official_report_p115_new_2024_regression.json")

    @pytest.fixture
    def gap(self):
        return load("pi_official_report_p115_remaining_gap_regression.json")

    @pytest.fixture
    def stale(self):
        return load("pi_official_report_p115_stale_review_validation.json")

    def test_18_new_2024_exact_pass(self, new2024):
        assert new2024["test_types"]["exact_year_2024"]["failed"] == 0

    def test_18_latest_pass(self, new2024):
        assert new2024["test_types"]["latest"]["failed"] == 0

    def test_provider_calls_zero(self, new2024):
        assert new2024["provider_calls_during_serving"] == 0

    def test_19_gap_unavailable(self, gap):
        assert gap["all_returned_unavailable"] is True

    def test_no_wrong_fallback(self, gap):
        assert gap["wrong_year_fallback"] == 0

    def test_3_stale_not_wrong(self, stale):
        assert stale["stale_wrong_selection_count"] == 0

    def test_stale_not_deleted(self, stale):
        for r in stale["records"]:
            assert r["physically_deleted"] is False


class TestFinalGate:
    @pytest.fixture
    def gate(self):
        return load("pi_official_report_p115_final_gate.json")

    def test_rollout_10pct(self, gate):
        assert gate["rollout_percent"] == 10

    def test_5_windows(self, gate):
        assert gate["observation_windows"] == 5

    def test_selected_gte_1000(self, gate):
        assert gate["selected_eligible_requests"] >= 1000

    def test_unique_symbols_100(self, gate):
        assert gate["selected_unique_symbols"] == 100

    def test_styles_10(self, gate):
        assert gate["query_styles_covered"] >= 10

    def test_multi_turn_60(self, gate):
        assert gate["multi_turn"] >= 60

    def test_safety_1(self, gate):
        assert gate["safety_correctness_rate"] == 1.0

    def test_zero_tolerance_zero(self, gate):
        assert gate["zero_tolerance_event_count"] == 0

    def test_ten_pct_passed(self, gate):
        assert gate["ten_percent_shadow_passed"] is True

    def test_not_raise_above_10(self, gate):
        assert gate["recommended_to_raise_above_ten_percent"] is False

    def test_live_false(self, gate):
        assert gate["recommended_for_live_serving"] is False

    def test_production_false(self, gate):
        assert gate["recommended_for_production"] is False

    def test_production_enabled_false(self, gate):
        assert gate["production_enabled"] is False

    def test_live_serving_false(self, gate):
        assert gate["live_serving"] is False

    def test_wrong_year_zero(self, gate):
        assert gate["wrong_year_count"] == 0

    def test_fabricated_url_zero(self, gate):
        assert gate["fabricated_url_count"] == 0

    def test_pi_write_zero(self, gate):
        assert gate["pi_business_write_count"] == 0

    def test_tool_p95_lte_4s(self, gate):
        assert gate["tool_p95_ms"] <= 4000

    def test_pi_p95_lte_5s(self, gate):
        assert gate["pi_p95_ms"] <= 5000

    def test_auto_rollback_not_triggered(self, gate):
        assert gate["auto_rollback_triggered"] is False

    def test_resource_gate(self, gate):
        assert gate["resource_gate_passed"] is True

    def test_capacity_gate(self, gate):
        assert gate["capacity_gate_passed"] is True

    def test_browser_regression(self, gate):
        assert gate["browser_regression_passed"] is True

    def test_continue_10(self, gate):
        assert gate["recommended_to_continue_ten_percent"] is True
