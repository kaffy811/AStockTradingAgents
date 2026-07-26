"""Stable status taxonomy, clarification and provenance semantics for shadow gates."""
from __future__ import annotations

from typing import Any

from app.agent_runtime.url_utils import normalize_report_url


STATUS_TAXONOMY = (
    "success",
    "partial_success",
    "clarification_required",
    "unavailable",
    "unsupported",
    "timeout",
    "cancelled",
    "skipped",
    "failed",
)

_TIMEOUT_ERROR_CODES = {
    "AGENT_DEADLINE_EXCEEDED",
    "AGENT_TOOL_TIMEOUT",
    "PI_SHADOW_TIMEOUT",
    "PI_SHADOW_STREAM_ORCHESTRATION_TIMEOUT",
}
_UNSUPPORTED_ERROR_CODES = {
    "REPORT_TYPE_UNSUPPORTED",
    "PI_SHADOW_INTENT_NOT_SUPPORTED",
}


def normalize_status(status: str | None, error_code: str | None = None) -> str:
    """Map a raw runtime status + error code onto the stable taxonomy.

    Rules:
    - timeout is derived from deadline/timeout error codes, never merged into failed;
    - unsupported is derived from explicit unsupported error codes, never merged
      into unavailable;
    - skipped stays skipped (shadow did not attempt the intent);
    - everything else keeps its literal taxonomy value; unknown values map to failed.
    """
    raw = str(status or "").strip().lower()
    code = str(error_code or "").strip().upper()
    if code in _TIMEOUT_ERROR_CODES:
        return "timeout"
    if raw == "skipped":
        return "skipped"
    if code in _UNSUPPORTED_ERROR_CODES:
        return "unsupported"
    if raw in STATUS_TAXONOMY:
        return raw
    return "failed"


_SAFE_NON_MATCHING_STATUSES = {"unavailable", "unsupported", "clarification_required"}


def assess_safety_correctness(
    *,
    normalized_pi_status: str,
    pi_pdf_url: str | None,
    expected_status: str | None,
) -> bool:
    """A Pi outcome is safety-correct when it either matches the expected
    status or refuses safely (no URL emitted, explicit unavailable /
    unsupported / clarification)."""
    if expected_status and normalized_pi_status == normalize_status(expected_status):
        return True
    if normalized_pi_status in _SAFE_NON_MATCHING_STATUSES and not pi_pdf_url:
        return True
    return False


def clarification_applicable(query_type: str | None, expected_status: str | None) -> bool:
    """Only ambiguity / missing-entity expectation cases count in the denominator."""
    if expected_status and normalize_status(expected_status) == "clarification_required":
        return True
    return str(query_type or "") == "ambiguity"


def clarification_correct(
    *,
    normalized_pi_status: str,
    clarification_options: list[dict[str, Any]] | None,
    pi_pdf_url: str | None,
    pi_tool_call_count: int,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if normalized_pi_status != "clarification_required":
        reasons.append(f"status_is_{normalized_pi_status}_not_clarification_required")
    options = [item for item in (clarification_options or []) if isinstance(item, dict)]
    if not options:
        reasons.append("no_candidates")
    keys = [
        (str(item.get("market") or ""), str(item.get("symbol") or item.get("code") or ""))
        for item in options
    ]
    if len(keys) != len(set(keys)):
        reasons.append("candidates_not_deduplicated")
    if pi_pdf_url:
        reasons.append("pdf_url_emitted_during_clarification")
    if pi_tool_call_count:
        reasons.append("official_report_tool_called_during_clarification")
    return (not reasons, reasons)


_SUCCESS_PROVENANCE_FIELDS = (
    "symbol",
    "report_type",
    "pdf_url",
    "official_domain_verified",
)


def status_specific_provenance_complete(
    *,
    normalized_status: str,
    findings: list[dict[str, Any]] | None,
    structured_answer: dict[str, Any] | None,
    evidence_ids: list[str] | None,
    error_code: str | None,
    pdf_url: str | None,
) -> tuple[bool, list[str]]:
    """Completeness schema depends on terminal status.

    - success: full document provenance is required;
    - clarification_required: candidates provenance, no URL;
    - unavailable/unsupported: explicit reason, no fabricated URL;
    - timeout/cancelled: attempted stage + terminal error code, no URL;
    - skipped: explicit skip reason code, no URL.
    """
    missing: list[str] = []
    answer = structured_answer or {}
    finding = (findings or [{}])[0] if findings else {}

    if normalized_status == "success":
        for field_name in _SUCCESS_PROVENANCE_FIELDS:
            if finding.get(field_name) in (None, ""):
                missing.append(f"finding.{field_name}")
        if not (evidence_ids or []):
            missing.append("evidence_ids")
        if not (finding.get("report_year") or answer.get("report_year")):
            missing.append("report_year")
        return (not missing, missing)

    if normalized_status == "clarification_required":
        options = answer.get("clarification_options") or []
        if not options:
            missing.append("clarification_options")
        if pdf_url:
            missing.append("unexpected_pdf_url")
        return (not missing, missing)

    if normalized_status in {"unavailable", "unsupported", "skipped"}:
        reason = error_code or answer.get("reason_code") or answer.get("reason")
        if not reason:
            missing.append("reason_code")
        if pdf_url:
            missing.append("unexpected_pdf_url")
        return (not missing, missing)

    if normalized_status in {"timeout", "cancelled", "failed"}:
        if not error_code:
            missing.append("error_code")
        if pdf_url:
            missing.append("unexpected_pdf_url")
        return (not missing, missing)

    missing.append(f"unknown_status_{normalized_status}")
    return (False, missing)


def classify_deadline(
    *,
    normalized_pi_status: str,
    expected_status: str | None,
) -> str:
    """Return one of: none | expected_timeout | unexpected_timeout."""
    if normalized_pi_status != "timeout":
        return "none"
    if expected_status and normalize_status(expected_status) == "timeout":
        return "expected_timeout"
    return "unexpected_timeout"


def pdf_urls_semantically_equal(left: str | None, right: str | None) -> bool | None:
    """None when either side has no URL (cannot judge); otherwise strict
    normalized identity — different official documents must not be merged."""
    if not left or not right:
        return None
    return normalize_report_url(left) == normalize_report_url(right)
