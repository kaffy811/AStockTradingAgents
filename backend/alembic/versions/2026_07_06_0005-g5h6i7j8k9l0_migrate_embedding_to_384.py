"""migrate_embedding_to_384

Phase 6G-1: Change report_chunks.embedding from vector(1536) to vector(384).
Reason: 384-dim native models (BAAI/bge-small-zh-v1.5, intfloat/multilingual-e5-small)
are the recommended 0-cost local models. Silent pad/truncate removed.
This migration drops and re-adds the embedding column (PostgreSQL cannot ALTER vector dim).
All existing embeddings are cleared. Documents previously marked rag_status='embedded'
are reset to rag_status='chunked' so they will be re-embedded at the correct dimension.

Revision ID: g5h6i7j8k9l0
Revises: f4a5b6c7d8e9
Create Date: 2026-07-06
"""
import logging

from alembic import op
import sqlalchemy as sa

log = logging.getLogger(__name__)

revision = 'g5h6i7j8k9l0'
down_revision = 'f4a5b6c7d8e9'
branch_labels = None
depends_on = None

VECTOR_ALREADY_ENABLED = 'VECTOR_ALREADY_ENABLED'
VECTOR_EXTENSION_UNAVAILABLE = 'VECTOR_EXTENSION_UNAVAILABLE'
TEXT_FALLBACK_PRESERVED = 'TEXT_FALLBACK_PRESERVED'
VECTOR_384_SCHEMA_SELECTED = 'VECTOR_384_SCHEMA_SELECTED'


class Vector(sa.types.UserDefinedType):
    cache_ok = True

    def __init__(self, dimensions: int):
        self.dimensions = dimensions

    def get_col_spec(self, **kw) -> str:  # noqa: ANN003
        return f'vector({self.dimensions})'


def _database_has_vector(conn) -> bool:
    return bool(conn.scalar(sa.text(
        "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')"
    )))


def _embedding_column_exists(conn) -> bool:
    return any(column['name'] == 'embedding' for column in sa.inspect(conn).get_columns('report_chunks'))


def upgrade() -> None:
    conn = op.get_bind()
    vector_enabled = _database_has_vector(conn)
    log.info('vector_capability=%s', VECTOR_ALREADY_ENABLED if vector_enabled else VECTOR_EXTENSION_UNAVAILABLE)

    # Step 1: Drop HNSW index before changing a vector dimension.
    op.execute("DROP INDEX IF EXISTS ix_report_chunks_embedding")

    # Step 2/3: VECTOR dimensions are incompatible and intentionally reset.
    # TEXT fallback has no dimension change, so preserve its existing values.
    if vector_enabled:
        op.drop_column('report_chunks', 'embedding')
        op.add_column('report_chunks', sa.Column('embedding', Vector(384), nullable=True))
        log.info('vector_capability=%s', VECTOR_384_SCHEMA_SELECTED)
    else:
        if not _embedding_column_exists(conn):
            op.add_column('report_chunks', sa.Column('embedding', sa.Text(), nullable=True))
        log.info('vector_capability=%s', TEXT_FALLBACK_PRESERVED)

    # Step 4: Also drop embedding_model (stale from 1536-dim) and reset embed_error
    op.execute("UPDATE report_chunks SET embedding_model = NULL, embed_error = NULL")

    # Step 5: Recreate HNSW index only for the database vector path.
    if vector_enabled:
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_report_chunks_embedding "
            "ON report_chunks USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64)"
        )

    # Step 6: Reset rag_status — documents that were 'embedded' with 1536-dim
    # vectors must be re-embedded. Reset to 'chunked' so the embed step reruns.
    op.execute(
        "UPDATE report_documents SET rag_status = 'chunked' WHERE rag_status = 'embedded'"
    )
    op.execute(
        "UPDATE report_documents SET rag_error = NULL WHERE rag_status = 'chunked'"
    )


def downgrade() -> None:
    conn = op.get_bind()
    vector_enabled = _database_has_vector(conn)

    # Drop HNSW index on 384-dim column
    op.execute("DROP INDEX IF EXISTS ix_report_chunks_embedding")

    # VECTOR downgrade resets incompatible dimensions. TEXT remains TEXT and
    # retains its values because there is no schema conversion to perform.
    if vector_enabled:
        op.drop_column('report_chunks', 'embedding')
        op.add_column('report_chunks', sa.Column('embedding', Vector(1536), nullable=True))

    # Restore HNSW index for vector(1536)
    if vector_enabled:
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_report_chunks_embedding "
            "ON report_chunks USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64)"
        )

    # Note: downgrade cannot recover the original 1536-dim vectors (data is lost).
    # All chunk embeddings remain NULL after downgrade.
