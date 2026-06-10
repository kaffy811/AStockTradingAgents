"""add analysis_scope to analysis_reports

Revision ID: b4d8e2f1a6c9
Revises: a7c3f91e2b85
Create Date: 2026-06-04 00:03:00

"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b4d8e2f1a6c9'
down_revision: Union[str, None] = 'a7c3f91e2b85'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'analysis_reports',
        sa.Column(
            'analysis_scope',
            sa.String(length=32),
            nullable=False,
            server_default='comprehensive',
        ),
    )


def downgrade() -> None:
    op.drop_column('analysis_reports', 'analysis_scope')
