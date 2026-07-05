"""add ETL tables for industry ranking bottom layer

Revision ID: b8c3d9e2f5a1
Revises: a2c5e8f1b4d7
Create Date: 2026-07-05 00:01:00

Phase 2B: MySQL-compatible PostgreSQL ETL tables for:
  1. etl_stock_basic       — 股票基本信息（全市场，Tushare stock_basic）
  2. etl_daily_basic       — 日频估值/市值（Tushare daily_basic，按 trade_date 批量入库）
  3. etl_fina_indicator    — 财务核心指标（Tushare fina_indicator，按 period 批量入库）
  4. industry_rank_snapshot — 预计算行业排名快照（窗口函数离线计算结果）

Note: The project uses PostgreSQL (not MySQL); ranking SQL uses identical standard
window-function syntax. Upsert uses PostgreSQL ON CONFLICT DO UPDATE.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "b8c3d9e2f5a1"
down_revision = "a2c5e8f1b4d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. etl_stock_basic ────────────────────────────────────────────────────
    op.create_table(
        "etl_stock_basic",
        sa.Column("ts_code",    sa.String(16),  primary_key=True, comment="Tushare ts_code，如 600519.SH"),
        sa.Column("symbol",     sa.String(12),  nullable=True,  comment="股票代码"),
        sa.Column("name",       sa.String(64),  nullable=True,  comment="股票名称"),
        sa.Column("area",       sa.String(32),  nullable=True,  comment="地域"),
        sa.Column("industry",   sa.String(64),  nullable=True,  comment="所属行业（申万一级或 Tushare 行业）"),
        sa.Column("fullname",   sa.String(128), nullable=True,  comment="公司全称"),
        sa.Column("enname",     sa.String(128), nullable=True,  comment="英文全称"),
        sa.Column("market",     sa.String(16),  nullable=True,  comment="市场类型（主板/创业板/科创板/北交所）"),
        sa.Column("exchange",   sa.String(8),   nullable=True,  comment="交易所（SSE/SZSE/BSE）"),
        sa.Column("list_date",  sa.String(10),  nullable=True,  comment="上市日期 YYYY-MM-DD"),
        sa.Column("is_hs",      sa.String(4),   nullable=True,  comment="是否沪深港通（N/H/S）"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_etl_stock_basic_industry", "etl_stock_basic", ["industry"])
    op.create_index("ix_etl_stock_basic_market",   "etl_stock_basic", ["market"])

    # ── 2. etl_daily_basic ───────────────────────────────────────────────────
    op.create_table(
        "etl_daily_basic",
        sa.Column("id",           sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("ts_code",      sa.String(16),  nullable=False, comment="Tushare ts_code"),
        sa.Column("trade_date",   sa.String(10),  nullable=False, comment="交易日期 YYYYMMDD"),
        sa.Column("close",        sa.Numeric(16, 4), nullable=True),
        sa.Column("turnover_rate",sa.Numeric(10, 4), nullable=True, comment="换手率 %"),
        sa.Column("volume_ratio", sa.Numeric(10, 4), nullable=True),
        sa.Column("pe",           sa.Numeric(16, 4), nullable=True),
        sa.Column("pe_ttm",       sa.Numeric(16, 4), nullable=True),
        sa.Column("pb",           sa.Numeric(16, 4), nullable=True),
        sa.Column("ps",           sa.Numeric(16, 4), nullable=True),
        sa.Column("ps_ttm",       sa.Numeric(16, 4), nullable=True),
        sa.Column("dv_ratio",     sa.Numeric(10, 4), nullable=True, comment="股息率 %"),
        sa.Column("dv_ttm",       sa.Numeric(10, 4), nullable=True),
        sa.Column("total_share",  sa.Numeric(24, 4), nullable=True, comment="总股本（万股）"),
        sa.Column("float_share",  sa.Numeric(24, 4), nullable=True),
        sa.Column("free_share",   sa.Numeric(24, 4), nullable=True),
        sa.Column("total_mv",     sa.Numeric(24, 4), nullable=True, comment="总市值（万元）"),
        sa.Column("circ_mv",      sa.Numeric(24, 4), nullable=True, comment="流通市值（万元）"),
        sa.Column("updated_at",   sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("ts_code", "trade_date", name="uq_etl_daily_basic_code_date"),
    )
    op.create_index("ix_etl_daily_basic_trade_date", "etl_daily_basic", ["trade_date"])
    op.create_index("ix_etl_daily_basic_ts_code",    "etl_daily_basic", ["ts_code"])

    # ── 3. etl_fina_indicator ────────────────────────────────────────────────
    op.create_table(
        "etl_fina_indicator",
        sa.Column("id",                 sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("ts_code",            sa.String(16),  nullable=False),
        sa.Column("end_date",           sa.String(10),  nullable=False, comment="报告期末 YYYYMMDD"),
        sa.Column("ann_date",           sa.String(10),  nullable=True,  comment="披露日 YYYYMMDD"),
        sa.Column("roe",                sa.Numeric(16, 4), nullable=True, comment="ROE %"),
        sa.Column("roa",                sa.Numeric(16, 4), nullable=True),
        sa.Column("roic",               sa.Numeric(16, 4), nullable=True),
        sa.Column("grossprofit_margin", sa.Numeric(16, 4), nullable=True, comment="毛利率 %"),
        sa.Column("netprofit_margin",   sa.Numeric(16, 4), nullable=True, comment="净利率 %"),
        sa.Column("revenue_yoy",        sa.Numeric(16, 4), nullable=True, comment="营收同比 %"),
        sa.Column("netprofit_yoy",      sa.Numeric(16, 4), nullable=True, comment="净利润同比 %"),
        sa.Column("dt_netprofit_yoy",   sa.Numeric(16, 4), nullable=True, comment="扣非净利润同比 %"),
        sa.Column("assets_turn",        sa.Numeric(16, 4), nullable=True, comment="总资产周转率"),
        sa.Column("inv_turn",           sa.Numeric(16, 4), nullable=True),
        sa.Column("ar_turn",            sa.Numeric(16, 4), nullable=True),
        sa.Column("current_ratio",      sa.Numeric(16, 4), nullable=True),
        sa.Column("quick_ratio",        sa.Numeric(16, 4), nullable=True),
        sa.Column("debt_to_assets",     sa.Numeric(16, 4), nullable=True, comment="资产负债率 %"),
        sa.Column("updated_at",         sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("ts_code", "end_date", name="uq_etl_fina_indicator_code_period"),
    )
    op.create_index("ix_etl_fina_indicator_end_date", "etl_fina_indicator", ["end_date"])
    op.create_index("ix_etl_fina_indicator_ts_code",  "etl_fina_indicator", ["ts_code"])

    # ── 4. industry_rank_snapshot ────────────────────────────────────────────
    op.create_table(
        "industry_rank_snapshot",
        sa.Column("id",                    sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("ts_code",               sa.String(16),  nullable=False, comment="股票代码"),
        sa.Column("trade_date",            sa.String(10),  nullable=False, comment="行情日期 YYYYMMDD"),
        sa.Column("end_date",              sa.String(10),  nullable=False, comment="财报报告期 YYYYMMDD"),
        sa.Column("industry",              sa.String(64),  nullable=False, comment="行业分组"),
        sa.Column("metric",                sa.String(64),  nullable=False, comment="指标名称"),
        sa.Column("value",                 sa.Numeric(24, 6), nullable=True, comment="指标值"),
        sa.Column("rank_in_industry",      sa.Integer,     nullable=False, comment="行业内排名（1=最佳）"),
        sa.Column("peer_count",            sa.Integer,     nullable=False, comment="行业内参与排名的样本数"),
        sa.Column("percentile_in_industry",sa.Numeric(8, 4), nullable=False, comment="百分位 [0,1]，越高越好"),
        sa.Column("direction",             sa.String(32),  nullable=False, comment="higher_is_better / lower_is_better"),
        sa.Column("source_table",          sa.String(32),  nullable=False, comment="数据来源表"),
        sa.Column("generated_at",          sa.DateTime(timezone=True), nullable=False, comment="计算时间"),
        sa.UniqueConstraint(
            "ts_code", "trade_date", "end_date", "metric",
            name="uq_industry_rank_snapshot",
        ),
    )
    op.create_index("ix_irs_ts_code",    "industry_rank_snapshot", ["ts_code"])
    op.create_index("ix_irs_trade_date", "industry_rank_snapshot", ["trade_date"])
    op.create_index("ix_irs_end_date",   "industry_rank_snapshot", ["end_date"])
    op.create_index("ix_irs_industry",   "industry_rank_snapshot", ["industry"])
    op.create_index("ix_irs_metric",     "industry_rank_snapshot", ["metric"])


def downgrade() -> None:
    op.drop_table("industry_rank_snapshot")
    op.drop_table("etl_fina_indicator")
    op.drop_table("etl_daily_basic")
    op.drop_table("etl_stock_basic")
