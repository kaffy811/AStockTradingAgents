from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.pool import AsyncAdaptedQueuePool

from app.core.config import settings
from app.core.database import async_engine
from app.services.company_v2_report_rag_db_repository import DatabaseCompanyV2ReportRagRepository


def test_postgres_engines_use_reusable_async_pool():
    assert isinstance(async_engine.sync_engine.pool, AsyncAdaptedQueuePool)
    assert getattr(async_engine.sync_engine.pool, "_pre_ping", False) is True

    repo = DatabaseCompanyV2ReportRagRepository()
    repo._database_url = "postgresql+asyncpg://user:pass@localhost/db"  # noqa: SLF001
    repo._sessionmaker = None  # noqa: SLF001
    repo._engine = None  # noqa: SLF001

    async def _bootstrap():
        maker = await repo._get_sessionmaker()  # noqa: SLF001
        return maker

    asyncio.run(_bootstrap())
    assert isinstance(repo._engine.sync_engine.pool, AsyncAdaptedQueuePool)  # noqa: SLF001
    assert getattr(repo._engine.sync_engine.pool, "_pre_ping", False) is True  # noqa: SLF001


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
