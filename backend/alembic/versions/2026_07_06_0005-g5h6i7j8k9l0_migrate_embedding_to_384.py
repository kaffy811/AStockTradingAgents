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
from alembic import op
import sqlalchemy as sa

revision = 'g5h6i7j8k9l0'
down_revision = 'f4a5b6c7d8e9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: Drop HNSW index (required before changing column type)
    op.execute("DROP INDEX IF EXISTS ix_report_chunks_embedding")

    # Step 2: Drop old vector(1536) column
    try:
        op.drop_column('report_chunks', 'embedding')
    except Exception:
        pass  # Column may not exist if pgvector was unavailable during phase 6F

    # Step 3: Add new vector(384) column
    try:
        from pgvector.sqlalchemy import Vector
        op.add_column('report_chunks', sa.Column('embedding', Vector(384), nullable=True))
    except ImportError:
        op.add_column('report_chunks', sa.Column('embedding', sa.Text(), nullable=True))

    # Step 4: Also drop embedding_model (stale from 1536-dim) and reset embed_error
    op.execute("UPDATE report_chunks SET embedding_model = NULL, embed_error = NULL")

    # Step 5: Recreate HNSW index for vector(384)
    try:
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_report_chunks_embedding "
            "ON report_chunks USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64)"
        )
    except Exception:
        pass  # pgvector not available; keyword fallback still works

    # Step 6: Reset rag_status — documents that were 'embedded' with 1536-dim
    # vectors must be re-embedded. Reset to 'chunked' so the embed step reruns.
    op.execute(
        "UPDATE report_documents SET rag_status = 'chunked' WHERE rag_status = 'embedded'"
    )
    op.execute(
        "UPDATE report_documents SET rag_error = NULL WHERE rag_status = 'chunked'"
    )


def downgrade() -> None:
    # Drop HNSW index on 384-dim column
    op.execute("DROP INDEX IF EXISTS ix_report_chunks_embedding")

    # Drop vector(384) column
    try:
        op.drop_column('report_chunks', 'embedding')
    except Exception:
        pass

    # Restore vector(1536) column
    try:
        from pgvector.sqlalchemy import Vector
        op.add_column('report_chunks', sa.Column('embedding', Vector(1536), nullable=True))
    except ImportError:
        op.add_column('report_chunks', sa.Column('embedding', sa.Text(), nullable=True))

    # Restore HNSW index for vector(1536)
    try:
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_report_chunks_embedding "
            "ON report_chunks USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64)"
        )
    except Exception:
        pass

    # Note: downgrade cannot recover the original 1536-dim vectors (data is lost).
    # All chunk embeddings remain NULL after downgrade.
