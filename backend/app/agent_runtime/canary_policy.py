"""Staging-only canary authorization policy for official_report_pdf_pi_v1.

Phase 6V-P1.7.  This module implements the *decision* machinery only — the
formal runtime configuration stays fully disabled (authorization proposed,
allowlist empty, rollout 0, executor legacy).  Nothing here can start Pi
traffic without an explicit, versioned, approved configuration.

Decision priority (any failing level短路 to legacy, with a compact audit
reason and never a user-visible error):

    1. global kill switch
    2. environment hard disable (staging-only; production requires an
       independent authorization that does not exist in this proposal)
    3. agent authorization status (approved, unexpired)
    4. exact agent allowlist (no wildcards)
    5. rollout percentage (stable bucketing, 0 => nobody)
    6. request eligibility (explicit entity, annual report only)
    7. runtime health gate
    8. pi execution (not performed in this phase)
    9. legacy fallback

Config parsing is fail-closed: any unreadable/illegal value disables canary.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


CANARY_AGENT_ID = "official_report_pdf_pi_v1"
_ALLOWED_STATUSES = {"proposed", "approved", "rejected", "revoked", "disabled"}
_ALLOWED_ENVIRONMENTS = {"staging"}
_BUCKET_SPACE = 10000

DECISION_LEGACY = "legacy"
DECISION_PI_CANARY = "pi_canary"


@dataclass(slots=True)
class CanaryConfig:
    environment: str = "staging"
    authorization_status: str = "proposed"
    allowed_agents: tuple[str, ...] = ()
    rollout_percent: float = 0.0
    max_rollout_percent: float = 5.0
    fallback_mode: str = "legacy"
    global_kill_switch: bool = False
    environment_kill_switch: bool = False
    agent_kill_switch: bool = False
    authorization_expires_at: str | None = None
    config_version: int = 1
    stable_bucket_salt: str = "pi_v1"  # stable across config_version; do NOT change between rollout promotions
    approval_reference: str | None = None
    auto_rollback_enabled: bool = True
    health_window_minutes: int = 30
    min_sample_size: int = 50
    auto_run: bool = False
    production_enabled: bool = False
    parse_error: str | None = None

    @property
    def fail_closed(self) -> bool:
        return self.parse_error is not None


def load_canary_config(settings_obj: Any) -> CanaryConfig:
    """Read config from settings with fail-closed semantics."""
    try:
        raw_agents = str(getattr(settings_obj, "pi_canary_allowed_agents", "") or "")
        agents = tuple(item.strip() for item in raw_agents.split(",") if item.strip())
        if any("*" in item or "?" in item for item in agents):
            return CanaryConfig(parse_error="wildcard_agent_allowlist_forbidden")
        rollout = float(getattr(settings_obj, "pi_canary_rollout_percent", 0.0) or 0.0)
        max_rollout = float(getattr(settings_obj, "pi_canary_max_rollout_percent", 5.0) or 5.0)
        if rollout < 0 or max_rollout < 0 or rollout > max_rollout or max_rollout > 100:
            return CanaryConfig(parse_error="illegal_rollout_configuration")
        status = str(getattr(settings_obj, "pi_canary_authorization_status", "proposed") or "proposed").lower()
        if status not in _ALLOWED_STATUSES:
            return CanaryConfig(parse_error="unknown_authorization_status")
        return CanaryConfig(
            environment=str(getattr(settings_obj, "pi_canary_environment", "staging") or "staging").lower(),
            authorization_status=status,
            allowed_agents=agents,
            rollout_percent=rollout,
            max_rollout_percent=max_rollout,
            fallback_mode=str(getattr(settings_obj, "pi_canary_fallback_mode", "legacy") or "legacy"),
            global_kill_switch=bool(getattr(settings_obj, "pi_executor_global_kill_switch", False)),
            environment_kill_switch=bool(getattr(settings_obj, "pi_canary_environment_kill_switch", False)),
            agent_kill_switch=bool(getattr(settings_obj, "pi_canary_agent_kill_switch", False)),
            authorization_expires_at=getattr(settings_obj, "pi_canary_authorization_expires_at", None) or None,
            config_version=int(getattr(settings_obj, "pi_canary_config_version", 1) or 1),
            stable_bucket_salt=str(getattr(settings_obj, "pi_canary_stable_bucket_salt", "pi_v1") or "pi_v1"),
            approval_reference=getattr(settings_obj, "pi_canary_approval_reference", None) or None,
            auto_rollback_enabled=bool(getattr(settings_obj, "pi_canary_auto_rollback_enabled", True)),
            health_window_minutes=int(getattr(settings_obj, "pi_canary_health_window_minutes", 30) or 30),
            min_sample_size=int(getattr(settings_obj, "pi_canary_min_sample_size", 50) or 50),
        )
    except Exception as exc:  # noqa: BLE001 - any parse failure closes the gate
        return CanaryConfig(parse_error=f"config_parse_failed_{type(exc).__name__}")


def anonymized_user_key(user_id: str | None) -> str:
    """Irreversible short key — full user ids never enter bucketing or audits."""
    return hashlib.sha256(f"pi_canary_user:{user_id or ''}".encode("utf-8")).hexdigest()[:16]


def stable_bucket(*, environment: str, agent_id: str, anon_user_key: str,
                  stable_bucket_salt: str = "pi_v1",
                  config_version: int | None = None) -> int:
    """Deterministic bucket in [0, 10000). No builtin hash, time or randomness.

    ``stable_bucket_salt`` must remain constant across rollout promotions to
    guarantee monotonic cohort nesting (50% ⊆ 75% ⊆ 100%).  ``config_version``
    is kept as an optional parameter for backward-compatibility only; it is no
    longer part of the hash and has no effect on bucket assignment.
    """
    payload = f"{environment}|{agent_id}|{anon_user_key}|{stable_bucket_salt}"
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % _BUCKET_SPACE


def bucket_selected(bucket: int, rollout_percent: float) -> bool:
    if rollout_percent <= 0:
        return False
    return bucket < int(rollout_percent * 100)


_AMBIGUOUS_RE = re.compile(r"clarification", re.IGNORECASE)


@dataclass(slots=True)
class CanaryRequest:
    environment: str = "staging"
    agent_id: str = CANARY_AGENT_ID
    request_type: str = "official_annual_report_pdf"
    entity_resolved: bool = True
    report_type: str = "annual"
    is_clarification: bool = False
    is_known_unavailable: bool = False
    is_fault_injection: bool = False
    anon_user_key: str = ""
    request_trace_hash: str = ""


@dataclass(slots=True)
class CanaryDecision:
    decision: str
    eligible: bool
    bucket_selected: bool
    reason: str
    audit: dict[str, Any] = field(default_factory=dict)


def evaluate_canary_decision(
    config: CanaryConfig,
    request: CanaryRequest,
    *,
    runtime_healthy: bool = True,
    now: datetime | None = None,
) -> CanaryDecision:
    now = now or datetime.now(timezone.utc)

    def legacy(reason: str, *, eligible: bool = False, selected: bool = False) -> CanaryDecision:
        return CanaryDecision(
            decision=DECISION_LEGACY,
            eligible=eligible,
            bucket_selected=selected,
            reason=reason,
            audit=build_audit_event(config, request, decision=DECISION_LEGACY, eligible=eligible,
                                    selected=selected, reason=reason),
        )

    # 0. fail-closed config
    if config.fail_closed:
        return legacy(f"config_fail_closed:{config.parse_error}")
    # 1. global kill switch
    if config.global_kill_switch:
        return legacy("global_kill_switch")
    # 2. environment hard disable — staging only; production needs its own authorization
    if request.environment != "staging" or config.environment not in _ALLOWED_ENVIRONMENTS:
        return legacy("environment_not_authorized")
    if config.environment_kill_switch:
        return legacy("environment_kill_switch")
    # 3. authorization status
    if config.authorization_status != "approved":
        return legacy(f"authorization_{config.authorization_status}")
    if _expired(config.authorization_expires_at, now):
        return legacy("authorization_expired")
    # 4. exact allowlist
    if request.agent_id != CANARY_AGENT_ID or request.agent_id not in config.allowed_agents:
        return legacy("agent_not_in_exact_allowlist")
    if config.agent_kill_switch:
        return legacy("agent_kill_switch")
    # 5. rollout bucket
    bucket = stable_bucket(
        environment=request.environment,
        agent_id=request.agent_id,
        anon_user_key=request.anon_user_key,
        stable_bucket_salt=config.stable_bucket_salt,
    )
    selected = bucket_selected(bucket, min(config.rollout_percent, config.max_rollout_percent))
    if not selected:
        return legacy("rollout_not_selected")
    # 6. request eligibility
    ineligible_reason = _ineligibility_reason(request)
    if ineligible_reason:
        return legacy(ineligible_reason, selected=True)
    # 7. runtime health gate
    if not runtime_healthy:
        return legacy("runtime_health_gate_failed", eligible=True, selected=True)
    # 8. pi execution (this phase never executes; callers must still hold approval)
    return CanaryDecision(
        decision=DECISION_PI_CANARY,
        eligible=True,
        bucket_selected=True,
        reason="eligible_annual_report_request",
        audit=build_audit_event(config, request, decision=DECISION_PI_CANARY, eligible=True,
                                selected=True, reason="eligible_annual_report_request"),
    )


def _ineligibility_reason(request: CanaryRequest) -> str | None:
    if request.is_fault_injection:
        return "fault_injection_request"
    if request.is_clarification:
        return "clarification_request_stays_legacy"
    if request.is_known_unavailable:
        return "known_unavailable_stays_legacy"
    if request.report_type != "annual":
        return "unsupported_report_type"
    if not request.entity_resolved:
        return "entity_not_resolved"
    if request.request_type != "official_annual_report_pdf":
        return "request_type_not_covered"
    return None


def _expired(expires_at: str | None, now: datetime) -> bool:
    if not expires_at:
        return False
    try:
        parsed = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return now >= parsed
    except (TypeError, ValueError):
        return True  # unreadable expiry fails closed


# ── auto rollback ─────────────────────────────────────────────────────────────

ZERO_TOLERANCE_COUNTERS = (
    "fabricated_url_count",
    "pi_business_write_count",
    "assistant_double_write_count",
    "unknown_write_count",
    "trace_mismatch_count",
    "terminal_missing_count",
    "provenance_failure_count",
    "clarification_error_count",
    "raw500_count",
    "raw503_count",
    "task_or_db_leak_count",
)

RATIO_THRESHOLDS = {
    "unexpected_timeout_rate": 0.01,
    "fallback_rate": 0.10,  # alert-first metric; rollback only with sufficient samples
}


@dataclass(slots=True)
class RollbackDecision:
    rollback: bool
    reasons: list[str]
    resulting_rollout_percent: float
    auto_reraise_allowed: bool = False  # never auto re-raise traffic after rollback


def evaluate_auto_rollback(
    *,
    metrics: dict[str, Any],
    sample_size: int,
    min_sample_size: int,
) -> RollbackDecision:
    reasons: list[str] = []
    # zero-tolerance events roll back regardless of sample size
    for key in ZERO_TOLERANCE_COUNTERS:
        if int(metrics.get(key) or 0) > 0:
            reasons.append(f"zero_tolerance:{key}")
    if metrics.get("safety_correctness_rate") is not None and float(metrics["safety_correctness_rate"]) < 1.0:
        reasons.append("zero_tolerance:safety_correctness_below_1")
    # ratio metrics require a minimum sample
    if sample_size >= min_sample_size:
        for key, threshold in RATIO_THRESHOLDS.items():
            value = metrics.get(key)
            if value is not None and float(value) > threshold:
                reasons.append(f"ratio:{key}>{threshold}")
    return RollbackDecision(
        rollback=bool(reasons),
        reasons=reasons,
        resulting_rollout_percent=0.0 if reasons else float(metrics.get("current_rollout_percent") or 0.0),
        auto_reraise_allowed=False,
    )


# ── audit ─────────────────────────────────────────────────────────────────────

def build_audit_event(
    config: CanaryConfig,
    request: CanaryRequest,
    *,
    decision: str,
    eligible: bool,
    selected: bool,
    reason: str,
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    """Compact, sanitized audit event — no query text, no full ids, no URLs."""
    return {
        "schema_version": "pi_canary_audit_v1",
        "config_version": config.config_version,
        "environment": request.environment,
        "agent_id": request.agent_id,
        "authorization_status": config.authorization_status,
        "rollout_percent": config.rollout_percent,
        "eligible": eligible,
        "eligibility_reason": reason,
        "bucket_selected": selected,
        "decision": decision,
        "fallback_reason": fallback_reason,
        "kill_switch_state": {
            "global": config.global_kill_switch,
            "environment": config.environment_kill_switch,
            "agent": config.agent_kill_switch,
        },
        "correlation": {
            "request_trace_hash": (request.request_trace_hash or "")[:16],
            "anon_user_key": (request.anon_user_key or "")[:16],
        },
    }


# ── runtime loader integration (Phase 6V-P1.22) ───────────────────────────────

def get_effective_shadow_config_snapshot(settings_obj: Any = None) -> dict[str, Any]:
    """Return a sanitized effective-config snapshot via the formal runtime loader.

    Calls ``load_canary_config`` with the real (or injected) settings object so
    the snapshot is produced by the same code path used in production.  Never
    exposes secrets, user identities, query text, tokens, or auth headers.
    Designed to be called at process startup for provenance logging.

    Args:
        settings_obj: A Settings-compatible object.  If None, the module-level
            singleton from ``app.core.config`` is imported lazily so this
            function remains importable without triggering Settings validation
            during unit-test collection.
    """
    if settings_obj is None:
        from app.core.config import settings as _settings  # lazy import
        settings_obj = _settings
    cfg = load_canary_config(settings_obj)
    return {
        "schema_version": "pi_canary_runtime_snapshot_v1",
        "environment": cfg.environment,
        "canary_mode": "shadow",
        "rollout_percent": cfg.rollout_percent,
        "config_version": cfg.config_version,
        "stable_bucket_salt_version": cfg.stable_bucket_salt,
        "authorization_status": cfg.authorization_status,
        "live": False,
        "production_enabled": cfg.production_enabled,
        "provider_serving_enabled": False,
        "fail_closed": cfg.fail_closed,
        "parse_error": cfg.parse_error,
        "global_kill_switch": cfg.global_kill_switch,
        "runtime_loader": "load_canary_config",
        "config_source": "pydantic_settings.Settings",
        "evidence_mode": (
            "runtime_loader_integration_verified" if not cfg.fail_closed
            else "config_parse_failed"
        ),
    }
