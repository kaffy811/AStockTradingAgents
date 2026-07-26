"""Runtime event recorder."""
from __future__ import annotations

from typing import Any

from app.agent_runtime.contracts import PiRuntimeEvent


class PiEventRecorder:
    def __init__(self, *, trace_id: str, run_id: str) -> None:
        self.trace_id = trace_id
        self.run_id = run_id
        self._sequence = 0
        self.events: list[PiRuntimeEvent] = []

    def emit(self, event_type: str, payload: dict[str, Any] | None = None) -> PiRuntimeEvent:
        self._sequence += 1
        event = PiRuntimeEvent(
            trace_id=self.trace_id,
            run_id=self.run_id,
            event_type=event_type,
            sequence=self._sequence,
            payload=payload or {},
        )
        self.events.append(event)
        return event

    def public_events(self, *, debug: bool = False) -> list[dict[str, Any]]:
        if debug:
            return [event.to_dict() for event in self.events]
        visible = []
        for event in self.events:
            payload = dict(event.payload)
            for key in ("prompt", "arguments", "tool_args", "provider_secret", "report_id", "chunk_id"):
                payload.pop(key, None)
            item = event.to_dict()
            item["payload"] = payload
            visible.append(item)
        return visible
