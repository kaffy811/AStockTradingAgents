"""Compact diagnostics sink for Pi shadow acceptance."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.agent_runtime.contracts import utc_now
from app.core.config import settings


def query_hash(value: str | None) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()[:16]


def user_hash(value: str | None) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()[:12] if value else ""


class PiShadowDiagnosticsSink:
    def path(self) -> Path | None:
        raw = str(getattr(settings, "pi_agent_shadow_diagnostics_path", "") or "").strip()
        return Path(raw).expanduser() if raw else None

    def ready(self) -> bool:
        path = self.path()
        if path is None:
            return False
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8"):
                pass
            return True
        except OSError:
            return False

    def record(
        self,
        *,
        raw_query: str,
        conversation_id: str,
        user_id: str,
        result: dict[str, Any],
    ) -> None:
        path = self.path()
        if path is None:
            return
        payload = {
            "schema_version": "pi_shadow_diagnostic_v1",
            "recorded_at": utc_now(),
            "trace_id": result.get("trace_id"),
            "run_id": result.get("run_id"),
            "conversation_id": conversation_id,
            "query_hash": query_hash(raw_query),
            "user_hash": user_hash(user_id),
            "status": result.get("status"),
            "agent_id": result.get("agent_id"),
            "turn_count": result.get("turn_count", 0),
            "tool_call_count": result.get("tool_call_count", 0),
            "llm_call_count": (result.get("metrics") or {}).get("model_calls", 0),
            "metrics": self._compact_metrics(result.get("metrics") or {}),
            "findings": self._compact_findings(result.get("findings") or []),
            "evidence_ids_count": len(result.get("evidence_ids") or []),
            "error_code": (result.get("error") or {}).get("code"),
            "events": self._compact_events(result.get("events") or []),
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        except OSError:
            return

    def _compact_metrics(self, metrics: dict[str, Any]) -> dict[str, Any]:
        return {
            "latency_ms": int(metrics.get("latency_ms") or 0),
            "model_calls": int(metrics.get("model_calls") or 0),
            "tool_calls": int(metrics.get("tool_calls") or 0),
            "input_tokens": int(metrics.get("input_tokens") or 0),
            "output_tokens": int(metrics.get("output_tokens") or 0),
        }

    def _compact_findings(self, findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        compact: list[dict[str, Any]] = []
        for item in findings[:3]:
            compact.append({
                "type": item.get("type"),
                "market": item.get("market"),
                "symbol": item.get("symbol"),
                "company_name": item.get("company_name"),
                "report_year": item.get("report_year"),
                "report_type": item.get("report_type"),
                "source_page_url": item.get("source_page_url"),
                "pdf_url": item.get("pdf_url") or item.get("official_url"),
                "official_domain_verified": bool(item.get("official_domain_verified")),
            })
        return compact

    def _compact_events(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "event_type": event.get("event_type"),
                "timestamp": event.get("timestamp"),
                "sequence": event.get("sequence"),
                "status": (event.get("payload") or {}).get("status"),
            }
            for event in events[:40]
        ]


pi_shadow_diagnostics_sink = PiShadowDiagnosticsSink()
