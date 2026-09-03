from __future__ import annotations

import contextvars
import json
import logging
import time
import uuid
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.config import settings

log = logging.getLogger("company_v2_debug")

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)

_SENSITIVE_KEYS = ("secret", "token", "api_key", "authorization", "password", "local_path")


def current_request_id() -> str:
    return request_id_var.get() or str(uuid.uuid4())


def sanitize_debug_payload(value: Any, *, max_chars: int = 2000) -> Any:
    def _clean(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {
                str(k): ("[redacted]" if any(s in str(k).lower() for s in _SENSITIVE_KEYS) else _clean(v))
                for k, v in obj.items()
                if "local_path" not in str(k).lower()
            }
        if isinstance(obj, list):
            return [_clean(v) for v in obj[:20]]
        if isinstance(obj, (str, int, float, bool)) or obj is None:
            return obj
        return str(obj)

    cleaned = _clean(value)
    raw = json.dumps(cleaned, ensure_ascii=False, default=str)
    if len(raw) <= max_chars:
        return cleaned
    return {"preview": raw[:max_chars], "truncated": True, "chars": len(raw)}


def log_provider_event(event: dict[str, Any]) -> None:
    if not getattr(settings, "debug_company_v2", False):
        return
    safe = sanitize_debug_payload(event, max_chars=getattr(settings, "company_v2_raw_preview_chars", 2000))
    log.info(json.dumps(safe, ensure_ascii=False, default=str))


def log_company_v2_event(event: dict[str, Any]) -> dict[str, Any]:
    safe = sanitize_debug_payload(event, max_chars=getattr(settings, "company_v2_raw_preview_chars", 2000))
    if getattr(settings, "debug_company_v2", False):
        log.info(json.dumps(safe, ensure_ascii=False, default=str))
    return safe


class CompanyV2RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api/v2/company/"):
            return await call_next(request)

        rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_var.set(rid)
        started = time.monotonic()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = rid
            if getattr(settings, "debug_company_v2", False):
                log.info(json.dumps({
                    "request_id": rid,
                    "path": request.url.path,
                    "status": response.status_code,
                    "latency_ms": int((time.monotonic() - started) * 1000),
                }, ensure_ascii=False))
            return response
        finally:
            request_id_var.reset(token)
