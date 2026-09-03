"""mvp_r12: is_admin on app_users, code_hash/code_prefix on mvp_invite

Revision ID: o3p4q5r6s7t8
Revises: n2o3p4q5r6s7
Create Date: 2026-07-26 12:00:00

Phase MVP-R1.2 — Invite Security Closure.

Changes:
  app_users        — add is_admin (bool, default false)
  mvp_invite       — add code_hash (sha256 hex, unique, indexed)
                   — add code_prefix (first 8 chars, for display)
                   — drop invite_code (plaintext codes no longer stored)
"""
from alembic import op
import sqlalchemy as sa

revision = "o3p4q5r6s7t8"
down_revision = "n2o3p4q5r6s7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── app_users: add is_admin ────────────────────────────────────────────────
    op.add_column(
        "app_users",
        sa.Column(
            "is_admin",
            sa.Boolean,
            nullable=False,
            server_default="false",
        ),
    )

    # ── mvp_invite: add code_hash + code_prefix ────────────────────────────────
    op.add_column(
        "mvp_invite",
        sa.Column("code_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "mvp_invite",
        sa.Column("code_prefix", sa.String(8), nullable=True),
    )

    # Drop old plaintext invite_code column and its index
    op.drop_index("ix_mvp_invite_invite_code", table_name="mvp_invite")
    op.drop_column("mvp_invite", "invite_code")

    # Create unique index on code_hash
    op.create_index(
        "ix_mvp_invite_code_hash",
        "mvp_invite",
        ["code_hash"],
        unique=True,
        postgresql_where=sa.text("code_hash IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_mvp_invite_code_hash", table_name="mvp_invite")
    op.add_column(
        "mvp_invite",
        sa.Column("invite_code", sa.String(64), nullable=True),
    )
    op.create_index("ix_mvp_invite_invite_code", "mvp_invite", ["invite_code"])
    op.drop_column("mvp_invite", "code_prefix")
    op.drop_column("mvp_invite", "code_hash")
    op.drop_column("app_users", "is_admin")
