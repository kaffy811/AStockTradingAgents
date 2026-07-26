#!/usr/bin/env python3
"""Run Phase 6T-C4 field-definition-aligned AI verification artifacts.

Scope is intentionally narrow:
- CN/601686 2024 annual report only
- existing report_id=1 and parsed page sidecar
- Phase 6T-C2 real AI extraction replay with C4 provider-definition metadata
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
from app.services.company_v2_financial_field_definition_registry import build_field_definition_match

MARKET = "CN"
SYMBOL = "601686"
TS_CODE = "601686.SH"
REPORT_ID = 1
REPORT_YEAR = 2024
REPORT_TYPE = "annual"
ARTIFACT_DIR = BACKEND / "docs" / "artifacts"
C2_OFFICIAL_ARTIFACT = ARTIFACT_DIR / "company_v2_601686_ai_official_verification_phase6tc2.json"
OFFICIAL_ARTIFACT = ARTIFACT_DIR / "company_v2_601686_ai_official_verification_phase6tc4.json"
QUEUE_ARTIFACT = ARTIFACT_DIR / "company_v2_601686_ai_human_review_queue_phase6tc4.json"
SUMMARY_ARTIFACT = ARTIFACT_DIR / "company_v2_601686_ai_verification_summary_phase6tc4.md"

BEFORE_FIELD_STATUSES = {
    "revenue": "definition_mismatch",
    "net_profit_parent": "definition_mismatch",
    "roe_weighted": "definition_mismatch",
}
BEFORE_HUMAN_REVIEW_QUEUE_COUNT = 3


C4_PROVIDER_ALIGNMENT = {
    "revenue": {
        "provider_definition": "main_business_revenue",
        "matched_label": "主营业务收入",
        "structured_field_name": "MBRevenue",
        "value_basis": "annual_cumulative",
    },
    "net_profit_parent": {
        "provider_definition": "net_profit",
        "matched_label": "净利润",
        "structured_field_name": "netProfit",
        "value_basis": "annual_cumulative",
    },
    "net_profit": {
        "provider_definition": "net_profit",
        "matched_label": "净利润",
        "structured_field_name": "netProfit",
        "value_basis": "annual_cumulative",
    },
    "roe_weighted": {
        "provider_definition": "unknown_roe",
        "matched_label": "roeAvg",
        "structured_field_name": "roe",
        "value_basis": "annual_cumulative",
    },
    "total_share": {
        "provider_definition": "total_share",
        "matched_label": "总股本",
        "structured_field_name": "totalShare",
        "value_basis": "point_in_time",
    },
    "float_share": {
        "provider_definition": "float_share",
        "matched_label": "流通股本",
        "structured_field_name": "liqaShare",
        "value_basis": "point_in_time",
    },
}


class ReplayPhase6TC2LLMClient:
    def __init__(self, artifact_path: Path) -> None:
        self.artifact_path = artifact_path

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.0) -> str:
        payload = json.loads(self.artifact_path.read_text(encoding="utf-8"))
        fields = _align_c2_fields(payload.get("fields") or {})
        return json.dumps({
            "verification_status": payload.get("ai_verification_status") or payload.get("verification_status"),
            "report_id": payload.get("report_id"),
            "report_year": payload.get("report_year"),
            "report_type": payload.get("report_type"),
            "fields": fields,
            "human_review_queue": [],
            "non_blocking_findings": [],
            "warnings": payload.get("warnings") or [],
        }, ensure_ascii=False)


def _align_c2_fields(fields: dict[str, Any]) -> dict[str, Any]:
    aligned: dict[str, Any] = {}
    for field, entry in fields.items():
        if not isinstance(entry, dict):
            continue
        item = dict(entry)
        item.setdefault("structured_period", f"{REPORT_YEAR}-12-31")
        item.setdefault("report_period", f"{REPORT_YEAR}-12-31")
        metadata = C4_PROVIDER_ALIGNMENT.get(field)
        if metadata:
            item.update(metadata)
            item["field_definition_match"] = build_field_definition_match(field, {
                **metadata,
                "reason": item.get("reason"),
                "evidence_excerpt": item.get("evidence_excerpt"),
            })
        aligned[field] = item
    return aligned


def _structured_debug_from_c2_artifact(artifact_path: Path) -> dict[str, Any]:
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    fields = _align_c2_fields(payload.get("fields") or {})
    row: dict[str, Any] = {"period": f"{REPORT_YEAR}-12-31"}
    source_field_map: dict[str, str] = {}
    for field, entry in fields.items():
        if entry.get("structured_value") is None:
            continue
        row[field] = entry.get("structured_value")
        source_field_map[field] = entry.get("structured_field_name") or field
        row[f"{field}_provider_definition"] = entry.get("provider_definition")
        row[f"{field}_matched_label"] = entry.get("matched_label")
        row[f"{field}_field_definition_match"] = (entry.get("field_definition_match") or {}).get("match_type")
        row[f"{field}_value_basis"] = entry.get("value_basis")
    row["source_field_map"] = source_field_map
    row["source"] = "phase6tc2_structured_replay_with_c4_metadata"
    return {
        "modules": {
            "phase6tc4_structured_replay": {
                "history": [row],
                "normalized": {"history": [row], "rows": [row]},
            }
        }
    }


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


def _provider_definition_summary(fields: dict[str, Any]) -> dict[str, int]:
    summary = {"known": 0, "unknown": 0}
    for entry in fields.values():
        if not isinstance(entry, dict) or entry.get("structured_value") is None:
            continue
        provider_definition = entry.get("provider_definition") or "unknown"
        if provider_definition == "unknown":
            summary["unknown"] += 1
        else:
            summary["known"] += 1
    return summary


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _write_summary(summary: dict[str, Any]) -> None:
    lines = [
        "# CompanyV2 601686 AI Verification Phase 6T-C4",
        "",
        "## Before C4",
        "",
        f"- revenue: {summary['before_field_statuses'].get('revenue')}",
        f"- net_profit_parent: {summary['before_field_statuses'].get('net_profit_parent')}",
        f"- roe_weighted: {summary['before_field_statuses'].get('roe_weighted')}",
        f"- human_review_queue_count: {summary.get('before_human_review_queue_count')}",
        "",
        "## After C4",
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
        f"- provider_definition_known_count: {summary.get('provider_definition_summary', {}).get('known')}",
        f"- provider_definition_unknown_count: {summary.get('provider_definition_summary', {}).get('unknown')}",
        f"- local_path_leaked: {str(summary.get('local_path_leaked')).lower()}",
        f"- full_pdf_text_returned: {str(summary.get('full_pdf_text_returned')).lower()}",
        f"- semantic_calibration_input: {summary.get('semantic_calibration_input')}",
        "",
        "## field_statuses",
        "",
    ]
    for field, status in (summary.get("field_statuses") or {}).items():
        lines.append(f"- {field}: {status}")
    lines.extend(["", "## status_breakdown", ""])
    for status, count in sorted((summary.get("status_breakdown") or {}).items()):
        lines.append(f"- {status}: {count}")
    lines.extend(["", "## human_review_queue", ""])
    for item in summary.get("human_review_queue") or []:
        lines.append(
            "- field={field}; status={status}; provider_definition={provider_definition}; reason={reason}".format(
                field=item.get("field"),
                status=item.get("status"),
                provider_definition=item.get("provider_definition"),
                reason=item.get("reason"),
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
        "before_field_statuses": BEFORE_FIELD_STATUSES,
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
        "provider_definition_summary": {"known": 0, "unknown": 0},
        "field_statuses": {},
        "status_breakdown": {},
        "human_review_queue": [],
        "local_path_leaked": _contains_local_path(payload),
        "full_pdf_text_returned": _contains_full_pdf_text(payload),
        "semantic_calibration_input": "failed",
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
        if not C2_OFFICIAL_ARTIFACT.exists():
            return _failure("PHASE6TC2_AI_EXTRACTION_UNAVAILABLE", "Phase 6T-C2 real AI extraction artifact is unavailable", doc=doc)
        parsed_source = json.loads(sidecar.read_text(encoding="utf-8"))
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
            "semantic_calibration_input": "phase6tc2_real_ai_output_replay_with_c4_provider_metadata",
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
            "before_field_statuses": BEFORE_FIELD_STATUSES,
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
            "provider_definition_summary": _provider_definition_summary(fields),
            "field_statuses": {field: entry.get("status") for field, entry in fields.items() if isinstance(entry, dict)},
            "status_breakdown": _status_breakdown(fields),
            "human_review_queue": payload.get("human_review_queue") or [],
            "local_path_leaked": _contains_local_path(payload),
            "full_pdf_text_returned": _contains_full_pdf_text(payload),
            "semantic_calibration_input": "phase6tc2_real_ai_output_replay_with_c4_provider_metadata",
        }
        _write_summary(summary)
        print(json.dumps({
            "ok": True,
            "report_id": REPORT_ID,
            "final_status": payload.get("ai_verification_status"),
            "true_conflict_count": summary.get("true_conflict_count"),
            "human_review_queue_count": summary.get("human_review_queue_count"),
            "provider_definition_summary": summary.get("provider_definition_summary"),
            "artifacts": {
                "official": str(OFFICIAL_ARTIFACT),
                "queue": str(QUEUE_ARTIFACT),
                "summary": str(SUMMARY_ARTIFACT),
            },
        }, ensure_ascii=False, indent=2))
        return payload


if __name__ == "__main__":
    asyncio.run(run())
