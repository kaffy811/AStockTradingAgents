"""
Run Registry Factory — 延迟初始化工厂（M40-b）。

提供 get_run_registry() → AnalysisRunRegistry 单例。

行为：
  - 默认（ANALYSIS_RUN_REGISTRY=memory）：MemoryAnalysisRunRegistry（进程内，重启清空）
  - Redis 模式（ANALYSIS_RUN_REGISTRY=redis）：RedisAnalysisRunRegistry（跨进程，支持多 worker）

Redis 模式要求：
  - REDIS_URL 可达，且 connect_redis() 已在 lifespan 中调用成功
  - Redis 不可用时：get_run_registry() 抛出 RuntimeError（不静默 fallback memory）

设计：
  - 延迟初始化：_registry 首次调用时才创建，避免在模块导入时访问 Redis 客户端
  - 线程安全：asyncio 单线程模型，无需额外锁
"""

from __future__ import annotations

import logging

from app.core.config import settings
from app.services.analysis_run_registry import MemoryAnalysisRunRegistry
from app.services.run_registry_protocol import AnalysisRunRegistry

log = logging.getLogger(__name__)

# ── Singleton（延迟初始化）────────────────────────────────────────────────────

_registry: AnalysisRunRegistry | None = None


def get_run_registry() -> AnalysisRunRegistry:
    """
    返回全局 AnalysisRunRegistry 单例（延迟初始化）。

    memory 模式（默认）：MemoryAnalysisRunRegistry，进程内共享，重启清空。
    redis 模式：RedisAnalysisRunRegistry，跨进程持久，需 REDIS_URL 可用。

    Redis 不可用时抛出 RuntimeError — 调用方应捕获并返回 HTTP 503。
    """
    global _registry

    if _registry is not None:
        return _registry

    mode = settings.analysis_run_registry.lower().strip()

    if mode == "redis":
        from app.core.database import get_redis
        from app.services.redis_run_registry import RedisAnalysisRunRegistry

        redis_client = get_redis()
        if redis_client is None:
            raise RuntimeError(
                "ANALYSIS_RUN_REGISTRY=redis 但 Redis 客户端不可用。"
                "请确认 REDIS_URL 配置正确且 Redis 服务已启动。"
            )

        _registry = RedisAnalysisRunRegistry(
            redis        = redis_client,
            ttl_seconds  = settings.analysis_run_ttl_seconds,
            event_maxlen = settings.analysis_run_event_maxlen,
            env          = settings.app_env,
        )
        log.info(
            "RunRegistry: using Redis (ttl=%ds, maxlen=%d, env=%s)",
            settings.analysis_run_ttl_seconds,
            settings.analysis_run_event_maxlen,
            settings.app_env,
        )

    elif mode == "memory":
        _registry = MemoryAnalysisRunRegistry()
        log.info("RunRegistry: using Memory (in-process)")

    else:
        log.warning(
            "RunRegistry: unknown ANALYSIS_RUN_REGISTRY=%r, falling back to memory", mode
        )
        _registry = MemoryAnalysisRunRegistry()

    return _registry
