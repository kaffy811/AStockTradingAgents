from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any
from uuid import uuid4

from app.core.structured_debug_logger import sanitize_debug_payload
from app.services.cache_service import cache_service, cache_status


_CACHE_META_KEY = "_cache_meta"
_CACHE_VALUE_KEY = "value"


class CompanyV2SnapshotCacheService:
    def __init__(self) -> None:
        self._memory: dict[str, Any] = {}
        self._memory_locks: dict[str, tuple[str, float]] = {}

    def make_key(self, kind: str, ts_code: str, *parts: str) -> str:
        raw = ":".join([kind, ts_code, *parts])
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
        return f"cv2:{kind}:{ts_code}:{digest}"

    def make_company_key(self, kind: str, market: str, symbol: str, *parts: str, version: str) -> str:
        clean_parts = [str(part) for part in parts if part not in (None, "")]
        return ":".join([kind, market.upper(), symbol, *clean_parts, version])

    async def get(self, key: str, *, force_refresh: bool = False) -> tuple[Any | None, bool, bool, str]:
        if force_refresh:
            return None, False, False, cache_status()
        cached = await cache_service.get_json(key)
        if cached is None:
            cached = self._memory.get(key)
        if cached is None:
            return None, False, False, cache_status()
        return cached, True, bool(cached.get("_stale", False)) if isinstance(cached, dict) else False, cache_status()

    async def set(self, key: str, value: Any, ttl: int) -> None:
        safe = sanitize_debug_payload(value, max_chars=200000)
        self._memory[key] = safe
        await cache_service.set_json(key, safe, ttl)

    async def get_swr(self, key: str, *, force_refresh: bool = False) -> tuple[Any | None, str, str]:
        """
        Return (value, swr_status, cache_status).
        swr_status: miss | fresh | stale | expired
        """
        if force_refresh:
            return None, "miss", cache_status()
        cached = await cache_service.get_json(key)
        if cached is None:
            cached = self._memory.get(key)
        if cached is None:
            return None, "miss", cache_status()

        if not isinstance(cached, dict) or _CACHE_META_KEY not in cached:
            return cached, "fresh", cache_status()

        meta = cached.get(_CACHE_META_KEY) or {}
        value = cached.get(_CACHE_VALUE_KEY)
        now = time.time()
        fresh_until = float(meta.get("fresh_until") or 0)
        stale_until = float(meta.get("stale_until") or 0)
        if fresh_until >= now:
            return value, "fresh", cache_status()
        if stale_until >= now:
            return value, "stale", cache_status()
        return value, "expired", cache_status()

    async def set_swr(self, key: str, value: Any, *, fresh_ttl: int, stale_ttl: int) -> None:
        safe = sanitize_debug_payload(value, max_chars=300000)
        now = time.time()
        payload = {
            _CACHE_META_KEY: {
                "created_at": now,
                "fresh_until": now + max(1, fresh_ttl),
                "stale_until": now + max(1, fresh_ttl + stale_ttl),
                "cache_key": key,
                "version": key.split(":")[-1] if ":" in key else "",
            },
            _CACHE_VALUE_KEY: safe,
        }
        self._memory[key] = payload
        await cache_service.set_json(key, payload, max(1, fresh_ttl + stale_ttl))

    async def acquire_refresh_lock(self, key: str, *, ttl: int = 15) -> str | None:
        lock_key = f"lock:{key}"
        token = str(uuid4())
        if await cache_service.set_lock(lock_key, token, ttl):
            return token
        now = time.time()
        existing = self._memory_locks.get(lock_key)
        if existing and existing[1] > now:
            return None
        self._memory_locks[lock_key] = (token, now + ttl)
        return token

    async def release_refresh_lock(self, key: str, token: str | None) -> None:
        if not token:
            return
        lock_key = f"lock:{key}"
        await cache_service.release_lock(lock_key, token)
        existing = self._memory_locks.get(lock_key)
        if existing and existing[0] == token:
            self._memory_locks.pop(lock_key, None)

    async def invalidate_patterns(self, patterns: list[str]) -> dict[str, int]:
        deleted: dict[str, int] = {}
        for pattern in patterns:
            deleted[pattern] = await cache_service.delete_pattern(pattern)
            for key in list(self._memory.keys()):
                if _pattern_match(pattern, key):
                    self._memory.pop(key, None)
        return deleted


def _pattern_match(pattern: str, key: str) -> bool:
    if "*" not in pattern:
        return pattern == key
    prefix, _, suffix = pattern.partition("*")
    return key.startswith(prefix) and (not suffix or key.endswith(suffix))


company_v2_snapshot_cache_service = CompanyV2SnapshotCacheService()
