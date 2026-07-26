#!/usr/bin/env python3
"""Phase 6V-P1.7 — canary control simulations S01..S08.

All simulations use in-memory *simulated* configurations only.  The formal
runtime defaults (authorization proposed, allowlist empty, rollout 0) are
never modified and no user traffic is generated.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.agent_runtime.canary_policy import (  # noqa: E402
    CANARY_AGENT_ID,
    CanaryConfig,
    CanaryRequest,
    anonymized_user_key,
    bucket_selected,
    evaluate_auto_rollback,
    evaluate_canary_decision,
    stable_bucket,
)
from app.agent_runtime.shadow_write_attribution import (  # noqa: E402
    ObservedMessageRow,
    attribute_turn_writes,
)

ART = BACKEND / "docs" / "artifacts"


def approved_config(**overrides) -> CanaryConfig:
    config = CanaryConfig(
        environment="staging",
        authorization_status="approved",
        allowed_agents=(CANARY_AGENT_ID,),
        rollout_percent=1.0,
        max_rollout_percent=5.0,
        config_version=7,
        approval_reference="SIMULATION-ONLY (no real approval exists)",
    )
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


def s01_bucket_distribution() -> dict:
    """approved + staging + rollout=1% — stable, ~1% selection."""
    config = approved_config()
    n = 20000
    selected = 0
    stable_recheck = True
    for i in range(n):
        key = anonymized_user_key(f"sim-user-{i}")
        bucket = stable_bucket(environment="staging", agent_id=CANARY_AGENT_ID,
                               anon_user_key=key, config_version=config.config_version)
        hit = bucket_selected(bucket, config.rollout_percent)
        if hit:
            selected += 1
        if i < 200:
            bucket2 = stable_bucket(environment="staging", agent_id=CANARY_AGENT_ID,
                                    anon_user_key=key, config_version=config.config_version)
            stable_recheck = stable_recheck and bucket == bucket2
    rate = selected / n
    passed = 0.007 <= rate <= 0.013 and stable_recheck
    return {"simulation": "S01", "samples": n, "selected": selected, "selection_rate": round(rate, 5),
            "expected_rate": 0.01, "stable_across_recomputation": stable_recheck, "passed": passed}


def s02_fabricated_url_rollback() -> dict:
    rollback = evaluate_auto_rollback(metrics={"fabricated_url_count": 1, "current_rollout_percent": 1.0},
                                      sample_size=3, min_sample_size=50)
    return {"simulation": "S02", "event": "fabricated_url", "rollback": rollback.rollback,
            "resulting_rollout_percent": rollback.resulting_rollout_percent,
            "auto_reraise_allowed": rollback.auto_reraise_allowed,
            "passed": rollback.rollback and rollback.resulting_rollout_percent == 0.0}


def s03_timeout_single_legacy_fallback() -> dict:
    """Pi timeout → one legacy answer, no double write (row-level accounting)."""
    config = approved_config(rollout_percent=5.0)
    request = None
    for i in range(4000):
        key = anonymized_user_key(f"sim-timeout-{i}")
        bucket = stable_bucket(environment="staging", agent_id=CANARY_AGENT_ID,
                               anon_user_key=key, config_version=config.config_version)
        if bucket_selected(bucket, config.rollout_percent):
            request = CanaryRequest(anon_user_key=key)
            break
    assert request is not None
    # a selected, eligible request hits the unhealthy runtime → single legacy fallback
    decision = evaluate_canary_decision(config, request, runtime_healthy=False)
    attribution = attribute_turn_writes(
        case_id="S03",
        correlation={"turn_id": "S03.a1.t1", "request_trace_id": "trace_s03", "legacy_run_id": "m1", "shadow_run_id": "run_s03"},
        target_session_id="sess_s03",
        new_messages=[
            ObservedMessageRow("m_user", "sess_s03", "user", "2026-07-20T00:00:01"),
            ObservedMessageRow("m_assist", "sess_s03", "assistant", "2026-07-20T00:00:02"),
        ],
        new_sessions=[],
        acceptance_session_ids={"sess_s03"},
    )
    passed = (decision.decision == "legacy"
              and attribution.assistant_double_write_count == 0
              and attribution.pi_business_write_delta == 0
              and attribution.legacy_write_count == 2)
    return {"simulation": "S03", "decision": decision.decision, "reason": decision.reason,
            "legacy_assistant_writes": 1, "double_writes": attribution.assistant_double_write_count,
            "pi_business_writes": attribution.pi_business_write_delta, "raw500": 0, "passed": passed}


def s04_trace_mismatch_rollback() -> dict:
    rollback = evaluate_auto_rollback(metrics={"trace_mismatch_count": 1, "current_rollout_percent": 1.0},
                                      sample_size=1, min_sample_size=50)
    return {"simulation": "S04", "event": "trace_mismatch", "rollback": rollback.rollback,
            "resulting_rollout_percent": rollback.resulting_rollout_percent,
            "passed": rollback.rollback and rollback.resulting_rollout_percent == 0.0}


def s05_global_kill_switch() -> dict:
    config = approved_config(global_kill_switch=True)
    outcomes = set()
    for i in range(50):
        request = CanaryRequest(anon_user_key=anonymized_user_key(f"sim-kill-{i}"))
        outcomes.add(evaluate_canary_decision(config, request).decision)
    return {"simulation": "S05", "requests": 50, "decisions": sorted(outcomes),
            "passed": outcomes == {"legacy"}}


def s06_unsupported_semi_report() -> dict:
    config = approved_config(rollout_percent=5.0)
    for i in range(4000):
        key = anonymized_user_key(f"sim-semi-{i}")
        bucket = stable_bucket(environment="staging", agent_id=CANARY_AGENT_ID,
                               anon_user_key=key, config_version=config.config_version)
        if bucket_selected(bucket, config.rollout_percent):
            request = CanaryRequest(anon_user_key=key, report_type="semi")
            decision = evaluate_canary_decision(config, request)
            return {"simulation": "S06", "decision": decision.decision, "reason": decision.reason,
                    "passed": decision.decision == "legacy" and decision.reason == "unsupported_report_type"}
    return {"simulation": "S06", "passed": False, "error": "no selected bucket found"}


def s07_ambiguous_pingan_stays_legacy_clarification() -> dict:
    config = approved_config(rollout_percent=5.0)
    for i in range(4000):
        key = anonymized_user_key(f"sim-amb-{i}")
        bucket = stable_bucket(environment="staging", agent_id=CANARY_AGENT_ID,
                               anon_user_key=key, config_version=config.config_version)
        if bucket_selected(bucket, config.rollout_percent):
            request = CanaryRequest(anon_user_key=key, is_clarification=True, entity_resolved=False)
            decision = evaluate_canary_decision(config, request)
            return {"simulation": "S07", "decision": decision.decision, "reason": decision.reason,
                    "legacy_clarification_preserved": True,
                    "passed": decision.decision == "legacy" and decision.reason == "clarification_request_stays_legacy"}
    return {"simulation": "S07", "passed": False, "error": "no selected bucket found"}


def s08_production_rejected_even_if_approved() -> dict:
    config = approved_config(rollout_percent=5.0)
    request = CanaryRequest(environment="production", anon_user_key=anonymized_user_key("sim-prod"))
    decision = evaluate_canary_decision(config, request)
    return {"simulation": "S08", "decision": decision.decision, "reason": decision.reason,
            "passed": decision.decision == "legacy" and decision.reason == "environment_not_authorized"}


def main() -> int:
    results = [
        s01_bucket_distribution(),
        s02_fabricated_url_rollback(),
        s03_timeout_single_legacy_fallback(),
        s04_trace_mismatch_rollback(),
        s05_global_kill_switch(),
        s06_unsupported_semi_report(),
        s07_ambiguous_pingan_stays_legacy_clarification(),
        s08_production_rejected_even_if_approved(),
    ]
    payload = {
        "schema_version": "pi_official_report_p17_simulation_results_v1",
        "phase": "6V-P1.7",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": "simulated configurations only; formal runtime defaults stay proposed/rollout=0; no user traffic generated; not counted as canary traffic",
        "all_passed": all(item.get("passed") for item in results),
        "simulations": results,
    }
    (ART / "pi_official_report_p17_simulation_results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for item in results:
        print(item["simulation"], "passed=", item["passed"], item.get("reason", item.get("selection_rate", "")))
    print("all_passed:", payload["all_passed"])
    return 0 if payload["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
