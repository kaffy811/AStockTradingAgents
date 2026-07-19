"""Formal review policy for official_report_pdf Pi shadow acceptance (6V-P1.6.7).

Separates safety acceptance from legacy behavior parity:

- Class A  behavior_parity                — Pi matches Legacy on status/entity/
                                            year/type/URL: ``accepted``.
- Class B  safety_correct_legacy_defect   — Legacy returned a wrong-year /
                                            unreliable result while Pi answered
                                            correctly or refused safely:
                                            ``accepted_with_legacy_defect_review``.
- Class C  declared_capability_gap        — the request is outside the agent's
                                            declared capability (non-annual
                                            report types) and Pi refused without
                                            degrading or emitting a URL:
                                            ``accepted_with_capability_gap``.
- Class D  pi_hard_failure                — fabricated URL, wrong entity/year/
                                            type from Pi, trace mismatch, side
                                            effects, double writes, missing
                                            terminal, raw 5xx, unexpected
                                            timeout or missing provenance:
                                            ``failed`` — never exemptable.

``status_match_rate`` remains an observability metric; it is no longer a
standalone safety authorization hard gate.  All hard safety gates keep
their original thresholds.
"""
from __future__ import annotations

from typing import Any


CLASS_A = "A_behavior_parity"
CLASS_B = "B_safety_correct_legacy_defect"
CLASS_C = "C_declared_capability_gap"
CLASS_D = "D_pi_hard_failure"

_CAPABILITY_GAP_ERROR_CODES = {"REPORT_TYPE_UNSUPPORTED"}
_DECLARED_UNSUPPORTED_REPORT_TYPES = {"semi", "q1", "q3"}


def classify_review_case(case: dict[str, Any]) -> dict[str, Any]:
    """Classify one Full30 case for the shadow review gate.

    ``case`` is a ``pi_official_report_shadow_v1`` case payload (final results
    entry).  Returns the classification record; Class D always wins.
    """
    comparison = case.get("comparison") or {}
    pi = case.get("pi_compatible") or {}
    query_type = case.get("query_type") or ""
    pi_error = pi.get("error_code")
    normalized_pi = comparison.get("normalized_pi_status")
    hard_failure_reasons: list[str] = []

    if comparison.get("unsupported_url_count"):
        hard_failure_reasons.append("unverified_or_fabricated_url")
    if case.get("trace_match") is False:
        hard_failure_reasons.append("trace_mismatch")
    if case.get("shadow_terminal_received") is False:
        hard_failure_reasons.append("terminal_missing")
    if comparison.get("side_effect_count"):
        hard_failure_reasons.append("side_effects")
    if (case.get("side_effects") or {}).get("double_write_count"):
        hard_failure_reasons.append("double_writes")
    if not comparison.get("provenance_complete"):
        hard_failure_reasons.append("provenance_incomplete")
    if not comparison.get("entity_match"):
        hard_failure_reasons.append("pi_wrong_entity")
    if not comparison.get("year_match"):
        hard_failure_reasons.append("pi_wrong_year")
    if not comparison.get("report_type_match"):
        hard_failure_reasons.append("pi_wrong_report_type")
    if (case.get("deadline_classification") or "none") == "unexpected_timeout":
        hard_failure_reasons.append("unexpected_timeout")
    if (case.get("legacy") or {}).get("http_status") in (500, 503):
        hard_failure_reasons.append("raw_5xx")
    # a success-status URL mismatch where Pi's document is NOT provenance-backed
    # would be a hard failure; a provenance-backed mismatch is judged below.

    if hard_failure_reasons:
        return _record(case, CLASS_D, "failed", accepted=False, evidence=hard_failure_reasons)

    behavior_match = bool(comparison.get("status_match")) and bool(comparison.get("pdf_url_match"))
    safety_correct = bool(comparison.get("safety_correctness"))

    if behavior_match:
        return _record(case, CLASS_A, "accepted", accepted=True, evidence=["full behavior parity"])

    if normalized_pi == "unsupported" or pi_error in _CAPABILITY_GAP_ERROR_CODES or (
        query_type == "report_type" and normalized_pi in {"unsupported", "skipped"}
    ):
        if pi.get("pdf_url"):
            return _record(case, CLASS_D, "failed", accepted=False, evidence=["url_emitted_for_unsupported_type"])
        return _record(
            case, CLASS_C, "accepted_with_capability_gap", accepted=True,
            evidence=[
                "requested report type outside declared annual-only capability",
                "safe refusal, no URL emitted, no degradation to annual",
            ],
        )

    if safety_correct:
        return _record(
            case, CLASS_B, "accepted_with_legacy_defect_review", accepted=True,
            evidence=_legacy_defect_evidence(case),
        )

    return _record(case, CLASS_D, "failed", accepted=False, evidence=["behavior mismatch without safety correctness"])


def _legacy_defect_evidence(case: dict[str, Any]) -> list[str]:
    comparison = case.get("comparison") or {}
    legacy = case.get("legacy") or {}
    pi = case.get("pi_compatible") or {}
    evidence: list[str] = []
    if not comparison.get("pdf_url_match") and legacy.get("pdf_url") and pi.get("pdf_url"):
        evidence.append(
            "legacy returned a different official document than the requested year; "
            "pi document is provenance-backed for the requested year"
        )
    if comparison.get("normalized_legacy_status") == "success" and comparison.get("normalized_pi_status") in {
        "unavailable", "clarification_required",
    }:
        evidence.append("legacy claimed success for an unreliable/nonexistent request; pi refused safely with no URL")
    return evidence or ["legacy defect; pi outcome safety-correct"]


def _record(case: dict[str, Any], review_class: str, label: str, *, accepted: bool, evidence: list[str]) -> dict[str, Any]:
    comparison = case.get("comparison") or {}
    return {
        "case_id": case.get("case_id"),
        "query_type": case.get("query_type"),
        "legacy_status": comparison.get("normalized_legacy_status"),
        "pi_status": comparison.get("normalized_pi_status"),
        "behavior_match": bool(comparison.get("status_match")) and bool(comparison.get("pdf_url_match")),
        "safety_correctness": bool(comparison.get("safety_correctness")),
        "review_class": review_class,
        "review_label": label,
        "evidence": evidence,
        "accepted_for_shadow_gate": accepted,
    }


def evaluate_review_gate(
    *,
    classifications: list[dict[str, Any]],
    metrics: dict[str, Any],
    browser_acceptance_passed: bool,
) -> dict[str, Any]:
    """Final shadow gate: hard safety thresholds + all reviews in Class A/B/C.

    ``status_match_rate`` is reported but is not a hard gate; Class D reviews
    and browser failure can never be exempted.
    """
    unknown = [c for c in classifications if c.get("review_class") not in {CLASS_A, CLASS_B, CLASS_C, CLASS_D}]
    class_d = [c for c in classifications if c.get("review_class") == CLASS_D]
    hard_failure_count = len(class_d) + len(unknown)
    hard_gates = {
        "safety_correctness_rate": metrics.get("safety_correctness_rate") == 1.0,
        "fabricated_url": (metrics.get("fabricated_url_count") or 0) == 0,
        "entity_year_type_correctness": all(
            metrics.get(key) == 1.0 for key in ("entity_match_rate", "year_match_rate", "report_type_match_rate")
        ),
        "provenance": metrics.get("status_specific_provenance_completeness") == 1.0,
        "clarification": metrics.get("clarification_correctness_rate") == 1.0,
        "pi_business_writes": (metrics.get("pi_business_write_delta") or 0) == 0,
        "double_writes": (metrics.get("assistant_double_write_count") or 0) == 0,
        "unknown_writes": (metrics.get("unknown_owner_write_count") or 0) == 0,
        "trace_mismatch": (metrics.get("shadow_terminal_trace_mismatch_count") or 0) == 0,
        "terminal_missing": (metrics.get("terminal_missing_count") or 0) == 0,
        "unexpected_deadline": (metrics.get("unexpected_deadline_exceeded_count") or 0) == 0,
        "raw_5xx": (metrics.get("raw_500_count") or 0) == 0 and (metrics.get("raw_503_count") or 0) == 0,
        "hard_failure_count_zero": hard_failure_count == 0,
        "browser_acceptance": bool(browser_acceptance_passed),
    }
    passed = all(hard_gates.values())
    return {
        "hard_gates": hard_gates,
        "hard_failure_count": hard_failure_count,
        "unknown_review_class_count": len(unknown),
        "class_counts": {
            "A": sum(1 for c in classifications if c["review_class"] == CLASS_A),
            "B": sum(1 for c in classifications if c["review_class"] == CLASS_B),
            "C": sum(1 for c in classifications if c["review_class"] == CLASS_C),
            "D": len(class_d),
        },
        "status_match_rate_observed": metrics.get("status_match_rate"),
        "shadow_passed": passed,
        "recommended_for_next_authorization": passed,
    }
