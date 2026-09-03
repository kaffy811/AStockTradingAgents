"""
app/services/rate_limit_service.py — 问财报 Redis 速率限制（Phase 6K）

Strategy: fixed-window per minute + per hour.
Key pattern:
  rl:{scope}:{bucket_key}:min:{window_minute}
  rl:{scope}:{bucket_key}:hr:{window_hour}

Bucket key priority: user_id → session_id → ip → "anon"
Returns RateLimitResult with remaining counts and retry_after hint.

Redis unavailable → silently allow (fail-open for availability).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

_SCOPE = "rc"  # report-chat namespace


@dataclass
class RateLimitResult:
    allowed: bool
    limit_minute: int
    limit_hour: int
    remaining_minute: int
    remaining_hour: int
    # If blocked, seconds until the current window resets (for Retry-After header)
    retry_after_seconds: int | None


def _make_bucket_key(
    user_id: str | int | None,
    session_id: str | None,
    ip: str | None,
) -> str:
    """Choose a bucket key with priority: user_id > session_id > ip > 'anon'."""
    if user_id is not None:
        return f"u:{user_id}"
    if session_id:
        return f"s:{session_id[:32]}"  # truncate long session IDs
    if ip:
        return f"ip:{ip}"
    return "anon"


def _current_windows() -> tuple[int, int]:
    """Return (window_minute, window_hour) as integer epoch-based counters."""
    ts = int(time.time())
    return ts // 60, ts // 3600


async def _get_redis() -> Any | None:
    try:
        from app.core.database import get_redis
        return get_redis()
    except Exception:
        return None


async def check_rate_limit(
    user_id: str | int | None = None,
    session_id: str | None = None,
    ip: str | None = None,
) -> RateLimitResult:
    """
    Check and increment rate limit counters.

    Returns RateLimitResult. If Redis is unavailable, allows the request (fail-open).
    This call always increments the counter even on success — callers should not call
    it speculatively.
    """
    from app.core.config import settings

    limit_min = settings.report_chat_rate_limit_per_minute
    limit_hr = settings.report_chat_rate_limit_per_hour

    if not settings.enable_report_chat_rate_limit:
        return RateLimitResult(
            allowed=True,
            limit_minute=limit_min,
            limit_hour=limit_hr,
            remaining_minute=limit_min,
            remaining_hour=limit_hr,
            retry_after_seconds=None,
        )

    redis = await _get_redis()
    if redis is None:
        # Fail-open: Redis unavailable → allow
        log.debug("rate_limit_service: Redis unavailable, allowing request")
        return RateLimitResult(
            allowed=True,
            limit_minute=limit_min,
            limit_hour=limit_hr,
            remaining_minute=limit_min,
            remaining_hour=limit_hr,
            retry_after_seconds=None,
        )

    bucket = _make_bucket_key(user_id, session_id, ip)
    win_min, win_hr = _current_windows()

    key_min = f"rl:{_SCOPE}:{bucket}:min:{win_min}"
    key_hr = f"rl:{_SCOPE}:{bucket}:hr:{win_hr}"

    try:
        # Pipeline: INCR both keys, then EXPIRE them if they're new
        pipe = redis.pipeline()
        pipe.incr(key_min)
        pipe.incr(key_hr)
        results = await pipe.execute()
        count_min, count_hr = results[0], results[1]

        # Set TTL on first increment to avoid orphaned keys
        # min window: 90s (1.5× the window for safety)
        # hr window: 3900s (1.08× the window)
        if count_min == 1:
            await redis.expire(key_min, 90)
        if count_hr == 1:
            await redis.expire(key_hr, 3900)

        allowed = (count_min <= limit_min) and (count_hr <= limit_hr)

        remaining_min = max(0, limit_min - count_min)
        remaining_hr = max(0, limit_hr - count_hr)

        retry_after: int | None = None
        if not allowed:
            if count_min > limit_min:
                # Seconds until the next minute window
                retry_after = 60 - (int(time.time()) % 60)
            else:
                # Seconds until the next hour window
                retry_after = 3600 - (int(time.time()) % 3600)

        return RateLimitResult(
            allowed=allowed,
            limit_minute=limit_min,
            limit_hour=limit_hr,
            remaining_minute=remaining_min,
            remaining_hour=remaining_hr,
            retry_after_seconds=retry_after,
        )

    except Exception as e:
        log.debug("rate_limit_service error: %s — allowing request", e)
        return RateLimitResult(
            allowed=True,
            limit_minute=limit_min,
            limit_hour=limit_hr,
            remaining_minute=limit_min,
            remaining_hour=limit_hr,
            retry_after_seconds=None,
        )


def rate_limit_meta_dict(result: RateLimitResult) -> dict:
    """Convert RateLimitResult to a serializable dict for API responses."""
    return {
        "allowed":            result.allowed,
        "limit_minute":       result.limit_minute,
        "limit_hour":         result.limit_hour,
        "remaining_minute":   result.remaining_minute,
        "remaining_hour":     result.remaining_hour,
        "retry_after_seconds": result.retry_after_seconds,
    }
