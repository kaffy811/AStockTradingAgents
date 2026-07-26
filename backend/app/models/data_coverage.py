"""
app/models/data_coverage.py — 数据覆盖率快照 ORM 模型（Phase 6N-6）

三张表：
  data_coverage_snapshot  — 每只股票每交易日的字段完整率汇总快照
  provider_error_log      — 数据源错误日志（按字段/Provider/日期）
  missing_field_queue     — 缺失字段回填任务队列
"""

import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, Integer, String, Text,
    UniqueConstraint, func,
)

from app.core.database import Base


class DataCoverageSnapshot(Base):
    """
    每只股票每交易日的字段完整率快照。

    ON CONFLICT (ts_code, trade_date) DO UPDATE — 重跑时覆盖而非堆叠。
    """

    __tablename__ = "data_coverage_snapshot"
    __table_args__ = (
        UniqueConstraint("ts_code", "trade_date", name="uq_coverage_ts_date"),
    )

    id                    = Column(Integer, primary_key=True, autoincrement=True)
    ts_code               = Column(String(20), nullable=False, index=True,
                                   comment="Tushare 股票代码，如 000725.SZ")
    trade_date            = Column(String(10), nullable=False, index=True,
                                   comment="交易日 YYYY-MM-DD")
    overall_completeness  = Column(Float, default=0.0,
                                   comment="全字段完整率 0.0–1.0")
    quote_completeness    = Column(Float, default=0.0,
                                   comment="行情字段完整率")
    valuation_completeness= Column(Float, default=0.0,
                                   comment="估值字段完整率")
    financial_completeness= Column(Float, default=0.0,
                                   comment="财务字段平均完整率（income/balance/cashflow/indicators）")
    rag_status            = Column(String(20), default="unknown",
                                   comment="RAG 状态：ready / not_indexed / empty / unknown")
    missing_field_count   = Column(Integer, default=0,
                                   comment="缺失字段总数")
    generated_at          = Column(DateTime, server_default=func.now(),
                                   onupdate=func.now(),
                                   comment="审计生成时间（UTC）")


class ProviderErrorLog(Base):
    """
    数据源错误日志。

    每次数据获取失败时追加一条记录，供后续 SLA 统计和告警使用。
    """

    __tablename__ = "provider_error_log"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    ts_code      = Column(String(20), nullable=False, index=True,
                          comment="Tushare 股票代码")
    field_name   = Column(String(64), nullable=False, index=True,
                          comment="出错的字段名（CORE_FIELDS key）")
    provider     = Column(String(64), nullable=False,
                          comment="数据源名称，如 tushare_daily_basic / baostock")
    reason_code  = Column(String(64), nullable=True,
                          comment="ReasonCode 枚举值")
    error_detail = Column(Text, nullable=True,
                          comment="原始错误信息（repr(exc)）")
    trade_date   = Column(String(10), nullable=True, index=True,
                          comment="数据对应交易日")
    logged_at    = Column(DateTime, server_default=func.now(),
                          comment="日志记录时间（UTC）")
    retry_count  = Column(Integer, default=0,
                          comment="已重试次数")
    resolved     = Column(Boolean, default=False,
                          comment="是否已通过后续 backfill 解决")


class MissingFieldQueue(Base):
    """
    缺失字段回填任务队列。

    CoverageAuditService 在发现字段缺失后写入此表，
    后台 backfill worker 轮询 status='pending' 条目进行补填。
    """

    __tablename__ = "missing_field_queue"
    __table_args__ = (
        UniqueConstraint("ts_code", "field_name", "trade_date",
                         name="uq_missing_field_ts_field_date"),
    )

    id           = Column(Integer, primary_key=True, autoincrement=True)
    ts_code      = Column(String(20), nullable=False, index=True,
                          comment="Tushare 股票代码")
    field_name   = Column(String(64), nullable=False, index=True,
                          comment="缺失的字段名")
    reason_code  = Column(String(64), nullable=True,
                          comment="缺失原因 ReasonCode")
    trade_date   = Column(String(10), nullable=False, index=True,
                          comment="缺失对应的交易日")
    retry_count  = Column(Integer, default=0,
                          comment="已重试次数")
    status       = Column(String(20), default="pending", index=True,
                          comment="任务状态：pending / in_progress / done / failed")
    last_attempt = Column(DateTime, nullable=True,
                          comment="最后一次尝试时间（UTC）")
    error_detail = Column(Text, nullable=True,
                          comment="最后一次失败的错误信息")
    created_at   = Column(DateTime, server_default=func.now(),
                          comment="任务创建时间（UTC）")
    updated_at   = Column(DateTime, server_default=func.now(),
                          onupdate=func.now(),
                          comment="任务最后更新时间（UTC）")
