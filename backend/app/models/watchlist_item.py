from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, field_validator
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


# ── ORM model ─────────────────────────────────────────────────────────────────

class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    __table_args__ = (
        UniqueConstraint("user_id", "market", "symbol", name="uq_watchlist_user_market_symbol"),
        Index("idx_watchlist_user_order", "user_id", "sort_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    market:     Mapped[str]        = mapped_column(String(8),  nullable=False)
    symbol:     Mapped[str]        = mapped_column(String(32), nullable=False)
    name:       Mapped[str | None] = mapped_column(String(64), nullable=True)
    note:       Mapped[str | None] = mapped_column(Text,       nullable=True)
    sort_order: Mapped[int]        = mapped_column(Integer,    nullable=False, default=0)
    created_at: Mapped[datetime]   = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime]   = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class WatchlistAddRequest(BaseModel):
    market:     str
    symbol:     str
    name:       str | None = None
    note:       str | None = None
    sort_order: int        = 0

    @field_validator("market")
    @classmethod
    def validate_market(cls, v: str) -> str:
        v = v.upper()
        if v not in {"CN", "HK"}:
            raise ValueError(f"market 只支持 CN 或 HK，收到 '{v}'")
        return v

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("symbol 不能为空")
        return v


class WatchlistPatchRequest(BaseModel):
    name:       str | None = None
    note:       str | None = None
    sort_order: int | None = None


class WatchlistLatestReport(BaseModel):
    """最近一次综合分析报告的轻量摘要，不含 report_md / sections / report_metadata 大字段。"""
    id:          uuid.UUID
    created_at:  datetime
    report_type: str
    warnings:    list[str]
    agents:      dict[str, dict]

    model_config = {"from_attributes": True}


class WatchlistItemResponse(BaseModel):
    id:            uuid.UUID
    market:        str
    symbol:        str
    name:          str | None
    note:          str | None
    sort_order:    int
    created_at:    datetime
    latest_report: WatchlistLatestReport | None = None

    model_config = {"from_attributes": True}


class WatchlistListResponse(BaseModel):
    total: int
    items: list[WatchlistItemResponse]


class WatchlistEnrichedItemResponse(BaseModel):
    id:            uuid.UUID
    market:        str
    symbol:        str
    name:          str | None
    note:          str | None
    sort_order:    int
    created_at:    datetime
    updated_at:    datetime
    latest_price:  float | None = None
    change_pct:    float | None = None
    industry_code: str | None = None
    industry_name: str | None = None
    quote_status:  str = "ok"    # "ok" | "failed"
    quote_message: str | None = None
    latest_report: WatchlistLatestReport | None = None


class WatchlistEnrichedListResponse(BaseModel):
    total: int
    items: list[WatchlistEnrichedItemResponse]
