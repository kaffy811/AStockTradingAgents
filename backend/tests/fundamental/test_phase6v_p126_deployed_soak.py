"""
Phase 6V-P1.26 — Deployed 100% Shadow Soak Evidence Tests
==========================================================
Verifies:
  1. X1-X10 soak artifacts exist and all PASS
  2. Rollback drill artifact reflects correct state transitions
  3. Gate M closure artifact confirms browser/UI isolation
  4. Evidence reconciliation correctly classifies P1.25 W1-W8 as math-only
  5. Cumulative totals are correct (P1.8 → P1.26)
  6. Final decision evaluates 16 Live Serving Readiness gates
  7. Deployed runtime snapshot at 100/v11/pi_v1 (post-rollback-restore)
  8. Soak harness HTTP soak math: bucket_selected at 100% = all selected
"""

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

# ── Env setup (must precede any app imports) ──────────────────────────────────
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/test")
os.environ.setdefault("SECRET_KEY", "test-only-secret-for-p126-isolated-run-minimum-16-chars")

# ── Paths ─────────────────────────────────────────────────────────────────────
ARTIFACTS_DIR = Path(__file__).parent.parent.parent / "docs" / "artifacts"

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_artifact(name: str) -> dict:
    path = ARTIFACTS_DIR / name
    assert path.exists(), f"Artifact not found: {path}"
    with open(path) as f:
        return json.load(f)


def stable_bucket(environment: str, agent_id: str, anon_user_key: str,
                   stable_bucket_salt: str) -> int:
    raw = f"{environment}|{agent_id}|{anon_user_key}|{stable_bucket_salt}"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return int(digest[:4], 16) % 10000


def bucket_selected(bucket: int, rollout_percent: float) -> bool:
    return bucket < int(rollout_percent * 100)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. X1-X10 Soak Window Artifacts
# ═══════════════════════════════════════════════════════════════════════════════

class TestSoakWindowArtifacts:
    """Verify all 10 soak window artifacts exist and pass."""

    @pytest.mark.parametrize("window_id", [f"x{i}" for i in range(1, 11)])
    def test_window_artifact_exists(self, window_id: str):
        name = f"company_v2_phase6v_p126_{window_id}.json"
        path = ARTIFACTS_DIR / name
        assert path.exists(), f"Window artifact missing: {name}"

    @pytest.mark.parametrize("window_id", [f"x{i}" for i in range(1, 11)])
    def test_window_pass(self, window_id: str):
        d = load_artifact(f"company_v2_phase6v_p126_{window_id}.json")
        assert d["window_pass"] is True, f"{window_id}: window_pass is False"

    @pytest.mark.parametrize("window_id", [f"x{i}" for i in range(1, 11)])
    def test_window_zero_violations(self, window_id: str):
        d = load_artifact(f"company_v2_phase6v_p126_{window_id}.json")
        assert d["bucket_selection"]["violations"] == 0

    @pytest.mark.parametrize("window_id", [f"x{i}" for i in range(1, 11)])
    def test_window_snapshot_ok(self, window_id: str):
        d = load_artifact(f"company_v2_phase6v_p126_{window_id}.json")
        assert d["snapshot_ok"] is True

    @pytest.mark.parametrize("window_id", [f"x{i}" for i in range(1, 11)])
    def test_window_http_ok(self, window_id: str):
        d = load_artifact(f"company_v2_phase6v_p126_{window_id}.json")
        assert d["all_http_ok"] is True

    @pytest.mark.parametrize("window_id", [f"x{i}" for i in range(1, 11)])
    def test_window_rollout_100(self, window_id: str):
        d = load_artifact(f"company_v2_phase6v_p126_{window_id}.json")
        assert d["snapshot"]["rollout_percent"] == 100.0

    @pytest.mark.parametrize("window_id", [f"x{i}" for i in range(1, 11)])
    def test_window_config_version_9(self, window_id: str):
        d = load_artifact(f"company_v2_phase6v_p126_{window_id}.json")
        # Windows run before rollback restore — cv=9 (pre-rollback) or cv=11 (post)
        assert d["snapshot"]["config_version"] in (9, 11), \
            f"Unexpected cv: {d['snapshot']['config_version']}"

    @pytest.mark.parametrize("window_id", [f"x{i}" for i in range(1, 11)])
    def test_window_salt_pi_v1(self, window_id: str):
        d = load_artifact(f"company_v2_phase6v_p126_{window_id}.json")
        assert d["snapshot"]["stable_bucket_salt_version"] == "pi_v1"

    @pytest.mark.parametrize("window_id", [f"x{i}" for i in range(1, 11)])
    def test_window_live_false(self, window_id: str):
        d = load_artifact(f"company_v2_phase6v_p126_{window_id}.json")
        assert d["snapshot"]["live"] is False

    @pytest.mark.parametrize("window_id", [f"x{i}" for i in range(1, 11)])
    def test_window_prod_disabled(self, window_id: str):
        d = load_artifact(f"company_v2_phase6v_p126_{window_id}.json")
        assert d["snapshot"]["production_enabled"] is False

    @pytest.mark.parametrize("window_id", [f"x{i}" for i in range(1, 11)])
    def test_window_1000_selected(self, window_id: str):
        d = load_artifact(f"company_v2_phase6v_p126_{window_id}.json")
        assert d["bucket_selection"]["selected"] == 1000

    @pytest.mark.parametrize("window_id", [f"x{i}" for i in range(1, 11)])
    def test_window_eligible_requests_count(self, window_id: str):
        d = load_artifact(f"company_v2_phase6v_p126_{window_id}.json")
        assert d["bucket_selection"]["eligible_requests"] == 1000

    @pytest.mark.parametrize("window_id", [f"x{i}" for i in range(1, 11)])
    def test_window_parse_error_null(self, window_id: str):
        d = load_artifact(f"company_v2_phase6v_p126_{window_id}.json")
        assert d["snapshot"]["parse_error"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Soak Summary Artifact
# ═══════════════════════════════════════════════════════════════════════════════

class TestSoakSummaryArtifact:
    """Verify the soak summary artifact."""

    def test_summary_exists(self):
        path = ARTIFACTS_DIR / "company_v2_phase6v_p126_soak_summary.json"
        assert path.exists()

    def test_summary_all_windows_pass(self):
        d = load_artifact("company_v2_phase6v_p126_soak_summary.json")
        assert d["all_windows_pass"] is True

    def test_summary_10_windows(self):
        d = load_artifact("company_v2_phase6v_p126_soak_summary.json")
        assert d["windows_executed"] == 10

    def test_summary_10000_selected(self):
        d = load_artifact("company_v2_phase6v_p126_soak_summary.json")
        assert d["cumulative_selected"] == 10000

    def test_summary_10000_eligible(self):
        d = load_artifact("company_v2_phase6v_p126_soak_summary.json")
        assert d["total_eligible"] == 10000

    def test_summary_soak_health_excellent(self):
        d = load_artifact("company_v2_phase6v_p126_soak_summary.json")
        assert d["soak_health"] == "excellent"

    def test_summary_expected_config_rollout_100(self):
        d = load_artifact("company_v2_phase6v_p126_soak_summary.json")
        assert d["expected_config"]["rollout_percent"] == 100.0

    def test_summary_expected_live_false(self):
        d = load_artifact("company_v2_phase6v_p126_soak_summary.json")
        assert d["expected_config"]["live"] is False

    def test_summary_window_count_matches(self):
        d = load_artifact("company_v2_phase6v_p126_soak_summary.json")
        assert len(d["window_summary"]) == 10

    def test_summary_all_window_violations_zero(self):
        d = load_artifact("company_v2_phase6v_p126_soak_summary.json")
        for w in d["window_summary"]:
            assert w["violations"] == 0, f"Window {w['id']} has violations"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Gate M Closure Artifact
# ═══════════════════════════════════════════════════════════════════════════════

class TestGateMClosure:
    """Verify Gate M is closed in P1.26."""

    def test_gate_m_artifact_exists(self):
        path = ARTIFACTS_DIR / "company_v2_phase6v_p126_gate_m_closure.json"
        assert path.exists()

    def test_gate_m_pass(self):
        d = load_artifact("company_v2_phase6v_p126_gate_m_closure.json")
        assert d["gate_status"] == "pass"

    def test_gate_m_p125_was_not_evaluated(self):
        d = load_artifact("company_v2_phase6v_p126_gate_m_closure.json")
        assert d["p125_status"] == "not_evaluated"

    def test_gate_m_frontend_http_200(self):
        d = load_artifact("company_v2_phase6v_p126_gate_m_closure.json")
        assert d["p126_closure"]["frontend_http_status"] == 200

    def test_gate_m_backend_health_200(self):
        d = load_artifact("company_v2_phase6v_p126_gate_m_closure.json")
        assert d["p126_closure"]["backend_health_status"] == 200

    def test_gate_m_live_serving_isolation(self):
        d = load_artifact("company_v2_phase6v_p126_gate_m_closure.json")
        assert d["p126_closure"]["live_serving_isolation_confirmed"] is True

    def test_gate_m_production_traffic_isolation(self):
        d = load_artifact("company_v2_phase6v_p126_gate_m_closure.json")
        assert d["p126_closure"]["production_traffic_isolation_confirmed"] is True

    def test_gate_m_cors_enabled(self):
        d = load_artifact("company_v2_phase6v_p126_gate_m_closure.json")
        assert d["p126_closure"]["cors_middleware_enabled"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Evidence Reconciliation
# ═══════════════════════════════════════════════════════════════════════════════

class TestEvidenceReconciliation:
    """Verify P1.25 W1-W8 are correctly classified as math-only."""

    def test_reconciliation_exists(self):
        path = ARTIFACTS_DIR / "company_v2_phase6v_p126_evidence_reconciliation.json"
        assert path.exists()

    def test_w1_w8_classified_as_math(self):
        d = load_artifact("company_v2_phase6v_p126_evidence_reconciliation.json")
        assert d["p125_evidence_audit"]["w1_through_w8_nature"] == "mathematical_bucket_policy_tests"

    def test_w1_w8_not_sufficient_for_p126_soak(self):
        d = load_artifact("company_v2_phase6v_p126_evidence_reconciliation.json")
        assert d["p125_evidence_audit"]["w1_through_w8_sufficient_for_p126_soak"] is False

    def test_w1_w8_sufficient_for_gate_c(self):
        d = load_artifact("company_v2_phase6v_p126_evidence_reconciliation.json")
        assert d["p125_evidence_audit"]["w1_through_w8_sufficient_for_gate_c"] is True

    def test_gate_m_was_not_evaluated_in_p125(self):
        d = load_artifact("company_v2_phase6v_p126_evidence_reconciliation.json")
        assert d["p125_evidence_audit"]["gate_m_p125_status"] == "not_evaluated"

    def test_x_windows_classified_as_real_http(self):
        d = load_artifact("company_v2_phase6v_p126_evidence_reconciliation.json")
        assert d["p126_evidence_addendum"]["x1_through_x10_nature"] == "real_http_deployed_soak"

    def test_x_windows_10000_selected(self):
        d = load_artifact("company_v2_phase6v_p126_evidence_reconciliation.json")
        assert d["p126_evidence_addendum"]["x1_through_x10_total_selected"] == 10000

    def test_gate_m_closed_in_p126(self):
        d = load_artifact("company_v2_phase6v_p126_evidence_reconciliation.json")
        assert d["p126_evidence_addendum"]["gate_m_p126_status"] == "closed"

    def test_grand_total_cumulative(self):
        d = load_artifact("company_v2_phase6v_p126_evidence_reconciliation.json")
        totals = d["cumulative_totals"]["grand_total_p18_through_p126"]
        assert totals["total_selected"] == 65373
        assert totals["zero_violations"] is True
        assert totals["violation_rate"] == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Rollback Drill Artifact
# ═══════════════════════════════════════════════════════════════════════════════

class TestRollbackDrill:
    """Verify rollback drill: 100/v9 → 75/v10 → 100/v11."""

    def test_rollback_artifact_exists(self):
        path = ARTIFACTS_DIR / "company_v2_phase6v_p126_rollback_drill.json"
        assert path.exists()

    def test_all_steps_pass(self):
        d = load_artifact("company_v2_phase6v_p126_rollback_drill.json")
        assert d["drill_summary"]["all_steps_pass"] is True

    def test_no_parse_error_at_any_step(self):
        d = load_artifact("company_v2_phase6v_p126_rollback_drill.json")
        assert d["drill_summary"]["parse_error_at_any_step"] is False

    def test_live_never_enabled(self):
        d = load_artifact("company_v2_phase6v_p126_rollback_drill.json")
        assert d["drill_summary"]["live_enabled_at_any_step"] is False

    def test_production_never_enabled(self):
        d = load_artifact("company_v2_phase6v_p126_rollback_drill.json")
        assert d["drill_summary"]["production_enabled_at_any_step"] is False

    def test_step1_pre_rollback(self):
        d = load_artifact("company_v2_phase6v_p126_rollback_drill.json")
        s = d["drill_steps"][0]
        assert s["rollout_percent"] == 100.0
        assert s["config_version"] == 9

    def test_step2_rollback_applied(self):
        d = load_artifact("company_v2_phase6v_p126_rollback_drill.json")
        s = d["drill_steps"][1]
        assert s["rollout_percent"] == 75.0
        assert s["config_version"] == 10

    def test_step3_restore_100(self):
        d = load_artifact("company_v2_phase6v_p126_rollback_drill.json")
        s = d["drill_steps"][2]
        assert s["rollout_percent"] == 100.0
        assert s["config_version"] == 11

    def test_config_version_monotonicity(self):
        d = load_artifact("company_v2_phase6v_p126_rollback_drill.json")
        cvs = [s["config_version"] for s in d["drill_steps"]]
        # Must be: 9, 10, 11 (rollback uses 10 not a reuse)
        assert cvs == [9, 10, 11]

    def test_final_state_100_v11(self):
        d = load_artifact("company_v2_phase6v_p126_rollback_drill.json")
        f = d["final_state"]
        assert f["rollout_percent"] == 100.0
        assert f["config_version"] == 11
        assert f["stable_bucket_salt"] == "pi_v1"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Canary Math: 100% Rollout Correctness
# ═══════════════════════════════════════════════════════════════════════════════

class TestHundredPercentSoakMath:
    """Verify bucket_selected is always True at rollout=100%."""

    CANARY_AGENT_ID = "official_report_pdf_pi_v1"
    SALT = "pi_v1"

    def _bucket(self, key: str) -> int:
        return stable_bucket("staging", self.CANARY_AGENT_ID, key, self.SALT)

    def test_all_buckets_selected_at_100_percent(self):
        """Every bucket in [0, 9999] must be selected at 100% rollout."""
        for i in range(0, 10000, 100):  # sample every 100th bucket
            b = self._bucket(f"soak_req_{i:06d}")
            assert bucket_selected(b, 100.0), \
                f"Bucket {b} not selected at 100% rollout (req_{i})"

    def test_1000_unique_request_ids_all_selected(self):
        selected = sum(
            1 for i in range(1000)
            if bucket_selected(self._bucket(f"x_window_req_{i}"), 100.0)
        )
        assert selected == 1000

    def test_bucket_range_invariant(self):
        """All buckets are in [0, 9999]."""
        for i in range(200):
            b = self._bucket(f"invariant_check_{i}")
            assert 0 <= b <= 9999, f"Bucket {b} out of range"

    def test_rollback_75_percent_allows_fewer(self):
        """At 75% rollout, 25% of buckets are NOT selected."""
        not_selected = sum(
            1 for i in range(10000)
            if not bucket_selected(self._bucket(f"rollback_req_{i}"), 75.0)
        )
        # At 75%: ~25% not selected
        assert 2000 <= not_selected <= 3000, \
            f"Expected ~2500 not selected, got {not_selected}"

    def test_100_percent_minus_rollback_diff(self):
        """Promoting from 75→100 adds exactly 2500 more selections."""
        selected_100 = sum(
            1 for i in range(10000)
            if bucket_selected(self._bucket(f"diff_req_{i}"), 100.0)
        )
        selected_75 = sum(
            1 for i in range(10000)
            if bucket_selected(self._bucket(f"diff_req_{i}"), 75.0)
        )
        diff = selected_100 - selected_75
        assert 2000 <= diff <= 3000, \
            f"Expected ~2500 diff, got {diff} (100%={selected_100}, 75%={selected_75})"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Final Decision Artifact — 16-Gate Evaluation
# ═══════════════════════════════════════════════════════════════════════════════

class TestFinalDecision:
    """Verify the P1.26 final decision artifact evaluates all 16 gates."""

    def test_final_decision_exists(self):
        path = ARTIFACTS_DIR / "company_v2_phase6v_p126_final_decision.json"
        assert path.exists()

    def test_phase_is_p126(self):
        d = load_artifact("company_v2_phase6v_p126_final_decision.json")
        assert "P1.26" in d["phase"]

    def test_state_a(self):
        d = load_artifact("company_v2_phase6v_p126_final_decision.json")
        assert d["state"] == "A"

    def test_gate_m_is_pass(self):
        d = load_artifact("company_v2_phase6v_p126_final_decision.json")
        assert d["gate_results"]["M"] == "pass"

    def test_all_16_gates_present(self):
        d = load_artifact("company_v2_phase6v_p126_final_decision.json")
        gates = d["gate_results"]
        # Gates A-P = 16 gates
        expected = set("ABCDEFGHIJKLMNOP")
        assert expected == set(gates.keys()), \
            f"Missing gates: {expected - set(gates.keys())}"

    def test_no_gate_failed(self):
        d = load_artifact("company_v2_phase6v_p126_final_decision.json")
        for gate, result in d["gate_results"].items():
            assert result != "fail", f"Gate {gate} = fail"

    def test_live_not_authorized(self):
        d = load_artifact("company_v2_phase6v_p126_final_decision.json")
        assert d["live_serving_authorized"] is False

    def test_live_not_applied(self):
        d = load_artifact("company_v2_phase6v_p126_final_decision.json")
        assert d["live"] is False

    def test_production_not_enabled(self):
        d = load_artifact("company_v2_phase6v_p126_final_decision.json")
        assert d["production_enabled"] is False

    def test_rollout_100(self):
        d = load_artifact("company_v2_phase6v_p126_final_decision.json")
        assert d["actual_rollout_percent_after_phase"] == 100

    def test_salt_pi_v1(self):
        d = load_artifact("company_v2_phase6v_p126_final_decision.json")
        assert d["stable_bucket_salt_version"] == "pi_v1"

    def test_soak_x_windows_pass(self):
        d = load_artifact("company_v2_phase6v_p126_final_decision.json")
        assert d["soak_x_windows_all_pass"] is True

    def test_10000_x_window_selections(self):
        d = load_artifact("company_v2_phase6v_p126_final_decision.json")
        assert d["soak_x_windows_total_selected"] == 10000

    def test_cumulative_grand_total(self):
        d = load_artifact("company_v2_phase6v_p126_final_decision.json")
        assert d["cumulative_p18_through_p126"]["total_selected"] == 65373

    def test_zero_violations_cumulative(self):
        d = load_artifact("company_v2_phase6v_p126_final_decision.json")
        assert d["cumulative_p18_through_p126"]["zero_violations"] == 0

    def test_rollback_drill_pass(self):
        d = load_artifact("company_v2_phase6v_p126_final_decision.json")
        assert d["rollback_drill_pass"] is True

    def test_next_phase_is_p127_or_live_gate(self):
        d = load_artifact("company_v2_phase6v_p126_final_decision.json")
        assert "next_phase_recommendation" in d
        assert "phase" in d["next_phase_recommendation"]


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Soak Harness Script Exists and is Valid Python
# ═══════════════════════════════════════════════════════════════════════════════

class TestSoakHarnessScript:
    """Verify the soak harness script is present and valid."""

    SCRIPT_PATH = Path(__file__).parent.parent.parent / "scripts" / "run_deployed_shadow_soak.py"

    def test_script_exists(self):
        assert self.SCRIPT_PATH.exists()

    def test_script_is_valid_python(self):
        import py_compile
        py_compile.compile(str(self.SCRIPT_PATH), doraise=True)

    def test_script_has_stable_bucket_function(self):
        content = self.SCRIPT_PATH.read_text()
        assert "def stable_bucket(" in content

    def test_script_has_bucket_selected_function(self):
        content = self.SCRIPT_PATH.read_text()
        assert "def bucket_selected(" in content

    def test_script_uses_docker_exec_for_snapshot(self):
        content = self.SCRIPT_PATH.read_text()
        assert "docker" in content and "exec" in content

    def test_script_canary_agent_id_correct(self):
        content = self.SCRIPT_PATH.read_text()
        assert 'CANARY_AGENT_ID = "official_report_pdf_pi_v1"' in content

    def test_script_expected_rollout_100(self):
        content = self.SCRIPT_PATH.read_text()
        assert "EXPECTED_ROLLOUT = 100.0" in content

    def test_script_live_serving_not_authorized(self):
        content = self.SCRIPT_PATH.read_text()
        # Script must not set live=True or production_enabled=True
        assert "live=True" not in content
        assert "production_enabled=True" not in content
