"""add auto_saved to analysis_reports

Revision ID: a7c3f91e2b85
Revises: 3a2f8b4c1d9e
Create Date: 2026-06-04 00:02:00

"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7c3f91e2b85'
down_revision: Union[str, None] = '3a2f8b4c1d9e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'analysis_reports',
        sa.Column('auto_saved', sa.Boolean(), nullable=False, server_default='false'),
    )


def downgrade() -> None:
    op.drop_column('analysis_reports', 'auto_saved')
