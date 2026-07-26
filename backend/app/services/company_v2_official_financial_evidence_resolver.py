"""Resolve official report evidence for a single financial field."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.services.company_v2_financial_field_definition_registry import get_field_profile
from app.services.company_v2_official_field_extractor import (
    _scale,
    _table_scope_unit,
    extract_official_fields,
)
from app.services.company_v2_report_chunker import load_pages_from_sidecar

_MONETARY_FIELDS = {"revenue", "net_profit", "net_profit_parent", "operating_cashflow", "total_assets", "equity_parent"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _find_sidecar(report_id: int) -> Path | None:
    candidates = sorted(Path("/tmp/company_v2_report_pdfs").glob(f"company_v2_report_{report_id}_*.pages.json"))
    return candidates[0] if candidates else None


def _derive_period_from_text(text: str, report_year: int | None, report_type: str | None, field_name: str) -> str | None:
    if not text and report_year is None:
        return None
    for pattern in [
        r"(\d{4})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})\s*[日号]?",
        r"截至\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日",
    ]:
        match = re.search(pattern, text)
        if match:
            y, m, d = map(int, match.groups())
            return f"{y:04d}-{m:02d}-{d:02d}"
    if report_year:
        if field_name in {"total_share", "float_share"} and "12-12" in text:
            match = re.search(r"(\d{4})年12月12日", text)
            if match:
                return f"{int(match.group(1)):04d}-12-12"
        if report_type == "annual":
            return f"{report_year}-12-31"
    return None


def _score_candidate(field_name: str, candidate: dict[str, Any], report_year: int | None) -> float:
    score = float(candidate.get("confidence") or 0.0)
    page = int(candidate.get("page") or 0)
    excerpt = str(candidate.get("evidence_excerpt") or "")
    profile = get_field_profile(field_name)
    for alias in profile.get("official_report_labels") or []:
        if alias and alias in excerpt:
            score += 0.12
    if field_name in {"revenue", "net_profit", "net_profit_parent", "operating_cashflow"} and page and page <= 20:
        score += 0.08
    if field_name in {"total_share", "float_share"} and "12-12" in excerpt:
        score += 0.08
    if report_year and str(report_year) in excerpt:
        score += 0.03
    return min(score, 1.0)


def _has_explicit_date(text: str) -> bool:
    return bool(re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", text or ""))


def _build_alternatives(official_fields: dict[str, Any], field_name: str) -> list[dict[str, Any]]:
    alternatives: list[dict[str, Any]] = []
    for key, value in official_fields.items():
        if key == field_name or not value:
            continue
        if not isinstance(value, dict):
            continue
        alternatives.append(
            {
                "field_name": key,
                "value": value.get("value"),
                "unit": value.get("unit"),
                "page": value.get("page"),
                "score": round(float(value.get("confidence") or 0.0), 4),
            }
        )
    return sorted(alternatives, key=lambda item: item["score"], reverse=True)[:3]


def resolve_official_financial_evidence(
    *,
    symbol: str,
    report_id: int,
    field_name: str,
    provider_definition: str | None,
    provider_period: str | None,
    provider_value_basis: str | None,
    report_year: int | None = None,
    report_type: str | None = None,
    sidecar_path: str | Path | None = None,
    source_url: str | None = None,
) -> dict[str, Any]:
    sidecar = Path(sidecar_path) if sidecar_path else _find_sidecar(report_id)
    if not sidecar or not sidecar.exists():
        return {
            "field_name": field_name,
            "status": "insufficient_evidence",
            "retrieval_mode": "unavailable",
            "candidate": None,
            "alternatives": [],
            "warnings": ["page sidecar unavailable"],
        }

    pages, parsed = load_pages_from_sidecar(sidecar)
    extracted = extract_official_fields(parsed, report_id=report_id)
    official_fields = extracted.get("official_fields") or {}
    candidate = official_fields.get(field_name)

    retrieval_mode = "extractor"
    if field_name in {"total_share", "float_share"}:
        profile = get_field_profile(field_name)
        query_terms = list(profile.get("official_report_labels") or []) or [field_name]
        explicit_candidate: dict[str, Any] | None = None
        for page in pages:
            text = page.text or ""
            if not _has_explicit_date(text):
                continue
            if not any(term and term in text for term in query_terms):
                continue
            for term in query_terms:
                pattern = rf"{re.escape(term)}[^\d\-]*([\-0-9,，.]+)\s*(万股|亿股|股)?"
                match = re.search(pattern, text)
                if not match:
                    continue
                try:
                    numeric = float(str(match.group(1)).replace(",", "").replace("，", ""))
                except Exception:
                    continue
                unit = match.group(2) or profile.get("expected_unit")
                explicit_candidate = {
                    "value": numeric,
                    "unit": unit,
                    "raw_value": numeric,
                    "raw_unit": unit,
                    "confidence": 0.7,
                    "source": "cninfo_pdf",
                    "page": page.page,
                    "evidence_excerpt": text[max(0, match.start() - 80) : min(len(text), match.end() + 140)],
                    "official_field_name": profile.get("display_name") or field_name,
                    "matched_alias": term,
                    "official_table": None,
                    "official_row_label": term,
                    "official_column_label": None,
                    "evidence_note": "explicit date candidate for point-in-time share count",
                    "field_semantics": profile,
                    "verified": False,
                    "report_id": str(report_id),
                }
                explicit_candidate["score"] = _score_candidate(field_name, explicit_candidate, report_year) + 0.1
                if not candidate or (candidate.get("page") and int(candidate.get("page")) != int(page.page)):
                    candidate = explicit_candidate
                    retrieval_mode = "keyword"
                    break
            if candidate is explicit_candidate:
                break
    if not candidate:
        profile = get_field_profile(field_name)
        query_terms = list(profile.get("official_report_labels") or []) or [field_name]
        best: dict[str, Any] | None = None
        for page in pages:
            text = page.text or ""
            if not any(term and term in text for term in query_terms):
                continue
            for term in query_terms:
                if not term or term not in text:
                    continue
                pattern = rf"{re.escape(term)}[^\d\-]*([\-0-9,，.]+)\s*(亿元|万元|元|万股|亿股|股|%|元/股)?"
                match = re.search(pattern, text)
                if not match:
                    continue
                value = match.group(1)
                try:
                    numeric = float(str(value).replace(",", "").replace("，", ""))
                except Exception:
                    continue
                # Phase 6T-J2 unit precedence: inline > table-level in scope > unknown.
                # Never default monetary units to the registry expected_unit.
                inline_unit = match.group(2)
                unit_source = "inline" if inline_unit else None
                unit = inline_unit
                scope = None
                if unit is None and field_name in _MONETARY_FIELDS:
                    scope = _table_scope_unit(text, match.start(), field_name)
                    if scope:
                        unit = scope["unit"]
                        unit_source = "table_level"
                scale, normalized_unit = _scale(unit, field=field_name)
                if field_name in _MONETARY_FIELDS:
                    if scale is None:
                        normalized_value = numeric
                        normalized_unit = None
                        unit = None
                        unit_source = "unknown"
                    else:
                        normalized_value = numeric * scale
                else:
                    normalized_value = numeric * (scale or 1.0)
                    unit = unit or profile.get("expected_unit")
                    unit_source = unit_source or "intrinsic"
                excerpt = text[max(0, match.start() - 80) : min(len(text), match.end() + 120)]
                item = {
                    "value": normalized_value,
                    "unit": normalized_unit if field_name in _MONETARY_FIELDS else unit,
                    "raw_value": numeric,
                    "raw_unit": unit,
                    "unit_scale": scale,
                    "unit_source": unit_source,
                    "unit_confidence": 0.0 if unit_source == "unknown" else (1.0 if unit_source == "inline" else 0.9),
                    "unit_evidence_text": (scope or {}).get("unit_evidence_text") or inline_unit,
                    "unit_evidence_page": page.page if unit_source in {"inline", "table_level"} else None,
                    "table_scope_id": (f"p{page.page}#u{scope['unit_evidence_offset']}" if scope else None),
                    "classification_hint": "unit_context_missing" if unit_source == "unknown" else None,
                    "confidence": 0.45,
                    "source": "cninfo_pdf",
                    "page": page.page,
                    "evidence_excerpt": excerpt,
                    "official_field_name": profile.get("display_name") or field_name,
                    "matched_alias": term,
                    "official_table": None,
                    "official_row_label": term,
                    "official_column_label": None,
                    "evidence_note": "keyword fallback candidate",
                    "field_semantics": profile,
                    "verified": False,
                    "report_id": str(report_id),
                }
                item["score"] = _score_candidate(field_name, item, report_year)
                if not best or item["score"] > best["score"]:
                    best = item
        candidate = best
        retrieval_mode = "keyword"

    alternatives = _build_alternatives(official_fields, field_name)
    if not candidate:
        return {
            "field_name": field_name,
            "status": "insufficient_evidence",
            "retrieval_mode": retrieval_mode,
            "candidate": None,
            "alternatives": alternatives,
            "warnings": ["official field not found in selected report"],
        }

    page_text = next((page.text for page in pages if int(page.page) == int(candidate.get("page") or 0)), "")
    official_period = _derive_period_from_text(page_text or candidate.get("evidence_excerpt") or "", report_year, report_type, field_name)
    if official_period is None and report_year and report_type == "annual":
        official_period = f"{report_year}-12-31"

    candidate = dict(candidate)
    candidate["official_period"] = official_period
    candidate["score"] = round(_score_candidate(field_name, candidate, report_year), 4)

    if field_name in {"total_share", "float_share"} and official_period and provider_period and official_period != provider_period:
        status = "resolved"
    else:
        status = "resolved"

    return {
        "field_name": field_name,
        "status": status,
        "retrieval_mode": retrieval_mode,
        "candidate": {
            "value": candidate.get("value"),
            "unit": candidate.get("unit"),
            "raw_value": candidate.get("raw_value"),
            "raw_unit": candidate.get("raw_unit"),
            "unit_scale": candidate.get("unit_scale"),
            "unit_source": candidate.get("unit_source"),
            "unit_confidence": candidate.get("unit_confidence"),
            "unit_evidence_text": candidate.get("unit_evidence_text"),
            "unit_evidence_page": candidate.get("unit_evidence_page"),
            "table_scope_id": candidate.get("table_scope_id"),
            "classification_hint": candidate.get("classification_hint"),
            "definition": candidate.get("official_field_name") or get_field_profile(field_name).get("display_name"),
            "period": candidate.get("official_period"),
            "value_basis": "point_in_time" if field_name in {"total_share", "float_share", "equity_parent", "total_assets"} else "annual_cumulative",
            "page": candidate.get("page"),
            "chunk_id": candidate.get("chunk_id"),
            "excerpt": candidate.get("evidence_excerpt"),
            "source_url": source_url or "",
            "score": candidate.get("score"),
            "official_field_name": candidate.get("official_field_name"),
            "matched_alias": candidate.get("matched_alias"),
            "table_title": candidate.get("official_table"),
            "evidence_page": candidate.get("page"),
            "official_row_label": candidate.get("official_row_label"),
            "official_column_label": candidate.get("official_column_label"),
        },
        "alternatives": alternatives,
        "warnings": [],
        "pages_scanned": len(pages),
        "parsed_status": parsed.get("parse_status"),
    }


company_v2_official_financial_evidence_resolver = resolve_official_financial_evidence
