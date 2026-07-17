from collections.abc import AsyncGenerator
import logging

from redis.asyncio import Redis, from_url
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool

from app.core.config import settings

log = logging.getLogger(__name__)

# ── SQLAlchemy ────────────────────────────────────────────────────────────────
# DB_CONNECTION_MODE explicitly controls local pooling policy:
# - transaction_pooler: Supabase/PgBouncer transaction pooling; no prepared
#   statements, short transactions, and either NullPool or a very small queue
#   pool. Never use 5+10 burst connections here.
# - session_pooler/direct: bounded AsyncAdaptedQueuePool with pre-ping/recycle.

_database_url = make_url(settings.database_url)
_is_postgres = _database_url.drivername.startswith("postgresql")
_connection_mode = (settings.database_connection_mode or "transaction_pooler").strip().lower()
_transaction_strategy = (settings.database_transaction_pool_strategy or "small_queue_pool").strip().lower()
if not _is_postgres:
    _poolclass = NullPool
elif _connection_mode == "transaction_pooler" and _transaction_strategy == "null_pool":
    _poolclass = NullPool
else:
    _poolclass = AsyncAdaptedQueuePool

_engine_kwargs = {
    "poolclass": _poolclass,
    "connect_args": {
        "statement_cache_size": 0,
        "command_timeout": settings.database_command_timeout_seconds,
    },
    "echo": settings.debug,
    "pool_pre_ping": settings.database_pool_pre_ping,
}
if _poolclass is AsyncAdaptedQueuePool:
    pool_size = settings.database_pool_size
    max_overflow = settings.database_max_overflow
    if _connection_mode in {"direct", "session_pooler"}:
        pool_size = settings.database_direct_pool_size
        max_overflow = settings.database_direct_max_overflow
    _engine_kwargs.update(
        {
            "pool_size": pool_size,
            "max_overflow": max_overflow,
            "pool_recycle": settings.database_pool_recycle_seconds,
            "pool_timeout": settings.database_pool_timeout_seconds,
        }
    )

async_engine = create_async_engine(settings.database_url, **_engine_kwargs)

log.info(
    "database engine configured mode=%s host_class=%s port=%s pool=%s pool_size=%s max_overflow=%s pool_timeout=%s command_timeout=%s",
    _connection_mode,
    "supabase_pooler" if "pooler.supabase.com" in (_database_url.host or "") else "database_host",
    _database_url.port,
    _poolclass.__name__,
    _engine_kwargs.get("pool_size"),
    _engine_kwargs.get("max_overflow"),
    _engine_kwargs.get("pool_timeout"),
    settings.database_command_timeout_seconds,
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
    from app.models import company_v2_report_rag  # noqa: F401
    from app.models import company_v2_financial_fusion_job  # noqa: F401
    from app.models import company_v2_financial_fusion_worker_observation  # noqa: F401

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
