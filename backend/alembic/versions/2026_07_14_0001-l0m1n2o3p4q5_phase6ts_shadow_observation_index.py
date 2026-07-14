"""phase6ts shadow observation non-unique job index

Revision ID: l0m1n2o3p4q5
Revises: k9l0m1n2o3p4
Create Date: 2026-07-14
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "l0m1n2o3p4q5"
down_revision = "k9l0m1n2o3p4"
branch_labels = None
depends_on = None


WORKER_TABLE = "company_v2_financial_fusion_worker_observations"
JOB_ID_INDEX = "ix_company_v2_financial_fusion_worker_observations_job_id"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table(WORKER_TABLE):
        return
    indexes = {index["name"]: index for index in inspector.get_indexes(WORKER_TABLE)}
    existing = indexes.get(JOB_ID_INDEX)
    if existing is not None:
        op.drop_index(JOB_ID_INDEX, table_name=WORKER_TABLE)
    op.create_index(JOB_ID_INDEX, WORKER_TABLE, ["job_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table(WORKER_TABLE):
        return
    indexes = {index["name"]: index for index in inspector.get_indexes(WORKER_TABLE)}
    if JOB_ID_INDEX in indexes:
        op.drop_index(JOB_ID_INDEX, table_name=WORKER_TABLE)
    op.create_index(JOB_ID_INDEX, WORKER_TABLE, ["job_id"], unique=False)
