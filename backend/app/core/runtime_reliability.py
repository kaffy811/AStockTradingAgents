"""Runtime reliability primitives for Chat/Auth request paths."""
from __future__ import annotations

import asyncio
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


@dataclass(slots=True)
class AuthPrincipal:
    id: uuid.UUID
    username: str
    email: str
    is_active: bool
    created_at: datetime | None = None
    role: str = "user"
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

    def inc(self, name: str, amount: int = 1) -> None:
        self.counters[name] = self.counters.get(name, 0) + amount

    def observe(self, name: str, value: float) -> None:
        self.observations.setdefault(name, []).append(value)

    def snapshot(self) -> dict[str, Any]:
        pool = async_engine.sync_engine.pool
        return {
            "counters": dict(self.counters),
            "observations": {k: list(v[-100:]) for k, v in self.observations.items()},
            "pool_checked_out": getattr(pool, "checkedout", lambda: None)(),
            "pool_overflow": getattr(pool, "overflow", lambda: None)(),
        }


runtime_metrics = RuntimeMetrics()


def reset_runtime_metrics() -> None:
    runtime_metrics.counters.clear()
    runtime_metrics.observations.clear()


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
        parts = [str(user_id)]
        if token_version:
            parts.append(f"tv:{token_version}")
        if role_version:
            parts.append(f"rv:{role_version}")
        return "|".join(parts)

    def get(self, user_id: str, *, count_miss: bool = True) -> AuthPrincipal | None:
        item = self._items.get(user_id)
        if not item:
            if count_miss:
                runtime_metrics.inc("auth_cache_miss")
            return None
        expires_at, principal = item
        if expires_at < time.time():
            self._items.pop(user_id, None)
            if count_miss:
                runtime_metrics.inc("auth_cache_miss")
            return None
        runtime_metrics.inc("auth_cache_hit")
        principal.cache_status = "hit"
        return principal

    def set(self, principal: AuthPrincipal) -> None:
        self._items[str(principal.id)] = (time.time() + settings.auth_user_cache_ttl_seconds, principal)

    def invalidate(self, user_id: str) -> None:
        self._items.pop(user_id, None)

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


def _principal_from_user(user: User, *, token_exp: int | None, cache_status: str) -> AuthPrincipal:
    return AuthPrincipal(
        id=user.id,
        username=user.username,
        email=user.email,
        is_active=bool(user.is_active),
        created_at=user.created_at,
        token_exp=token_exp,
        cache_status=cache_status,
    )


async def load_auth_principal(user_id: str, *, token_exp: int | None = None, force_db: bool = False) -> AuthPrincipal:
    if not force_db:
        cached = auth_principal_cache.get(user_id)
        if cached:
            return cached

    state = auth_db_circuit.before_call()
    if state == "open":
        cached = auth_principal_cache.get(user_id)
        if cached:
            cached.cache_status = "stale_circuit"
            return cached
        runtime_metrics.inc("db_connect_timeouts")
        raise auth_db_unavailable_exception()

    async with auth_principal_cache.lock_for(user_id):
        if not force_db:
            cached = auth_principal_cache.get(user_id, count_miss=False)
            if cached:
                runtime_metrics.inc("auth_singleflight_join")
                return cached

        started = time.perf_counter()
        runtime_metrics.inc("db_connect_attempts")
        try:
            async def _lookup() -> AuthPrincipal:
                async with AsyncSessionLocal() as session:
                    result = await session.execute(
                        select(User.id, User.username, User.email, User.is_active, User.created_at)
                        .where(User.id == uuid.UUID(str(user_id)))
                    )
                    row = result.first()
                    if row is None:
                        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
                    principal = AuthPrincipal(
                        id=row.id,
                        username=row.username,
                        email=row.email,
                        is_active=bool(row.is_active),
                        created_at=row.created_at,
                        token_exp=token_exp,
                        cache_status="miss",
                    )
                    if not principal.is_active:
                        raise HTTPException(status.HTTP_403_FORBIDDEN, "User disabled")
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
        ):
            auth_db_circuit.record_failure()
            runtime_metrics.inc("db_connect_timeouts")
            raise auth_db_unavailable_exception() from None


def runtime_reliability_snapshot() -> dict[str, Any]:
    snap = runtime_metrics.snapshot()
    snap["circuit_state"] = auth_db_circuit.state
    snap["generated_at"] = datetime.now(timezone.utc).isoformat()
    return snap
