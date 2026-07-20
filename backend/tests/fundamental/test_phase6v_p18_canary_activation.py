"""Phase 6V-P1.8 — owner self-approval, C0/C1 state machine and rollback tests.

Together with test_phase6v_p17_canary_policy.py (32 rules) this covers the
42-item P1.8 gate matrix; items already proven in P1.7 (exact allowlist,
wildcard rejection, bucketing determinism/distribution, kill-switch priority,
sample rules, audit sanitization) are not duplicated here.
"""
from __future__ import annotations

import pytest

from app.agent_runtime.canary_activation import (
    CanaryActivationError,
    CanaryController,
    approval_checksum,
    build_owner_approval_record,
    validate_owner_approval,
)
from app.agent_runtime.canary_policy import (
    CANARY_AGENT_ID,
    CanaryRequest,
    anonymized_user_key,
    bucket_selected,
    evaluate_canary_decision,
    stable_bucket,
)

SHA = "85e61c0bc2eff444797ba1e17fd0c8b576221857"


def _controller() -> CanaryController:
    return CanaryController(approval=build_owner_approval_record(source_sha=SHA), source_sha=SHA)


# 1-3: approval record
def test_owner_self_approval_record_valid():
    record = build_owner_approval_record(source_sha=SHA)
    validate_owner_approval(record, source_sha=SHA)
    assert record["approval_type"] == "project_owner_self_approval"
    assert record["project_type"] == "personal_project"
    assert record["checksum"] == approval_checksum(record)


def test_production_authorized_must_be_false():
    record = build_owner_approval_record(source_sha=SHA)
    record["production_authorized"] = True
    record["checksum"] = approval_checksum(record)
    with pytest.raises(CanaryActivationError, match="production"):
        validate_owner_approval(record, source_sha=SHA)


def test_approved_rollout_must_be_exactly_one_and_sha_bound():
    record = build_owner_approval_record(source_sha=SHA)
    record["approved_rollout_percent"] = 5
    record["checksum"] = approval_checksum(record)
    with pytest.raises(CanaryActivationError, match="exactly_one"):
        validate_owner_approval(record, source_sha=SHA)
    fresh = build_owner_approval_record(source_sha=SHA)
    with pytest.raises(CanaryActivationError, match="sha_mismatch"):
        validate_owner_approval(fresh, source_sha="deadbeef")
    tampered = build_owner_approval_record(source_sha=SHA)
    tampered["max_rollout_percent"] = 100
    with pytest.raises(CanaryActivationError, match="checksum"):
        validate_owner_approval(tampered, source_sha=SHA)


# 4-6: C0
def test_c0_config_has_rollout_zero_and_cannot_execute_pi():
    controller = _controller()
    controller.approve_c0()
    config = controller.current_config()
    assert config.rollout_percent == 0.0
    assert config.allowed_agents == (CANARY_AGENT_ID,)
    request = CanaryRequest(anon_user_key=anonymized_user_key("c0-user"))
    decision = evaluate_canary_decision(config, request)
    assert decision.decision == "legacy" and decision.reason == "rollout_not_selected"


def test_c0_thousand_users_zero_selected():
    controller = _controller()
    controller.approve_c0()
    config = controller.current_config()
    hits = sum(
        1 for i in range(1000)
        if bucket_selected(
            stable_bucket(environment="staging", agent_id=CANARY_AGENT_ID,
                          anon_user_key=anonymized_user_key(f"c0-{i}"),
                          config_version=config.config_version),
            config.rollout_percent,
        )
    )
    assert hits == 0


# 7-11: promotion rules
def test_manual_promotion_after_c0_reaches_one_percent():
    controller = _controller()
    controller.approve_c0()
    event = controller.promote_to_c1(promotion_source="project_owner_manual_decision")
    assert controller.state == "active_c1"
    assert controller.rollout_percent == 1.0
    assert event["from_rollout"] == 0 and event["to_rollout"] == 1
    assert event["config_version"] == 3  # version increments on promotion


def test_cannot_enter_c1_without_c0():
    controller = _controller()
    with pytest.raises(CanaryActivationError, match="illegal_transition_disabled"):
        controller.promote_to_c1(promotion_source="project_owner_manual_decision")


def test_cannot_auto_promote():
    controller = _controller()
    controller.approve_c0()
    with pytest.raises(CanaryActivationError, match="project_owner_manual_decision"):
        controller.promote_to_c1(promotion_source="background_scheduler")


def test_rollout_capped_at_one_percent_this_phase_max_still_five():
    controller = _controller()
    controller.approve_c0()
    controller.promote_to_c1(promotion_source="project_owner_manual_decision")
    config = controller.current_config()
    assert config.rollout_percent == 1.0
    assert config.max_rollout_percent == 5.0


# rollback semantics
def test_rollback_sets_zero_and_forbids_auto_recovery():
    controller = _controller()
    controller.approve_c0()
    controller.promote_to_c1(promotion_source="project_owner_manual_decision")
    event = controller.execute_rollback(reason="zero_tolerance:fabricated_url_count")
    assert controller.state == "rolled_back"
    assert controller.rollout_percent == 0.0
    assert event["auto_recovery_allowed"] is False
    with pytest.raises(CanaryActivationError, match="auto_recovery_after_rollback_forbidden"):
        controller.reactivate_after_rollback()
    # after rollback the effective config selects nobody
    config = controller.current_config()
    assert config.rollout_percent == 0.0 and config.authorization_status == "disabled"


def test_rolled_back_cannot_promote_again():
    controller = _controller()
    controller.approve_c0()
    controller.promote_to_c1(promotion_source="project_owner_manual_decision")
    controller.execute_rollback(reason="drill")
    with pytest.raises(CanaryActivationError, match="illegal_transition_rolled_back"):
        controller.promote_to_c1(promotion_source="project_owner_manual_decision")


# eligibility interplay with live config (unsupported/clarification stay legacy)
def test_c1_unsupported_and_clarification_and_other_agents_stay_legacy():
    controller = _controller()
    controller.approve_c0()
    controller.promote_to_c1(promotion_source="project_owner_manual_decision")
    config = controller.current_config()
    # find a selected key
    key = None
    for i in range(5000):
        candidate = anonymized_user_key(f"c1-{i}")
        if bucket_selected(stable_bucket(environment="staging", agent_id=CANARY_AGENT_ID,
                                         anon_user_key=candidate, config_version=config.config_version), 1.0):
            key = candidate
            break
    assert key is not None
    semi = evaluate_canary_decision(config, CanaryRequest(anon_user_key=key, report_type="semi"))
    assert semi.reason == "unsupported_report_type"
    clar = evaluate_canary_decision(config, CanaryRequest(anon_user_key=key, is_clarification=True))
    assert clar.reason == "clarification_request_stays_legacy"
    other = evaluate_canary_decision(config, CanaryRequest(anon_user_key=key, agent_id="another_agent"))
    assert other.reason == "agent_not_in_exact_allowlist"
    prod = evaluate_canary_decision(config, CanaryRequest(anon_user_key=key, environment="production"))
    assert prod.reason == "environment_not_authorized"


# repo defaults unchanged (items 41-42)
def test_repository_defaults_remain_legacy_and_disabled():
    from app.core.config import Settings

    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://user:pass@localhost/test",  # test-only dummy
        secret_key="test-only-secret",
    )
    assert settings.agent_executor_mode == "legacy"
    assert settings.pi_agent_shadow_enabled is False
    assert settings.pi_agent_allowed_agents == ""
    assert settings.pi_canary_authorization_status == "proposed"
    assert settings.pi_canary_rollout_percent == 0.0
    assert settings.chat_runtime_mode == "legacy"
