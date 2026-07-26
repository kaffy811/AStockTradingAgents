"""Public response helpers for CompanyV2 AI verification."""
from __future__ import annotations

import re
from typing import Any


SENSITIVE_RESPONSE_KEYS = {
    "local_path",
    "path",
    "pdf_text",
    "full_pdf_text",
    "raw_pdf_text",
    "text_pages",
}


def sanitize_ai_verification_payload(value: Any) -> Any:
    """Remove sensitive PDF internals and bound evidence excerpts."""
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            if key in SENSITIVE_RESPONSE_KEYS:
                continue
            if key in {"evidence_excerpt", "text"}:
                clean[key] = re.sub(r"\s+", " ", str(item or "")).strip()[:1500]
            else:
                clean[key] = sanitize_ai_verification_payload(item)
        return clean
    if isinstance(value, list):
        return [sanitize_ai_verification_payload(item) for item in value]
    return value


def build_ai_verify_error_payload(
    *,
    request_id: str,
    report_id: int,
    report_year: int | None,
    report_type: str | None,
    error_code: str,
    message: str | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "request_id": request_id,
        "report_id": report_id,
        "report_year": report_year,
        "report_type": report_type or "annual",
        "ai_verification_status": "insufficient_evidence",
        "error_code": error_code,
        "fields": {},
        "human_review_queue": [],
        "non_blocking_findings": [],
        "summary_counts": {},
        "warnings": warnings or [],
    }
    if message:
        payload["message"] = message
    return payload
