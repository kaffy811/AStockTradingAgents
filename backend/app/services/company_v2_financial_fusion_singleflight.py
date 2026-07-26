"""Singleflight guard for Company V2 financial evidence fusion."""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(slots=True)
class SingleflightState:
    request_id: str
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
    completed_at: float | None = None


class CompanyV2FinancialFusionSingleflight:
    def __init__(self, *, completed_grace_seconds: float = 10.0) -> None:
        self._lock = threading.Lock()
        self._states: dict[str, SingleflightState] = {}
        self._events: dict[str, threading.Event] = {}
        self._completed_grace_seconds = completed_grace_seconds

    def clear(self) -> None:
        with self._lock:
            self._states.clear()
            self._events.clear()

    def run(self, key: str, work: Callable[[], dict[str, Any]], request_id: str | None = None) -> dict[str, Any]:
        request_id = request_id or str(uuid.uuid4())
        with self._lock:
            existing = self._states.get(key)
            if existing and existing.status == "completed" and existing.completed_at is not None:
                if time.monotonic() - existing.completed_at > self._completed_grace_seconds:
                    self._states.pop(key, None)
                    self._events.pop(key, None)
                    existing = None
            if existing and existing.status in {"running", "completed", "failed"}:
                event = self._events[key]
                reused_request_id = existing.request_id
            else:
                state = SingleflightState(request_id=request_id, status="running")
                self._states[key] = state
                event = self._events[key] = threading.Event()
                reused_request_id = None
                break_run = True
                # satisfy linter-like flow
                if break_run:
                    pass
        if reused_request_id is not None:
            event.wait()
            with self._lock:
                state = self._states.get(key)
                if not state:
                    return {"status": "failed", "error_code": "SINGLEFLIGHT_STATE_LOST", "request_id": reused_request_id}
                if state.status == "failed":
                    return {
                        "status": "failed",
                        "error_code": "SINGLEFLIGHT_LEADER_FAILED",
                        "error": state.error,
                        "singleflight_status": "reused_failed",
                        "singleflight_request_id": reused_request_id,
                    }
                payload = dict(state.result or {})
                payload["singleflight_status"] = "reused"
                payload["singleflight_request_id"] = reused_request_id
                return payload

        try:
            result = work()
            with self._lock:
                self._states[key] = SingleflightState(request_id=request_id, status="completed", result=result, completed_at=time.monotonic())
            return {**result, "singleflight_status": "completed", "singleflight_request_id": request_id}
        except Exception as exc:
            with self._lock:
                self._states[key] = SingleflightState(request_id=request_id, status="failed", error=str(exc)[:500])
            raise
        finally:
            event.set()


company_v2_financial_fusion_singleflight = CompanyV2FinancialFusionSingleflight()
