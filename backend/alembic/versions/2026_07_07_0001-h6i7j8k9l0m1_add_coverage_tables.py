"""add_coverage_tables

Phase 6N-6: Add data completeness architecture tables.
  - data_coverage_snapshot  (uq: ts_code + trade_date)
  - provider_error_log
  - missing_field_queue     (uq: ts_code + field_name + trade_date)

Revision ID: h6i7j8k9l0m1
Revises: g5h6i7j8k9l0
Create Date: 2026-07-07
"""
from alembic import op
import sqlalchemy as sa

revision = 'h6i7j8k9l0m1'
down_revision = 'g5h6i7j8k9l0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── data_coverage_snapshot ──────────────────────────────────────────────
    op.create_table(
        'data_coverage_snapshot',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('ts_code', sa.String(20), nullable=False, comment='Tushare 股票代码'),
        sa.Column('trade_date', sa.String(10), nullable=False, comment='交易日 YYYY-MM-DD'),
        sa.Column('overall_completeness', sa.Float(), server_default='0', nullable=True,
                  comment='全字段完整率 0.0–1.0'),
        sa.Column('quote_completeness', sa.Float(), server_default='0', nullable=True),
        sa.Column('valuation_completeness', sa.Float(), server_default='0', nullable=True),
        sa.Column('financial_completeness', sa.Float(), server_default='0', nullable=True),
        sa.Column('rag_status', sa.String(20), server_default='unknown', nullable=True),
        sa.Column('missing_field_count', sa.Integer(), server_default='0', nullable=True),
        sa.Column('generated_at', sa.DateTime(), server_default=sa.text('NOW()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ts_code', 'trade_date', name='uq_coverage_ts_date'),
    )
    op.create_index('ix_coverage_ts_code', 'data_coverage_snapshot', ['ts_code'])
    op.create_index('ix_coverage_trade_date', 'data_coverage_snapshot', ['trade_date'])

    # ── provider_error_log ──────────────────────────────────────────────────
    op.create_table(
        'provider_error_log',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('ts_code', sa.String(20), nullable=False, comment='Tushare 股票代码'),
        sa.Column('field_name', sa.String(64), nullable=False, comment='出错字段名'),
        sa.Column('provider', sa.String(64), nullable=False, comment='数据源名称'),
        sa.Column('reason_code', sa.String(64), nullable=True),
        sa.Column('error_detail', sa.Text(), nullable=True),
        sa.Column('trade_date', sa.String(10), nullable=True),
        sa.Column('logged_at', sa.DateTime(), server_default=sa.text('NOW()'), nullable=True),
        sa.Column('retry_count', sa.Integer(), server_default='0', nullable=True),
        sa.Column('resolved', sa.Boolean(), server_default='false', nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_provider_error_ts_code', 'provider_error_log', ['ts_code'])
    op.create_index('ix_provider_error_field', 'provider_error_log', ['field_name'])
    op.create_index('ix_provider_error_trade_date', 'provider_error_log', ['trade_date'])

    # ── missing_field_queue ─────────────────────────────────────────────────
    op.create_table(
        'missing_field_queue',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('ts_code', sa.String(20), nullable=False, comment='Tushare 股票代码'),
        sa.Column('field_name', sa.String(64), nullable=False, comment='缺失字段名'),
        sa.Column('reason_code', sa.String(64), nullable=True),
        sa.Column('trade_date', sa.String(10), nullable=False, comment='交易日'),
        sa.Column('retry_count', sa.Integer(), server_default='0', nullable=True),
        sa.Column('status', sa.String(20), server_default='pending', nullable=True,
                  comment='pending / in_progress / done / failed'),
        sa.Column('last_attempt', sa.DateTime(), nullable=True),
        sa.Column('error_detail', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('NOW()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('NOW()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ts_code', 'field_name', 'trade_date',
                            name='uq_missing_field_ts_field_date'),
    )
    op.create_index('ix_missing_field_ts_code', 'missing_field_queue', ['ts_code'])
    op.create_index('ix_missing_field_name', 'missing_field_queue', ['field_name'])
    op.create_index('ix_missing_field_trade_date', 'missing_field_queue', ['trade_date'])
    op.create_index('ix_missing_field_status', 'missing_field_queue', ['status'])


def downgrade() -> None:
    op.drop_table('missing_field_queue')
    op.drop_table('provider_error_log')
    op.drop_table('data_coverage_snapshot')
