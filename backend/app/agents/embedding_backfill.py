"""
embedding_backfill.py — Phase 2D: Batch re-embed existing chunks.

Public API
----------
backfill_missing_embeddings(db, *, batch_size, limit, symbol, market, dry_run)
    async → dict

Finds financial_document_chunks where embedding_vector IS NULL,
calls embed_texts() in batches, and writes the vectors back.

Design:
  • dry_run=True → count only, no DB write.
  • Single batch failure is non-fatal; recorded in errors[].
  • symbol/market filters for targeted per-stock backfill.
  • limit caps the total chunks processed (useful for gradual rollout).
  • embed_texts imported at module level so it can be patched in tests.
  • Returns structured stats dict.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Module-level import enables test patching via
# patch("app.agents.embedding_backfill.embed_texts", ...)
from app.agents.embedding_service import embed_texts, _get_provider  # noqa: E402

log = logging.getLogger(__name__)

_DEFAULT_BATCH_SIZE = 64
_SELECT_BATCH_SIZE  = 500   # rows per SELECT page (always ≥ embed batch_size)


async def backfill_missing_embeddings(
    db: AsyncSession,
    *,
    batch_size: int = _DEFAULT_BATCH_SIZE,
    limit: int | None = None,
    symbol: str | None = None,
    market: str | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Embed all chunks that have embedding_vector IS NULL.

    Parameters
    ----------
    db         : AsyncSession (caller manages commit / rollback)
    batch_size : number of chunks per embed_texts() call (default 64)
    limit      : stop after processing this many chunks (None = all)
    symbol     : restrict to this stock symbol
    market     : restrict to this market (US/CN/HK)
    dry_run    : if True, skip DB writes — return stats only

    Returns
    -------
    {
        "ok":        bool,
        "dry_run":   bool,
        "scanned":   int,   # total chunks found (or capped at limit)
        "embedded":  int,
        "failed":    int,
        "skipped":   int,
        "batches":   int,
        "errors":    list[str],
    }
    """
    batch_size = max(1, batch_size)
    stats: dict[str, Any] = {
        "ok":       True,
        "dry_run":  dry_run,
        "scanned":  0,
        "embedded": 0,
        "failed":   0,
        "skipped":  0,
        "batches":  0,
        "errors":   [],
    }

    if not dry_run and _get_provider() == "mock":
        log.warning(
            "backfill running with EMBEDDING_PROVIDER=mock; "
            "embeddings will be deterministic hashes, not semantic vectors. "
            "Set EMBEDDING_PROVIDER=openai for production."
        )

    # Resolve embedding model name
    try:
        from app.core.config import settings  # noqa: PLC0415
        embedding_model = getattr(settings, "embedding_model", None) or _get_provider()
    except Exception:
        embedding_model = "mock"

    # Build filter clause
    where_parts = ["c.embedding_vector IS NULL"]
    params: dict[str, Any] = {}
    if symbol:
        where_parts.append("c.symbol = :symbol")
        params["symbol"] = symbol.upper()
    if market:
        where_parts.append("c.market = :market")
        params["market"] = market.upper()
    where_sql = " AND ".join(where_parts)

    # Count total missing
    try:
        cnt_result = await db.execute(
            text(f"SELECT COUNT(*) FROM financial_document_chunks c WHERE {where_sql}"),
            dict(params),
        )
        total_missing = int((cnt_result.fetchone() or [0])[0])
    except Exception as exc:
        log.warning("backfill count query failed: %s", exc)
        stats["ok"] = False
        stats["errors"].append(f"count_error: {exc}")
        return stats

    stats["scanned"] = min(total_missing, limit) if limit is not None else total_missing

    if dry_run:
        log.info("backfill dry_run: %d chunks need embedding", total_missing)
        return stats

    if total_missing == 0:
        log.info("backfill: no chunks to embed")
        return stats

    # Fetch → embed → write loop
    processed = 0
    offset    = 0

    while True:
        remaining   = (limit - processed) if limit is not None else _SELECT_BATCH_SIZE
        if remaining <= 0:
            break

        fetch_count = min(remaining, _SELECT_BATCH_SIZE)
        fetch_params = {**params, "limit": fetch_count, "offset": offset}

        try:
            rows_result = await db.execute(
                text(f"""
                    SELECT c.id, c.chunk_text
                    FROM financial_document_chunks c
                    WHERE {where_sql}
                    ORDER BY c.id
                    LIMIT :limit OFFSET :offset
                """),
                fetch_params,
            )
            rows = rows_result.fetchall()
        except Exception as exc:
            log.error("backfill fetch error at offset %d: %s", offset, exc)
            stats["errors"].append(f"fetch_error@offset{offset}: {exc}")
            stats["ok"] = False
            break

        if not rows:
            break

        # Process in embed batches
        for batch_start in range(0, len(rows), batch_size):
            batch_rows  = rows[batch_start: batch_start + batch_size]
            # SQLAlchemy Row supports index access; SimpleNamespace in tests uses attrs.
            # Use _row_id() / _row_text() helpers for compatibility.
            chunk_ids   = [_row_id(r)   for r in batch_rows]
            chunk_texts = [_row_text(r) for r in batch_rows]

            valid_indices = [i for i, t in enumerate(chunk_texts) if t.strip()]
            if not valid_indices:
                stats["skipped"] += len(batch_rows)
                continue

            valid_ids   = [chunk_ids[i]   for i in valid_indices]
            valid_texts = [chunk_texts[i] for i in valid_indices]

            try:
                vectors = await embed_texts(valid_texts)
                stats["batches"] += 1
            except Exception as emb_exc:
                log.warning("backfill embed batch failed: %s", emb_exc)
                stats["errors"].append(f"embed_error: {emb_exc}")
                stats["failed"] += len(valid_ids)
                processed += len(batch_rows)
                continue

            embedded_at = datetime.now(timezone.utc).isoformat()

            for chunk_id, vec in zip(valid_ids, vectors):
                vec_str = "[" + ",".join(f"{v:.8f}" for v in vec) + "]"
                try:
                    await db.execute(text("""
                        UPDATE financial_document_chunks
                        SET embedding_vector = :vec::vector,
                            embedding_model  = :model,
                            embedded_at      = :embedded_at
                        WHERE id = :chunk_id
                    """), {
                        "vec":         vec_str,
                        "model":       embedding_model,
                        "embedded_at": embedded_at,
                        "chunk_id":    chunk_id,
                    })
                    stats["embedded"] += 1
                except Exception as write_exc:
                    log.warning("backfill write failed for %s: %s", chunk_id, write_exc)
                    stats["errors"].append(f"write_error:{chunk_id}: {write_exc}")
                    stats["failed"] += 1

            skipped_in_batch = len(batch_rows) - len(valid_indices)
            stats["skipped"] += skipped_in_batch
            processed += len(batch_rows)

        offset += len(rows)

        try:
            await db.flush()
        except Exception:
            pass

        if limit is not None and processed >= limit:
            break

    log.info(
        "backfill complete: scanned=%d embedded=%d failed=%d skipped=%d batches=%d",
        stats["scanned"], stats["embedded"], stats["failed"],
        stats["skipped"], stats["batches"],
    )
    return stats


# ── Row compat helpers ─────────────────────────────────────────────────────────
# SQLAlchemy Row objects support index access (r[0]) but SimpleNamespace (used
# in unit tests) requires attribute access (r.id).  These helpers handle both.

def _row_id(r: Any) -> str:
    try:
        return str(r.id)
    except AttributeError:
        return str(r[0])


def _row_text(r: Any) -> str:
    try:
        return r.chunk_text or ""
    except AttributeError:
        return r[1] or ""
