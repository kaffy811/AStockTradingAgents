"""Compact diagnostics sink for Pi shadow acceptance.

Storage contract (v2):
- Every record still appends one JSONL line for human audit (append-only).
- When the record carries a shadow run identity, an additional per-run file
  ``<jsonl_path>.runs/<run_id>.json`` is written atomically (tmp + os.replace).
- A terminal per-run record is written exactly once: a later record for the
  same run_id can never overwrite an existing terminal record; the stale
  write is preserved in the JSONL stream with ``stale_terminal_ignored``.
- Readers must address records by ``run_id`` (see :meth:`read_run`); matching
  by recency / conversation / query hash is forbidden for acceptance gating.
- No full query text, prompt, token or chain-of-thought is ever stored.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from app.agent_runtime.contracts import utc_now
from app.core.config import settings


DIAGNOSTICS_RECORD_VERSION = 2


def query_hash(value: str | None) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()[:16]


def user_hash(value: str | None) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()[:12] if value else ""


def stable_payload_hash(value: Any) -> str:
    payload = json.dumps(value or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def record_checksum(payload: dict[str, Any]) -> str:
    core = {
        "trace_id": payload.get("trace_id"),
        "run_id": payload.get("run_id"),
        "status": payload.get("status"),
        "error_code": payload.get("error_code"),
        "input_snapshot_hash": payload.get("input_snapshot_hash"),
        "terminal_sequence": payload.get("terminal_sequence"),
    }
    return hashlib.sha256(
        json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]


class PiShadowDiagnosticsSink:
    def path(self) -> Path | None:
        raw = str(getattr(settings, "pi_agent_shadow_diagnostics_path", "") or "").strip()
        return Path(raw).expanduser() if raw else None

    def runs_dir(self) -> Path | None:
        path = self.path()
        if path is None:
            return None
        return path.parent / (path.name + ".runs")

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
        correlation: dict[str, Any] | None = None,
    ) -> None:
        path = self.path()
        if path is None:
            return
        envelope = {
            key: value
            for key, value in (correlation or {}).items()
            if key in {
                "acceptance_run_id",
                "case_id",
                "case_attempt",
                "turn_id",
                "request_trace_id",
                "legacy_run_id",
                "shadow_run_id",
                "input_snapshot_hash",
            }
            and value not in (None, "")
        }
        payload = {
            "schema_version": "pi_shadow_diagnostic_v1",
            "diagnostics_record_version": DIAGNOSTICS_RECORD_VERSION,
            "recorded_at": utc_now(),
            "written_at": utc_now(),
            "trace_id": result.get("trace_id"),
            "run_id": result.get("run_id") or envelope.get("shadow_run_id"),
            "conversation_id": conversation_id,
            "query_hash": query_hash(raw_query),
            "user_hash": user_hash(user_id),
            "status": result.get("status"),
            "terminal": True,
            "terminal_sequence": 1,
            "completed_at": utc_now(),
            "agent_id": result.get("agent_id"),
            "turn_count": result.get("turn_count", 0),
            "tool_call_count": result.get("tool_call_count", 0),
            "llm_call_count": (result.get("metrics") or {}).get("model_calls", 0),
            "metrics": self._compact_metrics(result.get("metrics") or {}),
            "findings": self._compact_findings(result.get("findings") or []),
            "structured_answer_compact": self._compact_structured_answer(result.get("structured_answer") or {}),
            "evidence_ids_count": len(result.get("evidence_ids") or []),
            "error_code": (result.get("error") or {}).get("code"),
            "events": self._compact_events(result.get("events") or []),
            "input_snapshot_hash": stable_payload_hash(result.get("shadow_input") or {}),
            "side_effect_count": int(result.get("side_effect_count") or 0),
            "correlation": envelope,
        }
        payload["checksum"] = record_checksum(payload)
        stale = False
        run_id = payload.get("run_id")
        if run_id:
            stale = not self._write_run_record(str(run_id), payload)
        if stale:
            payload = {**payload, "stale_terminal_ignored": True}
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        except OSError:
            return

    def _write_run_record(self, run_id: str, payload: dict[str, Any]) -> bool:
        """Write the per-run terminal record exactly once.

        Returns True when this payload became the terminal record; False when a
        terminal record already existed (stale write must be ignored by readers).
        """
        runs_dir = self.runs_dir()
        if runs_dir is None:
            return True
        safe_run_id = "".join(ch for ch in run_id if ch.isalnum() or ch in "_-")[:64]
        if not safe_run_id:
            return True
        try:
            runs_dir.mkdir(parents=True, exist_ok=True)
            target = runs_dir / f"{safe_run_id}.json"
            existing = self.read_run(safe_run_id)
            if existing is not None and existing.get("terminal") is True:
                return False
            tmp = runs_dir / f".{safe_run_id}.{os.getpid()}.tmp"
            tmp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
            os.replace(tmp, target)
            return True
        except OSError:
            return True

    def read_run(self, run_id: str) -> dict[str, Any] | None:
        runs_dir = self.runs_dir()
        if runs_dir is None:
            return None
        safe_run_id = "".join(ch for ch in run_id if ch.isalnum() or ch in "_-")[:64]
        target = runs_dir / f"{safe_run_id}.json"
        if not target.exists():
            return None
        try:
            return json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _compact_metrics(self, metrics: dict[str, Any]) -> dict[str, Any]:
        return {
            "latency_ms": int(metrics.get("latency_ms") or 0),
            "model_calls": int(metrics.get("model_calls") or 0),
            "tool_calls": int(metrics.get("tool_calls") or 0),
            "input_tokens": int(metrics.get("input_tokens") or 0),
            "output_tokens": int(metrics.get("output_tokens") or 0),
            "tool_latency_breakdown": {
                str(key): int(value or 0)
                for key, value in (metrics.get("tool_latency_breakdown") or {}).items()
                if isinstance(value, int | float)
            },
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
                "tool_call_id": item.get("tool_call_id"),
                "retrieved_at": item.get("retrieved_at"),
                "verification_method": item.get("verification_method"),
                "provider": item.get("provider"),
            })
        return compact

    def _compact_structured_answer(self, answer: dict[str, Any]) -> dict[str, Any]:
        options = answer.get("clarification_options") or []
        compact_options = [
            {
                "market": item.get("market"),
                "symbol": item.get("symbol") or item.get("code"),
                "short_name": item.get("short_name") or item.get("name"),
            }
            for item in options[:5]
            if isinstance(item, dict)
        ]
        return {
            "status": answer.get("status"),
            "reason_code": answer.get("reason_code"),
            "reason": answer.get("reason"),
            "detected_intent": answer.get("detected_intent"),
            "normalized_intent": answer.get("normalized_intent"),
            "requested_report_year": answer.get("requested_report_year"),
            "requested_report_type": answer.get("requested_report_type"),
            "checked_source_scope": answer.get("checked_source_scope"),
            "provider": answer.get("provider"),
            "clarification_options": compact_options,
            "ambiguity_term": answer.get("ambiguity_term"),
            "selection_not_performed_reason": answer.get("selection_not_performed_reason"),
        }

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
