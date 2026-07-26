"""Staging canary activation state machine for official_report_pdf_pi_v1.

Phase 6V-P1.8 — personal-project owner self-approval model.

States and legal transitions:

    disabled -> approved_c0 -> active_c1 -> completed_c1
                                   \\-> rolled_back
    (revoked / expired reachable from any approved state)

Forbidden by construction:
- disabled -> active_c1 (C0 validation cannot be skipped)
- automatic promotion into C1 (promotion requires an explicit
  ``project_owner_manual_decision`` source)
- rollout above 1% in this phase (approval caps it)
- rolled_back -> active_c1 without a fresh owner decision (auto-recovery is
  rejected here; a new approval record is required)
- any effect on production (environment is pinned to staging)

The repository defaults stay untouched: this controller only manages the
runner-scoped staging configuration used during controlled acceptance.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.agent_runtime.canary_policy import CANARY_AGENT_ID, CanaryConfig

STATE_DISABLED = "disabled"
STATE_APPROVED_C0 = "approved_c0"
STATE_ACTIVE_C1 = "active_c1"
STATE_COMPLETED_C1 = "completed_c1"
STATE_ROLLED_BACK = "rolled_back"
STATE_REVOKED = "revoked"
STATE_EXPIRED = "expired"

_PROMOTION_SOURCE = "project_owner_manual_decision"


class CanaryActivationError(RuntimeError):
    pass


def build_owner_approval_record(*, source_sha: str, approved_at: str | None = None) -> dict[str, Any]:
    """Owner self-approval record for a personal project — no fictitious
    names/emails/signatures, staging only, rollout capped at 1%."""
    record = {
        "approval_type": "project_owner_self_approval",
        "approved_by_role": "project_owner",
        "project_type": "personal_project",
        "environment": "staging",
        "agent_id": CANARY_AGENT_ID,
        "approved_scope": ["c0_rollout_zero_validation", "c1_rollout_one_percent"],
        "approved_rollout_percent": 1,
        "max_rollout_percent": 5,
        "production_authorized": False,
        "legacy_fallback_required": True,
        "kill_switch_required": True,
        "auto_rollback_required": True,
        "source_sha": source_sha,
        "approved_at": approved_at or datetime.now(timezone.utc).isoformat(),
        "decision": "approved_for_staging_canary_only",
    }
    record["checksum"] = approval_checksum(record)
    return record


def approval_checksum(record: dict[str, Any]) -> str:
    core = {key: value for key, value in record.items() if key != "checksum"}
    payload = json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def validate_owner_approval(record: dict[str, Any], *, source_sha: str) -> None:
    """Fail-closed validation of the self-approval record."""
    if not isinstance(record, dict):
        raise CanaryActivationError("approval_record_missing")
    if record.get("checksum") != approval_checksum(record):
        raise CanaryActivationError("approval_checksum_mismatch")
    if record.get("source_sha") != source_sha:
        raise CanaryActivationError("approval_source_sha_mismatch_regenerate_required")
    if record.get("production_authorized") is not False:
        raise CanaryActivationError("production_must_not_be_authorized")
    if record.get("approved_rollout_percent") != 1:
        raise CanaryActivationError("approved_rollout_must_be_exactly_one")
    if record.get("environment") != "staging":
        raise CanaryActivationError("approval_environment_must_be_staging")
    if record.get("agent_id") != CANARY_AGENT_ID:
        raise CanaryActivationError("approval_agent_mismatch")
    if record.get("decision") != "approved_for_staging_canary_only":
        raise CanaryActivationError("approval_decision_invalid")


@dataclass(slots=True)
class CanaryController:
    """Runner-scoped staging canary state; never mutates repository defaults."""

    approval: dict[str, Any]
    source_sha: str
    state: str = STATE_DISABLED
    config_version: int = 2
    rollout_percent: float = 0.0
    events: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        validate_owner_approval(self.approval, source_sha=self.source_sha)

    # ── transitions ───────────────────────────────────────────────────────────

    def approve_c0(self) -> None:
        if self.state != STATE_DISABLED:
            raise CanaryActivationError(f"illegal_transition_{self.state}_to_approved_c0")
        self.state = STATE_APPROVED_C0
        self.rollout_percent = 0.0
        self._event("approve_c0", {"rollout_percent": 0})

    def promote_to_c1(self, *, promotion_source: str) -> dict[str, Any]:
        if promotion_source != _PROMOTION_SOURCE:
            raise CanaryActivationError("promotion_requires_project_owner_manual_decision")
        if self.state != STATE_APPROVED_C0:
            raise CanaryActivationError(f"illegal_transition_{self.state}_to_active_c1")
        self.state = STATE_ACTIVE_C1
        self.rollout_percent = 1.0
        self.config_version += 1
        event = self._event("promote_to_c1", {
            "promotion_source": promotion_source,
            "from_rollout": 0,
            "to_rollout": 1,
            "config_version": self.config_version,
        })
        return event

    def execute_rollback(self, *, reason: str) -> dict[str, Any]:
        if self.state not in {STATE_APPROVED_C0, STATE_ACTIVE_C1}:
            raise CanaryActivationError(f"illegal_rollback_from_{self.state}")
        self.state = STATE_ROLLED_BACK
        self.rollout_percent = 0.0
        return self._event("auto_rollback", {
            "reason": reason,
            "rollout_percent": 0,
            "auto_recovery_allowed": False,
        })

    def complete_c1(self) -> None:
        if self.state != STATE_ACTIVE_C1:
            raise CanaryActivationError(f"illegal_transition_{self.state}_to_completed_c1")
        self.state = STATE_COMPLETED_C1
        self._event("complete_c1", {"final_rollout_percent": self.rollout_percent})

    def reactivate_after_rollback(self) -> None:
        raise CanaryActivationError("auto_recovery_after_rollback_forbidden_new_owner_decision_required")

    # ── config view ───────────────────────────────────────────────────────────

    def current_config(self) -> CanaryConfig:
        active = self.state in {STATE_APPROVED_C0, STATE_ACTIVE_C1}
        return CanaryConfig(
            environment="staging",
            authorization_status="approved" if active else "revoked" if self.state == STATE_REVOKED else "disabled",
            allowed_agents=(CANARY_AGENT_ID,) if active else (),
            rollout_percent=self.rollout_percent if self.state == STATE_ACTIVE_C1 else 0.0,
            max_rollout_percent=5.0,
            config_version=self.config_version,
            approval_reference=f"owner_self_approval:{self.approval.get('checksum')}",
        )

    @property
    def authorization_phase(self) -> str:
        return {"approved_c0": "c0", "active_c1": "c1", "completed_c1": "c1"}.get(self.state, "none")

    def _event(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = {
            "event": kind,
            "at": datetime.now(timezone.utc).isoformat(),
            "state": self.state,
            **payload,
        }
        self.events.append(event)
        return event
