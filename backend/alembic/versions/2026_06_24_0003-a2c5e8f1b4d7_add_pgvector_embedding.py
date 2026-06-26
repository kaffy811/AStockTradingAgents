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

log = logging.getLogger(__name__)

revision: str = "a2c5e8f1b4d7"
down_revision: Union[str, None] = "f1a4b7c9d2e5"
branch_labels = None
depends_on = None


def _pgvector_available() -> bool:
    """Return True if the connected DB has pgvector installed."""
    try:
        conn = op.get_bind()
        conn.execute(sa.text("SELECT 'vector'::regtype"))
        return True
    except Exception:
        return False


def upgrade() -> None:
    # ── 1. Enable pgvector extension (no-op if not installed) ──────────────
    try:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        log.info("pgvector extension enabled (or already present)")
    except Exception as exc:
        log.warning("pgvector extension unavailable — vector search disabled: %s", exc)

    # ── 2. Add embedding columns ────────────────────────────────────────────
    # Determine column type: vector(1536) if pgvector available, else TEXT fallback
    if _pgvector_available():
        from pgvector.sqlalchemy import Vector  # type: ignore[import]
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
    if _pgvector_available():
        try:
            op.execute("""
                CREATE INDEX IF NOT EXISTS ix_fdc_embedding_vector_hnsw
                ON financial_document_chunks
                USING hnsw (embedding_vector vector_cosine_ops)
                WITH (m = 16, ef_construction = 64)
            """)
            log.info("HNSW index created on embedding_vector")
        except Exception as exc:
            log.warning("HNSW index creation failed (non-fatal): %s", exc)


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
