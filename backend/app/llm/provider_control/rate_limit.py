"""
Cross-worker rate limiter — Phase 6V-P1.31.

Uses Redis sliding window (fixed 60-second window) with Lua atomic INCR.
"""
from __future__ import annotations

import time
from typing import Any

from .models import RateLimitState
from .errors import RateLimitExceededError

# Lua: atomic rate limit check+increment within sliding window
# KEYS[1] = window count key, ARGV[1] = window_seconds TTL, ARGV[2] = limit
# Returns new count, or -1 if over limit
_LUA_RATE_LIMIT = """
local current = redis.call('GET', KEYS[1])
if current == false then current = 0 else current = tonumber(current) end
if current >= tonumber(ARGV[2]) then return -1 end
local new_val = redis.call('INCR', KEYS[1])
if new_val == 1 then
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
end
return new_val
"""


class SlidingWindowRateLimiter:
    """
    Per-minute rate limiter backed by Redis.

    Uses a fixed window (60s) with Lua atomic check+increment.
    Window key rotates every `window_seconds` seconds.
    All workers share the same Redis key → truly cross-worker.
    """

    def __init__(
        self,
        redis_client: Any,
        *,
        namespace: str = "pi_provider_rate",
        limit_per_minute: int = 60,
        window_seconds: int = 60,
    ) -> None:
        self._redis = redis_client
        self._ns = namespace
        self._limit = limit_per_minute
        self._window_s = window_seconds

    def _window_key(self) -> str:
        window_id = int(time.time()) // self._window_s
        return f"{self._ns}:window:{window_id}"

    def try_acquire(self) -> bool:
        """Attempt to acquire a rate limit slot. Returns True if successful."""
        key = self._window_key()
        result = self._redis.eval(
            _LUA_RATE_LIMIT, 1, key, str(self._window_s), str(self._limit)
        )
        return int(result) != -1

    def acquire_or_raise(self) -> None:
        """Acquire slot or raise RateLimitExceededError."""
        if not self.try_acquire():
            raise RateLimitExceededError(
                f"Rate limit exceeded: max {self._limit} requests per {self._window_s}s.",
                retry_after_seconds=float(self._window_s),
            )

    def get_current_count(self) -> int:
        key = self._window_key()
        raw = self._redis.get(key)
        if raw is None:
            return 0
        return int(raw)

    def get_state(self) -> RateLimitState:
        return RateLimitState(
            requests_in_window=self.get_current_count(),
            window_seconds=self._window_s,
            limit_per_window=self._limit,
            namespace=self._ns,
        )
