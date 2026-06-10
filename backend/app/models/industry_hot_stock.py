from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from pydantic import BaseModel
from sqlalchemy import Date, DateTime, Float, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


# ── ORM model ─────────────────────────────────────────────────────────────────

class IndustryHotStockSnapshot(Base):
    """
    行业热门股 Top-N 每日快照。

    每次刷新时先删除同 (market, industry_code, trade_date, score_version)
    下的旧记录，再批量插入新记录，保证幂等。
    """
    __tablename__ = "industry_hot_stock_snapshot"

    __table_args__ = (
        UniqueConstraint(
            "market", "industry_code", "trade_date", "symbol", "score_version",
            name="uq_hot_stock_mid_tsv",
        ),
        Index("idx_hot_stock_industry_date", "market", "industry_code", "trade_date"),
        Index("idx_hot_stock_symbol_date",   "market", "symbol",        "trade_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    market: Mapped[str] = mapped_column(String(8),   nullable=False, index=True)
    industry_code: Mapped[str] = mapped_column(String(32),  nullable=False, index=True)
    industry_name: Mapped[str] = mapped_column(String(128), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32),  nullable=False, index=True)
    stock_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    hot_score: Mapped[float] = mapped_column(Float, nullable=False)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount_norm: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_abs_norm: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_version: Mapped[str] = mapped_column(
        String(16), nullable=False, default="v1"
    )
    data_source: Mapped[str] = mapped_column(
        String(64), nullable=False, default="akshare_stock_zh_a_spot"
    )
    score_factors: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
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

class HotStockItem(BaseModel):
    rank:            int
    symbol:          str
    stock_name:      str | None
    hot_score:       float
    amount:          float | None
    change_pct:      float | None
    amount_norm:     float | None
    change_abs_norm: float | None
    data_source:     str
    score_factors:   dict | None

    model_config = {"from_attributes": True}


class HotStockDataQuality(BaseModel):
    message: str | None = None


class HotStockResponse(BaseModel):
    market:        str
    industry_code: str
    industry_name: str | None
    trade_date:    date | None
    score_version: str
    items:         list[HotStockItem]
    data_quality:  HotStockDataQuality
