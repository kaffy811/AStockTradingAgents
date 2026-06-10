from collections.abc import AsyncGenerator

from redis.asyncio import Redis, from_url
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import settings

# ── SQLAlchemy ────────────────────────────────────────────────────────────────
# NullPool: disables SQLAlchemy's local connection pool.
#   Supabase Transaction Pooler (PgBouncer) already manages pooling server-side;
#   running a second pool on top causes prepared-statement conflicts.
# statement_cache_size=0: asyncpg caches prepared statements by default.
#   PgBouncer in transaction mode routes statements to different backend
#   connections, so a statement cached on connection A may not exist on
#   connection B → DuplicatePreparedStatementError. Setting cache size to 0
#   disables client-side prepared statement caching entirely.

async_engine = create_async_engine(
    settings.database_url,
    poolclass=NullPool,
    connect_args={"statement_cache_size": 0},
    echo=settings.debug,
)

AsyncSessionLocal = async_sessionmaker(
    async_engine,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    """Ensure tables exist at startup.

    Development / staging (default):
        create_all is a safe no-op for tables that already exist, and creates
        any new table that was added since the last manual migration.  It is
        intentionally kept as a convenience for local development.

    Production (ENABLE_CREATE_ALL=false):
        Set this env var to skip create_all and rely exclusively on Alembic.
        Run ``uv run alembic upgrade head`` before starting the server.

    NOTE (D2-c baseline):
        Alembic has been initialised (revision 4b49004d01a6).  The DB has
        been stamped to ``head``.  Future schema changes should be made via
        ``alembic revision --autogenerate`` + ``alembic upgrade head``.
        See docs/deployment_docker.md §Alembic 迁移管理.
    """
    if not settings.enable_create_all:
        import logging
        logging.getLogger(__name__).info(
            "ENABLE_CREATE_ALL=false — skipping create_all; "
            "run 'alembic upgrade head' before first start."
        )
        return

    # Import all ORM models so Base.metadata is fully populated before create_all.
    from app.models import user             # noqa: F401
    from app.models import analysis_report  # noqa: F401
    from app.models import industry           # noqa: F401
    from app.models import industry_hot_stock # noqa: F401
    from app.models import watchlist_item     # noqa: F401

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ── Redis (optional — failure is non-fatal) ──────────────────────────────────

_redis_client: Redis | None = None


async def connect_redis() -> None:
    global _redis_client
    try:
        client = from_url(settings.redis_url, decode_responses=True)
        await client.ping()
        _redis_client = client
    except Exception as exc:
        # Redis is optional — log but don't block startup.
        import logging
        logging.getLogger(__name__).warning("Redis unavailable: %s", exc)


async def close_redis() -> None:
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None


def get_redis() -> Redis | None:
    return _redis_client
