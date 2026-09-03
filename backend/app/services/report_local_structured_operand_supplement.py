"""Bounded, report-local operand recovery for allowlisted derived metrics.

This is deliberately not a retriever.  It inspects only the active index for
the already-selected report and period, and only when net-margin operands are
missing from the normal structured extraction.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select

from app.models.company_v2_report_rag import ReportRagChunk, ReportRagDocument


_NUMBER = r"([-+]?\d[\d,，]*(?:\.\d+)?)"
_OPERANDS = {
    "revenue": "营业收入",
    "parent_net_profit": "归属于上市公司股东的净利润",
}


def _flexible(label: str) -> str:
    return r"\s*".join(re.escape(char) for char in label)


def _value(text: str, label: str) -> Decimal | None:
    match = re.search(rf"{_flexible(label)}[^\d+-]{{0,45}}{_NUMBER}", text)
    if not match:
        return None
    try:
        value = Decimal(match.group(1).replace(",", "").replace("，", ""))
    except (InvalidOperation, ValueError):
        return None
    return value if value.is_finite() else None


def _metric_requested(question: str) -> bool:
    return "净利率" in str(question or "")


def bind_supplement_evidence_ids(
    structured: dict[str, Any], evidence_map: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Bind internal chunk locators to request-local E labels in-place."""
    labels = {
        str(chunk.get("chunk_id") or chunk.get("id")): evidence_id
        for evidence_id, chunk in evidence_map.items()
    }
    for item in (structured.get("fields") or {}).values():
        if item.get("source_type") != "report_local_structured_operand_supplement":
            continue
        evidence_id = labels.get(str(item.get("source_chunk_id")))
        item["source_evidence_ids"] = [evidence_id] if evidence_id else []
        item["provenance_complete"] = bool(evidence_id)
    return structured


async def supplement_report_local_operands(
    *, db: Any, question: str, report_id: Any, report_year: Any,
    selected_period: str, structured: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Return merged fields plus at most one same-report source chunk."""
    fields = structured.setdefault("fields", {})
    missing = [name for name in _OPERANDS if name not in fields]
    audit = {"requested": False, "missing": missing, "supplemented": [], "reason": None}
    if not _metric_requested(question) or not missing:
        audit["reason"] = "metric_not_requested" if not _metric_requested(question) else "operands_present"
        return structured, [], audit
    audit["requested"] = True
    try:
        year = int(report_year)
        rid = int(report_id)
    except (TypeError, ValueError):
        audit["reason"] = "invalid_report_scope"
        return structured, [], audit
    if str(selected_period or "") != f"{year}-12-31":
        audit["reason"] = "selected_period_mismatch"
        return structured, [], audit
    if db is None or not hasattr(db, "execute"):
        audit["reason"] = "request_database_unavailable"
        return structured, [], audit

    doc_stmt = (
        select(ReportRagDocument)
        .where(
            ReportRagDocument.report_id == rid,
            ReportRagDocument.report_year == year,
            ReportRagDocument.report_type == "annual",
            ReportRagDocument.active_index == 1,
            ReportRagDocument.deleted_at.is_(None),
        )
        .order_by(ReportRagDocument.index_generation.desc())
    )
    doc = (await db.execute(doc_stmt)).scalars().first()
    if doc is None:
        audit["reason"] = "active_selected_report_index_missing"
        return structured, [], audit

    chunk_stmt = (
        select(ReportRagChunk)
        .where(
            ReportRagChunk.rag_document_id == int(doc.id),
            ReportRagChunk.report_id == rid,
            ReportRagChunk.text.ilike("%营业收入%"),
            ReportRagChunk.text.ilike("%归属于上市公司股东%"),
            ReportRagChunk.text.ilike("%净%利润%"),
        )
        .order_by(ReportRagChunk.chunk_index)
        .limit(8)
    )
    rows = (await db.execute(chunk_stmt)).scalars().all()
    for row in rows:
        text = str(row.text or "")
        compact = re.sub(r"\s+", " ", text)
        if f"{year}年" not in compact:
            continue
        unit_match = re.search(r"单位[：:]?\s*([^\s]+)", compact)
        currency_match = re.search(r"币种[：:]?\s*([^\s]+)", compact)
        if not unit_match or unit_match.group(1) != "元":
            continue
        if currency_match and not currency_match.group(1).startswith("人民币"):
            continue
        values = {name: _value(compact, label) for name, label in _OPERANDS.items()}
        if any(values[name] is None for name in missing):
            continue
        chunk = {
            "chunk_id": int(row.id), "report_id": rid, "report_year": year,
            "report_type": "annual", "period": str(selected_period),
            "chunk_index": int(row.chunk_index), "section_title": row.section_title,
            "content": text, "page_start": int(row.page_start), "page_end": int(row.page_end),
            "source_url": doc.source_url, "score": None,
            "source_type": "report_local_structured_operand_supplement",
        }
        for name in missing:
            value = values[name]
            fields[name] = {
                "metric": "net_profit" if name == "parent_net_profit" else name,
                "field": name, "value": float(value), "normalized_value": str(value),
                "unit": "元", "period": str(year), "period_end": str(selected_period),
                "report_id": rid, "source_chunk_id": int(row.id),
                "source_evidence_ids": [],
                "source_type": "report_local_structured_operand_supplement",
                "provenance_complete": False,
            }
            audit["supplemented"].append(name)
        structured["field_count"] = len(fields)
        structured["supplemented_field_count"] = len(audit["supplemented"])
        structured["extraction_method"] = "report_local_structured_operand_supplement"
        audit["reason"] = "complete_report_local_evidence"
        return structured, [chunk], audit
    audit["reason"] = "complete_same_period_unit_evidence_not_found"
    return structured, [], audit
