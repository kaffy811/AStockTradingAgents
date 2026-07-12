"""
app/services/free_fundamental_cache_service.py — Free Mode 基本面数据缓存服务（Phase 6N）

Cache-first 策略，降低对 BaoStock/AkShare/PDF 的频繁请求。

TTL 设计：
  - BaoStock 财务指标      7 天（季报数据低频更新）
  - BaoStock 全量聚合包    7 天（get_all_financial_indicators）
  - PDF 发现 URL           30 天（年报 URL 稳定）
  - 实时行情 (AkShare)      1 天（BaoStock fallback 价格）
  - 诊断快照               1 小时（diagnostics endpoint）

设计原则：
  - Redis 不可用时静默 fail-open：返回 None（调用方使用新鲜数据）
  - 所有 key 前缀 ta:{env}:free_fundamental:
  - key 结构：{prefix}:{ts_code}:{table}  e.g. ta:development:free_fundamental:600519.SH:profit
  - 不暴露 local_path、secrets 等敏感字段
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import settings

log = logging.getLogger(__name__)

# ── TTL 常量（秒）──────────────────────────────────────────────────────────────
TTL_FINANCIAL_TABLE     = 7 * 24 * 3600      # 7 天：BaoStock 单张财务表
TTL_FINANCIAL_AGGREGATE = 7 * 24 * 3600      # 7 天：BaoStock 全量聚合包
TTL_PDF_DISCOVERY       = 30 * 24 * 3600     # 30 天：PDF 年报发现 URL
TTL_QUOTE               = 1 * 24 * 3600      # 1 天：BaoStock kline fallback 价格
TTL_DIAGNOSTICS         = 1 * 3600           # 1 小时：diagnostics snapshot

_PREFIX = "free_fundamental"


def _key(ts_code: str, table: str) -> str:
    env = getattr(settings, "app_env", "development")
    return f"ta:{env}:{_PREFIX}:{ts_code}:{table}"


def _get_redis() -> Any | None:
    try:
        from app.core.database import get_redis
        return get_redis()
    except Exception:
        return None


class FreeFundamentalCacheService:
    """
    BaoStock / AkShare / PDF 数据的 Redis TTL 缓存。

    所有方法 fail-open：Redis 不可用时 get 返回 None，set 静默忽略。
    """

    # ── 通用 get/set ────────────────────────────────────────────────────────────

    async def _get(self, key: str) -> Any | None:
        redis = _get_redis()
        if redis is None:
            return None
        try:
            raw = await redis.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as exc:
            log.debug("FreeFundamentalCache get failed key=%s: %s", key, exc)
            return None

    async def _set(self, key: str, value: Any, ttl: int) -> None:
        redis = _get_redis()
        if redis is None:
            return
        try:
            await redis.setex(key, ttl, json.dumps(value, ensure_ascii=False))
        except Exception as exc:
            log.debug("FreeFundamentalCache set failed key=%s: %s", key, exc)

    async def _delete(self, key: str) -> None:
        redis = _get_redis()
        if redis is None:
            return
        try:
            await redis.delete(key)
        except Exception as exc:
            log.debug("FreeFundamentalCache delete failed key=%s: %s", key, exc)

    # ── BaoStock 单张财务表 ─────────────────────────────────────────────────────

    async def get_financial_table(self, ts_code: str, table: str) -> list[dict] | None:
        """
        获取 BaoStock 单张财务表缓存。

        Parameters
        ----------
        ts_code : str
            e.g. "600519.SH"
        table : str
            one of: profit / growth / balance / operation / cash_flow / dupont

        Returns
        -------
        list[dict] | None
            None 表示缓存未命中，调用方需从 BaoStock 拉取新鲜数据。
        """
        data = await self._get(_key(ts_code, f"table:{table}"))
        if data is not None and isinstance(data, list):
            return data
        return None

    async def set_financial_table(
        self, ts_code: str, table: str, rows: list[dict]
    ) -> None:
        """写入 BaoStock 单张财务表缓存（TTL 7 天）。"""
        await self._set(_key(ts_code, f"table:{table}"), rows, TTL_FINANCIAL_TABLE)

    # ── BaoStock 全量聚合包 ────────────────────────────────────────────────────

    async def get_all_financial(self, ts_code: str) -> dict[str, list[dict]] | None:
        """
        获取 BaoStock 全量聚合包（6 张表）缓存。

        Returns
        -------
        dict[str, list[dict]] | None
            None 表示缓存未命中。
        """
        data = await self._get(_key(ts_code, "all_financial"))
        if data is not None and isinstance(data, dict):
            return data
        return None

    async def set_all_financial(
        self, ts_code: str, tables: dict[str, list[dict]]
    ) -> None:
        """写入 BaoStock 全量聚合包缓存（TTL 7 天）。"""
        await self._set(_key(ts_code, "all_financial"), tables, TTL_FINANCIAL_AGGREGATE)

    # ── PDF 年报发现 ────────────────────────────────────────────────────────────

    async def get_pdf_discovery(self, ts_code: str, year: int) -> dict | None:
        """
        获取 PDF 年报发现结果缓存。

        Returns
        -------
        dict | None
            None 表示缓存未命中；dict 为 report_discovery_agent.discover_latest 的返回值。
        """
        data = await self._get(_key(ts_code, f"pdf_discovery:{year}"))
        if data is not None and isinstance(data, dict):
            return data
        return None

    async def set_pdf_discovery(self, ts_code: str, year: int, result: dict) -> None:
        """写入 PDF 年报发现结果缓存（TTL 30 天）。仅当 result 有 candidates 时写入。"""
        candidates = result.get("candidates") or []
        if not candidates:
            # 空结果不缓存，避免负缓存影响后续发现
            return
        await self._set(_key(ts_code, f"pdf_discovery:{year}"), result, TTL_PDF_DISCOVERY)

    async def invalidate_pdf_discovery(self, ts_code: str, year: int) -> None:
        """手动清除 PDF 发现缓存（年报重新发现时使用）。"""
        await self._delete(_key(ts_code, f"pdf_discovery:{year}"))

    # ── BaoStock 行情 fallback（最近收盘价）──────────────────────────────────

    async def get_quote(self, ts_code: str) -> dict | None:
        """
        获取 BaoStock kline fallback 行情缓存。

        Returns
        -------
        dict | None
            None 表示缓存未命中；dict 为 BaoStockClient.get_recent_close 的返回值。
        """
        data = await self._get(_key(ts_code, "quote"))
        if data is not None and isinstance(data, dict):
            return data
        return None

    async def set_quote(self, ts_code: str, quote: dict) -> None:
        """写入 BaoStock 行情 fallback 缓存（TTL 1 天）。"""
        await self._set(_key(ts_code, "quote"), quote, TTL_QUOTE)

    # ── Diagnostics 快照 ────────────────────────────────────────────────────────

    async def get_diagnostics(self, ts_code: str) -> dict | None:
        """
        获取诊断快照缓存（GET /stock/{code}/fundamentals/diagnostics 结果）。

        TTL 1 小时，避免每次页面刷新都并发探针 17 个模块。
        """
        data = await self._get(_key(ts_code, "diagnostics"))
        if data is not None and isinstance(data, dict):
            return data
        return None

    async def set_diagnostics(self, ts_code: str, result: dict) -> None:
        """写入诊断快照缓存（TTL 1 小时）。"""
        await self._set(_key(ts_code, "diagnostics"), result, TTL_DIAGNOSTICS)

    async def invalidate_diagnostics(self, ts_code: str) -> None:
        """手动清除诊断快照缓存（数据刷新后调用）。"""
        await self._delete(_key(ts_code, "diagnostics"))

    # ── 批量失效 ────────────────────────────────────────────────────────────────

    async def invalidate_all(self, ts_code: str) -> None:
        """清除指定股票所有 free_fundamental 缓存（强制刷新时使用）。"""
        redis = _get_redis()
        if redis is None:
            return
        try:
            env = getattr(settings, "app_env", "development")
            pattern = f"ta:{env}:{_PREFIX}:{ts_code}:*"
            keys = await redis.keys(pattern)
            if keys:
                await redis.delete(*keys)
                log.info("FreeFundamentalCache: invalidated %d keys for %s", len(keys), ts_code)
        except Exception as exc:
            log.debug("FreeFundamentalCache invalidate_all failed %s: %s", ts_code, exc)


# ── 模块级单例 ────────────────────────────────────────────────────────────────
free_fundamental_cache = FreeFundamentalCacheService()
