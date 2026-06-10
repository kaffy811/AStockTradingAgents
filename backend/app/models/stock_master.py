from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StockMaster(Base):
    """
    股票主数据表。
    每只股票在每个市场唯一一行，与行业分类无关。
    搜索联想（/stocks/search）的主要数据源。
    """

    __tablename__ = "stock_master"

    __table_args__ = (
        UniqueConstraint("market", "symbol", name="uq_stock_master_market_symbol"),
        Index("idx_stock_master_market_symbol",   "market", "symbol"),
        Index("idx_stock_master_market_name",     "market", "name"),
        Index("idx_stock_master_market_exchange", "market", "exchange"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    market: Mapped[str] = mapped_column(String(8), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    name:   Mapped[str] = mapped_column(String(128), nullable=False)
    exchange:   Mapped[str] = mapped_column(String(32), nullable=False, default="")
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False, default="stock")
    status:     Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    source:     Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
