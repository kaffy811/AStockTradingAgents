"""
app/routers/health.py — Lightweight + deep health check endpoints.

GET /api/v1/health      — fast liveness probe (DB + Redis connection state).
GET /api/v1/health/deep — comprehensive readiness check (pgvector, tables,
                          data-source imports, embedding provider status).

Security: no secrets, tokens, or internal paths are returned.
"""
from __future__ import annotations

import importlib
import logging

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import settings
from app.core.database import async_engine, get_redis
from app.core.runtime_reliability import runtime_reliability_snapshot

log = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])

# ── Constants ──────────────────────────────────────────────────────────────────

_APP_VERSION = settings.app_version
_APP_ENV = settings.app_env


# ── /health ────────────────────────────────────────────────────────────────────

@router.get("")
async def health():
    """Fast liveness probe — checks DB + Redis connectivity."""
    db_ok = False
    redis_ok = False

    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        log.warning("health: db check failed: %s", type(exc).__name__)

    redis = get_redis()
    if redis is not None:
        try:
            await redis.ping()
            redis_ok = True
        except Exception as exc:
            log.warning("health: redis check failed: %s", type(exc).__name__)

    status = "ok" if db_ok else "degraded"

    return {
        "status": status,
        "app": settings.app_name,
        "version": _APP_VERSION,
        "env": _APP_ENV,
        "db_status": "ok" if db_ok else "unavailable",
        "redis_status": "ok" if redis_ok else "unavailable",
        "data_mode": settings.data_mode,
        "report_rag_enabled": settings.enable_report_rag,
    }


@router.get("/runtime")
async def health_runtime():
    """Runtime reliability metrics. No URL, JWT, email, or user labels."""
    return {
        "status": "ok",
        "database_connection_mode": settings.database_connection_mode,
        "database_transaction_pool_strategy": settings.database_transaction_pool_strategy,
        "runtime": runtime_reliability_snapshot(),
    }


# ── /health/deep ───────────────────────────────────────────────────────────────

@router.get("/deep")
async def health_deep():
    """
    Comprehensive readiness check.

    Checks PostgreSQL, Redis, pgvector extension, required tables,
    data-source library imports, embedding provider, and report chat cache.

    Returns HTTP 200 with status=degraded on partial failures —
    callers should inspect individual `checks` entries.
    No secrets, tokens, or internal paths are returned.
    """
    checks: dict[str, dict] = {}
    overall = "ok"

    # ── PostgreSQL ─────────────────────────────────────────────────────────────
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["postgres"] = {"status": "ok"}
    except Exception as exc:
        checks["postgres"] = {"status": "error", "reason": type(exc).__name__}
        overall = "degraded"

    # ── Redis ──────────────────────────────────────────────────────────────────
    redis = get_redis()
    if redis is None:
        checks["redis"] = {"status": "unavailable", "reason": "REDIS_URL not configured or connection failed"}
    else:
        try:
            await redis.ping()
            checks["redis"] = {"status": "ok"}
        except Exception as exc:
            checks["redis"] = {"status": "error", "reason": type(exc).__name__}

    # ── pgvector extension ─────────────────────────────────────────────────────
    try:
        async with async_engine.connect() as conn:
            result = await conn.execute(
                text("SELECT installed_version FROM pg_available_extensions WHERE name='vector'")
            )
            row = result.fetchone()
        if row and row[0]:
            checks["pgvector"] = {"status": "ok", "version": row[0]}
        else:
            checks["pgvector"] = {"status": "unavailable", "reason": "pgvector extension not installed"}
            overall = "degraded"
    except Exception as exc:
        checks["pgvector"] = {"status": "error", "reason": type(exc).__name__}
        overall = "degraded"

    # ── Required tables ────────────────────────────────────────────────────────
    for tbl in ("report_documents", "report_chunks"):
        try:
            async with async_engine.connect() as conn:
                result = await conn.execute(
                    text(f"SELECT to_regclass('public.{tbl}')")
                )
                row = result.fetchone()
            exists = row is not None and row[0] is not None
            checks[f"table_{tbl}"] = {"status": "ok" if exists else "missing"}
            if not exists:
                overall = "degraded"
        except Exception as exc:
            checks[f"table_{tbl}"] = {"status": "error", "reason": type(exc).__name__}
            overall = "degraded"

    # ── BaoStock availability ──────────────────────────────────────────────────
    try:
        importlib.import_module("baostock")
        checks["baostock"] = {"status": "available"}
    except ImportError:
        checks["baostock"] = {"status": "unavailable", "reason": "baostock not installed"}
        if settings.enable_baostock:
            overall = "degraded"

    # ── AkShare availability ───────────────────────────────────────────────────
    try:
        importlib.import_module("akshare")
        checks["akshare"] = {"status": "available"}
    except ImportError:
        checks["akshare"] = {"status": "unavailable", "reason": "akshare not installed"}
        if settings.enable_akshare:
            overall = "degraded"

    # ── Embedding provider ─────────────────────────────────────────────────────
    provider = settings.report_embedding_provider
    if provider == "mock":
        checks["embedding_provider"] = {
            "status": "ok",
            "provider": "mock",
            "note": "mock mode — suitable for CI/link-test only",
        }
    elif provider == "local":
        model = settings.report_embedding_model or "BAAI/bge-small-zh-v1.5"
        try:
            importlib.import_module("sentence_transformers")
            checks["embedding_provider"] = {
                "status": "ok",
                "provider": "local",
                "model": model,
                "dim": settings.report_embedding_dim,
            }
        except ImportError:
            checks["embedding_provider"] = {
                "status": "error",
                "provider": "local",
                "reason": "sentence_transformers not installed",
            }
            overall = "degraded"
    elif provider == "disabled":
        checks["embedding_provider"] = {
            "status": "disabled",
            "provider": "disabled",
            "note": "embeddings disabled — RAG will not work",
        }
        if settings.enable_report_rag:
            overall = "degraded"
    else:
        checks["embedding_provider"] = {
            "status": "unknown",
            "provider": provider,
            "reason": f"unrecognised REPORT_EMBEDDING_PROVIDER value: {provider!r}",
        }
        overall = "degraded"

    # ── Report chat cache ──────────────────────────────────────────────────────
    cache_status = "enabled" if settings.enable_report_chat_cache else "disabled"
    redis_backing = checks.get("redis", {}).get("status") == "ok"
    checks["report_chat_cache"] = {
        "status": cache_status,
        "redis_backing": redis_backing,
        "ttl_seconds": settings.report_chat_cache_ttl_seconds,
    }

    # ── Rate limit ─────────────────────────────────────────────────────────────
    checks["report_chat_rate_limit"] = {
        "status": "enabled" if settings.enable_report_chat_rate_limit else "disabled",
        "per_minute": settings.report_chat_rate_limit_per_minute,
        "per_hour": settings.report_chat_rate_limit_per_hour,
    }

    # ── Feature flags ──────────────────────────────────────────────────────────
    checks["feature_flags"] = {
        "data_mode": settings.data_mode,
        "report_rag": settings.enable_report_rag,
        "report_pdf": settings.enable_report_pdf,
        "report_chat_memory": settings.enable_report_chat_memory,
        "multi_agent_orchestrator": settings.enable_multi_agent_orchestrator,
    }

    return {
        "status": overall,
        "app": settings.app_name,
        "version": _APP_VERSION,
        "env": _APP_ENV,
        "checks": checks,
    }
