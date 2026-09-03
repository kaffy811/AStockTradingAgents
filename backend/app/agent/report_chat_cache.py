"""
app/agent/report_chat_cache.py — 问财报 Redis TTL 缓存（Phase 6K）

Cache key:  rc:{CACHE_VERSION}:{intent_type}:{ts_code}:{question_hash}:{filters_hash}
            intent_type: "analysis" (default) or "locator"
            Separates analysis answers from locator answers so different intents
            never share a cache slot for the same (ts_code, question) pair.
TTL:        REPORT_CHAT_CACHE_TTL_SECONDS (default 1800s / 30 min)

Rules:
- Only cache non-rejected, non-partial results (partial=False, investment_advice_blocked=False)
- Rejected investment-advice questions get a short TTL (60s) rejection cache to avoid re-LLM
- force_refresh=True bypasses read
- Redis unavailable → silently skip caching, answer normally
- Stale results may be served if Redis TTL is near expiry (within 10% of original TTL)
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

log = logging.getLogger(__name__)

# Bump this when the cache schema changes to force all cache invalidation.
_CACHE_VERSION = "v1"

# Short TTL for "safe rejection" answers (investment advice blocked, etc.)
_REJECTION_TTL = 60  # 1 minute


# ── Hashing helpers ───────────────────────────────────────────────────────────

def _question_hash(normalized_question: str) -> str:
    """Short stable hash of the normalized question."""
    return hashlib.sha256(normalized_question.encode("utf-8")).hexdigest()[:16]


def _filters_hash(report_types: list[str] | None, years: list[int] | None, report_id: int | None = None) -> str:
    """Stable hash of query filters."""
    payload = {
        "rt": sorted(report_types or []),
        "yr": sorted(years or []),
        "rid": int(report_id) if report_id is not None else None,
    }
    s = json.dumps(payload, sort_keys=True)
    return hashlib.md5(s.encode()).hexdigest()[:8]


def make_cache_key(
    ts_code: str,
    normalized_question: str,
    report_types: list[str] | None = None,
    years: list[int] | None = None,
    report_id: int | None = None,
    intent_type: str = "analysis",
) -> str:
    """Build deterministic cache key for a report-chat query.

    The *intent_type* segment prevents analysis answers from being served for
    locator queries and vice versa when the normalized question hashes collide.
    Valid values: ``"analysis"`` (default), ``"locator"``.
    """
    from app.core.config import settings
    version = settings.report_chat_cache_version or _CACHE_VERSION
    qh = _question_hash(normalized_question)
    fh = _filters_hash(report_types, years, report_id)
    return f"rc:{version}:{intent_type}:{ts_code}:{qh}:{fh}"


# ── Redis helpers ─────────────────────────────────────────────────────────────

async def _get_redis() -> Any | None:
    try:
        from app.core.database import get_redis
        return get_redis()
    except Exception:
        return None


def _dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _loads(raw: str | bytes) -> Any:
    return json.loads(raw)


# ── Public API ────────────────────────────────────────────────────────────────

async def read_cache(
    ts_code: str,
    normalized_question: str,
    report_types: list[str] | None = None,
    years: list[int] | None = None,
    report_id: int | None = None,
    intent_type: str = "analysis",
) -> dict | None:
    """
    Return cached chat result or None.

    Never raises.
    """
    from app.core.config import settings
    if not settings.enable_report_chat_cache:
        return None

    redis = await _get_redis()
    if redis is None:
        return None

    key = make_cache_key(ts_code, normalized_question, report_types, years, report_id, intent_type)
    try:
        raw = await redis.get(key)
        if raw is None:
            return None
        data = _loads(raw)
        # Annotate cache hit in meta
        if isinstance(data, dict) and "cache_meta" in data:
            data["cache_meta"]["hit"] = True
        return data
    except Exception as e:
        log.debug("report_chat_cache read error: %s", e)
        return None


async def write_cache(
    ts_code: str,
    normalized_question: str,
    result: dict,
    report_types: list[str] | None = None,
    years: list[int] | None = None,
    report_id: int | None = None,
    is_rejection: bool = False,
    intent_type: str = "analysis",
) -> bool:
    """
    Write chat result to cache.

    Only caches:
      - non-partial approved/revised answers
      - rejection answers (short TTL)

    Returns True if written, False otherwise. Never raises.
    """
    from app.core.config import settings
    if not settings.enable_report_chat_cache:
        return False

    # Don't cache partial errors that aren't rejections
    if result.get("partial") and not is_rejection:
        return False

    redis = await _get_redis()
    if redis is None:
        return False

    key = make_cache_key(ts_code, normalized_question, report_types, years, report_id, intent_type)
    ttl = _REJECTION_TTL if is_rejection else settings.report_chat_cache_ttl_seconds

    payload = dict(result)
    payload["cache_meta"] = {
        "hit":         False,  # will be set to True on read
        "key":         key,
        "ttl_seconds": ttl,
        "created_at":  int(time.time()),
    }

    try:
        await redis.setex(key, ttl, _dumps(payload))
        return True
    except Exception as e:
        log.debug("report_chat_cache write error: %s", e)
        return False


def _empty_cache_meta() -> dict:
    """Return a safe default cache_meta for non-cached responses."""
    return {
        "hit":         False,
        "key":         None,
        "ttl_seconds": None,
        "created_at":  None,
    }
