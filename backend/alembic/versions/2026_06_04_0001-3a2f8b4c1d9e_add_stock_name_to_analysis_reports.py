"""add stock_name to analysis_reports

Revision ID: 3a2f8b4c1d9e
Revises: 76fe066db8b1
Create Date: 2026-06-04 00:01:00.000000+00:00

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3a2f8b4c1d9e'
down_revision: Union[str, None] = '76fe066db8b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'analysis_reports',
        sa.Column('stock_name', sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('analysis_reports', 'stock_name')
