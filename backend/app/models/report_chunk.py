"""
app/models/report_chunk.py — PDF 报告文本 chunks（Phase 6F）

每条 report_documents 记录对应多个 chunks，每个 chunk:
  - 约 800-1200 中文字符
  - 与相邻 chunk 有 100-200 字重叠
  - 生成 SHA-256 content_hash 去重
  - 使用 pgvector 存储 1536 维 embedding
"""
import datetime
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from app.core.database import Base

try:
    from pgvector.sqlalchemy import Vector
    _VECTOR_AVAILABLE = True
except ImportError:
    from sqlalchemy import Text as Vector  # graceful fallback
    _VECTOR_AVAILABLE = False


class ReportChunk(Base):
    __tablename__ = "report_chunks"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    report_id       = Column(Integer, ForeignKey("report_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    ts_code         = Column(String(20), nullable=False, index=True)
    symbol          = Column(String(20), nullable=False)
    market          = Column(String(10), nullable=False, default="CN")
    report_type     = Column(String(20), nullable=True)
    report_year     = Column(Integer, nullable=True)
    period          = Column(String(10), nullable=True)
    chunk_index     = Column(Integer, nullable=False)
    section_title   = Column(String(200), nullable=True)
    page_start      = Column(Integer, nullable=True)
    page_end        = Column(Integer, nullable=True)
    content         = Column(Text, nullable=False)
    content_hash    = Column(String(64), nullable=False, index=True, unique=True)
    embedding       = Column(Vector(1536) if _VECTOR_AVAILABLE else Text, nullable=True)
    embedding_model = Column(String(100), nullable=True)
    token_count     = Column(Integer, nullable=True)
    embed_error     = Column(Text, nullable=True)
    created_at      = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
