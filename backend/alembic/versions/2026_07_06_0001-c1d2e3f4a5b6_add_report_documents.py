"""add report_documents table for Phase 6A zero-cost PDF indexing

Revision ID: c1d2e3f4a5b6
Revises: b8c3d9e2f5a1
Create Date: 2026-07-06 00:01:00

Phase 6A: Adds report_documents table to index annual/semi-annual report PDFs
collected from public sources (CNINFO etc.). Only activated when
ENABLE_REPORT_PDF=true.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "c1d2e3f4a5b6"
down_revision = "b8c3d9e2f5a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ts_code", sa.String(20), nullable=False, comment="Tushare 股票代码，如 600519.SH"),
        sa.Column("report_type", sa.String(20), nullable=True, comment="报告类型: annual / semi / q1 / q3"),
        sa.Column("period_end", sa.String(10), nullable=True, comment="报告期截止日 YYYY-MM-DD"),
        sa.Column("title", sa.String(200), nullable=True, comment="报告标题"),
        sa.Column("source_url", sa.String(500), nullable=True, comment="原始下载 URL"),
        sa.Column("local_path", sa.String(500), nullable=True, comment="本地存储路径"),
        sa.Column("file_sha256", sa.String(64), nullable=True, comment="文件 SHA-256 校验和"),
        sa.Column("text_excerpt", sa.Text(), nullable=True, comment="正文摘录（首 2000 字符）"),
        sa.Column("disclosure_date", sa.String(10), nullable=True, comment="披露日 YYYY-MM-DD"),
        sa.Column("parsed", sa.Boolean(), nullable=True, comment="是否已完成 PDF 解析"),
        sa.Column("created_at", sa.DateTime(), nullable=True, comment="入库时间（UTC）"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_report_documents_ts_code", "report_documents", ["ts_code"])


def downgrade() -> None:
    op.drop_index("ix_report_documents_ts_code", table_name="report_documents")
    op.drop_table("report_documents")
