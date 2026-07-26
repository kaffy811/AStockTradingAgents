"""Release gate for market-wide security entity resolver coverage.

Writes a JSON artifact with full active-security resolution statistics. The
script intentionally uses the production SecurityEntityResolver aggregation
path instead of fixture rows.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from app.core.database import AsyncSessionLocal
from app.services.security_entity_resolver import (
    INDEX_VERSION,
    SecurityEntityResolver,
    normalize_security_text,
)


DEFAULT_OUTPUT = Path("backend/docs/artifacts/security_entity_index_integrity.json")


def _entity_key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("market") or "").upper(), str(row.get("symbol") or ""))


def _is_active_security(row: dict[str, Any]) -> bool:
    return bool(row.get("symbol")) and str(row.get("entity_type") or "equity").lower() in {"equity", "stock"}


def _first_match_symbol(resolver: SecurityEntityResolver, query: str, rows: list[dict[str, Any]]) -> str | None:
    candidates = resolver._match_candidates(query, rows, min_confidence=0.72)  # noqa: SLF001
    return candidates[0].symbol if candidates else None


async def build_integrity_report(markets: list[str]) -> dict[str, Any]:
    resolver = SecurityEntityResolver()
    started = time.perf_counter()
    report: dict[str, Any] = {
        "version": INDEX_VERSION,
        "generated_at": time.time(),
        "markets": {},
    }

    async with AsyncSessionLocal() as db:
        for market in markets:
            market_started = time.perf_counter()
            rows = [row for row in await resolver._load_index(db, market) if _is_active_security(row)]  # noqa: SLF001
            by_symbol = {_entity_key(row): row for row in rows}
            source_counts = Counter()
            normalized_to_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in rows:
                for source in str(row.get("source") or "unknown").split(";"):
                    source_counts[source] += 1
                for name in row.get("normalized_names") or []:
                    if name:
                        normalized_to_rows[name].append(row)

            duplicate_names = {
                name: [
                    {"market": r.get("market"), "symbol": r.get("symbol"), "short_name": r.get("short_name")}
                    for r in rs
                ]
                for name, rs in normalized_to_rows.items()
                if len({_entity_key(r) for r in rs}) > 1
            }

            short_name_counts = Counter(
                normalize_security_text(row.get("short_name"))
                for row in rows
                if row.get("short_name")
            )
            unique_short_rows = [
                row
                for row in rows
                if row.get("short_name") and short_name_counts[normalize_security_text(row.get("short_name"))] == 1
            ]

            exact_short_ok = 0
            exact_full_ok = 0
            code_ok = 0
            unresolved: list[dict[str, Any]] = []
            ambiguous: list[dict[str, Any]] = []

            for row in unique_short_rows:
                expected = str(row.get("symbol"))
                short_query = f"{row.get('short_name')}最新财报表现如何"
                full_query = str(row.get("full_name") or row.get("short_name") or "")
                code_query = expected

                short_symbol = _first_match_symbol(resolver, short_query, rows)
                full_symbol = _first_match_symbol(resolver, full_query, rows) if full_query else None
                code_symbol = _first_match_symbol(resolver, code_query, rows)

                if short_symbol == expected:
                    exact_short_ok += 1
                else:
                    unresolved.append({
                        "market": row.get("market"),
                        "symbol": expected,
                        "short_name": row.get("short_name"),
                        "query": short_query,
                        "matched_symbol": short_symbol,
                    })
                if full_symbol == expected:
                    exact_full_ok += 1
                if code_symbol == expected:
                    code_ok += 1

            for name, records in duplicate_names.items():
                if name and len(ambiguous) < 100:
                    ambiguous.append({
                        "normalized_name": name,
                        "candidates": records[:8],
                    })

            report["markets"][market] = {
                "total_securities": len(rows),
                "securities_with_short_name": sum(1 for row in rows if row.get("short_name")),
                "indexed_securities": len(by_symbol),
                "exact_short_name_resolvable": exact_short_ok,
                "exact_short_name_tested": len(unique_short_rows),
                "exact_full_name_resolvable": exact_full_ok,
                "code_resolvable": code_ok,
                "duplicate_normalized_names": len(duplicate_names),
                "ambiguous_names_sample": ambiguous[:20],
                "unresolved_records_count": len(unresolved),
                "unresolved_records_sample": unresolved[:50],
                "records_excluded_by_reason": {},
                "source_counts": dict(source_counts),
                "elapsed_ms": round((time.perf_counter() - market_started) * 1000, 2),
            }

    report["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return report


async def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--markets", default="CN,HK,US")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    markets = [m.strip().upper() for m in args.markets.split(",") if m.strip()]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    report = await build_integrity_report(markets)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "output": str(output), "version": INDEX_VERSION}, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(_main())
