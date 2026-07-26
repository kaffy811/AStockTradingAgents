"""Row-level, owner-attributed write accounting for Pi shadow acceptance.

P1.6.4 used whole-table before/after counts, which attributed writes from a
concurrently running acceptance execution to the current case ("33 Pi business
writes" / "22 assistant double writes").  This module attributes每一条写入 by
row identity and correlation ownership instead.

Owners:
- legacy      — the expected user/assistant persistence of the measured turn;
- pi_shadow   — a business-table write performed by the Pi shadow path
                 (must never happen; counted into pi_business_write_delta);
- system      — acceptance-runner bookkeeping (e.g. the runner's own session
                 creation for a known case of the same acceptance run);
- other_case  — rows belonging to a different case/session of the same
                 acceptance run (measurement-window contamination);
- unknown     — anything unattributable; unknown writes must fail the Gate.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


def _hash_id(value: Any) -> str:
    text = str(value or "")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16] if text else ""


@dataclass(slots=True)
class ObservedMessageRow:
    message_id: str
    session_id: str
    role: str
    created_at: str


@dataclass(slots=True)
class ObservedSessionRow:
    session_id: str
    title_case_marker: str | None
    created_at: str


@dataclass(slots=True)
class WriteAttributionV2:
    case_id: str
    correlation: dict[str, Any]
    writes: list[dict[str, Any]] = field(default_factory=list)
    pi_business_write_delta: int = 0
    assistant_double_write_count: int = 0
    unknown_owner_write_count: int = 0
    other_case_write_count: int = 0
    legacy_write_count: int = 0
    system_write_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "pi_shadow_write_attribution_v2",
            "case_id": self.case_id,
            "correlation": {
                key: value
                for key, value in self.correlation.items()
                if key
                in {
                    "acceptance_run_id",
                    "case_id",
                    "case_attempt",
                    "turn_id",
                    "request_trace_id",
                    "legacy_run_id",
                    "shadow_run_id",
                    "input_snapshot_hash",
                }
            },
            "writes": self.writes,
            "pi_business_write_delta": self.pi_business_write_delta,
            "assistant_double_write_count": self.assistant_double_write_count,
            "unknown_owner_write_count": self.unknown_owner_write_count,
            "other_case_write_count": self.other_case_write_count,
            "legacy_write_count": self.legacy_write_count,
            "system_write_count": self.system_write_count,
        }


def assistant_logical_response_id(session_id: str, turn_id: str, response_kind: str = "primary_answer") -> str:
    return _hash_id(f"{session_id}:{turn_id}:{response_kind}")


def attribute_turn_writes(
    *,
    case_id: str,
    correlation: dict[str, Any],
    target_session_id: str,
    new_messages: list[ObservedMessageRow],
    new_sessions: list[ObservedSessionRow],
    acceptance_session_ids: set[str],
    expected_user_messages: int = 1,
    expected_assistant_messages: int = 1,
) -> WriteAttributionV2:
    """Attribute every observed new row for one measured turn."""
    result = WriteAttributionV2(case_id=case_id, correlation=dict(correlation or {}))
    turn_id = str(correlation.get("turn_id") or "")
    seen_user = 0
    seen_assistant = 0
    for row in sorted(new_messages, key=lambda item: (item.created_at, item.message_id)):
        record: dict[str, Any] = {
            "resource": "chat_messages",
            "operation": "insert",
            "record_id_hash": _hash_id(row.message_id),
            "session_id_hash": _hash_id(row.session_id),
            "turn_id": turn_id or None,
            "request_trace_id": correlation.get("request_trace_id"),
            "legacy_run_id": correlation.get("legacy_run_id"),
            "shadow_run_id": None,
            "writer_component": "chat_service.message_persistence",
            "role": row.role,
        }
        if row.session_id == target_session_id:
            if row.role == "user" and seen_user < expected_user_messages:
                seen_user += 1
                record.update({"owner": "legacy", "expected": True})
                result.legacy_write_count += 1
            elif row.role == "assistant" and seen_assistant < expected_assistant_messages:
                seen_assistant += 1
                record.update({
                    "owner": "legacy",
                    "expected": True,
                    "assistant_logical_response_id": assistant_logical_response_id(row.session_id, turn_id),
                })
                result.legacy_write_count += 1
            elif row.role == "assistant":
                # Same session + same turn + assistant role beyond expectation:
                # this is a true duplicate persistence of the logical response.
                record.update({
                    "owner": "unknown",
                    "expected": False,
                    "assistant_logical_response_id": assistant_logical_response_id(row.session_id, turn_id),
                    "classification": "true_duplicate_assistant_write",
                })
                result.assistant_double_write_count += 1
                result.unknown_owner_write_count += 1
            else:
                record.update({"owner": "unknown", "expected": False, "classification": "unexpected_target_session_write"})
                result.unknown_owner_write_count += 1
        elif row.session_id in acceptance_session_ids:
            record.update({"owner": "other_case", "expected": False, "classification": "other_case_window_contamination"})
            result.other_case_write_count += 1
        else:
            record.update({"owner": "unknown", "expected": False, "classification": "foreign_session_write"})
            result.unknown_owner_write_count += 1
        result.writes.append(record)

    for session_row in new_sessions:
        record = {
            "resource": "chat_sessions",
            "operation": "insert",
            "record_id_hash": _hash_id(session_row.session_id),
            "session_id_hash": _hash_id(session_row.session_id),
            "turn_id": turn_id or None,
            "request_trace_id": correlation.get("request_trace_id"),
            "legacy_run_id": correlation.get("legacy_run_id"),
            "shadow_run_id": None,
            "writer_component": "chat_service.session_create",
        }
        if session_row.session_id == target_session_id:
            record.update({"owner": "system", "expected": True, "classification": "acceptance_runner_target_session"})
            result.system_write_count += 1
        elif session_row.session_id in acceptance_session_ids or session_row.title_case_marker:
            record.update({"owner": "other_case", "expected": False, "classification": "other_case_session_creation"})
            result.other_case_write_count += 1
        else:
            record.update({"owner": "unknown", "expected": False, "classification": "foreign_session_creation"})
            result.unknown_owner_write_count += 1
        result.writes.append(record)

    # Only owner=pi_shadow business writes count into the Pi delta.  The Pi
    # shadow path is read-only; any row it produced would surface here as an
    # unknown-owner write and fail the Gate explicitly instead of silently.
    result.pi_business_write_delta = sum(
        1 for item in result.writes if item.get("owner") == "pi_shadow"
    )
    return result


def parse_case_marker(title: str | None, *, prefix: str = "pi-shadow-") -> str | None:
    text = str(title or "")
    if text.startswith(prefix):
        marker = text[len(prefix):].strip()
        return marker or None
    return None


def utc_iso(value: datetime | str | None) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "")
