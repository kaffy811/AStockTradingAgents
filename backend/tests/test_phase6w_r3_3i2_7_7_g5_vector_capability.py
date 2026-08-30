"""Database capability and data contracts for g5h6i7j8k9l0."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
import subprocess
import sys

import asyncpg
import pytest


BACKEND = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND / 'alembic/versions/2026_07_06_0005-g5h6i7j8k9l0_migrate_embedding_to_384.py'


def test_migration_graph_has_no_other_unsafe_vector_imports() -> None:
    versions = BACKEND / 'alembic/versions'
    risky = []
    for path in versions.glob('*.py'):
        source = path.read_text()
        if 'from pgvector' in source or 'import pgvector' in source:
            risky.append(path.name)
    assert risky == []


def test_g5_uses_catalog_and_preserves_text_contract() -> None:
    source = MIGRATION.read_text()
    assert 'pg_extension' in source
    assert 'pgvector.sqlalchemy' not in source
    assert 'TEXT_FALLBACK_PRESERVED' in source
    assert 'Vector(384)' in source and 'Vector(1536)' in source
    assert 'if vector_enabled:' in source


async def _reset(url: str) -> None:
    conn = await asyncpg.connect(url.replace('postgresql+asyncpg://', 'postgresql://'))
    try:
        await conn.execute('DROP SCHEMA public CASCADE; CREATE SCHEMA public')
    finally:
        await conn.close()


def _alembic(url: str, *args: str, backend: Path = BACKEND) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, '-m', 'alembic', *args], cwd=backend,
        env={**os.environ, 'DATABASE_URL': url, 'SECRET_KEY': 'isolated-g5-capability-key'},
        text=True, capture_output=True, check=True,
    )


def _prepare_f4(url: str) -> None:
    overlay = os.getenv('R33I_PORTABLE_OVERLAY_BACKEND')
    if not overlay:
        pytest.fail('R33I_PORTABLE_OVERLAY_BACKEND must point to the audited combined overlay')
    _alembic(url, 'upgrade', 'f4a5b6c7d8e9', backend=Path(overlay))


async def _seed(url: str, expect_vector: bool) -> int:
    conn = await asyncpg.connect(url.replace('postgresql+asyncpg://', 'postgresql://'))
    try:
        report_id = await conn.fetchval("""INSERT INTO report_documents
            (ts_code, report_type, title, source_url, rag_status)
            VALUES ('G5.TEST','annual','g5 probe','https://example.invalid','embedded') RETURNING id""")
        has_embedding = await conn.fetchval("""SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name='report_chunks' AND column_name='embedding')""")
        if has_embedding:
            embedding_sql = 'NULL' if expect_vector else "'preserve-text-embedding'"
            await conn.execute(f"""INSERT INTO report_chunks
                (report_id, ts_code, symbol, chunk_index, content, content_hash, embedding)
                VALUES ($1,'G5.TEST','G5',0,'row-preserved','g5-capability-probe',{embedding_sql})""", report_id)
        else:
            await conn.execute("""INSERT INTO report_chunks
                (report_id, ts_code, symbol, chunk_index, content, content_hash)
                VALUES ($1,'G5.TEST','G5',0,'row-preserved','g5-capability-probe')""", report_id)
        return report_id
    finally:
        await conn.close()


async def _verify(
    url: str, report_id: int, expected_type: str, expected_index: bool,
    expect_text_preserved: bool,
) -> None:
    conn = await asyncpg.connect(url.replace('postgresql+asyncpg://', 'postgresql://'))
    try:
        assert await conn.fetchval('SELECT 1') == 1
        actual_type = await conn.fetchval("""SELECT format_type(a.atttypid,a.atttypmod)
            FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
            WHERE c.relname='report_chunks' AND a.attname='embedding'""")
        assert actual_type == expected_type
        assert bool(await conn.fetchval("""SELECT EXISTS (
            SELECT 1 FROM pg_indexes WHERE indexname='ix_report_chunks_embedding')""")) is expected_index
        row = await conn.fetchrow(
            'SELECT content, embedding::text AS embedding FROM report_chunks WHERE report_id=$1', report_id
        )
        assert row and row['content'] == 'row-preserved'
        if expect_text_preserved:
            assert row['embedding'] == 'preserve-text-embedding'
        else:
            assert row['embedding'] is None
        assert await conn.fetchval('SELECT rag_status FROM report_documents WHERE id=$1', report_id) == 'chunked'
        await conn.execute("""INSERT INTO report_chunks
            (report_id, ts_code, symbol, chunk_index, content, content_hash)
            VALUES ($1,'G5.TEST','G5',1,'connection-usable','g5-post-upgrade-probe')""", report_id)
    finally:
        await conn.close()


@pytest.mark.parametrize(
    'env_name,expected_type,expected_index,expect_text_preserved',
    [
        ('R33I_G5_STANDARD_URL', 'text', False, True),
        ('R33I_G5_PERMISSION_URL', 'text', False, True),
        ('R33I_G5_ENABLED_URL', 'vector(384)', True, False),
        ('R33I_G5_AVAILABLE_URL', 'text', False, False),
    ],
)
def test_g5_capability_and_data_paths(
    env_name: str, expected_type: str, expected_index: bool, expect_text_preserved: bool
) -> None:
    url = os.getenv(env_name)
    if not url:
        pytest.skip(f'{env_name} requires a disposable PostgreSQL database')
    asyncio.run(_reset(url))
    _prepare_f4(url)
    if env_name == 'R33I_G5_AVAILABLE_URL':
        async def disable_after_parent() -> None:
            conn = await asyncpg.connect(url.replace('postgresql+asyncpg://', 'postgresql://'))
            try:
                await conn.execute('DROP EXTENSION IF EXISTS vector CASCADE')
            finally:
                await conn.close()
        asyncio.run(disable_after_parent())
    report_id = asyncio.run(_seed(url, expected_type.startswith('vector')))
    _alembic(url, 'upgrade', 'g5h6i7j8k9l0')
    asyncio.run(_verify(url, report_id, expected_type, expected_index, expect_text_preserved))
    _alembic(url, 'upgrade', 'g5h6i7j8k9l0')
