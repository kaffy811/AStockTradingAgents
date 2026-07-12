from __future__ import annotations

from sqlalchemy.pool import AsyncAdaptedQueuePool

from app.core.database import async_engine
from app.services.company_v2_report_rag_db_repository import DatabaseCompanyV2ReportRagRepository


def test_postgres_engines_use_reusable_async_pool():
    assert isinstance(async_engine.sync_engine.pool, AsyncAdaptedQueuePool)

    repo = DatabaseCompanyV2ReportRagRepository()
    repo._database_url = "postgresql+asyncpg://user:pass@localhost/db"  # noqa: SLF001
    repo._sessionmaker = None  # noqa: SLF001
    repo._engine = None  # noqa: SLF001

    async def _bootstrap():
        maker = await repo._get_sessionmaker()  # noqa: SLF001
        return maker

    import asyncio

    asyncio.run(_bootstrap())
    assert isinstance(repo._engine.sync_engine.pool, AsyncAdaptedQueuePool)  # noqa: SLF001
