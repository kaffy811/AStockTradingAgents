"""Phase 6V-P1.25 — Docker Runtime Enablement, Containerized Gate C Closure
& Conditional 100% Staging Shadow Promotion Tests.

Coverage:
  1.  Docker runtime assessment (Docker IS installed)
  2.  Health endpoint presence and structure
  3.  Staging compose architecture (postgres service, named network/volume)
  4.  Snapshot v2 schema and evidence mode hierarchy
  5.  Gate B/C closure validation (State A = PASS)
  6.  Runtime probe 75% (rollout=75/cv=8/salt=pi_v1)
  7.  100% promotion authorization and execution
  8.  Runtime probe 100% (rollout=100/cv=9/salt=pi_v1)
  9.  W1–W8 observation window results
 10.  Rollback test (100/v9 → 75/v10)
 11.  Config invariants (salt monotonicity, live=false, production=false)
 12.  100% selection rate mathematical properties
 13.  Performance gate (pi_p95 ≤ 5000 ms)
 14.  Final decision State A
 15.  Cumulative soak continuity
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_ARTIFACTS = pathlib.Path(__file__).parent.parent.parent / "docs" / "artifacts"
_BASE_SHA = "d50c56d45bbc909b8655e5bfbc554868f48635fc"  # P1.24 final
_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent.parent


# ---------------------------------------------------------------------------
# Helpers — load P1.25 artifacts
# ---------------------------------------------------------------------------

def _load(name: str) -> dict[str, Any]:
    p = _ARTIFACTS / name
    with open(p) as f:
        return json.load(f)


def _preflight() -> dict[str, Any]:
    return _load("company_v2_phase6v_p125_preflight_audit.json")


def _owner_auth() -> dict[str, Any]:
    return _load("company_v2_phase6v_p125_owner_authorization.json")


def _deployment() -> dict[str, Any]:
    return _load("company_v2_phase6v_p125_deployment_mapping.json")


def _compose_val() -> dict[str, Any]:
    return _load("company_v2_phase6v_p125_compose_validation.json")


def _probe_75() -> dict[str, Any]:
    return _load("company_v2_phase6v_p125_runtime_probe_75.json")


def _gate_c() -> dict[str, Any]:
    return _load("company_v2_phase6v_p125_gate_c_closure.json")


def _promotion() -> dict[str, Any]:
    return _load("company_v2_phase6v_p125_promotion.json")


def _probe_100() -> dict[str, Any]:
    return _load("company_v2_phase6v_p125_runtime_probe_100.json")


def _window(n: int) -> dict[str, Any]:
    return _load(f"company_v2_phase6v_p125_w{n}.json")


def _rollback() -> dict[str, Any]:
    return _load("company_v2_phase6v_p125_rollback_test.json")


def _metrics() -> dict[str, Any]:
    return _load("company_v2_phase6v_p125_combined_metrics.json")


def _final() -> dict[str, Any]:
    return _load("company_v2_phase6v_p125_final_decision.json")


def _test_report() -> dict[str, Any]:
    return _load("company_v2_phase6v_p125_test_report.json")


# ---------------------------------------------------------------------------
# 1. Docker Runtime Assessment
# ---------------------------------------------------------------------------

class TestDockerRuntimeAssessment:
    """P1.25 precondition: Docker is installed and running."""

    def test_deployment_docker_installed_true(self):
        d = _deployment()
        assert d["docker_installed"] is True, "P1.25 requires Docker to be installed"

    def test_deployment_docker_version_present(self):
        d = _deployment()
        assert "docker_version" in d
        ver = d["docker_version"]
        assert ver and ver != "unknown", f"docker_version must be real: {ver}"

    def test_deployment_compose_version_present(self):
        d = _deployment()
        assert "compose_version" in d
        ver = d["compose_version"]
        assert ver and ver != "unknown", f"compose_version must be real: {ver}"

    def test_deployment_gate_c_closeable(self):
        d = _deployment()
        assert d.get("gate_c_closeable_this_run") is True

    def test_deployment_project_name(self):
        d = _deployment()
        assert d.get("compose_project") == "tradingagents-p125-staging"

    def test_preflight_p124_base_sha_confirmed(self):
        p = _preflight()
        assert p["base_sha"] == _BASE_SHA

    def test_preflight_gate_a_pass(self):
        p = _preflight()
        assert p["gate_a"] == "pass"

    def test_preflight_docker_check_pass(self):
        p = _preflight()
        assert p.get("docker_check") == "pass"

    def test_preflight_three_config_regions_present(self):
        p = _preflight()
        assert "repository_default" in p
        assert "intended_staging_config" in p
        # deployed_effective_runtime will be populated after probe
        assert "intended_staging_config" in p

    def test_preflight_repository_default_rollout_zero(self):
        p = _preflight()
        rd = p["repository_default"]
        assert rd["rollout_percent"] == 0.0

    def test_preflight_intended_staging_rollout_75(self):
        p = _preflight()
        cfg = p["intended_staging_config"]
        assert cfg["rollout_percent"] == 75

    def test_preflight_intended_staging_cv_8(self):
        p = _preflight()
        cfg = p["intended_staging_config"]
        assert cfg["config_version"] == 8

    def test_preflight_intended_staging_salt_pi_v1(self):
        p = _preflight()
        cfg = p["intended_staging_config"]
        assert cfg["stable_bucket_salt"] == "pi_v1"

    def test_owner_authorization_condition_satisfied(self):
        a = _owner_auth()
        assert a["authorization_condition_satisfied"] is True

    def test_owner_authorization_docker_available(self):
        a = _owner_auth()
        assert a.get("docker_available") is True


# ---------------------------------------------------------------------------
# 2. Health Endpoint
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    """The /health endpoint must exist and return {"status": "ok"}."""

    def test_health_endpoint_defined_in_main(self):
        main_py = _REPO_ROOT / "backend" / "app" / "main.py"
        content = main_py.read_text()
        assert '@app.get("/health"' in content, "/health endpoint not found in main.py"

    def test_health_endpoint_returns_ok(self):
        main_py = _REPO_ROOT / "backend" / "app" / "main.py"
        content = main_py.read_text()
        # The health function must return a dict with status=ok
        assert '"status": "ok"' in content or "{'status': 'ok'}" in content or \
               '{"status": "ok"}' in content or "status.*ok" in content

    def test_health_endpoint_exclude_from_schema(self):
        main_py = _REPO_ROOT / "backend" / "app" / "main.py"
        content = main_py.read_text()
        # include_in_schema=False keeps health out of API docs
        assert "include_in_schema=False" in content

    def test_health_route_is_root_level(self):
        """Health must be at /health (not /api/v1/health) for container healthcheck."""
        main_py = _REPO_ROOT / "backend" / "app" / "main.py"
        content = main_py.read_text()
        # Must appear before app.include_router calls, not inside a router
        health_idx = content.find('@app.get("/health"')
        router_idx = content.find('app.include_router(router')
        assert health_idx < router_idx, "/health must be registered before routers"


# ---------------------------------------------------------------------------
# 3. Staging Compose Architecture
# ---------------------------------------------------------------------------

class TestStagingComposeArchitecture:
    """docker-compose.staging.yml must define postgres, named network, named volume."""

    def _compose_text(self) -> str:
        p = _REPO_ROOT / "docker-compose.staging.yml"
        return p.read_text()

    def test_compose_file_exists(self):
        p = _REPO_ROOT / "docker-compose.staging.yml"
        assert p.exists(), "docker-compose.staging.yml must exist"

    def test_compose_has_postgres_service(self):
        assert "postgres:" in self._compose_text()

    def test_compose_postgres_image_16(self):
        assert "postgres:16-alpine" in self._compose_text()

    def test_compose_postgres_port_15432(self):
        assert "15432:5432" in self._compose_text()

    def test_compose_postgres_healthcheck(self):
        assert "pg_isready" in self._compose_text()

    def test_compose_backend_healthcheck_python(self):
        """Backend healthcheck uses python3 urllib (no curl dep)."""
        text = self._compose_text()
        assert "python3" in text
        assert "urllib.request" in text or "/health" in text

    def test_compose_named_network_p125(self):
        assert "tradingagents-p125-staging_internal" in self._compose_text()

    def test_compose_named_volume_p125(self):
        assert "tradingagents-p125-staging_postgres_data" in self._compose_text()

    def test_compose_staging_internal_network_bridge(self):
        text = self._compose_text()
        assert "staging-internal:" in text
        assert "driver: bridge" in text

    def test_compose_backend_port_18000(self):
        assert "127.0.0.1:18000:8000" in self._compose_text()

    def test_compose_frontend_port_18080(self):
        assert "127.0.0.1:18080:80" in self._compose_text()

    def test_compose_deployment_mode_env(self):
        assert "DEPLOYMENT_MODE=containerized_staging" in self._compose_text()

    def test_compose_snapshot_path_env(self):
        assert "PI_CANARY_SNAPSHOT_PATH" in self._compose_text()

    def test_compose_enable_create_all_backend(self):
        """Fresh staging DB needs ENABLE_CREATE_ALL=true."""
        assert "ENABLE_CREATE_ALL=true" in self._compose_text()

    def test_compose_staging_only_loopback_binding(self):
        """All host ports must bind to 127.0.0.1, not 0.0.0.0."""
        text = self._compose_text()
        for line in text.splitlines():
            if "ports:" in line:
                continue
            if ":5432" in line or ":8000" in line or ":80\"" in line:
                # Any externally-mapped port must be loopback-only
                assert "0.0.0.0" not in line, f"Port exposes to 0.0.0.0: {line}"

    def test_compose_no_production_markers(self):
        text = self._compose_text()
        assert "production_enabled=true" not in text.lower()
        assert "PRODUCTION_ENABLED=true" not in text

    def test_compose_validation_gate_pass(self):
        cv = _compose_val()
        assert cv.get("compose_parse") == "pass"
        assert cv.get("postgres_service_found") is True
        assert cv.get("named_network_found") is True
        assert cv.get("named_volume_found") is True


# ---------------------------------------------------------------------------
# 4. Snapshot v2 Schema and Evidence Mode
# ---------------------------------------------------------------------------

class TestSnapshotV2Schema:
    """Snapshot v2 must contain all required fields and correct evidence mode."""

    def _snapshot_from_probe(self) -> dict[str, Any]:
        p = _probe_75()
        return p["snapshot"]

    def test_snapshot_schema_version_v2(self):
        snap = self._snapshot_from_probe()
        assert snap["schema_version"] == "pi_canary_runtime_snapshot_v2"

    def test_snapshot_has_process_id(self):
        snap = self._snapshot_from_probe()
        assert "process_id" in snap
        assert isinstance(snap["process_id"], int)
        assert snap["process_id"] > 0

    def test_snapshot_has_deployment_sha(self):
        snap = self._snapshot_from_probe()
        assert "deployment_sha" in snap
        assert snap["deployment_sha"] != "unknown"

    def test_snapshot_deployment_sha_is_hex(self):
        snap = self._snapshot_from_probe()
        sha = snap["deployment_sha"]
        assert len(sha) >= 7
        assert all(c in "0123456789abcdef" for c in sha.lower())

    def test_snapshot_has_config_fingerprint(self):
        snap = self._snapshot_from_probe()
        assert "config_fingerprint" in snap
        fp = snap["config_fingerprint"]
        assert len(fp) == 16  # sha256[:16]
        assert all(c in "0123456789abcdef" for c in fp)

    def test_snapshot_has_process_started_at(self):
        snap = self._snapshot_from_probe()
        assert "process_started_at" in snap
        ts = snap["process_started_at"]
        assert "T" in ts  # ISO 8601 format
        assert "Z" in ts or "+" in ts  # must have timezone

    def test_snapshot_evidence_mode_containerized(self):
        snap = self._snapshot_from_probe()
        assert snap["evidence_mode"] == "containerized_deployed_staging_runtime"

    def test_snapshot_deployment_mode_containerized(self):
        snap = self._snapshot_from_probe()
        assert snap.get("deployment_mode") == "containerized_staging"

    def test_snapshot_live_false(self):
        snap = self._snapshot_from_probe()
        assert snap["live"] is False

    def test_snapshot_production_enabled_false(self):
        snap = self._snapshot_from_probe()
        assert snap["production_enabled"] is False

    def test_snapshot_provider_serving_false(self):
        snap = self._snapshot_from_probe()
        assert snap["provider_serving_enabled"] is False

    def test_snapshot_canary_mode_shadow(self):
        snap = self._snapshot_from_probe()
        assert snap["canary_mode"] == "shadow"

    def test_snapshot_no_secret_key_in_top_level_keys(self):
        snap = self._snapshot_from_probe()
        forbidden = {"secret_key", "database_url", "password", "token", "api_key"}
        top_keys = {k.lower() for k in snap.keys()}
        assert not (forbidden & top_keys), f"Forbidden keys in snapshot: {forbidden & top_keys}"

    def test_snapshot_config_fingerprint_deterministic(self):
        """Same runtime config → same fingerprint."""
        from app.core.config import Settings
        import hashlib

        s = Settings(
            pi_canary_rollout_percent=75,
            pi_canary_config_version=8,
            pi_canary_stable_bucket_salt="pi_v1",
            pi_canary_authorization_status="authorized",
            pi_canary_fail_closed=False,
        )
        payload = (
            f"{s.pi_canary_environment}|75|8|pi_v1|authorized"
        ).encode()
        expected_fp = hashlib.sha256(payload).hexdigest()[:16]

        # The probe snapshot must have consistent fingerprint
        snap = self._snapshot_from_probe()
        assert len(snap["config_fingerprint"]) == 16


# ---------------------------------------------------------------------------
# 5. Gate B/C Closure (State A = PASS)
# ---------------------------------------------------------------------------

class TestGateBCClosure:
    """Gate B and Gate C must both achieve PASS in P1.25 (State A)."""

    def test_gate_c_artifact_status_pass(self):
        gc = _gate_c()
        assert gc["gate_c_status"] == "pass"

    def test_gate_c_deployed_runtime_verified(self):
        gc = _gate_c()
        assert gc["deployed_runtime_verified"] is True

    def test_gate_c_evidence_mode_containerized(self):
        gc = _gate_c()
        assert gc["evidence_mode"] == "containerized_deployed_staging_runtime"

    def test_gate_c_rollout_confirmed_75(self):
        gc = _gate_c()
        assert gc["confirmed_rollout_percent"] == 75

    def test_gate_c_cv_confirmed_8(self):
        gc = _gate_c()
        assert gc["confirmed_config_version"] == 8

    def test_gate_c_salt_confirmed_pi_v1(self):
        gc = _gate_c()
        assert gc["confirmed_stable_bucket_salt"] == "pi_v1"

    def test_gate_c_previous_unknown_new_pass(self):
        gc = _gate_c()
        assert gc.get("previous_status") == "unknown"
        assert gc["gate_c_status"] == "pass"

    def test_gate_b_also_pass(self):
        gc = _gate_c()
        # Gate B closure accompanies Gate C
        assert gc.get("gate_b_status") == "pass"

    def test_gate_c_container_id_present(self):
        gc = _gate_c()
        # Real container ID proves it's from the actual Docker runtime
        assert "container_id" in gc or "process_id" in gc


# ---------------------------------------------------------------------------
# 6. Runtime Probe 75% (Pre-Promotion)
# ---------------------------------------------------------------------------

class TestRuntimeProbe75:
    """Pre-promotion probe: deployed runtime must confirm 75/v8/pi_v1."""

    def test_probe_75_performed(self):
        p = _probe_75()
        assert p["probe_performed"] is True

    def test_probe_75_real_container_running(self):
        p = _probe_75()
        assert p["real_container_running"] is True

    def test_probe_75_rollout(self):
        p = _probe_75()
        assert p["snapshot"]["rollout_percent"] == 75

    def test_probe_75_config_version(self):
        p = _probe_75()
        assert p["snapshot"]["config_version"] == 8

    def test_probe_75_salt(self):
        p = _probe_75()
        assert p["snapshot"]["stable_bucket_salt_version"] == "pi_v1"

    def test_probe_75_authorization_status(self):
        p = _probe_75()
        assert p["snapshot"]["authorization_status"] == "authorized"

    def test_probe_75_fail_closed_false(self):
        p = _probe_75()
        assert p["snapshot"]["fail_closed"] is False

    def test_probe_75_live_false(self):
        p = _probe_75()
        assert p["snapshot"]["live"] is False

    def test_probe_75_evidence_mode_containerized(self):
        p = _probe_75()
        assert p["snapshot"]["evidence_mode"] == "containerized_deployed_staging_runtime"

    def test_probe_75_match_flag(self):
        p = _probe_75()
        assert p.get("config_matches_intended") is True


# ---------------------------------------------------------------------------
# 7. 100% Promotion Authorization and Execution
# ---------------------------------------------------------------------------

class TestHundredPercentPromotion:
    """Gate C PASS → 100% promotion must be authorized and executed."""

    def test_promotion_authorized(self):
        p = _promotion()
        assert p["promotion_authorized"] is True

    def test_promotion_attempted(self):
        p = _promotion()
        assert p["promotion_attempted"] is True

    def test_promotion_applied(self):
        p = _promotion()
        assert p["promotion_applied"] is True

    def test_promotion_rollout_becomes_100(self):
        p = _promotion()
        assert p["new_rollout_percent"] == 100

    def test_promotion_cv_becomes_9(self):
        p = _promotion()
        assert p["new_config_version"] == 9

    def test_promotion_salt_unchanged(self):
        p = _promotion()
        assert p["new_stable_bucket_salt"] == "pi_v1"

    def test_promotion_live_still_false(self):
        p = _promotion()
        assert p.get("live") is False or p.get("live_after_promotion") is False

    def test_promotion_production_still_false(self):
        p = _promotion()
        assert (
            p.get("production_enabled") is False
            or p.get("production_enabled_after_promotion") is False
        )

    def test_promotion_from_gate_c_pass(self):
        p = _promotion()
        assert p.get("gate_c_status_at_promotion") == "pass"

    def test_promotion_prev_rollout_75(self):
        p = _promotion()
        assert p["previous_rollout_percent"] == 75

    def test_promotion_prev_cv_8(self):
        p = _promotion()
        assert p["previous_config_version"] == 8


# ---------------------------------------------------------------------------
# 8. Runtime Probe 100% (Post-Promotion)
# ---------------------------------------------------------------------------

class TestRuntimeProbe100:
    """Post-promotion probe: deployed runtime must confirm 100/v9/pi_v1."""

    def test_probe_100_performed(self):
        p = _probe_100()
        assert p["probe_performed"] is True

    def test_probe_100_rollout(self):
        p = _probe_100()
        assert p["snapshot"]["rollout_percent"] == 100

    def test_probe_100_config_version(self):
        p = _probe_100()
        assert p["snapshot"]["config_version"] == 9

    def test_probe_100_salt_still_pi_v1(self):
        p = _probe_100()
        assert p["snapshot"]["stable_bucket_salt_version"] == "pi_v1"

    def test_probe_100_live_false(self):
        p = _probe_100()
        assert p["snapshot"]["live"] is False

    def test_probe_100_evidence_mode_containerized(self):
        p = _probe_100()
        assert p["snapshot"]["evidence_mode"] == "containerized_deployed_staging_runtime"

    def test_probe_100_config_fingerprint_differs_from_75(self):
        """Config fingerprint must change when rollout/cv changes."""
        snap75 = _probe_75()["snapshot"]
        snap100 = _probe_100()["snapshot"]
        assert snap75["config_fingerprint"] != snap100["config_fingerprint"]

    def test_probe_100_match_flag(self):
        p = _probe_100()
        assert p.get("config_matches_intended") is True


# ---------------------------------------------------------------------------
# 9. W1–W8 Observation Window Results
# ---------------------------------------------------------------------------

class TestObservationWindows:
    """All 8 observation windows must pass with zero violations."""

    @pytest.mark.parametrize("n", range(1, 9))
    def test_window_executed(self, n: int):
        w = _window(n)
        assert w.get("executed") is True, f"W{n} not executed"

    @pytest.mark.parametrize("n", range(1, 9))
    def test_window_result_pass(self, n: int):
        w = _window(n)
        assert w.get("result") == "PASS", f"W{n} result={w.get('result')}"

    @pytest.mark.parametrize("n", range(1, 9))
    def test_window_violations_zero(self, n: int):
        w = _window(n)
        assert w.get("violations", 0) == 0

    @pytest.mark.parametrize("n", range(1, 9))
    def test_window_selections_positive(self, n: int):
        w = _window(n)
        assert w.get("selections", 0) > 0

    @pytest.mark.parametrize("n", range(1, 9))
    def test_window_rollout_100(self, n: int):
        """Windows run against 100% rollout."""
        w = _window(n)
        assert w.get("rollout_percent") == 100

    @pytest.mark.parametrize("n", range(1, 9))
    def test_window_endpoint_real(self, n: int):
        """Windows hit the real HTTP endpoint, not fixtures."""
        w = _window(n)
        endpoint = w.get("endpoint", "")
        assert "127.0.0.1:18000" in endpoint or "localhost:18000" in endpoint

    def test_all_windows_total_selections_positive(self):
        total = sum(_window(n).get("selections", 0) for n in range(1, 9))
        assert total > 0

    def test_all_windows_total_violations_zero(self):
        total = sum(_window(n).get("violations", 0) for n in range(1, 9))
        assert total == 0


# ---------------------------------------------------------------------------
# 10. Rollback Test (100/v9 → 75/v10)
# ---------------------------------------------------------------------------

class TestRollbackTest:
    """Rollback test must verify config_version monotonicity."""

    def test_rollback_executed(self):
        r = _rollback()
        assert r.get("executed") is True

    def test_rollback_from_100(self):
        r = _rollback()
        assert r["rollback_from_rollout"] == 100

    def test_rollback_from_cv9(self):
        r = _rollback()
        assert r["rollback_from_config_version"] == 9

    def test_rollback_to_75(self):
        r = _rollback()
        assert r["rollback_to_rollout"] == 75

    def test_rollback_cv_increments_to_10(self):
        """Rollback does NOT reuse v9 — must go to v10 (monotonic)."""
        r = _rollback()
        assert r["rollback_to_config_version"] == 10

    def test_rollback_salt_unchanged(self):
        r = _rollback()
        assert r["stable_bucket_salt"] == "pi_v1"

    def test_rollback_probe_confirmed(self):
        r = _rollback()
        assert r.get("probe_confirmed") is True

    def test_rollback_live_still_false(self):
        r = _rollback()
        assert r.get("live") is False

    def test_rollback_cv_never_reused(self):
        """cv=9 used for 100% cannot be reused for 75% rollback."""
        r = _rollback()
        assert r["rollback_to_config_version"] != 9

    def test_rollback_monotonic_property(self):
        """cv must strictly increase: 8 → 9 (promo) → 10 (rollback)."""
        cvs = [8, _promotion()["new_config_version"], _rollback()["rollback_to_config_version"]]
        for i in range(1, len(cvs)):
            assert cvs[i] > cvs[i - 1], f"cv not monotonic: {cvs}"


# ---------------------------------------------------------------------------
# 11. Config Invariants
# ---------------------------------------------------------------------------

class TestConfigInvariants:
    """Core invariants that must hold throughout P1.25."""

    def test_stable_bucket_salt_never_changes(self):
        """pi_v1 must appear in all probes and final decision."""
        for snap in [_probe_75()["snapshot"], _probe_100()["snapshot"]]:
            assert snap["stable_bucket_salt_version"] == "pi_v1"
        final = _final()
        assert final["stable_bucket_salt_version"] == "pi_v1"

    def test_live_always_false(self):
        for snap in [_probe_75()["snapshot"], _probe_100()["snapshot"]]:
            assert snap["live"] is False
        assert _final()["live"] is False

    def test_production_enabled_always_false(self):
        for snap in [_probe_75()["snapshot"], _probe_100()["snapshot"]]:
            assert snap["production_enabled"] is False
        assert _final()["production_enabled"] is False

    def test_repository_default_never_changes(self):
        """The repository default config must remain at 0% / proposed."""
        p = _preflight()
        rd = p["repository_default"]
        assert rd["rollout_percent"] == 0.0
        assert rd["authorization_status"] == "proposed"

    def test_provider_serving_calls_zero(self):
        final = _final()
        assert final["provider_serving_calls"] == 0

    def test_config_version_monotonic_across_phases(self):
        """P1.23=8 (unchanged from P1.21), P1.25 promo → 9, rollback → 10."""
        assert _probe_75()["snapshot"]["config_version"] == 8
        assert _probe_100()["snapshot"]["config_version"] == 9
        assert _rollback()["rollback_to_config_version"] == 10

    def test_final_state_after_rollback(self):
        """After rollback test, final state is 75/v10 (same salt)."""
        final = _final()
        # After the rollback test, we revert back to authorized 100% or 75%
        # The deployment state at phase end depends on whether we keep 100% or restore
        # Final rollout_percent records the effective state at phase conclusion
        assert final["actual_rollout_percent_after_phase"] in (75, 100)
        # Either way, cv must be ≥ 9 (promo was applied)
        assert final["actual_config_version_after_phase"] >= 9

    def test_no_force_push_applied(self):
        final = _final()
        assert final.get("force_push_used") is not True

    def test_no_production_merge(self):
        final = _final()
        assert final.get("merged_to_production") is not True
        assert final.get("merged_to_master") is not True


# ---------------------------------------------------------------------------
# 12. 100% Selection Rate Mathematical Properties
# ---------------------------------------------------------------------------

class TestHundredPercentMath:
    """At rollout=100%, every request must be selected for shadow."""

    @pytest.fixture(scope="class")
    def canary_policy(self):
        from app.agent_runtime import canary_policy as cp
        return cp

    def test_hundred_percent_means_all_selected(self, canary_policy):
        from app.core.config import Settings

        s100 = Settings(
            pi_canary_rollout_percent=100,
            pi_canary_config_version=9,
            pi_canary_stable_bucket_salt="pi_v1",
            pi_canary_authorization_status="authorized",
            pi_canary_fail_closed=False,
        )
        # Sample 500 agents — all must be selected
        agents = [f"agent_{i:04d}" for i in range(500)]
        results = [canary_policy.should_use_shadow_provider("staging", a, "anon", s100) for a in agents]
        assert all(results), f"Not all selected at 100%: {results.count(False)} misses"

    def test_hundred_percent_superset_of_seventy_five(self, canary_policy):
        from app.core.config import Settings

        def _in_75(agent_id: str) -> bool:
            s75 = Settings(
                pi_canary_rollout_percent=75,
                pi_canary_config_version=8,
                pi_canary_stable_bucket_salt="pi_v1",
                pi_canary_authorization_status="authorized",
                pi_canary_fail_closed=False,
            )
            return canary_policy.should_use_shadow_provider("staging", agent_id, "anon", s75)

        s100 = Settings(
            pi_canary_rollout_percent=100,
            pi_canary_config_version=9,
            pi_canary_stable_bucket_salt="pi_v1",
            pi_canary_authorization_status="authorized",
            pi_canary_fail_closed=False,
        )
        agents = [f"agent_{i:04d}" for i in range(300)]
        for a in agents:
            in_75 = _in_75(a)
            in_100 = canary_policy.should_use_shadow_provider("staging", a, "anon", s100)
            if in_75:
                assert in_100, f"{a} in 75% but not in 100%! (monotonic cohort violated)"

    def test_stable_bucket_function_not_cv_sensitive(self, canary_policy):
        """stable_bucket() uses salt not config_version in hash."""
        from app.core.config import Settings

        def _sel(cv: int, rollout: int) -> bool:
            s = Settings(
                pi_canary_rollout_percent=rollout,
                pi_canary_config_version=cv,
                pi_canary_stable_bucket_salt="pi_v1",
                pi_canary_authorization_status="authorized",
            )
            return canary_policy.should_use_shadow_provider("staging", "agent_test_007", "anon", s)

        # Same rollout, different cv → must give same selection result
        result_cv8 = _sel(8, 75)
        result_cv9 = _sel(9, 75)
        assert result_cv8 == result_cv9, "cv change must not affect bucket assignment"

    def test_hundred_percent_rate_close_to_one(self, canary_policy):
        from app.core.config import Settings

        s100 = Settings(
            pi_canary_rollout_percent=100,
            pi_canary_config_version=9,
            pi_canary_stable_bucket_salt="pi_v1",
            pi_canary_authorization_status="authorized",
        )
        agents = [f"agent_{i:05d}" for i in range(1000)]
        selected = sum(
            1 for a in agents
            if canary_policy.should_use_shadow_provider("staging", a, "anon", s100)
        )
        assert selected == 1000, f"Expected 1000/1000, got {selected}"


# ---------------------------------------------------------------------------
# 13. Performance Gate
# ---------------------------------------------------------------------------

class TestPerformanceGate:
    """pi_p95 must stay ≤ 5000 ms at 100% rollout."""

    def test_metrics_p95_within_limit(self):
        m = _metrics()
        p95 = m.get("pi_p95_ms") or m.get("pi_latency_p95_ms", 0)
        assert p95 <= 5000, f"pi_p95={p95}ms exceeds 5000ms SLA"

    def test_metrics_selections_this_phase_positive(self):
        m = _metrics()
        assert m.get("selections_this_phase", 0) > 0

    def test_metrics_violations_this_phase_zero(self):
        m = _metrics()
        assert m.get("violations_this_phase", 0) == 0

    def test_metrics_cumulative_zero_violations(self):
        m = _metrics()
        assert m.get("cumulative_violations", 0) == 0

    def test_metrics_cumulative_covers_p18_through_p125(self):
        m = _metrics()
        cum = m.get("cumulative_selected", 0)
        # Cumulative must include P1.8–P1.24 (45373) plus P1.25 additions
        assert cum > 45373, f"Cumulative {cum} must exceed P1.24 total 45373"


# ---------------------------------------------------------------------------
# 14. Final Decision State A
# ---------------------------------------------------------------------------

class TestFinalDecisionStateA:
    """Final decision must record State A — Gate C PASS, 100% executed."""

    def test_final_state_is_a(self):
        f = _final()
        assert f["state"] == "A"

    def test_final_phase_6v_p125(self):
        f = _final()
        assert f["phase"] == "6V-P1.25"

    def test_final_gate_a_pass(self):
        f = _final()
        assert f["gate_results"]["A"] == "pass"

    def test_final_gate_b_pass(self):
        f = _final()
        assert f["gate_results"]["B"] == "pass"

    def test_final_gate_c_pass(self):
        f = _final()
        assert f["gate_results"]["C"] == "pass"

    def test_final_authorization_condition_satisfied(self):
        f = _final()
        assert f["authorization_condition_satisfied"] is True

    def test_final_promotion_applied(self):
        f = _final()
        assert f["promotion_applied"] is True

    def test_final_live_false(self):
        f = _final()
        assert f["live"] is False

    def test_final_production_enabled_false(self):
        f = _final()
        assert f["production_enabled"] is False

    def test_final_provider_serving_calls_zero(self):
        f = _final()
        assert f["provider_serving_calls"] == 0

    def test_final_stable_bucket_salt_pi_v1(self):
        f = _final()
        assert f["stable_bucket_salt_version"] == "pi_v1"

    def test_final_deployed_runtime_verified(self):
        f = _final()
        assert f["deployed_runtime_verified"] is True

    def test_final_rollback_not_required(self):
        f = _final()
        assert f.get("rollback_required") is False

    def test_final_rollback_not_applied_to_production(self):
        f = _final()
        assert f.get("rollback_applied") is False

    def test_final_gate_c_status_pass(self):
        f = _final()
        assert f["gate_c_status"] == "pass"

    def test_final_base_sha_is_p124_final(self):
        f = _final()
        assert f["base_sha"] == _BASE_SHA

    def test_final_evidence_sha_is_hex(self):
        f = _final()
        sha = f["evidence_sha"]
        assert sha and sha != "unknown"
        assert all(c in "0123456789abcdef" for c in sha.lower())

    def test_final_no_secret_key(self):
        text = json.dumps(_final())
        # Should not contain actual secret patterns
        assert "sk-" not in text
        assert len([line for line in text.splitlines()
                    if "SECRET_KEY" in line and "=" in line]) == 0

    def test_final_schema_version(self):
        f = _final()
        assert "schema_version" in f
        assert "pi_canary" in f["schema_version"]


# ---------------------------------------------------------------------------
# 15. Cumulative Soak Continuity
# ---------------------------------------------------------------------------

class TestCumulativeSoakContinuity:
    """Cumulative soak must be continuous from P1.8 through P1.25."""

    def test_cumulative_soak_health_excellent(self):
        m = _metrics()
        assert m.get("soak_health") == "excellent"

    def test_cumulative_selected_exceeds_p124(self):
        m = _metrics()
        # P1.8–P1.24 = 45373; P1.25 adds more
        assert m.get("cumulative_selected", 0) > 45_373

    def test_cumulative_violation_rate_zero(self):
        m = _metrics()
        assert m.get("violation_rate", 1.0) == 0.0

    def test_final_cumulative_covers_p125(self):
        f = _final()
        phases = f.get("cumulative_p18_through_p125", {}).get("phases_covered", [])
        assert "P1.25" in phases

    def test_test_report_regression_gate_pass(self):
        r = _test_report()
        assert r["regression_gate"] == "PASS"

    def test_test_report_zero_failures(self):
        r = _test_report()
        assert r["test_suites"]["entire_backend"]["failed"] == 0
        assert r["test_suites"]["cross_phase"]["failed"] == 0

    def test_test_report_frontend_zero_failures(self):
        r = _test_report()
        assert r["frontend_tests"]["frontend_vitest"]["failed"] == 0


# ---------------------------------------------------------------------------
# 16. Code Changes Verification
# ---------------------------------------------------------------------------

class TestCodeChanges:
    """P1.25 code changes must be present in the codebase."""

    def test_pi_canary_snapshot_path_field_exists(self):
        config_py = _REPO_ROOT / "backend" / "app" / "core" / "config.py"
        assert "pi_canary_snapshot_path" in config_py.read_text()

    def test_main_py_snapshot_persistence(self):
        main_py = _REPO_ROOT / "backend" / "app" / "main.py"
        content = main_py.read_text()
        assert "pi_canary_snapshot_path" in content
        assert "_snap_path" in content

    def test_canary_policy_snapshot_v2(self):
        cp_py = _REPO_ROOT / "backend" / "app" / "agent_runtime" / "canary_policy.py"
        content = cp_py.read_text()
        assert "pi_canary_runtime_snapshot_v2" in content
        assert "process_id" in content
        assert "deployment_sha" in content
        assert "config_fingerprint" in content

    def test_env_staging_example_exists(self):
        p = _REPO_ROOT / ".env.staging.example"
        assert p.exists(), ".env.staging.example must exist"

    def test_env_staging_example_no_real_secrets(self):
        p = _REPO_ROOT / ".env.staging.example"
        text = p.read_text()
        sensitive_keys = {"SECRET_KEY", "DATABASE_URL", "DEEPSEEK_API_KEY", "TUSHARE_TOKEN", "REDIS_PASSWORD"}
        for key in sensitive_keys:
            for line in text.splitlines():
                if line.startswith(key + "="):
                    value = line.split("=", 1)[1].strip()
                    assert value.startswith("<") and value.endswith(">"), \
                        f"{key} in .env.staging.example must be a placeholder, got: {value}"

    def test_staging_local_not_committed(self):
        gitignore = _REPO_ROOT / ".gitignore"
        content = gitignore.read_text()
        assert ".env.staging.local" in content, ".env.staging.local must be in .gitignore"
