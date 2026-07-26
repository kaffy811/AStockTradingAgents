#!/usr/bin/env python3
"""
scripts/cleanup_report_cache.py — Clean expired report-chat cache & session memory.

Deletes:
  - Report-chat cache keys: rc:{version}:{ts_code}:*
  - Session memory keys:   cm:{session_id}:{ts_code}

Does NOT delete:
  - report_documents table rows
  - report_chunks table rows
  - Any other Redis keys

Usage:
    # Dry run — show what would be deleted:
    uv run python scripts/cleanup_report_cache.py --dry-run

    # Delete all cache + memory keys:
    uv run python scripts/cleanup_report_cache.py

    # Delete only keys for a specific stock:
    uv run python scripts/cleanup_report_cache.py --ts-code 600519.SH

    # Delete only cache (not session memory):
    uv run python scripts/cleanup_report_cache.py --cache-only

    # Delete only session memory (not cache):
    uv run python scripts/cleanup_report_cache.py --memory-only

Exit codes:
    0 — success or dry run
    1 — Redis unavailable or error
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

log = logging.getLogger("cleanup_report_cache")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


async def _scan_and_delete(redis, pattern: str, dry_run: bool) -> int:
    """Scan keys matching pattern and delete them. Returns count deleted."""
    deleted = 0
    cursor = 0
    while True:
        cursor, keys = await redis.scan(cursor=cursor, match=pattern, count=100)
        if keys:
            if dry_run:
                for k in keys:
                    log.info("  [dry-run] would delete: %s", k.decode() if isinstance(k, bytes) else k)
            else:
                await redis.delete(*keys)
            deleted += len(keys)
        if cursor == 0:
            break
    return deleted


async def _main_async(args: argparse.Namespace) -> int:
    from app.core.database import connect_redis, get_redis, close_redis

    await connect_redis()
    redis = get_redis()
    if redis is None:
        log.error("Redis is unavailable. Set REDIS_URL in environment.")
        return 1

    from app.core.config import settings
    cache_version = settings.report_chat_cache_version

    ts_filter = f"{args.ts_code.upper()}:*" if args.ts_code else "*"

    results = {"timestamp": datetime.utcnow().isoformat(), "dry_run": args.dry_run}

    if not args.memory_only:
        cache_pattern = f"rc:{cache_version}:{ts_filter}"
        log.info("Scanning cache keys: %s", cache_pattern)
        n = await _scan_and_delete(redis, cache_pattern, args.dry_run)
        results["cache_keys_deleted"] = n
        log.info("%s cache keys %s", n, "found (dry-run)" if args.dry_run else "deleted")

    if not args.cache_only:
        mem_pattern = f"cm:*:{args.ts_code.upper()}" if args.ts_code else "cm:*"
        log.info("Scanning session memory keys: %s", mem_pattern)
        n = await _scan_and_delete(redis, mem_pattern, args.dry_run)
        results["memory_keys_deleted"] = n
        log.info("%s session memory keys %s", n, "found (dry-run)" if args.dry_run else "deleted")

    await close_redis()

    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Cleanup report-chat cache and session memory")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted, no writes")
    parser.add_argument("--ts-code", help="Limit to a specific ts_code, e.g. 600519.SH")
    parser.add_argument("--cache-only", action="store_true", help="Delete only report-chat cache keys")
    parser.add_argument("--memory-only", action="store_true", help="Delete only session memory keys")
    args = parser.parse_args()

    if args.cache_only and args.memory_only:
        print("ERROR: --cache-only and --memory-only are mutually exclusive", file=sys.stderr)
        return 1

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
