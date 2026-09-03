#!/usr/bin/env python3
"""Run Phase 6T-C3 semantic-calibrated AI verification artifact capture.

Scope is intentionally narrow:
- CN/601686 2024 annual report only
- existing report_id=1, parsed page sidecar, and Phase 6T-C2 real AI extraction
- no RAG ingestion
- no CNINFO/PDF download/parse main-chain changes
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from sqlalchemy import select

from app.models.report_document import ReportDocument
from app.services.company_v2_ai_official_verification_agent import verify_with_ai
from app.services.company_v2_ai_verification_response import sanitize_ai_verification_payload

MARKET = "CN"
SYMBOL = "601686"
TS_CODE = "601686.SH"
REPORT_ID = 1
REPORT_YEAR = 2024
REPORT_TYPE = "annual"
ARTIFACT_DIR = BACKEND / "docs" / "artifacts"
C2_OFFICIAL_ARTIFACT = ARTIFACT_DIR / "company_v2_601686_ai_official_verification_phase6tc2.json"
OFFICIAL_ARTIFACT = ARTIFACT_DIR / "company_v2_601686_ai_official_verification_phase6tc3.json"
QUEUE_ARTIFACT = ARTIFACT_DIR / "company_v2_601686_ai_human_review_queue_phase6tc3.json"
SUMMARY_ARTIFACT = ARTIFACT_DIR / "company_v2_601686_ai_verification_summary_phase6tc3.md"

BEFORE_FINAL_STATUS = "conflict"
BEFORE_HUMAN_REVIEW_QUEUE_COUNT = 10


class ReplayPhase6TC2LLMClient:
    def __init__(self, artifact_path: Path) -> None:
        self.artifact_path = artifact_path

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        payload = json.loads(self.artifact_path.read_text(encoding="utf-8"))
        return json.dumps({
            "verification_status": payload.get("ai_verification_status") or payload.get("verification_status"),
            "report_id": payload.get("report_id"),
            "report_year": payload.get("report_year"),
            "report_type": payload.get("report_type"),
            "fields": payload.get("fields") or {},
            "human_review_queue": [],
            "non_blocking_findings": [],
            "warnings": payload.get("warnings") or [],
        }, ensure_ascii=False)


def _contains_full_pdf_text(payload: Any) -> bool:
    text = json.dumps(payload, ensure_ascii=False, default=str)
    return "text_pages" in text or "full_pdf_text" in text or "raw_pdf_text" in text


def _contains_local_path(payload: Any) -> bool:
    text = json.dumps(payload, ensure_ascii=False, default=str)
    return "local_path" in text or "/tmp/company_v2_report_pdfs" in text


def _status_breakdown(fields: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in fields.values():
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _structured_debug_from_c2_artifact(artifact_path: Path) -> dict[str, Any]:
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    fields = payload.get("fields") or {}
    row: dict[str, Any] = {"period": f"{REPORT_YEAR}-12-31"}
    for field, entry in fields.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("structured_value") is not None:
            row[field] = entry.get("structured_value")
    return {
        "modules": {
            "phase6tc2_structured_replay": {
                "history": [row],
                "normalized": {"history": [row], "rows": [row]},
            }
        }
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _write_summary(summary: dict[str, Any]) -> None:
    lines = [
        "# CompanyV2 601686 AI Verification Phase 6T-C3",
        "",
        "## Before",
        "",
        f"- final_status: {summary.get('before_final_status')}",
        f"- human_review_queue_count: {summary.get('before_human_review_queue_count')}",
        "",
        "## After",
        "",
        f"- report_id: {summary.get('report_id')}",
        f"- report_year: {summary.get('report_year')}",
        f"- report_type: {summary.get('report_type')}",
        f"- pdf_url: {summary.get('pdf_url')}",
        f"- download_status: {summary.get('download_status')}",
        f"- parse_status: {summary.get('parse_status')}",
        f"- page_count: {summary.get('page_count')}",
        f"- parsed_page_sidecar_exists: {str(summary.get('parsed_page_sidecar_exists')).lower()}",
        f"- final_status: {summary.get('final_status')}",
        f"- true_conflict_count: {summary.get('true_conflict_count')}",
        f"- human_review_queue_count: {summary.get('human_review_queue_count')}",
        f"- non_blocking_findings_count: {summary.get('non_blocking_findings_count')}",
        f"- local_path_leaked: {str(summary.get('local_path_leaked')).lower()}",
        f"- full_pdf_text_returned: {str(summary.get('full_pdf_text_returned')).lower()}",
        f"- semantic_calibration_input: {summary.get('semantic_calibration_input')}",
        "",
        "## status_breakdown",
        "",
    ]
    for status, count in sorted((summary.get("status_breakdown") or {}).items()):
        lines.append(f"- {status}: {count}")
    lines.extend(["", "## human_review_queue", ""])
    queue = summary.get("human_review_queue") or []
    if not queue:
        lines.append("- []")
    else:
        for item in queue:
            lines.append(
                "- field={field}; status={status}; reason={reason}; confidence={confidence}; page={page}".format(
                    field=item.get("field"),
                    status=item.get("status"),
                    reason=item.get("reason"),
                    confidence=item.get("confidence"),
                    page=item.get("evidence_page"),
                )
            )
    lines.extend(["", "## non_blocking_findings", ""])
    findings = summary.get("non_blocking_findings") or []
    if not findings:
        lines.append("- []")
    else:
        for item in findings:
            lines.append(
                "- field={field}; status={status}; reason={reason}; confidence={confidence}; page={page}".format(
                    field=item.get("field"),
                    status=item.get("status"),
                    reason=item.get("reason"),
                    confidence=item.get("confidence"),
                    page=item.get("evidence_page"),
                )
            )
    SUMMARY_ARTIFACT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _failure(stage: str, message: str, *, doc: ReportDocument | None = None) -> dict[str, Any]:
    payload = sanitize_ai_verification_payload({
        "ok": False,
        "stage": stage,
        "message": message,
        "report_id": REPORT_ID,
        "report_year": REPORT_YEAR,
        "report_type": REPORT_TYPE,
        "ai_verification_status": "insufficient_evidence",
        "fields": {},
        "human_review_queue": [],
        "non_blocking_findings": [],
        "summary_counts": {},
        "warnings": [message],
    })
    _write_json(OFFICIAL_ARTIFACT, payload)
    _write_json(QUEUE_ARTIFACT, {"report_id": REPORT_ID, "human_review_queue": [], "non_blocking_findings": []})
    _write_summary({
        "before_final_status": BEFORE_FINAL_STATUS,
        "before_human_review_queue_count": BEFORE_HUMAN_REVIEW_QUEUE_COUNT,
        "report_id": REPORT_ID,
        "report_year": REPORT_YEAR,
        "report_type": REPORT_TYPE,
        "pdf_url": doc.pdf_url if doc else None,
        "download_status": doc.download_status if doc else stage,
        "parse_status": doc.parse_status if doc else stage,
        "page_count": None,
        "parsed_page_sidecar_exists": False,
        "final_status": "insufficient_evidence",
        "true_conflict_count": 0,
        "human_review_queue_count": 0,
        "non_blocking_findings_count": 0,
        "status_breakdown": {},
        "human_review_queue": [],
        "non_blocking_findings": [],
        "local_path_leaked": _contains_local_path(payload),
        "full_pdf_text_returned": _contains_full_pdf_text(payload),
    })
    print(json.dumps({"ok": False, "stage": stage, "message": message, "report_id": REPORT_ID}, ensure_ascii=False))
    return payload


async def run() -> dict[str, Any]:
    from app.core.database import AsyncSessionLocal

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ReportDocument).where(ReportDocument.id == REPORT_ID))
        doc = result.scalars().first()
        if not doc or doc.ts_code != TS_CODE or doc.report_year != REPORT_YEAR or doc.report_type != REPORT_TYPE:
            return _failure("REPORT_RECORD_UNAVAILABLE", "601686 2024 annual report record is unavailable", doc=doc)
        local_path = Path(doc.local_path) if doc.local_path else None
        sidecar = local_path.with_suffix(".pages.json") if local_path else None
        if not sidecar or not sidecar.exists():
            return _failure("PARSED_PAGE_SIDECAR_UNAVAILABLE", "parsed page sidecar is unavailable", doc=doc)
        parsed_source = json.loads(sidecar.read_text(encoding="utf-8"))

        if not C2_OFFICIAL_ARTIFACT.exists():
            return _failure("PHASE6TC2_AI_EXTRACTION_UNAVAILABLE", "Phase 6T-C2 real AI extraction artifact is unavailable", doc=doc)
        debug_data = _structured_debug_from_c2_artifact(C2_OFFICIAL_ARTIFACT)
        report_document = {
            "report_id": REPORT_ID,
            "ts_code": doc.ts_code,
            "symbol": SYMBOL,
            "report_year": REPORT_YEAR,
            "report_type": REPORT_TYPE,
            "pdf_url": doc.pdf_url,
            "source": doc.source or "cninfo",
        }
        try:
            ai_result = await asyncio.to_thread(
                verify_with_ai,
                report_document,
                parsed_source,
                debug_data,
                None,
                REPORT_YEAR,
                REPORT_TYPE,
                llm_client=ReplayPhase6TC2LLMClient(C2_OFFICIAL_ARTIFACT),
                llm_timeout_seconds=10.0,
            )
        except Exception as exc:
            return _failure("AI_VERIFY_FAILED", str(exc)[:500], doc=doc)

        fields = ai_result.get("fields") or {}
        summary_counts = ai_result.get("summary_counts") or {}
        payload = sanitize_ai_verification_payload({
            "ok": True,
            "report_id": REPORT_ID,
            "report_year": REPORT_YEAR,
            "report_type": REPORT_TYPE,
            "pdf_url": doc.pdf_url,
            "download_status": doc.download_status,
            "parse_status": doc.parse_status,
            "page_count": parsed_source.get("page_count"),
            "parsed_page_sidecar_exists": True,
            "ai_verification_status": ai_result.get("verification_status"),
            "fields": fields,
            "human_review_queue": ai_result.get("human_review_queue") or [],
            "non_blocking_findings": ai_result.get("non_blocking_findings") or [],
            "summary_counts": summary_counts,
            "warnings": ai_result.get("warnings") or [],
            "semantic_calibration_input": "phase6tc2_real_ai_output_replay",
        })
        _write_json(OFFICIAL_ARTIFACT, payload)
        _write_json(QUEUE_ARTIFACT, {
            "report_id": REPORT_ID,
            "report_year": REPORT_YEAR,
            "report_type": REPORT_TYPE,
            "human_review_queue": payload.get("human_review_queue") or [],
            "non_blocking_findings": payload.get("non_blocking_findings") or [],
        })
        summary = {
            "before_final_status": BEFORE_FINAL_STATUS,
            "before_human_review_queue_count": BEFORE_HUMAN_REVIEW_QUEUE_COUNT,
            "report_id": REPORT_ID,
            "report_year": REPORT_YEAR,
            "report_type": REPORT_TYPE,
            "pdf_url": doc.pdf_url,
            "download_status": doc.download_status,
            "parse_status": doc.parse_status,
            "page_count": parsed_source.get("page_count"),
            "parsed_page_sidecar_exists": True,
            "final_status": payload.get("ai_verification_status"),
            "true_conflict_count": summary_counts.get("true_conflict_count", 0),
            "human_review_queue_count": len(payload.get("human_review_queue") or []),
            "non_blocking_findings_count": len(payload.get("non_blocking_findings") or []),
            "status_breakdown": _status_breakdown(fields),
            "semantic_calibration_input": "phase6tc2_real_ai_output_replay",
            "human_review_queue": payload.get("human_review_queue") or [],
            "non_blocking_findings": payload.get("non_blocking_findings") or [],
            "local_path_leaked": _contains_local_path(payload),
            "full_pdf_text_returned": _contains_full_pdf_text(payload),
        }
        _write_summary(summary)
        print(json.dumps({
            "ok": True,
            "report_id": REPORT_ID,
            "before_final_status": BEFORE_FINAL_STATUS,
            "after_final_status": payload.get("ai_verification_status"),
            "true_conflict_count": summary.get("true_conflict_count"),
            "human_review_queue_count": summary.get("human_review_queue_count"),
            "non_blocking_findings_count": summary.get("non_blocking_findings_count"),
            "artifacts": {
                "official": str(OFFICIAL_ARTIFACT),
                "queue": str(QUEUE_ARTIFACT),
                "summary": str(SUMMARY_ARTIFACT),
            },
        }, ensure_ascii=False, indent=2))
        return payload


if __name__ == "__main__":
    asyncio.run(run())
