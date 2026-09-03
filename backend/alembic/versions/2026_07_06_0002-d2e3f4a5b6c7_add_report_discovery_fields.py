"""add report discovery fields

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-07-06
"""
from alembic import op
import sqlalchemy as sa

revision = "d2e3f4a5b6c7"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("report_documents", sa.Column("pdf_url", sa.String(500), nullable=True))
    op.add_column("report_documents", sa.Column("report_year", sa.Integer(), nullable=True))
    op.add_column("report_documents", sa.Column("source", sa.String(20), nullable=True))
    op.add_column("report_documents", sa.Column("download_status", sa.String(20), server_default="pending", nullable=True))
    op.add_column("report_documents", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column("report_documents", sa.Column("warnings_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("report_documents", "warnings_json")
    op.drop_column("report_documents", "confidence")
    op.drop_column("report_documents", "download_status")
    op.drop_column("report_documents", "source")
    op.drop_column("report_documents", "report_year")
    op.drop_column("report_documents", "pdf_url")
