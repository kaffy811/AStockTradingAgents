"""
NewsDataService — 个股新闻数据服务（Phase 1 + Redis Phase R3）。

调用链路：
  get_stock_news(market, symbol, hours_back, limit)
    ├─ L1: Redis 缓存检查（key = news:{market}:{symbol}:{hours_back}:{limit}）
    │       命中 → deepcopy，cached=True，return
    ├─ L2: 内存 TTL cache（同 key）
    │       命中 → 回写 Redis，cached=True，return
    ├─ EastmoneyNewsProvider.get_stock_news() 实时拉取
    ├─ 按 publish_time 过滤 hours_back 窗口
    ├─ 按 limit 截断
    ├─ 写内存缓存 + stale 缓存 + Redis（TTL 600s）
    └─ 返回标准化 dict

缓存策略（Phase R3 更新）：
  - Redis L1 TTL = 600s（与内存 TTL 一致）
  - provider 成功 → 写内存 + 写 Redis(600s)，cached=False
  - provider 失败 + 有 stale 缓存 → 返回旧数据，写 Redis(300s)，cached=True，message 说明
  - provider 失败 + 无缓存 → items=[], count=0，不写 Redis，message 说明失败原因
  - Redis 不可用时完全降级到原有内存逻辑，业务零感知

HK 约束：
  news 通过 stock_news_em 关键词搜索获取（00700 格式），结果可能包含弱相关内容。
  data_quality.message 中说明，Redis 缓存时该 message 会一并缓存并正常返回。

序列化说明（R3 分析）：
  - publish_time 由 news_provider._parse_publish_time() 已转为 ISO 8601 字符串
  - url / source / summary 为 str | None
  - symbols 为 list[str]
  - 所有字段均为原生 Python 类型，直接 JSON 序列化，无需额外处理

禁止：
  - 不写 NewsAnalystAgent
  - 不入库
  - 不使用 Tushare / Alpha Vantage / yfinance
  - 不编造新闻
"""

from __future__ import annotations

import copy
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Any

from app.data.providers.news_provider import EastmoneyNewsProvider
from app.services.cache_service import cache_service

log = logging.getLogger(__name__)

# ── 缓存常量 ──────────────────────────────────────────────────────────────────

_NEWS_TTL:       int = 600   # 秒（10 分钟）— 正常结果 Redis + 内存 TTL
_NEWS_STALE_TTL: int = 300   # 秒（5 分钟）— stale 降级结果写 Redis 的较短 TTL

# 主缓存：key → (payload, expire_at_monotonic)
_cache:       dict[str, tuple[Any, float]] = {}
# Stale 缓存：key → payload，永不自动过期
_stale_cache: dict[str, Any] = {}

# ── HK message ────────────────────────────────────────────────────────────────

_HK_NEWS_MESSAGE = (
    "HK news is fetched via akshare stock_news_em keyword search; "
    "results may include non-HK or loosely related content."
)


# ── 缓存 helpers ──────────────────────────────────────────────────────────────

def _cache_key(market: str, symbol: str, hours_back: int, limit: int) -> str:
    return f"news:{market}:{symbol}:{hours_back}:{limit}"


def _cache_get(key: str) -> tuple[Any, bool]:
    """读取主缓存。返回 (value, hit)。过期或不存在返回 (None, False)。"""
    entry = _cache.get(key)
    if entry is None:
        return None, False
    value, expire_at = entry
    if time.monotonic() > expire_at:
        return None, False
    return value, True


def _cache_set(key: str, value: Any) -> None:
    """写入主缓存和 stale 缓存。"""
    _cache[key] = (value, time.monotonic() + _NEWS_TTL)
    _stale_cache[key] = value


def _stale_get(key: str) -> tuple[Any, bool]:
    """读取 stale 缓存（无视 TTL）。返回 (value, found)。"""
    value = _stale_cache.get(key)
    return (value, value is not None)


# ── 时间过滤 ──────────────────────────────────────────────────────────────────

_TZ_BJT = timezone(timedelta(hours=8))   # 北京时间 UTC+8，模块级常量


def _within_hours(publish_time: str | None, hours_back: int) -> bool:
    """
    判断 publish_time（ISO 8601 字符串）是否在 hours_back 窗口内。
    无法解析时返回 True（保留该新闻，不因解析失败而丢弃）。
    AkShare 返回的发布时间为北京时间（无时区信息），加 UTC+8 偏移后与 UTC now 比较。
    """
    if publish_time is None:
        return True
    try:
        dt = datetime.fromisoformat(publish_time)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_TZ_BJT)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        return dt >= cutoff
    except (ValueError, TypeError):
        return True


# ── 主服务 ────────────────────────────────────────────────────────────────────

class NewsDataService:
    """
    个股新闻数据服务（Phase 1 + Redis Phase R3）。

    单例使用：
        from app.services.news_data_service import news_data_service
        result = news_data_service.get_stock_news("CN", "600519", hours_back=72, limit=20)
    """

    def __init__(self) -> None:
        self._provider = EastmoneyNewsProvider()

    def get_stock_news(
        self,
        market:     str,
        symbol:     str,
        hours_back: int = 72,
        limit:      int = 20,
    ) -> dict:
        """
        获取个股新闻列表（含 Redis L1 + 内存 L2 缓存、stale 降级逻辑）。

        Args:
            market:     "CN" 或 "HK"（已大写）
            symbol:     股票代码（已 strip）
            hours_back: 只返回最近 N 小时内的新闻（时间过滤）
            limit:      最多返回条数

        Returns:
            {
                "market":  str,
                "symbol":  str,
                "items":   list[dict],   # NewsItem list
                "count":   int,
                "data_quality": {
                    "provider": str | None,
                    "cached":   bool,
                    "message":  str | None,
                }
            }
        """
        key = _cache_key(market, symbol, hours_back, limit)

        # ── L1: Redis 缓存 ─────────────────────────────────────────────────
        redis_payload = cache_service.sync_get_json(key)
        if redis_payload is not None:
            log.info("news Redis HIT [%s/%s]", market, symbol)
            result = copy.deepcopy(redis_payload)
            result["data_quality"]["cached"] = True
            return result

        # ── L2: 内存 TTL 缓存 ─────────────────────────────────────────────
        cached_payload, hit = _cache_get(key)
        if hit:
            log.debug("NewsDataService: memory cache hit [%s/%s]", market, symbol)
            # 回写 Redis（跨进程/重启后恢复）
            cache_service.sync_set_json(key, cached_payload, _NEWS_TTL)
            result = copy.deepcopy(cached_payload)
            result["data_quality"]["cached"] = True
            return result

        # ── L3: 实时拉取 ──────────────────────────────────────────────────
        hk_message = _HK_NEWS_MESSAGE if market == "HK" else None

        try:
            raw_items = self._provider.get_stock_news(market, symbol, limit=limit)
        except Exception as exc:
            log.error(
                "NewsDataService: provider failed [%s/%s]: %s",
                market, symbol, exc,
            )
            # provider 失败，尝试返回 stale 缓存
            stale_payload, found = _stale_get(key)
            if found:
                log.info(
                    "NewsDataService: returning stale cache [%s/%s]", market, symbol
                )
                result = copy.deepcopy(stale_payload)
                dq = result["data_quality"]
                dq["cached"] = True
                stale_msg = f"Live provider unavailable ({exc}); showing cached data."
                if dq.get("message"):
                    dq["message"] = f"{dq['message']} {stale_msg}"
                else:
                    dq["message"] = stale_msg
                # 写 Redis 短 TTL（降级数据，让下次尽快重试上游）
                cache_service.sync_set_json(key, result, _NEWS_STALE_TTL)
                return result

            # 无 stale 缓存，降级返回空列表（不写 Redis）
            fail_message = f"News provider unavailable: {exc}"
            if hk_message:
                fail_message = f"{hk_message} {fail_message}"
            return {
                "market":  market,
                "symbol":  symbol,
                "items":   [],
                "count":   0,
                "data_quality": {
                    "provider": "akshare_stock_news_em",
                    "cached":   False,
                    "message":  fail_message,
                },
            }

        # ── Step 3: hours_back 时间过滤 ───────────────────────────────────
        filtered = [
            item for item in raw_items
            if _within_hours(item.get("publish_time"), hours_back)
        ]

        # ── Step 4: limit 截断 ────────────────────────────────────────────
        final_items = filtered[:limit]

        log.info(
            "NewsDataService: [%s/%s] raw=%d filtered=%d final=%d",
            market, symbol, len(raw_items), len(filtered), len(final_items),
        )

        # ── Step 5: 组装结果 ──────────────────────────────────────────────
        result: dict = {
            "market":  market,
            "symbol":  symbol,
            "items":   final_items,
            "count":   len(final_items),
            "data_quality": {
                "provider": "akshare_stock_news_em",
                "cached":   False,
                "message":  hk_message,
            },
        }

        # ── Step 6: 写内存缓存 + stale + Redis ────────────────────────────
        _cache_set(key, result)
        cache_service.sync_set_json(key, result, _NEWS_TTL)
        log.info("news written to memory+Redis [%s/%s]", market, symbol)

        return result


# ── 模块级单例 ────────────────────────────────────────────────────────────────

news_data_service = NewsDataService()
