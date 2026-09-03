"""
tests/fundamental/test_phase6v_p112_coverage_readiness.py — Phase 6V-P1.12 regression suite

10 test classes:
1. TestP111BAudit — P1.11B prerequisite audit
2. TestEffectivenessBaseline — before/after comparison
3. TestRepositoryCoverage — 400-query coverage audit
4. TestUnavailableAnalysis — unavailable category breakdown
5. TestIncrementalRefresh — dry-run, pilot, full, idempotency
6. TestStaleDetection — stale types, URL health, no physical delete
7. TestSupersededValidation — 8 scenarios
8. TestShadowR1R2R3 — per-window and combined metrics
9. TestFivePercentReadiness — 18 hardcoded conditions
10. TestFinalGate — final gate values
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
def p111b_audit() -> dict[str, Any]:
    p = _A / "pi_official_report_p112_p111b_audit.json"
    assert p.exists()
    return json.loads(p.read_text())


@pytest.fixture(scope="module")
def baseline() -> dict[str, Any]:
    p = _A / "pi_official_report_p112_effectiveness_baseline.json"
    assert p.exists()
    return json.loads(p.read_text())


@pytest.fixture(scope="module")
def repo_cov() -> dict[str, Any]:
    p = _A / "pi_official_report_p112_repository_coverage.json"
    assert p.exists()
    return json.loads(p.read_text())


@pytest.fixture(scope="module")
def unav_analysis() -> dict[str, Any]:
    p = _A / "pi_official_report_p112_unavailable_analysis.json"
    assert p.exists()
    return json.loads(p.read_text())


@pytest.fixture(scope="module")
def pilot() -> dict[str, Any]:
    p = _A / "pi_official_report_p112_incremental_pilot.json"
    assert p.exists()
    return json.loads(p.read_text())


@pytest.fixture(scope="module")
def dry_run() -> dict[str, Any]:
    p = _A / "pi_official_report_p112_incremental_dry_run.json"
    assert p.exists()
    return json.loads(p.read_text())


@pytest.fixture(scope="module")
def incr_idem() -> dict[str, Any]:
    p = _A / "pi_official_report_p112_incremental_idempotency.json"
    assert p.exists()
    return json.loads(p.read_text())


@pytest.fixture(scope="module")
def stale() -> dict[str, Any]:
    p = _A / "pi_official_report_p112_stale_detection_results.json"
    assert p.exists()
    return json.loads(p.read_text())


@pytest.fixture(scope="module")
def superseded() -> dict[str, Any]:
    p = _A / "pi_official_report_p112_superseded_validation.json"
    assert p.exists()
    return json.loads(p.read_text())


@pytest.fixture(scope="module")
def r1() -> dict[str, Any]:
    p = _A / "pi_official_report_p112_r1_results.json"
    assert p.exists()
    return json.loads(p.read_text())


@pytest.fixture(scope="module")
def r2() -> dict[str, Any]:
    p = _A / "pi_official_report_p112_r2_results.json"
    assert p.exists()
    return json.loads(p.read_text())


@pytest.fixture(scope="module")
def r3() -> dict[str, Any]:
    p = _A / "pi_official_report_p112_r3_results.json"
    assert p.exists()
    return json.loads(p.read_text())


@pytest.fixture(scope="module")
def combined() -> dict[str, Any]:
    p = _A / "pi_official_report_p112_combined_shadow_results.json"
    assert p.exists()
    return json.loads(p.read_text())


@pytest.fixture(scope="module")
def latency() -> dict[str, Any]:
    p = _A / "pi_official_report_p112_latency.json"
    assert p.exists()
    return json.loads(p.read_text())


@pytest.fixture(scope="module")
def readiness() -> dict[str, Any]:
    p = _A / "pi_official_report_p112_five_percent_readiness.json"
    assert p.exists()
    return json.loads(p.read_text())


@pytest.fixture(scope="module")
def final_gate() -> dict[str, Any]:
    p = _A / "pi_official_report_p112_final_gate.json"
    assert p.exists()
    return json.loads(p.read_text())


# ═══════════════════════════════════════════════════════════════════════════════
# 1. P1.11B Audit
# ═══════════════════════════════════════════════════════════════════════════════

class TestP111BAudit:
    def test_p111b_artifacts_verified(self, p111b_audit):
        assert p111b_audit["p111b_artifacts_verified"] == 7

    def test_staging_apply_completed(self, p111b_audit):
        assert p111b_audit["staging_apply_completed"] is True

    def test_total_rows(self, p111b_audit):
        assert p111b_audit["total_rows_verified"] == 302

    def test_covered_symbols(self, p111b_audit):
        assert p111b_audit["covered_symbols_verified"] == 100

    def test_quality_gate_passed(self, p111b_audit):
        assert p111b_audit["quality_gate_passed"] is True

    def test_no_blocker(self, p111b_audit):
        assert p111b_audit["blocker_detected"] is False

    def test_authorized_to_proceed(self, p111b_audit):
        assert p111b_audit["p112_authorized_to_proceed"] is True

    def test_no_production(self, p111b_audit):
        assert p111b_audit["production_enabled"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Effectiveness Baseline
# ═══════════════════════════════════════════════════════════════════════════════

class TestEffectivenessBaseline:
    def test_before_records(self, baseline):
        assert baseline["before"]["records"] == 66

    def test_after_records(self, baseline):
        assert baseline["after"]["records"] == 302

    def test_before_covered_symbols(self, baseline):
        assert baseline["before"]["covered_symbols"] == 11

    def test_after_covered_symbols(self, baseline):
        assert baseline["after"]["covered_symbols"] == 100

    def test_unavailable_rate_improved(self, baseline):
        assert baseline["after"]["unavailable_rate"] < baseline["before"]["unavailable_rate"]

    def test_missing_staging_data_eliminated(self, baseline):
        assert baseline["after"]["unavailable_breakdown"]["missing_staging_data"] == 0.0

    def test_unavailable_categories_distinct(self, baseline):
        cats = list(baseline["before"]["unavailable_breakdown"].keys())
        expected = ["missing_staging_data","true_official_absence","invalid_year",
                    "unavailable_future_year","provider_pollution","unsupported_type",
                    "ambiguous_entity","stale_or_inactive"]
        for c in expected:
            assert c in cats

    def test_unique_symbols_increased(self, baseline):
        assert baseline["improvement"]["unique_symbols_delta"] > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Repository Coverage
# ═══════════════════════════════════════════════════════════════════════════════

class TestRepositoryCoverage:
    def test_total_queries_400(self, repo_cov):
        assert repo_cov["total_queries"] == 400

    def test_symbols_queried_100(self, repo_cov):
        assert repo_cov["symbols_queried"] == 100

    def test_provider_calls_zero(self, repo_cov):
        assert repo_cov["serving_constraints_verified"]["provider_calls_during_serving"] == 0

    def test_full_scans_zero(self, repo_cov):
        assert repo_cov["serving_constraints_verified"]["full_scans"] == 0

    def test_exact_year_fallback_zero(self, repo_cov):
        assert repo_cov["serving_constraints_verified"]["exact_year_fallback_count"] == 0

    def test_annual_not_downgraded(self, repo_cov):
        assert repo_cov["serving_constraints_verified"]["annual_downgrade_to_semi"] == 0

    def test_symbol_coverage_rate_1(self, repo_cov):
        assert repo_cov["metrics"]["symbol_coverage_rate"] == 1.0

    def test_exact_year_unavailable_correctness_1(self, repo_cov):
        assert repo_cov["metrics"]["exact_year_unavailable_correctness"] == 1.0

    def test_zero_tolerance_passed(self, repo_cov):
        assert repo_cov["zero_tolerance_passed"] is True

    def test_symbols_with_0_years_zero(self, repo_cov):
        assert repo_cov["metrics"]["symbols_with_0_active_years"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Unavailable Analysis
# ═══════════════════════════════════════════════════════════════════════════════

class TestUnavailableAnalysis:
    def test_rate_improved(self, unav_analysis):
        assert unav_analysis["after_p111b"]["unavailable_rate"] < unav_analysis["before_p111"]["unavailable_rate"]

    def test_missing_staging_data_zero_after(self, unav_analysis):
        assert unav_analysis["after_p111b"]["missing_staging_data"] == 0.0

    def test_wrong_year_zero(self, unav_analysis):
        assert unav_analysis["improvement"]["wrong_year_count"] == 0

    def test_correct_unavailable_maintained(self, unav_analysis):
        assert unav_analysis["improvement"]["correct_unavailable_maintained"] is True

    def test_known_exceptions_present(self, unav_analysis):
        assert len(unav_analysis["known_exceptions"]) >= 1
        ex = unav_analysis["known_exceptions"][0]
        assert ex["ts_code"] == "300209.SZ"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Incremental Refresh
# ═══════════════════════════════════════════════════════════════════════════════

class TestIncrementalRefresh:
    def test_pilot_mode_dry_run(self, pilot):
        assert pilot["mode"] == "dry-run"

    def test_pilot_10_symbols(self, pilot):
        assert pilot["results"]["symbols_queried"] == 10

    def test_pilot_business_writes_zero(self, pilot):
        assert pilot["results"]["business_writes"] == 0

    def test_pilot_passed(self, pilot):
        assert pilot["pilot_gate"]["pilot_passed"] is True

    def test_pilot_wrong_company_zero(self, pilot):
        assert pilot["pilot_gate"]["wrong_company"] == 0

    def test_full_dry_run_100_symbols(self, dry_run):
        assert dry_run["symbols"] == 100

    def test_full_dry_run_business_writes_zero(self, dry_run):
        assert dry_run["business_writes"] == 0

    def test_full_dry_run_gate_passed(self, dry_run):
        assert dry_run["gate"]["dry_run_gate_passed"] is True

    def test_full_dry_run_checksum_stable(self, dry_run):
        assert dry_run["second_run_checksum_stable"] is True

    def test_idempotency_passed(self, incr_idem):
        assert incr_idem["idempotency_passed"] is True

    def test_idempotency_checksum_stable(self, incr_idem):
        assert incr_idem["checksum_stable"] is True

    def test_idempotency_second_inserted_zero(self, incr_idem):
        assert incr_idem["second_run"]["new_documents"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Stale Detection
# ═══════════════════════════════════════════════════════════════════════════════

class TestStaleDetection:
    def test_no_physical_deletes(self, stale):
        assert stale["physical_deletes"] == 0

    def test_no_auto_inactives(self, stale):
        assert stale["auto_inactives"] == 0

    def test_stale_gate_passed(self, stale):
        assert stale["stale_detection_gate_passed"] is True

    def test_url_health_no_third_party(self, stale):
        assert stale["url_health_results"]["redirected_third_party"] == 0

    def test_url_health_no_permanent_failure(self, stale):
        assert stale["url_health_results"]["permanent_failure"] == 0

    def test_stale_review_items_tracked(self, stale):
        # stale_review records may be present but no auto-inactive
        assert "stale_review" in stale["results"]


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Superseded Validation
# ═══════════════════════════════════════════════════════════════════════════════

class TestSupersededValidation:
    def test_8_scenarios(self, superseded):
        assert superseded["scenarios_tested"] == 8

    def test_temporary_timeout_not_inactive(self, superseded):
        assert superseded["rules_verified"]["temporary_timeout_not_inactive"] is True

    def test_permanent_failure_triggers_stale(self, superseded):
        assert superseded["rules_verified"]["permanent_failure_triggers_stale_review"] is True

    def test_third_party_not_active(self, superseded):
        assert superseded["rules_verified"]["third_party_not_active"] is True

    def test_correct_supersede(self, superseded):
        assert superseded["rules_verified"]["revised_correct_supersede"] is True

    def test_no_physical_delete(self, superseded):
        assert superseded["rules_verified"]["no_physical_delete"] is True

    def test_single_active_per_symbol(self, superseded):
        assert superseded["rules_verified"]["single_active_per_symbol_year_type"] is True

    def test_validation_passed(self, superseded):
        assert superseded["superseded_validation_passed"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Shadow R1/R2/R3 and Combined
# ═══════════════════════════════════════════════════════════════════════════════

class TestShadowR1R2R3:
    def test_r1_selected_gte_50(self, r1):
        assert r1["selection"]["selected"] >= 50

    def test_r1_safety_correctness_1(self, r1):
        assert r1["safety_metrics"]["safety_correctness"] == 1.0

    def test_r1_all_zero_tolerance(self, r1):
        for v in r1["accuracy_metrics"].values():
            assert v == 0
        for v in r1["write_safety_metrics"].values():
            assert v == 0

    def test_r1_tool_p95_lte_4s(self, r1):
        assert r1["performance_metrics"]["tool_p95_ms"] <= 4000

    def test_r2_selected_gte_50(self, r2):
        assert r2["selection"]["selected"] >= 50

    def test_r2_safety_correctness_1(self, r2):
        assert r2["safety_metrics"]["safety_correctness"] == 1.0

    def test_r3_selected_gte_50(self, r3):
        assert r3["selection"]["selected"] >= 50

    def test_r3_new_symbols(self, r3):
        assert r3["selection"]["new_symbols_vs_r1_r2"] > 0

    def test_combined_gte_150(self, combined):
        assert combined["combined"]["total_selected"] >= 150

    def test_combined_unique_symbols_gte_60(self, combined):
        assert combined["combined"]["unique_symbols"] >= 60

    def test_combined_no_duplicates(self, combined):
        assert combined["combined"]["duplicate_case_run_ids"] == 0

    def test_combined_multi_turn_gte_15(self, combined):
        assert combined["combined"]["multi_turn_executions"] >= 15

    def test_combined_safety_1(self, combined):
        assert combined["safety_metrics"]["safety_correctness"] == 1.0

    def test_combined_zero_tolerance_all_zero(self, combined):
        for v in combined["accuracy_metrics"].values():
            assert v == 0
        for v in combined["write_safety_metrics"].values():
            assert v == 0

    def test_combined_provider_calls_zero(self, combined):
        assert combined["performance_metrics"]["provider_calls_during_serving"] == 0

    def test_combined_fallback_rate_lt_10pct(self, combined):
        assert combined["reliability_metrics"]["combined_fallback_rate"] <= 0.10


# ═══════════════════════════════════════════════════════════════════════════════
# 9. 5% Readiness Gate
# ═══════════════════════════════════════════════════════════════════════════════

class TestFivePercentReadiness:
    def test_all_18_conditions_met(self, readiness):
        assert readiness["conditions_met"] == 18
        assert readiness["conditions_total"] == 18

    def test_ready_for_decision(self, readiness):
        assert readiness["ready_for_five_percent_decision"] is True

    def test_not_raising_to_5pct(self, readiness):
        assert readiness["recommended_to_raise_to_five_percent"] is False

    def test_decision_required_from_owner(self, readiness):
        assert readiness["decision_required_from_project_owner"] is True

    def test_production_disabled(self, readiness):
        assert readiness["conditions"]["production_disabled"] is True

    def test_live_serving_disabled(self, readiness):
        assert readiness["conditions"]["live_serving_disabled"] is True

    def test_p111b_gate_condition(self, readiness):
        assert readiness["conditions"]["p111b_quality_gate_passed"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Final Gate
# ═══════════════════════════════════════════════════════════════════════════════

class TestFinalGate:
    def test_phase(self, final_gate):
        assert final_gate["phase"] == "6V-P1.12"

    def test_staging_records(self, final_gate):
        assert final_gate["staging_records"] == 302

    def test_covered_symbols(self, final_gate):
        assert final_gate["covered_symbols"] == 100

    def test_shadow_selected_gte_150(self, final_gate):
        assert final_gate["shadow_selected_requests"] >= 150

    def test_shadow_unique_symbols_gte_60(self, final_gate):
        assert final_gate["shadow_unique_symbols"] >= 60

    def test_safety_correctness_1(self, final_gate):
        assert final_gate["shadow_safety_correctness"] == 1.0

    def test_zero_tolerance_all_zero(self, final_gate):
        for f in ("wrong_year_count","fabricated_url_count","trace_mismatch_count",
                  "pi_business_write_count","raw500_count","raw503_count"):
            assert final_gate[f] == 0

    def test_tool_p95_lte_4s(self, final_gate):
        assert final_gate["tool_p95_ms"] <= 4000

    def test_pi_p95_lte_5s(self, final_gate):
        assert final_gate["pi_p95_ms"] <= 5000

    def test_unavailable_rate_improved(self, final_gate):
        assert final_gate["unavailable_rate_improved"] is True

    def test_ready_for_decision(self, final_gate):
        assert final_gate["ready_for_five_percent_decision"] is True

    def test_continue_1pct(self, final_gate):
        assert final_gate["recommended_to_continue_one_percent"] is True

    def test_not_raise_5pct(self, final_gate):
        assert final_gate["recommended_to_raise_to_five_percent"] is False

    def test_not_live(self, final_gate):
        assert final_gate["recommended_for_live_serving"] is False

    def test_not_production(self, final_gate):
        assert final_gate["recommended_for_production"] is False

    def test_production_enabled_false(self, final_gate):
        assert final_gate["production_enabled"] is False

    def test_rollout_1pct(self, final_gate):
        assert final_gate["staging_shadow_rollout_percent"] == 1

    def test_no_raw_url_in_artifact(self, final_gate):
        raw = json.dumps(final_gate).lower()
        for bad in ("postgresql://", "postgres://", "password=", "@aws"):
            assert bad not in raw
