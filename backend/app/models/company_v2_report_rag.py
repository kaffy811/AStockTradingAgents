"""Company V2 single-report RAG models.

These models describe the Phase 6T-D report QA index. The service layer keeps a
repository abstraction so storage can move from JSON/in-memory to PostgreSQL or
pgvector without changing chunking/retrieval contracts.
"""
from __future__ import annotations

import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from app.core.database import Base


class ReportRagDocument(Base):
    """Indexed CNINFO report document metadata."""

    __tablename__ = "company_v2_report_rag_documents"
    __table_args__ = (
        # One row per (report, generation); superseded generations are kept for audit.
        UniqueConstraint(
            "report_id",
            "index_generation",
            name="uq_company_v2_rag_doc_generation",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(Integer, nullable=False, index=True)
    market = Column(String(10), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    company_name = Column(String(200), nullable=True)
    report_year = Column(Integer, nullable=False, index=True)
    report_type = Column(String(30), nullable=False, index=True)
    announcement_date = Column(String(20), nullable=True)
    source_url = Column(String(500), nullable=False)
    pdf_hash = Column(String(80), nullable=True)
    parse_version = Column(String(50), nullable=False)
    page_count = Column(Integer, nullable=False, default=0)
    chunk_count = Column(Integer, nullable=False, default=0)
    embedding_model = Column(String(100), nullable=True)
    embedding_version = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    active_index = Column(Integer, nullable=False, default=1)
    supersedes_rag_document_id = Column(Integer, nullable=True)
    stale_reason = Column(Text, nullable=True)
    indexed_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    index_generation = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class ReportRagChunk(Base):
    """Page-grounded chunk for one indexed report."""

    __tablename__ = "company_v2_report_rag_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rag_document_id = Column(Integer, ForeignKey("company_v2_report_rag_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    report_id = Column(Integer, nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    page_start = Column(Integer, nullable=False)
    page_end = Column(Integer, nullable=False)
    section_title = Column(String(300), nullable=True)
    text = Column(Text, nullable=False)
    text_hash = Column(String(64), nullable=False, index=True)
    token_count = Column(Integer, nullable=False, default=0)
    embedding = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
