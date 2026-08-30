"""Database capability contracts for report-chunk revision f4a5b6c7d8e9."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
import subprocess
import sys

import asyncpg
import pytest


BACKEND = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND / 'alembic/versions/2026_07_06_0004-f4a5b6c7d8e9_add_report_chunks.py'


def test_f4_uses_database_extension_state_not_python_importability() -> None:
    source = MIGRATION.read_text()
    assert 'pg_extension' in source
    assert 'pgvector.sqlalchemy' not in source
    assert 'ImportError' not in source
    assert "if vector_enabled:" in source


def test_f4_preserves_schema_contract_and_reason_codes() -> None:
    source = MIGRATION.read_text()
    for value in (
        'VECTOR_ALREADY_ENABLED',
        'VECTOR_EXTENSION_UNAVAILABLE',
        'TEXT_FALLBACK_SELECTED',
        'VECTOR_SCHEMA_SELECTED',
        'Vector(1536)',
        'ix_report_chunks_embedding',
        'vector_cosine_ops',
        'm = 16, ef_construction = 64',
    ):
        assert value in source


async def _reset(url: str) -> None:
    conn = await asyncpg.connect(url.replace('postgresql+asyncpg://', 'postgresql://'))
    try:
        await conn.execute('DROP SCHEMA public CASCADE; CREATE SCHEMA public')
    finally:
        await conn.close()


def _alembic(url: str, *args: str, backend: Path = BACKEND) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, '-m', 'alembic', *args],
        cwd=backend,
        env={**os.environ, 'DATABASE_URL': url, 'SECRET_KEY': 'isolated-f4-capability-key'},
        text=True,
        capture_output=True,
        check=True,
    )


def _prepare_parent(url: str) -> None:
    overlay = os.getenv('R33I_PORTABLE_OVERLAY_BACKEND')
    if not overlay:
        pytest.fail('R33I_PORTABLE_OVERLAY_BACKEND must point to the audited bootstrap overlay')
    _alembic(url, 'upgrade', 'e3f4a5b6c7d8', backend=Path(overlay))


async def _set_extension(url: str, enabled: bool) -> None:
    conn = await asyncpg.connect(url.replace('postgresql+asyncpg://', 'postgresql://'))
    try:
        if enabled:
            await conn.execute('CREATE EXTENSION IF NOT EXISTS vector')
        else:
            await conn.execute('DROP EXTENSION IF EXISTS vector CASCADE')
    finally:
        await conn.close()


async def _verify(url: str, expected_type: str, expected_index: bool) -> None:
    conn = await asyncpg.connect(url.replace('postgresql+asyncpg://', 'postgresql://'))
    try:
        assert await conn.fetchval('SELECT 1') == 1
        assert await conn.fetchval("""SELECT udt_name FROM information_schema.columns
            WHERE table_name='report_chunks' AND column_name='embedding'""") == expected_type
        assert bool(await conn.fetchval("""SELECT EXISTS (
            SELECT 1 FROM pg_indexes WHERE indexname='ix_report_chunks_embedding')""")) is expected_index
        report_id = await conn.fetchval("""INSERT INTO report_documents
            (ts_code, report_type, title, source_url)
            VALUES ('TEST.CN','annual','schema probe','https://example.invalid')
            RETURNING id""")
        await conn.execute("""INSERT INTO report_chunks
            (report_id, ts_code, symbol, chunk_index, content, content_hash)
            VALUES ($1,'TEST.CN','TEST',0,'connection usable','f4-capability-probe')""", report_id)
        assert await conn.fetchval(
            "SELECT content FROM report_chunks WHERE report_id=$1", report_id
        ) == 'connection usable'
    finally:
        await conn.close()


@pytest.mark.parametrize(
    'env_name,extension_enabled,expected_type,expected_index',
    [
        ('R33I_F4_STANDARD_URL', False, 'text', False),
        ('R33I_F4_PERMISSION_URL', False, 'text', False),
        ('R33I_F4_ENABLED_URL', True, 'vector', True),
        ('R33I_F4_AVAILABLE_URL', False, 'text', False),
    ],
)
def test_f4_database_capability_paths(
    env_name: str, extension_enabled: bool, expected_type: str, expected_index: bool
) -> None:
    url = os.getenv(env_name)
    if not url:
        pytest.skip(f'{env_name} requires a disposable PostgreSQL database')
    asyncio.run(_reset(url))
    _prepare_parent(url)
    asyncio.run(_set_extension(url, extension_enabled))
    _alembic(url, 'upgrade', 'f4a5b6c7d8e9')
    asyncio.run(_verify(url, expected_type, expected_index))
    _alembic(url, 'upgrade', 'f4a5b6c7d8e9')
