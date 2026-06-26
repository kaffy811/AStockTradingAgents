"""
rag_eval_runner.py — Phase 2D.5: RAG Evaluation Metrics Runner.

Public API
----------
run_rag_eval(*, cases_path, db=None, search_fn=None, top_k, search_mode) → dict

Loads evaluation cases from a JSON file and computes:
  • Recall@k     — fraction of cases where ≥1 expected keyword appears in top-k results
  • MRR          — Mean Reciprocal Rank of first keyword-matching result
  • nDCG@k       — normalised Discounted Cumulative Gain using graded relevance

Design:
  • search_fn defaults to financial_rag_search (imported lazily to avoid circular)
  • db=None → uses a mock DB stub that returns the eval case's own doc as the only result
    (useful for offline CI eval without a real Postgres connection)
  • Each case may optionally define "relevance_grades" : {result_title: int 0-3} for nDCG
    If absent, binary relevance is used (keyword match → grade 1, else 0).
  • Returns a structured dict including per-case breakdown and aggregate metrics.
"""
from __future__ import annotations

import json
import logging
import math
import os
import time
import uuid
from types import SimpleNamespace
from typing import Any, Callable, Awaitable
from unittest.mock import AsyncMock, MagicMock

log = logging.getLogger(__name__)


# ── Metric helpers ─────────────────────────────────────────────────────────────

def _recall_at_k(results: list[dict], expected_keywords: list[str]) -> float:
    """1.0 if any expected keyword appears in any result chunk, else 0.0."""
    if not expected_keywords or not results:
        return 0.0
    combined = " ".join(r.get("chunk", "").lower() for r in results)
    return 1.0 if any(kw.lower() in combined for kw in expected_keywords) else 0.0


def _reciprocal_rank(results: list[dict], expected_keywords: list[str]) -> float:
    """1/rank of the first result containing any expected keyword, or 0."""
    for i, r in enumerate(results, start=1):
        text = r.get("chunk", "").lower()
        if any(kw.lower() in text for kw in expected_keywords):
            return 1.0 / i
    return 0.0


def _relevance_grade(result: dict, expected_keywords: list[str], grades: dict[str, int]) -> int:
    """
    Return relevance grade for a result dict.

    If `grades` is populated (title → int), use it.
    Otherwise use binary: 1 if any keyword in chunk, else 0.
    """
    title = result.get("title", "")
    if title in grades:
        return grades[title]
    text = result.get("chunk", "").lower()
    return 1 if any(kw.lower() in text for kw in expected_keywords) else 0


def _dcg(grades: list[int]) -> float:
    """Discounted Cumulative Gain."""
    return sum(g / math.log2(i + 2) for i, g in enumerate(grades))


def _ndcg_at_k(
    results: list[dict],
    expected_keywords: list[str],
    top_k: int,
    grade_map: dict[str, int],
) -> float:
    """nDCG@k using per-result relevance grades."""
    if not results:
        return 0.0
    result_grades = [
        _relevance_grade(r, expected_keywords, grade_map)
        for r in results[:top_k]
    ]
    # Ideal DCG: assume all top_k results are maximally relevant (grade 1 for binary)
    max_grade  = max(grade_map.values()) if grade_map else 1
    ideal      = [max_grade] * min(top_k, len(results))
    ideal_dcg  = _dcg(ideal) or 1.0
    actual_dcg = _dcg(result_grades)
    return actual_dcg / ideal_dcg


# ── Mock DB builder ────────────────────────────────────────────────────────────

def _build_mock_db_for_case(case: dict) -> Any:
    """
    Build an AsyncMock DB session that returns the eval case's own doc
    as the single search result (no real Postgres needed).
    """
    doc = case["doc"]
    row = SimpleNamespace(
        chunk_id=str(uuid.uuid4()),
        chunk_text=doc["text"],
        chunk_index=0,
        chunk_symbol=doc["symbol"],
        chunk_market=doc["market"],
        chunk_metadata={},
        embedding_model=None,
        doc_id=str(uuid.uuid4()),
        title=doc["title"],
        source_type=doc["source_type"],
        source=doc["source"],
        published_at=doc.get("published_at", ""),
        url=doc.get("url", ""),
        doc_metadata={
            "symbol": doc["symbol"],
            "market": doc["market"],
        },
        vector_score=0.88,
        keyword_raw=float(len(doc["text"])),
    )
    mr = MagicMock()
    mr.fetchall.return_value = [row]
    mock_db = AsyncMock()
    mock_db.execute.return_value = mr
    return mock_db


# ── Default search function ────────────────────────────────────────────────────

async def _default_search_fn(
    query: str,
    db: Any,
    *,
    symbol: str | None,
    market: str | None,
    top_k: int,
    search_mode: str,
) -> dict:
    from app.agents.financial_rag_tool import financial_rag_search  # noqa: PLC0415
    return await financial_rag_search(
        query, db,
        symbol=symbol,
        market=market,
        top_k=top_k,
        search_mode=search_mode,
    )


# ── Main runner ────────────────────────────────────────────────────────────────

async def run_rag_eval(
    *,
    cases_path: str | None = None,
    cases: list[dict] | None = None,
    db: Any = None,
    search_fn: Callable[..., Awaitable[dict]] | None = None,
    top_k: int = 5,
    search_mode: str = "keyword",
) -> dict:
    """
    Run RAG evaluation over a set of eval cases.

    Parameters
    ----------
    cases_path  : path to a JSON file containing a list of eval case dicts
    cases       : inline list of eval cases (alternative to cases_path)
    db          : SQLAlchemy AsyncSession; None → use per-case mock DB
    search_fn   : async callable(query, db, *, symbol, market, top_k, search_mode) → dict
                  defaults to financial_rag_search
    top_k       : number of results per query
    search_mode : "keyword" | "vector" | "hybrid"

    Returns
    -------
    {
        "ok":          bool,
        "top_k":       int,
        "search_mode": str,
        "cases_total": int,
        "cases_ok":    int,
        "cases_failed": int,
        "recall_at_k": float,   # mean over all cases
        "mrr":         float,   # mean reciprocal rank
        "ndcg_at_k":  float,   # mean nDCG@top_k
        "elapsed_ms":  int,
        "per_case":    list[dict],   # per-case breakdown
        "errors":      list[str],
    }
    """
    if cases is None:
        if cases_path is None:
            cases_path = os.path.join(
                os.path.dirname(__file__),
                "..", "..", "tests", "fixtures", "rag_eval_cases.json",
            )
        with open(cases_path, encoding="utf-8") as f:
            cases = json.load(f)

    if search_fn is None:
        search_fn = _default_search_fn

    t0 = time.monotonic()
    per_case: list[dict] = []
    errors: list[str]   = []
    recalls, rrs, ndcgs = [], [], []

    for case in cases:
        case_id  = case.get("id", "?")
        query    = case["query"]
        keywords = case.get("expected_keywords", [])
        grade_map: dict[str, int] = case.get("relevance_grades", {})

        # Use per-case mock DB when no real session provided
        case_db = db if db is not None else _build_mock_db_for_case(case)

        try:
            result = await search_fn(
                query, case_db,
                symbol=case.get("symbol"),
                market=case.get("market"),
                top_k=top_k,
                search_mode=search_mode,
            )

            if not result.get("ok"):
                raise RuntimeError(result.get("error", "unknown error"))

            results_list = result.get("results", [])
            recall = _recall_at_k(results_list, keywords)
            rr     = _reciprocal_rank(results_list, keywords)
            ndcg   = _ndcg_at_k(results_list, keywords, top_k, grade_map)

            recalls.append(recall)
            rrs.append(rr)
            ndcgs.append(ndcg)

            per_case.append({
                "id":          case_id,
                "ok":          True,
                "recall_at_k": round(recall, 4),
                "rr":          round(rr, 4),
                "ndcg_at_k":   round(ndcg, 4),
                "results_count": len(results_list),
                "search_mode_used": result.get("search_mode", search_mode),
                "elapsed_ms":  result.get("elapsed_ms", 0),
            })

        except Exception as exc:
            err_msg = f"case {case_id}: {exc}"
            log.warning("rag_eval error: %s", err_msg)
            errors.append(err_msg)
            per_case.append({
                "id":          case_id,
                "ok":          False,
                "recall_at_k": 0.0,
                "rr":          0.0,
                "ndcg_at_k":   0.0,
                "error":       str(exc),
            })
            # Still push zeros so aggregate metrics reflect failure
            recalls.append(0.0)
            rrs.append(0.0)
            ndcgs.append(0.0)

    cases_ok     = sum(1 for c in per_case if c["ok"])
    cases_failed = len(per_case) - cases_ok

    def _mean(xs: list[float]) -> float:
        return round(sum(xs) / len(xs), 4) if xs else 0.0

    return {
        "ok":           len(errors) == 0,
        "top_k":        top_k,
        "search_mode":  search_mode,
        "cases_total":  len(cases),
        "cases_ok":     cases_ok,
        "cases_failed": cases_failed,
        "recall_at_k":  _mean(recalls),
        "mrr":          _mean(rrs),
        "ndcg_at_k":    _mean(ndcgs),
        "elapsed_ms":   int((time.monotonic() - t0) * 1000),
        "per_case":     per_case,
        "errors":       errors,
    }
