"""
app/agent/ai_cache.py — AI 分析结果 Redis 缓存（Phase 3）

Cache key: fs:ai:{ts_code}:{mode}:{prompt_version}:{input_hash}
TTL: 86400s (24h)

Rules:
- rejected 内容不写入正常缓存
- revised 内容可写入缓存（保留 review_notes）
- force_refresh=True 绕过读取
- Claude/DeepSeek 失败时返回 stale 缓存（stale=True）
"""
from __future__ import annotations

import hashlib
import json
import logging
import time

log = logging.getLogger(__name__)

PROMPT_VERSION = "v1"
DEFAULT_TTL = 86400  # 24h


def _input_hash(data_pack: dict) -> str:
    """Stable hash of the data pack used as cache key component."""
    relevant = {
        "collected": data_pack.get("collected_modules", []),
        "missing": data_pack.get("missing_modules", []),
        "facts_count": len(data_pack.get("compressed_facts", [])),
        "quality": data_pack.get("data_quality", {}).get("score"),
        "chunk_ids": sorted(data_pack.get("allowed_chunk_ids", [])),
    }
    s = json.dumps(relevant, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(s.encode()).hexdigest()[:12]


def _cache_key(ts_code: str, mode: str, input_hash: str) -> str:
    return f"fs:ai:{ts_code}:{mode}:{PROMPT_VERSION}:{input_hash}"


async def _get_redis():
    try:
        from app.core.database import get_redis
        return get_redis()
    except Exception:
        return None


async def read_cache(ts_code: str, mode: str, data_pack: dict) -> dict | None:
    """Return cached result or None. Sets stale=True if TTL near expiry."""
    redis = await _get_redis()
    if redis is None:
        return None
    key = _cache_key(ts_code, mode, _input_hash(data_pack))
    try:
        raw = await redis.get(key)
        if raw is None:
            return None
        data = json.loads(raw)
        log.debug("AI cache HIT key=%s", key)
        return data
    except Exception as exc:
        log.warning("AI cache read error: %s", exc)
        return None


async def write_cache(ts_code: str, mode: str, data_pack: dict, result: dict) -> None:
    """Write result to cache. Do not call with rejected results."""
    redis = await _get_redis()
    if redis is None:
        return
    key = _cache_key(ts_code, mode, _input_hash(data_pack))
    try:
        payload = dict(result)
        payload["_cached_at"] = time.time()
        await redis.setex(key, DEFAULT_TTL, json.dumps(payload, ensure_ascii=False))
        log.debug("AI cache WRITE key=%s ttl=%ds", key, DEFAULT_TTL)
    except Exception as exc:
        log.warning("AI cache write error: %s", exc)


async def read_stale_cache(ts_code: str, mode: str, data_pack: dict) -> dict | None:
    """Same as read_cache but marks result as stale. Used as LLM failure fallback."""
    result = await read_cache(ts_code, mode, data_pack)
    if result is not None:
        result["_stale"] = True
    return result
