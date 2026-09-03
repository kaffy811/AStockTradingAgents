"""
app/agent/schemas.py — Phase 3 AI 财报分析数据结构定义
"""
from __future__ import annotations
from typing import Any


# ── Data Agent output ─────────────────────────────────────────────────────────

def make_data_pack(
    ts_code: str,
    market: str,
    symbol: str,
    collected: list[str],
    missing: list[dict],
    stale: list[str],
    partial: list[str],
    data_quality: dict,
    module_summaries: dict,
    compressed_facts: list[dict],
    report_rag_context: list[dict] | None = None,
    allowed_chunk_ids: list[int] | None = None,
    rag_meta: dict | None = None,
) -> dict:
    return {
        "ts_code": ts_code,
        "market": market,
        "symbol": symbol,
        "collected_modules": collected,
        "missing_modules": missing,
        "stale_modules": stale,
        "partial_modules": partial,
        "data_quality": data_quality,
        "module_summaries": module_summaries,
        "compressed_facts": compressed_facts,
        "report_rag_context": report_rag_context or [],
        "allowed_chunk_ids": allowed_chunk_ids or [],
        "rag_meta": rag_meta or {},
    }


# ── Analysis Agent output (expected JSON shape) ───────────────────────────────

ANALYSIS_OUTPUT_KEYS = {
    "summary", "overall_score", "dimensions",
    "highlights", "risks", "watch_items",
    "data_limitations", "raw_disclaimer",
}

# source_chunks is optional — present only when RAG context was provided
ANALYSIS_OPTIONAL_KEYS = {"source_chunks"}

DIMENSION_KEYS = {"name", "score", "level", "evidence", "risks"}


def validate_analysis_output(obj: Any) -> list[str]:
    """Return list of validation errors (empty = valid)."""
    errors = []
    if not isinstance(obj, dict):
        return ["output is not a dict"]
    for k in ANALYSIS_OUTPUT_KEYS:
        if k not in obj:
            errors.append(f"missing key: {k}")
    dims = obj.get("dimensions", [])
    if not isinstance(dims, list):
        errors.append("dimensions is not a list")
    else:
        for i, d in enumerate(dims):
            if not isinstance(d, dict):
                errors.append(f"dimensions[{i}] is not a dict")
            else:
                for k in DIMENSION_KEYS:
                    if k not in d:
                        errors.append(f"dimensions[{i}] missing key: {k}")
    return errors


# ── Review Agent output ───────────────────────────────────────────────────────

SAFE_PLACEHOLDER: dict = {
    "summary": "AI 分析暂不可用，当前展示确定性财务数据模块。",
    "overall_score": None,
    "dimensions": [],
    "highlights": [],
    "risks": [],
    "watch_items": [],
    "data_limitations": ["AI 输出未通过合规审核，已返回安全占位内容。"],
    "disclaimer": "本内容仅供参考，不构成投资建议。",
    "review": {
        "review_status": "rejected",
        "review_notes": [{"type": "compliance_block", "message": "AI 输出未通过合规审核"}],
        "blocked_phrases": [],
    },
}


def make_review_result(
    status: str,
    notes: list[dict],
    blocked: list[str],
    final: dict,
    audit: dict | None = None,
) -> dict:
    return {
        "review_status": status,
        "review_notes": notes,
        "blocked_phrases": blocked,
        "final": final,
        "audit": audit or {},
    }
