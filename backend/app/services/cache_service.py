"""
RedisCacheService — 统一 Redis 缓存封装（Phase R0）。

设计原则：
  - Redis 不可用时静默降级，不抛异常，业务零感知。
  - 提供 async 方法（供 async 上下文直接使用）。
  - 提供 sync_* 方法（供被 to_thread / ThreadPoolExecutor 执行的同步服务使用）。
  - sync_* 方法依赖启动时通过 set_event_loop() 注入的 event loop 引用。
  - JSON 序列化支持 datetime / date / Decimal / UUID。
  - 所有 key 自动加 ta:{env}: 前缀。

使用方式：
  # async 上下文（路由、lifespan）
  from app.services.cache_service import cache_service
  await cache_service.set_json("foo", data, ttl=300)
  val = await cache_service.get_json("foo")

  # 同步上下文（被 to_thread 调用的 Service 方法）
  val = cache_service.sync_get_json("foo")
  cache_service.sync_set_json("foo", data, ttl=300)

启动 Redis（本地开发）：
  brew services start redis
  或 docker run -d --name tradingagents-redis -p 6379:6379 redis:7-alpine
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.core.config import settings
from app.core.database import get_redis

log = logging.getLogger(__name__)

# 运行中的 event loop 引用，由 main.py lifespan 注入
_loop: asyncio.AbstractEventLoop | None = None


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """在 lifespan 启动时调用，保存 event loop 供 sync_* 方法使用。"""
    global _loop
    _loop = loop


# ── JSON 序列化 ───────────────────────────────────────────────────────────────

class _Encoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, datetime):
            return {"__type__": "datetime", "v": obj.isoformat()}
        if isinstance(obj, date):
            return {"__type__": "date", "v": obj.isoformat()}
        if isinstance(obj, Decimal):
            return {"__type__": "decimal", "v": str(obj)}
        if isinstance(obj, UUID):
            return {"__type__": "uuid", "v": str(obj)}
        return super().default(obj)


def _object_hook(obj: dict) -> Any:
    t = obj.get("__type__")
    if t == "datetime":
        return datetime.fromisoformat(obj["v"])
    if t == "date":
        return date.fromisoformat(obj["v"])
    if t == "decimal":
        return Decimal(obj["v"])
    if t == "uuid":
        return UUID(obj["v"])
    return obj


def _dumps(value: Any) -> str:
    return json.dumps(value, cls=_Encoder, ensure_ascii=False)


def _loads(raw: str) -> Any:
    return json.loads(raw, object_hook=_object_hook)


# ── Key 构造 ──────────────────────────────────────────────────────────────────

def _full_key(key: str) -> str:
    env = getattr(settings, "app_env", "dev")
    return f"ta:{env}:{key}"


# ── 主服务类 ──────────────────────────────────────────────────────────────────

class RedisCacheService:
    """
    统一 Redis 缓存封装。

    Redis 为 None（未启动）或操作异常时，所有方法优雅降级：
      get_json      → None
      set_json      → False
      delete        → False
      exists        → False
      get_or_set_json → 直接调用 loader

    sync_* 方法通过 run_coroutine_threadsafe 桥接 async Redis，
    专为从线程池（to_thread / ThreadPoolExecutor）中调用设计。
    """

    # ── Async 方法 ────────────────────────────────────────────────────────────

    async def get_json(self, key: str) -> Any | None:
        """从 Redis 获取并反序列化 JSON 值。未命中或 Redis 不可用返回 None。"""
        redis = get_redis()
        if redis is None:
            return None
        fk = _full_key(key)
        try:
            raw = await redis.get(fk)
            if raw is None:
                return None
            return _loads(raw)
        except Exception as exc:
            log.warning("cache get_json error [%s]: %s", key, exc)
            return None

    async def set_json(self, key: str, value: Any, ttl: int) -> bool:
        """序列化后写入 Redis，ttl 单位秒。Redis 不可用返回 False。"""
        redis = get_redis()
        if redis is None:
            return False
        fk = _full_key(key)
        try:
            await redis.setex(fk, ttl, _dumps(value))
            log.debug("cache set_json OK [%s] ttl=%ds", key, ttl)
            return True
        except Exception as exc:
            log.warning("cache set_json error [%s]: %s", key, exc)
            return False

    async def delete(self, key: str) -> bool:
        """删除 Redis key。Redis 不可用返回 False。"""
        redis = get_redis()
        if redis is None:
            return False
        try:
            await redis.delete(_full_key(key))
            return True
        except Exception as exc:
            log.warning("cache delete error [%s]: %s", key, exc)
            return False

    async def exists(self, key: str) -> bool:
        """检查 key 是否存在。Redis 不可用返回 False。"""
        redis = get_redis()
        if redis is None:
            return False
        try:
            return bool(await redis.exists(_full_key(key)))
        except Exception as exc:
            log.warning("cache exists error [%s]: %s", key, exc)
            return False

    async def get_or_set_json(
        self, key: str, ttl: int, loader: Callable[[], Any]
    ) -> Any:
        """
        先查 Redis；未命中则调用 loader，写入 Redis 后返回。
        loader 可以是普通函数或协程函数。
        """
        cached = await self.get_json(key)
        if cached is not None:
            return cached
        value = await loader() if asyncio.iscoroutinefunction(loader) else loader()
        if value is not None:
            await self.set_json(key, value, ttl)
        return value

    # ── Sync-safe 桥接方法（供线程池中的同步代码使用）──────────────────────────

    @staticmethod
    def _loop_ready() -> bool:
        """检查 _loop 是否可用：非 None、未关闭、正在运行。"""
        return _loop is not None and not _loop.is_closed() and _loop.is_running()

    def sync_get_json(self, key: str, timeout: float = 1.5) -> Any | None:
        """
        同步获取 Redis JSON，适合从 to_thread / ThreadPoolExecutor 调用。
        _loop 未注入、已关闭或未运行时静默返回 None。
        """
        if not self._loop_ready():
            return None
        try:
            future = asyncio.run_coroutine_threadsafe(self.get_json(key), _loop)
            return future.result(timeout=timeout)
        except Exception as exc:
            log.warning("cache sync_get_json error [%s]: %s", key, exc)
            return None

    def sync_set_json(self, key: str, value: Any, ttl: int, timeout: float = 1.5) -> bool:
        """
        同步写入 Redis JSON，适合从 to_thread / ThreadPoolExecutor 调用。
        _loop 未注入、已关闭或未运行时静默返回 False。
        """
        if not self._loop_ready():
            return False
        try:
            future = asyncio.run_coroutine_threadsafe(
                self.set_json(key, value, ttl), _loop
            )
            return future.result(timeout=timeout)
        except Exception as exc:
            log.warning("cache sync_set_json error [%s]: %s", key, exc)
            return False

    def sync_exists(self, key: str, timeout: float = 0.8) -> bool:
        """
        同步检查 key 是否存在，适合从 to_thread / ThreadPoolExecutor 调用。
        _loop 未注入、已关闭或未运行时静默返回 False。
        """
        if not self._loop_ready():
            return False
        try:
            future = asyncio.run_coroutine_threadsafe(self.exists(key), _loop)
            return future.result(timeout=timeout)
        except Exception as exc:
            log.warning("cache sync_exists error [%s]: %s", key, exc)
            return False


# ── 模块级单例 ────────────────────────────────────────────────────────────────

cache_service = RedisCacheService()
