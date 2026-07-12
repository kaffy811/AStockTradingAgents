"""Phase 6T-J1: align company_v2_report_rag_documents with ORM model and
support multi-generation persistence.

The RAG tables were originally created via Base.metadata.create_all before the
model gained generation/stale columns, so the live table lacks them. This
migration:
  1. adds the missing columns (idempotent);
  2. drops the UNIQUE index on report_id (one row per generation is required
     to preserve superseded generations for audit);
  3. adds a UNIQUE constraint on (report_id, index_generation).

Revision ID: i7j8k9l0m1n2
Revises: h6i7j8k9l0m1
"""
from __future__ import annotations

from alembic import op

revision = "i7j8k9l0m1n2"
down_revision = "h6i7j8k9l0m1"
branch_labels = None
depends_on = None

_ADD_COLUMNS = [
    ("active_index", "INTEGER NOT NULL DEFAULT 1"),
    ("supersedes_rag_document_id", "INTEGER"),
    ("stale_reason", "TEXT"),
    ("indexed_at", "TIMESTAMP WITHOUT TIME ZONE"),
    ("deleted_at", "TIMESTAMP WITHOUT TIME ZONE"),
    ("index_generation", "INTEGER NOT NULL DEFAULT 1"),
]


def upgrade() -> None:
    for name, ddl in _ADD_COLUMNS:
        op.execute(
            f"ALTER TABLE company_v2_report_rag_documents ADD COLUMN IF NOT EXISTS {name} {ddl}"
        )
    # report_id must allow multiple generation rows; keep a plain index.
    op.execute("DROP INDEX IF EXISTS ix_company_v2_report_rag_documents_report_id")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_company_v2_report_rag_documents_report_id "
        "ON company_v2_report_rag_documents (report_id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_company_v2_rag_doc_generation "
        "ON company_v2_report_rag_documents (report_id, index_generation)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_company_v2_rag_doc_generation")
    op.execute("DROP INDEX IF EXISTS ix_company_v2_report_rag_documents_report_id")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_company_v2_report_rag_documents_report_id "
        "ON company_v2_report_rag_documents (report_id)"
    )
    for name, _ in _ADD_COLUMNS:
        op.execute(f"ALTER TABLE company_v2_report_rag_documents DROP COLUMN IF EXISTS {name}")
