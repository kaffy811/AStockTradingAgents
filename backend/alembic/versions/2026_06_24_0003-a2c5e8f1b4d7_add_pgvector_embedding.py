"""add pgvector embedding columns to financial_document_chunks

Revision ID: a2c5e8f1b4d7
Revises: f1a4b7c9d2e5
Create Date: 2026-06-24 00:03:00

Phase 2C: Embedding + pgvector upgrade.

Changes:
  1. CREATE EXTENSION IF NOT EXISTS vector  (graceful — no-op if unavailable)
  2. Add embedding_vector vector(1536)       to financial_document_chunks
  3. Add embedding_model  varchar(100)       to financial_document_chunks
  4. Add embedded_at      timestamptz        to financial_document_chunks
  5. Create HNSW index on embedding_vector   (skipped gracefully if pgvector absent)

Safety:
  - All new columns are nullable → zero downtime, no backfill required.
  - Old `embedding` TEXT column is NOT touched → existing tests unaffected.
  - If pgvector extension is unavailable the column type falls back to TEXT
    (so CI without pgvector still passes migrations); the application layer
    handles the fallback to keyword search at runtime.
"""
from __future__ import annotations

import logging
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.exc import DBAPIError

log = logging.getLogger(__name__)

revision: str = "a2c5e8f1b4d7"
down_revision: Union[str, None] = "f1a4b7c9d2e5"
branch_labels = None
depends_on = None


VECTOR_ALREADY_ENABLED = "VECTOR_ALREADY_ENABLED"
VECTOR_EXTENSION_AVAILABLE = "VECTOR_EXTENSION_AVAILABLE"
VECTOR_EXTENSION_UNAVAILABLE = "VECTOR_EXTENSION_UNAVAILABLE"
VECTOR_EXTENSION_PERMISSION_DENIED = "VECTOR_EXTENSION_PERMISSION_DENIED"
VECTOR_EXTENSION_CREATE_FAILED_RECOVERED = "VECTOR_EXTENSION_CREATE_FAILED_RECOVERED"
TEXT_FALLBACK_SELECTED = "TEXT_FALLBACK_SELECTED"


class Vector(sa.types.UserDefinedType):
    """Render the database-owned pgvector type without a Python adapter."""

    cache_ok = True

    def __init__(self, dimensions: int):
        self.dimensions = dimensions

    def get_col_spec(self, **kw) -> str:  # noqa: ANN003
        return f"vector({self.dimensions})"


def _extension_enabled(conn) -> bool:
    return bool(conn.scalar(sa.text(
        "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')"
    )))


def _extension_available(conn) -> bool:
    return bool(conn.scalar(sa.text(
        "SELECT EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector')"
    )))


def _sqlstate(exc: DBAPIError) -> str | None:
    original = getattr(exc, "orig", None)
    return getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)


def _enable_vector_if_safe(conn) -> tuple[bool, str]:
    """Return database capability and a non-sensitive reason code.

    Failed extension DDL is rolled back to a savepoint, leaving Alembic's outer
    migration transaction usable for the TEXT fallback.
    """
    if _extension_enabled(conn):
        return True, VECTOR_ALREADY_ENABLED
    if not _extension_available(conn):
        return False, VECTOR_EXTENSION_UNAVAILABLE

    log.info("vector_capability=%s", VECTOR_EXTENSION_AVAILABLE)
    try:
        with conn.begin_nested():
            conn.execute(sa.text("CREATE EXTENSION vector"))
    except DBAPIError as exc:
        reason = (
            VECTOR_EXTENSION_PERMISSION_DENIED
            if _sqlstate(exc) == "42501"
            else VECTOR_EXTENSION_CREATE_FAILED_RECOVERED
        )
        return False, reason

    return _extension_enabled(conn), VECTOR_ALREADY_ENABLED


def upgrade() -> None:
    # ── 1. Decide database capability without poisoning the outer transaction.
    conn = op.get_bind()
    vector_enabled, capability_reason = _enable_vector_if_safe(conn)
    log.info("vector_capability=%s", capability_reason)
    if not vector_enabled:
        log.info("vector_capability=%s", TEXT_FALLBACK_SELECTED)

    # ── 2. Add embedding columns ────────────────────────────────────────────
    # Determine column type: vector(1536) if pgvector available, else TEXT fallback
    if vector_enabled:
        embedding_col = sa.Column(
            "embedding_vector", Vector(1536), nullable=True,
            comment="Query embedding from text-embedding-3-small or compatible model"
        )
    else:
        log.warning(
            "pgvector not available — embedding_vector added as TEXT placeholder"
        )
        embedding_col = sa.Column(
            "embedding_vector", sa.Text, nullable=True,
            comment="Placeholder; upgrade to vector(1536) once pgvector is installed"
        )

    op.add_column("financial_document_chunks", embedding_col)

    op.add_column(
        "financial_document_chunks",
        sa.Column(
            "embedding_model", sa.String(100), nullable=True,
            comment="Model name used to create embedding, e.g. text-embedding-3-small"
        ),
    )
    op.add_column(
        "financial_document_chunks",
        sa.Column(
            "embedded_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when embedding was last computed",
        ),
    )

    # ── 3. Create HNSW vector index (graceful skip) ─────────────────────────
    if vector_enabled:
        try:
            with conn.begin_nested():
                conn.execute(sa.text("""
                    CREATE INDEX IF NOT EXISTS ix_fdc_embedding_vector_hnsw
                    ON financial_document_chunks
                    USING hnsw (embedding_vector vector_cosine_ops)
                    WITH (m = 16, ef_construction = 64)
                """))
            log.info("HNSW index created on embedding_vector")
        except DBAPIError:
            log.warning("vector_index=CREATE_FAILED_RECOVERED")


def downgrade() -> None:
    try:
        op.drop_index(
            "ix_fdc_embedding_vector_hnsw",
            table_name="financial_document_chunks",
        )
    except Exception:
        pass
    op.drop_column("financial_document_chunks", "embedded_at")
    op.drop_column("financial_document_chunks", "embedding_model")
    op.drop_column("financial_document_chunks", "embedding_vector")
