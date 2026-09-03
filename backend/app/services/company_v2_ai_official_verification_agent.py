"""AI-assisted official disclosure verification for CompanyV2 reports.

This agent compares bounded CNINFO PDF evidence excerpts with annual/quarterly
structured CompanyV2 JSON. It does not provide investment advice and does not
perform RAG QA.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any

from app.services.company_v2_ai_verification_guardrail import apply_ai_verification_guardrail
from app.services.company_v2_financial_field_definition_registry import build_field_definition_match
from app.services.company_v2_official_verification_service import extract_structured_fields
from app.services.company_v2_pdf_evidence_retriever import FIELD_KEYWORDS, retrieve_candidate_excerpts


TARGET_FIELDS = [
    "revenue",
    "net_profit_parent",
    "net_profit",
    "operating_cashflow",
    "total_assets",
    "equity_parent",
    "eps_basic",
    "roe_weighted",
    "total_share",
    "float_share",
]

SENSITIVE_KEYS = {
    "local_path",
    "path",
    "pdf_text",
    "full_pdf_text",
    "raw_pdf_text",
    "text_pages",
}

SYSTEM_PROMPT = """你是公司年报官方披露字段校对 Agent。
你只做数据校对，不做投资建议；不得输出买入、卖出、目标价、保证上涨。
必须基于 evidence excerpt；证据不足时输出 insufficient_evidence。
不得编造 official_value。必须识别元、万元、亿元、%、股、万股、亿股。
必须识别年报、半年报、一季报、三季报期间。
必须区分净利润、归母净利润、扣非归母净利润。
只输出合法 JSON。"""


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.S)
    if match:
        cleaned = match.group(1)
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("AI verification output must be a JSON object")
    return parsed


def _field_value(item: Any) -> Any:
    if isinstance(item, dict):
        return item.get("value", item.get("raw_value"))
    return item


def _bounded_text(value: Any, *, max_chars: int = 1500) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:max_chars]


def _sanitize_public_payload(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            if key in SENSITIVE_KEYS:
                continue
            if key in {"evidence_excerpt", "text"}:
                clean[key] = _bounded_text(item)
            else:
                clean[key] = _sanitize_public_payload(item)
        return clean
    if isinstance(value, list):
        return [_sanitize_public_payload(item) for item in value]
    return value


def _chat_with_timeout(llm_client: Any, messages: list[dict[str, str]], *, temperature: float, timeout_seconds: float) -> str:
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(llm_client.chat, messages, temperature=temperature)
    try:
        return future.result(timeout=timeout_seconds)
    except TimeoutError as exc:
        future.cancel()
        raise TimeoutError("AI verification LLM call timed out") from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _structured_payload(structured_json: dict[str, Any], target_fields: list[str], report_year: int, report_type: str) -> dict[str, Any]:
    extracted = extract_structured_fields(
        structured_json,
        report_year=report_year,
        report_type=report_type,
        annual_required=report_type == "annual",
    )
    payload: dict[str, Any] = {}
    for field in target_fields:
        source_field = "roe" if field == "roe_weighted" and "roe" in extracted else field
        entry = extracted.get(source_field)
        if isinstance(entry, dict):
            structured_entry = {
                "structured_field_name": entry.get("provider_field_name") or source_field,
                "structured_period": entry.get("structured_period") or entry.get("provider_period"),
                "provider_definition": entry.get("provider_definition"),
                "matched_label": entry.get("matched_label"),
            }
            payload[field] = {
                "value": _field_value(entry),
                "period": structured_entry["structured_period"],
                "source": entry.get("provider_source") or entry.get("source"),
                "field_name": structured_entry["structured_field_name"],
                "reason": entry.get("reason"),
                "as_of_date": entry.get("as_of_date") or entry.get("structured_as_of_date"),
                "provider_definition": entry.get("provider_definition"),
                "matched_label": entry.get("matched_label"),
                "report_period": entry.get("report_period") or structured_entry["structured_period"],
                "value_basis": entry.get("value_basis") or "unknown",
                "field_definition_match": build_field_definition_match(field, structured_entry),
            }
        else:
            payload[field] = {
                "value": _field_value(entry),
                "period": None,
                "source": None,
                "field_name": source_field,
                "provider_definition": None,
                "matched_label": None,
                "report_period": None,
                "value_basis": "unknown",
                "field_definition_match": build_field_definition_match(field, {"structured_field_name": source_field}),
            }
    return payload


def _fallback_result(
    *,
    report_document: dict[str, Any],
    target_fields: list[str],
    excerpts: dict[str, list[dict[str, Any]]],
    structured: dict[str, Any],
    report_year: int,
    report_type: str,
    warning: str,
) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for field in target_fields:
        status = "insufficient_evidence" if excerpts.get(field) else "official_field_not_found"
        entry = {
            "status": status,
            "official_value": None,
            "structured_value": structured.get(field, {}).get("value"),
            "structured_period": structured.get(field, {}).get("period"),
            "structured_field_name": structured.get(field, {}).get("field_name"),
            "field_definition_match": structured.get(field, {}).get("field_definition_match"),
            "provider_definition": structured.get(field, {}).get("provider_definition"),
            "matched_label": structured.get(field, {}).get("matched_label"),
            "report_period": structured.get(field, {}).get("report_period"),
            "value_basis": structured.get(field, {}).get("value_basis"),
            "unit": None,
            "relative_diff_pct": None,
            "confidence": 0.0,
            "evidence_page": excerpts.get(field, [{}])[0].get("page") if excerpts.get(field) else None,
            "evidence_excerpt": excerpts.get(field, [{}])[0].get("text") if excerpts.get(field) else "",
            "reason": warning if excerpts.get(field) else "candidate evidence not found",
            "needs_human_review": False,
            "report_year": report_year,
            "report_type": report_type,
        }
        fields[field] = entry
    guarded = apply_ai_verification_guardrail({
        "verification_status": "insufficient_evidence",
        "report_id": report_document.get("report_id") or report_document.get("id"),
        "report_year": report_year,
        "report_type": report_type,
        "fields": fields,
        "human_review_queue": [],
        "non_blocking_findings": [],
        "warnings": [warning],
    }, report_year=report_year, report_type=report_type)
    return guarded


def _build_user_prompt(
    *,
    report_document: dict[str, Any],
    excerpts: dict[str, list[dict[str, Any]]],
    structured: dict[str, Any],
    target_fields: list[str],
    report_year: int,
    report_type: str,
) -> str:
    payload = {
        "task": "compare_cninfo_pdf_excerpts_with_company_v2_structured_json",
        "report_document": {
            "report_id": report_document.get("report_id") or report_document.get("id"),
            "ts_code": report_document.get("ts_code"),
            "symbol": report_document.get("symbol"),
            "report_year": report_year,
            "report_type": report_type,
            "pdf_url": report_document.get("pdf_url"),
            "source": report_document.get("source") or "cninfo",
        },
        "target_fields": target_fields,
        "structured_json": structured,
        "candidate_excerpts": excerpts,
        "output_schema": {
            "verification_status": "verified|partial|conflict|needs_human_review|insufficient_evidence",
            "report_year": report_year,
            "report_type": report_type,
            "fields": {
                "<field>": {
                    "status": "verified|likely_match|conflict|structured_field_missing|official_field_not_found|insufficient_evidence|definition_mismatch|period_basis_mismatch|unit_scale_suspected|needs_human_review|skipped",
                    "official_value": "number|null",
                    "structured_value": "number|null",
                    "structured_period": "string|null",
                    "structured_field_name": "string|null",
                    "field_definition_match": "object",
                    "unit": "CNY|CNY/share|%|shares|null",
                    "relative_diff_pct": "number|null",
                    "confidence": "0..1",
                    "evidence_page": "number|null",
                    "evidence_excerpt": "string",
                    "reason": "string",
                    "needs_human_review": "boolean",
                }
            },
            "human_review_queue": [],
            "warnings": [],
        },
    }
    return json.dumps(payload, ensure_ascii=False)


def verify_with_ai(
    report_document: dict[str, Any],
    pdf_text_pages: dict[str, Any] | list[dict[str, Any]],
    structured_json: dict[str, Any],
    target_fields: list[str] | None,
    report_year: int,
    report_type: str,
    *,
    llm_client: Any | None = None,
    confidence_threshold: float = 0.75,
    llm_timeout_seconds: float = 45.0,
) -> dict[str, Any]:
    fields = [field for field in (target_fields or TARGET_FIELDS) if field in FIELD_KEYWORDS]
    excerpts = retrieve_candidate_excerpts(pdf_text_pages, fields)
    structured = _structured_payload(structured_json, fields, report_year, report_type)

    if not any(excerpts.values()):
        return _sanitize_public_payload(_fallback_result(
            report_document=report_document,
            target_fields=fields,
            excerpts=excerpts,
            structured=structured,
            report_year=report_year,
            report_type=report_type,
            warning="INSUFFICIENT_EVIDENCE",
        ))

    if llm_client is None:
        try:
            from app.llm.factory import get_llm_client
            llm_client = get_llm_client()
        except Exception:
            return _sanitize_public_payload(_fallback_result(
                report_document=report_document,
                target_fields=fields,
                excerpts=excerpts,
                structured=structured,
                report_year=report_year,
                report_type=report_type,
                warning="AI_KEY_MISSING",
            ))

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": _build_user_prompt(
                report_document=report_document,
                excerpts=excerpts,
                structured=structured,
                target_fields=fields,
                report_year=report_year,
                report_type=report_type,
            ),
        },
    ]
    try:
        raw = _chat_with_timeout(llm_client, messages, temperature=0.0, timeout_seconds=llm_timeout_seconds)
        parsed = _extract_json(raw)
    except Exception:
        try:
            retry_messages = [*messages, {"role": "user", "content": "上一次输出不是合法 JSON。请只返回 JSON，不要解释。"}]
            raw = _chat_with_timeout(llm_client, retry_messages, temperature=0.0, timeout_seconds=llm_timeout_seconds)
            parsed = _extract_json(raw)
        except Exception:
            return _sanitize_public_payload(_fallback_result(
                report_document=report_document,
                target_fields=fields,
                excerpts=excerpts,
                structured=structured,
                report_year=report_year,
                report_type=report_type,
                warning="AI_VERIFICATION_PARSE_ERROR",
            ))

    parsed.setdefault("report_id", report_document.get("report_id") or report_document.get("id"))
    parsed.setdefault("report_year", report_year)
    parsed.setdefault("report_type", report_type)
    parsed.setdefault("fields", {})
    parsed.setdefault("human_review_queue", [])
    parsed.setdefault("non_blocking_findings", [])
    parsed.setdefault("warnings", [])
    for field in fields:
        parsed["fields"].setdefault(field, {
            "status": "official_field_not_found",
            "official_value": None,
            "structured_value": structured.get(field, {}).get("value"),
            "structured_period": structured.get(field, {}).get("period"),
            "structured_field_name": structured.get(field, {}).get("field_name"),
            "field_definition_match": structured.get(field, {}).get("field_definition_match"),
            "provider_definition": structured.get(field, {}).get("provider_definition"),
            "matched_label": structured.get(field, {}).get("matched_label"),
            "report_period": structured.get(field, {}).get("report_period"),
            "value_basis": structured.get(field, {}).get("value_basis"),
            "confidence": 0.0,
            "evidence_page": None,
            "evidence_excerpt": "",
            "reason": "AI output omitted field",
            "needs_human_review": False,
        })
        parsed["fields"][field].setdefault("structured_value", structured.get(field, {}).get("value"))
        parsed["fields"][field].setdefault("structured_period", structured.get(field, {}).get("period"))
        parsed["fields"][field].setdefault("structured_field_name", structured.get(field, {}).get("field_name"))
        parsed["fields"][field].setdefault("field_definition_match", structured.get(field, {}).get("field_definition_match"))
        parsed["fields"][field].setdefault("provider_definition", structured.get(field, {}).get("provider_definition"))
        parsed["fields"][field].setdefault("matched_label", structured.get(field, {}).get("matched_label"))
        parsed["fields"][field].setdefault("report_period", structured.get(field, {}).get("report_period"))
        parsed["fields"][field].setdefault("value_basis", structured.get(field, {}).get("value_basis"))
    guarded = apply_ai_verification_guardrail(
        parsed,
        report_year=report_year,
        report_type=report_type,
        confidence_threshold=confidence_threshold,
    )
    return _sanitize_public_payload(guarded)


company_v2_ai_official_verification_agent = verify_with_ai
