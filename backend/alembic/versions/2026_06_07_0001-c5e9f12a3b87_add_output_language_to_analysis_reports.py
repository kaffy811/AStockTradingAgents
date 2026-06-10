"""add output_language to analysis_reports

Revision ID: c5e9f12a3b87
Revises: b4d8e2f1a6c9
Create Date: 2026-06-07 00:01:00

"""
from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c5e9f12a3b87'
down_revision: Union[str, None] = 'b4d8e2f1a6c9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'analysis_reports',
        sa.Column(
            'output_language',
            sa.String(length=16),
            nullable=False,
            server_default='zh-CN',
        ),
    )


def downgrade() -> None:
    op.drop_column('analysis_reports', 'output_language')
