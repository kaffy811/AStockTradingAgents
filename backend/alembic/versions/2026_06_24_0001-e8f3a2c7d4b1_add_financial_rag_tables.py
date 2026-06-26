"""add financial_documents and financial_document_chunks tables

Revision ID: e8f3a2c7d4b1
Revises: d7e3a9b5c2f8
Create Date: 2026-06-24 00:01:00

Phase 2A: Financial Knowledge Base RAG tables.

financial_documents  — one row per source document (annual report, research note, etc.)
financial_document_chunks — chunked text slices used for retrieval.

No pgvector dependency in this migration.  The embedding column is added
as a nullable TEXT placeholder so the schema can be upgraded to
vector(1536) later (via ALTER COLUMN) without a re-migration.
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8f3a2c7d4b1"
down_revision: Union[str, None] = "d7e3a9b5c2f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── financial_documents ───────────────────────────────────────────────────
    op.create_table(
        "financial_documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("symbol",      sa.String(20),  nullable=True),
        sa.Column("market",      sa.String(10),  nullable=True),
        sa.Column("title",       sa.Text,        nullable=False),
        sa.Column("source_type", sa.String(50),  nullable=False,
                  comment="annual_report | quarterly_report | announcement | research_report | regulation | other"),
        sa.Column("source",      sa.String(100), nullable=True,
                  comment="e.g. SEC, HKEX, Bloomberg, internal"),
        sa.Column("published_at", sa.Date,        nullable=True),
        sa.Column("url",         sa.Text,         nullable=True),
        sa.Column("raw_text",    sa.Text,         nullable=True,
                  comment="Full source text (not sent to LLM directly; chunked)"),
        sa.Column("metadata",    JSONB,           nullable=True,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at",  sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # Indexes for fast filtering
    op.create_index("ix_financial_documents_symbol",  "financial_documents", ["symbol"])
    op.create_index("ix_financial_documents_market",  "financial_documents", ["market"])
    op.create_index("ix_financial_documents_source_type",
                    "financial_documents", ["source_type"])
    op.create_index("ix_financial_documents_published_at",
                    "financial_documents", ["published_at"])

    # ── financial_document_chunks ─────────────────────────────────────────────
    op.create_table(
        "financial_document_chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", UUID(as_uuid=True), nullable=False,
                  comment="FK → financial_documents.id"),
        sa.Column("symbol",      sa.String(20),  nullable=True),
        sa.Column("market",      sa.String(10),  nullable=True),
        sa.Column("chunk_index", sa.Integer,     nullable=False, default=0),
        sa.Column("chunk_text",  sa.Text,        nullable=False,
                  comment="500-1000 Chinese chars or 800-1500 English tokens"),
        # Placeholder for future pgvector upgrade.
        # ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector
        # after installing pgvector.
        sa.Column("embedding",   sa.Text,        nullable=True,
                  comment="Reserved for pgvector; nullable until extension installed"),
        sa.Column("metadata",    JSONB,           nullable=True,
                  server_default=sa.text("'{}'::jsonb"),
                  comment="page, section, language, etc."),
        sa.Column("created_at",  sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        # FK (no cascade delete to allow orphaned chunks cleanup separately)
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["financial_documents.id"],
            ondelete="CASCADE",
        ),
    )

    op.create_index("ix_fdc_document_id",  "financial_document_chunks", ["document_id"])
    op.create_index("ix_fdc_symbol",       "financial_document_chunks", ["symbol"])
    op.create_index("ix_fdc_market",       "financial_document_chunks", ["market"])
    op.create_index("ix_fdc_chunk_index",  "financial_document_chunks", ["chunk_index"])


def downgrade() -> None:
    op.drop_table("financial_document_chunks")
    op.drop_table("financial_documents")
