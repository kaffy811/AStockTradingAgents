"""
financial_rag_tool.py — Phase 2D / 2D.5: Hybrid RAG with configurable weights,
Cosine-MMR diversity reranking, and enhanced search diagnostics.

Supports three search modes:
  "hybrid"  — vector + keyword, merged and re-ranked (default)
  "vector"  — pure cosine-similarity search on embedding_vector
  "keyword" — ILIKE text search (Phase 2A backward-compatible behaviour)

Automatic fallback chain:
  hybrid / vector → embed fails     → keyword only
  hybrid / vector → pgvector error  → keyword only

Scoring (all weights come from settings, configurable via env):
  combined = rag_vector_weight  * vector_score
           + rag_keyword_weight * keyword_score
           + source_boost (≤ rag_source_boost_weight)
           + recency_boost (≤ rag_recency_boost_weight)

  When vector_score is absent:   keyword_weight normalised to 1.0
  When keyword_score is absent:  vector_weight  normalised to 1.0

MMR diversity (rag_mmr_enabled=True by default):
  Phase 2D.5 — True Cosine-MMR when chunk vectors are available:
    MMR(d) = λ * Rel(d,q) - (1-λ) * max_cos(d, selected)
    where Rel(d,q) = combined_score, max_cos uses the stored chunk vector.
  Fallback to per-doc cap when vectors are absent.
  diagnostics.mmr_strategy reports: "cosine" | "per_doc_cap" | "disabled"

Return shape:
  {
    "ok":         bool,
    "query":      str,
    "results":    [...],          # see _row_to_result for per-result shape
    "search_mode": str,           # actual mode used
    "elapsed_ms": int,
    "diagnostics": {
      "search_mode_requested":          str,
      "search_mode_used":               str,
      "vector_available":               bool,
      "keyword_fallback_used":          bool,
      "embedding_provider":             str,
      "candidate_count":                int,
      "returned_count":                 int,
      "mmr_enabled":                    bool,
      "mmr_strategy":                   str,   # Phase 2D.5
      "score_weights":                  dict,  # Phase 2D.5
      "embedding_coverage_in_candidates": float,  # Phase 2D.5
      "official_source_ratio":          float,    # Phase 2D.5
    },
  }
"""
from __future__ import annotations

import logging
import math
import time
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

_MAX_TOP_K         = 10   # public API clamp (backward compatible with Phase 2A tests)
_DEFAULT_TOP_K     = 5
_CHUNK_DISPLAY_LEN = 800


# ── Official source classification (inline; avoids circular import) ────────────

_OFFICIAL_DOMAINS_QUICK: dict[str, str] = {
    "sse.com.cn":     "official_exchange",
    "szse.cn":        "official_exchange",
    "cninfo.com.cn":  "official_exchange",
    "hkexnews.hk":   "official_exchange",
    "sec.gov":        "official_exchange",
    "edgar.sec.gov":  "official_exchange",
    "eastmoney.com":  "authoritative_media",
    "xueqiu.com":     "authoritative_media",
    "nasdaq.com":     "authoritative_media",
}

_AUTHORITY_SCORES = {
    "official_exchange":   1.0,
    "official_company":    0.9,
    "authoritative_media": 0.6,
    "general":             0.3,
}


def _source_level_for_url(url: str | None) -> str:
    if not url:
        return "general"
    url_lower = url.lower()
    for domain, level in _OFFICIAL_DOMAINS_QUICK.items():
        if domain in url_lower:
            return level
    return "general"


# ── Config helpers ────────────────────────────────────────────────────────────

def _cfg(attr: str, default: float) -> float:
    """Read a float setting from app config, fallback to default."""
    try:
        from app.core.config import settings  # noqa: PLC0415
        return float(getattr(settings, attr, default))
    except Exception:
        return default


def _cfg_bool(attr: str, default: bool) -> bool:
    try:
        from app.core.config import settings  # noqa: PLC0415
        return bool(getattr(settings, attr, default))
    except Exception:
        return default


def _cfg_int(attr: str, default: int) -> int:
    try:
        from app.core.config import settings  # noqa: PLC0415
        return int(getattr(settings, attr, default))
    except Exception:
        return default


def _cfg_str(attr: str, default: str) -> str:
    try:
        from app.core.config import settings  # noqa: PLC0415
        return str(getattr(settings, attr, default) or default)
    except Exception:
        return default


# ── Score computation ─────────────────────────────────────────────────────────

def _compute_score(
    vector_score: float,
    keyword_score: float,
    source_level: str,
    published_at_str: str,
) -> tuple[float, dict]:
    """
    Compute combined score using configurable weights.

    Returns (combined_score, score_detail_dict).
    """
    v_weight = _cfg("rag_vector_weight",         0.6)
    k_weight = _cfg("rag_keyword_weight",         0.3)
    s_max    = _cfg("rag_source_boost_weight",    0.07)
    r_max    = _cfg("rag_recency_boost_weight",   0.03)

    has_vector  = vector_score > 0.0
    has_keyword = keyword_score > 0.0

    if has_vector and has_keyword:
        base = v_weight * vector_score + k_weight * keyword_score
    elif has_vector:
        base = vector_score        # normalise to 1.0 weight
    else:
        base = keyword_score       # normalise to 1.0 weight

    # Source boost (capped at s_max to avoid low-relevance official docs displacing high-relevance general ones)
    src_boost_raw = {
        "official_exchange":   s_max,
        "official_company":    s_max * 0.85,
        "authoritative_media": s_max * 0.5,
        "general":             0.0,
    }.get(source_level, 0.0)

    # Recency boost
    rec_boost = _recency_boost_scaled(published_at_str, r_max)

    combined = min(base + src_boost_raw + rec_boost, 1.0)

    return combined, {
        "vector_score":   round(vector_score, 4),
        "keyword_score":  round(keyword_score, 4),
        "source_boost":   round(src_boost_raw, 4),
        "recency_boost":  round(rec_boost, 4),
        "combined_score": round(combined, 4),
    }


def _recency_boost_scaled(published_at_str: str, max_boost: float) -> float:
    """Exponential decay recency boost; half-life = 365 days."""
    if not published_at_str:
        return 0.0
    try:
        parts = published_at_str.split("-")
        pub = date(int(parts[0]), int(parts[1]), int(parts[2]))
        age_days = max(0, (date.today() - pub).days)
        return max_boost * (0.5 ** (age_days / 365.0))
    except Exception:
        return 0.0


# ── Public entry point ─────────────────────────────────────────────────────────

async def financial_rag_search(
    query: str,
    db: AsyncSession,
    *,
    symbol: str | None = None,
    market: str | None = None,
    top_k: int = _DEFAULT_TOP_K,
    source_type: str | None = None,
    report_year: int | None = None,
    report_type: str | None = None,
    search_mode: str = "hybrid",
) -> dict:
    """
    Hybrid RAG search for financial document chunks.

    Parameters
    ----------
    query        : natural-language query string
    db           : async SQLAlchemy session (read-only)
    symbol       : filter by stock symbol (e.g. "AAPL")
    market       : filter by market ("US" | "CN" | "HK")
    top_k        : max results (clamped 1–10)
    source_type  : filter by document type (e.g. "annual_report")
    report_year  : filter by year in document metadata
    report_type  : filter by report_type in metadata (e.g. "annual")
    search_mode  : "hybrid" | "vector" | "keyword"

    Returns
    -------
    See module docstring for the full return shape (including diagnostics).
    Never raises.
    """
    top_k = min(max(1, top_k), _MAX_TOP_K)
    t0 = time.monotonic()

    diag: dict[str, Any] = {
        "search_mode_requested":            search_mode,
        "search_mode_used":                 search_mode,
        "vector_available":                 False,
        "keyword_fallback_used":            False,
        "embedding_provider":               _cfg_str("embedding_provider", "mock"),
        "candidate_count":                  0,
        "returned_count":                   0,
        "mmr_enabled":                      _cfg_bool("rag_mmr_enabled", True),
        # Phase 2D.5 enhanced diagnostics
        "mmr_strategy":                     "disabled",
        "score_weights":                    {
            "vector":   _cfg("rag_vector_weight",       0.6),
            "keyword":  _cfg("rag_keyword_weight",      0.3),
            "source":   _cfg("rag_source_boost_weight", 0.07),
            "recency":  _cfg("rag_recency_boost_weight", 0.03),
        },
        "embedding_coverage_in_candidates": 0.0,
        "official_source_ratio":            0.0,
    }

    try:
        results, mode_used, candidates, extra_diag = await _dispatch(
            db, query,
            symbol=symbol, market=market, top_k=top_k,
            source_type=source_type, report_year=report_year,
            report_type=report_type, search_mode=search_mode,
            diag=diag,
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        diag["search_mode_used"] = mode_used
        diag["candidate_count"]  = candidates
        diag["returned_count"]   = len(results)
        diag.update(extra_diag)
        log.debug(
            "financial_rag_search: mode=%s→%s query=%r results=%d elapsed=%dms",
            search_mode, mode_used, query[:60], len(results), elapsed_ms,
        )
        return {
            "ok":          True,
            "query":       query,
            "results":     results,
            "search_mode": mode_used,
            "elapsed_ms":  elapsed_ms,
            "diagnostics": diag,
        }

    except Exception as exc:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        log.warning("financial_rag_search failed: %s", exc)
        diag["search_mode_used"] = search_mode
        return {
            "ok":          False,
            "query":       query,
            "results":     [],
            "search_mode": search_mode,
            "elapsed_ms":  elapsed_ms,
            "error":       str(exc),
            "diagnostics": diag,
        }


# ── Dispatch ───────────────────────────────────────────────────────────────────

async def _dispatch(
    db: AsyncSession,
    query: str,
    *,
    symbol: str | None,
    market: str | None,
    top_k: int,
    source_type: str | None,
    report_year: int | None,
    report_type: str | None,
    search_mode: str,
    diag: dict,
) -> tuple[list[dict], str, int, dict]:
    """Return (results, mode_actually_used, candidate_count, extra_diag)."""
    mmr_enabled = _cfg_bool("rag_mmr_enabled", True)

    def _apply_mmr(raw: list[dict]) -> tuple[list[dict], str]:
        """Apply MMR and return (filtered_results, mmr_strategy_label)."""
        if not mmr_enabled:
            return raw[:top_k], "disabled"
        final, strategy = _mmr_filter_with_strategy(raw, top_k)
        return final, strategy

    def _extra(candidates_list: list[dict], mmr_strategy: str) -> dict:
        """Build extra diagnostics dict from candidate list."""
        total = len(candidates_list)
        with_vec = sum(1 for r in candidates_list if r.get("_chunk_vec"))
        official = sum(
            1 for r in candidates_list
            if r["metadata"].get("source_level") in ("official_exchange", "official_company")
        )
        return {
            "mmr_strategy":                   mmr_strategy,
            "embedding_coverage_in_candidates": round(with_vec / total, 4) if total else 0.0,
            "official_source_ratio":           round(official / total, 4) if total else 0.0,
        }

    if search_mode == "keyword":
        raw = await _keyword_search(
            db, query, symbol=symbol, market=market, top_k=top_k,
            source_type=source_type, report_year=report_year,
            report_type=report_type, mode_label="keyword",
        )
        results, strategy = _apply_mmr(raw)
        return results, "keyword", len(raw), _extra(raw, strategy)

    # Try embedding ────────────────────────────────────────────────────────────
    try:
        query_vec = await _get_query_vector(query)
        diag["vector_available"] = True
    except Exception as emb_exc:
        log.info("Vector embedding unavailable (%s) — fallback keyword", emb_exc)
        diag["keyword_fallback_used"] = True
        raw = await _keyword_search(
            db, query, symbol=symbol, market=market, top_k=top_k,
            source_type=source_type, report_year=report_year,
            report_type=report_type, mode_label="keyword",
        )
        results, strategy = _apply_mmr(raw)
        return results, "keyword", len(raw), _extra(raw, strategy)

    # Try vector DB search ─────────────────────────────────────────────────────
    try:
        vector_results = await _vector_search(
            db, query_vec, symbol=symbol, market=market, top_k=top_k,
            source_type=source_type, report_year=report_year,
            report_type=report_type,
        )
    except Exception as vsearch_exc:
        log.info("Vector DB search failed (%s) — fallback keyword", vsearch_exc)
        diag["keyword_fallback_used"] = True
        diag["vector_available"] = False
        raw = await _keyword_search(
            db, query, symbol=symbol, market=market, top_k=top_k,
            source_type=source_type, report_year=report_year,
            report_type=report_type, mode_label="keyword",
        )
        results, strategy = _apply_mmr(raw)
        return results, "keyword", len(raw), _extra(raw, strategy)

    if search_mode == "vector":
        results, strategy = _apply_mmr(vector_results)
        return results, "vector", len(vector_results), _extra(vector_results, strategy)

    # hybrid: merge vector + keyword ───────────────────────────────────────────
    keyword_results = await _keyword_search(
        db, query, symbol=symbol, market=market, top_k=top_k,
        source_type=source_type, report_year=report_year,
        report_type=report_type, mode_label="keyword",
    )

    merged  = _hybrid_merge(vector_results, keyword_results, top_k=top_k)
    results, strategy = _apply_mmr(merged)
    mode    = "hybrid" if (vector_results and keyword_results) else (
        "vector" if vector_results else "keyword"
    )
    return results, mode, len(merged), _extra(merged, strategy)


# ── Query vector ───────────────────────────────────────────────────────────────

async def _get_query_vector(query: str) -> list[float]:
    from app.agents.embedding_service import embed_text  # noqa: PLC0415
    return await embed_text(query)


# ── Filter helpers ─────────────────────────────────────────────────────────────

def _build_filters(
    symbol: str | None,
    market: str | None,
    source_type: str | None,
    report_year: int | None,
    report_type: str | None,
    params: dict[str, Any],
) -> str:
    filters: list[str] = []
    if symbol:
        filters.append("(c.symbol = :symbol OR c.symbol IS NULL)")
        params["symbol"] = symbol.upper()
    if market:
        filters.append("(c.market = :market OR c.market IS NULL)")
        params["market"] = market.upper()
    if source_type:
        filters.append("d.source_type = :source_type")
        params["source_type"] = source_type
    if report_year:
        filters.append(
            "(d.metadata->>'report_year' = :report_year OR "
            " EXTRACT(YEAR FROM d.published_at) = :report_year_int)"
        )
        params["report_year"]     = str(report_year)
        params["report_year_int"] = report_year
    if report_type:
        filters.append("d.metadata->>'report_type' = :report_type")
        params["report_type"] = report_type
    return (" AND " + " AND ".join(filters)) if filters else ""


# ── Vector search ─────────────────────────────────────────────────────────────

async def _vector_search(
    db: AsyncSession,
    query_vec: list[float],
    *,
    symbol: str | None,
    market: str | None,
    top_k: int,
    source_type: str | None,
    report_year: int | None,
    report_type: str | None,
) -> list[dict]:
    params: dict[str, Any] = {"top_k": top_k}
    extra_where = _build_filters(symbol, market, source_type, report_year, report_type, params)
    vec_str = "[" + ",".join(f"{v:.8f}" for v in query_vec) + "]"
    params["query_vec"] = vec_str

    sql = text(f"""
        SELECT
            c.id              AS chunk_id,
            c.chunk_text,
            c.chunk_index,
            c.symbol          AS chunk_symbol,
            c.market          AS chunk_market,
            c.metadata        AS chunk_metadata,
            c.embedding_model,
            d.id              AS doc_id,
            d.title,
            d.source_type,
            d.source,
            d.published_at,
            d.url,
            d.metadata        AS doc_metadata,
            1.0 - (c.embedding_vector <=> :query_vec::vector) AS vector_score,
            c.embedding_vector::text                           AS chunk_vec_text
        FROM financial_document_chunks c
        JOIN financial_documents d ON d.id = c.document_id
        WHERE c.embedding_vector IS NOT NULL
        {extra_where}
        ORDER BY c.embedding_vector <=> :query_vec::vector ASC
        LIMIT :top_k
    """)

    try:
        result = await db.execute(sql, params)
        rows = result.fetchall()
    except Exception as exc:
        raise RuntimeError(f"vector search DB error: {exc}") from exc

    out = []
    for row in rows:
        r = _row_to_result(row, vector_score=float(row.vector_score or 0.0),
                           mode_label="vector")
        # Attach chunk vector for Cosine-MMR (hidden field, stripped before returning)
        r["_chunk_vec"] = _parse_vec_text(getattr(row, "chunk_vec_text", None))
        out.append(r)
    return out


# ── Keyword search ─────────────────────────────────────────────────────────────

async def _keyword_search(
    db: AsyncSession,
    query: str,
    *,
    symbol: str | None,
    market: str | None,
    top_k: int,
    source_type: str | None,
    report_year: int | None,
    report_type: str | None,
    mode_label: str = "keyword",
) -> list[dict]:
    params: dict[str, Any] = {"query_lower": query.lower(), "top_k": top_k}
    extra_where = _build_filters(symbol, market, source_type, report_year, report_type, params)

    sql = text(f"""
        SELECT
            c.id              AS chunk_id,
            c.chunk_text,
            c.chunk_index,
            c.symbol          AS chunk_symbol,
            c.market          AS chunk_market,
            c.metadata        AS chunk_metadata,
            NULL              AS embedding_model,
            d.id              AS doc_id,
            d.title,
            d.source_type,
            d.source,
            d.published_at,
            d.url,
            d.metadata        AS doc_metadata,
            (
                CHAR_LENGTH(LOWER(c.chunk_text || ' ' || COALESCE(d.title, ''))) -
                CHAR_LENGTH(
                    REPLACE(
                        LOWER(c.chunk_text || ' ' || COALESCE(d.title, '')),
                        :query_lower, ''
                    )
                )
            )::float / GREATEST(CHAR_LENGTH(:query_lower), 1)::float AS keyword_raw
        FROM financial_document_chunks c
        JOIN financial_documents d ON d.id = c.document_id
        WHERE (
            LOWER(c.chunk_text)              LIKE '%' || :query_lower || '%'
            OR LOWER(COALESCE(d.title, '')) LIKE '%' || :query_lower || '%'
        )
        {extra_where}
        ORDER BY keyword_raw DESC, c.chunk_index ASC
        LIMIT :top_k
    """)

    try:
        result = await db.execute(sql, params)
        rows = result.fetchall()
    except Exception as exc:
        log.debug("keyword search DB query skipped: %s", exc)
        return []

    out = []
    for row in rows:
        raw_kw   = float(getattr(row, "keyword_raw", 0.0) or 0.0)
        kw_score = min(raw_kw / max(len(query), 1), 1.0)
        out.append(_row_to_result(row, keyword_score=kw_score, mode_label=mode_label))
    return out


# ── Row → result dict ─────────────────────────────────────────────────────────

def _row_to_result(
    row: Any,
    *,
    vector_score: float = 0.0,
    keyword_score: float = 0.0,
    mode_label: str,
) -> dict:
    chunk_meta: dict = row.chunk_metadata or {}
    doc_meta:   dict = row.doc_metadata   or {}
    merged_meta = {**doc_meta, **chunk_meta}

    chunk_text   = (row.chunk_text or "")[:_CHUNK_DISPLAY_LEN]
    published_at = str(row.published_at) if row.published_at else ""
    url          = row.url or merged_meta.get("url", "")
    source_level = _source_level_for_url(url)

    combined, score_detail = _compute_score(
        vector_score, keyword_score, source_level, published_at
    )

    return {
        "title":           row.title or "",
        "source_type":     row.source_type or "document",
        "source":          row.source or "",
        "published_at":    published_at,
        "chunk":           chunk_text,
        "score":           round(combined, 4),
        "score_detail":    score_detail,
        "search_mode_used": mode_label,
        "metadata": {
            "symbol":          row.chunk_symbol or merged_meta.get("symbol", ""),
            "market":          row.chunk_market or merged_meta.get("market", ""),
            "url":             url,
            "page":            merged_meta.get("page"),
            "page_start":      merged_meta.get("page_start"),
            "page_end":        merged_meta.get("page_end"),
            "doc_id":          str(row.doc_id),
            "source_level":    source_level,
            "authority_score": _AUTHORITY_SCORES.get(source_level, 0.3),
            "verified":        source_level in ("official_exchange", "official_company"),
            "report_year":     merged_meta.get("report_year"),
            "report_type":     merged_meta.get("report_type", ""),
            "search_mode_used": mode_label,
        },
    }


# ── Hybrid merge ──────────────────────────────────────────────────────────────

def _hybrid_merge(
    vector_results: list[dict],
    keyword_results: list[dict],
    *,
    top_k: int,
) -> list[dict]:
    """
    Merge vector + keyword results with configurable weights.

    1. Index vector results by (doc_id, chunk_text[:100]) — stable dedup key.
    2. For keyword results that overlap: recompute combined_score with both scores.
    3. Keyword-only results added as-is.
    4. Sort by combined_score DESC.
    5. Does NOT apply MMR — that is done by _mmr_filter() afterwards.
    """
    v_weight = _cfg("rag_vector_weight",  0.6)
    k_weight = _cfg("rag_keyword_weight", 0.3)

    seen: dict[tuple, dict] = {}

    for r in vector_results:
        key = (r["metadata"]["doc_id"], r["chunk"][:100])
        entry = dict(r)
        entry["search_mode_used"] = "vector"
        entry["metadata"] = dict(r["metadata"])
        entry["metadata"]["search_mode_used"] = "vector"
        seen[key] = entry

    for r in keyword_results:
        key = (r["metadata"]["doc_id"], r["chunk"][:100])
        if key in seen:
            existing  = seen[key]
            v_score   = existing["score_detail"]["vector_score"]
            k_score   = r["score_detail"]["keyword_score"]
            s_boost   = existing["score_detail"]["source_boost"]
            rec_boost = existing["score_detail"]["recency_boost"]
            combined  = min(v_weight * v_score + k_weight * k_score + s_boost + rec_boost, 1.0)
            existing["score_detail"]["keyword_score"]  = round(k_score, 4)
            existing["score_detail"]["combined_score"] = round(combined, 4)
            existing["score"]                          = round(combined, 4)
            existing["search_mode_used"]               = "hybrid"
            existing["metadata"]["search_mode_used"]   = "hybrid"
        else:
            entry = dict(r)
            entry["search_mode_used"] = "keyword"
            entry["metadata"] = dict(r["metadata"])
            entry["metadata"]["search_mode_used"] = "keyword"
            seen[key] = entry

    return sorted(seen.values(), key=lambda x: x["score"], reverse=True)[:top_k]


# ── Vec text parser ────────────────────────────────────────────────────────────

def _parse_vec_text(vec_text: str | None) -> list[float] | None:
    """
    Parse a pgvector text representation '[0.1,0.2,...]' into a Python list.
    Returns None if the text is missing or malformed.
    """
    if not vec_text:
        return None
    try:
        stripped = vec_text.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            stripped = stripped[1:-1]
        return [float(v) for v in stripped.split(",") if v.strip()]
    except Exception:
        return None


# ── Cosine similarity ──────────────────────────────────────────────────────────

def _cosine_sim(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length vectors. Returns [−1, 1]."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a)) or 1.0
    mag_b = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (mag_a * mag_b)


# ── Cosine MMR ────────────────────────────────────────────────────────────────

def _cosine_mmr(results: list[dict], top_k: int, lambda_val: float) -> list[dict]:
    """
    Maximal Marginal Relevance using stored chunk cosine vectors.

    MMR(d) = λ * rel(d) - (1-λ) * max_{s ∈ Selected} cos(d, s)

    Requires each result to have a non-None `_chunk_vec` field.
    Assumes results are pre-sorted by `score` DESC.
    """
    if not results:
        return []

    # Seed with the top-scored result (guaranteed highest relevance)
    selected: list[dict]       = [results[0]]
    selected_vecs: list[list[float]] = [results[0]["_chunk_vec"]]
    remaining = results[1:]

    while len(selected) < top_k and remaining:
        best_mmr:  float       = float("-inf")
        best_idx:  int         = 0

        for i, cand in enumerate(remaining):
            rel   = cand["score"]
            c_vec = cand["_chunk_vec"]
            # Redundancy: max cosine similarity to already selected
            red   = max(
                (_cosine_sim(c_vec, s_vec) for s_vec in selected_vecs),
                default=0.0,
            )
            mmr_score = lambda_val * rel - (1.0 - lambda_val) * red
            if mmr_score > best_mmr:
                best_mmr = mmr_score
                best_idx = i

        chosen = remaining.pop(best_idx)
        selected.append(chosen)
        selected_vecs.append(chosen["_chunk_vec"])

    return selected


# ── MMR / diversity filter ─────────────────────────────────────────────────────

def _mmr_filter_with_strategy(results: list[dict], top_k: int) -> tuple[list[dict], str]:
    """
    Apply MMR diversity filter and return (filtered_results, strategy_label).

    Strategy selection:
      "cosine"      — all candidates have _chunk_vec → true Cosine-MMR
      "per_doc_cap" — fallback when vectors absent; limits chunks per doc
      "disabled"    — rag_mmr_enabled=False
    """
    if not _cfg_bool("rag_mmr_enabled", True):
        return results[:top_k], "disabled"

    if not results:
        return [], "disabled"

    lambda_val  = _cfg("rag_mmr_lambda", 0.7)
    max_per_doc = _cfg_int("rag_mmr_max_per_doc", 2)

    # Check if all candidates have chunk vectors
    has_vectors = all(r.get("_chunk_vec") for r in results)

    if has_vectors and len(results) > top_k:
        filtered = _cosine_mmr(results, top_k, lambda_val)
        # Strip hidden _chunk_vec from output
        for r in filtered:
            r.pop("_chunk_vec", None)
        return filtered, "cosine"

    # Fallback: per-doc cap
    # Strip hidden _chunk_vec from all results first
    for r in results:
        r.pop("_chunk_vec", None)

    if len(results) <= top_k:
        return results, "per_doc_cap"

    doc_counts: dict[str, int] = {}
    selected: list[dict]       = []
    deferred: list[dict]       = []

    for r in results:
        doc_id = r["metadata"]["doc_id"]
        count  = doc_counts.get(doc_id, 0)
        if count < max_per_doc:
            selected.append(r)
            doc_counts[doc_id] = count + 1
            if len(selected) == top_k:
                break
        else:
            deferred.append(r)

    # Fill remaining slots from deferred — still respect per-doc cap
    if len(selected) < top_k:
        for r in deferred:
            if len(selected) >= top_k:
                break
            doc_id = r["metadata"]["doc_id"]
            if doc_counts.get(doc_id, 0) < max_per_doc:
                selected.append(r)
                doc_counts[doc_id] = doc_counts.get(doc_id, 0) + 1

    return selected, "per_doc_cap"


def _mmr_filter(results: list[dict], top_k: int) -> list[dict]:
    """
    Backward-compatible MMR wrapper (Phase 2D tests import this by name).

    Delegates to _mmr_filter_with_strategy(); discards the strategy label.
    """
    filtered, _ = _mmr_filter_with_strategy(results, top_k)
    return filtered


# ── Backward-compat aliases (Phase 2C tests import these by name) ─────────────

def _source_boost(source_level: str) -> float:
    """Return source boost value for the given source level (Phase 2C compat)."""
    max_boost = _cfg("rag_source_boost_weight", 0.07)
    return {
        "official_exchange":   max_boost,
        "official_company":    max_boost * 0.85,
        "authoritative_media": max_boost * 0.5,
        "general":             0.0,
    }.get(source_level, 0.0)


def _recency_boost(published_at_str: str) -> float:
    """Return recency boost for the given date string (Phase 2C compat)."""
    return _recency_boost_scaled(
        published_at_str,
        _cfg("rag_recency_boost_weight", 0.03),
    )
