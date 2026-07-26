#!/usr/bin/env python3
"""
scripts/rebuild_report_index.py — Rebuild the report RAG index.

For each stock that has downloaded / parsed PDF reports, re-runs the
chunk + embed pipeline and upserts chunks into the report_chunks table.

Usage:
    # Rebuild all indexed stocks (dry-run):
    uv run python scripts/rebuild_report_index.py --dry-run

    # Rebuild a specific stock:
    uv run python scripts/rebuild_report_index.py --symbol 600519.SH

    # Rebuild all with a limit:
    uv run python scripts/rebuild_report_index.py --limit 10

    # Rebuild all, force re-embed even if chunks exist:
    uv run python scripts/rebuild_report_index.py --force

Exit codes:
    0 — completed (some may be skipped/failed — see summary)
    1 — fatal initialisation error
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Ensure the project root is on sys.path when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

log = logging.getLogger("rebuild_report_index")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


async def _rebuild_one(ts_code: str, report_id: int, force: bool, dry_run: bool) -> dict:
    """Chunk + embed a single report document."""
    from app.services.report_chunk_service import ReportChunkService
    from app.services.report_embedding_service import ReportEmbeddingService
    from app.core.database import AsyncSessionLocal as async_session_factory

    result = {"ts_code": ts_code, "report_id": report_id, "status": "unknown"}
    if dry_run:
        result["status"] = "dry_run"
        return result

    try:
        async with async_session_factory() as db:
            chunk_svc = ReportChunkService(db)
            embed_svc = ReportEmbeddingService(db)

            # Check if already chunked
            existing = await chunk_svc.count_chunks(report_id)
            if existing > 0 and not force:
                result["status"] = "skipped"
                result["reason"] = f"{existing} chunks already exist (use --force to re-embed)"
                return result

            # Chunk
            n_chunks = await chunk_svc.chunk_report(report_id)
            if n_chunks == 0:
                result["status"] = "failed"
                result["reason"] = "chunk produced 0 chunks (no text?)"
                return result

            # Embed
            n_embedded = await embed_svc.embed_report(report_id)
            result["status"] = "success"
            result["chunks"] = n_chunks
            result["embedded"] = n_embedded
    except Exception as exc:
        result["status"] = "failed"
        result["reason"] = f"{type(exc).__name__}: {exc}"
        log.error("rebuild_report_index: %s report_id=%d failed: %s", ts_code, report_id, exc)

    return result


async def _main_async(args: argparse.Namespace) -> int:
    from app.core.database import init_db
    from app.models.report_document import ReportDocument
    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal as async_session_factory

    await init_db()

    async with async_session_factory() as db:
        stmt = select(ReportDocument.id, ReportDocument.ts_code).where(
            ReportDocument.parsed.is_(True)
        )
        if args.symbol:
            ts_code = args.symbol.upper()
            stmt = stmt.where(ReportDocument.ts_code == ts_code)
        stmt = stmt.order_by(ReportDocument.id.desc())
        if args.limit:
            stmt = stmt.limit(args.limit)

        from sqlalchemy import text
        result = await db.execute(stmt)
        rows = result.fetchall()

    if not rows:
        log.info("No eligible report documents found.")
        return 0

    log.info("Found %d report documents to process", len(rows))
    if args.dry_run:
        log.info("DRY RUN — no writes will be performed")

    results: list[dict] = []
    for row in rows:
        r = await _rebuild_one(row.ts_code, row.id, force=args.force, dry_run=args.dry_run)
        results.append(r)
        log.info("[%s] %s  report_id=%d", r["status"].upper(), r["ts_code"], r["report_id"])

    success = sum(1 for r in results if r["status"] == "success")
    failed = sum(1 for r in results if r["status"] == "failed")
    skipped = sum(1 for r in results if r["status"] in ("skipped", "dry_run"))

    summary = {
        "timestamp": datetime.utcnow().isoformat(),
        "total": len(results),
        "success": success,
        "failed": failed,
        "skipped": skipped,
        "results": results,
    }

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Rebuild report RAG index")
    parser.add_argument("--symbol", help="Single ts_code to rebuild, e.g. 600519.SH")
    parser.add_argument(
        "--symbols",
        help="Comma-separated ts_codes to rebuild, e.g. 600519.SH,000725.SZ (used when --symbol not set)",
    )
    parser.add_argument("--limit", type=int, help="Max number of reports to process")
    parser.add_argument("--force", action="store_true", help="Re-embed even if chunks already exist")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be processed, no writes")
    args = parser.parse_args()

    # --symbols is handled by running --symbol once per code
    if args.symbols and not args.symbol:
        codes = [c.strip() for c in args.symbols.split(",") if c.strip()]
        import sys as _sys
        for code in codes:
            _args = argparse.Namespace(
                symbol=code, symbols=None, limit=args.limit,
                force=args.force, dry_run=args.dry_run,
            )
            try:
                asyncio.run(_main_async(_args))
            except Exception as exc:
                log.error("Failed for %s: %s", code, exc)
        return 0

    try:
        return asyncio.run(_main_async(args))
    except KeyboardInterrupt:
        log.info("Interrupted by user")
        return 1
    except Exception as exc:
        log.error("Fatal error: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
