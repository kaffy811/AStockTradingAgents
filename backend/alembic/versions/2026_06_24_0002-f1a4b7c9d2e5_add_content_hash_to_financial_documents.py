"""add content_hash to financial_documents

Revision ID: f1a4b7c9d2e5
Revises: e8f3a2c7d4b1
Create Date: 2026-06-24 00:02:00

Phase 2B: adds content_hash (SHA-256 hex, 64 chars) to financial_documents for
deduplication.  The column is nullable so existing rows keep working without
a backfill.  A UNIQUE constraint prevents duplicate documents from being
inserted via ingest_financial_document().
"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1a4b7c9d2e5"
down_revision: Union[str, None] = "e8f3a2c7d4b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "financial_documents",
        sa.Column(
            "content_hash",
            sa.String(64),
            nullable=True,
            unique=True,
            comment="SHA-256 hex of title+source+published_at+raw_text[:5000]; used for dedup",
        ),
    )
    op.create_index(
        "ix_financial_documents_content_hash",
        "financial_documents",
        ["content_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_financial_documents_content_hash", table_name="financial_documents")
    op.drop_column("financial_documents", "content_hash")
