"""Durable, administrator-only audit records for Report Chat pipelines."""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class ReportAnalysisTrace(Base):
    __tablename__ = "report_analysis_traces"

    trace_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(String(64), nullable=False, unique=True, index=True)
    pipeline_version = Column(String(40), nullable=False)
    git_sha = Column(String(64), nullable=True)
    runtime_image_identity = Column(String(255), nullable=True)
    session_hash = Column(String(64), nullable=True, index=True)
    question_redacted = Column(Text, nullable=True)
    question_hash = Column(String(64), nullable=False)
    market = Column(String(10), nullable=False)
    symbol = Column(String(20), nullable=False, index=True)
    requested_report_id = Column(Integer, nullable=True)
    requested_years = Column(JSONB, nullable=False, default=list)
    final_status = Column(String(40), nullable=False, default="started")
    partial = Column(Boolean, nullable=False, default=False)
    trace_persistence_failed = Column(Boolean, nullable=False, default=False)
    started_at = Column(DateTime(timezone=True), nullable=False, default=lambda: dt.datetime.now(dt.timezone.utc))
    completed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_report_analysis_traces_expires_at", "expires_at"),)


class ReportAnalysisTraceStage(Base):
    __tablename__ = "report_analysis_trace_stages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("report_analysis_traces.trace_id", ondelete="CASCADE"),
        nullable=False,
    )
    stage_name = Column(String(8), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    status = Column(String(24), nullable=False)
    error_code = Column(String(80), nullable=True)
    input_hash = Column(String(64), nullable=True)
    output_hash = Column(String(64), nullable=True)
    input_payload = Column(JSONB, nullable=False, default=dict)
    payload = Column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index("uq_report_analysis_trace_stage", "trace_id", "stage_name", unique=True),
        Index("ix_report_analysis_trace_stage_status", "status"),
    )
