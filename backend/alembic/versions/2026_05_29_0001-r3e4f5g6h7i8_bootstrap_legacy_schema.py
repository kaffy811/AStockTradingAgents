"""Version the schema that predates the existing-schema Alembic baseline.

Revision ID: r3e4f5g6h7i8
Revises:

Existing installations already at 4b49004d01a6 or a descendant do not execute
this newly linked ancestor.  Unversioned legacy installations may execute it;
each table is therefore created only when absent.  Existing tables are never
altered or replaced here.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "r3e4f5g6h7i8"
down_revision = None
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB()


def _missing(table_name: str) -> bool:
    return not sa.inspect(op.get_bind()).has_table(table_name)


def upgrade() -> None:
    if _missing("app_users"):
        op.create_table(
            "app_users",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("username", sa.String(32), nullable=False),
            sa.Column("email", sa.String(254), nullable=False),
            sa.Column("hashed_password", sa.String(255), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("username"),
            sa.UniqueConstraint("email"),
        )
        op.create_index("ix_app_users_username", "app_users", ["username"])
        op.create_index("ix_app_users_email", "app_users", ["email"])

    if _missing("analysis_reports"):
        op.create_table(
            "analysis_reports",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("user_id", UUID, sa.ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("market", sa.String(8), nullable=False),
            sa.Column("symbol", sa.String(32), nullable=False),
            sa.Column("report_type", sa.String(32), nullable=False),
            sa.Column("report_md", sa.Text(), nullable=False),
            sa.Column("sections", JSONB, nullable=False),
            sa.Column("report_metadata", JSONB, nullable=False),
            sa.Column("warnings", JSONB, nullable=False),
            sa.Column("agents", JSONB, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_analysis_reports_user_id", "analysis_reports", ["user_id"])
        op.create_index("ix_analysis_reports_symbol", "analysis_reports", ["symbol"])
        op.create_index("idx_reports_user_created", "analysis_reports", ["user_id", "created_at"])

    if _missing("watchlist_items"):
        op.create_table(
            "watchlist_items",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("user_id", UUID, sa.ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("market", sa.String(8), nullable=False),
            sa.Column("symbol", sa.String(32), nullable=False),
            sa.Column("name", sa.String(64)),
            sa.Column("note", sa.Text()),
            sa.Column("sort_order", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("user_id", "market", "symbol", name="uq_watchlist_user_market_symbol"),
        )
        op.create_index("ix_watchlist_items_user_id", "watchlist_items", ["user_id"])
        op.create_index("idx_watchlist_user_order", "watchlist_items", ["user_id", "sort_order"])

    if _missing("industry_master"):
        op.create_table(
            "industry_master",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("market", sa.String(8), nullable=False),
            sa.Column("industry_code", sa.String(32), nullable=False),
            sa.Column("industry_name", sa.String(128), nullable=False),
            sa.Column("industry_level", sa.Integer(), nullable=False),
            sa.Column("parent_code", sa.String(32)),
            sa.Column("source", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("market", "industry_code", "source", name="uq_industry_master_mcs"),
        )
        op.create_index("ix_industry_master_market", "industry_master", ["market"])
        op.create_index("ix_industry_master_industry_code", "industry_master", ["industry_code"])
        op.create_index("idx_industry_master_market_code", "industry_master", ["market", "industry_code"])

    if _missing("stock_industry_map"):
        op.create_table(
            "stock_industry_map",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("market", sa.String(8), nullable=False),
            sa.Column("symbol", sa.String(32), nullable=False),
            sa.Column("stock_name", sa.String(128)),
            sa.Column("industry_code", sa.String(32), nullable=False),
            sa.Column("industry_name", sa.String(128), nullable=False),
            sa.Column("industry_level", sa.Integer(), nullable=False),
            sa.Column("source", sa.String(64), nullable=False),
            sa.Column("is_primary", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("market", "symbol", "industry_code", "source", name="uq_stock_industry_mscs"),
        )
        op.create_index("ix_stock_industry_map_market", "stock_industry_map", ["market"])
        op.create_index("ix_stock_industry_map_symbol", "stock_industry_map", ["symbol"])
        op.create_index("ix_stock_industry_map_industry_code", "stock_industry_map", ["industry_code"])
        op.create_index("idx_stock_industry_market_sym", "stock_industry_map", ["market", "symbol"])
        op.create_index("idx_stock_industry_code", "stock_industry_map", ["industry_code"])

    if _missing("industry_hot_stock_snapshot"):
        op.create_table(
            "industry_hot_stock_snapshot",
            sa.Column("id", UUID, primary_key=True),
            sa.Column("market", sa.String(8), nullable=False),
            sa.Column("industry_code", sa.String(32), nullable=False),
            sa.Column("industry_name", sa.String(128), nullable=False),
            sa.Column("trade_date", sa.Date(), nullable=False),
            sa.Column("rank", sa.Integer(), nullable=False),
            sa.Column("symbol", sa.String(32), nullable=False),
            sa.Column("stock_name", sa.String(128)),
            sa.Column("hot_score", sa.Float(), nullable=False),
            sa.Column("amount", sa.Float()),
            sa.Column("change_pct", sa.Float()),
            sa.Column("amount_norm", sa.Float()),
            sa.Column("change_abs_norm", sa.Float()),
            sa.Column("score_version", sa.String(16), nullable=False),
            sa.Column("data_source", sa.String(64), nullable=False),
            sa.Column("score_factors", JSONB),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("market", "industry_code", "trade_date", "symbol", "score_version", name="uq_hot_stock_mid_tsv"),
        )
        op.create_index("ix_industry_hot_stock_snapshot_market", "industry_hot_stock_snapshot", ["market"])
        op.create_index("ix_industry_hot_stock_snapshot_industry_code", "industry_hot_stock_snapshot", ["industry_code"])
        op.create_index("ix_industry_hot_stock_snapshot_trade_date", "industry_hot_stock_snapshot", ["trade_date"])
        op.create_index("ix_industry_hot_stock_snapshot_symbol", "industry_hot_stock_snapshot", ["symbol"])
        op.create_index("idx_hot_stock_industry_date", "industry_hot_stock_snapshot", ["market", "industry_code", "trade_date"])
        op.create_index("idx_hot_stock_symbol_date", "industry_hot_stock_snapshot", ["market", "symbol", "trade_date"])

    if _missing("company_v2_report_rag_documents"):
        op.create_table(
            "company_v2_report_rag_documents",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("report_id", sa.Integer(), nullable=False),
            sa.Column("market", sa.String(10), nullable=False),
            sa.Column("symbol", sa.String(20), nullable=False),
            sa.Column("company_name", sa.String(200)),
            sa.Column("report_year", sa.Integer(), nullable=False),
            sa.Column("report_type", sa.String(30), nullable=False),
            sa.Column("announcement_date", sa.String(20)),
            sa.Column("source_url", sa.String(500), nullable=False),
            sa.Column("pdf_hash", sa.String(80)),
            sa.Column("parse_version", sa.String(50), nullable=False),
            sa.Column("page_count", sa.Integer(), nullable=False),
            sa.Column("chunk_count", sa.Integer(), nullable=False),
            sa.Column("embedding_model", sa.String(100)),
            sa.Column("embedding_version", sa.String(100)),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
        )
        op.create_index("ix_company_v2_report_rag_documents_report_id", "company_v2_report_rag_documents", ["report_id"], unique=True)

    if _missing("company_v2_report_rag_chunks"):
        op.create_table(
            "company_v2_report_rag_chunks",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("rag_document_id", sa.Integer(), sa.ForeignKey("company_v2_report_rag_documents.id", ondelete="CASCADE"), nullable=False),
            sa.Column("report_id", sa.Integer(), nullable=False),
            sa.Column("chunk_index", sa.Integer(), nullable=False),
            sa.Column("page_start", sa.Integer(), nullable=False),
            sa.Column("page_end", sa.Integer(), nullable=False),
            sa.Column("section_title", sa.String(300)),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("text_hash", sa.String(64), nullable=False),
            sa.Column("token_count", sa.Integer(), nullable=False),
            sa.Column("embedding", sa.Text()),
            sa.Column("metadata_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime()),
        )
        op.create_index("ix_company_v2_report_rag_chunks_rag_document_id", "company_v2_report_rag_chunks", ["rag_document_id"])
        op.create_index("ix_company_v2_report_rag_chunks_report_id", "company_v2_report_rag_chunks", ["report_id"])
        op.create_index("ix_company_v2_report_rag_chunks_text_hash", "company_v2_report_rag_chunks", ["text_hash"])


def downgrade() -> None:
    # The revision represents schema that existed before Alembic ownership.
    # Never drop legacy tables or user data during graph downgrade.
    pass
