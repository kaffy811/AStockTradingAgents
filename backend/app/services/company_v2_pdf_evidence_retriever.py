"""Retrieve bounded PDF evidence excerpts for CompanyV2 official verification."""
from __future__ import annotations

import re
from typing import Any


FIELD_KEYWORDS: dict[str, list[str]] = {
    "revenue": ["营业收入", "营收", "operating revenue", "revenue"],
    "net_profit_parent": ["归属于上市公司股东的净利润", "归母净利润", "归属于母公司股东的净利润"],
    "net_profit": ["净利润"],
    "operating_cashflow": ["经营活动产生的现金流量净额", "经营现金流"],
    "total_assets": ["资产总计", "总资产"],
    "equity_parent": ["归属于上市公司股东的净资产", "归母净资产", "归属于上市公司股东的所有者权益"],
    "eps_basic": ["基本每股收益"],
    "roe_weighted": ["加权平均净资产收益率"],
    "total_share": ["总股本"],
    "float_share": ["流通股本"],
}


def _normalize_pages(pdf_text_pages: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(pdf_text_pages, dict):
        pages = pdf_text_pages.get("text_pages") or []
    else:
        pages = pdf_text_pages
    return [page for page in pages if isinstance(page, dict) and page.get("text")]


def _excerpt_around(text: str, keyword: str, *, max_chars: int) -> str:
    lower = text.lower()
    idx = lower.find(keyword.lower())
    if idx < 0:
        idx = 0
    half = max_chars // 2
    start = max(0, idx - half)
    end = min(len(text), start + max_chars)
    return re.sub(r"\s+", " ", text[start:end]).strip()


def retrieve_candidate_excerpts(
    pdf_text_pages: dict[str, Any] | list[dict[str, Any]],
    target_fields: list[str] | None = None,
    *,
    top_k: int = 3,
    max_chars: int = 1500,
) -> dict[str, list[dict[str, Any]]]:
    """Return top bounded excerpts by field keyword hits.

    The caller must pass parsed page text, not raw PDF bytes. This function never
    returns full pages unless the page is shorter than max_chars.
    """
    fields = target_fields or list(FIELD_KEYWORDS)
    pages = _normalize_pages(pdf_text_pages)
    results: dict[str, list[dict[str, Any]]] = {}
    for field in fields:
        keywords = FIELD_KEYWORDS.get(field, [field])
        scored: list[tuple[int, int, dict[str, Any]]] = []
        for page in pages:
            text = page.get("text") or ""
            lower = text.lower()
            matched = [kw for kw in keywords if kw.lower() in lower]
            if not matched:
                continue
            score = sum(lower.count(kw.lower()) for kw in matched)
            first_pos = min((lower.find(kw.lower()) for kw in matched if lower.find(kw.lower()) >= 0), default=0)
            scored.append((
                score,
                -first_pos,
                {
                    "page": page.get("page"),
                    "text": _excerpt_around(text, matched[0], max_chars=max_chars),
                    "keywords": matched,
                },
            ))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        results[field] = [item[2] for item in scored[:top_k]]
    return results


company_v2_pdf_evidence_retriever = retrieve_candidate_excerpts
