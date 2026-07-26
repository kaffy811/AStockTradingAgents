"""add_report_chunks

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-07-06
"""
from alembic import op
import sqlalchemy as sa

revision = 'f4a5b6c7d8e9'
down_revision = 'e3f4a5b6c7d8'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # New columns on report_documents
    op.add_column('report_documents', sa.Column('rag_status', sa.String(20), nullable=True, server_default='pending'))
    op.add_column('report_documents', sa.Column('chunk_count', sa.Integer(), nullable=True))
    op.add_column('report_documents', sa.Column('rag_error', sa.Text(), nullable=True))

    # New report_chunks table
    # Try to use vector type; fall back to text if pgvector unavailable
    try:
        from pgvector.sqlalchemy import Vector
        embedding_col = sa.Column('embedding', Vector(1536), nullable=True)
    except ImportError:
        embedding_col = sa.Column('embedding', sa.Text(), nullable=True)

    op.create_table(
        'report_chunks',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('report_id', sa.Integer(), sa.ForeignKey('report_documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('ts_code', sa.String(20), nullable=False),
        sa.Column('symbol', sa.String(20), nullable=False),
        sa.Column('market', sa.String(10), nullable=False, server_default='CN'),
        sa.Column('report_type', sa.String(20), nullable=True),
        sa.Column('report_year', sa.Integer(), nullable=True),
        sa.Column('period', sa.String(10), nullable=True),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('section_title', sa.String(200), nullable=True),
        sa.Column('page_start', sa.Integer(), nullable=True),
        sa.Column('page_end', sa.Integer(), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=False, unique=True),
        embedding_col,
        sa.Column('embedding_model', sa.String(100), nullable=True),
        sa.Column('token_count', sa.Integer(), nullable=True),
        sa.Column('embed_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_report_chunks_report_id', 'report_chunks', ['report_id'])
    op.create_index('ix_report_chunks_ts_code', 'report_chunks', ['ts_code'])
    op.create_index('ix_report_chunks_content_hash', 'report_chunks', ['content_hash'], unique=True)

    # HNSW index for vector similarity search (only if pgvector available)
    try:
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_report_chunks_embedding "
            "ON report_chunks USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 64)"
        )
    except Exception:
        pass  # pgvector not available, keyword fallback will work


def downgrade() -> None:
    op.drop_table('report_chunks')
    op.drop_column('report_documents', 'rag_status')
    op.drop_column('report_documents', 'chunk_count')
    op.drop_column('report_documents', 'rag_error')
