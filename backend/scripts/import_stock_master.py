"""
stock_master 导入脚本
=====================
两种模式：

1. CN 回填模式（默认）：
   uv run python scripts/import_stock_master.py [--dry-run]
   从 stock_industry_map 回填 CN 股票主数据。

2. CSV 导入模式：
   uv run python scripts/import_stock_master.py --csv data/stock_master/hk_stocks.csv --market HK [--dry-run]
   从 CSV 文件导入任意市场的股票主数据。
   CSV 必需列：market,symbol,name,exchange,asset_type,status,source

可重复运行；使用 INSERT ... ON CONFLICT DO UPDATE，幂等。

输出：
    total_candidates / to_upsert / skipped / stock_master_rows_after_upsert
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings
from app.core.database import Base
from app.models import IndustryMaster, StockIndustryMap, StockMaster  # noqa: F401 — populates Base.metadata


# ── Engine ────────────────────────────────────────────────────────────────────

def make_engine():
    return create_async_engine(
        settings.database_url,
        poolclass=NullPool,
        connect_args={"statement_cache_size": 0},
        echo=False,
    )


# ── Symbol helpers ────────────────────────────────────────────────────────────

def infer_exchange(symbol: str) -> str:
    """Infer exchange from CN symbol prefix."""
    if symbol.startswith("6"):
        return "SSE"
    if symbol.startswith("0") or symbol.startswith("3"):
        return "SZSE"
    return ""


def normalize_hk_symbol(symbol: str) -> str:
    """Normalize HK symbol to 5-digit zero-padded format: 700 → 00700."""
    return symbol.strip().lstrip("0").zfill(5)


# ── Build upsert rows from CSV ────────────────────────────────────────────────

def build_rows_from_csv(csv_path: Path, market_override: str) -> tuple[list[dict], int]:
    """
    Read CSV and build upsert row list.
    Returns (rows, skipped_count).
    CSV columns: market,symbol,name,exchange,asset_type,status,source
    """
    upsert_rows: list[dict] = []
    skipped = 0

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            market = (row.get("market") or market_override).strip().upper()
            symbol = (row.get("symbol") or "").strip()
            name   = (row.get("name")   or "").strip()

            if not symbol or not name:
                skipped += 1
                continue

            # Normalize HK symbol to 5-digit format
            if market == "HK":
                symbol = normalize_hk_symbol(symbol)

            upsert_rows.append({
                "id":         uuid.uuid4(),
                "market":     market,
                "symbol":     symbol,
                "name":       name,
                "exchange":   (row.get("exchange")   or "").strip(),
                "asset_type": (row.get("asset_type") or "stock").strip(),
                "status":     (row.get("status")     or "active").strip(),
                "source":     (row.get("source")     or "manual").strip(),
            })

    return upsert_rows, skipped


# ── Build upsert rows from stock_industry_map (CN backfill) ──────────────────

async def build_rows_from_industry_map(
    session: AsyncSession,
    market: str,
) -> tuple[list[dict], int]:
    """
    Pull CN stock data from stock_industry_map (DISTINCT ON symbol).
    Returns (rows, skipped_null_name).
    """
    rows = (await session.execute(text("""
        SELECT DISTINCT ON (symbol)
            market, symbol, stock_name
        FROM stock_industry_map
        WHERE market = :market
          AND stock_name IS NOT NULL
        ORDER BY symbol, industry_code
    """), {"market": market.upper()})).fetchall()

    upsert_rows: list[dict] = []
    skipped = 0

    for r in rows:
        sym  = r.symbol
        name = (r.stock_name or "").strip()
        if not name:
            skipped += 1
            continue
        upsert_rows.append({
            "id":         uuid.uuid4(),
            "market":     market.upper(),
            "symbol":     sym,
            "name":       name,
            "exchange":   infer_exchange(sym),
            "asset_type": "stock",
            "status":     "active",
            "source":     "sw_industry_map",
        })

    return upsert_rows, skipped


# ── Batch upsert ──────────────────────────────────────────────────────────────

async def do_upsert(session: AsyncSession, upsert_rows: list[dict], chunk_size: int = 500) -> None:
    """Batch upsert into stock_master using ON CONFLICT DO UPDATE."""
    for i in range(0, len(upsert_rows), chunk_size):
        chunk = upsert_rows[i : i + chunk_size]
        stmt = pg_insert(StockMaster).values(chunk)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_stock_master_market_symbol",
            set_={
                "name":       stmt.excluded.name,
                "exchange":   stmt.excluded.exchange,
                "status":     stmt.excluded.status,
                "source":     stmt.excluded.source,
                "updated_at": text("now()"),
            },
        )
        await session.execute(stmt)
    await session.commit()


# ── Core runner ───────────────────────────────────────────────────────────────

async def run(market: str, csv_path: Path | None, dry_run: bool) -> None:
    engine = make_engine()
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with AsyncSessionLocal() as session:

        # ── Build rows ──────────────────────────────────────────────
        if csv_path is not None:
            upsert_rows, skipped = build_rows_from_csv(csv_path, market)
            total_candidates = len(upsert_rows) + skipped
            print(f"  total_rows       : {total_candidates}")
            print(f"  skipped          : {skipped}")
        else:
            upsert_rows, skipped = await build_rows_from_industry_map(session, market)
            total_candidates = len(upsert_rows) + skipped
            print(f"  total_candidates : {total_candidates}")
            print(f"  skipped_null_name: {skipped}")

        print(f"  to_upsert        : {len(upsert_rows)}")

        if dry_run:
            print("  [dry-run] no changes written.")
            await engine.dispose()
            return

        if not upsert_rows:
            print("  nothing to insert.")
            await engine.dispose()
            return

        # ── Upsert ──────────────────────────────────────────────────
        await do_upsert(session, upsert_rows)

        # ── Final count ─────────────────────────────────────────────
        final_count = (await session.execute(
            text("SELECT COUNT(*) FROM stock_master WHERE market = :m"),
            {"m": market.upper()},
        )).scalar()

        print(f"  stock_master rows after upsert: {final_count}")
        print(f"  upsert complete ✅")

    await engine.dispose()


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Import stock_master data")
    parser.add_argument("--market",  default="CN", help="Market code (default: CN)")
    parser.add_argument("--csv",     default=None, help="Path to CSV file (enables CSV mode)")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no DB writes")
    args = parser.parse_args()

    csv_path = Path(args.csv) if args.csv else None
    if csv_path and not csv_path.exists():
        print(f"ERROR: CSV file not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    mode = "CSV" if csv_path else "industry_map backfill"
    print(f"\n=== import_stock_master ({'DRY RUN' if args.dry_run else 'LIVE'} | {mode}) ===")
    print(f"  market: {args.market.upper()}")
    if csv_path:
        print(f"  csv   : {csv_path}")

    asyncio.run(run(args.market, csv_path, args.dry_run))


if __name__ == "__main__":
    main()
