"""Persistent jobs for Company V2 financial fusion manual rollout."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text

from app.core.database import Base


class CompanyV2FinancialFusionJob(Base):
    __tablename__ = "company_v2_financial_fusion_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(64), nullable=False, unique=True, index=True)
    market = Column(String(10), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    report_id = Column(Integer, nullable=False, index=True)
    report_year = Column(Integer, nullable=True)
    report_type = Column(String(30), nullable=True)
    requested_fields_json = Column(Text, nullable=False)
    request_fingerprint = Column(String(96), nullable=False, index=True)
    requester_scope = Column(String(60), nullable=False, default="manual")
    status = Column(String(30), nullable=False, default="queued", index=True)
    progress = Column(Float, nullable=False, default=0.0)
    current_stage = Column(String(60), nullable=False, default="queued")
    cache_hit = Column(Integer, nullable=False, default=0)
    result_id = Column(String(120), nullable=True)
    result_json = Column(Text, nullable=True)
    error_code = Column(String(80), nullable=True)
    error_message = Column(Text, nullable=True)
    retryable = Column(Integer, nullable=False, default=0)
    repository_backend = Column(String(40), nullable=True)
    extractor_version = Column(String(80), nullable=True)
    cache_key = Column(String(140), nullable=True)
    cache_key_version = Column(String(40), nullable=True)
    active_generation = Column(Integer, nullable=True)
    timings_json = Column(Text, nullable=True)
    requester_metadata_json = Column(Text, nullable=True)
    claimed_by = Column(String(80), nullable=True)
    claimed_at = Column(DateTime, nullable=True)
    heartbeat_at = Column(DateTime, nullable=True)
    lease_expires_at = Column(DateTime, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    next_retry_at = Column(DateTime, nullable=True)
    execution_mode = Column(String(20), nullable=True)
    worker_version = Column(String(40), nullable=True)
    rollout_bucket_at_claim = Column(Integer, nullable=True)
    rollout_percent_at_claim = Column(Integer, nullable=True)
    auto_run_at_claim = Column(Boolean, nullable=True)
    last_error_message_sanitized = Column(Text, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow, nullable=False)
