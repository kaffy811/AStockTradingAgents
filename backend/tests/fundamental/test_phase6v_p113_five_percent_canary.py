"""
tests/fundamental/test_phase6v_p113_five_percent_canary.py
Phase 6V-P1.13: 5% shadow canary regression suite

7 test classes, 42+ tests:
1. TestApprovalAndPromotion
2. TestBucketDistribution
3. TestSafetyAndRollback
4. TestObservationWindows (F1-F5 and combined)
5. TestStaleReviewProtection
6. TestIsolationAndUX
7. TestFinalGate
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Any
import pytest

_BACKEND = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_BACKEND))
_A = _BACKEND / "docs" / "artifacts"


@pytest.fixture(scope="module")
def approval() -> dict[str, Any]:
    p = _A / "pi_official_report_p113_project_owner_approval.json"
    assert p.exists()
    return json.loads(p.read_text())

@pytest.fixture(scope="module")
def baseline() -> dict[str, Any]:
    p = _A / "pi_official_report_p113_pre_promotion_baseline.json"
    assert p.exists()
    return json.loads(p.read_text())

@pytest.fixture(scope="module")
def promotion() -> dict[str, Any]:
    p = _A / "pi_official_report_p113_promotion_audit.json"
    assert p.exists()
    return json.loads(p.read_text())

@pytest.fixture(scope="module")
def bucket_dist() -> dict[str, Any]:
    p = _A / "pi_official_report_p113_bucket_distribution.json"
    assert p.exists()
    return json.loads(p.read_text())

@pytest.fixture(scope="module")
def safety_audit() -> dict[str, Any]:
    p = _A / "pi_official_report_p113_safety_audit.json"
    assert p.exists()
    return json.loads(p.read_text())

@pytest.fixture(scope="module")
def rollback_audit() -> dict[str, Any]:
    p = _A / "pi_official_report_p113_auto_rollback_audit.json"
    assert p.exists()
    return json.loads(p.read_text())

@pytest.fixture(scope="module")
def combined() -> dict[str, Any]:
    p = _A / "pi_official_report_p113_combined_results.json"
    assert p.exists()
    return json.loads(p.read_text())

@pytest.fixture(scope="module")
def stale_val() -> dict[str, Any]:
    p = _A / "pi_official_report_p113_stale_review_validation.json"
    assert p.exists()
    return json.loads(p.read_text())

@pytest.fixture(scope="module")
def latency() -> dict[str, Any]:
    p = _A / "pi_official_report_p113_latency.json"
    assert p.exists()
    return json.loads(p.read_text())

@pytest.fixture(scope="module")
def browser() -> dict[str, Any]:
    p = _A / "pi_official_report_p113_browser_regression.json"
    assert p.exists()
    return json.loads(p.read_text())

@pytest.fixture(scope="module")
def parallel_audit() -> dict[str, Any]:
    p = _A / "pi_official_report_p113_incremental_parallel_audit.json"
    assert p.exists()
    return json.loads(p.read_text())

@pytest.fixture(scope="module")
def final_gate() -> dict[str, Any]:
    p = _A / "pi_official_report_p113_final_gate.json"
    assert p.exists()
    return json.loads(p.read_text())

@pytest.fixture(scope="module")
def f1() -> dict[str, Any]:
    return json.loads((_A / "pi_official_report_p113_f1_results.json").read_text())

@pytest.fixture(scope="module")
def f2() -> dict[str, Any]:
    return json.loads((_A / "pi_official_report_p113_f2_results.json").read_text())

@pytest.fixture(scope="module")
def f3() -> dict[str, Any]:
    return json.loads((_A / "pi_official_report_p113_f3_results.json").read_text())

@pytest.fixture(scope="module")
def f4() -> dict[str, Any]:
    return json.loads((_A / "pi_official_report_p113_f4_results.json").read_text())

@pytest.fixture(scope="module")
def f5() -> dict[str, Any]:
    return json.loads((_A / "pi_official_report_p113_f5_results.json").read_text())


class TestApprovalAndPromotion:
    def test_approval_type_project_owner(self, approval):
        assert approval["approval_type"] == "project_owner_self_approval"

    def test_personal_project(self, approval):
        assert approval["project_type"] == "personal_project"

    def test_approved_scope_five_pct_shadow(self, approval):
        assert approval["approved_scope"] == "five_percent_shadow_canary"

    def test_from_1_to_5(self, approval):
        assert approval["from_rollout_percent"] == 1
        assert approval["to_rollout_percent"] == 5

    def test_live_not_authorized(self, approval):
        assert approval["live_serving_authorized"] is False

    def test_production_not_authorized(self, approval):
        assert approval["production_authorized"] is False

    def test_ten_pct_not_authorized(self, approval):
        assert approval["ten_percent_authorized"] is False

    def test_source_sha_40(self, approval):
        assert len(approval["source_sha"]) == 40

    def test_baseline_passed(self, baseline):
        assert baseline["baseline_passed"] is True

    def test_baseline_safety_1(self, baseline):
        assert baseline["safety_metrics"]["safety_correctness"] == 1.0

    def test_baseline_zero_writes(self, baseline):
        assert baseline["write_safety_metrics"]["pi_business_write"] == 0

    def test_promotion_success(self, promotion):
        assert promotion["promotion_result"] == "success"

    def test_promotion_rollout_5(self, promotion):
        assert promotion["rollout_verified"] == 5

    def test_promotion_max_5(self, promotion):
        assert promotion["max_rollout_allowed"] == 5

    def test_promotion_config_version_incremented(self, promotion):
        assert promotion["config_version_after"] == promotion["config_version_before"] + 1

    def test_promotion_default_config_unchanged(self, promotion):
        assert promotion["repository_default_config_unchanged"] is True
        assert promotion["PI_AGENT_SHADOW_ENABLED_default"] is False
        assert promotion["AGENT_EXECUTOR_MODE_default"] == "legacy"
        assert promotion["authorized_agents_default"] == []

    def test_promotion_live_false(self, promotion):
        assert promotion["live_serving"] is False

    def test_promotion_production_false(self, promotion):
        assert promotion["production"] is False


class TestBucketDistribution:
    def test_sample_size_50k(self, bucket_dist):
        assert bucket_dist["sample_keys_tested"] == 50000

    def test_within_expected_range(self, bucket_dist):
        assert bucket_dist["within_expected_range"] is True

    def test_selected_rate_in_range(self, bucket_dist):
        rate = bucket_dist["selected_rate"]
        assert 0.047 <= rate <= 0.053

    def test_deterministic(self, bucket_dist):
        assert bucket_dist["deterministic"] is True

    def test_no_python_builtin_hash(self, bucket_dist):
        assert bucket_dist["uses_python_builtin_hash"] is False

    def test_no_time_or_random(self, bucket_dist):
        assert bucket_dist["uses_time_or_random"] is False

    def test_no_complete_user_id(self, bucket_dist):
        assert bucket_dist["complete_user_id_stored"] is False

    def test_config_version_rebuckets(self, bucket_dist):
        assert bucket_dist["config_version_change_rebuckets"] is True


class TestSafetyAndRollback:
    def test_safety_correctness_1(self, safety_audit):
        assert safety_audit["safety_correctness"] == 1.0

    def test_all_zero_tolerance_zero(self, safety_audit):
        for k, v in safety_audit["zero_tolerance_metrics"].items():
            assert v == 0, f"Zero tolerance violated: {k}={v}"

    def test_timeout_rate_0(self, safety_audit):
        assert safety_audit["unexpected_timeout_rate"] == 0.0

    def test_fallback_rate_lt_10pct(self, safety_audit):
        assert safety_audit["fallback_rate"] <= 0.10

    def test_no_auto_rollback(self, safety_audit):
        assert safety_audit["auto_rollback_triggered"] is False

    def test_safety_gate_passed(self, safety_audit):
        assert safety_audit["safety_gate_passed"] is True

    def test_rollback_not_triggered(self, rollback_audit):
        assert rollback_audit["auto_rollback_triggered"] is False

    def test_subsequent_success_cannot_erase_failure(self, rollback_audit):
        assert rollback_audit["subsequent_success_cannot_erase_failure"] is True

    def test_auto_recovery_disabled(self, rollback_audit):
        assert rollback_audit["auto_recovery_disabled"] is True

    def test_rollback_conditions_all_false(self, rollback_audit):
        for cond in rollback_audit["rollback_conditions_tested"]:
            assert cond["triggered"] is False


class TestObservationWindows:
    def test_f1_selected_gte_100(self, f1):
        assert f1["selection"]["selected"] >= 100

    def test_f1_safety_1(self, f1):
        assert f1["safety_metrics"]["safety_correctness"] == 1.0

    def test_f1_zero_tolerance(self, f1):
        for v in f1["accuracy_metrics"].values():
            assert v == 0
        for v in f1["write_safety_metrics"].values():
            assert v == 0

    def test_f2_selected_gte_100(self, f2):
        assert f2["selection"]["selected"] >= 100

    def test_f3_selected_gte_100(self, f3):
        assert f3["selection"]["selected"] >= 100

    def test_f3_new_symbols(self, f3):
        assert f3["selection"]["new_symbols_vs_f1_f2"] > 0

    def test_f4_selected_gte_100(self, f4):
        assert f4["selection"]["selected"] >= 100

    def test_f5_selected_gte_100(self, f5):
        assert f5["selection"]["selected"] >= 100

    def test_combined_gte_500(self, combined):
        assert combined["combined"]["total_selected"] >= 500

    def test_combined_unique_symbols_gte_90(self, combined):
        assert combined["combined"]["unique_symbols"] >= 90

    def test_combined_no_duplicates(self, combined):
        assert combined["combined"]["duplicate_case_run_ids"] == 0

    def test_combined_multi_turn_gte_30(self, combined):
        assert combined["combined"]["multi_turn_executions"] >= 30

    def test_combined_query_styles_gte_8(self, combined):
        assert len(combined["combined"]["query_styles_covered"]) >= 8

    def test_combined_safety_1(self, combined):
        assert combined["safety_metrics"]["safety_correctness"] == 1.0

    def test_combined_all_zero_tolerance(self, combined):
        for v in combined["accuracy_metrics"].values():
            assert v == 0
        for v in combined["write_safety_metrics"].values():
            assert v == 0

    def test_combined_provider_calls_zero(self, combined):
        assert combined["performance_metrics"]["provider_calls_during_serving"] == 0

    def test_combined_fallback_rate_lt_10pct(self, combined):
        assert combined["reliability_metrics"]["combined_fallback_rate"] <= 0.10

    def test_combined_timeout_rate_zero(self, combined):
        assert combined["reliability_metrics"]["unexpected_timeout_rate"] == 0.0

    def test_tool_p95_lte_4s(self, latency):
        assert latency["combined"]["tool_p95_ms"] <= 4000

    def test_pi_p95_lte_5s(self, latency):
        assert latency["combined"]["pi_p95_ms"] <= 5000

    def test_no_performance_degradation(self, latency):
        assert latency["p112_comparison"]["within_20pct_threshold"] is True

    def test_performance_gate_passed(self, latency):
        assert latency["performance_gate"]["performance_gate_passed"] is True


class TestStaleReviewProtection:
    def test_3_stale_review_records(self, stale_val):
        assert stale_val["stale_review_records_count"] == 3

    def test_no_stale_wrong_selection(self, stale_val):
        assert stale_val["stale_wrong_selection_count"] == 0

    def test_all_stale_not_served(self, stale_val):
        for rec in stale_val["validation_results"]:
            assert rec["wrongly_selected_as_healthy"] is False
            assert rec["filtered_from_serving"] is True
            assert rec["physically_deleted"] is False

    def test_shadow_samples_cover_stale_symbols(self, stale_val):
        assert stale_val["shadow_samples_covering_stale_symbols"] > 0

    def test_stale_gate_passed(self, stale_val):
        assert stale_val["stale_review_gate_passed"] is True


class TestIsolationAndUX:
    def test_incremental_dry_run_no_writes(self, parallel_audit):
        assert parallel_audit["business_writes"] == 0

    def test_incremental_serving_no_provider_calls(self, parallel_audit):
        assert parallel_audit["serving_provider_calls"] == 0

    def test_incremental_no_active_selection_change(self, parallel_audit):
        assert parallel_audit["active_selection_unchanged"] is True

    def test_incremental_no_db_conflicts(self, parallel_audit):
        assert parallel_audit["db_lock_conflicts"] == 0

    def test_incremental_parallel_safe(self, parallel_audit):
        assert parallel_audit["parallel_safety_gate_passed"] is True

    def test_browser_regression_passed(self, browser):
        assert browser["browser_regression_passed"] is True

    def test_user_visible_legacy_only(self, browser):
        assert browser["user_visible_legacy_only_confirmed"] is True

    def test_pi_not_leaked(self, browser):
        assert browser["pi_result_leaked"] is False

    def test_no_duplicate_ui_elements(self, browser):
        assert browser["duplicate_ui_elements"] is False

    def test_all_browser_cases_passed(self, browser):
        assert browser["passed"] == browser["total_cases"]


class TestFinalGate:
    def test_phase_p113(self, final_gate):
        assert final_gate["phase"] == "6V-P1.13"

    def test_rollout_5(self, final_gate):
        assert final_gate["rollout_percent"] == 5

    def test_selected_gte_500(self, final_gate):
        assert final_gate["selected_eligible_requests"] >= 500

    def test_unique_symbols_gte_90(self, final_gate):
        assert final_gate["selected_unique_symbols"] >= 90

    def test_five_pct_shadow_passed(self, final_gate):
        assert final_gate["five_percent_shadow_passed"] is True

    def test_continue_5pct(self, final_gate):
        assert final_gate["recommended_to_continue_five_percent"] is True

    def test_not_raise_above_5pct(self, final_gate):
        assert final_gate["recommended_to_raise_above_five_percent"] is False

    def test_not_live_serving(self, final_gate):
        assert final_gate["recommended_for_live_serving"] is False

    def test_not_production(self, final_gate):
        assert final_gate["recommended_for_production"] is False

    def test_production_enabled_false(self, final_gate):
        assert final_gate["production_enabled"] is False

    def test_auto_rollback_not_triggered(self, final_gate):
        assert final_gate["auto_rollback_triggered"] is False

    def test_no_raw_db_url(self, final_gate):
        raw = json.dumps(final_gate).lower()
        for bad in ("postgresql://", "postgres://", "password=", "@aws"):
            assert bad not in raw
