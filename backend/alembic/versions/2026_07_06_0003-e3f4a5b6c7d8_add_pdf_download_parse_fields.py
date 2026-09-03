"""add_pdf_download_parse_fields

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-07-06
"""
from alembic import op
import sqlalchemy as sa

revision = 'e3f4a5b6c7d8'
down_revision = 'd2e3f4a5b6c7'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('report_documents', sa.Column('file_size', sa.Integer(), nullable=True, comment='文件大小（字节）'))
    op.add_column('report_documents', sa.Column('parse_status', sa.String(20), nullable=True, server_default='pending', comment='解析状态: pending/parsed/failed'))
    op.add_column('report_documents', sa.Column('download_error', sa.Text(), nullable=True, comment='下载错误信息'))
    op.add_column('report_documents', sa.Column('parse_error', sa.Text(), nullable=True, comment='解析错误信息'))

def downgrade() -> None:
    op.drop_column('report_documents', 'file_size')
    op.drop_column('report_documents', 'parse_status')
    op.drop_column('report_documents', 'download_error')
    op.drop_column('report_documents', 'parse_error')
