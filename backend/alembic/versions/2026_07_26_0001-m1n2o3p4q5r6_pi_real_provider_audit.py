"""pi_real_provider_audit table — Phase 6V-P1.31

Revision ID: m1n2o3p4q5r6
Revises: l0m1n2o3p4q5
Create Date: 2026-07-26
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "m1n2o3p4q5r6"
down_revision = "l0m1n2o3p4q5"
branch_labels = None
depends_on = None

TABLE_NAME = "pi_real_provider_audit"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table(TABLE_NAME):
        return

    op.create_table(
        TABLE_NAME,
        # Surrogate PK
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        # Unique call identifier (UUID4 string)
        sa.Column("call_id", sa.String(64), nullable=False, unique=True),
        # Phase label (e.g. "6V-P1.32")
        sa.Column("phase", sa.String(32), nullable=False, default=""),
        # Call outcome enum value
        sa.Column("outcome", sa.String(32), nullable=False),
        # Provider model identifier (never contains API key)
        sa.Column("model_id", sa.String(64), nullable=False, default=""),
        # Token usage (0 if not captured)
        sa.Column("input_tokens", sa.Integer, nullable=False, default=0),
        sa.Column("output_tokens", sa.Integer, nullable=False, default=0),
        sa.Column("cached_input_tokens", sa.Integer, nullable=False, default=0),
        sa.Column("reasoning_tokens", sa.Integer, nullable=False, default=0),
        sa.Column("usage_complete", sa.Boolean, nullable=False, default=False),
        # Cost estimate as string decimal (never float)
        sa.Column("estimated_cost_cny", sa.String(32), nullable=False, default="0"),
        # Duration in milliseconds
        sa.Column("duration_ms", sa.Integer, nullable=False, default=0),
        # Error type string (empty on success)
        sa.Column("error_type", sa.String(128), nullable=False, default=""),
        # What triggered the call
        sa.Column("trigger", sa.String(64), nullable=False, default=""),
        # Config version at time of call
        sa.Column("config_version", sa.Integer, nullable=False, default=12),
        # Hash-only fields (NO raw prompt or response content)
        sa.Column("request_hash", sa.String(16), nullable=False, default=""),
        sa.Column("response_hash", sa.String(16), nullable=False, default=""),
        # Timestamps
        sa.Column("epoch", sa.Float, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Indexes for common query patterns
    op.create_index(
        f"ix_{TABLE_NAME}_phase",
        TABLE_NAME,
        ["phase"],
    )
    op.create_index(
        f"ix_{TABLE_NAME}_outcome",
        TABLE_NAME,
        ["outcome"],
    )
    op.create_index(
        f"ix_{TABLE_NAME}_created_at",
        TABLE_NAME,
        ["created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table(TABLE_NAME):
        return

    op.drop_index(f"ix_{TABLE_NAME}_created_at", table_name=TABLE_NAME)
    op.drop_index(f"ix_{TABLE_NAME}_outcome", table_name=TABLE_NAME)
    op.drop_index(f"ix_{TABLE_NAME}_phase", table_name=TABLE_NAME)
    op.drop_table(TABLE_NAME)
