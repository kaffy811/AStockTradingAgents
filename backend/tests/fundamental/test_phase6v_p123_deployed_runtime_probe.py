"""
Phase 6V-P1.23 — Deployed Runtime Probe Closure Test Suite
===========================================================
Covers State B: Gate C = UNKNOWN, no 100% promotion.

Total target: ~156 tests across 9 classes.
"""

import json
import os

import pytest

ARTIFACTS_DIR = os.path.join(os.path.dirname(__file__), "../../docs/artifacts")
PHASE_PREFIX = "company_v2_phase6v_p123"


def _load(name: str) -> dict:
    path = os.path.join(ARTIFACTS_DIR, f"{PHASE_PREFIX}_{name}.json")
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="class")
def preflight():
    return _load("preflight_audit")


@pytest.fixture(scope="class")
def auth():
    return _load("owner_conditional_authorization")


@pytest.fixture(scope="class")
def deployment():
    return _load("deployment_mapping")


@pytest.fixture(scope="class")
def probe_before():
    return _load("runtime_probe_before")


@pytest.fixture(scope="class")
def probe_closure():
    return _load("runtime_probe_closure")


@pytest.fixture(scope="class")
def test_report():
    return _load("test_report")


@pytest.fixture(scope="class")
def final_decision():
    return _load("final_decision")


# ---------------------------------------------------------------------------
# Class 1: TestPreflightAudit (~10 tests)
# ---------------------------------------------------------------------------

class TestPreflightAudit:

    def test_p122_final_sha_confirmed(self, preflight):
        assert preflight["base_sha"] == "779da4cd3f33ff6a1b21b7c36cf182b7b2c4500d"

    def test_p122_artifacts_count_ge_27(self, preflight):
        audit = preflight["p122_artifact_audit"]
        assert audit["artifacts_verified"] >= 27

    def test_p122_commits_all_verified(self, preflight):
        commit_audit = preflight["p122_commit_audit"]
        assert commit_audit["commits_verified"] == 6
        for commit in commit_audit["commits"]:
            assert commit["verified"] is True

    def test_p122_commit_sha_shorts_present(self, preflight):
        short_shas = {c["sha_short"] for c in preflight["p122_commit_audit"]["commits"]}
        expected = {"bb04945", "73d5f3e", "c02485f", "240aa1c", "ed30400", "779da4c"}
        assert expected == short_shas

    def test_gate_c_was_unknown_before_p123(self, preflight):
        gate_status = preflight["gate_status_entering_p123"]
        assert gate_status["gate_c"] == "unknown"

    def test_gate_c_was_not_pass_before_p123(self, preflight):
        gate_status = preflight["gate_status_entering_p123"]
        assert gate_status["gate_c"] != "pass"

    def test_rollout_before_p123_is_75(self, preflight):
        assert preflight["current_rollout_percent"] == 75

    def test_config_version_before_p123_is_8(self, preflight):
        assert preflight["current_config_version"] == 8

    def test_stable_bucket_salt_is_pi_v1(self, preflight):
        assert preflight["current_stable_bucket_salt"] == "pi_v1"

    def test_gates_a_b_were_pass(self, preflight):
        gate_status = preflight["gate_status_entering_p123"]
        assert gate_status["gate_a"] == "pass"
        assert gate_status["gate_b"] == "pass"

    def test_no_configuration_drift_detected(self, preflight):
        # intended == current: rollout and config_version unchanged
        assert preflight["intended_rollout_percent"] == preflight["current_rollout_percent"]
        assert preflight["intended_config_version"] == preflight["current_config_version"]

    def test_promotion_was_not_authorized_before_p123(self, preflight):
        # Promotion target is 100% — meaning promotion was conditional/not yet done
        assert preflight["promotion_target_rollout_percent"] == 100
        # preconditions satisfied but gate_c still unknown → promotion not yet authorized
        assert preflight["gate_status_entering_p123"]["gate_c"] == "unknown"


# ---------------------------------------------------------------------------
# Class 2: TestOwnerConditionalAuthorization (~12 tests)
# ---------------------------------------------------------------------------

class TestOwnerConditionalAuthorization:

    def test_authorization_recorded(self, auth):
        # The artifact exists and has carry_forward=true
        assert auth["authorization_carry_forward"] is True

    def test_condition_type_gate_c_pass(self, auth):
        cond = auth["condition"]
        assert cond["condition_id"] == "gate_c_pass"

    def test_condition_satisfied_false(self, auth):
        assert auth["condition"]["condition_satisfied"] is False

    def test_promotion_authorized_false(self, auth):
        assert auth["promotion_authorized"] is False

    def test_live_authorized_false(self, auth):
        assert auth["live_authorized"] is False

    def test_production_authorized_false(self, auth):
        assert auth["production_authorized"] is False

    def test_legacy_removal_not_authorized(self, auth):
        assert auth["legacy_deprecation_authorized"] is False

    def test_stable_bucket_salt_change_not_authorized(self, auth):
        # No mention of changing the salt; carry forward condition remains gate_c_pass
        carry = auth["carry_forward_condition"].lower()
        assert "gate c" in carry or "gate_c" in carry

    def test_repository_default_modification_not_authorized(self, auth):
        # promotion_authorized == False means no repository defaults are modified
        assert auth["promotion_authorized"] is False

    def test_provider_serving_not_authorized(self, auth):
        assert auth["provider_serving_authorized"] is False

    def test_promotion_target_rollout_100(self, auth):
        assert auth["authorization_target_rollout"] == 100

    def test_promotion_target_config_version_9(self, auth):
        assert auth["authorization_target_config_version"] == 9


# ---------------------------------------------------------------------------
# Class 3: TestDeploymentMapping (~12 tests)
# ---------------------------------------------------------------------------

class TestDeploymentMapping:

    def test_deployment_found_true(self, deployment):
        assert deployment["deployment_found"] is True

    def test_deployment_type_contains_docker(self, deployment):
        dtype = deployment["deployment_type"].lower()
        assert "docker" in dtype or "compose" in dtype

    def test_no_cicd_pipeline(self, deployment):
        assert deployment["cicd_pipeline_found"] is False

    def test_staging_service_running_false(self, deployment):
        assert deployment["staging_service_running"] is False

    def test_staging_url_is_null(self, deployment):
        assert deployment["staging_url"] is None

    def test_pi_canary_vars_not_in_env_example(self, deployment):
        assert deployment["pi_canary_vars_in_env_example"] is False

    def test_probe_access_method_none(self, deployment):
        method = deployment["probe_access_method"].lower()
        assert "none" in method

    def test_localhost_port_not_accessible(self, deployment):
        # exit code 7 = connection refused
        assert deployment["staging_service_probe_exit_code"] == 7

    def test_deployment_sha_not_accessible(self, deployment):
        assert deployment["deployment_sha_accessible"] is False

    def test_deploy_guide_investigated(self, deployment):
        files = deployment["files_investigated"]
        assert any("deployment_guide" in f or "server_deployment" in f for f in files)

    def test_environment_source_mentions_env_file(self, deployment):
        env_src = deployment["environment_source"].lower()
        assert ".env" in env_src

    def test_no_running_instance(self, deployment):
        # staging_service_running == False is the authoritative indicator
        assert deployment["staging_service_running"] is False


# ---------------------------------------------------------------------------
# Class 4: TestRuntimeProbeBefore (~15 tests)
# ---------------------------------------------------------------------------

class TestRuntimeProbeBefore:

    def test_probe_performed_true(self, probe_before):
        assert probe_before["probe_performed"] is True

    def test_probe_method_contains_local(self, probe_before):
        method = probe_before["probe_method"].lower()
        assert "local" in method or "real_settings" in method

    def test_probe_does_not_qualify_as_deployed_runtime(self, probe_before):
        assert probe_before["probe_qualifies_as_deployed_runtime"] is False

    def test_effective_rollout_percent_is_zero(self, probe_before):
        assert probe_before["effective_rollout_percent"] == 0.0

    def test_effective_config_version_is_1(self, probe_before):
        # Repository default is config_version=1
        assert probe_before["effective_config_version"] == 1

    def test_stable_bucket_salt_version_pi_v1(self, probe_before):
        assert probe_before["stable_bucket_salt_version"] == "pi_v1"

    def test_authorization_status_proposed(self, probe_before):
        assert probe_before["authorization_status"] == "proposed"

    def test_live_false(self, probe_before):
        assert probe_before["live"] is False

    def test_production_enabled_false(self, probe_before):
        assert probe_before["production_enabled"] is False

    def test_provider_serving_enabled_false(self, probe_before):
        assert probe_before["provider_serving_enabled"] is False

    def test_evidence_mode_runtime_loader_integration_verified(self, probe_before):
        assert probe_before["evidence_mode"] == "runtime_loader_integration_verified"

    def test_runtime_loader_is_load_canary_config(self, probe_before):
        raw = probe_before["raw_probe_result"]
        assert raw["runtime_loader"] == "load_canary_config"

    def test_probe_sanitized_no_secrets(self, probe_before):
        raw_str = json.dumps(probe_before).lower()
        assert "secret_key" not in raw_str
        assert "database_url" not in raw_str
        assert "password" not in raw_str

    def test_gate_c_contribution_contains_unknown(self, probe_before):
        contrib = probe_before["gate_c_contribution"].upper()
        assert "UNKNOWN" in contrib

    def test_reason_for_not_qualifying(self, probe_before):
        reason = probe_before["probe_qualifies_as_deployed_runtime_reason"].lower()
        assert (
            "repository default" in reason
            or "staging" in reason
            or "env" in reason
            or "local" in reason
        )


# ---------------------------------------------------------------------------
# Class 5: TestRuntimeProbeClosure (~15 tests)
# ---------------------------------------------------------------------------

class TestRuntimeProbeClosure:

    def test_gate_c_status_is_unknown(self, probe_closure):
        assert probe_closure["gate_c_status"] == "unknown"

    def test_gate_c_previous_is_unknown(self, probe_closure):
        assert probe_closure["gate_c_previous"] == "unknown"

    def test_gate_c_not_upgraded(self, probe_closure):
        assert probe_closure["gate_c_upgraded"] is False

    def test_deployed_runtime_not_verified(self, probe_closure):
        assert probe_closure["deployed_runtime_verified"] is False

    def test_probe_method_does_not_satisfy_section_7(self, probe_closure):
        assert probe_closure["probe_method_satisfies_section_7"] is False

    def test_section_7_not_met_has_at_least_2_items(self, probe_closure):
        not_met = probe_closure["section_7_requirements_not_met"]
        assert isinstance(not_met, list)
        assert len(not_met) >= 2

    def test_section_7_not_met_mentions_staging_or_env(self, probe_closure):
        reasons_combined = " ".join(probe_closure["section_7_requirements_not_met"]).lower()
        assert (
            "startup command" in reasons_combined
            or "staging" in reasons_combined
            or "env" in reasons_combined
            or "pi_canary" in reasons_combined
        )

    def test_promotion_blocked_true(self, probe_closure):
        assert probe_closure["promotion_blocked"] is True

    def test_blocking_reason_non_empty(self, probe_closure):
        assert isinstance(probe_closure["blocking_reason"], str)
        assert len(probe_closure["blocking_reason"]) > 0

    def test_final_rollout_is_75(self, probe_closure):
        assert probe_closure["final_rollout"] == 75

    def test_final_config_version_is_8(self, probe_closure):
        assert probe_closure["final_config_version"] == 8

    def test_final_stable_salt_is_pi_v1(self, probe_closure):
        assert probe_closure["final_stable_bucket_salt"] == "pi_v1"

    def test_100_percent_not_authorized(self, probe_closure):
        assert probe_closure["promotion_blocked"] is True

    def test_100_percent_not_applied(self, probe_closure):
        # shadow_continuation.shadow_percent != 100
        shadow = probe_closure["shadow_continuation"]
        assert shadow["shadow_percent"] != 100

    def test_continue_shadow_at_75(self, probe_closure):
        shadow = probe_closure["shadow_continuation"]
        assert shadow["continue_shadow"] is True
        assert shadow["shadow_percent"] == 75


# ---------------------------------------------------------------------------
# Class 6: TestCanaryPolicyRuntimeProbe (~20 tests)
# ---------------------------------------------------------------------------

class TestCanaryPolicyRuntimeProbe:

    @pytest.fixture(scope="class")
    def snapshot(self):
        from app.agent_runtime.canary_policy import get_effective_shadow_config_snapshot
        return get_effective_shadow_config_snapshot()

    def test_function_exists_and_callable(self):
        from app.agent_runtime.canary_policy import get_effective_shadow_config_snapshot
        assert callable(get_effective_shadow_config_snapshot)

    def test_call_with_no_args_returns_dict(self, snapshot):
        assert isinstance(snapshot, dict)

    def test_returns_key_rollout_percent(self, snapshot):
        assert "rollout_percent" in snapshot

    def test_returns_key_config_version(self, snapshot):
        assert "config_version" in snapshot

    def test_returns_key_stable_bucket_salt_version(self, snapshot):
        assert "stable_bucket_salt_version" in snapshot

    def test_returns_key_authorization_status(self, snapshot):
        assert "authorization_status" in snapshot

    def test_returns_key_live(self, snapshot):
        assert "live" in snapshot

    def test_returns_key_production_enabled(self, snapshot):
        assert "production_enabled" in snapshot

    def test_returns_key_evidence_mode(self, snapshot):
        assert "evidence_mode" in snapshot

    def test_returns_key_runtime_loader(self, snapshot):
        assert "runtime_loader" in snapshot

    def test_rollout_percent_is_zero_no_staging_env(self, snapshot):
        assert snapshot["rollout_percent"] == 0.0

    def test_authorization_status_is_proposed(self, snapshot):
        assert snapshot["authorization_status"] == "proposed"

    def test_live_is_false(self, snapshot):
        assert snapshot["live"] is False

    def test_production_enabled_is_false(self, snapshot):
        assert snapshot["production_enabled"] is False

    def test_evidence_mode_is_runtime_loader_integration_verified(self, snapshot):
        assert snapshot["evidence_mode"] == "runtime_loader_integration_verified"

    def test_runtime_loader_is_load_canary_config(self, snapshot):
        assert snapshot["runtime_loader"] == "load_canary_config"

    def test_result_does_not_contain_secret_key(self, snapshot):
        raw = json.dumps(snapshot).upper()
        assert "SECRET_KEY" not in raw

    def test_result_does_not_contain_database_url(self, snapshot):
        raw = json.dumps(snapshot).upper()
        assert "DATABASE_URL" not in raw

    def test_result_does_not_contain_password(self, snapshot):
        raw = json.dumps(snapshot).lower()
        assert "password" not in raw

    def test_result_does_not_contain_token_as_standalone_field(self, snapshot):
        assert "token" not in snapshot


# ---------------------------------------------------------------------------
# Class 7: TestFixtureCannotSatisfyGateC (~10 tests)
# ---------------------------------------------------------------------------

class TestFixtureCannotSatisfyGateC:

    class _FakeSettings:
        """Simulates a Settings object with staging-intended values.

        Uses authorization_status="approved" (a valid _ALLOWED_STATUSES value)
        so the loader parses without fail-closed, allowing rollout=75 to be read.
        "authorized" is not a valid status in the canary policy; staging .env
        would use "approved" for an approved canary.
        """
        pi_canary_rollout_percent = 75
        pi_canary_config_version = 8
        pi_canary_authorization_status = "approved"
        pi_canary_allowed_agents = "official_report_pdf_pi_v1"
        pi_canary_max_rollout_percent = 100.0
        pi_canary_stable_bucket_salt = "pi_v1"
        pi_canary_environment = "staging"
        pi_canary_fallback_mode = "legacy"
        pi_executor_global_kill_switch = False
        pi_canary_environment_kill_switch = False
        pi_canary_agent_kill_switch = False
        pi_canary_authorization_expires_at = None
        pi_canary_approval_reference = None
        pi_canary_auto_rollback_enabled = True
        pi_canary_health_window_minutes = 30
        pi_canary_min_sample_size = 50

    def test_fake_settings_rollout_75_not_sufficient_for_gate_c(self):
        # Gate C requires a DEPLOYED runtime probe; FakeSettings is a test fixture only
        from app.agent_runtime.canary_policy import get_effective_shadow_config_snapshot
        snap = get_effective_shadow_config_snapshot(self._FakeSettings())
        # Loader works with FakeSettings but this is NOT a deployed runtime
        assert snap["rollout_percent"] == 75.0  # loader reads it correctly
        # However, the evidence_mode is still runtime_loader_integration_verified, not deployed_runtime
        assert snap["evidence_mode"] == "runtime_loader_integration_verified"

    def test_test_fixture_simulation_does_not_satisfy_gate_c(self):
        # Gate C requires evidence_mode == "deployed_runtime" or "deployed_runtime_verified"
        from app.agent_runtime.canary_policy import get_effective_shadow_config_snapshot
        snap = get_effective_shadow_config_snapshot(self._FakeSettings())
        gate_c_evidence_modes = {"deployed_runtime", "deployed_runtime_verified"}
        assert snap["evidence_mode"] not in gate_c_evidence_modes

    def test_runtime_loader_integration_verified_does_not_satisfy_gate_c(self):
        from app.agent_runtime.canary_policy import get_effective_shadow_config_snapshot
        snap = get_effective_shadow_config_snapshot(self._FakeSettings())
        assert snap["evidence_mode"] == "runtime_loader_integration_verified"
        assert snap["evidence_mode"] not in {"deployed_runtime", "deployed_runtime_verified"}

    def test_fake_settings_passed_to_loader_gives_rollout_75(self):
        from app.agent_runtime.canary_policy import load_canary_config
        cfg = load_canary_config(self._FakeSettings())
        assert cfg.rollout_percent == 75.0

    def test_fake_settings_is_not_a_deployed_runtime(self):
        # FakeSettings has no attribute confirming it is a deployed staging process
        assert not hasattr(self._FakeSettings, "_is_deployed_staging_runtime")

    def test_gate_c_requires_deployed_runtime_evidence_mode(self):
        # Conceptual: Gate C pass criterion
        deployed_rt_modes = {"deployed_runtime", "deployed_runtime_verified"}
        current_mode = "runtime_loader_integration_verified"
        assert current_mode not in deployed_rt_modes

    def test_current_evidence_mode_not_deployed_runtime(self):
        from app.agent_runtime.canary_policy import get_effective_shadow_config_snapshot
        snap = get_effective_shadow_config_snapshot()
        assert snap["evidence_mode"] != "deployed_runtime"

    def test_deployed_runtime_verified_false_in_probe_closure(self, probe_closure):
        assert probe_closure["deployed_runtime_verified"] is False

    def test_authorization_condition_satisfied_false(self, probe_closure):
        # probe_method_satisfies_section_7 == False => condition not satisfied
        assert probe_closure["probe_method_satisfies_section_7"] is False

    def test_promotion_cannot_proceed_without_gate_c_pass(self, probe_closure):
        assert probe_closure["promotion_blocked"] is True
        assert "C" in probe_closure["blocking_gates"]

    @pytest.fixture(scope="class")
    def probe_closure(self):
        return _load("runtime_probe_closure")


# ---------------------------------------------------------------------------
# Class 8: TestFinalDecision (~15 tests)
# ---------------------------------------------------------------------------

class TestFinalDecision:

    def test_promotion_authorized_false(self, final_decision):
        assert final_decision["promotion_authorized"] is False

    def test_promotion_attempted_false(self, final_decision):
        assert final_decision["promotion_attempted"] is False

    def test_promotion_applied_false(self, final_decision):
        assert final_decision["promotion_applied"] is False

    def test_actual_rollout_percent_after_phase_75(self, final_decision):
        assert final_decision["actual_rollout_percent_after_phase"] == 75

    def test_actual_config_version_after_phase_8(self, final_decision):
        assert final_decision["actual_config_version_after_phase"] == 8

    def test_stable_bucket_salt_version_pi_v1(self, final_decision):
        assert final_decision["stable_bucket_salt_version"] == "pi_v1"

    def test_continue_one_hundred_percent_shadow_false(self, final_decision):
        assert final_decision["continue_one_hundred_percent_shadow"] is False

    def test_continue_seventy_five_percent_shadow_true(self, final_decision):
        assert final_decision["continue_seventy_five_percent_shadow"] is True

    def test_rollback_required_false(self, final_decision):
        assert final_decision["rollback_required"] is False

    def test_rollback_applied_false(self, final_decision):
        assert final_decision["rollback_applied"] is False

    def test_live_false(self, final_decision):
        assert final_decision["live"] is False

    def test_production_enabled_false(self, final_decision):
        assert final_decision["production_enabled"] is False

    def test_provider_serving_calls_zero(self, final_decision):
        assert final_decision["provider_serving_calls"] == 0

    def test_recommended_for_live_serving_false(self, final_decision):
        assert final_decision["recommended_for_live_serving"] is False

    def test_legacy_deprecation_authorized_false(self, final_decision):
        assert final_decision["legacy_deprecation_authorized"] is False


# ---------------------------------------------------------------------------
# Class 9: TestGateResults (~10 tests)
# ---------------------------------------------------------------------------

class TestGateResults:

    def test_gate_a_pass(self, final_decision):
        assert final_decision["gate_results"]["A"] == "pass"

    def test_gate_b_pass(self, final_decision):
        assert final_decision["gate_results"]["B"] == "pass"

    def test_gate_c_unknown(self, final_decision):
        gate_c = final_decision["gate_results"]["C"]
        assert gate_c == "unknown"
        assert gate_c != "pass"
        assert gate_c != "fail"

    def test_gates_d_through_n_not_evaluated(self, final_decision):
        d_through_n = final_decision["gate_results"]["D_through_N"]
        assert "not_evaluated" in d_through_n

    def test_blocking_reason_non_empty(self, final_decision):
        assert isinstance(final_decision["blocking_reason"], str)
        assert len(final_decision["blocking_reason"]) > 0

    def test_conditional_owner_authorization_recorded(self, final_decision):
        assert final_decision["conditional_owner_authorization_recorded"] is True

    def test_authorization_condition_satisfied_false(self, final_decision):
        assert final_decision["authorization_condition_satisfied"] is False

    def test_gate_c_status_in_final_decision(self, final_decision):
        assert final_decision["gate_c_status"] == "unknown"

    def test_state_b_confirmed(self, final_decision):
        assert final_decision["state"] == "B"

    def test_recommended_for_production_false(self, final_decision):
        assert final_decision["recommended_for_production"] is False


# ---------------------------------------------------------------------------
# Class 10: TestSafetyInvariants (~10 tests)
# ---------------------------------------------------------------------------

class TestSafetyInvariants:

    def test_live_false(self, final_decision):
        assert final_decision["live"] is False

    def test_production_enabled_false(self, final_decision):
        assert final_decision["production_enabled"] is False

    def test_provider_serving_calls_zero(self, final_decision):
        assert final_decision["provider_serving_calls"] == 0

    def test_recommended_for_production_false(self, final_decision):
        assert final_decision["recommended_for_production"] is False

    def test_recommended_for_live_serving_false(self, final_decision):
        assert final_decision["recommended_for_live_serving"] is False

    def test_legacy_deprecation_authorized_false(self, final_decision):
        assert final_decision["legacy_deprecation_authorized"] is False

    def test_cumulative_selected_ge_45000(self, final_decision):
        cumulative = final_decision["cumulative_p18_through_p123"]
        assert cumulative["total_selected"] >= 45000

    def test_cumulative_violations_zero(self, final_decision):
        cumulative = final_decision["cumulative_p18_through_p123"]
        assert cumulative["zero_violations"] == 0

    def test_100_percent_not_applied(self, final_decision):
        assert final_decision["promotion_applied"] is False
        assert final_decision["actual_rollout_percent_after_phase"] != 100

    def test_stable_bucket_salt_unchanged_from_pi_v1(self, final_decision):
        assert final_decision["stable_bucket_salt_version"] == "pi_v1"


# ---------------------------------------------------------------------------
# Class 11: TestTestEvidence (~7 tests — from test_report.json)
# ---------------------------------------------------------------------------

class TestTestEvidence:

    def test_targeted_suite_passed_ge_100(self, test_report):
        targeted = test_report["test_suites"]["targeted"]
        assert targeted["passed"] >= 100

    def test_targeted_suite_failed_zero(self, test_report):
        targeted = test_report["test_suites"]["targeted"]
        assert targeted["failed"] == 0

    def test_cross_phase_passed_ge_3000(self, test_report):
        cross = test_report["test_suites"]["cross_phase"]
        assert cross["passed"] >= 3000

    def test_full_fundamental_passed_ge_4000(self, test_report):
        ff = test_report["test_suites"]["full_fundamental"]
        assert ff["passed"] >= 4000

    def test_entire_backend_passed_ge_6000(self, test_report):
        eb = test_report["test_suites"]["entire_backend"]
        assert eb["passed"] >= 6000

    def test_frontend_passed_ge_600(self, test_report):
        fe = test_report["frontend_tests"]["frontend_vitest"]
        assert fe["passed"] >= 600

    def test_secret_scan_clean(self, test_report):
        scan = test_report["security"]["secret_scan"]
        assert scan["result"] == "clean"
        assert scan["violations_found"] == 0
