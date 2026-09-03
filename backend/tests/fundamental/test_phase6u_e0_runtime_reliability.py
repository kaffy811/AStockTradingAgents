from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from jose import JWTError

from app.core import runtime_reliability as rr
from app.core.config import settings
from app.core.database import _engine_kwargs, _pool_policy
from app.dependencies import get_current_user


class _Creds:
    credentials = "token"


class _FakeResult:
    def __init__(self, user_id: uuid.UUID, *, active: bool = True, missing: bool = False):
        self.user_id = user_id
        self.active = active
        self.missing = missing

    def first(self):
        if self.missing:
            return None
        return SimpleNamespace(
            id=self.user_id,
            username="tester",
            email="tester@example.com",
            is_active=self.active,
            created_at=datetime.now(timezone.utc),
        )


class _FakeSession:
    calls = 0

    def __init__(
        self,
        user_id: uuid.UUID,
        delay: float = 0.0,
        cancel: bool = False,
        exc: Exception | None = None,
        active: bool = True,
        missing: bool = False,
    ):
        self.user_id = user_id
        self.delay = delay
        self.cancel = cancel
        self.exc = exc
        self.active = active
        self.missing = missing

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, stmt):
        _FakeSession.calls += 1
        if self.cancel:
            raise asyncio.CancelledError()
        if self.exc:
            raise self.exc
        if self.delay:
            await asyncio.sleep(self.delay)
        return _FakeResult(self.user_id, active=self.active, missing=self.missing)

    async def connection(self):
        return self

    async def rollback(self):
        return None


@pytest.fixture(autouse=True)
def _clear_auth_cache():
    rr.auth_principal_cache._items.clear()  # noqa: SLF001
    rr.auth_principal_cache._locks.clear()  # noqa: SLF001
    rr.reset_runtime_metrics()
    rr.auth_db_circuit.failures = 0
    rr.auth_db_circuit.state = "closed"
    rr.auth_db_circuit.opened_at = None
    yield


@pytest.mark.asyncio
async def test_valid_cached_principal_no_db_query(monkeypatch):
    user_id = uuid.uuid4()
    principal = rr.AuthPrincipal(
        id=user_id,
        username="cached",
        email="cached@example.com",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    rr.auth_principal_cache.set(principal)

    def _boom():
        raise AssertionError("DB should not be called")

    monkeypatch.setattr(rr, "AsyncSessionLocal", _boom)
    loaded = await rr.load_auth_principal(str(user_id))
    assert loaded.username == "cached"
    assert loaded.cache_status == "hit"
    snapshot = rr.runtime_reliability_snapshot()
    assert snapshot["counters"]["auth_cache_hit"] == 1
    assert snapshot["recent_auth_lookups"][-1]["cache_hit"] is True
    assert snapshot["recent_auth_lookups"][-1]["total_ms"] < 100


@pytest.mark.asyncio
async def test_auth_cache_miss_performs_one_short_query(monkeypatch):
    user_id = uuid.uuid4()
    _FakeSession.calls = 0
    monkeypatch.setattr(rr, "AsyncSessionLocal", lambda: _FakeSession(user_id))
    loaded = await rr.load_auth_principal(str(user_id))
    assert loaded.id == user_id
    assert _FakeSession.calls == 1
    snapshot = rr.runtime_reliability_snapshot()
    recent = snapshot["recent_auth_lookups"][-1]
    assert recent["cache_hit"] is False
    assert recent["status"] == "success"
    assert "user_id_hash" in recent
    assert str(user_id) not in str(recent)


@pytest.mark.asyncio
async def test_auth_db_failure_is_not_cached_as_principal(monkeypatch):
    user_id = uuid.uuid4()
    _FakeSession.calls = 0
    monkeypatch.setattr(rr, "AsyncSessionLocal", lambda: _FakeSession(user_id, exc=OSError("db unavailable")))
    with pytest.raises(HTTPException) as exc:
        await rr.load_auth_principal(str(user_id), force_db=True)
    assert exc.value.status_code == 503
    assert rr.auth_principal_cache.get(str(user_id), count_miss=False) is None
    assert _FakeSession.calls == 1


@pytest.mark.asyncio
async def test_inactive_user_not_cached_as_active(monkeypatch):
    user_id = uuid.uuid4()
    _FakeSession.calls = 0
    monkeypatch.setattr(rr, "AsyncSessionLocal", lambda: _FakeSession(user_id, active=False))
    with pytest.raises(HTTPException) as exc:
        await rr.load_auth_principal(str(user_id), force_db=True)
    assert exc.value.status_code == 403
    assert rr.auth_principal_cache.get(str(user_id), count_miss=False) is None
    assert _FakeSession.calls == 1


@pytest.mark.asyncio
async def test_auth_cache_explicit_clear_removes_principal():
    user_id = uuid.uuid4()
    principal = rr.AuthPrincipal(
        id=user_id,
        username="cached",
        email="cached@example.com",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    rr.auth_principal_cache.set(principal)
    assert rr.auth_principal_cache.get(str(user_id), count_miss=False) is not None
    rr.auth_principal_cache._items.clear()  # noqa: SLF001
    assert rr.auth_principal_cache.get(str(user_id), count_miss=False) is None


@pytest.mark.asyncio
async def test_auth_cache_does_not_store_token(monkeypatch):
    user_id = uuid.uuid4()
    monkeypatch.setattr(rr, "AsyncSessionLocal", lambda: _FakeSession(user_id))
    loaded = await rr.load_auth_principal(str(user_id), token_exp=1893456000, force_db=True)
    assert loaded.id == user_id
    cached = rr.auth_principal_cache.get(str(user_id), count_miss=False)
    assert cached is not None
    assert cached.token_exp is None
    cache_repr = repr(rr.auth_principal_cache._items)  # noqa: SLF001
    assert "bearer" not in cache_repr.lower()
    assert "eyj" not in cache_repr.lower()


@pytest.mark.asyncio
async def test_singleflight_exception_releases_waiter(monkeypatch):
    user_id = uuid.uuid4()
    _FakeSession.calls = 0
    monkeypatch.setattr(rr, "AsyncSessionLocal", lambda: _FakeSession(user_id, exc=OSError("db unavailable")))
    results = await asyncio.gather(
        rr.load_auth_principal(str(user_id)),
        rr.load_auth_principal(str(user_id)),
        return_exceptions=True,
    )
    assert all(isinstance(item, HTTPException) for item in results)
    assert rr.auth_principal_cache.get(str(user_id), count_miss=False) is None


def test_auth_cache_test_isolation_starts_empty():
    assert rr.auth_principal_cache._items == {}  # noqa: SLF001


@pytest.mark.asyncio
async def test_auth_cache_ttl_expires(monkeypatch):
    user_id = uuid.uuid4()
    principal = rr.AuthPrincipal(
        id=user_id,
        username="cached",
        email="cached@example.com",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    monkeypatch.setattr(settings, "auth_user_cache_ttl_seconds", 0)
    rr.auth_principal_cache.set(principal)
    _FakeSession.calls = 0
    monkeypatch.setattr(rr, "AsyncSessionLocal", lambda: _FakeSession(user_id))
    loaded = await rr.load_auth_principal(str(user_id))
    assert loaded.id == user_id
    assert _FakeSession.calls == 1


@pytest.mark.asyncio
async def test_20_concurrent_same_user_singleflight(monkeypatch):
    user_id = uuid.uuid4()
    _FakeSession.calls = 0
    monkeypatch.setattr(rr, "AsyncSessionLocal", lambda: _FakeSession(user_id, delay=0.01))
    results = await asyncio.gather(*[rr.load_auth_principal(str(user_id)) for _ in range(20)])
    assert {item.id for item in results} == {user_id}
    assert _FakeSession.calls == 1
    snapshot = rr.runtime_reliability_snapshot()
    assert snapshot["counters"]["db_connect_attempts"] == 1
    assert snapshot["counters"]["auth_singleflight_join"] >= 1


@pytest.mark.asyncio
async def test_db_connect_timeout_returns_503(monkeypatch):
    user_id = uuid.uuid4()
    monkeypatch.setattr(settings, "auth_db_lookup_timeout_seconds", 0.01)
    monkeypatch.setattr(rr, "AsyncSessionLocal", lambda: _FakeSession(user_id, delay=1.0))
    with pytest.raises(HTTPException) as exc:
        await rr.load_auth_principal(str(user_id), force_db=True)
    assert exc.value.status_code == 503
    assert exc.value.detail["error_code"] == rr.AUTH_DATABASE_TIMEOUT
    assert exc.value.detail["retryable"] is True
    assert exc.value.detail["phase"] in {"connect", "db_execute", "cleanup", "total"}


@pytest.mark.asyncio
async def test_builtin_timeout_error_returns_503(monkeypatch):
    user_id = uuid.uuid4()
    monkeypatch.setattr(rr, "AsyncSessionLocal", lambda: _FakeSession(user_id, exc=TimeoutError("ssl connect timeout")))
    with pytest.raises(HTTPException) as exc:
        await rr.load_auth_principal(str(user_id), force_db=True)
    assert exc.value.status_code == 503
    assert exc.value.detail["error_code"] == rr.AUTH_DATABASE_TIMEOUT
    assert exc.value.headers["Retry-After"] == "3"


@pytest.mark.asyncio
async def test_cancelled_error_propagates(monkeypatch):
    user_id = uuid.uuid4()
    monkeypatch.setattr(rr, "AsyncSessionLocal", lambda: _FakeSession(user_id, cancel=True))
    with pytest.raises(asyncio.CancelledError):
        await rr.load_auth_principal(str(user_id), force_db=True)


@pytest.mark.asyncio
async def test_invalid_token_returns_401(monkeypatch):
    import app.dependencies as deps

    def _bad(token):
        raise JWTError("bad")

    monkeypatch.setattr(deps, "decode_token", _bad)
    with pytest.raises(HTTPException) as exc:
        await get_current_user(_Creds())
    assert exc.value.status_code == 401


def test_connection_mode_config_and_transaction_prepared_statement_disabled():
    assert _pool_policy.connection_mode in {"transaction_pooler", "session_pooler", "direct"}
    if _pool_policy.dialect == "postgresql":
        assert _engine_kwargs["connect_args"]["statement_cache_size"] == 0
    if _pool_policy.connection_mode == "transaction_pooler" and _pool_policy.pool_kwargs.get("pool_size"):
        assert (_engine_kwargs.get("pool_size") or 0) <= 2
        assert (_engine_kwargs.get("max_overflow") or 0) <= 2


def test_circuit_opens_on_repeated_timeout_and_half_open_recovers():
    breaker = rr.CircuitBreaker(threshold=2, open_seconds=0.01)
    assert breaker.before_call() == "closed"
    breaker.record_failure()
    assert breaker.state == "closed"
    breaker.record_failure()
    assert breaker.state == "open"
    assert breaker.before_call() == "open"
    import time
    time.sleep(0.02)
    assert breaker.before_call() == "half_open"
    breaker.record_success()
    assert breaker.state == "closed"
