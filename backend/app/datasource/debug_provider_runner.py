from __future__ import annotations

import asyncio
import inspect
import time
from datetime import datetime, timezone
from typing import Any, Callable

from app.core.structured_debug_logger import current_request_id, log_provider_event, sanitize_debug_payload


def _classify_exception(exc: Exception) -> str:
    msg = repr(exc).lower()
    if "timeout" in msg:
        return "PROVIDER_TIMEOUT"
    if any(k in msg for k in ("connection", "remote", "refused", "proxy", "network", "unreachable")):
        return "PROVIDER_NETWORK_ERROR"
    if any(k in msg for k in ("column", "schema", "keyerror")):
        return "PROVIDER_SCHEMA_CHANGED"
    return "PROVIDER_EXCEPTION"


def _status_from_error_code(error_code: str | None) -> str:
    if error_code is None:
        return "success"
    if error_code == "PROVIDER_TIMEOUT":
        return "timeout"
    if error_code == "PROVIDER_NETWORK_ERROR":
        return "network_error"
    if error_code == "PROVIDER_SCHEMA_CHANGED":
        return "schema_error"
    if error_code == "PROVIDER_EMPTY":
        return "empty"
    return "exception"


def _non_null_fields(rows: list[dict[str, Any]]) -> list[str]:
    fields: set[str] = set()
    for row in rows:
        for key, value in row.items():
            if value not in (None, "", "—", "--"):
                fields.add(str(key))
    return sorted(fields)


def _dataframe_payload(raw: Any, include_raw: bool, max_raw_chars: int) -> dict[str, Any] | None:
    try:
        import pandas as pd  # type: ignore
    except Exception:
        pd = None
    if pd is None or not isinstance(raw, pd.DataFrame):
        return None
    sample = raw.head(5).where(raw.notna(), None).to_dict(orient="records")
    payload = {
        "raw_type": "DataFrame",
        "raw_shape": [int(raw.shape[0]), int(raw.shape[1])],
        "columns": [str(c) for c in raw.columns],
        "raw_sample": sanitize_debug_payload(sample, max_chars=max_raw_chars),
        "rows_count": int(raw.shape[0]),
    }
    if include_raw:
        payload["raw_full"] = sanitize_debug_payload(
            raw.where(raw.notna(), None).to_dict(orient="records"),
            max_chars=max_raw_chars,
        )
    return payload


def _rows_payload(raw: Any, include_raw: bool, max_raw_chars: int) -> dict[str, Any]:
    raw_type = type(raw).__name__
    if raw is None:
        rows: list[dict[str, Any]] = []
    elif isinstance(raw, tuple) and raw and isinstance(raw[0], dict):
        rows = [raw[0], raw[1] if len(raw) > 1 and isinstance(raw[1], dict) else {}]
    elif isinstance(raw, dict):
        rows = [raw]
    elif isinstance(raw, list):
        rows = [r if isinstance(r, dict) else {"value": r} for r in raw]
    elif hasattr(raw, "json"):
        try:
            body = raw.json()
        except Exception:
            body = getattr(raw, "text", "")[:max_raw_chars]
        rows = [body] if isinstance(body, dict) else [{"preview": body}]
    else:
        rows = [{"value": str(raw)}]

    columns = sorted({str(k) for row in rows if isinstance(row, dict) for k in row.keys()})
    payload = {
        "raw_type": raw_type,
        "raw_shape": [len(rows), len(columns)],
        "columns": columns,
        "raw_sample": sanitize_debug_payload(rows[:5], max_chars=max_raw_chars),
        "rows_count": len(rows),
    }
    if include_raw:
        payload["raw_full"] = sanitize_debug_payload(rows, max_chars=max_raw_chars)
    return payload


async def run_provider_with_debug(
    provider_name: str,
    endpoint_name: str,
    fn: Callable[..., Any],
    args: tuple[Any, ...] | None = None,
    kwargs: dict[str, Any] | None = None,
    *,
    include_raw: bool = False,
    max_raw_chars: int = 20000,
    request_id: str | None = None,
    symbol: str | None = None,
    module_key: str | None = None,
    cache_hit: bool = False,
    cache_stale: bool = False,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()
    args = args or ()
    kwargs = kwargs or {}
    result: dict[str, Any] = {
        "provider": provider_name,
        "endpoint": endpoint_name,
        "attempted": True,
        "success": False,
        "raw_type": None,
        "raw_shape": None,
        "columns": [],
        "raw_sample": [],
        "rows_count": 0,
        "status": "exception",
        "started_at": started_at,
        "ended_at": None,
        "elapsed_ms": 0,
        "latency_ms": 0,
        "error_code": None,
        "error_message": None,
        "cache_hit": cache_hit,
        "cache_stale": cache_stale,
        "detached_timeout": False,
    }
    is_async_callable = inspect.iscoroutinefunction(fn)

    async def _call_provider() -> Any:
        if is_async_callable:
            return await fn(*args, **kwargs)
        value = await asyncio.to_thread(fn, *args, **kwargs)
        return await value if inspect.isawaitable(value) else value

    try:
        if timeout_seconds and timeout_seconds > 0:
            raw = await asyncio.wait_for(_call_provider(), timeout=timeout_seconds)
        else:
            raw = await _call_provider()
        df_payload = _dataframe_payload(raw, include_raw, max_raw_chars)
        payload = df_payload or _rows_payload(raw, include_raw, max_raw_chars)
        result.update(payload)
        result["success"] = result["rows_count"] > 0
        if not result["success"]:
            result["error_code"] = "PROVIDER_EMPTY"
            result["error_message"] = "provider returned no rows"
        result["status"] = _status_from_error_code(result.get("error_code"))
        result["non_null_fields"] = _non_null_fields(
            payload.get("raw_full") if isinstance(payload.get("raw_full"), list) else payload.get("raw_sample", [])
        )
        return result
    except asyncio.TimeoutError as exc:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        result["error_code"] = "PROVIDER_TIMEOUT"
        result["status"] = "timeout"
        result["latency_ms"] = int((timeout_seconds or 0) * 1000) if timeout_seconds else elapsed_ms
        result["elapsed_ms"] = result["latency_ms"]
        result["error_message"] = f"Provider call exceeded {timeout_seconds:g}s" if timeout_seconds else "provider timeout"
        result["detached_timeout"] = not is_async_callable
        return result
    except Exception as exc:
        error_code = _classify_exception(exc)
        result["error_code"] = error_code
        result["status"] = _status_from_error_code(error_code)
        result["error_message"] = str(exc)[:500]
        return result
    finally:
        ended_at = datetime.now(timezone.utc).isoformat()
        elapsed_ms = int((time.monotonic() - started) * 1000)
        result["ended_at"] = ended_at
        if result.get("latency_ms", 0) <= 0:
            result["latency_ms"] = elapsed_ms
        if result.get("elapsed_ms", 0) <= 0:
            result["elapsed_ms"] = result["latency_ms"]
        log_provider_event({
            "request_id": request_id or current_request_id(),
            "symbol": symbol,
            "module_key": module_key,
            "provider": provider_name,
            "endpoint": endpoint_name,
            "status": result.get("status"),
            "rows_count": result.get("rows_count", 0),
            "columns_count": len(result.get("columns") or []),
            "latency_ms": result.get("latency_ms", 0),
            "cache_hit": cache_hit,
            "cache_stale": cache_stale,
            "error_code": result.get("error_code"),
            "detached_timeout": result.get("detached_timeout", False),
            "raw_preview": result.get("raw_sample"),
        })
