"""fix mvp_invite redeemed_by_user_id uuid

Revision ID: 37cd8a42ecfe
Revises: o3p4q5r6s7t8
Create Date: 2026-07-27 11:20:39
"""

from alembic import op
import sqlalchemy as sa


revision = "37cd8a42ecfe"
down_revision = "o3p4q5r6s7t8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "mvp_invite",
        "redeemed_by_user_id",
        existing_type=sa.Integer(),
        type_=sa.UUID(),
        existing_nullable=True,
        postgresql_using="NULL::uuid",
    )


def downgrade() -> None:
    op.alter_column(
        "mvp_invite",
        "redeemed_by_user_id",
        existing_type=sa.UUID(),
        type_=sa.Integer(),
        existing_nullable=True,
        postgresql_using="NULL::integer",
    )
