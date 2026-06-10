"""Alembic migration environment.

Design decisions
----------------
* DATABASE_URL is read from ``app.core.config.settings`` — never stored in
  alembic.ini — so the same ini file works across environments.
* All ORM models are imported via ``import app.models`` which triggers the
  module-level ``__init__.py`` imports; this guarantees that every table is
  registered in ``Base.metadata`` before autogenerate inspects it.
* The engine is configured with ``NullPool`` and ``statement_cache_size=0``
  for compatibility with Supabase Transaction Pooler (PgBouncer transaction
  mode), exactly mirroring the app's own engine in database.py.
* The async path uses ``async_engine_from_config`` + ``run_sync`` so that
  asyncpg (the driver) works within Alembic's synchronous migration runner.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# ── App imports ────────────────────────────────────────────────────────────────
# These must be importable; run alembic from the backend/ directory
# (or ensure backend/ is on sys.path via prepend_sys_path in alembic.ini).
from app.core.config import settings
from app.core.database import Base
import app.models  # noqa: F401 — side-effect: populates Base.metadata

# ── Alembic Config object ──────────────────────────────────────────────────────
config = context.config

# Interpret the config file's logging section.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for --autogenerate comparisons.
target_metadata = Base.metadata


# ── URL helper ─────────────────────────────────────────────────────────────────

def get_url() -> str:
    """Return the DATABASE_URL from app settings.

    Falls back to the ini-file placeholder only if settings import fails,
    which should never happen in a properly configured environment.
    """
    return settings.database_url


# ── Offline mode ───────────────────────────────────────────────────────────────
# Generates SQL without connecting to the database.
# Useful for generating migration scripts on machines without DB access.

def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online mode ────────────────────────────────────────────────────────────────
# Connects to the database and applies migrations in a real transaction.

def do_run_migrations(connection) -> None:
    """Synchronous callback executed inside run_sync()."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine, open a connection, run migrations."""
    # Build config dict from the ini [alembic] section.
    configuration = config.get_section(config.config_ini_section, {})

    # Override the placeholder URL with the real one from settings.
    configuration["sqlalchemy.url"] = get_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        # NullPool: no local connection pooling — Supabase PgBouncer handles it.
        poolclass=pool.NullPool,
        # statement_cache_size=0: prevents asyncpg prepared-statement conflicts
        # across PgBouncer's transaction-mode connection rotation.
        connect_args={"statement_cache_size": 0},
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


# ── Entry point ────────────────────────────────────────────────────────────────

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
