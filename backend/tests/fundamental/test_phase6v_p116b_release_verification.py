"""
Phase 6V-P1.16B: Canonical Backend Full Suite + Frontend Release Verification

Tests cover:
1. Environment audit: ephemeral test vars, no production resources
2. Test collection: 0 errors, correct scope
3. Backend full suite results: passed/failed/skipped/exit
4. Frontend: npm ci / test / build
5. P1.16A artifact re-verification (unmodified)
6. Performance threshold classification (warning/review/hard)
7. Secret scan: no credentials committed
8. Resource audit
9. 25% readiness gate (15 conditions)
"""

import json
import pathlib
import pytest

ARTIFACT_DIR = pathlib.Path(__file__).parent.parent.parent / "docs" / "artifacts"


def load(name: str) -> dict:
    return json.loads((ARTIFACT_DIR / name).read_text())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def env_audit():
    return load("pi_official_report_p116b_environment_audit.json")


@pytest.fixture(scope="module")
def collection():
    return load("pi_official_report_p116b_test_collection.json")


@pytest.fixture(scope="module")
def full_suite():
    return load("pi_official_report_p116b_backend_full_suite.json")


@pytest.fixture(scope="module")
def frontend():
    return load("pi_official_report_p116b_frontend_verification.json")


@pytest.fixture(scope="module")
def p116a_audit():
    return load("pi_official_report_p116b_p116a_gate_audit.json")


@pytest.fixture(scope="module")
def secret_scan():
    return load("pi_official_report_p116b_secret_scan.json")


@pytest.fixture(scope="module")
def resource():
    return load("pi_official_report_p116b_resource_audit.json")


@pytest.fixture(scope="module")
def readiness():
    return load("pi_official_report_p116b_twenty_five_percent_readiness.json")


@pytest.fixture(scope="module")
def final_gate():
    return load("pi_official_report_p116b_final_gate.json")


# ---------------------------------------------------------------------------
# 1. Environment Audit
# ---------------------------------------------------------------------------

class TestEnvironmentAudit:
    def test_production_resources_not_used(self, env_audit):
        assert env_audit["production_resources_used"] is False

    def test_services_ephemeral(self, env_audit):
        assert env_audit["services_ephemeral"] is True

    def test_credentials_not_committed(self, env_audit):
        assert env_audit["credentials_committed"] is False

    def test_env_vars_not_committed(self, env_audit):
        assert env_audit["env_vars_not_committed"] is True

    def test_redis_available(self, env_audit):
        assert env_audit["redis_available"] is True

    def test_no_production_database_url_in_artifact(self, env_audit):
        # Artifact must not contain actual credentials or production URLs
        text = json.dumps(env_audit)
        # No actual database password or token in artifact
        assert "password" not in text.lower()
        # No actual complete connection string with credentials
        assert "@" not in env_audit.get("database_host_hash", "")
        assert env_audit.get("credentials_committed") is False

    def test_resolution_documented(self, env_audit):
        assert env_audit["resolution"] != ""

    def test_skip_policy_documented(self, env_audit):
        assert "conftest" in env_audit["integration_test_skip_policy"].lower()


# ---------------------------------------------------------------------------
# 2. Test Collection
# ---------------------------------------------------------------------------

class TestCollection:
    def test_collection_errors_zero(self, collection):
        assert collection["result"]["collection_errors"] == 0

    def test_collected_positive(self, collection):
        assert collection["result"]["collected"] > 0

    def test_exit_code_zero(self, collection):
        assert collection["result"]["exit_code"] == 0

    def test_collection_gate_passed(self, collection):
        assert collection["collection_gate_passed"] is True

    def test_targeted_not_substituted(self, collection):
        # Must document that targeted != full
        assert collection["vs_p111b_historical"]["delta_explanation"] != ""

    def test_delta_explained(self, collection):
        assert collection["vs_p116a_minimal_venv"]["delta_explanation"] != ""
        # P1.16B should collect more than P1.16A (88 errors fixed)
        assert collection["vs_p116a_minimal_venv"]["p116b_collected"] > collection["vs_p116a_minimal_venv"]["p116a_collected"]

    def test_p116a_errors_resolved(self, collection):
        assert collection["vs_p116a_minimal_venv"]["p116a_collection_errors"] == 88
        assert collection["vs_p116a_minimal_venv"]["p116b_collection_errors"] == 0

    def test_no_testpaths_narrowed(self, collection):
        # Verify testpaths were not changed to hide failures
        assert "tests" in collection["testpaths"]


# ---------------------------------------------------------------------------
# 3. Backend Full Suite
# ---------------------------------------------------------------------------

class TestBackendFullSuite:
    def test_collection_errors_zero(self, full_suite):
        assert full_suite["result"]["collection_errors"] == 0

    def test_failed_zero(self, full_suite):
        assert full_suite["result"]["failed"] == 0, \
            f"Backend full suite had {full_suite['result']['failed']} failures"

    def test_exit_code_zero(self, full_suite):
        assert full_suite["result"]["exit_code"] == 0

    def test_passed_substantial(self, full_suite):
        assert full_suite["result"]["passed"] > 3000

    def test_suite_passed(self, full_suite):
        assert full_suite["backend_full_suite_passed"] is True

    def test_not_targeted_substitute(self, full_suite):
        assert full_suite["targeted_not_substituted"] is True

    def test_skipped_all_marked(self, full_suite):
        """Skipped tests must be live-service-marked, not hiding core failures."""
        skip_info = full_suite["skip_breakdown"]
        assert skip_info["core_runtime_skipped"] is False
        assert skip_info["repository_skipped"] is False
        assert skip_info["auth_skipped"] is False
        assert skip_info["streaming_skipped"] is False
        assert skip_info["persistence_skipped"] is False

    def test_skipped_count_reasonable(self, full_suite):
        # Skipped count should be small (live service tests only)
        assert full_suite["result"]["skipped"] < 100

    def test_warnings_not_errors(self, full_suite):
        assert full_suite["warning_breakdown"]["warnings_are_errors"] is False

    def test_duration_reasonable(self, full_suite):
        # Full suite should complete in reasonable time (< 30 minutes)
        assert full_suite["result"]["duration_seconds"] < 1800


# ---------------------------------------------------------------------------
# 4. Frontend Verification
# ---------------------------------------------------------------------------

class TestFrontendVerification:
    def test_npm_ci_exit_zero(self, frontend):
        assert frontend["npm_ci"]["exit_code"] == 0

    def test_npm_ci_passed(self, frontend):
        assert frontend["npm_ci"]["passed"] is True

    def test_lock_file_consistent(self, frontend):
        assert frontend["npm_ci"]["lock_file_consistent"] is True

    def test_frontend_tests_passed(self, frontend):
        assert frontend["npm_test"]["exit_code"] == 0
        assert frontend["npm_test"]["passed"] is True

    def test_frontend_no_failures(self, frontend):
        assert frontend["npm_test"]["tests_failed"] == 0

    def test_frontend_test_count_substantial(self, frontend):
        assert frontend["npm_test"]["tests_passed"] >= 100

    def test_frontend_build_exit_zero(self, frontend):
        assert frontend["npm_build"]["exit_code"] == 0

    def test_frontend_build_passed(self, frontend):
        assert frontend["npm_build"]["passed"] is True

    def test_no_build_errors(self, frontend):
        assert frontend["npm_build"]["errors"] == 0

    def test_frontend_verification_passed(self, frontend):
        assert frontend["frontend_verification_passed"] is True


# ---------------------------------------------------------------------------
# 5. P1.16A Gate Re-verification
# ---------------------------------------------------------------------------

class TestP116AGateAudit:
    def test_selected_1535(self, p116a_audit):
        assert p116a_audit["p116a_verified"]["additional_selected"] == 1535

    def test_unique_symbols_100(self, p116a_audit):
        assert p116a_audit["p116a_verified"]["unique_symbols"] == 100

    def test_safety_1(self, p116a_audit):
        assert p116a_audit["p116a_verified"]["safety_correctness"] == 1.0

    def test_zero_tolerance_0(self, p116a_audit):
        assert p116a_audit["p116a_verified"]["zero_tolerance_count"] == 0

    def test_tool_p95_lt_3800ms(self, p116a_audit):
        assert p116a_audit["p116a_verified"]["tool_p95_ms"] < 3800

    def test_pi_p95_lt_4800ms(self, p116a_audit):
        assert p116a_audit["p116a_verified"]["pi_p95_ms"] < 4800

    def test_pi_over_5s_lte_2pct(self, p116a_audit):
        assert p116a_audit["p116a_verified"]["pi_over_5s_rate_pct"] <= 2.0

    def test_pi_over_6s_zero(self, p116a_audit):
        assert p116a_audit["p116a_verified"]["pi_over_6s_count"] == 0

    def test_live_false(self, p116a_audit):
        assert p116a_audit["p116a_verified"]["live_serving"] is False

    def test_production_false(self, p116a_audit):
        assert p116a_audit["p116a_verified"]["production_enabled"] is False

    def test_artifacts_unmodified(self, p116a_audit):
        assert p116a_audit["artifacts_unmodified"] is True

    def test_gate_audit_passed(self, p116a_audit):
        assert p116a_audit["gate_audit_passed"] is True


# ---------------------------------------------------------------------------
# 6. Performance Threshold Classification
# ---------------------------------------------------------------------------

class TestPerformanceThresholds:
    """Pi p95=4748ms: above 4700ms warning, below 4800ms review, far below 5000ms hard blocker."""

    def test_pi_p95_above_warning_threshold(self, p116a_audit):
        pi_p95 = p116a_audit["p116a_verified"]["pi_p95_ms"]
        warning = p116a_audit["performance_threshold_classification"]["warning_threshold_ms"]
        assert pi_p95 > warning, f"Expected pi_p95 {pi_p95} > warning {warning}"

    def test_warning_triggered(self, p116a_audit):
        assert p116a_audit["performance_threshold_classification"]["warning_triggered"] is True

    def test_review_not_triggered(self, p116a_audit):
        assert p116a_audit["performance_threshold_classification"]["review_triggered"] is False

    def test_hard_blocker_not_triggered(self, p116a_audit):
        assert p116a_audit["performance_threshold_classification"]["hard_blocker_triggered"] is False

    def test_4700ms_not_hard_blocker(self, p116a_audit):
        """4700ms warning must NOT be treated as a hard promotion blocker."""
        # Performance gate passes despite warning
        assert p116a_audit["gate_audit_passed"] is True

    def test_p117_monitor_requirement_documented(self, p116a_audit):
        assert "4800ms" in p116a_audit["performance_threshold_classification"]["p117_monitor_requirement"]

    def test_pi_p95_strictly_lt_4800ms(self, p116a_audit):
        """4800ms is the review threshold; current value must be strictly less."""
        assert p116a_audit["p116a_verified"]["pi_p95_ms"] < 4800

    def test_pi_p95_strictly_lt_5000ms(self, p116a_audit):
        """5000ms is the hard blocker; must be far below."""
        assert p116a_audit["p116a_verified"]["pi_p95_ms"] < 5000


# ---------------------------------------------------------------------------
# 7. Secret Scan
# ---------------------------------------------------------------------------

class TestSecretScan:
    def test_no_secrets_committed(self, secret_scan):
        assert secret_scan["secrets_found"] == 0

    def test_no_tokens_committed(self, secret_scan):
        assert secret_scan["tokens_found"] == 0

    def test_no_database_urls_committed(self, secret_scan):
        assert secret_scan["database_urls_found"] == 0

    def test_no_env_files_committed(self, secret_scan):
        assert secret_scan["env_vars_committed"] is False
        assert secret_scan["dotenv_files_committed"] is False

    def test_scan_clean(self, secret_scan):
        assert secret_scan["scan_clean"] is True


# ---------------------------------------------------------------------------
# 8. Resource Audit
# ---------------------------------------------------------------------------

class TestResourceAudit:
    def test_backend_suite_no_task_leak(self, resource):
        assert resource["backend_suite_resource"]["async_tasks_leaked"] == 0

    def test_backend_suite_no_db_leak(self, resource):
        assert resource["backend_suite_resource"]["db_connections_leaked"] == 0

    def test_backend_suite_no_redis_leak(self, resource):
        assert resource["backend_suite_resource"]["redis_connections_leaked"] == 0

    def test_backend_suite_no_pending_rollback(self, resource):
        assert resource["backend_suite_resource"]["PendingRollbackError"] == 0

    def test_shadow_no_pool_exhaustion(self, resource):
        assert resource["shadow_canary_resource"]["pool_exhaustion"] == 0

    def test_shadow_no_task_leak(self, resource):
        assert resource["shadow_canary_resource"]["task_leak"] == 0

    def test_resource_gate_passed(self, resource):
        assert resource["resource_gate_passed"] is True


# ---------------------------------------------------------------------------
# 9. 25% Readiness Gate (15 conditions)
# ---------------------------------------------------------------------------

class TestTwentyFivePercentReadiness:
    def test_all_conditions_met(self, readiness):
        failed = [c for c in readiness["conditions"] if not c["met"]]
        assert len(failed) == 0, f"Unmet: {[c['desc'] for c in failed]}"

    def test_conditions_count_15(self, readiness):
        assert readiness["conditions_total"] == 15
        assert readiness["conditions_met"] == 15

    def test_ready_for_decision(self, readiness):
        assert readiness["ready_for_twenty_five_percent_decision"] is True

    def test_decision_required_from_owner(self, readiness):
        assert readiness["decision_required_from_project_owner"] is True

    def test_not_raise_25pct(self, readiness):
        assert readiness["recommended_to_raise_to_twenty_five_percent"] is False

    def test_continue_10pct(self, readiness):
        assert readiness["recommended_to_continue_ten_percent"] is True

    def test_performance_review_not_triggered(self, readiness):
        assert readiness["performance_review_triggered"] is False

    def test_rollout_10pct(self, readiness):
        assert readiness["rollout_percent"] == 10

    def test_live_not_authorized(self, readiness):
        assert readiness["live_serving_authorized"] is False

    def test_production_not_authorized(self, readiness):
        assert readiness["production_authorized"] is False

    def test_25pct_not_authorized(self, readiness):
        assert readiness["twenty_five_percent_authorized"] is False

    def test_collection_condition_met(self, readiness):
        c01 = next(c for c in readiness["conditions"] if c["id"] == "C01")
        assert c01["met"] is True
        assert c01["value"] == 0

    def test_backend_full_suite_condition_met(self, readiness):
        c02 = next(c for c in readiness["conditions"] if c["id"] == "C02")
        assert c02["met"] is True

    def test_frontend_conditions_met(self, readiness):
        c04 = next(c for c in readiness["conditions"] if c["id"] == "C04")
        c05 = next(c for c in readiness["conditions"] if c["id"] == "C05")
        c06 = next(c for c in readiness["conditions"] if c["id"] == "C06")
        assert c04["met"] is True  # npm ci
        assert c05["met"] is True  # frontend tests
        assert c06["met"] is True  # frontend build

    def test_p116a_pi_p95_condition_met(self, readiness):
        c11 = next(c for c in readiness["conditions"] if c["id"] == "C11")
        assert c11["met"] is True
        assert "4748" in str(c11["value"])


# ---------------------------------------------------------------------------
# 10. Final Gate
# ---------------------------------------------------------------------------

class TestFinalGate:
    def test_p116b_gate_passed(self, final_gate):
        assert final_gate["p116b_gate_passed"] is True

    def test_collection_errors_zero(self, final_gate):
        assert final_gate["backend_collection_errors"] == 0

    def test_backend_full_suite_passed(self, final_gate):
        assert final_gate["backend_full_suite_passed"] is True

    def test_backend_failed_zero(self, final_gate):
        assert final_gate["backend_failed"] == 0

    def test_frontend_tests_passed(self, final_gate):
        assert final_gate["frontend_tests_passed"] is True

    def test_frontend_build_passed(self, final_gate):
        assert final_gate["frontend_build_passed"] is True

    def test_p116a_safety_passed(self, final_gate):
        assert final_gate["p116a_safety_gate_passed"] is True

    def test_p116a_performance_passed(self, final_gate):
        assert final_gate["p116a_performance_margin_gate_passed"] is True

    def test_15_readiness_conditions(self, final_gate):
        assert final_gate["readiness_conditions_met"] == 15
        assert final_gate["readiness_conditions_total"] == 15

    def test_ready_for_25pct_decision(self, final_gate):
        assert final_gate["ready_for_twenty_five_percent_decision"] is True

    def test_not_raise_to_25pct(self, final_gate):
        assert final_gate["recommended_to_raise_to_twenty_five_percent"] is False

    def test_rollout_stays_10pct(self, final_gate):
        assert final_gate["rollout_percent"] == 10

    def test_not_recommended_live(self, final_gate):
        assert final_gate["recommended_for_live_serving"] is False

    def test_not_recommended_production(self, final_gate):
        assert final_gate["recommended_for_production"] is False

    def test_production_disabled(self, final_gate):
        assert final_gate["production_enabled"] is False
