from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool

from app.core.config import settings
from app.core.database import async_engine
from app.core.database_pool_policy import resolve_database_pool_policy
from app.services.company_v2_report_rag_db_repository import DatabaseCompanyV2ReportRagRepository


@pytest.mark.parametrize(
    ("database_url", "strategy", "mode", "expected_pool"),
    [
        ("sqlite+aiosqlite:///:memory:", "small_queue_pool", "transaction_pooler", NullPool),
        ("sqlite+aiosqlite:///./test.db", "small_queue_pool", "transaction_pooler", NullPool),
        ("postgresql+asyncpg://user:pass@localhost/db", "small_queue_pool", "transaction_pooler", AsyncAdaptedQueuePool),
        ("postgresql+asyncpg://user:pass@localhost/db", "queue_pool", "transaction_pooler", AsyncAdaptedQueuePool),
        ("postgresql+asyncpg://user:pass@localhost/db", "null_pool", "transaction_pooler", NullPool),
        ("postgresql+asyncpg://user:pass@localhost/db", "small_queue_pool", "direct", AsyncAdaptedQueuePool),
    ],
)
def test_database_pool_policy_matrix(database_url: str, strategy: str, mode: str, expected_pool: type):
    policy = resolve_database_pool_policy(
        database_url,
        strategy,
        connection_mode=mode,
        pool_pre_ping=True,
        command_timeout_seconds=45,
        pool_size=2,
        max_overflow=0,
        direct_pool_size=5,
        direct_max_overflow=10,
        pool_recycle_seconds=1800,
        pool_timeout_seconds=10,
    )

    assert policy.pool_class is expected_pool
    assert policy.pool_kwargs["poolclass"] is expected_pool
    assert policy.pool_kwargs["pool_pre_ping"] is True
    if database_url.startswith("postgresql"):
        assert policy.connect_args == {"statement_cache_size": 0, "command_timeout": 45}
    else:
        assert policy.connect_args == {}
        assert "connect_args" not in policy.pool_kwargs


def test_database_pool_policy_rejects_invalid_postgres_strategy():
    with pytest.raises(ValueError, match="unsupported database transaction pool strategy"):
        resolve_database_pool_policy(
            "postgresql+asyncpg://user:pass@localhost/db",
            "definitely_invalid",
        )


def test_database_pool_policy_direct_mode_uses_direct_pool_limits():
    policy = resolve_database_pool_policy(
        "postgresql+asyncpg://user:pass@localhost/db",
        "small_queue_pool",
        connection_mode="session_pooler",
        pool_size=2,
        max_overflow=0,
        direct_pool_size=7,
        direct_max_overflow=3,
    )

    assert policy.pool_class is AsyncAdaptedQueuePool
    assert policy.pool_kwargs["pool_size"] == 7
    assert policy.pool_kwargs["max_overflow"] == 3


def test_database_engine_matches_current_dialect_policy():
    current_policy = resolve_database_pool_policy(
        settings.database_url,
        settings.database_transaction_pool_strategy,
        connection_mode=settings.database_connection_mode,
        pool_pre_ping=settings.database_pool_pre_ping,
        command_timeout_seconds=settings.database_command_timeout_seconds,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        direct_pool_size=settings.database_direct_pool_size,
        direct_max_overflow=settings.database_direct_max_overflow,
        pool_recycle_seconds=settings.database_pool_recycle_seconds,
        pool_timeout_seconds=settings.database_pool_timeout_seconds,
    )

    assert isinstance(async_engine.sync_engine.pool, current_policy.pool_class)
    assert getattr(async_engine.sync_engine.pool, "_pre_ping", False) is settings.database_pool_pre_ping


def test_postgres_engine_factory_uses_reusable_async_pool_without_connecting():
    policy = resolve_database_pool_policy(
        "postgresql+asyncpg://user:pass@localhost/db",
        "small_queue_pool",
        connection_mode="transaction_pooler",
        pool_pre_ping=True,
        command_timeout_seconds=45,
    )
    engine = create_async_engine("postgresql+asyncpg://user:pass@localhost/db", **policy.pool_kwargs)
    try:
        assert isinstance(engine.sync_engine.pool, AsyncAdaptedQueuePool)
        assert getattr(engine.sync_engine.pool, "_pre_ping", False) is True
    finally:
        asyncio.run(engine.dispose())


def test_rag_postgres_engine_uses_reusable_async_pool():
    DatabaseCompanyV2ReportRagRepository.close_shared_resources()

    repo = DatabaseCompanyV2ReportRagRepository()
    repo._database_url = "postgresql+asyncpg://user:pass@localhost/db"  # noqa: SLF001
    repo._sessionmaker = None  # noqa: SLF001
    repo._engine = None  # noqa: SLF001

    async def _bootstrap():
        maker = await repo._get_sessionmaker()  # noqa: SLF001
        return maker

    asyncio.run(_bootstrap())
    try:
        assert isinstance(repo._engine.sync_engine.pool, AsyncAdaptedQueuePool)  # noqa: SLF001
        assert getattr(repo._engine.sync_engine.pool, "_pre_ping", False) is True  # noqa: SLF001
    finally:
        DatabaseCompanyV2ReportRagRepository.close_shared_resources()


def test_rag_db_repository_reuses_shared_loop_and_engine():
    DatabaseCompanyV2ReportRagRepository.close_shared_resources()
    r1 = DatabaseCompanyV2ReportRagRepository(database_url="postgresql+asyncpg://user:pass@localhost/db")
    r2 = DatabaseCompanyV2ReportRagRepository(database_url="postgresql+asyncpg://user:pass@localhost/db")

    r1._run(r1._get_sessionmaker())  # noqa: SLF001
    r2._run(r2._get_sessionmaker())  # noqa: SLF001

    assert r1._loop is r2._loop  # noqa: SLF001
    assert r1._engine is r2._engine  # noqa: SLF001
    DatabaseCompanyV2ReportRagRepository.close_shared_resources()


def test_rag_db_run_timeout_cancels_future(monkeypatch):
    from app.services.company_v2_report_rag_db_repository import CompanyV2RagRepositoryError

    DatabaseCompanyV2ReportRagRepository.close_shared_resources()
    monkeypatch.setattr(settings, "company_v2_rag_db_run_timeout_seconds", 0.01)
    repo = DatabaseCompanyV2ReportRagRepository()

    async def _slow():
        await asyncio.sleep(1)
        return "late"

    try:
        with pytest.raises(CompanyV2RagRepositoryError) as exc:
            repo._run(_slow())  # noqa: SLF001
        assert exc.value.error_code == "RAG_DB_QUERY_TIMEOUT"
        assert repo._run(asyncio.sleep(0, result="ok")) == "ok"  # noqa: SLF001
    finally:
        DatabaseCompanyV2ReportRagRepository.close_shared_resources()
