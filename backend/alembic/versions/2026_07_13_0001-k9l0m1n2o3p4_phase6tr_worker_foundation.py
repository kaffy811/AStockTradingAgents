"""phase6tr worker foundation

Revision ID: k9l0m1n2o3p4
Revises: j8k9l0m1n2o3
Create Date: 2026-07-13
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "k9l0m1n2o3p4"
down_revision = "j8k9l0m1n2o3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    job_table = "company_v2_financial_fusion_jobs"
    existing_columns = {column["name"] for column in inspector.get_columns(job_table)} if inspector.has_table(job_table) else set()
    if "claimed_by" not in existing_columns:
        op.add_column(job_table, sa.Column("claimed_by", sa.String(length=80), nullable=True))
    if "claimed_at" not in existing_columns:
        op.add_column(job_table, sa.Column("claimed_at", sa.DateTime(), nullable=True))
    if "heartbeat_at" not in existing_columns:
        op.add_column(job_table, sa.Column("heartbeat_at", sa.DateTime(), nullable=True))
    if "lease_expires_at" not in existing_columns:
        op.add_column(job_table, sa.Column("lease_expires_at", sa.DateTime(), nullable=True))
    if "attempt_count" not in existing_columns:
        op.add_column(job_table, sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
    if "max_attempts" not in existing_columns:
        op.add_column(job_table, sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"))
    if "next_retry_at" not in existing_columns:
        op.add_column(job_table, sa.Column("next_retry_at", sa.DateTime(), nullable=True))
    if "execution_mode" not in existing_columns:
        op.add_column(job_table, sa.Column("execution_mode", sa.String(length=20), nullable=True))
    if "worker_version" not in existing_columns:
        op.add_column(job_table, sa.Column("worker_version", sa.String(length=40), nullable=True))
    if "rollout_bucket_at_claim" not in existing_columns:
        op.add_column(job_table, sa.Column("rollout_bucket_at_claim", sa.Integer(), nullable=True))
    if "rollout_percent_at_claim" not in existing_columns:
        op.add_column(job_table, sa.Column("rollout_percent_at_claim", sa.Integer(), nullable=True))
    if "auto_run_at_claim" not in existing_columns:
        op.add_column(job_table, sa.Column("auto_run_at_claim", sa.Boolean(), nullable=True))
    if "last_error_message_sanitized" not in existing_columns:
        op.add_column(job_table, sa.Column("last_error_message_sanitized", sa.Text(), nullable=True))
    if "ix_company_v2_financial_fusion_jobs_claimable" not in {index["name"] for index in inspector.get_indexes(job_table)}:
        op.create_index(
            "ix_company_v2_financial_fusion_jobs_claimable",
            job_table,
            ["status", "next_retry_at", "lease_expires_at", "created_at"],
        )
    if "ix_company_v2_financial_fusion_jobs_claimed_by" not in {index["name"] for index in inspector.get_indexes(job_table)}:
        op.create_index("ix_company_v2_financial_fusion_jobs_claimed_by", job_table, ["claimed_by"])
    if "ix_company_v2_financial_fusion_jobs_lease_expires_at" not in {index["name"] for index in inspector.get_indexes(job_table)}:
        op.create_index("ix_company_v2_financial_fusion_jobs_lease_expires_at", job_table, ["lease_expires_at"])

    worker_table = "company_v2_financial_fusion_worker_observations"
    existing_worker_columns = {column["name"] for column in inspector.get_columns(worker_table)} if inspector.has_table(worker_table) else set()
    if not inspector.has_table(worker_table):
        op.create_table(
            worker_table,
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("job_id", sa.String(length=64), nullable=False),
            sa.Column("symbol", sa.String(length=20), nullable=False),
            sa.Column("report_id", sa.Integer(), nullable=False),
            sa.Column("worker_id", sa.String(length=80), nullable=False),
            sa.Column("observed_at", sa.DateTime(), nullable=False),
            sa.Column("claimed_at", sa.DateTime(), nullable=True),
            sa.Column("released_at", sa.DateTime(), nullable=True),
            sa.Column("would_execute", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("block_reason", sa.String(length=80), nullable=True),
            sa.Column("allowlist_match", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("report_ready", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("rag_ready", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("structured_ready", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("circuit_open", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("auto_run", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("rollout_percent", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("stage3_authorized", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("worker_version", sa.String(length=40), nullable=False),
            sa.Column("execution_mode", sa.String(length=20), nullable=False),
            sa.Column("provider_calls", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("rag_query_calls", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("extractor_calls", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("fusion_calls", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sanitized_payload_json", sa.Text(), nullable=True),
        )
    else:
        if "claimed_at" not in existing_worker_columns:
            op.add_column(worker_table, sa.Column("claimed_at", sa.DateTime(), nullable=True))
        if "released_at" not in existing_worker_columns:
            op.add_column(worker_table, sa.Column("released_at", sa.DateTime(), nullable=True))
        if "provider_calls" not in existing_worker_columns:
            op.add_column(worker_table, sa.Column("provider_calls", sa.Integer(), nullable=False, server_default="0"))
        if "rag_query_calls" not in existing_worker_columns:
            op.add_column(worker_table, sa.Column("rag_query_calls", sa.Integer(), nullable=False, server_default="0"))
        if "extractor_calls" not in existing_worker_columns:
            op.add_column(worker_table, sa.Column("extractor_calls", sa.Integer(), nullable=False, server_default="0"))
        if "fusion_calls" not in existing_worker_columns:
            op.add_column(worker_table, sa.Column("fusion_calls", sa.Integer(), nullable=False, server_default="0"))
    worker_indexes = {index["name"] for index in inspector.get_indexes(worker_table)} if inspector.has_table(worker_table) else set()
    if "ix_company_v2_financial_fusion_worker_observations_job_id" not in worker_indexes and inspector.has_table(worker_table):
        op.create_index("ix_company_v2_financial_fusion_worker_observations_job_id", worker_table, ["job_id"])
    if "ix_company_v2_financial_fusion_worker_observations_symbol" not in worker_indexes and inspector.has_table(worker_table):
        op.create_index("ix_company_v2_financial_fusion_worker_observations_symbol", worker_table, ["symbol"])
    if "ix_company_v2_financial_fusion_worker_observations_worker_id" not in worker_indexes and inspector.has_table(worker_table):
        op.create_index("ix_company_v2_financial_fusion_worker_observations_worker_id", worker_table, ["worker_id"])


def downgrade() -> None:
    op.drop_index("ix_company_v2_financial_fusion_worker_observations_worker_id", table_name="company_v2_financial_fusion_worker_observations")
    op.drop_index("ix_company_v2_financial_fusion_worker_observations_symbol", table_name="company_v2_financial_fusion_worker_observations")
    op.drop_index("ix_company_v2_financial_fusion_worker_observations_job_id", table_name="company_v2_financial_fusion_worker_observations")
    op.drop_table("company_v2_financial_fusion_worker_observations")
    op.drop_index("ix_company_v2_financial_fusion_jobs_lease_expires_at", table_name="company_v2_financial_fusion_jobs")
    op.drop_index("ix_company_v2_financial_fusion_jobs_claimed_by", table_name="company_v2_financial_fusion_jobs")
    op.drop_index("ix_company_v2_financial_fusion_jobs_claimable", table_name="company_v2_financial_fusion_jobs")
    op.drop_column("company_v2_financial_fusion_jobs", "last_error_message_sanitized")
    op.drop_column("company_v2_financial_fusion_jobs", "auto_run_at_claim")
    op.drop_column("company_v2_financial_fusion_jobs", "rollout_percent_at_claim")
    op.drop_column("company_v2_financial_fusion_jobs", "rollout_bucket_at_claim")
    op.drop_column("company_v2_financial_fusion_jobs", "worker_version")
    op.drop_column("company_v2_financial_fusion_jobs", "execution_mode")
    op.drop_column("company_v2_financial_fusion_jobs", "next_retry_at")
    op.drop_column("company_v2_financial_fusion_jobs", "max_attempts")
    op.drop_column("company_v2_financial_fusion_jobs", "attempt_count")
    op.drop_column("company_v2_financial_fusion_jobs", "lease_expires_at")
    op.drop_column("company_v2_financial_fusion_jobs", "heartbeat_at")
    op.drop_column("company_v2_financial_fusion_jobs", "claimed_at")
    op.drop_column("company_v2_financial_fusion_jobs", "claimed_by")
