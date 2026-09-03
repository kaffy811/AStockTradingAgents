"""Transaction-safe database capability contracts for revision a2c5e8f1b4d7."""
from __future__ import annotations

import asyncio
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import asyncpg
import pytest


BACKEND = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND / "alembic/versions/2026_06_24_0003-a2c5e8f1b4d7_add_pgvector_embedding.py"


def _load_migration():
    spec = importlib.util.spec_from_file_location("vector_fallback_migration", MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_capability_detection_uses_database_catalogs_not_python_package() -> None:
    source = MIGRATION.read_text()
    assert "pg_extension" in source
    assert "pg_available_extensions" in source
    assert "begin_nested" in source
    assert "pgvector.sqlalchemy" not in source
    assert "SELECT 'vector'::regtype" not in source


def test_reason_codes_are_stable_and_non_sensitive() -> None:
    module = _load_migration()
    assert {
        module.VECTOR_ALREADY_ENABLED,
        module.VECTOR_EXTENSION_AVAILABLE,
        module.VECTOR_EXTENSION_UNAVAILABLE,
        module.VECTOR_EXTENSION_PERMISSION_DENIED,
        module.VECTOR_EXTENSION_CREATE_FAILED_RECOVERED,
        module.TEXT_FALLBACK_SELECTED,
    } == {
        "VECTOR_ALREADY_ENABLED",
        "VECTOR_EXTENSION_AVAILABLE",
        "VECTOR_EXTENSION_UNAVAILABLE",
        "VECTOR_EXTENSION_PERMISSION_DENIED",
        "VECTOR_EXTENSION_CREATE_FAILED_RECOVERED",
        "TEXT_FALLBACK_SELECTED",
    }


async def _reset(url: str) -> None:
    conn = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
    finally:
        await conn.close()


def _alembic(
    url: str, *args: str, backend: Path = BACKEND
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=backend,
        env={**os.environ, "DATABASE_URL": url, "SECRET_KEY": "isolated-vector-fallback-key"},
        text=True,
        capture_output=True,
        check=True,
    )


def _prepare_parent(url: str) -> None:
    fixture_backend = os.getenv("R33I_BOOTSTRAP_FIXTURE_BACKEND")
    if not fixture_backend:
        pytest.fail("R33I_BOOTSTRAP_FIXTURE_BACKEND must point to the versioned bootstrap worktree backend")
    _alembic(url, "upgrade", "f1a4b7c9d2e5", backend=Path(fixture_backend))


async def _verify(url: str, expected_type: str, expected_index: bool) -> None:
    conn = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        assert await conn.fetchval("SELECT 1") == 1
        actual_type = await conn.fetchval("""SELECT udt_name FROM information_schema.columns
            WHERE table_name='financial_document_chunks' AND column_name='embedding_vector'""")
        assert actual_type == expected_type
        has_index = bool(await conn.fetchval("""SELECT EXISTS (
            SELECT 1 FROM pg_indexes WHERE indexname='ix_fdc_embedding_vector_hnsw')"""))
        assert has_index is expected_index
        document_id = await conn.fetchval("""INSERT INTO financial_documents
            (market, symbol, title, source_type, raw_text)
            VALUES ('CN','TEST','transaction probe','test','probe') RETURNING id""")
        await conn.execute("""INSERT INTO financial_document_chunks
            (document_id, chunk_index, chunk_text)
            VALUES ($1, 0, 'transaction usable')""", document_id)
        assert await conn.fetchval(
            "SELECT chunk_text FROM financial_document_chunks WHERE document_id=$1", document_id
        ) == "transaction usable"
    finally:
        await conn.close()


@pytest.mark.parametrize(
    "env_name,expected_type,expected_index",
    [
        ("R33I_VECTOR_STANDARD_URL", "text", False),
        ("R33I_VECTOR_PERMISSION_URL", "text", False),
        ("R33I_VECTOR_ENABLED_URL", "vector", True),
        ("R33I_VECTOR_AVAILABLE_URL", "vector", True),
    ],
)
def test_a2_migration_paths_are_transaction_safe(
    env_name: str, expected_type: str, expected_index: bool
) -> None:
    url = os.getenv(env_name)
    if not url:
        pytest.skip(f"{env_name} requires a disposable PostgreSQL database")
    asyncio.run(_reset(url))
    if env_name == "R33I_VECTOR_ENABLED_URL":
        async def enable() -> None:
            conn = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"))
            try:
                await conn.execute("CREATE EXTENSION vector")
            finally:
                await conn.close()
        asyncio.run(enable())
    _prepare_parent(url)
    _alembic(url, "upgrade", "a2c5e8f1b4d7")
    asyncio.run(_verify(url, expected_type, expected_index))
    _alembic(url, "upgrade", "a2c5e8f1b4d7")
