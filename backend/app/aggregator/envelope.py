"""
app/aggregator/envelope.py — 统一响应信封（DataEnvelope）

所有 Fundamental Service API 端点均返回 DataEnvelope 格式：

    {
      "ok": true,
      "data": { ... },
      "reason": null,
      "stale": false,
      "partial_errors": [],
      "cached_at": "2026-07-04T10:23:45+08:00"
    }

失败场景：
  - ok=false + reason=<描述> + data=null    （完全失败）
  - ok=true  + partial_errors=[...]         （部分字段缺失，但 data 可用）
  - ok=true  + stale=true                  （返回缓存旧数据，源暂不可用）
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, NotRequired, TypedDict


# ── 类型定义 ─────────────────────────────────────────────────────────────────

class DataEnvelope(TypedDict):
    """
    所有基本面 API 的统一响应信封。

    字段：
        ok            — True 表示 data 非 None（即使部分字段缺失）
        data          — 模块数据（dict / list / None）
        reason        — ok=False 时的原因描述；ok=True 时为 None
        stale         — True 表示数据来自过期缓存（源暂不可用）
        partial_errors — ok=True 但某些子字段解析失败的描述列表
        cached_at     — ISO 8601 带时区时间戳；None 表示直接从源获取（未缓存）
        error_code    — Phase 6N-8A：稳定错误码（DATA_SOURCE_EMPTY /
                        DATA_SOURCE_UNAVAILABLE 等）。仅 provider 类错误使用，
                        绝不承载 AUTH_REQUIRED（auth 走 HTTP 401/403）。
    """
    ok: bool
    data: Any | None
    reason: str | None
    stale: bool
    partial_errors: list[str]
    cached_at: str | None
    error_code: NotRequired[str | None]


# ── 辅助函数 ─────────────────────────────────────────────────────────────────

_CST = timezone(timedelta(hours=8))  # 北京时间 UTC+8


def _now_cst() -> str:
    """返回当前北京时间的 ISO 8601 字符串。"""
    return datetime.now(_CST).isoformat(timespec="seconds")


def ok_envelope(
    data: Any,
    *,
    stale: bool = False,
    cached_at: str | None = None,
    partial_errors: list[str] | None = None,
) -> DataEnvelope:
    """
    构建成功信封。

    Args:
        data:           模块数据（任意可 JSON 序列化的值）
        stale:          是否为过期缓存数据
        cached_at:      缓存时间戳（从 Redis 读取时传入）
        partial_errors: 字段级失败的描述（ok 仍为 True）

    Returns:
        DataEnvelope with ok=True
    """
    return DataEnvelope(
        ok=True,
        data=data,
        reason=None,
        stale=stale,
        partial_errors=partial_errors or [],
        cached_at=cached_at,
    )


def err_envelope(
    reason: str,
    *,
    stale: bool = False,
    cached_at: str | None = None,
    error_code: str | None = None,
) -> DataEnvelope:
    """
    构建失败信封。

    Args:
        reason:     失败原因描述（面向开发者，不直接暴露给用户）
        stale:      是否为过期缓存（失败但仍有旧数据 — 一般不用此组合）
        cached_at:  旧数据的缓存时间
        error_code: Phase 6N-8A 稳定错误码（如 DATA_SOURCE_EMPTY /
                    DATA_SOURCE_UNAVAILABLE），供前端分类展示

    Returns:
        DataEnvelope with ok=False, data=None
    """
    env = DataEnvelope(
        ok=False,
        data=None,
        reason=reason,
        stale=stale,
        partial_errors=[],
        cached_at=cached_at,
    )
    if error_code is not None:
        env["error_code"] = error_code
    return env


_DEFAULT_META: dict = {
    "render_type": "placeholder",
    "chart_type": "none",
    "unit_hints": {},
    "field_labels": {},
    "empty_state": "暂无数据",
}


def build_api_response(
    envelope: DataEnvelope,
    market: str,
    symbol: str,
    ts_code: str,
    module_key: str,
    module_name: str,
    module_meta: dict | None = None,
) -> dict:
    """
    将内部 DataEnvelope 转换为标准化 API 响应格式。

    输出结构：
    {
      "market":      "CN",
      "symbol":      "600519",
      "ts_code":     "600519.SH",
      "module_key":  "valuation",
      "module_name": "估值分位",
      "group":       "财务分析",
      "group_seq":   2,
      "data":        { ... },
      "errors":      [],          # 永远是数组
      "partial":     false,       # 内部部分字段失败
      "stale":       false,
      "generated_at": "2026-07-05T10:23:45+08:00",
      "source": {
        "primary":       "tushare",
        "fallback":      "akshare",
        "akshare_enabled": false,
        "actual":        "tushare"
      },
      "meta": {
        "render_type":  "chart_table",
        "chart_type":   "line",
        "unit_hints":   {...},
        "field_labels": {...},
        "empty_state":  "暂无数据"
      }
    }

    Args:
        envelope:    DataEnvelope from tool or cache
        market:      Market code (CN / HK / US)
        symbol:      Stock symbol
        ts_code:     Tushare ts_code (e.g. 600519.SH)
        module_key:  Module identifier
        module_name: Chinese module name
        module_meta: Optional MODULE_CATALOG entry dict; when provided adds
                     group, group_seq, and meta fields to the response.
                     When None, defaults are used.
    """
    from app.core.config import settings

    data = envelope["data"]

    # 从 data dict 中提取 actual source（不破坏原 dict 内容）
    actual_source = "tushare"
    if isinstance(data, dict):
        actual_source = data.get("source", "tushare")

    # 构建 errors 列表（永远是 list，不为 null）
    errors: list[str] = []
    if not envelope["ok"] and envelope["reason"]:
        errors = [envelope["reason"]]
    elif envelope["partial_errors"]:
        errors = list(envelope["partial_errors"])

    # 提取 group / group_seq / meta 字段
    if module_meta is not None:
        group = module_meta.get("group", "")
        group_seq = module_meta.get("group_seq", 0)
        meta = {
            "render_type":  module_meta.get("render_type", "placeholder"),
            "chart_type":   module_meta.get("chart_type", "none"),
            "unit_hints":   module_meta.get("unit_hints", {}),
            "field_labels": module_meta.get("field_labels", {}),
            "empty_state":  "暂无数据",
        }
    else:
        group = ""
        group_seq = 0
        meta = dict(_DEFAULT_META)

    # When ok=False, data is None — populate with a safe stub so frontend never crashes
    if not envelope["ok"]:
        reason_text = envelope.get("reason") or (errors[0] if errors else "数据源不可用")
        data = {"rows": [], "reasons": [reason_text]}
    elif envelope["partial_errors"] and isinstance(data, dict) and "reasons" not in data:
        # ok=True but partial_errors present — surface reasons into data so frontend
        # can show DataSourceBanner / FundamentalEmptyReason with a useful message.
        data = {**data, "reasons": list(envelope["partial_errors"])}

    return {
        "market":      market.upper(),
        "symbol":      symbol,
        "ts_code":     ts_code,
        "module_key":  module_key,
        "module_name": module_name,
        "group":       group,
        "group_seq":   group_seq,
        "data":        data,
        "errors":      errors,
        # partial=True when ok=False (data unavailable) OR when partial_errors exist
        "partial":     (not envelope["ok"]) or bool(envelope["partial_errors"]),
        "stale":       envelope["stale"],
        "generated_at": _now_cst(),
        "source": {
            "primary":         "tushare",
            "fallback":        "akshare" if settings.enable_akshare else None,
            "akshare_enabled": settings.enable_akshare,
            "actual":          actual_source,
        },
        "meta":        meta,
    }


def from_cache(raw: dict) -> DataEnvelope:
    """
    从 Redis 读取的 JSON 反序列化为 DataEnvelope。
    确保必填字段存在并类型正确。
    """
    return DataEnvelope(
        ok=bool(raw.get("ok", False)),
        data=raw.get("data"),
        reason=raw.get("reason"),
        stale=bool(raw.get("stale", False)),
        partial_errors=list(raw.get("partial_errors") or []),
        cached_at=raw.get("cached_at"),
    )
