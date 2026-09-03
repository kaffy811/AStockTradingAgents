"""Phase 6V-P1.6.7 — review policy / final shadow gate calculator tests."""
from __future__ import annotations

from app.agent_runtime.shadow_review_policy import (
    CLASS_A,
    CLASS_B,
    CLASS_C,
    CLASS_D,
    classify_review_case,
    evaluate_review_gate,
)


def _case(**overrides):
    base = {
        "case_id": "X01",
        "query_type": "explicit_company_name",
        "trace_match": True,
        "shadow_terminal_received": True,
        "deadline_classification": "none",
        "legacy": {"http_status": 200, "pdf_url": "https://static.cninfo.com.cn/finalpage/a.PDF"},
        "pi_compatible": {"error_code": None, "pdf_url": "https://static.cninfo.com.cn/finalpage/a.PDF"},
        "side_effects": {"double_write_count": 0},
        "comparison": {
            "status_match": True,
            "pdf_url_match": True,
            "entity_match": True,
            "year_match": True,
            "report_type_match": True,
            "provenance_complete": True,
            "safety_correctness": True,
            "unsupported_url_count": 0,
            "side_effect_count": 0,
            "normalized_legacy_status": "success",
            "normalized_pi_status": "success",
        },
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = {**base[key], **value}
        else:
            base[key] = value
    return base


def _metrics(**overrides):
    metrics = {
        "safety_correctness_rate": 1.0,
        "fabricated_url_count": 0,
        "entity_match_rate": 1.0,
        "year_match_rate": 1.0,
        "report_type_match_rate": 1.0,
        "status_specific_provenance_completeness": 1.0,
        "clarification_correctness_rate": 1.0,
        "pi_business_write_delta": 0,
        "assistant_double_write_count": 0,
        "unknown_owner_write_count": 0,
        "shadow_terminal_trace_mismatch_count": 0,
        "terminal_missing_count": 0,
        "unexpected_deadline_exceeded_count": 0,
        "raw_500_count": 0,
        "raw_503_count": 0,
        "status_match_rate": 0.6333,
    }
    metrics.update(overrides)
    return metrics


def test_behavior_parity_is_class_a_accepted():
    record = classify_review_case(_case())
    assert record["review_class"] == CLASS_A and record["accepted_for_shadow_gate"]


def test_safety_correct_legacy_defect_class_b_passes_review():
    """Rule 1: behavior mismatch + safety correct => Class B review-pass."""
    record = classify_review_case(_case(comparison={
        "status_match": False, "normalized_legacy_status": "success",
        "normalized_pi_status": "unavailable", "safety_correctness": True,
    }, pi_compatible={"pdf_url": None}))
    assert record["review_class"] == CLASS_B and record["accepted_for_shadow_gate"]


def test_capability_gap_class_c_passes_review():
    """Rule 2: declared unsupported report type => Class C review-pass."""
    record = classify_review_case(_case(query_type="report_type", comparison={
        "status_match": False, "normalized_pi_status": "unsupported",
        "safety_correctness": True,
    }, pi_compatible={"error_code": "REPORT_TYPE_UNSUPPORTED", "pdf_url": None}))
    assert record["review_class"] == CLASS_C and record["accepted_for_shadow_gate"]


def test_fabricated_url_never_review_passes():
    """Rule 3."""
    record = classify_review_case(_case(comparison={"unsupported_url_count": 1}))
    assert record["review_class"] == CLASS_D and not record["accepted_for_shadow_gate"]


def test_wrong_pi_year_never_review_passes():
    """Rule 4."""
    record = classify_review_case(_case(comparison={"year_match": False}))
    assert record["review_class"] == CLASS_D and "pi_wrong_year" in record["evidence"]


def test_trace_mismatch_never_review_passes():
    """Rule 5."""
    record = classify_review_case(_case(trace_match=False))
    assert record["review_class"] == CLASS_D and "trace_mismatch" in record["evidence"]


def test_business_write_never_review_passes():
    """Rule 6."""
    record = classify_review_case(_case(comparison={"side_effect_count": 2}))
    assert record["review_class"] == CLASS_D and "side_effects" in record["evidence"]


def test_browser_not_run_fails_gate():
    """Rule 7."""
    gate = evaluate_review_gate(
        classifications=[classify_review_case(_case())],
        metrics=_metrics(),
        browser_acceptance_passed=False,
    )
    assert not gate["shadow_passed"] and not gate["hard_gates"]["browser_acceptance"]


def test_every_review_must_be_classified_and_unknown_class_fails():
    """Rules 8+9: unknown review class => hard failure => gate fail."""
    bogus = {"case_id": "Z", "review_class": "E_mystery", "accepted_for_shadow_gate": True}
    gate = evaluate_review_gate(
        classifications=[classify_review_case(_case()), bogus],
        metrics=_metrics(),
        browser_acceptance_passed=True,
    )
    assert gate["unknown_review_class_count"] == 1
    assert gate["hard_failure_count"] == 1
    assert not gate["shadow_passed"]


def test_status_match_observed_but_not_a_hard_gate():
    """Rule 10: low status_match_rate alone no longer blocks a safe gate."""
    gate = evaluate_review_gate(
        classifications=[
            classify_review_case(_case()),
            classify_review_case(_case(comparison={
                "status_match": False, "normalized_pi_status": "unavailable",
                "safety_correctness": True,
            }, pi_compatible={"pdf_url": None})),
        ],
        metrics=_metrics(status_match_rate=0.5),
        browser_acceptance_passed=True,
    )
    assert gate["status_match_rate_observed"] == 0.5
    assert gate["shadow_passed"]
    # but safety hard gates still bind
    gate_bad = evaluate_review_gate(
        classifications=[classify_review_case(_case())],
        metrics=_metrics(safety_correctness_rate=0.9),
        browser_acceptance_passed=True,
    )
    assert not gate_bad["shadow_passed"]
