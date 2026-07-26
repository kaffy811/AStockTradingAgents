"""
tests/fundamental/test_phase6v_p113a_2024_coverage.py
Phase 6V-P1.13A: 2024 annual report gap fill validation suite

9 test classes, 80+ tests covering:
1. TestGapInventory
2. TestGapClassification
3. TestDryRun
4. TestDryRunGate
5. TestApplyResults
6. TestIdempotency
7. TestPostApplyCoverage
8. TestExactYearRegression
9. TestShadowRegression
10. TestFinalGate
11. TestFixture
12. TestUnavailableAnalysis
13. TestStaleReviewAudit
14. TestSafetyAudit
15. TestWriteAudit
16. TestResourceAudit
"""
from __future__ import annotations
import json
import pytest
from pathlib import Path
from typing import Any

ARTIFACT_DIR = Path(__file__).parent.parent.parent / "docs" / "artifacts"
FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"


def load(name: str) -> dict[str, Any]:
    p = ARTIFACT_DIR / name
    assert p.exists(), f"Artifact not found: {p}"
    return json.loads(p.read_text())


def load_fixture(name: str) -> dict[str, Any]:
    p = FIXTURE_DIR / name
    assert p.exists(), f"Fixture not found: {p}"
    return json.loads(p.read_text())


# ---------------------------------------------------------------------------
# 1. Gap Inventory
# ---------------------------------------------------------------------------
class TestGapInventory:
    @pytest.fixture
    def inv(self):
        return load("pi_official_report_p113a_2024_gap_inventory.json")

    def test_universe_100(self, inv):
        assert inv["universe_symbols"] == 100

    def test_missing_37(self, inv):
        assert inv["symbols_missing_2024_annual"] == 37

    def test_with_2024_63(self, inv):
        assert inv["symbols_with_2024_annual"] == 63

    def test_universe_adds_up(self, inv):
        assert inv["symbols_with_2024_annual"] + inv["symbols_missing_2024_annual"] == inv["universe_symbols"]

    def test_query_year_2024(self, inv):
        assert inv["query_criteria"]["report_year"] == 2024

    def test_query_type_annual(self, inv):
        assert inv["query_criteria"]["report_type"] == "annual"

    def test_full_report_only(self, inv):
        assert inv["query_criteria"]["is_full_report"] is True

    def test_official_domain_verified(self, inv):
        assert inv["query_criteria"]["official_domain_verified"] is True

    def test_active_only(self, inv):
        assert inv["query_criteria"]["active"] is True

    def test_not_superseded(self, inv):
        assert inv["query_criteria"]["superseded"] is False

    def test_missing_count_matches_list(self, inv):
        assert len(inv["missing_symbols"]) == inv["symbols_missing_2024_annual"]

    def test_gap_count_by_reason_sums_to_37(self, inv):
        total = sum(inv["gap_count_by_reason"].values())
        assert total == 37

    def test_staged_missing_18(self, inv):
        assert inv["gap_count_by_reason"]["staged_missing"] == 18

    def test_provider_not_found_8(self, inv):
        assert inv["gap_count_by_reason"]["provider_not_found"] == 8

    def test_officially_not_disclosed_3(self, inv):
        assert inv["gap_count_by_reason"]["officially_not_disclosed"] == 3

    def test_summary_only_3(self, inv):
        assert inv["gap_count_by_reason"]["summary_only"] == 3

    def test_wrong_report_type_2(self, inv):
        assert inv["gap_count_by_reason"]["wrong_report_type_only"] == 2

    def test_manual_review_3(self, inv):
        assert inv["gap_count_by_reason"]["manual_review_required"] == 3


# ---------------------------------------------------------------------------
# 2. Gap Classification
# ---------------------------------------------------------------------------
class TestGapClassification:
    @pytest.fixture
    def cls(self):
        return load("pi_official_report_p113a_gap_classification.json")

    def test_total_classified_37(self, cls):
        assert cls["total_classified"] == 37

    def test_can_apply_count(self, cls):
        can_apply = sum(1 for c in cls["classifications"] if c["can_apply"])
        assert can_apply == cls["can_apply_count"]

    def test_cannot_apply_count(self, cls):
        cannot = sum(1 for c in cls["classifications"] if not c["can_apply"])
        assert cannot == cls["cannot_apply_count"]

    def test_can_apply_plus_cannot_equals_total(self, cls):
        assert cls["can_apply_count"] + cls["cannot_apply_count"] == cls["total_classified"]

    def test_summary_rejected(self, cls):
        summary = [c for c in cls["classifications"] if c["classification"] == "summary_only"]
        for c in summary:
            assert c["can_apply"] is False

    def test_wrong_type_rejected(self, cls):
        wt = [c for c in cls["classifications"] if c["classification"] == "wrong_report_type_only"]
        for c in wt:
            assert c["can_apply"] is False

    def test_officially_not_disclosed_rejected(self, cls):
        ond = [c for c in cls["classifications"] if c["classification"] == "officially_not_disclosed"]
        for c in ond:
            assert c["can_apply"] is False

    def test_provider_not_found_rejected(self, cls):
        pnf = [c for c in cls["classifications"] if c["classification"] == "provider_not_found"]
        for c in pnf:
            assert c["can_apply"] is False

    def test_manual_review_rejected(self, cls):
        mr = [c for c in cls["classifications"] if c["classification"] == "manual_review_required"]
        for c in mr:
            assert c["can_apply"] is False

    def test_no_blanket_provider_missing(self, cls):
        pm = sum(1 for c in cls["classifications"] if c["classification"] == "provider_not_found")
        assert pm < 37

    def test_staging_missing_all_can_apply(self, cls):
        sm = [c for c in cls["classifications"] if c["classification"] == "staging_missing_provider_available"]
        for c in sm:
            assert c["can_apply"] is True

    def test_classification_count_18_can_apply(self, cls):
        assert cls["can_apply_count"] == 18

    def test_all_entries_have_symbol(self, cls):
        for c in cls["classifications"]:
            assert "symbol" in c and c["symbol"]

    def test_all_entries_have_classification(self, cls):
        for c in cls["classifications"]:
            assert "classification" in c and c["classification"]


# ---------------------------------------------------------------------------
# 3. Dry Run
# ---------------------------------------------------------------------------
class TestDryRun:
    @pytest.fixture
    def dr(self):
        return load("pi_official_report_p113a_2024_dry_run.json")

    def test_is_dry_run(self, dr):
        assert dr["dry_run"] is True

    def test_business_writes_zero(self, dr):
        assert dr["business_writes"] == 0

    def test_wrong_company_zero(self, dr):
        assert dr["wrong_company"] == 0

    def test_wrong_year_zero(self, dr):
        assert dr["wrong_year"] == 0

    def test_wrong_report_type_zero(self, dr):
        assert dr["wrong_report_type"] == 0

    def test_third_party_rejected_zero(self, dr):
        assert dr["third_party_rejected"] == 0

    def test_duplicate_active_zero(self, dr):
        assert dr["duplicate_active"] == 0

    def test_missing_provenance_zero(self, dr):
        assert dr["missing_provenance"] == 0

    def test_unverified_active_zero(self, dr):
        assert dr["unverified_active"] == 0

    def test_errors_zero(self, dr):
        assert dr["errors"] == 0

    def test_environment_staging(self, dr):
        assert dr["environment"] == "staging"

    def test_verified_full_annual_18(self, dr):
        assert dr["verified_full_annual"] == 18

    def test_planned_candidates_18(self, dr):
        assert dr["planned_candidates_count"] == 18

    def test_dry_run_gate_passed(self, dr):
        assert dr["dry_run_gate_passed"] is True


# ---------------------------------------------------------------------------
# 4. Dry Run Gate
# ---------------------------------------------------------------------------
class TestDryRunGate:
    @pytest.fixture
    def gate(self):
        return load("pi_official_report_p113a_dry_run_gate.json")

    def test_gate_passed(self, gate):
        assert gate["gate_passed"] is True

    def test_wrong_company_zero(self, gate):
        assert gate["wrong_company"] == 0

    def test_wrong_year_zero(self, gate):
        assert gate["wrong_year"] == 0

    def test_wrong_report_type_zero(self, gate):
        assert gate["wrong_report_type"] == 0

    def test_duplicate_active_zero(self, gate):
        assert gate["duplicate_active"] == 0

    def test_missing_provenance_zero(self, gate):
        assert gate["missing_provenance"] == 0

    def test_unverified_active_zero(self, gate):
        assert gate["unverified_active"] == 0

    def test_dry_run_business_writes_zero(self, gate):
        assert gate["dry_run_business_writes"] == 0

    def test_fabricated_url_zero(self, gate):
        assert gate["fabricated_url"] == 0

    def test_third_party_domain_zero(self, gate):
        assert gate["third_party_domain"] == 0

    def test_authorization_to_proceed(self, gate):
        assert gate["authorization_to_proceed"] is True

    def test_all_zero_tolerance_passed(self, gate):
        metrics = gate["zero_tolerance_metrics"]
        for k, v in metrics.items():
            assert v["passed"] is True, f"zero_tolerance metric {k} did not pass"
            assert v["value"] == 0, f"zero_tolerance metric {k} value != 0: {v['value']}"


# ---------------------------------------------------------------------------
# 5. Apply Results
# ---------------------------------------------------------------------------
class TestApplyResults:
    @pytest.fixture
    def apply(self):
        return load("pi_official_report_p113a_apply_results.json")

    def test_failed_zero(self, apply):
        assert apply["failed"] == 0

    def test_rejected_zero(self, apply):
        assert apply["rejected"] == 0

    def test_inserted_equals_planned(self, apply):
        assert apply["inserted"] == apply["planned_verified_candidates"]

    def test_inserted_18(self, apply):
        assert apply["inserted"] == 18

    def test_no_duplicate_active(self, apply):
        assert apply.get("duplicate_active_created", 0) == 0

    def test_staging_guard_confirmed(self, apply):
        assert apply.get("staging_guard_passed") is True

    def test_production_rejected(self, apply):
        assert apply.get("production_apply_rejected") is True or \
               apply.get("environment") == "staging"

    def test_total_rows_after_320(self, apply):
        assert apply["total_rows_after"] == 320

    def test_active_2024_after_81(self, apply):
        assert apply["active_2024_annual_rows_after"] == 81

    def test_environment_staging(self, apply):
        assert apply["environment"] == "staging"

    def test_quality_checks_company_match(self, apply):
        assert apply["quality_checks_post_insert"]["company_match_rate"] == 1.0

    def test_quality_checks_year_match(self, apply):
        assert apply["quality_checks_post_insert"]["year_match_rate"] == 1.0

    def test_quality_checks_official_domain(self, apply):
        assert apply["quality_checks_post_insert"]["official_domain_verified_rate"] == 1.0


# ---------------------------------------------------------------------------
# 6. Idempotency
# ---------------------------------------------------------------------------
class TestIdempotency:
    @pytest.fixture
    def idem(self):
        return load("pi_official_report_p113a_idempotency_results.json")

    def test_second_inserted_zero(self, idem):
        assert idem["summary"]["inserted"] == 0

    def test_unchanged_18(self, idem):
        assert idem["summary"]["unchanged"] == 18

    def test_row_delta_zero(self, idem):
        assert idem["idempotency_checks"]["row_count_delta"] == 0

    def test_identity_drift_zero(self, idem):
        assert idem["idempotency_checks"]["document_identity_drift"] == 0

    def test_duplicate_active_delta_zero(self, idem):
        assert idem["idempotency_checks"]["active_duplicate_delta"] == 0

    def test_idempotency_passed(self, idem):
        assert idem["idempotency_passed"] is True

    def test_checksum_match(self, idem):
        assert idem["idempotency_checks"]["checksum_match"] is True

    def test_failed_zero(self, idem):
        assert idem["summary"]["failed"] == 0

    def test_active_2024_after_unchanged(self, idem):
        checks = idem["idempotency_checks"]
        assert checks["active_2024_annual_before"] == checks["active_2024_annual_after"]

    def test_zero_tolerance_zero(self, idem):
        zt = idem["zero_tolerance_checks"]
        assert zt["duplicate_active_created"] == 0
        assert zt["wrong_year_inserted"] == 0
        assert zt["wrong_type_inserted"] == 0
        assert zt["fabricated_url_inserted"] == 0


# ---------------------------------------------------------------------------
# 7. Post Apply Coverage
# ---------------------------------------------------------------------------
class TestPostApplyCoverage:
    @pytest.fixture
    def cov(self):
        return load("pi_official_report_p113a_post_apply_coverage.json")

    def test_gap_reduced(self, cov):
        assert cov["gap_after"] < cov["gap_before"]

    def test_gap_before_37(self, cov):
        assert cov["gap_before"] == 37

    def test_gap_after_19(self, cov):
        assert cov["gap_after"] == 19

    def test_inserted_2024_records_18(self, cov):
        assert cov["inserted_2024_records"] == 18

    def test_symbols_with_2024_after_81(self, cov):
        assert cov["symbols_with_2024_after"] == 81

    def test_wrong_year_zero(self, cov):
        assert cov["wrong_year"] == 0

    def test_wrong_type_zero(self, cov):
        assert cov["wrong_type"] == 0

    def test_third_party_zero(self, cov):
        assert cov["third_party"] == 0

    def test_duplicate_active_zero(self, cov):
        assert cov["duplicate_active"] == 0

    def test_provenance_complete(self, cov):
        assert cov["provenance_complete"] is True

    def test_three_year_complete_meets_target(self, cov):
        target = cov["coverage_target_update"]["three_year_complete_target"]
        after = cov["coverage_target_update"]["three_year_complete_after"]
        assert after >= target

    def test_coverage_target_passed(self, cov):
        assert cov["coverage_target_update"]["three_year_complete_passed"] is True

    def test_remaining_breakdown_sums_to_19(self, cov):
        total = sum(cov["remaining_breakdown"].values())
        assert total == 19


# ---------------------------------------------------------------------------
# 8. Exact Year Regression
# ---------------------------------------------------------------------------
class TestExactYearRegression:
    @pytest.fixture
    def reg(self):
        return load("pi_official_report_p113a_2024_regression.json")

    def test_total_cases_gte_114(self, reg):
        assert reg["summary"]["total_cases"] >= 114

    def test_all_cases_passed(self, reg):
        assert reg["summary"]["passed"] == reg["summary"]["total_cases"]

    def test_failed_zero(self, reg):
        assert reg["summary"]["failed"] == 0

    def test_wrong_year_zero(self, reg):
        assert reg["zero_tolerance_results"]["wrong_year"] == 0

    def test_wrong_type_zero(self, reg):
        assert reg["zero_tolerance_results"]["wrong_report_type"] == 0

    def test_provider_calls_serving_zero(self, reg):
        assert reg["serving_metrics"]["provider_calls"] == 0

    def test_full_scans_zero(self, reg):
        assert reg["serving_metrics"]["full_scans"] == 0

    def test_no_fallback_to_other_year(self, reg):
        assert reg["zero_tolerance_results"]["wrong_year_fallback"] == 0

    def test_unavailable_correctness_1(self, reg):
        assert reg["summary"]["unavailable_correctness_rate"] == 1.0

    def test_2023_control_pass(self, reg):
        ctrl = reg.get("control_cases_2023", {})
        assert ctrl.get("all_pass") is True

    def test_2022_control_pass(self, reg):
        ctrl = reg.get("control_cases_2022", {})
        assert ctrl.get("all_pass") is True

    def test_2023_control_count(self, reg):
        assert reg["control_cases_2023"]["count"] == 20

    def test_2022_control_count(self, reg):
        assert reg["control_cases_2022"]["count"] == 20

    def test_newly_available_18(self, reg):
        assert reg["newly_available_2024_cases"]["count"] == 18

    def test_newly_available_all_pass(self, reg):
        assert reg["newly_available_2024_cases"]["all_pass"] is True

    def test_still_unavailable_19(self, reg):
        assert reg["still_unavailable_2024_cases"]["count"] == 19

    def test_still_unavailable_no_wrong_fallback(self, reg):
        assert reg["still_unavailable_2024_cases"]["no_wrong_fallback"] is True

    def test_wrong_company_zero(self, reg):
        assert reg["zero_tolerance_results"]["wrong_company"] == 0

    def test_fabricated_url_zero(self, reg):
        assert reg["zero_tolerance_results"]["fabricated_url"] == 0


# ---------------------------------------------------------------------------
# 9. Shadow Regression
# ---------------------------------------------------------------------------
class TestShadowRegression:
    @pytest.fixture
    def shadow(self):
        return load("pi_official_report_p113a_shadow_regression.json")

    def test_rollout_5_percent(self, shadow):
        assert shadow["rollout_config"]["staging_shadow_rollout_percent"] == 5

    def test_selected_gte_100(self, shadow):
        assert shadow["selection"]["selected"] >= 100

    def test_2024_targeted_gte_50(self, shadow):
        assert shadow["selection"].get("targeted_2024", 0) >= 50

    def test_unique_symbols_gte_37(self, shadow):
        assert shadow["selection"]["unique_symbols"] >= 37

    def test_query_styles_gte_6(self, shadow):
        assert shadow["selection"].get("query_styles", 0) >= 6

    def test_multi_turn_gte_10(self, shadow):
        assert shadow["selection"].get("multi_turn", 0) >= 10

    def test_safety_correctness_1(self, shadow):
        assert shadow["safety_metrics"]["safety_correctness"] == 1.0

    def test_wrong_year_zero(self, shadow):
        assert shadow["accuracy_metrics"]["wrong_year_count"] == 0

    def test_wrong_report_type_zero(self, shadow):
        assert shadow["accuracy_metrics"]["wrong_report_type_count"] == 0

    def test_fabricated_url_zero(self, shadow):
        assert shadow["accuracy_metrics"]["fabricated_url_count"] == 0

    def test_trace_mismatch_zero(self, shadow):
        assert shadow["accuracy_metrics"]["trace_mismatch_count"] == 0

    def test_pi_business_write_zero(self, shadow):
        assert shadow["write_safety_metrics"]["pi_business_write_count"] == 0

    def test_assistant_double_write_zero(self, shadow):
        assert shadow["write_safety_metrics"]["assistant_double_write_count"] == 0

    def test_unknown_owner_write_zero(self, shadow):
        assert shadow["write_safety_metrics"]["unknown_owner_write_count"] == 0

    def test_raw500_zero(self, shadow):
        assert shadow["reliability_metrics"]["raw500_count"] == 0

    def test_raw503_zero(self, shadow):
        assert shadow["reliability_metrics"]["raw503_count"] == 0

    def test_timeout_rate_lte_1pct(self, shadow):
        assert shadow["reliability_metrics"]["timeout_rate"] <= 0.01

    def test_fallback_rate_lte_10pct(self, shadow):
        assert shadow["reliability_metrics"]["fallback_rate"] <= 0.10

    def test_tool_p95_lte_4s(self, shadow):
        assert shadow["performance_metrics"]["tool_p95_ms"] <= 4000

    def test_task_leak_zero(self, shadow):
        assert shadow["resource_metrics"]["task_leak_count"] == 0

    def test_db_leak_zero(self, shadow):
        assert shadow["resource_metrics"]["db_leak_count"] == 0

    def test_pending_rollback_zero(self, shadow):
        assert shadow["resource_metrics"]["pending_rollback_errors"] == 0

    def test_not_raise_to_10pct(self, shadow):
        assert shadow["rollout_config"].get("recommended_to_raise_to_ten_percent") is False

    def test_live_false(self, shadow):
        assert shadow["rollout_config"].get("live_serving") is False

    def test_production_false(self, shadow):
        assert shadow["rollout_config"].get("production_enabled") is False

    def test_canary_mode_shadow(self, shadow):
        assert shadow["rollout_config"]["canary_mode"] == "shadow"

    def test_newly_available_correctly_served(self, shadow):
        nav = shadow["newly_available_shadow_results"]
        assert nav["wrong_year_in_shadow"] == 0
        assert nav["unavailable_mistakenly_returned"] == 0


# ---------------------------------------------------------------------------
# 10. Final Gate
# ---------------------------------------------------------------------------
class TestFinalGate:
    @pytest.fixture
    def gate(self):
        return load("pi_official_report_p113a_final_gate.json")

    def test_starting_gap_37(self, gate):
        assert gate["starting_2024_gap_count"] == 37

    def test_verified_added_18(self, gate):
        assert gate["verified_2024_records_added"] == 18

    def test_remaining_gap_19(self, gate):
        assert gate["remaining_2024_gap_count"] == 19

    def test_quality_gate_passed(self, gate):
        assert gate["quality_gate_passed"] is True

    def test_idempotency_passed(self, gate):
        assert gate["idempotency_passed"] is True

    def test_exact_year_regression_passed(self, gate):
        assert gate["exact_year_regression_passed"] is True

    def test_exact_year_cases_gte_114(self, gate):
        assert gate["exact_year_cases"] >= 114

    def test_shadow_selected_gte_100(self, gate):
        assert gate["shadow_selected_requests"] >= 100

    def test_shadow_2024_targeted_gte_50(self, gate):
        assert gate["shadow_2024_targeted"] >= 50

    def test_safety_1(self, gate):
        assert gate["shadow_safety_correctness"] == 1.0

    def test_wrong_year_zero(self, gate):
        assert gate["wrong_year_count"] == 0

    def test_wrong_type_zero(self, gate):
        assert gate["wrong_type_count"] == 0

    def test_fabricated_url_zero(self, gate):
        assert gate["fabricated_url_count"] == 0

    def test_trace_mismatch_zero(self, gate):
        assert gate["trace_mismatch_count"] == 0

    def test_pi_business_write_zero(self, gate):
        assert gate["pi_business_write_count"] == 0

    def test_rollout_5pct(self, gate):
        assert gate["rollout_percent"] == 5

    def test_staging_rollout_5pct(self, gate):
        assert gate["staging_shadow_rollout_percent"] == 5

    def test_not_raise_to_10pct(self, gate):
        assert gate["recommended_to_raise_to_ten_percent"] is False

    def test_live_false(self, gate):
        assert gate["recommended_for_live_serving"] is False

    def test_production_false(self, gate):
        assert gate["recommended_for_production"] is False

    def test_production_enabled_false(self, gate):
        assert gate["production_enabled"] is False

    def test_live_serving_false(self, gate):
        assert gate["live_serving"] is False

    def test_continue_5pct(self, gate):
        assert gate["recommended_to_continue_five_percent"] is True

    def test_db_environment_staging(self, gate):
        assert gate["db_identity"]["environment"] == "staging"

    def test_db_production_disabled(self, gate):
        assert gate["db_identity"]["production_enabled"] is False

    def test_task_leak_zero(self, gate):
        assert gate["task_leak_count"] == 0

    def test_db_leak_zero(self, gate):
        assert gate["db_leak_count"] == 0

    def test_pending_rollback_zero(self, gate):
        assert gate["pending_rollback_error_count"] == 0

    def test_stale_review_delta_zero(self, gate):
        assert gate["stale_review_delta"] == 0

    def test_stale_wrong_selection_zero(self, gate):
        assert gate["stale_wrong_selection_count"] == 0


# ---------------------------------------------------------------------------
# 11. Fixture Validation
# ---------------------------------------------------------------------------
class TestFixture:
    @pytest.fixture
    def fix(self):
        return load_fixture("official_report_2024_gap_regression_v1.json")

    def test_total_cases_gte_75(self, fix):
        assert fix["total_cases"] >= 75

    def test_cases_list_matches_total(self, fix):
        assert len(fix["cases"]) == fix["total_cases"]

    def test_newly_available_count_18(self, fix):
        na = [c for c in fix["cases"] if c["category"] == "newly_available"]
        assert len(na) == 18

    def test_genuinely_unavailable_count_19(self, fix):
        gu = [c for c in fix["cases"] if c["category"] == "genuinely_unavailable"]
        assert len(gu) == 19

    def test_control_2023_count_20(self, fix):
        ctrl = [c for c in fix["cases"] if c["category"] == "control_2023"]
        assert len(ctrl) == 20

    def test_control_2022_count_20(self, fix):
        ctrl = [c for c in fix["cases"] if c["category"] == "control_2022"]
        assert len(ctrl) == 20

    def test_newly_available_all_success(self, fix):
        for c in fix["cases"]:
            if c["category"] == "newly_available":
                assert c["expected_status"] == "success"
                assert c["expected_report_year"] == 2024

    def test_unavailable_all_must_not_fallback(self, fix):
        for c in fix["cases"]:
            if c["category"] == "genuinely_unavailable":
                assert c["must_not_fallback"] is True
                assert c["expected_status"] == "unavailable"

    def test_all_cases_have_symbol(self, fix):
        for c in fix["cases"]:
            assert "symbol" in c and c["symbol"]

    def test_all_cases_have_category(self, fix):
        for c in fix["cases"]:
            assert "category" in c and c["category"]

    def test_phase_p113a(self, fix):
        assert fix["phase"] == "6V-P1.13A"


# ---------------------------------------------------------------------------
# 12. Unavailable Analysis
# ---------------------------------------------------------------------------
class TestUnavailableAnalysis:
    @pytest.fixture
    def ana(self):
        return load("pi_official_report_p113a_unavailable_analysis.json")

    def test_before_gap_37(self, ana):
        assert ana["before_fill"]["total_2024_gaps"] == 37

    def test_after_gap_19(self, ana):
        assert ana["after_fill"]["total_2024_gaps"] == 19

    def test_fillable_before_18(self, ana):
        assert ana["before_fill"]["fillable_count"] == 18

    def test_fillable_after_0(self, ana):
        assert ana["after_fill"]["fillable_count"] == 0

    def test_gaps_eliminated_18(self, ana):
        assert ana["gap_reduction"]["gaps_eliminated"] == 18

    def test_no_wrong_data_inserted(self, ana):
        assert ana["quality_confirmation"]["zero_wrong_data_inserted"] is True

    def test_unavailable_correctly_served(self, ana):
        assert ana["quality_confirmation"]["unavailable_correctly_served"] is True

    def test_no_fabricated_urls(self, ana):
        assert ana["quality_confirmation"]["no_fabricated_urls"] is True


# ---------------------------------------------------------------------------
# 13. Stale Review Audit
# ---------------------------------------------------------------------------
class TestStaleReviewAudit:
    @pytest.fixture
    def stale(self):
        return load("pi_official_report_p113a_stale_review_audit.json")

    def test_stale_review_before_3(self, stale):
        assert stale["stale_review_before_fill"] == 3

    def test_stale_review_after_3(self, stale):
        assert stale["stale_review_after_fill"] == 3

    def test_stale_delta_zero(self, stale):
        assert stale["stale_review_delta"] == 0

    def test_new_stale_from_insert_zero(self, stale):
        assert stale["new_stale_from_2024_insert"] == 0

    def test_newly_inserted_all_healthy(self, stale):
        assert stale["newly_inserted_records_stale_status"]["healthy_count"] == 18
        assert stale["newly_inserted_records_stale_status"]["stale_review_count"] == 0

    def test_gate_passed(self, stale):
        assert stale["stale_review_gate_passed"] is True

    def test_wrong_selection_zero(self, stale):
        assert stale["stale_wrong_selection_count"] == 0

    def test_no_stale_activated(self, stale):
        assert stale["stale_records_newly_activated"] == 0


# ---------------------------------------------------------------------------
# 14. Safety Audit
# ---------------------------------------------------------------------------
class TestSafetyAudit:
    @pytest.fixture
    def safety(self):
        return load("pi_official_report_p113a_safety_audit.json")

    def test_safety_correctness_1(self, safety):
        assert safety["safety_correctness"] == 1.0

    def test_harmful_content_zero(self, safety):
        assert safety["harmful_content_count"] == 0

    def test_pii_leak_zero(self, safety):
        assert safety["pii_leak_count"] == 0

    def test_wrong_year_zero(self, safety):
        assert safety["wrong_year_count"] == 0

    def test_fabricated_url_zero(self, safety):
        assert safety["fabricated_url_count"] == 0

    def test_zero_tolerance_violations_zero(self, safety):
        assert safety["zero_tolerance_violations"] == 0

    def test_gate_passed(self, safety):
        assert safety["safety_gate_passed"] is True

    def test_newly_inserted_safety_passed(self, safety):
        assert safety["newly_inserted_records_safety"]["all_safety_checks_passed"] is True


# ---------------------------------------------------------------------------
# 15. Write Audit
# ---------------------------------------------------------------------------
class TestWriteAudit:
    @pytest.fixture
    def write(self):
        return load("pi_official_report_p113a_write_audit.json")

    def test_pi_business_write_zero(self, write):
        assert write["pi_business_write_count"] == 0

    def test_assistant_double_writes_zero(self, write):
        assert write["assistant_double_writes"] == 0

    def test_unknown_writes_zero(self, write):
        assert write["unknown_writes"] == 0

    def test_write_audit_passed(self, write):
        assert write["write_audit_passed"] is True

    def test_dry_run_business_writes_zero(self, write):
        assert write["write_audit_details"]["dry_run_phase"]["business_writes"] == 0

    def test_shadow_pi_write_zero(self, write):
        assert write["write_audit_details"]["shadow_regression_phase"]["pi_business_write_count"] == 0


# ---------------------------------------------------------------------------
# 16. Resource Audit
# ---------------------------------------------------------------------------
class TestResourceAudit:
    @pytest.fixture
    def res(self):
        return load("pi_official_report_p113a_resource_audit.json")

    def test_task_leak_zero(self, res):
        assert res["task_leak"] == 0

    def test_db_leak_zero(self, res):
        assert res["db_leak"] == 0

    def test_pending_rollback_zero(self, res):
        assert res["PendingRollbackError"] == 0

    def test_raw500_zero(self, res):
        assert res["raw_500_count"] == 0

    def test_raw503_zero(self, res):
        assert res["raw_503_count"] == 0

    def test_resource_audit_passed(self, res):
        assert res["resource_audit_passed"] is True

    def test_all_phases_clean(self, res):
        for phase_name, phase_data in res["phase_breakdown"].items():
            assert phase_data["task_leak"] == 0, f"task_leak in {phase_name}"
            assert phase_data["db_leak"] == 0, f"db_leak in {phase_name}"
            assert phase_data["PendingRollbackError"] == 0, f"PendingRollbackError in {phase_name}"
