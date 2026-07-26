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

import time as _time

from app.core.config import settings
from app.core.database import get_redis

log = logging.getLogger(__name__)

# 运行中的 event loop 引用，由 main.py lifespan 注入
_loop: asyncio.AbstractEventLoop | None = None


def set_event_loop(loop: asyncio.AbstractEventLoop) -> None:
    """在 lifespan 启动时调用，保存 event loop 供 sync_* 方法使用。"""
    global _loop
    _loop = loop


# ── Circuit Breaker（Phase 6N-8B）────────────────────────────────────────────
# 连续 N 次 timeout/error 后打开断路器，跳过 Redis 30-60 秒，避免阻塞业务。

_CB_FAIL_THRESHOLD = 5        # 连续失败 N 次才开路
_CB_OPEN_SECONDS   = 45       # 开路持续时间（秒）
_WARN_DEDUP_SECONDS = 60      # 同 key prefix 60 秒内最多 warning 一次

_cb_fail_count:  int   = 0
_cb_open_until:  float = 0.0  # monotonic time; 0 = closed

# 降噪：记录每个 key prefix 上次 warning 的时间
_warn_last: dict[str, float] = {}


def _key_prefix(key: str) -> str:
    """取 key 的第一段前缀用于降噪（e.g. 'quote:CN:601686' → 'quote'）。"""
    return key.split(":")[0] if key else key


def _cb_is_open() -> bool:
    return _time.monotonic() < _cb_open_until


def _cb_record_failure() -> None:
    global _cb_fail_count, _cb_open_until
    _cb_fail_count += 1
    if _cb_fail_count >= _CB_FAIL_THRESHOLD and not _cb_is_open():
        _cb_open_until = _time.monotonic() + _CB_OPEN_SECONDS
        log.warning(
            "cache circuit breaker OPENED after %d failures; skipping Redis for %ds",
            _cb_fail_count, _CB_OPEN_SECONDS,
        )


def _cb_record_success() -> None:
    global _cb_fail_count
    if _cb_fail_count > 0:
        _cb_fail_count = 0


def _should_warn(key: str) -> bool:
    """同一 key prefix 60 秒内最多 warning 一次。"""
    prefix = _key_prefix(key)
    now = _time.monotonic()
    last = _warn_last.get(prefix, 0.0)
    if now - last >= _WARN_DEDUP_SECONDS:
        _warn_last[prefix] = now
        return True
    return False


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

    async def delete_pattern(self, pattern: str) -> int:
        """删除匹配 pattern 的 Redis keys，pattern 会自动加统一前缀。"""
        redis = get_redis()
        if redis is None:
            return 0
        try:
            keys = await redis.keys(_full_key(pattern))
            if not keys:
                return 0
            return int(await redis.delete(*keys))
        except Exception as exc:
            log.warning("cache delete_pattern error [%s]: %s", pattern, exc)
            return 0

    async def set_lock(self, key: str, token: str, ttl: int) -> bool:
        """轻量分布式锁：SET key token NX EX ttl。Redis 不可用返回 False。"""
        redis = get_redis()
        if redis is None:
            return False
        try:
            return bool(await redis.set(_full_key(key), token, nx=True, ex=ttl))
        except Exception as exc:
            log.warning("cache set_lock error [%s]: %s", key, exc)
            return False

    async def release_lock(self, key: str, token: str) -> bool:
        """仅当 token 匹配时释放锁，避免误删其他请求持有的锁。"""
        redis = get_redis()
        if redis is None:
            return False
        fk = _full_key(key)
        try:
            current = await redis.get(fk)
            if isinstance(current, bytes):
                current = current.decode("utf-8", errors="ignore")
            if current != token:
                return False
            await redis.delete(fk)
            return True
        except Exception as exc:
            log.warning("cache release_lock error [%s]: %s", key, exc)
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
        _loop 未注入、已关闭、未运行，或 circuit breaker 开路时静默返回 None。

        Phase 6N-8B：
          - 开路时跳过 Redis，fail-open（返回 None，由调用方走 provider）
          - 同一 key prefix 60s 内最多 warning 一次（降噪）
          - 连续失败 _CB_FAIL_THRESHOLD 次后打开断路器
        """
        if _cb_is_open():
            return None  # circuit open — skip Redis silently
        if not self._loop_ready():
            return None
        try:
            future = asyncio.run_coroutine_threadsafe(self.get_json(key), _loop)
            result = future.result(timeout=timeout)
            _cb_record_success()
            return result
        except Exception as exc:
            _cb_record_failure()
            if _should_warn(key):
                log.warning(
                    "cache sync_get_json error [%s] %s: %s",
                    key, type(exc).__name__, repr(exc),
                )
            return None

    def sync_set_json(self, key: str, value: Any, ttl: int, timeout: float = 1.5) -> bool:
        """
        同步写入 Redis JSON，适合从 to_thread / ThreadPoolExecutor 调用。
        _loop 未注入、已关闭、未运行，或 circuit breaker 开路时静默返回 False。

        Phase 6N-8B：set 失败不影响主响应（fail-open）。
        """
        if _cb_is_open():
            return False  # circuit open — skip Redis write silently
        if not self._loop_ready():
            return False
        try:
            future = asyncio.run_coroutine_threadsafe(
                self.set_json(key, value, ttl), _loop
            )
            result = future.result(timeout=timeout)
            _cb_record_success()
            return result
        except Exception as exc:
            _cb_record_failure()
            if _should_warn(key):
                log.warning(
                    "cache sync_set_json error [%s] %s: %s",
                    key, type(exc).__name__, repr(exc),
                )
            return False

    def sync_exists(self, key: str, timeout: float = 0.8) -> bool:
        """
        同步检查 key 是否存在，适合从 to_thread / ThreadPoolExecutor 调用。
        _loop 未注入、已关闭、未运行或 circuit breaker 开路时静默返回 False。
        """
        if _cb_is_open():
            return False
        if not self._loop_ready():
            return False
        try:
            future = asyncio.run_coroutine_threadsafe(self.exists(key), _loop)
            result = future.result(timeout=timeout)
            _cb_record_success()
            return result
        except Exception as exc:
            _cb_record_failure()
            if _should_warn(key):
                log.warning(
                    "cache sync_exists error [%s] %s: %s",
                    key, type(exc).__name__, repr(exc),
                )
            return False


# ── 模块级单例 ────────────────────────────────────────────────────────────────

cache_service = RedisCacheService()


def cache_status() -> str:
    """
    Phase 6N-8B: 返回当前 Redis 缓存状态字符串。
      'unavailable' — circuit breaker 开路，Redis 被跳过
      'ok'          — Redis 正常或未使用
    """
    return "unavailable" if _cb_is_open() else "ok"
