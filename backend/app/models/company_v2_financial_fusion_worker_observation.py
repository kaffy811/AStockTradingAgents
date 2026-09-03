"""Shadow worker observations for Company V2 financial fusion."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from app.core.database import Base


class CompanyV2FinancialFusionWorkerObservation(Base):
    __tablename__ = "company_v2_financial_fusion_worker_observations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(64), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    report_id = Column(Integer, nullable=False, index=True)
    worker_id = Column(String(80), nullable=False, index=True)
    observed_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    claimed_at = Column(DateTime, nullable=True)
    released_at = Column(DateTime, nullable=True)
    would_execute = Column(Boolean, nullable=False, default=False)
    block_reason = Column(String(80), nullable=True)
    allowlist_match = Column(Boolean, nullable=False, default=False)
    report_ready = Column(Boolean, nullable=False, default=False)
    rag_ready = Column(Boolean, nullable=False, default=False)
    structured_ready = Column(Boolean, nullable=False, default=False)
    circuit_open = Column(Boolean, nullable=False, default=False)
    auto_run = Column(Boolean, nullable=False, default=False)
    rollout_percent = Column(Integer, nullable=False, default=0)
    stage3_authorized = Column(Boolean, nullable=False, default=False)
    worker_version = Column(String(40), nullable=False, default="phase6tr-shadow-v1")
    execution_mode = Column(String(20), nullable=False, default="shadow")
    provider_calls = Column(Integer, nullable=False, default=0)
    rag_query_calls = Column(Integer, nullable=False, default=0)
    extractor_calls = Column(Integer, nullable=False, default=0)
    fusion_calls = Column(Integer, nullable=False, default=0)
    sanitized_payload_json = Column(Text, nullable=True)
