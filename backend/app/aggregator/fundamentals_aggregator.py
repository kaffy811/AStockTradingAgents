"""
app/aggregator/fundamentals_aggregator.py — 基本面数据聚合器

FundamentalsAggregator 负责：
1. 读 Redis 缓存（stale-while-revalidate 策略）
2. cache miss → 调用工具层 fetch_with_fallback()
3. 写 Redis 缓存（按模块 TTL）
4. 并发聚合多个模块（asyncio.gather + return_exceptions）
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from app.aggregator.envelope import DataEnvelope, ok_envelope, err_envelope, from_cache, _now_cst
from app.tools.fundamental import TOOL_REGISTRY, MODULE_CATALOG
from app.tools.fundamental.base import BaseFundamentalTool

log = logging.getLogger(__name__)

# 首屏快照拉取的模块列表（最常用的 3 个，并发加速）
_SNAPSHOT_MODULES = ["quote_snapshot", "financial_summary"]


def _cache_key(market: str, symbol: str, module_key: str, version: str = "v1") -> str:
    return f"fs:{market.upper()}:{symbol}:{module_key}:{version}"


class FundamentalsAggregator:
    """
    基本面数据聚合器（单例，通过 get_aggregator() 获取）。

    公共 API：
        fetch_snapshot(market, symbol) → dict[str, DataEnvelope]
        fetch_module(market, symbol, module_key) → DataEnvelope
        list_modules() → list[dict]
    """

    def __init__(self) -> None:
        self._cache_version: str = "v1"

    # ── 模块列表 ──────────────────────────────────────────────────────────────

    def list_modules(self) -> list[dict]:
        """
        返回所有正式展示模块的 metadata（含 available 字段）。

        过滤规则：
          display=True  AND  status != "hidden"

        别名（display=False / status="hidden"）不在此列表中，
        但仍可通过 /api/v1/stock/{code}/modules/{alias_key} 路由访问。
        """
        return [
            {
                **m,
                # available = 工具已注册（status=available/legacy 均已实现）
                "available": m["key"] in TOOL_REGISTRY or m.get("status") in ("available", "legacy"),
            }
            for m in MODULE_CATALOG
            if m.get("display", True) and m.get("status") != "hidden"
        ]

    # ── 单模块拉取 ────────────────────────────────────────────────────────────

    async def fetch_module(
        self,
        market: str,
        symbol: str,
        module_key: str,
    ) -> DataEnvelope:
        """
        拉取单个模块数据，带缓存读写。

        流程：
          1. 读 Redis → cache HIT（未 stale）→ 直接返回
          2. cache HIT（stale）→ 启动后台刷新，立即返回旧数据（stale=True）
          3. cache MISS → fetch_with_fallback → 写缓存 → 返回
        """
        tool_cls = TOOL_REGISTRY.get(module_key)
        if tool_cls is None:
            return err_envelope(
                f"模块 '{module_key}' 在 Phase 1 中未实现（计划在后续 Phase 中支持）"
            )

        tool: BaseFundamentalTool = tool_cls()
        cache_key = _cache_key(market, symbol, module_key, self._cache_version)

        # 尝试读缓存
        cached = await self._read_cache(cache_key)
        if cached is not None:
            return cached

        # cache MISS → 直接 fetch
        envelope = await self._do_fetch(tool, market, symbol)
        if envelope["ok"]:
            await self._write_cache(cache_key, envelope, tool.cache_ttl_seconds)
        return envelope

    async def _do_fetch(
        self,
        tool: BaseFundamentalTool,
        market: str,
        symbol: str,
    ) -> DataEnvelope:
        """调用工具层 fetch_with_fallback，提取 _partial_errors 到 envelope。"""
        try:
            envelope = await tool.fetch_with_fallback(market, symbol)
        except Exception as exc:
            log.error(
                "fetch_with_fallback 意外异常 [%s/%s/%s]: %s",
                tool.module_key, market, symbol, exc, exc_info=True,
            )
            return err_envelope(f"聚合器内部错误: {exc}")

        # 提取 _partial_errors（由工具 fetch() 附加到 data dict）
        if envelope["ok"] and isinstance(envelope["data"], dict):
            raw_errors = envelope["data"].pop("_partial_errors", [])
            if raw_errors:
                envelope["partial_errors"] = list(raw_errors)

        return envelope

    # ── 快照聚合 ──────────────────────────────────────────────────────────────

    async def fetch_snapshot(
        self,
        market: str,
        symbol: str,
    ) -> dict[str, DataEnvelope]:
        """
        并发拉取首屏快照模块（quote_snapshot + financial_summary）。
        返回 {module_key: DataEnvelope} 的 dict。
        """
        tasks = [
            self.fetch_module(market, symbol, key)
            for key in _SNAPSHOT_MODULES
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        snapshot: dict[str, DataEnvelope] = {}
        for key, result in zip(_SNAPSHOT_MODULES, results):
            if isinstance(result, Exception):
                log.error("snapshot 模块 %s 异常: %s", key, result)
                snapshot[key] = err_envelope(str(result))
            else:
                snapshot[key] = result  # type: ignore[assignment]

        return snapshot

    # ── Redis 缓存 ────────────────────────────────────────────────────────────

    async def _read_cache(self, key: str) -> DataEnvelope | None:
        """
        尝试从 Redis 读取缓存。
        返回 None 表示 cache MISS。
        返回 DataEnvelope（stale=True 表示已过期但仍可用）。
        """
        try:
            from app.core.database import get_redis
            redis = get_redis()
            if redis is None:
                return None
            raw = await redis.get(key)
            if raw is None:
                return None
            data = json.loads(raw)
            envelope = from_cache(data)
            log.debug("cache HIT key=%s stale=%s", key, envelope["stale"])
            return envelope
        except Exception as exc:
            log.warning("Redis 读取失败 key=%s: %s", key, exc)
            return None

    async def _write_cache(
        self,
        key: str,
        envelope: DataEnvelope,
        ttl_seconds: int,
    ) -> None:
        """将 DataEnvelope 写入 Redis，TTL = ttl_seconds。"""
        try:
            from app.core.database import get_redis
            redis = get_redis()
            if redis is None:
                return
            # 写入时记录 cached_at
            envelope_to_store = dict(envelope)
            envelope_to_store["cached_at"] = _now_cst()
            await redis.setex(key, ttl_seconds, json.dumps(envelope_to_store, ensure_ascii=False))
            log.debug("cache WRITE key=%s ttl=%ds", key, ttl_seconds)
        except Exception as exc:
            log.warning("Redis 写入失败 key=%s: %s", key, exc)


# ── 模块级单例 ────────────────────────────────────────────────────────────────

_aggregator: FundamentalsAggregator | None = None


def get_aggregator() -> FundamentalsAggregator:
    """获取聚合器单例（懒初始化）。"""
    global _aggregator
    if _aggregator is None:
        from app.core.config import settings
        agg = FundamentalsAggregator()
        agg._cache_version = settings.fs_cache_version
        _aggregator = agg
    return _aggregator
