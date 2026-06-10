from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel
from sqlalchemy import Boolean, DateTime, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


# ── ORM models ────────────────────────────────────────────────────────────────

class IndustryMaster(Base):
    """申万一级行业主表。每条记录对应一个行业分类条目。"""
    __tablename__ = "industry_master"

    __table_args__ = (
        UniqueConstraint("market", "industry_code", "source", name="uq_industry_master_mcs"),
        Index("idx_industry_master_market_code", "market", "industry_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    market: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    industry_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    industry_name: Mapped[str] = mapped_column(String(128), nullable=False)
    industry_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    parent_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[str] = mapped_column(
        String(64), nullable=False, default="sw_static_csv"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class StockIndustryMap(Base):
    """股票→申万一级行业映射表。支持一只股票映射到多个行业（is_primary 标识主分类）。"""
    __tablename__ = "stock_industry_map"

    __table_args__ = (
        UniqueConstraint(
            "market", "symbol", "industry_code", "source",
            name="uq_stock_industry_mscs",
        ),
        Index("idx_stock_industry_market_sym", "market", "symbol"),
        Index("idx_stock_industry_code", "industry_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    market: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    stock_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    industry_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    industry_name: Mapped[str] = mapped_column(String(128), nullable=False)
    industry_level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source: Mapped[str] = mapped_column(
        String(64), nullable=False, default="sw_static_csv"
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class IndustryInfoResponse(BaseModel):
    market:         str
    industry_code:  str
    industry_name:  str
    industry_level: int
    source:         str
    # ── Hot summary fields — null / zero if no snapshot exists ────────────────
    hot_score:      float | None = None
    stock_count:    int          = 0
    up_count:       int          = 0
    down_count:     int          = 0
    avg_change_pct: float | None = None
    amount:         float | None = None
    trade_date:     str | None   = None
    score_version:  str | None   = None
    data_quality:   dict | None  = None

    model_config = {"from_attributes": False}  # validated from dict, not ORM


class StockIndustryResponse(BaseModel):
    market:         str
    symbol:         str
    stock_name:     str | None
    industry_code:  str
    industry_name:  str
    industry_level: int
    source:         str
    is_primary:     bool

    model_config = {"from_attributes": True}


class IndustryConstituentItem(BaseModel):
    market:        str
    symbol:        str
    stock_name:    str | None
    industry_code: str
    industry_name: str

    model_config = {"from_attributes": True}


class IndustryConstituentsResponse(BaseModel):
    market:        str
    industry_code: str
    industry_name: str
    total:         int
    items:         list[IndustryConstituentItem]
