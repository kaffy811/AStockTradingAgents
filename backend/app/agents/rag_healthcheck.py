"""
rag_healthcheck.py — Phase 2D: pgvector readiness check.

Public API
----------
check_pgvector_ready(db) async → dict

Returns a structured health report:
  {
    "ok":                    bool,
    "extension_installed":   bool,
    "embedding_column_exists": bool,
    "vector_index_exists":   bool,
    "chunks_total":          int,
    "chunks_embedded":       int,
    "embedding_coverage":    float,   # 0.0–1.0
    "warnings":              list[str],
  }

Design:
  • Never raises — returns ok=False with warnings on any error.
  • Suitable for a /health/rag admin endpoint or startup logging.
  • All DB queries are read-only SELECT / information_schema lookups.
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)


async def check_pgvector_ready(db: AsyncSession) -> dict:
    """
    Probe the database for pgvector readiness.

    Parameters
    ----------
    db : AsyncSession (read-only; caller manages session lifecycle)

    Returns
    -------
    See module docstring for the full return shape.
    """
    warnings: list[str] = []
    result: dict = {
        "ok":                       False,
        "extension_installed":      False,
        "embedding_column_exists":  False,
        "vector_index_exists":      False,
        "chunks_total":             0,
        "chunks_embedded":          0,
        "embedding_coverage":       0.0,
        "warnings":                 warnings,
    }

    # ── 1. pgvector extension ─────────────────────────────────────────────────
    try:
        ext_row = await db.execute(text("""
            SELECT extname FROM pg_extension WHERE extname = 'vector' LIMIT 1
        """))
        result["extension_installed"] = ext_row.fetchone() is not None
    except Exception as exc:
        log.warning("pgvector extension check failed: %s", exc)
        warnings.append(f"extension_check_error: {exc}")

    if not result["extension_installed"]:
        warnings.append(
            "pgvector extension not installed; "
            "vector search will fallback to keyword"
        )

    # ── 2. embedding_vector column ────────────────────────────────────────────
    try:
        col_row = await db.execute(text("""
            SELECT 1
            FROM information_schema.columns
            WHERE table_name   = 'financial_document_chunks'
              AND column_name  = 'embedding_vector'
            LIMIT 1
        """))
        result["embedding_column_exists"] = col_row.fetchone() is not None
    except Exception as exc:
        log.warning("embedding_column check failed: %s", exc)
        warnings.append(f"column_check_error: {exc}")

    if not result["embedding_column_exists"]:
        warnings.append(
            "embedding_vector column missing; "
            "run: alembic upgrade head"
        )

    # ── 3. HNSW / IVFFlat index ───────────────────────────────────────────────
    try:
        idx_row = await db.execute(text("""
            SELECT indexname
            FROM pg_indexes
            WHERE tablename = 'financial_document_chunks'
              AND indexname  LIKE '%embedding_vector%'
            LIMIT 1
        """))
        result["vector_index_exists"] = idx_row.fetchone() is not None
    except Exception as exc:
        log.warning("vector index check failed: %s", exc)
        warnings.append(f"index_check_error: {exc}")

    if not result["vector_index_exists"]:
        warnings.append(
            "No vector index found on embedding_vector; "
            "ANN search will be slow (sequential scan)"
        )

    # ── 4. Coverage stats ─────────────────────────────────────────────────────
    try:
        stats_row = await db.execute(text("""
            SELECT
                COUNT(*)                                         AS total,
                COUNT(*) FILTER (WHERE embedding_vector IS NOT NULL) AS embedded
            FROM financial_document_chunks
        """))
        row = stats_row.fetchone()
        if row:
            total    = int(row[0] or 0)
            embedded = int(row[1] or 0)
            result["chunks_total"]    = total
            result["chunks_embedded"] = embedded
            result["embedding_coverage"] = round(
                embedded / total if total > 0 else 0.0, 4
            )
            if total > 0 and embedded < total:
                missing = total - embedded
                warnings.append(
                    f"{missing} chunks have no embedding_vector; "
                    "run backfill_embeddings to enable full vector search"
                )
    except Exception as exc:
        log.warning("coverage stats query failed: %s", exc)
        warnings.append(f"coverage_stats_error: {exc}")

    # ── 5. Overall ok ─────────────────────────────────────────────────────────
    result["ok"] = (
        result["extension_installed"]
        and result["embedding_column_exists"]
    )

    return result
