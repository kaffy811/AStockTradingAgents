"""
app/models/report_document.py — 上市公司年报/半年报文件索引（Phase 6A）

用于索引从 CNINFO / CSMAR 等公开渠道下载的 PDF 报告文件。
ENABLE_REPORT_PDF=true 时生效；默认关闭，不影响主服务。
"""
import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text

from app.core.database import Base


class ReportDocument(Base):
    """年报/半年报文件索引表。"""

    __tablename__ = "report_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts_code = Column(String(20), nullable=False, index=True, comment="Tushare 股票代码，如 600519.SH")
    report_type = Column(String(20), comment="报告类型: annual / semi / q1 / q3")
    period_end = Column(String(10), comment="报告期截止日 YYYY-MM-DD")
    title = Column(String(200), comment="报告标题")
    source_url = Column(String(500), comment="原始下载 URL")
    local_path = Column(String(500), nullable=True, comment="本地存储路径（S3 key 或文件系统路径）")
    file_sha256 = Column(String(64), nullable=True, comment="文件 SHA-256 校验和")
    text_excerpt = Column(Text, nullable=True, comment="正文摘录（首 5000-8000 字符，用于 AI source_reports）")
    disclosure_date = Column(String(10), nullable=True, comment="披露日 YYYY-MM-DD")
    pdf_url = Column(String(500), nullable=True, comment="直接 PDF 下载 URL")
    report_year = Column(Integer, nullable=True, comment="报告年份，如 2024")
    source = Column(String(20), nullable=True, comment="数据来源: cninfo/sse/szse/manual")
    download_status = Column(String(20), default="pending", comment="下载状态: pending/downloaded/failed")
    confidence = Column(Float, nullable=True, comment="置信度 0-1")
    warnings_json = Column(Text, nullable=True, comment="警告信息 JSON 列表")
    file_size = Column(Integer, nullable=True, comment="文件大小（字节）")
    parse_status = Column(String(20), default="pending", comment="解析状态: pending/parsed/failed")
    download_error = Column(Text, nullable=True, comment="下载错误信息")
    parse_error = Column(Text, nullable=True, comment="解析错误信息")
    parsed = Column(Boolean, default=False, comment="是否已完成 PDF 解析")
    rag_status   = Column(String(20), default="pending", comment="RAG状态: pending/chunked/embedded/failed")
    chunk_count  = Column(Integer, nullable=True, comment="chunk数量")
    rag_error    = Column(Text, nullable=True, comment="RAG错误信息")
    created_at = Column(
        DateTime,
        default=datetime.datetime.utcnow,
        comment="入库时间（UTC）",
    )
