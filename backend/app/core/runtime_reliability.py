"""Runtime reliability primitives for Chat/Auth request paths."""
from __future__ import annotations

import asyncio
import hashlib
import socket
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, OperationalError, SQLAlchemyError, TimeoutError as SQLAlchemyTimeoutError

from app.core.config import settings
from app.core.database import AsyncSessionLocal, async_engine
from app.models.user import User


AUTH_DATABASE_UNAVAILABLE = "AUTH_DATABASE_UNAVAILABLE"
AUTH_DATABASE_TIMEOUT = "AUTH_DATABASE_TIMEOUT"


@dataclass(slots=True)
class AuthPrincipal:
    id: uuid.UUID
    username: str
    email: str
    is_active: bool
    created_at: datetime | None = None
    role: str = "user"
    is_admin: bool = False
    token_exp: int | None = None
    cache_status: str = "miss"


@dataclass(slots=True)
class RequestDeadline:
    started_at: float = field(default_factory=time.perf_counter)
    total_budget_ms: int = 30000
    budgets_ms: dict[str, int] = field(default_factory=lambda: {
        "auth_lookup": 4000,
        "entity_lookup": 1000,
        "report_selection": 3000,
    })

    def remaining_ms(self) -> int:
        elapsed = int((time.perf_counter() - self.started_at) * 1000)
        return max(0, self.total_budget_ms - elapsed)

    def budget_seconds(self, key: str) -> float:
        return max(0.001, self.budgets_ms.get(key, self.total_budget_ms) / 1000)


class RuntimeMetrics:
    def __init__(self) -> None:
        self.counters: dict[str, int] = {}
        self.observations: dict[str, list[float]] = {}
        self.recent_auth_lookups: list[dict[str, Any]] = []

    def inc(self, name: str, amount: int = 1) -> None:
        self.counters[name] = self.counters.get(name, 0) + amount

    def observe(self, name: str, value: float) -> None:
        self.observations.setdefault(name, []).append(value)

    def record_auth_lookup(self, payload: dict[str, Any]) -> None:
        self.recent_auth_lookups.append(dict(payload))
        self.recent_auth_lookups = self.recent_auth_lookups[-50:]

    def snapshot(self) -> dict[str, Any]:
        pool = async_engine.sync_engine.pool
        return {
            "counters": dict(self.counters),
            "observations": {k: list(v[-100:]) for k, v in self.observations.items()},
            "recent_auth_lookups": list(self.recent_auth_lookups[-20:]),
            "pool_checked_out": getattr(pool, "checkedout", lambda: None)(),
            "pool_overflow": getattr(pool, "overflow", lambda: None)(),
        }


runtime_metrics = RuntimeMetrics()


def reset_runtime_metrics() -> None:
    runtime_metrics.counters.clear()
    runtime_metrics.observations.clear()
    runtime_metrics.recent_auth_lookups.clear()


class CircuitBreaker:
    def __init__(self, *, threshold: int, open_seconds: float) -> None:
        self.threshold = threshold
        self.open_seconds = open_seconds
        self.failures = 0
        self.opened_at: float | None = None
        self.state = "closed"

    def before_call(self) -> str:
        if self.state == "open" and self.opened_at is not None:
            if time.perf_counter() - self.opened_at >= self.open_seconds:
                self.state = "half_open"
        return self.state

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = None
        self.state = "closed"

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.state = "open"
            self.opened_at = time.perf_counter()


auth_db_circuit = CircuitBreaker(
    threshold=settings.auth_db_timeout_threshold,
    open_seconds=settings.auth_circuit_open_seconds,
)


class AuthPrincipalCache:
    def __init__(self) -> None:
        self._items: dict[str, tuple[float, AuthPrincipal]] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _key(self, user_id: str, *, token_version: str | None = None, role_version: str | None = None) -> str:
        digest = hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()[:24]
        parts = [digest]
        if token_version:
            parts.append(f"tv:{token_version}")
        if role_version:
            parts.append(f"rv:{role_version}")
        return "|".join(parts)

    def get(self, user_id: str, *, count_miss: bool = True) -> AuthPrincipal | None:
        item = self._items.get(self._key(user_id))
        if not item:
            if count_miss:
                runtime_metrics.inc("auth_cache_miss")
            return None
        expires_at, principal = item
        if expires_at < time.time():
            self._items.pop(self._key(user_id), None)
            if count_miss:
                runtime_metrics.inc("auth_cache_miss")
            return None
        runtime_metrics.inc("auth_cache_hit")
        principal.cache_status = "hit"
        return principal

    def set(self, principal: AuthPrincipal) -> None:
        cached_principal = AuthPrincipal(
            id=principal.id,
            username=principal.username,
            email=principal.email,
            is_active=principal.is_active,
            is_admin=principal.is_admin,
            created_at=principal.created_at,
            role=principal.role,
            token_exp=None,
            cache_status=principal.cache_status,
        )
        self._items[self._key(str(principal.id))] = (
            time.time() + settings.auth_user_cache_ttl_seconds,
            cached_principal,
        )

    def invalidate(self, user_id: str) -> None:
        self._items.pop(self._key(user_id), None)

    def lock_for(self, user_id: str) -> asyncio.Lock:
        self._locks.setdefault(user_id, asyncio.Lock())
        return self._locks[user_id]


auth_principal_cache = AuthPrincipalCache()


def auth_db_unavailable_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "status": "failed",
            "error_code": AUTH_DATABASE_UNAVAILABLE,
            "message": "账户状态验证服务暂时不可用，请稍后重试。",
            "retryable": True,
        },
        headers={"Retry-After": "3"},
    )


def auth_db_timeout_exception(*, phase: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "status": "failed",
            "error_code": AUTH_DATABASE_TIMEOUT,
            "message": "账户状态验证超时，请稍后重试。",
            "retryable": True,
            "phase": phase,
        },
        headers={"Retry-After": "3"},
    )


def _pool_snapshot() -> dict[str, Any]:
    pool = async_engine.sync_engine.pool
    return {
        "checked_out": getattr(pool, "checkedout", lambda: None)(),
        "checked_in": getattr(pool, "checkedin", lambda: None)(),
        "overflow": getattr(pool, "overflow", lambda: None)(),
        "status": getattr(pool, "status", lambda: "")(),
    }


def _principal_from_user(user: User, *, token_exp: int | None, cache_status: str) -> AuthPrincipal:
    is_admin = bool(getattr(user, "is_admin", False))
    return AuthPrincipal(
        id=user.id,
        username=user.username,
        email=user.email,
        is_active=bool(user.is_active),
        is_admin=is_admin,
        created_at=user.created_at,
        role="admin" if is_admin else "user",
        token_exp=token_exp,
        cache_status=cache_status,
    )


async def load_auth_principal(user_id: str, *, token_exp: int | None = None, force_db: bool = False) -> AuthPrincipal:
    total_started = time.perf_counter()
    user_id_hash = hashlib.sha256(str(user_id).encode("utf-8")).hexdigest()[:12]
    trace: dict[str, Any] = {
        "user_id_hash": user_id_hash,
        "cache_hit": False,
        "token_parse_ms": 0,
        "cache_lookup_ms": 0,
        "singleflight_wait_ms": 0,
        "connection_checkout_ms": 0,
        "connection_establish_ms": 0,
        "db_execute_ms": 0,
        "row_decode_ms": 0,
        "principal_build_ms": 0,
        "cleanup_ms": 0,
        "total_ms": 0,
        "deadline_ms": int(settings.auth_db_lookup_timeout_seconds * 1000),
        "timeout_phase": None,
        "status": "started",
    }
    if not force_db:
        cache_started = time.perf_counter()
        cached = auth_principal_cache.get(user_id)
        trace["cache_lookup_ms"] = int((time.perf_counter() - cache_started) * 1000)
        if cached:
            trace.update({
                "cache_hit": True,
                "status": "success",
                "total_ms": int((time.perf_counter() - total_started) * 1000),
            })
            runtime_metrics.observe("auth_lookup_ms", trace["total_ms"])
            runtime_metrics.record_auth_lookup(trace)
            return cached

    state = auth_db_circuit.before_call()
    if state == "open":
        cached = auth_principal_cache.get(user_id)
        if cached:
            cached.cache_status = "stale_circuit"
            return cached
        runtime_metrics.inc("db_connect_timeouts")
        raise auth_db_unavailable_exception()

    lock = auth_principal_cache.lock_for(user_id)
    lock_wait_started = time.perf_counter()
    async with lock:
        trace["singleflight_wait_ms"] = int((time.perf_counter() - lock_wait_started) * 1000)
        if not force_db:
            cache_started = time.perf_counter()
            cached = auth_principal_cache.get(user_id, count_miss=False)
            trace["cache_lookup_ms"] += int((time.perf_counter() - cache_started) * 1000)
            if cached:
                runtime_metrics.inc("auth_singleflight_join")
                trace.update({
                    "cache_hit": True,
                    "status": "success",
                    "total_ms": int((time.perf_counter() - total_started) * 1000),
                })
                runtime_metrics.observe("auth_lookup_ms", trace["total_ms"])
                runtime_metrics.record_auth_lookup(trace)
                return cached

        started = time.perf_counter()
        runtime_metrics.inc("db_connect_attempts")
        try:
            async def _lookup() -> AuthPrincipal:
                async with AsyncSessionLocal() as session:
                    checkout_started = time.perf_counter()
                    await asyncio.wait_for(
                        session.connection(),
                        timeout=settings.auth_db_connect_timeout_seconds,
                    )
                    trace["connection_checkout_ms"] = int((time.perf_counter() - checkout_started) * 1000)
                    if getattr(settings, "database_transaction_pool_strategy", "") == "null_pool":
                        trace["connection_establish_ms"] = trace["connection_checkout_ms"]

                    execute_started = time.perf_counter()
                    result = await asyncio.wait_for(session.execute(
                        select(User.id, User.username, User.email, User.is_active, User.is_admin, User.created_at)
                        .where(User.id == uuid.UUID(str(user_id)))
                    ), timeout=settings.auth_db_query_timeout_seconds)
                    trace["db_execute_ms"] = int((time.perf_counter() - execute_started) * 1000)
                    decode_started = time.perf_counter()
                    row = result.first()
                    trace["row_decode_ms"] = int((time.perf_counter() - decode_started) * 1000)
                    if row is None:
                        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
                    build_started = time.perf_counter()
                    _is_admin = bool(getattr(row, "is_admin", False))
                    principal = AuthPrincipal(
                        id=row.id,
                        username=row.username,
                        email=row.email,
                        is_active=bool(row.is_active),
                        is_admin=_is_admin,
                        role="admin" if _is_admin else "user",
                        created_at=row.created_at,
                        token_exp=token_exp,
                        cache_status="miss",
                    )
                    trace["principal_build_ms"] = int((time.perf_counter() - build_started) * 1000)
                    if not principal.is_active:
                        raise HTTPException(status.HTTP_403_FORBIDDEN, "User disabled")
                    cleanup_started = time.perf_counter()
                    await asyncio.wait_for(
                        session.rollback(),
                        timeout=settings.auth_db_cleanup_timeout_seconds,
                    )
                    trace["cleanup_ms"] = int((time.perf_counter() - cleanup_started) * 1000)
                    return principal

            principal = await asyncio.wait_for(
                _lookup(),
                timeout=settings.auth_db_lookup_timeout_seconds,
            )
            auth_db_circuit.record_success()
            auth_principal_cache.set(principal)
            elapsed_ms = (time.perf_counter() - started) * 1000
            runtime_metrics.observe("auth_db_lookup_ms", elapsed_ms)
            runtime_metrics.observe("auth_lookup_ms", elapsed_ms)
            trace.update({"status": "success", "total_ms": int(elapsed_ms)})
            runtime_metrics.record_auth_lookup(trace)
            return principal
        except asyncio.CancelledError:
            runtime_metrics.inc("request_cancelled")
            raise
        except HTTPException:
            auth_db_circuit.record_success()
            raise
        except (
            asyncio.TimeoutError,
            TimeoutError,
            SQLAlchemyTimeoutError,
            OperationalError,
            DBAPIError,
            SQLAlchemyError,
            socket.timeout,
            OSError,
        ) as exc:
            auth_db_circuit.record_failure()
            runtime_metrics.inc("db_connect_timeouts")
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            runtime_metrics.observe("auth_db_lookup_failed_ms", elapsed_ms)
            connection_invalidated = bool(getattr(exc, "connection_invalidated", False))
            timeout_phase = "total"
            if trace["connection_checkout_ms"] <= 0:
                timeout_phase = "connect"
            elif trace["db_execute_ms"] <= 0:
                timeout_phase = "db_execute"
            elif trace["cleanup_ms"] <= 0:
                timeout_phase = "cleanup"
            trace.update({
                "status": "failed",
                "total_ms": int((time.perf_counter() - total_started) * 1000),
                "timeout_phase": timeout_phase if isinstance(exc, (asyncio.TimeoutError, TimeoutError, SQLAlchemyTimeoutError)) else None,
                "error_class": type(exc).__name__,
                "connection_invalidated": connection_invalidated,
            })
            runtime_metrics.record_auth_lookup(trace)
            import logging

            logging.getLogger(__name__).warning(
                "auth_db_lookup_failed error_class=%s elapsed_ms=%s timeout_phase=%s connection_invalidated=%s pool=%s response_error_code=%s raised_at=app.core.runtime_reliability:load_auth_principal",
                type(exc).__name__,
                elapsed_ms,
                trace.get("timeout_phase"),
                connection_invalidated,
                _pool_snapshot(),
                AUTH_DATABASE_TIMEOUT if trace.get("timeout_phase") else AUTH_DATABASE_UNAVAILABLE,
            )
            if trace.get("timeout_phase"):
                raise auth_db_timeout_exception(phase=str(trace["timeout_phase"])) from None
            raise auth_db_unavailable_exception() from None


def runtime_reliability_snapshot() -> dict[str, Any]:
    snap = runtime_metrics.snapshot()
    snap["circuit_state"] = auth_db_circuit.state
    snap["generated_at"] = datetime.now(timezone.utc).isoformat()
    return snap
