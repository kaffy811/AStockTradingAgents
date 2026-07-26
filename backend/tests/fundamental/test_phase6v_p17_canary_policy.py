"""Phase 6V-P1.7 — staging canary authorization policy tests (32 gate rules)."""
from __future__ import annotations

from datetime import datetime, timezone

from app.agent_runtime.canary_policy import (
    CANARY_AGENT_ID,
    CanaryConfig,
    CanaryRequest,
    anonymized_user_key,
    bucket_selected,
    build_audit_event,
    evaluate_auto_rollback,
    evaluate_canary_decision,
    load_canary_config,
    stable_bucket,
)


def _config(**overrides) -> CanaryConfig:
    base = CanaryConfig(
        environment="staging",
        authorization_status="approved",
        allowed_agents=(CANARY_AGENT_ID,),
        rollout_percent=1.0,
        max_rollout_percent=5.0,
        config_version=1,
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def _request(**overrides) -> CanaryRequest:
    base = CanaryRequest(anon_user_key=anonymized_user_key("user-1"), request_trace_hash="t" * 16)
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def _selected_user(config: CanaryConfig) -> CanaryRequest:
    """Find a deterministic anon key that lands inside the rollout bucket."""
    for i in range(4000):
        key = anonymized_user_key(f"probe-{i}")
        bucket = stable_bucket(environment="staging", agent_id=CANARY_AGENT_ID,
                               anon_user_key=key,
                               stable_bucket_salt=getattr(config, "stable_bucket_salt", "pi_v1"))
        if bucket_selected(bucket, config.rollout_percent):
            return _request(anon_user_key=key)
    raise AssertionError("no bucket-selected probe found")


class _FakeSettings:
    def __init__(self, **kv):
        self.__dict__.update(kv)


# 1
def test_default_settings_are_proposed_and_disabled():
    from app.core.config import Settings

    config = load_canary_config(Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://user:pass@localhost/test",  # test-only dummy
        secret_key="test-only-secret",
    ))
    assert config.authorization_status == "proposed"
    assert config.allowed_agents == ()
    assert config.rollout_percent == 0.0
    assert config.max_rollout_percent == 5.0
    assert not config.global_kill_switch


# 2
def test_rollout_zero_never_selects_anyone():
    for i in range(500):
        bucket = stable_bucket(environment="staging", agent_id=CANARY_AGENT_ID,
                               anon_user_key=anonymized_user_key(f"user-{i}"), config_version=1)
        assert not bucket_selected(bucket, 0.0)


# 3
def test_non_staging_environment_rejected():
    decision = evaluate_canary_decision(_config(), _request(environment="production"))
    assert decision.decision == "legacy" and decision.reason == "environment_not_authorized"


# 4
def test_agent_not_in_exact_allowlist_rejected():
    decision = evaluate_canary_decision(_config(allowed_agents=()), _selected_user(_config()))
    assert decision.reason == "agent_not_in_exact_allowlist"


# 5
def test_wildcard_allowlist_fails_closed():
    config = load_canary_config(_FakeSettings(pi_canary_allowed_agents="official_*"))
    assert config.fail_closed
    decision = evaluate_canary_decision(config, _request())
    assert decision.decision == "legacy" and "wildcard" in decision.reason


# 6
def test_unapproved_authorization_rejected():
    for status in ("proposed", "rejected", "revoked", "disabled"):
        decision = evaluate_canary_decision(_config(authorization_status=status), _request())
        assert decision.decision == "legacy" and decision.reason == f"authorization_{status}"


# 7
def test_expired_authorization_rejected():
    decision = evaluate_canary_decision(
        _config(authorization_expires_at="2020-01-01T00:00:00+00:00"), _request(),
        now=datetime(2026, 7, 20, tzinfo=timezone.utc),
    )
    assert decision.reason == "authorization_expired"
    # unreadable expiry also fails closed
    decision2 = evaluate_canary_decision(_config(authorization_expires_at="not-a-date"), _request())
    assert decision2.reason == "authorization_expired"


# 8
def test_global_kill_switch_wins_over_everything():
    decision = evaluate_canary_decision(_config(global_kill_switch=True), _selected_user(_config()))
    assert decision.reason == "global_kill_switch"


# 9
def test_environment_kill_switch_precedes_authorization():
    decision = evaluate_canary_decision(
        _config(environment_kill_switch=True, authorization_status="proposed"), _request())
    assert decision.reason == "environment_kill_switch"


# 10
def test_agent_kill_switch_stops_selected_agent():
    config = _config(agent_kill_switch=True)
    decision = evaluate_canary_decision(config, _selected_user(config))
    assert decision.reason == "agent_kill_switch"


# 11
def test_unsupported_report_type_not_eligible():
    config = _config()
    request = _selected_user(config)
    request.report_type = "semi"
    decision = evaluate_canary_decision(config, request)
    assert decision.decision == "legacy" and decision.reason == "unsupported_report_type"


# 12
def test_clarification_request_not_eligible():
    config = _config()
    request = _selected_user(config)
    request.is_clarification = True
    decision = evaluate_canary_decision(config, request)
    assert decision.reason == "clarification_request_stays_legacy"


# 13
def test_known_unavailable_not_eligible():
    config = _config()
    request = _selected_user(config)
    request.is_known_unavailable = True
    decision = evaluate_canary_decision(config, request)
    assert decision.reason == "known_unavailable_stays_legacy"


# 14
def test_bucketing_deterministic_across_calls():
    key = anonymized_user_key("stable-user")
    buckets = {stable_bucket(environment="staging", agent_id=CANARY_AGENT_ID,
                             anon_user_key=key, config_version=3) for _ in range(10)}
    assert len(buckets) == 1


# 15 — updated P1.21: stable_bucket now uses stable_bucket_salt (not config_version) to
# guarantee monotonic cohort nesting across rollout promotions (50% ⊆ 75%).
# config_version is accepted for backward-compatibility but no longer affects the bucket.
def test_stable_bucket_stable_across_config_version():
    """bucket must be identical regardless of config_version (cohort monotonic nesting)."""
    key = anonymized_user_key("rebucket-user")
    b1 = stable_bucket(environment="staging", agent_id=CANARY_AGENT_ID, anon_user_key=key, config_version=1)
    b2 = stable_bucket(environment="staging", agent_id=CANARY_AGENT_ID, anon_user_key=key, config_version=2)
    assert b1 == b2  # config_version no longer participates in hash; salt "pi_v1" is stable

def test_stable_bucket_salt_changes_cohort():
    """Different stable_bucket_salt values must produce different buckets (by design)."""
    key = anonymized_user_key("salt-user")
    b1 = stable_bucket(environment="staging", agent_id=CANARY_AGENT_ID, anon_user_key=key, stable_bucket_salt="pi_v1")
    b2 = stable_bucket(environment="staging", agent_id=CANARY_AGENT_ID, anon_user_key=key, stable_bucket_salt="pi_v2")
    assert b1 != b2  # intentional: different salts allow controlled cohort reset


# 16
def test_full_user_id_never_used_or_stored():
    key = anonymized_user_key("a-very-long-real-user-id-uuid")
    assert "a-very-long" not in key and len(key) == 16
    audit = build_audit_event(_config(), _request(anon_user_key=key),
                              decision="legacy", eligible=False, selected=False, reason="x")
    assert "a-very-long" not in str(audit)


# 17
def test_rollout_cannot_exceed_max():
    config = load_canary_config(_FakeSettings(pi_canary_rollout_percent=10.0, pi_canary_max_rollout_percent=5.0))
    assert config.fail_closed and config.parse_error == "illegal_rollout_configuration"


# 18
def test_illegal_rollout_config_fails_closed():
    for kv in ({"pi_canary_rollout_percent": -1}, {"pi_canary_max_rollout_percent": 500},
               {"pi_canary_rollout_percent": "abc"}):
        config = load_canary_config(_FakeSettings(**kv))
        assert config.fail_closed
        assert evaluate_canary_decision(config, _request()).decision == "legacy"


# 19
def test_config_read_failure_fails_closed():
    class _Broken:
        def __getattr__(self, name):
            raise RuntimeError("boom")

    config = load_canary_config(_Broken())
    assert config.fail_closed
    assert evaluate_canary_decision(config, _request()).decision == "legacy"


# 20 — fallback single-write semantics are asserted at the policy level: a
# legacy decision never reports pi execution, so only the normal legacy
# persistence path runs (row-level double-write accounting from P1.6.5 stays
# the runtime enforcement).
def test_legacy_decision_never_reports_pi_execution():
    decision = evaluate_canary_decision(_config(authorization_status="proposed"), _request())
    assert decision.decision == "legacy"
    assert decision.audit["decision"] == "legacy"


# 21
def test_pi_failure_path_is_fallback_not_raw500():
    config = _config()
    request = _selected_user(config)
    decision = evaluate_canary_decision(config, request, runtime_healthy=False)
    assert decision.decision == "legacy"
    assert decision.reason == "runtime_health_gate_failed"
    assert decision.audit["fallback_reason"] is None  # audit records reason, not an error surface


# 22
def test_provenance_failure_triggers_rollback():
    rollback = evaluate_auto_rollback(metrics={"provenance_failure_count": 1}, sample_size=1, min_sample_size=50)
    assert rollback.rollback and "zero_tolerance:provenance_failure_count" in rollback.reasons


# 23
def test_fabricated_url_triggers_rollback():
    rollback = evaluate_auto_rollback(metrics={"fabricated_url_count": 1}, sample_size=1, min_sample_size=50)
    assert rollback.rollback and rollback.resulting_rollout_percent == 0.0


# 24
def test_business_write_triggers_rollback():
    rollback = evaluate_auto_rollback(metrics={"pi_business_write_count": 1}, sample_size=5, min_sample_size=50)
    assert rollback.rollback


# 25
def test_trace_mismatch_triggers_rollback():
    assert evaluate_auto_rollback(metrics={"trace_mismatch_count": 1}, sample_size=2, min_sample_size=50).rollback


# 26
def test_terminal_missing_triggers_rollback():
    assert evaluate_auto_rollback(metrics={"terminal_missing_count": 1}, sample_size=2, min_sample_size=50).rollback


# 27
def test_safety_correctness_below_one_triggers_rollback():
    rollback = evaluate_auto_rollback(metrics={"safety_correctness_rate": 0.99}, sample_size=3, min_sample_size=50)
    assert rollback.rollback and "safety_correctness_below_1" in rollback.reasons[0]


# 28
def test_ratio_metrics_do_not_fire_below_min_sample():
    rollback = evaluate_auto_rollback(metrics={"unexpected_timeout_rate": 0.5}, sample_size=10, min_sample_size=50)
    assert not rollback.rollback
    fired = evaluate_auto_rollback(metrics={"unexpected_timeout_rate": 0.5}, sample_size=50, min_sample_size=50)
    assert fired.rollback


# 29
def test_zero_tolerance_ignores_min_sample():
    rollback = evaluate_auto_rollback(metrics={"raw503_count": 1}, sample_size=1, min_sample_size=1000)
    assert rollback.rollback


# 30
def test_no_auto_reraise_after_rollback():
    rollback = evaluate_auto_rollback(metrics={"fabricated_url_count": 1}, sample_size=1, min_sample_size=50)
    assert rollback.rollback and rollback.auto_reraise_allowed is False


# 31
def test_audit_fields_are_sanitized():
    request = _request(request_trace_hash="abcdef0123456789deadbeef")
    audit = build_audit_event(_config(), request, decision="legacy", eligible=False, selected=False, reason="x")
    assert len(audit["correlation"]["request_trace_hash"]) <= 16
    text = str(audit)
    assert "query" not in text and "http" not in text and "Bearer" not in text


# 32
def test_default_production_remains_disabled():
    config = _config()  # even a fully approved staging config
    decision = evaluate_canary_decision(config, _request(environment="production"))
    assert decision.decision == "legacy" and decision.reason == "environment_not_authorized"
    assert config.production_enabled is False
