from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, field_validator
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


# ── ORM model ─────────────────────────────────────────────────────────────────

class AnalysisReport(Base):
    __tablename__ = "analysis_reports"

    __table_args__ = (
        Index("idx_reports_user_created", "user_id", "created_at"),
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
    market: Mapped[str] = mapped_column(String(8), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    report_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="comprehensive"
    )
    stock_name:     Mapped[str | None] = mapped_column(String(128), nullable=True)
    auto_saved:     Mapped[bool]       = mapped_column(Boolean,     nullable=False, default=False, server_default='false')
    analysis_scope:  Mapped[str] = mapped_column(String(32), nullable=False, default='comprehensive', server_default='comprehensive')
    output_language: Mapped[str] = mapped_column(String(16), nullable=False, default='zh-CN',          server_default='zh-CN')
    report_md: Mapped[str] = mapped_column(Text, nullable=False)
    sections: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    report_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    warnings: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    agents: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
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

class ReportCreateRequest(BaseModel):
    market:          str
    symbol:          str
    report_type:     str = "comprehensive"
    stock_name:      str | None = None
    auto_saved:      bool = False
    analysis_scope:  str = "comprehensive"
    output_language: str = "zh-CN"
    report_md:       str
    sections:        dict[str, str]
    report_metadata: dict
    warnings:        list[str] = []
    agents:          dict[str, dict]

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


class ReportCreateResponse(BaseModel):
    id:         uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class ReportListItem(BaseModel):
    id:              uuid.UUID
    market:          str
    symbol:          str
    report_type:     str
    stock_name:      str | None = None
    auto_saved:      bool = False
    analysis_scope:  str = "comprehensive"
    output_language: str = "zh-CN"
    warnings:        list[str]
    agents:          dict[str, dict]
    created_at:      datetime

    model_config = {"from_attributes": True}


class ReportListResponse(BaseModel):
    total: int
    items: list[ReportListItem]


class ReportDetailResponse(BaseModel):
    id:              uuid.UUID
    market:          str
    symbol:          str
    report_type:     str
    stock_name:      str | None = None
    auto_saved:      bool = False
    analysis_scope:  str = "comprehensive"
    output_language: str = "zh-CN"
    report_md:       str
    sections:        dict[str, str]
    report_metadata: dict
    warnings:        list[str]
    agents:          dict[str, dict]
    created_at:      datetime
    updated_at:      datetime

    model_config = {"from_attributes": True}
