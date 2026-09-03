"""report analysis durable traces

Revision ID: q5r6s7t8u9v0
Revises: p4q5r6s7t8u9
Create Date: 2026-08-26 22:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "q5r6s7t8u9v0"
down_revision = "p4q5r6s7t8u9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_analysis_traces",
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("pipeline_version", sa.String(40), nullable=False),
        sa.Column("git_sha", sa.String(64), nullable=True),
        sa.Column("runtime_image_identity", sa.String(255), nullable=True),
        sa.Column("session_hash", sa.String(64), nullable=True),
        sa.Column("question_redacted", sa.Text, nullable=True),
        sa.Column("question_hash", sa.String(64), nullable=False),
        sa.Column("market", sa.String(10), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("requested_report_id", sa.Integer, nullable=True),
        sa.Column("requested_years", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("final_status", sa.String(40), nullable=False, server_default="started"),
        sa.Column("partial", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("trace_persistence_failed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_report_analysis_traces_request_id", "report_analysis_traces", ["request_id"], unique=True)
    op.create_index("ix_report_analysis_traces_session_hash", "report_analysis_traces", ["session_hash"])
    op.create_index("ix_report_analysis_traces_symbol", "report_analysis_traces", ["symbol"])
    op.create_index("ix_report_analysis_traces_expires_at", "report_analysis_traces", ["expires_at"])
    op.create_table(
        "report_analysis_trace_stages",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("report_analysis_traces.trace_id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage_name", sa.String(8), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("input_hash", sa.String(64), nullable=True),
        sa.Column("output_hash", sa.String(64), nullable=True),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
    )
    op.create_index("uq_report_analysis_trace_stage", "report_analysis_trace_stages", ["trace_id", "stage_name"], unique=True)
    op.create_index("ix_report_analysis_trace_stage_status", "report_analysis_trace_stages", ["status"])


def downgrade() -> None:
    op.drop_table("report_analysis_trace_stages")
    op.drop_table("report_analysis_traces")
