"""phase6tk fusion jobs

Revision ID: j8k9l0m1n2o3
Revises: i7j8k9l0m1n2
Create Date: 2026-07-12
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "j8k9l0m1n2o3"
down_revision = "i7j8k9l0m1n2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_v2_financial_fusion_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("market", sa.String(length=10), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("report_id", sa.Integer(), nullable=False),
        sa.Column("report_year", sa.Integer(), nullable=True),
        sa.Column("report_type", sa.String(length=30), nullable=True),
        sa.Column("requested_fields_json", sa.Text(), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=96), nullable=False),
        sa.Column("requester_scope", sa.String(length=60), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
        sa.Column("current_stage", sa.String(length=60), nullable=False, server_default="queued"),
        sa.Column("cache_hit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_id", sa.String(length=120), nullable=True),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retryable", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("repository_backend", sa.String(length=40), nullable=True),
        sa.Column("extractor_version", sa.String(length=80), nullable=True),
        sa.Column("cache_key", sa.String(length=140), nullable=True),
        sa.Column("cache_key_version", sa.String(length=40), nullable=True),
        sa.Column("active_generation", sa.Integer(), nullable=True),
        sa.Column("timings_json", sa.Text(), nullable=True),
        sa.Column("requester_metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_company_v2_financial_fusion_jobs_job_id", "company_v2_financial_fusion_jobs", ["job_id"], unique=True)
    op.create_index("ix_company_v2_financial_fusion_jobs_symbol", "company_v2_financial_fusion_jobs", ["symbol"])
    op.create_index("ix_company_v2_financial_fusion_jobs_report_id", "company_v2_financial_fusion_jobs", ["report_id"])
    op.create_index("ix_company_v2_financial_fusion_jobs_status", "company_v2_financial_fusion_jobs", ["status"])
    op.create_index("ix_company_v2_financial_fusion_jobs_fingerprint", "company_v2_financial_fusion_jobs", ["request_fingerprint"])


def downgrade() -> None:
    op.drop_index("ix_company_v2_financial_fusion_jobs_fingerprint", table_name="company_v2_financial_fusion_jobs")
    op.drop_index("ix_company_v2_financial_fusion_jobs_status", table_name="company_v2_financial_fusion_jobs")
    op.drop_index("ix_company_v2_financial_fusion_jobs_report_id", table_name="company_v2_financial_fusion_jobs")
    op.drop_index("ix_company_v2_financial_fusion_jobs_symbol", table_name="company_v2_financial_fusion_jobs")
    op.drop_index("ix_company_v2_financial_fusion_jobs_job_id", table_name="company_v2_financial_fusion_jobs")
    op.drop_table("company_v2_financial_fusion_jobs")
