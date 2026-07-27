"""add email_verified_at to app_users

Phase MVP-R1.3 — Email Verification for invite-only registration.

Revision ID: p4q5r6s7t8u9
Revises: o3p4q5r6s7t8
Create Date: 2026-07-28

Changes:
  - app_users.email_verified_at  TIMESTAMPTZ NULL  (NULL = not verified yet)
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision = "p4q5r6s7t8u9"
down_revision = "o3p4q5r6s7t8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_users",
        sa.Column(
            "email_verified_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when the email address was verified. NULL = unverified.",
        ),
    )


def downgrade() -> None:
    op.drop_column("app_users", "email_verified_at")
