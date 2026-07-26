"""
app/models/data_field.py — 统一字段级数据结构（Phase 6N-6）

DataField 是贯穿整个数据管道的统一字段容器：
  - 记录每个字段的值、来源、状态、计算公式、依赖链
  - 为前端提供透明的数据溯源信息
  - 让 CoverageAuditService 能按字段统计完整率
  - 不直接写 DB（用 DataCoverageSnapshot 落库）

使用方式：
    field = DataField(
        field_name="market_cap",
        value=123456789,
        status=DataFieldStatus.COMPUTED,
        source="computed",
        formula="latest_price * total_share",
        dependencies=["latest_price", "total_share"],
        as_of="2024-01-15",
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── Status 枚举 ────────────────────────────────────────────────────────────────

class DataFieldStatus(str, Enum):
    OK               = "ok"               # 数据来自真实源，有效
    COMPUTED         = "computed"         # 由其他字段计算得出
    ESTIMATED        = "estimated"        # 估算值（非精确源）
    MISSING          = "missing"          # 字段不存在或未返回
    STALE            = "stale"            # 数据来自缓存，可能过期
    PROVIDER_FAILED  = "provider_failed"  # 所有数据源均失败
    DISABLED         = "disabled"         # 功能已禁用（如 token 未配置）


# ── ReasonCode 枚举 ────────────────────────────────────────────────────────────

class ReasonCode(str, Enum):
    # 网络 / 提供商错误
    PROVIDER_TIMEOUT        = "PROVIDER_TIMEOUT"
    PROVIDER_REMOTE_CLOSED  = "PROVIDER_REMOTE_CLOSED"
    PROVIDER_EMPTY          = "PROVIDER_EMPTY"
    NETWORK_UNAVAILABLE     = "NETWORK_UNAVAILABLE"
    RATE_LIMITED            = "RATE_LIMITED"

    # 认证 / 权限
    AUTH_REQUIRED           = "AUTH_REQUIRED"
    TOKEN_MISSING           = "TOKEN_MISSING"
    PERMISSION_DENIED       = "PERMISSION_DENIED"

    # 字段 / 数据质量
    FIELD_MISSING           = "FIELD_MISSING"
    FIELD_MISSING_DEPENDENCY = "FIELD_MISSING_DEPENDENCY"
    NOT_DISCLOSED           = "NOT_DISCLOSED"
    REPORT_NOT_FOUND        = "REPORT_NOT_FOUND"
    NOT_IMPLEMENTED         = "NOT_IMPLEMENTED"
    COLUMN_RENAMED          = "COLUMN_RENAMED"

    # RAG
    RAG_NOT_INDEXED         = "RAG_NOT_INDEXED"
    REPORT_NOT_INGESTED     = "REPORT_NOT_INGESTED"

    # 缓存
    CACHE_UNAVAILABLE       = "CACHE_UNAVAILABLE"


# ── DataField 主结构 ───────────────────────────────────────────────────────────

@dataclass
class DataField:
    """
    每个数据字段的统一容器。

    字段说明：
      value            — 字段值（None 表示缺失）
      status           — DataFieldStatus 枚举
      field_name       — 字段逻辑名称（与 CoreFieldRegistry 对应）
      source           — 实际数据源（如 "baostock"/"tushare"/"computed"/"kline_proxy"）
      source_priority  — 数据源优先级序号（1=最优先）
      as_of            — 数据对应日期（YYYY-MM-DD）
      fiscal_period    — 财报期（如 "20231231"），quote/kline 留空
      is_stale         — 来自 stale cache
      is_estimated     — 估算值标记
      formula          — 计算字段的公式字符串（如 "net_profit / revenue"）
      dependencies     — 计算所依赖的字段名列表
      reason_code      — ReasonCode 枚举，status!=ok 时必填
      attempted_sources — 依次尝试过的数据源列表
      provider_errors   — {source: error_message} 映射
    """
    field_name:        str
    value:             Any                   = None
    status:            DataFieldStatus       = DataFieldStatus.MISSING
    source:            str                   = ""
    source_priority:   int                   = 0
    as_of:             str                   = ""
    fiscal_period:     str                   = ""
    is_stale:          bool                  = False
    is_estimated:      bool                  = False
    formula:           str                   = ""
    dependencies:      list[str]             = field(default_factory=list)
    reason_code:       ReasonCode | None     = None
    attempted_sources: list[str]             = field(default_factory=list)
    provider_errors:   dict[str, str]        = field(default_factory=dict)

    # ── 便捷工厂方法 ──────────────────────────────────────────────────────────

    @classmethod
    def ok(
        cls,
        field_name: str,
        value: Any,
        source: str,
        *,
        as_of: str = "",
        fiscal_period: str = "",
        source_priority: int = 1,
        is_stale: bool = False,
    ) -> "DataField":
        return cls(
            field_name=field_name,
            value=value,
            status=DataFieldStatus.STALE if is_stale else DataFieldStatus.OK,
            source=source,
            source_priority=source_priority,
            as_of=as_of,
            fiscal_period=fiscal_period,
            is_stale=is_stale,
        )

    @classmethod
    def computed(
        cls,
        field_name: str,
        value: Any,
        formula: str,
        dependencies: list[str],
        *,
        as_of: str = "",
        fiscal_period: str = "",
    ) -> "DataField":
        return cls(
            field_name=field_name,
            value=value,
            status=DataFieldStatus.COMPUTED,
            source="computed",
            formula=formula,
            dependencies=dependencies,
            as_of=as_of,
            fiscal_period=fiscal_period,
        )

    @classmethod
    def missing(
        cls,
        field_name: str,
        reason_code: ReasonCode = ReasonCode.FIELD_MISSING,
        *,
        attempted_sources: list[str] | None = None,
        provider_errors: dict[str, str] | None = None,
    ) -> "DataField":
        return cls(
            field_name=field_name,
            value=None,
            status=DataFieldStatus.MISSING,
            reason_code=reason_code,
            attempted_sources=attempted_sources or [],
            provider_errors=provider_errors or {},
        )

    @classmethod
    def provider_failed(
        cls,
        field_name: str,
        attempted_sources: list[str],
        provider_errors: dict[str, str],
        *,
        reason_code: ReasonCode = ReasonCode.PROVIDER_EMPTY,
    ) -> "DataField":
        return cls(
            field_name=field_name,
            value=None,
            status=DataFieldStatus.PROVIDER_FAILED,
            reason_code=reason_code,
            attempted_sources=attempted_sources,
            provider_errors=provider_errors,
        )

    @classmethod
    def disabled(
        cls,
        field_name: str,
        reason_code: ReasonCode = ReasonCode.TOKEN_MISSING,
    ) -> "DataField":
        return cls(
            field_name=field_name,
            value=None,
            status=DataFieldStatus.DISABLED,
            reason_code=reason_code,
        )

    # ── 属性快捷方法 ──────────────────────────────────────────────────────────

    @property
    def has_value(self) -> bool:
        return self.value is not None

    @property
    def is_ok(self) -> bool:
        return self.status in (DataFieldStatus.OK, DataFieldStatus.COMPUTED, DataFieldStatus.ESTIMATED)

    def to_dict(self) -> dict:
        return {
            "field_name":        self.field_name,
            "value":             self.value,
            "status":            self.status.value,
            "source":            self.source,
            "source_priority":   self.source_priority,
            "as_of":             self.as_of,
            "fiscal_period":     self.fiscal_period,
            "is_stale":          self.is_stale,
            "is_estimated":      self.is_estimated,
            "formula":           self.formula,
            "dependencies":      self.dependencies,
            "reason_code":       self.reason_code.value if self.reason_code else None,
            "attempted_sources": self.attempted_sources,
            "provider_errors":   self.provider_errors,
        }
