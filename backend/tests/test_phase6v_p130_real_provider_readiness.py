"""
Phase 6V-P1.30 — Restricted Real Staging Provider Activation
Test suite: State B (NOT_EXECUTED)

Coverage:
- P1.29 evidence reconciliation (Gate B)
- Runtime probe consistency (Gate C)
- Provider adapter audit (codebase verification)
- Credential isolation audit (Gate D — FAIL)
- Pricing verification audit (Gate E — FAIL)
- Budget guard assessment (Gates F, G, I — FAIL)
- Fail-closed dry run (replay mode confirmed)
- All real-provider artifacts correctly marked NOT_EXECUTED
- Safety evidence (replay-live continued)
- Browser E2E (replay cases)
- Canonical test suite (Gate S)
- Replay restoration (Gate T)
- Production boundary (Gate U)
- Final decision State B
- Implementation gap documentation for P1.31
"""

import json
import os
import pytest
from pathlib import Path

ARTIFACTS = Path(__file__).parent.parent / "docs" / "artifacts"


def load(name: str) -> dict:
    p = ARTIFACTS / f"company_v2_phase6v_p130_{name}.json"
    assert p.exists(), f"Artifact not found: {p}"
    with open(p) as f:
        return json.load(f)


def load_md(name: str) -> str:
    p = ARTIFACTS / f"company_v2_phase6v_p130_{name}.md"
    assert p.exists(), f"Markdown artifact not found: {p}"
    return p.read_text()


# ---------------------------------------------------------------------------
# Preflight Audit
# ---------------------------------------------------------------------------

class TestPreflightAudit:
    def setup_method(self):
        self.data = load("preflight_audit")

    def test_base_sha(self):
        assert self.data["base"]["base_sha"] == "6ee8fc4f693db5f8956901295515f8a2253406de"

    def test_origin_head_matches_base(self):
        assert self.data["base"]["sha_match"] is True

    def test_cv_12(self):
        assert self.data["runtime_snapshot"]["config_version"] == 12

    def test_shadow_100(self):
        assert self.data["runtime_snapshot"]["shadow_rollout_percent"] == 100

    def test_live_1(self):
        assert self.data["runtime_snapshot"]["live_rollout_percent"] == 1

    def test_production_false(self):
        assert self.data["runtime_snapshot"]["production_enabled"] is False

    def test_provider_mode_replay(self):
        assert self.data["runtime_snapshot"]["provider_mode"] == "staging_replay"

    def test_real_provider_false(self):
        assert self.data["runtime_snapshot"]["real_provider_enabled"] is False

    def test_execution_decision_state_b(self):
        assert self.data["execution_decision"] == "STATE_B"

    def test_real_provider_not_executed(self):
        assert self.data["real_provider_execution"] == "NOT_EXECUTED"

    def test_blocking_gates_include_d_e_f_g_i(self):
        blocking = self.data["blocking_gates"]
        for gate in ["D", "E", "F", "G", "I"]:
            assert gate in blocking

    def test_state_retained_cv(self):
        assert self.data["state_retained"]["config_version"] == 12

    def test_state_retained_replay(self):
        assert self.data["state_retained"]["provider_mode"] == "staging_replay"


# ---------------------------------------------------------------------------
# P1.29 Evidence Reconciliation (Gate B)
# ---------------------------------------------------------------------------

class TestP129EvidenceReconciliation:
    def setup_method(self):
        self.data = load("p129_evidence_reconciliation")

    def test_p129_final_sha(self):
        assert self.data["p129_final_sha"] == "6ee8fc4f693db5f8956901295515f8a2253406de"

    def test_evaluated_replay_live_gates_passed(self):
        assert self.data["evaluated_replay_live_gates_passed"] is True

    def test_real_provider_gate_before_p130(self):
        assert self.data["real_provider_gate_status_before_p130"] == "NOT_EVALUATED"

    def test_replay_live_readiness(self):
        assert self.data["replay_live_readiness"] == "PASS"

    def test_real_provider_readiness(self):
        assert self.data["real_provider_readiness"] == "NOT_EVALUATED"

    def test_reported_cv(self):
        assert self.data["reported_config_version"] == 12

    def test_deployed_cv(self):
        assert self.data["deployed_config_version"] == 12

    def test_no_version_drift(self):
        assert self.data["version_drift_detected"] is False

    def test_proposed_v15_from_p129(self):
        assert self.data["proposed_p130_version_from_p129_report"] == 15

    def test_actual_current_cv(self):
        assert self.data["actual_current_cv"] == 12

    def test_next_monotonic_version(self):
        assert self.data["next_monotonic_version"] == 13

    def test_version_gap_explained(self):
        assert self.data["version_gap_explained"] is True

    def test_version_gap_explanation_present(self):
        assert len(self.data["version_gap_explanation"]) > 50

    def test_blocking_reasons_not_empty(self):
        assert len(self.data["blocking_reasons"]) >= 5

    def test_implementation_gaps_not_empty(self):
        assert len(self.data["implementation_gaps_identified"]) >= 5

    def test_p131_prerequisites_not_empty(self):
        assert len(self.data["p1_31_prerequisites"]) >= 5

    def test_gate_b_pass(self):
        assert self.data["gate_b_status"] == "PASS"


# ---------------------------------------------------------------------------
# Runtime Probe (Before)
# ---------------------------------------------------------------------------

class TestRuntimeProbeBefore:
    def setup_method(self):
        self.data = load("runtime_probe_before")

    def test_cv_12(self):
        assert self.data["config_fingerprint"]["config_version"] == 12

    def test_shadow_100(self):
        assert self.data["config_fingerprint"]["shadow_rollout_percent"] == 100

    def test_live_1(self):
        assert self.data["config_fingerprint"]["live_rollout_percent"] == 1

    def test_live_salt(self):
        assert self.data["config_fingerprint"]["live_salt"] == "pi_live_v1"

    def test_production_false(self):
        assert self.data["config_fingerprint"]["production_enabled"] is False

    def test_provider_replay(self):
        assert self.data["config_fingerprint"]["provider_mode"] == "staging_replay"

    def test_real_provider_false(self):
        assert self.data["config_fingerprint"]["real_provider_enabled"] is False

    def test_no_drift(self):
        assert self.data["version_check"]["drift"] is False

    def test_probe_pass(self):
        assert self.data["probe_result"] == "PASS"


# ---------------------------------------------------------------------------
# Provider Adapter Audit
# ---------------------------------------------------------------------------

class TestProviderAdapterAudit:
    def setup_method(self):
        self.data = load("provider_adapter_audit")

    def test_provider_deepseek(self):
        assert self.data["provider"] == "DeepSeek"

    def test_sdk_openai(self):
        assert "openai" in self.data["sdk"].lower()

    def test_adapter_file(self):
        assert "deepseek_client" in self.data["adapter_file"]

    def test_api_endpoint(self):
        assert "api.deepseek.com" in self.data["api_endpoint"]

    def test_default_model(self):
        assert self.data["models"]["default"] == "deepseek-v4-flash"

    def test_staging_key_exists_false(self):
        assert self.data["staging_key_exists"] is False

    def test_no_staging_auth_var(self):
        assert self.data["auth_env_staging_var"] is None

    def test_token_usage_not_captured(self):
        assert self.data["token_usage_captured"] is False

    def test_timeout_not_configured(self):
        assert self.data["timeout"]["configured"] is False

    def test_pipeline_goes_through_analysis_agent(self):
        assert self.data["pipeline_safety"]["real_calls_through_analysis_agent"] is True

    def test_pipeline_review_required(self):
        assert self.data["pipeline_safety"]["review_agent_required"] is True

    def test_provider_failure_falls_back(self):
        assert self.data["pipeline_safety"]["provider_failure_falls_back_to_legacy"] is True

    def test_no_second_provider_path(self):
        assert self.data["pipeline_safety"]["second_parallel_provider_path_exists"] is False

    def test_gaps_identified(self):
        assert len(self.data["gaps_for_real_provider_activation"]) >= 4

    def test_gate_a_adapter_integrity_pass(self):
        assert self.data["gate_a_adapter_integrity"] == "PASS"


# ---------------------------------------------------------------------------
# Credential Audit (Gate D — FAIL)
# ---------------------------------------------------------------------------

class TestCredentialAudit:
    def setup_method(self):
        self.data = load("credential_audit")

    def test_credential_present(self):
        assert self.data["credential_present"] is True

    def test_staging_credential_absent(self):
        assert self.data["credential_isolation_check"]["staging_specific_key_found"] is False

    def test_staging_key_var_name(self):
        assert self.data["credential_isolation_check"]["staging_specific_key_required"] == "DEEPSEEK_API_KEY_STAGING"

    def test_isolation_not_confirmed(self):
        assert self.data["credential_isolation_check"]["isolation_confirmed"] is False

    def test_no_staging_key_in_any_file(self):
        assert self.data["search_results"]["deepseek_api_key_staging_found_in_any_file"] is False

    def test_no_key_in_git(self):
        assert self.data["prohibited_sources_check"]["git_tracked_key"] is False

    def test_no_key_in_artifact(self):
        assert self.data["prohibited_sources_check"]["key_in_artifact"] is False

    def test_gate_d_fail(self):
        assert self.data["gate_d_status"] == "FAIL"

    def test_real_provider_blocked(self):
        assert self.data["real_provider_blocked"] is True

    def test_fingerprint_not_recorded(self):
        assert self.data["credential_fingerprint_prefix"] is None


# ---------------------------------------------------------------------------
# Pricing Verification (Gate E — FAIL)
# ---------------------------------------------------------------------------

class TestPricingVerification:
    def setup_method(self):
        self.data = load("pricing_verification")

    def test_provider_deepseek(self):
        assert self.data["provider"] == "DeepSeek"

    def test_pricing_found_false(self):
        assert self.data["pricing_found"] is False

    def test_not_from_memory(self):
        assert self.data["pricing_from_memory_or_assumption"] is False

    def test_no_codebase_price_table(self):
        assert self.data["pricing_source_check"]["codebase_pricing_table"] is None

    def test_gate_e_fail(self):
        assert self.data["gate_e_status"] == "FAIL"

    def test_real_provider_blocked(self):
        assert self.data["real_provider_blocked"] is True

    def test_remediation_actions_present(self):
        assert len(self.data["p1_31_remediation"]["action_required"]) >= 3


# ---------------------------------------------------------------------------
# Budget Guard (Gates F, G, I — FAIL)
# ---------------------------------------------------------------------------

class TestBudgetGuard:
    def setup_method(self):
        self.data = load("budget_guard")

    def test_pi_real_provider_enabled_missing(self):
        assert self.data["runtime_implementation_check"]["PI_REAL_PROVIDER_ENABLED_in_settings"] is False

    def test_max_requests_missing(self):
        assert self.data["runtime_implementation_check"]["PI_REAL_PROVIDER_MAX_REQUESTS_in_settings"] is False

    def test_max_cost_missing(self):
        assert self.data["runtime_implementation_check"]["PI_REAL_PROVIDER_MAX_COST_CNY_in_settings"] is False

    def test_request_budget_guard_missing(self):
        assert self.data["runtime_implementation_check"]["RequestBudgetGuard_module_exists"] is False

    def test_cost_accumulator_missing(self):
        assert self.data["runtime_implementation_check"]["CostAccumulator_module_exists"] is False

    def test_circuit_breaker_missing(self):
        assert self.data["runtime_implementation_check"]["ProviderCircuitBreaker_module_exists"] is False

    def test_gate_f_fail(self):
        assert self.data["gate_f_request_budget"]["status"] == "FAIL"

    def test_gate_g_fail(self):
        assert self.data["gate_g_cost_budget"]["status"] == "FAIL"

    def test_gate_i_fail(self):
        assert self.data["gate_i_provider_fail_closed"]["status"] == "FAIL"

    def test_gate_f_not_implemented(self):
        assert self.data["gate_f_request_budget"]["implementation_status"] == "NOT_IMPLEMENTED"

    def test_gate_g_not_implemented(self):
        assert self.data["gate_g_cost_budget"]["implementation_status"] == "NOT_IMPLEMENTED"

    def test_gate_i_not_implemented(self):
        assert self.data["gate_i_provider_fail_closed"]["implementation_status"] == "NOT_IMPLEMENTED"

    def test_implementation_plan_has_10_steps(self):
        assert len(self.data["p1_31_implementation_plan"]["steps"]) >= 10

    def test_replay_mode_currently_safe(self):
        assert "safe" in self.data["current_provider_mode_safety"].lower()


# ---------------------------------------------------------------------------
# Fail-Closed Dry Run
# ---------------------------------------------------------------------------

class TestFailClosedDryRun:
    def setup_method(self):
        self.data = load("fail_closed_dry_run")

    def test_requests_sent(self):
        assert self.data["requests_sent"] == 20

    def test_real_provider_calls_zero(self):
        assert self.data["dry_run_results"]["real_provider_calls"] == 0

    def test_pi_real_provider_visible_zero(self):
        assert self.data["dry_run_results"]["pi_real_provider_visible"] == 0

    def test_legacy_fallback_served(self):
        assert self.data["dry_run_results"]["legacy_fallback_served"] == 20

    def test_http_success(self):
        assert self.data["dry_run_results"]["http_success"] == 20

    def test_terminal_violations_zero(self):
        assert self.data["dry_run_results"]["terminal_violations"] == 0

    def test_provider_flag_absent_scenario_pass(self):
        scenario = next(s for s in self.data["fail_closed_scenarios_tested"]
                       if s["scenario"] == "pi_real_provider_enabled_flag_absent")
        assert scenario["verified"] is True

    def test_provider_mode_replay_scenario_pass(self):
        scenario = next(s for s in self.data["fail_closed_scenarios_tested"]
                       if s["scenario"] == "provider_mode_replay")
        assert scenario["verified"] is True

    def test_missing_credential_zero_calls(self):
        scenario = next(s for s in self.data["fail_closed_scenarios_tested"]
                       if s["scenario"] == "missing_credential_effect")
        assert scenario["real_calls"] == 0

    def test_gate_i_replay_safety_confirmed(self):
        assert self.data["gate_i_replay_safety_confirmed"] is True


# ---------------------------------------------------------------------------
# NOT_EXECUTED Artifacts
# ---------------------------------------------------------------------------

NOT_EXECUTED_ARTIFACTS = [
    "provider_activation",
    "runtime_probe_active",
    "r1_results",
    "r2_results",
    "r3_results",
    "r4_results",
    "r5_results",
    "r6_results",
    "r7_results",
    "r8_results",
    "real_provider_metrics",
    "cost_report",
    "provider_kill_switch"
]


class TestNotExecutedArtifacts:
    @pytest.mark.parametrize("name", NOT_EXECUTED_ARTIFACTS)
    def test_artifact_exists(self, name):
        p = ARTIFACTS / f"company_v2_phase6v_p130_{name}.json"
        assert p.exists(), f"NOT_EXECUTED artifact missing: {name}"

    @pytest.mark.parametrize("name", NOT_EXECUTED_ARTIFACTS)
    def test_artifact_status_not_executed(self, name):
        data = load(name)
        assert data["status"] == "NOT_EXECUTED", f"{name}: expected status=NOT_EXECUTED"

    @pytest.mark.parametrize("name", NOT_EXECUTED_ARTIFACTS)
    def test_no_fabricated_data(self, name):
        data = load(name)
        assert data["fabricated_data"] is False

    @pytest.mark.parametrize("name", NOT_EXECUTED_ARTIFACTS)
    def test_real_provider_calls_zero(self, name):
        data = load(name)
        assert data["real_provider_calls"] == 0

    @pytest.mark.parametrize("name", NOT_EXECUTED_ARTIFACTS)
    def test_real_provider_cost_zero(self, name):
        data = load(name)
        assert data["real_provider_cost_cny"] == 0


# ---------------------------------------------------------------------------
# Safety Evidence (Replay)
# ---------------------------------------------------------------------------

class TestSafetyEvidence:
    def setup_method(self):
        self.data = load("safety_evidence")

    def test_real_provider_safety_not_evaluated(self):
        assert self.data["real_provider_safety"]["status"] == "NOT_EVALUATED"

    def test_replay_pi_violations_zero(self):
        assert self.data["replay_live_safety_continued"]["pi_violations"] == 0

    def test_replay_terminal_violations_zero(self):
        assert self.data["replay_live_safety_continued"]["terminal_violations"] == 0

    def test_replay_duplicate_messages_zero(self):
        assert self.data["replay_live_safety_continued"]["duplicate_assistant_messages"] == 0

    def test_replay_fallback_rate(self):
        assert self.data["replay_live_safety_continued"]["fallback_success_rate"] == 1.0

    def test_cumulative_pi_violations_zero(self):
        assert self.data["cumulative_live_safety"]["total_pi_violations"] == 0

    def test_cumulative_terminal_violations_zero(self):
        assert self.data["cumulative_live_safety"]["total_terminal_violations"] == 0

    def test_cumulative_fallback_rate(self):
        assert self.data["cumulative_live_safety"]["cumulative_fallback_success_rate"] == 1.0

    def test_safety_gate_j_replay(self):
        assert self.data["safety_gate_j_replay_live"] == "PASS"

    def test_safety_gate_l_real_provider_not_evaluated(self):
        assert self.data["safety_gate_l_real_provider"] == "NOT_EVALUATED"


# ---------------------------------------------------------------------------
# Browser E2E
# ---------------------------------------------------------------------------

class TestBrowserE2E:
    def setup_method(self):
        self.data = load("browser_e2e")

    def test_total_cases_50(self):
        assert self.data["total_cases"] == 50

    def test_all_passed(self):
        assert self.data["passed"] == 50

    def test_zero_failed(self):
        assert self.data["failed"] == 0

    def test_real_provider_cases_not_executed(self):
        assert self.data["real_provider_browser_cases"]["count"] == 0
        assert self.data["real_provider_browser_cases"]["status"] == "NOT_EXECUTED"

    def test_no_mock_pass_substituted(self):
        note = self.data["real_provider_browser_cases"].get("note", "")
        assert "mock" in note.lower() or "not_executed" in note.lower()

    def test_network_isolation_credential(self):
        assert self.data["network_isolation"]["credential_not_in_dom"] is True

    def test_network_isolation_provider_metadata(self):
        assert self.data["network_isolation"]["provider_metadata_not_in_response"] is True

    def test_credential_leakage_zero(self):
        assert self.data["credential_leakage"] == 0

    def test_provider_metadata_leakage_zero(self):
        assert self.data["provider_metadata_leakage"] == 0

    def test_duplicate_assistant_messages_zero(self):
        assert self.data["duplicate_assistant_messages"] == 0


# ---------------------------------------------------------------------------
# Replay Restoration (Gate T)
# ---------------------------------------------------------------------------

class TestReplayRestoration:
    def setup_method(self):
        self.data = load("replay_restoration")

    def test_status_not_required(self):
        assert self.data["status"] == "NOT_REQUIRED"

    def test_final_cv_12(self):
        assert self.data["final_state"]["config_version"] == 12

    def test_final_provider_replay(self):
        assert self.data["final_state"]["provider_mode"] == "staging_replay"

    def test_final_real_provider_false(self):
        assert self.data["final_state"]["real_provider_enabled"] is False

    def test_gate_t_pass(self):
        assert self.data["gate_t_status"] == "PASS"


# ---------------------------------------------------------------------------
# Runtime Probe Final
# ---------------------------------------------------------------------------

class TestRuntimeProbeFinal:
    def setup_method(self):
        self.data = load("runtime_probe_final")

    def test_cv_12_unchanged(self):
        assert self.data["config_fingerprint"]["config_version"] == 12

    def test_provider_replay_unchanged(self):
        assert self.data["config_fingerprint"]["provider_mode"] == "staging_replay"

    def test_real_provider_false_unchanged(self):
        assert self.data["config_fingerprint"]["real_provider_enabled"] is False

    def test_real_provider_calls_zero(self):
        assert self.data["config_fingerprint"]["real_provider_request_count"] == 0

    def test_real_provider_cost_zero(self):
        assert self.data["config_fingerprint"]["real_provider_cost_cny"] == 0

    def test_state_b(self):
        assert self.data["state"] == "STATE_B"

    def test_probe_pass(self):
        assert self.data["probe_result"] == "PASS"


# ---------------------------------------------------------------------------
# Final Decision
# ---------------------------------------------------------------------------

class TestFinalDecision:
    def setup_method(self):
        self.data = load("final_decision")

    def test_decision_state_b(self):
        assert self.data["decision"] == "STATE_B_REAL_PROVIDER_NOT_EXECUTED"

    def test_real_provider_not_executed(self):
        assert self.data["real_provider_executed"] is False

    def test_real_provider_validation_not_passed(self):
        assert self.data["real_provider_validation_passed"] is False

    def test_zero_real_requests(self):
        assert self.data["real_provider_requests"] == 0

    def test_zero_real_cost(self):
        assert self.data["real_provider_cost_cny"] == 0

    def test_cv_12(self):
        assert self.data["runtime_final"]["config_version"] == 12

    def test_shadow_100(self):
        assert self.data["runtime_final"]["shadow_rollout_percent"] == 100

    def test_live_1(self):
        assert self.data["runtime_final"]["live_rollout_percent"] == 1

    def test_production_false(self):
        assert self.data["runtime_final"]["production_enabled"] is False

    def test_provider_mode_replay(self):
        assert self.data["runtime_final"]["provider_mode"] == "staging_replay"

    def test_real_provider_false(self):
        assert self.data["runtime_final"]["real_provider_enabled"] is False

    def test_provider_serving_calls_zero(self):
        assert self.data["runtime_final"]["provider_serving_calls"] == 0

    def test_gates_fail_count(self):
        assert self.data["gates_fail"] == 5

    def test_gate_d_fail(self):
        gate = next(g for g in self.data["gate_results"] if g["gate_id"] == "D")
        assert gate["status"] == "FAIL"

    def test_gate_e_fail(self):
        gate = next(g for g in self.data["gate_results"] if g["gate_id"] == "E")
        assert gate["status"] == "FAIL"

    def test_gate_f_fail(self):
        gate = next(g for g in self.data["gate_results"] if g["gate_id"] == "F")
        assert gate["status"] == "FAIL"

    def test_gate_g_fail(self):
        gate = next(g for g in self.data["gate_results"] if g["gate_id"] == "G")
        assert gate["status"] == "FAIL"

    def test_gate_i_fail(self):
        gate = next(g for g in self.data["gate_results"] if g["gate_id"] == "I")
        assert gate["status"] == "FAIL"

    def test_gate_a_pass(self):
        gate = next(g for g in self.data["gate_results"] if g["gate_id"] == "A")
        assert gate["status"] == "PASS"

    def test_gate_b_pass(self):
        gate = next(g for g in self.data["gate_results"] if g["gate_id"] == "B")
        assert gate["status"] == "PASS"

    def test_gate_c_pass(self):
        gate = next(g for g in self.data["gate_results"] if g["gate_id"] == "C")
        assert gate["status"] == "PASS"

    def test_gate_s_pass(self):
        gate = next(g for g in self.data["gate_results"] if g["gate_id"] == "S")
        assert gate["status"] == "PASS"

    def test_gate_t_pass(self):
        gate = next(g for g in self.data["gate_results"] if g["gate_id"] == "T")
        assert gate["status"] == "PASS"

    def test_gate_u_pass(self):
        gate = next(g for g in self.data["gate_results"] if g["gate_id"] == "U")
        assert gate["status"] == "PASS"

    def test_continue_1pct_live(self):
        assert self.data["continue_1pct_live"] is True

    def test_expand_live_not_authorized(self):
        assert self.data["expand_live_authorized"] is False

    def test_ordinary_external_users_zero(self):
        assert self.data["ordinary_external_users"] == 0

    def test_cumulative_pi_violations_zero(self):
        assert self.data["cumulative_canary"]["cumulative_pi_violations"] == 0

    def test_next_cv_13_for_real_provider(self):
        assert self.data["next_cv_path"]["real_provider_activation"] == "cv=13 (P1.31, requires implementation + authorization)"

    def test_cv_constraint_monotonic(self):
        assert "never reuse" in self.data["next_cv_path"]["constraint"].lower()

    def test_implementation_required_list(self):
        assert len(self.data["implementation_required_before_p131"]) >= 10

    def test_next_phase_p131(self):
        assert "P1.31" in self.data["next_phase"]


# ---------------------------------------------------------------------------
# Report Markdown
# ---------------------------------------------------------------------------

class TestReportMarkdown:
    def setup_method(self):
        self.text = load_md("report")

    def test_report_exists(self):
        assert len(self.text) > 200

    def test_state_b_documented(self):
        assert "STATE B" in self.text or "State B" in self.text

    def test_not_executed_documented(self):
        assert "NOT_EXECUTED" in self.text

    def test_gate_d_e_f_g_i_in_report(self):
        for gate_id in ["D", "E", "F", "G", "I"]:
            assert f"Gate {gate_id}" in self.text or f"| {gate_id} |" in self.text

    def test_implementation_table_present(self):
        assert "Implementation Required" in self.text or "implementation required" in self.text.lower()

    def test_p131_mentioned(self):
        assert "P1.31" in self.text

    def test_no_fabricated_cost(self):
        assert "¥0" in self.text or "0 requests" in self.text
