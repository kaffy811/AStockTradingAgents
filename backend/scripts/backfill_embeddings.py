"""
scripts/backfill_embeddings.py — Phase 2D: CLI for batch embedding backfill.

Usage examples:

  # Backfill all un-embedded chunks (with confirmation prompt)
  python scripts/backfill_embeddings.py

  # Backfill in batches of 64, max 500 chunks
  python scripts/backfill_embeddings.py --batch-size 64 --limit 500

  # Dry-run: count only, no DB writes
  python scripts/backfill_embeddings.py --dry-run

  # Filter by stock
  python scripts/backfill_embeddings.py --symbol AAPL --market US

  # Skip confirmation (CI / background jobs)
  python scripts/backfill_embeddings.py --yes
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Backfill embedding_vector for financial_document_chunks.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--batch-size",  type=int,  default=64,
                   help="Chunks per embed_texts() call (default 64)")
    p.add_argument("--limit",       type=int,  default=None,
                   help="Max total chunks to process (default: all)")
    p.add_argument("--symbol",      default=None,
                   help="Restrict to this stock symbol, e.g. AAPL")
    p.add_argument("--market",      default=None, choices=["US", "CN", "HK"],
                   help="Restrict to this market")
    p.add_argument("--dry-run",     action="store_true",
                   help="Count only — do NOT write to database")
    p.add_argument("--yes",         action="store_true",
                   help="Skip confirmation prompt (use in CI)")
    return p


async def _run(args: argparse.Namespace) -> int:
    from app.agents.embedding_backfill import backfill_missing_embeddings
    from app.agents.embedding_service import _get_provider
    from app.core.config import settings
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker

    provider = _get_provider()

    # Warn if mock provider in production mode
    if not args.dry_run and provider == "mock":
        print(
            "WARNING: EMBEDDING_PROVIDER=mock — embeddings will be deterministic hashes,\n"
            "         not semantic vectors. Set EMBEDDING_PROVIDER=openai for production.",
            file=sys.stderr,
        )

    # Confirmation prompt (skipped with --yes or --dry-run)
    if not args.yes and not args.dry_run:
        scope = ""
        if args.symbol:
            scope += f" symbol={args.symbol}"
        if args.market:
            scope += f" market={args.market}"
        if args.limit:
            scope += f" limit={args.limit}"
        print(f"Backfill embedding_vector for financial_document_chunks{scope}.")
        print(f"Provider: {provider}   Batch size: {args.batch_size}")
        ans = input("Continue? [y/N] ").strip().lower()
        if ans not in ("y", "yes"):
            print("Aborted.")
            return 0

    engine       = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        result = await backfill_missing_embeddings(
            session,
            batch_size=args.batch_size,
            limit=args.limit,
            symbol=args.symbol,
            market=args.market,
            dry_run=args.dry_run,
        )

        if not args.dry_run and result.get("embedded", 0) > 0:
            await session.commit()

    await engine.dispose()

    # Output
    if args.dry_run:
        print(
            f"[DRY RUN] Would embed up to {result['scanned']} chunks "
            f"with provider={provider}"
        )
    else:
        print(
            f"Backfill complete: "
            f"embedded={result['embedded']} "
            f"failed={result['failed']} "
            f"scanned={result['scanned']}"
        )
        if result.get("errors"):
            print(f"Errors ({len(result['errors'])}):", file=sys.stderr)
            for err in result["errors"][:10]:
                print(f"  {err}", file=sys.stderr)

    return 0 if result.get("ok") else 1


def main() -> None:
    parser = _build_parser()
    args   = parser.parse_args()
    rc     = asyncio.run(_run(args))
    sys.exit(rc)


if __name__ == "__main__":
    main()
