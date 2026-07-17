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
from app.core.database import _connection_mode, _engine_kwargs
from app.dependencies import get_current_user


class _Creds:
    credentials = "token"


class _FakeResult:
    def __init__(self, user_id: uuid.UUID):
        self.user_id = user_id

    def first(self):
        return SimpleNamespace(
            id=self.user_id,
            username="tester",
            email="tester@example.com",
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )


class _FakeSession:
    calls = 0

    def __init__(self, user_id: uuid.UUID, delay: float = 0.0, cancel: bool = False, exc: Exception | None = None):
        self.user_id = user_id
        self.delay = delay
        self.cancel = cancel
        self.exc = exc

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
        return _FakeResult(self.user_id)


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


@pytest.mark.asyncio
async def test_auth_cache_miss_performs_one_short_query(monkeypatch):
    user_id = uuid.uuid4()
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
    assert exc.value.detail["error_code"] == rr.AUTH_DATABASE_UNAVAILABLE
    assert exc.value.detail["retryable"] is True


@pytest.mark.asyncio
async def test_builtin_timeout_error_returns_503(monkeypatch):
    user_id = uuid.uuid4()
    monkeypatch.setattr(rr, "AsyncSessionLocal", lambda: _FakeSession(user_id, exc=TimeoutError("ssl connect timeout")))
    with pytest.raises(HTTPException) as exc:
        await rr.load_auth_principal(str(user_id), force_db=True)
    assert exc.value.status_code == 503
    assert exc.value.detail["error_code"] == rr.AUTH_DATABASE_UNAVAILABLE
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
    assert _connection_mode in {"transaction_pooler", "session_pooler", "direct"}
    assert _engine_kwargs["connect_args"]["statement_cache_size"] == 0
    if _connection_mode == "transaction_pooler":
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
