"""p132: mvp_invite, chat_feedback, mvp_analytics_event tables

Revision ID: n2o3p4q5r6s7
Revises: m1n2o3p4q5r6
Create Date: 2026-07-26 02:00:00

Phase 6V-P1.32 — MVP Release Candidate.

Creates:
  mvp_invite           — invite-only user access control
  chat_feedback        — per-answer thumbs/report feedback
  mvp_analytics_event  — structured launch analytics and error monitoring
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "n2o3p4q5r6s7"
down_revision = "m1n2o3p4q5r6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── mvp_invite ─────────────────────────────────────────────────────────────
    op.create_table(
        "mvp_invite",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("invite_code", sa.String(64), nullable=False, unique=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=False, server_default="system"),
        sa.Column("redeemed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("redeemed_at", sa.DateTime, nullable=True),
        sa.Column("redeemed_by_user_id", sa.Integer, nullable=True),
        sa.Column("max_uses", sa.Integer, nullable=False, server_default="1"),
        sa.Column("use_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime, nullable=True),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_mvp_invite_invite_code", "mvp_invite", ["invite_code"])
    op.create_index("ix_mvp_invite_email", "mvp_invite", ["email"])

    # ── chat_feedback ──────────────────────────────────────────────────────────
    op.create_table(
        "chat_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", sa.String(64), nullable=False),
        sa.Column("message_id", sa.String(64), nullable=True),
        sa.Column("user_id", sa.Integer, nullable=True),
        sa.Column("feedback_type", sa.String(32), nullable=False),
        sa.Column("feedback_detail", sa.String(128), nullable=True),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column("answer_snippet", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_chat_feedback_session_id", "chat_feedback", ["session_id"])
    op.create_index("ix_chat_feedback_user_id", "chat_feedback", ["user_id"])
    op.create_index("ix_chat_feedback_message_id", "chat_feedback", ["message_id"])

    # ── mvp_analytics_event ────────────────────────────────────────────────────
    op.create_table(
        "mvp_analytics_event",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_name", sa.String(128), nullable=False),
        sa.Column("event_category", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer, nullable=True),
        sa.Column("session_id", sa.String(64), nullable=True),
        sa.Column("properties", postgresql.JSON, nullable=True),
        sa.Column("error_class", sa.String(128), nullable=True),
        sa.Column("error_severity", sa.String(32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_mvp_analytics_event_name", "mvp_analytics_event", ["event_name"]
    )
    op.create_index(
        "ix_mvp_analytics_event_category", "mvp_analytics_event", ["event_category"]
    )
    op.create_index(
        "ix_mvp_analytics_event_created_at", "mvp_analytics_event", ["created_at"]
    )
    op.create_index(
        "ix_mvp_analytics_event_session_id", "mvp_analytics_event", ["session_id"]
    )


def downgrade() -> None:
    op.drop_table("mvp_analytics_event")
    op.drop_table("chat_feedback")
    op.drop_table("mvp_invite")
