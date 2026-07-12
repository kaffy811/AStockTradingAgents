from __future__ import annotations

import hashlib
import json
from typing import Any

from app.core.structured_debug_logger import sanitize_debug_payload
from app.services.cache_service import cache_service, cache_status


class CompanyV2SnapshotCacheService:
    def __init__(self) -> None:
        self._memory: dict[str, Any] = {}

    def make_key(self, kind: str, ts_code: str, *parts: str) -> str:
        raw = ":".join([kind, ts_code, *parts])
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
        return f"cv2:{kind}:{ts_code}:{digest}"

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


company_v2_snapshot_cache_service = CompanyV2SnapshotCacheService()
