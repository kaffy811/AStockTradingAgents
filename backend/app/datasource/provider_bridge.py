"""
app/datasource/provider_bridge.py — Provider exception → DataField ReasonCode 映射（Phase 6N-7）

将各数据源的自定义异常统一映射到 DataField.ReasonCode，供 CoverageAuditService
和其他消费方生成结构化的缺失字段记录。

使用方式：
    from app.datasource.provider_bridge import exc_to_reason_code, wrap_provider_call

    try:
        df = await tushare_client.get_daily_basic(ts_code)
    except Exception as exc:
        reason = exc_to_reason_code(exc)
        return DataField.missing(field_name, reason)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, TypeVar

from app.models.data_field import DataField, ReasonCode

log = logging.getLogger(__name__)

_T = TypeVar("_T")


# ── Provider exception → ReasonCode 映射 ──────────────────────────────────────

def exc_to_reason_code(exc: Exception) -> ReasonCode:
    """
    将数据源异常映射到 ReasonCode。

    优先级（从具体到通用）：
      TushareAuthError      → PERMISSION_DENIED
      TushareRateLimitError → RATE_LIMITED
      asyncio.TimeoutError  → PROVIDER_TIMEOUT
      TushareError（其他）  → PROVIDER_EMPTY or NETWORK_UNAVAILABLE
      ConnectionError etc.  → NETWORK_UNAVAILABLE
      其他                  → PROVIDER_EMPTY
    """
    exc_type = type(exc).__name__
    exc_str = str(exc).lower()

    # Tushare specific
    if exc_type == "TushareAuthError":
        return ReasonCode.PERMISSION_DENIED
    if exc_type == "TushareRateLimitError":
        return ReasonCode.RATE_LIMITED
    if exc_type == "TushareError":
        if "token" in exc_str or "未初始化" in str(exc) or "TOKEN" in str(exc):
            return ReasonCode.TOKEN_MISSING
        if "超时" in str(exc) or "timeout" in exc_str:
            return ReasonCode.PROVIDER_TIMEOUT
        return ReasonCode.PROVIDER_EMPTY

    # Generic async / network
    if isinstance(exc, asyncio.TimeoutError):
        return ReasonCode.PROVIDER_TIMEOUT

    if isinstance(exc, (ConnectionError, OSError)):
        return ReasonCode.NETWORK_UNAVAILABLE

    # BaoStock / AkShare specific patterns (string matching)
    if "permission" in exc_str or "权限" in str(exc):
        return ReasonCode.PERMISSION_DENIED
    if "rate" in exc_str or "频率" in str(exc) or "too many" in exc_str:
        return ReasonCode.RATE_LIMITED
    if "timeout" in exc_str or "timed out" in exc_str:
        return ReasonCode.PROVIDER_TIMEOUT
    if "network" in exc_str or "connection" in exc_str:
        return ReasonCode.NETWORK_UNAVAILABLE

    return ReasonCode.PROVIDER_EMPTY


def tushare_is_available() -> bool:
    """
    快速检查 TushareClient 是否已初始化（token 存在）。
    不发起网络请求，纯粹检查内存状态。
    """
    try:
        from app.datasource.tushare_client import tushare_client
        return tushare_client.is_available
    except Exception:
        return False


async def wrap_provider_call(
    field_name: str,
    provider_name: str,
    coro_fn: Callable[[], Awaitable[_T]],
    *,
    as_of: str = "",
    fiscal_period: str = "",
) -> tuple[_T | None, DataField | None]:
    """
    调用数据源协程，捕获异常并返回 (result, error_field)。

    返回值：
      (result, None)          — 成功，error_field 为 None
      (None,   DataField)     — 失败，result 为 None，error_field 含 reason_code

    使用方式：
        val, err = await wrap_provider_call(
            "pe_ttm", "tushare_daily_basic",
            lambda: tushare_client.get_daily_basic(ts_code),
        )
        if err:
            return err
        # use val
    """
    try:
        if not tushare_is_available() and provider_name.startswith("tushare"):
            return None, DataField.disabled(field_name, ReasonCode.TOKEN_MISSING)
        result = await coro_fn()
        return result, None
    except Exception as exc:
        reason = exc_to_reason_code(exc)
        log.warning(
            "provider %s field %s failed: %s [reason=%s]",
            provider_name, field_name, repr(exc), reason.value,
        )
        return None, DataField(
            field_name=field_name,
            value=None,
            status=__import__("app.models.data_field", fromlist=["DataFieldStatus"]).DataFieldStatus.PROVIDER_FAILED,
            source=provider_name,
            reason_code=reason,
            attempted_sources=[provider_name],
            provider_errors={provider_name: repr(exc)},
            as_of=as_of,
            fiscal_period=fiscal_period,
        )
