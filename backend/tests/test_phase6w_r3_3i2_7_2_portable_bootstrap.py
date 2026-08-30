"""Contracts for the versioned pre-Alembic legacy schema bootstrap."""
from __future__ import annotations

import ast
import asyncio
import os
from pathlib import Path
import subprocess
import sys

import asyncpg
import pytest


BACKEND = Path(__file__).resolve().parents[1]
VERSIONS = BACKEND / "alembic" / "versions"
BOOTSTRAP = VERSIONS / "2026_05_29_0001-r3e4f5g6h7i8_bootstrap_legacy_schema.py"
BASELINE = VERSIONS / "2026_05_30_1612-4b49004d01a6_baseline_existing_schema.py"

LEGACY_TABLES = {
    "app_users",
    "analysis_reports",
    "watchlist_items",
    "industry_master",
    "stock_industry_map",
    "industry_hot_stock_snapshot",
    "company_v2_report_rag_documents",
    "company_v2_report_rag_chunks",
}


def _literal_assignment(path: Path, name: str):
    tree = ast.parse(path.read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return ast.literal_eval(node.value)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found in {path.name}")


def test_bootstrap_is_root_and_existing_schema_baseline_follows_it() -> None:
    assert _literal_assignment(BOOTSTRAP, "revision") == "r3e4f5g6h7i8"
    assert _literal_assignment(BOOTSTRAP, "down_revision") is None
    assert _literal_assignment(BASELINE, "down_revision") == "r3e4f5g6h7i8"


def test_bootstrap_declares_every_required_legacy_table_before_analysis_alter() -> None:
    source = BOOTSTRAP.read_text()
    assert {name for name in LEGACY_TABLES if f'_missing("{name}")' in source} == LEGACY_TABLES
    analysis_alter = (VERSIONS / "2026_06_04_0001-3a2f8b4c1d9e_add_stock_name_to_analysis_reports.py").read_text()
    assert "op.add_column" in analysis_alter and "analysis_reports" in analysis_alter


def test_bootstrap_preserves_existing_tables_and_downgrade_data() -> None:
    source = BOOTSTRAP.read_text()
    assert "sa.inspect(op.get_bind()).has_table" in source
    downgrade = source.split("def downgrade()", 1)[1]
    assert "drop_table" not in downgrade
    assert "truncate" not in source.lower()
    assert "delete from" not in source.lower()


def test_bootstrap_contains_no_data_inserts_or_financial_fixtures() -> None:
    source = BOOTSTRAP.read_text().lower()
    for forbidden in ("bulk_insert", "insert into", "600519", "贵州茅台", "1708.99", "50.46"):
        assert forbidden not in source


def test_bootstrap_defines_required_keys_constraints_and_indexes() -> None:
    source = BOOTSTRAP.read_text()
    required = (
        'sa.ForeignKey("app_users.id", ondelete="CASCADE")',
        'sa.ForeignKey("company_v2_report_rag_documents.id", ondelete="CASCADE")',
        'name="uq_watchlist_user_market_symbol"',
        'name="uq_industry_master_mcs"',
        'name="uq_stock_industry_mscs"',
        'name="uq_hot_stock_mid_tsv"',
        '"idx_reports_user_created"',
        '"ix_company_v2_report_rag_documents_report_id"',
    )
    for contract in required:
        assert contract in source


def test_bootstrap_does_not_modify_vector_or_runtime_dependencies() -> None:
    source = BOOTSTRAP.read_text().lower()
    assert "vector" not in source
    assert "pgvector" not in source


async def _reset_schema(url: str) -> None:
    conn = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
    finally:
        await conn.close()


def _alembic(url: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "DATABASE_URL": url, "SECRET_KEY": "isolated-bootstrap-contract-key"}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )


@pytest.mark.parametrize("env_name", ["R33I_BOOTSTRAP_STANDARD_URL", "R33I_BOOTSTRAP_VECTOR_URL"])
def test_empty_database_reaches_head_and_repeat_is_noop(env_name: str) -> None:
    url = os.getenv(env_name)
    if not url:
        pytest.skip(f"{env_name} requires a disposable PostgreSQL database")
    asyncio.run(_reset_schema(url))
    _alembic(url, "upgrade", "head")
    _alembic(url, "upgrade", "head")
    current = _alembic(url, "current").stdout
    heads = _alembic(url, "heads").stdout
    assert "q5r6s7t8u9v0 (head)" in current
    assert "q5r6s7t8u9v0 (head)" in heads


def test_versioned_legacy_fixture_preserves_existing_data() -> None:
    url = os.getenv("R33I_BOOTSTRAP_EXISTING_URL")
    if not url:
        pytest.skip("R33I_BOOTSTRAP_EXISTING_URL requires a disposable PostgreSQL database")

    async def exercise() -> None:
        await _reset_schema(url)
        _alembic(url, "upgrade", "r3e4f5g6h7i8")
        conn = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"))
        try:
            await conn.execute(
                """INSERT INTO app_users
                (id, username, email, hashed_password, is_active)
                VALUES ('00000000-0000-0000-0000-000000000001',
                        'bootstrap-sentinel', 'bootstrap-sentinel@example.invalid',
                        'not-a-real-password-hash', true)"""
            )
        finally:
            await conn.close()
        _alembic(url, "upgrade", "head")
        conn = await asyncpg.connect(url.replace("postgresql+asyncpg://", "postgresql://"))
        try:
            assert await conn.fetchval(
                "SELECT username FROM app_users WHERE id='00000000-0000-0000-0000-000000000001'"
            ) == "bootstrap-sentinel"
        finally:
            await conn.close()

    asyncio.run(exercise())
