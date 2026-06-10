"""
StockCacheService — 股票数据缓存（Redis L1 + 内存 L2）。

缓存 key 规则：
  quote:{market}:{symbol}
  kline:{market}:{symbol}:{period}:{adjust}:{limit}

TTL：
  quote  → 60 秒
  kline  → 600 秒（10 分钟）

缓存分层（Phase R2）：
  L1 Redis（跨进程/实例共享，TTL 到期自动清除）
    → 命中：直接返回，不走内存缓存
    → 未命中：继续 L2
  L2 内存 dict（进程级，TTL 到期 _get 返回 miss）
    → 命中：回写 Redis 后返回
    → 未命中：调用方继续走上游数据源
  set 时：同时写内存 + Redis
  Redis 不可用：sync_* 静默返回 None/False，完全降级到原有逻辑

Stale fallback（不接入 Redis，仅进程内）：
  _stale_store 永久保存最近一次成功数据，不受 TTL 限制。
  当所有实时数据源失败时，可从 _stale_store 取回旧数据（stale=true）。

数据类型注意事项（Phase R2 分析）：
  - quote payload {"data": dict, "provider": str, "fallback_chain": list}
    所有字段均为纯 Python 原生类型，可直接 JSON 序列化。
  - kline payload {"bars": list[dict], "provider": str, "fallback_chain": list}
    bar dict 中 "date" 由各 Provider 统一转为 str（Eastmoney/Tencent 字符串，
    AkShare _df_to_records() 已将 pd.Timestamp 转为 "%Y-%m-%d" 字符串），
    其余字段为 float/int/None，可直接 JSON 序列化。
  - 无需 DataFrame 序列化/反序列化，从 Redis 读取后结构与原始一致。
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.services.cache_service import cache_service

log = logging.getLogger(__name__)

# ── TTL 常量 ──────────────────────────────────────────────────────────────────

_QUOTE_TTL: int = 60       # 秒
_KLINE_TTL: int = 600      # 秒（10 分钟）

# ── 存储 ──────────────────────────────────────────────────────────────────────

# 主缓存：key → (value, expire_at_monotonic)，过期后 _get 返回 miss
_store: dict[str, tuple[Any, float]] = {}

# Stale 缓存：key → value，永不自动过期，仅在有新数据写入时更新
# 用于所有实时数据源失败时的最后兜底（不接入 Redis，仅进程内）
_stale_store: dict[str, Any] = {}


# ── 内部 helpers ──────────────────────────────────────────────────────────────

def _get(key: str) -> tuple[Any, bool]:
    """
    读取主缓存。
    返回 (value, True) 命中；(None, False) 未命中或已过期。
    过期条目不删除，保留在 _store 中以备 stale 读取（_stale_store 也有备份）。
    """
    entry = _store.get(key)
    if entry is None:
        return None, False
    value, expire_at = entry
    if time.monotonic() > expire_at:
        return None, False
    return value, True


def _set(key: str, value: Any, ttl: int) -> None:
    """写入主缓存，同时更新 stale 缓存。"""
    _store[key] = (value, time.monotonic() + ttl)
    _stale_store[key] = value


def _get_stale(key: str) -> tuple[Any, bool]:
    """
    读取 stale 缓存（无视 TTL）。
    只要历史上曾成功写入过，就能返回，不管是否过期。
    返回 (value, found)。
    """
    value = _stale_store.get(key)
    return (value, value is not None)


# ── Quote 缓存 ────────────────────────────────────────────────────────────────

def get_quote_cache(market: str, symbol: str) -> tuple[Any, bool]:
    """
    读取有效 quote 缓存（TTL 内）。
    优先级：Redis L1 → 内存 L2。
    返回 (cached_payload, hit)。
    cached_payload 结构：{"data": dict, "provider": str, "fallback_chain": list}
    """
    m   = market.upper()
    key = f"quote:{m}:{symbol}"

    # L1: Redis
    redis_val = cache_service.sync_get_json(key)
    if redis_val is not None:
        log.info("quote Redis HIT [%s/%s]", m, symbol)
        return redis_val, True

    # L2: 内存
    mem_val, hit = _get(key)
    if hit:
        # 回写 Redis（跨进程共享）
        cache_service.sync_set_json(key, mem_val, _QUOTE_TTL)
        return mem_val, True

    return None, False


def get_quote_stale(market: str, symbol: str) -> tuple[Any, bool]:
    """
    读取 stale quote 缓存（忽略 TTL，历史数据兜底）。
    所有实时源失败时使用，返回最近一次成功数据。
    返回 (cached_payload, found)。found=False 表示从未缓存过。
    """
    key = f"quote:{market.upper()}:{symbol}"
    return _get_stale(key)


def set_quote_cache(
    market: str,
    symbol: str,
    data: dict,
    provider: str,
    fallback_chain: list[dict],
) -> None:
    """写入 quote 缓存：同时写内存 + Redis。"""
    m       = market.upper()
    key     = f"quote:{m}:{symbol}"
    payload = {"data": data, "provider": provider, "fallback_chain": fallback_chain}
    _set(key, payload, _QUOTE_TTL)
    cache_service.sync_set_json(key, payload, _QUOTE_TTL)


# ── Kline 缓存 ────────────────────────────────────────────────────────────────

def get_kline_cache(
    market: str,
    symbol: str,
    period: str,
    adjust: str,
    limit: int,
) -> tuple[Any, bool]:
    """
    读取有效 kline 缓存（TTL 内）。
    优先级：Redis L1 → 内存 L2。
    返回 (cached_payload, hit)。
    cached_payload 结构：{"bars": list[dict], "provider": str, "fallback_chain": list}
    """
    m   = market.upper()
    key = f"kline:{m}:{symbol}:{period}:{adjust}:{limit}"

    # L1: Redis
    redis_val = cache_service.sync_get_json(key)
    if redis_val is not None:
        log.info("kline Redis HIT [%s/%s %s %s limit=%d]", m, symbol, period, adjust, limit)
        return redis_val, True

    # L2: 内存
    mem_val, hit = _get(key)
    if hit:
        cache_service.sync_set_json(key, mem_val, _KLINE_TTL)
        return mem_val, True

    return None, False


def set_kline_cache(
    market: str,
    symbol: str,
    period: str,
    adjust: str,
    limit: int,
    bars: list[dict],
    provider: str,
    fallback_chain: list[dict],
) -> None:
    """写入 kline 缓存：同时写内存 + Redis。"""
    m       = market.upper()
    key     = f"kline:{m}:{symbol}:{period}:{adjust}:{limit}"
    payload = {"bars": bars, "provider": provider, "fallback_chain": fallback_chain}
    _set(key, payload, _KLINE_TTL)
    cache_service.sync_set_json(key, payload, _KLINE_TTL)


def get_kline_stale(
    market: str,
    symbol: str,
    period: str,
    adjust: str,
    limit: int,
) -> tuple[Any, bool]:
    """
    读取 stale kline 缓存（忽略 TTL，历史数据兜底）。
    所有实时 kline 源失败时使用，返回最近一次成功数据。
    返回 (cached_payload, found)。found=False 表示从未缓存过。
    注意：_set() 写入时已同步更新 _stale_store，无需额外操作。
    """
    key = f"kline:{market.upper()}:{symbol}:{period}:{adjust}:{limit}"
    return _get_stale(key)


# ── 调试工具 ──────────────────────────────────────────────────────────────────

def cache_stats() -> dict:
    """返回缓存统计。仅用于调试。"""
    now = time.monotonic()
    active = sum(1 for _, (_, exp) in _store.items() if exp > now)
    return {
        "total_keys": len(_store),
        "active_keys": active,
        "stale_keys": len(_stale_store),
    }


def clear_all() -> None:
    """清空所有内存缓存（包括 stale）。用于测试。注意：不清除 Redis。"""
    _store.clear()
    _stale_store.clear()
