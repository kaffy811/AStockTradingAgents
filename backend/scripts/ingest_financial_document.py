"""
scripts/ingest_financial_document.py — Phase 2B: CLI Document Ingest Tool.

Usage examples:

  # Import a PDF annual report
  python scripts/ingest_financial_document.py \\
    --file ./data/apple_annual_report.pdf \\
    --symbol AAPL --market US \\
    --title "Apple 2025 Annual Report" \\
    --source-type annual_report \\
    --source SEC \\
    --published-at 2025-10-30

  # Import raw text
  python scripts/ingest_financial_document.py \\
    --raw-text "Revenue grew 6% to 400 billion..." \\
    --title "Apple Q3 Note" \\
    --source-type research_report \\
    --source "Morgan Stanley"

  # Dry run (no DB write, shows chunk preview)
  python scripts/ingest_financial_document.py \\
    --file report.pdf --title "Test" --source-type annual_report --source SEC \\
    --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

VALID_SOURCE_TYPES = [
    "annual_report", "quarterly_report", "semi_annual_report",
    "announcement", "research_report", "regulation", "document", "other",
]


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Ingest a financial document into the RAG knowledge base.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    grp = p.add_mutually_exclusive_group()
    grp.add_argument("--file",     metavar="PATH",  help="Path to PDF / HTML / TXT / MD file")
    grp.add_argument("--raw-text", metavar="TEXT",  help="Raw text content to ingest directly")

    p.add_argument("--title",        required=True, help="Document title")
    p.add_argument("--source-type",  required=True, choices=VALID_SOURCE_TYPES,
                   help="Document category")
    p.add_argument("--source",       required=True, help="Source name (e.g. SEC, 上交所)")
    p.add_argument("--symbol",       default=None, help="Stock symbol, e.g. AAPL or 600519")
    p.add_argument("--market",       default=None, choices=["US", "CN", "HK"],
                   help="Market: US | CN | HK")
    p.add_argument("--published-at", default=None, metavar="YYYY-MM-DD",
                   help="Publication date of the document")
    p.add_argument("--url",          default=None, help="Source URL")
    p.add_argument("--dry-run",      action="store_true",
                   help="Parse and chunk only — do NOT write to database")
    p.add_argument("--no-embedding", action="store_true",
                   help="Skip embedding generation (use keyword-only RAG for this document)")
    return p


async def _run(args: argparse.Namespace) -> int:
    from app.agents.financial_document_ingest import (
        clean_financial_text,
        chunk_financial_text,
        _parse_pdf,
        _parse_html,
        ingest_financial_document,
    )

    # ── Resolve text content ──────────────────────────────────────────────────
    raw_text: str | None = None
    page_map: list = []

    if args.file:
        if not os.path.exists(args.file):
            print(f"ERROR: File not found: {args.file}", file=sys.stderr)
            return 1

        ext = args.file.lower().rsplit(".", 1)[-1] if "." in args.file else ""

        if ext == "pdf":
            try:
                raw_text, page_map = _parse_pdf(args.file)
            except RuntimeError as exc:
                print(f"ERROR: PDF parse failed: {exc}", file=sys.stderr)
                return 1

        elif ext in ("html", "htm"):
            try:
                with open(args.file, encoding="utf-8", errors="replace") as f:
                    raw_text = _parse_html(f.read())
            except OSError as exc:
                print(f"ERROR: Cannot read HTML: {exc}", file=sys.stderr)
                return 1

        else:
            try:
                with open(args.file, encoding="utf-8", errors="replace") as f:
                    raw_text = f.read()
            except OSError as exc:
                print(f"ERROR: Cannot read file: {exc}", file=sys.stderr)
                return 1

    elif args.raw_text:
        raw_text = args.raw_text
    else:
        print("ERROR: Provide --file or --raw-text.", file=sys.stderr)
        return 1

    if not raw_text or not raw_text.strip():
        print("ERROR: Document content is empty after parsing.", file=sys.stderr)
        return 1

    # ── Clean + chunk ─────────────────────────────────────────────────────────
    clean_text = clean_financial_text(raw_text)
    chunks     = chunk_financial_text(clean_text, page_map=page_map or None)

    print(f"Parsed:  {len(raw_text):,} chars  →  clean {len(clean_text):,} chars")
    print(f"Chunks:  {len(chunks)}")

    if len(chunks) >= 2:
        print("\n── Chunk 0 preview (first 300 chars) ──")
        print(chunks[0]["chunk_text"][:300])
        print("── Chunk 1 preview ──")
        print(chunks[1]["chunk_text"][:300])
    elif chunks:
        print("\n── Chunk 0 preview ──")
        print(chunks[0]["chunk_text"][:300])

    if args.dry_run:
        print("\n[DRY RUN] No database write.")
        return 0

    # ── DB write ──────────────────────────────────────────────────────────────
    print("\nConnecting to database …")
    from app.core.config import settings
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker

    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        result = await ingest_financial_document(
            db=session,
            raw_text=raw_text,
            url=args.url,
            symbol=args.symbol,
            market=args.market,
            title=args.title,
            source_type=args.source_type,
            source=args.source,
            published_at=args.published_at,
            enable_embedding=not getattr(args, "no_embedding", False),
        )
        if result.get("ok"):
            if result.get("duplicate"):
                print(
                    f"Duplicate — already in DB: document_id={result['document_id']}"
                )
            else:
                await session.commit()
                warnings = result.get("warnings", [])
                warn_str = f"  warnings={warnings}" if warnings else ""
                print(
                    f"Inserted document_id={result['document_id']}  "
                    f"chunks={result['chunks_inserted']}{warn_str}"
                )
        else:
            print(f"ERROR: {result.get('error', 'unknown')}", file=sys.stderr)
            return 1

    await engine.dispose()
    return 0


def main() -> None:
    parser = _build_parser()
    args   = parser.parse_args()
    rc     = asyncio.run(_run(args))
    sys.exit(rc)


if __name__ == "__main__":
    main()
