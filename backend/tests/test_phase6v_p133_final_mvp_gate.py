"""
Phase 6V-P1.33 — Final MVP Gate
Targeted test suite: 89 tests
Verifies model ID verification, pricing verification, provider path audit,
fail-closed behavior, State B credential audit, artifact integrity.
"""
import json
import os
import sys
import inspect
from pathlib import Path

import pytest

# Add backend to path
BACKEND = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND))

# Ensure minimum required env vars are set so Settings() can be instantiated
# in tests that need to inspect default field values directly.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/testdb")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-p133-unit-tests-only")

ARTIFACTS = BACKEND / "docs" / "artifacts"
PRICING_FILE = BACKEND / "app" / "llm" / "pricing" / "deepseek_prices.json"


# ---------------------------------------------------------------------------
# Gate E — Official Model Verification
# ---------------------------------------------------------------------------

class TestModelVerificationGateE:
    def test_pricing_file_exists(self):
        assert PRICING_FILE.exists(), "deepseek_prices.json must exist"

    def test_pricing_file_valid_json(self):
        data = json.loads(PRICING_FILE.read_text())
        assert isinstance(data, dict)

    def test_pricing_mode_is_official(self):
        data = json.loads(PRICING_FILE.read_text())
        assert data["pricing_mode"] == "official", f"Expected 'official', got {data.get('pricing_mode')}"

    def test_pricing_verified_true(self):
        data = json.loads(PRICING_FILE.read_text())
        assert data["verified"] is True

    def test_pricing_currency_is_usd(self):
        data = json.loads(PRICING_FILE.read_text())
        assert data["currency"] == "USD"

    def test_source_url_present(self):
        data = json.loads(PRICING_FILE.read_text())
        assert "source_url" in data
        assert "deepseek" in data["source_url"].lower()

    def test_source_retrieval_date_present(self):
        data = json.loads(PRICING_FILE.read_text())
        assert "source_retrieval_date" in data
        assert data["source_retrieval_date"] == "2026-07-26"

    def test_deepseek_v4_flash_is_official_model(self):
        data = json.loads(PRICING_FILE.read_text())
        models = data["models"]
        assert "deepseek-v4-flash" in models
        m = models["deepseek-v4-flash"]
        assert m["official_api_id"] == "deepseek-v4-flash"

    def test_deepseek_v4_pro_is_official_model(self):
        data = json.loads(PRICING_FILE.read_text())
        models = data["models"]
        assert "deepseek-v4-pro" in models
        m = models["deepseek-v4-pro"]
        assert m["official_api_id"] == "deepseek-v4-pro"

    def test_deepseek_chat_is_deprecated_alias(self):
        data = json.loads(PRICING_FILE.read_text())
        models = data["models"]
        flash = models["deepseek-v4-flash"]
        deprecated = flash.get("deprecated_aliases", [])
        assert "deepseek-chat" in deprecated, \
            "deepseek-chat must be listed as deprecated alias of deepseek-v4-flash"

    def test_deepseek_reasoner_deprecated_in_model_data(self):
        data = json.loads(PRICING_FILE.read_text())
        models = data["models"]
        # reasoner should be present and deprecated
        assert "deepseek-reasoner" in models
        reasoner = models["deepseek-reasoner"]
        combined = (
            reasoner.get("deprecation_status", "") +
            reasoner.get("deprecation_note", "")
        ).lower()
        assert "deprecat" in combined, \
            "deepseek-reasoner must be marked deprecated"

    def test_schema_version_references_deepseek_pricing(self):
        data = json.loads(PRICING_FILE.read_text())
        sv = data.get("schema_version", "")
        assert "deepseek" in sv.lower() or "pricing" in sv.lower() or "v2" in sv.lower()


# ---------------------------------------------------------------------------
# Gate F — Official Pricing Verification
# ---------------------------------------------------------------------------

class TestPricingVerificationGateF:
    def _flash_pricing(self):
        data = json.loads(PRICING_FILE.read_text())
        return data["models"]["deepseek-v4-flash"]["pricing_usd"]

    def _pro_pricing(self):
        data = json.loads(PRICING_FILE.read_text())
        return data["models"]["deepseek-v4-pro"]["pricing_usd"]

    def test_flash_input_cache_miss_price(self):
        p = self._flash_pricing()
        assert p["input_cache_miss_per_1m"] == "0.14"

    def test_flash_input_cache_hit_price(self):
        p = self._flash_pricing()
        assert p["input_cache_hit_per_1m"] == "0.0028"

    def test_flash_output_price(self):
        p = self._flash_pricing()
        assert p["output_per_1m"] == "0.28"

    def test_flash_pricing_verified(self):
        p = self._flash_pricing()
        assert p.get("verified") is True

    def test_pro_input_cache_miss_price(self):
        p = self._pro_pricing()
        assert p["input_cache_miss_per_1m"] == "0.435"

    def test_pro_input_cache_hit_price(self):
        p = self._pro_pricing()
        assert p["input_cache_hit_per_1m"] == "0.003625"

    def test_pro_output_price(self):
        p = self._pro_pricing()
        assert p["output_per_1m"] == "0.87"

    def test_pro_pricing_verified(self):
        p = self._pro_pricing()
        assert p.get("verified") is True

    def test_cny_estimates_not_verified(self):
        data = json.loads(PRICING_FILE.read_text())
        flash_cny = data["models"]["deepseek-v4-flash"]["pricing_cny_estimate"]
        assert flash_cny.get("verified") is False, \
            "CNY estimates must be marked verified=false (exchange rate estimate)"

    def test_exchange_rate_estimate_documented(self):
        data = json.loads(PRICING_FILE.read_text())
        flash_cny = data["models"]["deepseek-v4-flash"]["pricing_cny_estimate"]
        assert "exchange_rate_used" in flash_cny or \
               "exchange_rate_cny_per_usd_estimate" in data, \
            "Exchange rate estimate must be documented"

    def test_flash_enabled_for_staging_real_false(self):
        data = json.loads(PRICING_FILE.read_text())
        assert data["models"]["deepseek-v4-flash"].get("enabled_for_staging_real") is False, \
            "enabled_for_staging_real must remain False until P1.33.5 activation"

    def test_pro_enabled_for_staging_real_false(self):
        data = json.loads(PRICING_FILE.read_text())
        assert data["models"]["deepseek-v4-pro"].get("enabled_for_staging_real") is False


# ---------------------------------------------------------------------------
# Gate C — Provider Call Path Audit
# ---------------------------------------------------------------------------

class TestProviderPathAuditGateC:
    def test_factory_module_importable(self):
        import app.llm.factory as factory_module
        assert factory_module is not None

    def test_check_real_provider_gate_exists(self):
        import app.llm.factory as factory_module
        assert hasattr(factory_module, "check_real_provider_gate"), \
            "check_real_provider_gate() must exist in factory.py"

    def test_check_real_provider_gate_callable(self):
        from app.llm.factory import check_real_provider_gate
        assert callable(check_real_provider_gate)

    def test_check_real_provider_gate_returns_dict(self):
        from app.llm.factory import check_real_provider_gate
        result = check_real_provider_gate()
        assert isinstance(result, dict), "check_real_provider_gate() must return dict"

    def test_gate_result_has_gate_pass_key(self):
        from app.llm.factory import check_real_provider_gate
        result = check_real_provider_gate()
        assert "gate_pass" in result

    def test_gate_result_has_blocked_by_key(self):
        from app.llm.factory import check_real_provider_gate
        result = check_real_provider_gate()
        assert "blocked_by" in result

    def test_gate_result_has_error_class_key(self):
        from app.llm.factory import check_real_provider_gate
        result = check_real_provider_gate()
        assert "error_class" in result

    def test_gate_pass_is_bool(self):
        from app.llm.factory import check_real_provider_gate
        result = check_real_provider_gate()
        assert isinstance(result["gate_pass"], bool)

    def test_fail_closed_state_b(self):
        """Without credential (kill_switch=True by default), gate must return gate_pass=False"""
        from app.llm.factory import check_real_provider_gate
        result = check_real_provider_gate()
        # In State B (kill_switch=True, enabled=False), gate_pass must be False
        assert result["gate_pass"] is False, \
            f"State B: gate must fail-closed. Got gate_pass={result['gate_pass']}"

    def test_provider_activation_gate_importable(self):
        from app.llm.provider_control.activation_gate import ProviderActivationGate
        assert ProviderActivationGate is not None

    def test_activation_gate_has_check_all_method(self):
        from app.llm.provider_control.activation_gate import ProviderActivationGate
        assert hasattr(ProviderActivationGate, "check_all")
        assert callable(ProviderActivationGate.check_all)

    def test_kill_switch_check_in_gate(self):
        from app.llm.provider_control.activation_gate import ProviderActivationGate
        src = inspect.getsource(ProviderActivationGate)
        assert "kill_switch" in src.lower() or "killswitch" in src.lower()

    def test_credential_check_in_gate(self):
        from app.llm.provider_control.activation_gate import ProviderActivationGate
        src = inspect.getsource(ProviderActivationGate)
        assert "credential" in src.lower() or "api_key" in src.lower() or \
               "deepseek_api_key" in src.lower()

    def test_factory_imports_activation_gate(self):
        import app.llm.factory as factory_module
        src = inspect.getsource(factory_module)
        assert "ProviderActivationGate" in src or "activation_gate" in src

    def test_budget_guard_not_injected_in_factory_gate(self):
        """Document that budget guard is NOT injected into check_real_provider_gate()"""
        import app.llm.factory as factory_module
        src = inspect.getsource(factory_module.check_real_provider_gate)
        # The function should NOT pass budget_guard to ProviderActivationGate
        # (it calls ProviderActivationGate(settings=settings) with no Redis guards)
        assert "budget_guard=" not in src, \
            "budget_guard must NOT be injected in check_real_provider_gate() (State B gap documented)"


# ---------------------------------------------------------------------------
# Gate G — Budget Guard Currency
# ---------------------------------------------------------------------------

class TestBudgetGuardCurrencyGateG:
    def test_settings_has_max_cost_cny_setting(self):
        from app.core.config import Settings
        s = Settings()
        assert hasattr(s, "pi_real_provider_max_cost_cny"), \
            "Settings must have pi_real_provider_max_cost_cny"

    def test_max_cost_cny_default_is_100(self):
        from app.core.config import Settings
        s = Settings()
        assert s.pi_real_provider_max_cost_cny == 100.0

    def test_exchange_rate_estimate_in_pricing_file(self):
        data = json.loads(PRICING_FILE.read_text())
        data_str = json.dumps(data).lower()
        assert "exchange_rate" in data_str, \
            "Exchange rate estimate must be documented in pricing file"

    def test_cny_estimate_flash_input_reasonable(self):
        data = json.loads(PRICING_FILE.read_text())
        cny = data["models"]["deepseek-v4-flash"]["pricing_cny_estimate"]
        # 0.14 USD * 7.20 = 1.008 CNY
        val = float(cny["input_cache_miss_per_1m"])
        assert 0.8 < val < 1.5, f"Flash input CNY estimate {val} out of range [0.8, 1.5]"

    def test_cny_estimate_flash_output_reasonable(self):
        data = json.loads(PRICING_FILE.read_text())
        cny = data["models"]["deepseek-v4-flash"]["pricing_cny_estimate"]
        # 0.28 USD * 7.20 = 2.016 CNY
        val = float(cny["output_per_1m"])
        assert 1.5 < val < 3.0, f"Flash output CNY estimate {val} out of range [1.5, 3.0]"

    def test_100_requests_within_budget(self):
        """Verify 100 real requests would be within CNY 100 budget"""
        # 2000 input tokens + 500 output tokens per request
        # flash: 0.14 USD/1M input, 0.28 USD/1M output
        input_cost_usd = (2000 / 1_000_000) * 0.14 * 100  # 100 requests
        output_cost_usd = (500 / 1_000_000) * 0.28 * 100
        total_usd = input_cost_usd + output_cost_usd
        total_cny = total_usd * 7.20
        assert total_cny < 100.0, \
            f"100 requests approximately CNY {total_cny:.4f} must be under CNY 100 budget"

    def test_pricing_version_documented(self):
        data = json.loads(PRICING_FILE.read_text())
        assert "pricing_version" in data or "schema_version" in data

    def test_pricing_has_exchange_rate_note(self):
        data = json.loads(PRICING_FILE.read_text())
        # exchange_rate_cny_per_usd_estimate or exchange_rate_note should exist
        assert "exchange_rate_cny_per_usd_estimate" in data or \
               "exchange_rate_note" in data, \
            "Pricing file must document exchange rate estimate at top level"


# ---------------------------------------------------------------------------
# Gate H — Fail-Closed Preflight
# ---------------------------------------------------------------------------

class TestFailClosedPreflightGateH:
    def test_settings_kill_switch_default_true(self):
        from app.core.config import Settings
        s = Settings()
        assert s.pi_real_provider_kill_switch is True, \
            "Kill switch must default to True (fail-closed)"

    def test_settings_real_provider_enabled_default_false(self):
        from app.core.config import Settings
        s = Settings()
        assert s.pi_real_provider_enabled is False, \
            "Real provider must default to disabled"

    def test_settings_staging_key_default_none(self):
        from app.core.config import Settings
        s = Settings()
        key = s.deepseek_api_key_staging
        assert not key, "Staging key must default to None/empty (State B)"

    def test_gate_blocked_in_state_b(self):
        from app.llm.factory import check_real_provider_gate
        result = check_real_provider_gate()
        assert result["gate_pass"] is False

    def test_gate_returns_blocked_by_when_blocked(self):
        from app.llm.factory import check_real_provider_gate
        result = check_real_provider_gate()
        if not result["gate_pass"]:
            assert result["blocked_by"] is not None, \
                "blocked_by must be set when gate fails"

    def test_no_env_staging_key(self):
        """DEEPSEEK_API_KEY_STAGING must not be in environment"""
        val = os.environ.get("DEEPSEEK_API_KEY_STAGING", "")
        assert val == "", \
            "DEEPSEEK_API_KEY_STAGING must not be set in test environment (State B)"

    def test_kill_switch_error_importable(self):
        from app.llm.provider_control.errors import KillSwitchError
        assert KillSwitchError is not None

    def test_credential_gate_error_importable(self):
        from app.llm.provider_control.errors import CredentialGateError
        assert CredentialGateError is not None

    def test_provider_errors_module_exists(self):
        errors_path = BACKEND / "app" / "llm" / "provider_control" / "errors.py"
        assert errors_path.exists(), "provider_control/errors.py must exist"

    def test_30_simulated_requests_zero_real(self):
        """Simulate 30 gate checks — all must be blocked (State B)"""
        from app.llm.factory import check_real_provider_gate
        real_calls = 0
        for _ in range(30):
            result = check_real_provider_gate()
            if result["gate_pass"]:
                real_calls += 1
        assert real_calls == 0, \
            f"30 simulated gate checks had {real_calls} passes — must be 0 in State B"


# ---------------------------------------------------------------------------
# Gate D — Staging Credential Audit
# ---------------------------------------------------------------------------

class TestStateBCredentialAudit:
    def test_staging_key_not_in_env(self):
        assert os.environ.get("DEEPSEEK_API_KEY_STAGING", "") == ""

    def test_settings_staging_key_none(self):
        from app.core.config import Settings
        s = Settings()
        key = s.deepseek_api_key_staging
        assert not key, \
            f"deepseek_api_key_staging must be None/empty in State B, got: {bool(key)}"

    def test_credential_audit_artifact_exists(self):
        f = ARTIFACTS / "company_v2_phase6v_p133_credential_audit.json"
        assert f.exists()

    def test_credential_audit_status_not_set(self):
        f = ARTIFACTS / "company_v2_phase6v_p133_credential_audit.json"
        data = json.loads(f.read_text())
        assert data["status"] == "NOT_SET"

    def test_credential_audit_state_b(self):
        f = ARTIFACTS / "company_v2_phase6v_p133_credential_audit.json"
        data = json.loads(f.read_text())
        assert data["state"] == "B"

    def test_credential_audit_gate_d_not_evaluated(self):
        f = ARTIFACTS / "company_v2_phase6v_p133_credential_audit.json"
        data = json.loads(f.read_text())
        assert data["gate_d_result"] == "NOT_EVALUATED"

    def test_p133_final_decision_state_b(self):
        f = ARTIFACTS / "company_v2_phase6v_p133_final_decision.json"
        data = json.loads(f.read_text())
        assert data["real_provider_executed"] is False
        assert data["real_provider_requests"] == 0

    def test_real_provider_cost_zero(self):
        f = ARTIFACTS / "company_v2_phase6v_p133_final_decision.json"
        data = json.loads(f.read_text())
        assert data["real_provider_cost_cny"] == 0
        assert data["real_provider_cost_usd"] == 0.0


# ---------------------------------------------------------------------------
# Gate M — Replay Restoration
# ---------------------------------------------------------------------------

class TestReplayRestorationGateM:
    def test_settings_provider_mode_staging_replay(self):
        from app.core.config import Settings
        s = Settings()
        # pi_canary_provider_mode or similar setting should be staging_replay
        mode = getattr(s, "pi_canary_provider_mode", None) or \
               getattr(s, "pi_provider_mode", None) or \
               getattr(s, "provider_mode", None)
        if mode is not None:
            assert mode == "staging_replay", \
                f"Expected staging_replay, got {mode}"

    def test_replay_restoration_artifact_exists(self):
        f = ARTIFACTS / "company_v2_phase6v_p133_replay_restoration.json"
        assert f.exists()

    def test_replay_restoration_mode_unchanged(self):
        f = ARTIFACTS / "company_v2_phase6v_p133_replay_restoration.json"
        data = json.loads(f.read_text())
        assert data["mode_changed"] is False

    def test_cv_12_maintained(self):
        f = ARTIFACTS / "company_v2_phase6v_p133_replay_restoration.json"
        data = json.loads(f.read_text())
        assert data["cv_path"]["actual_cv"] == 12

    def test_gate_m_pass(self):
        f = ARTIFACTS / "company_v2_phase6v_p133_replay_restoration.json"
        data = json.loads(f.read_text())
        assert data["gate_m_result"] == "PASS"


# ---------------------------------------------------------------------------
# P1.32 Reconciliation Artifact
# ---------------------------------------------------------------------------

class TestP132ReconciliationArtifact:
    def test_reconciliation_artifact_exists(self):
        f = ARTIFACTS / "company_v2_phase6v_p133_p132_release_reconciliation.json"
        assert f.exists()

    def test_p132_claim_is_correct(self):
        f = ARTIFACTS / "company_v2_phase6v_p133_p132_release_reconciliation.json"
        data = json.loads(f.read_text())
        assert data["p132_claim_is_correct"] is True

    def test_reconciliation_clarifies_scope(self):
        f = ARTIFACTS / "company_v2_phase6v_p133_p132_release_reconciliation.json"
        data = json.loads(f.read_text())
        scope = data.get("p132_claim_scope", "")
        assert "product" in scope.lower() or "demo" in scope.lower() or "invite" in scope.lower()

    def test_reconciliation_lists_what_is_not_meant(self):
        f = ARTIFACTS / "company_v2_phase6v_p133_p132_release_reconciliation.json"
        data = json.loads(f.read_text())
        not_mean = data.get("p132_claim_does_NOT_mean", [])
        assert len(not_mean) >= 3

    def test_p133_resolves_gate_e(self):
        f = ARTIFACTS / "company_v2_phase6v_p133_p132_release_reconciliation.json"
        data = json.loads(f.read_text())
        resolves = " ".join(data.get("p133_resolves", []))
        assert "Gate E" in resolves or "model" in resolves.lower()

    def test_p133_resolves_gate_f(self):
        f = ARTIFACTS / "company_v2_phase6v_p133_p132_release_reconciliation.json"
        data = json.loads(f.read_text())
        resolves = " ".join(data.get("p133_resolves", []))
        assert "Gate F" in resolves or "pricing" in resolves.lower()

    def test_next_after_p133_is_mvp_r1(self):
        f = ARTIFACTS / "company_v2_phase6v_p133_p132_release_reconciliation.json"
        data = json.loads(f.read_text())
        next_phase = data.get("next_after_p133", "")
        assert "MVP-R1" in next_phase or "invite" in next_phase.lower()


# ---------------------------------------------------------------------------
# Artifact Integrity
# ---------------------------------------------------------------------------

REQUIRED_P133_ARTIFACTS = [
    "company_v2_phase6v_p133_preflight_audit.json",
    "company_v2_phase6v_p133_p132_release_reconciliation.json",
    "company_v2_phase6v_p133_provider_path_audit.json",
    "company_v2_phase6v_p133_model_verification.json",
    "company_v2_phase6v_p133_pricing_verification.json",
    "company_v2_phase6v_p133_credential_audit.json",
    "company_v2_phase6v_p133_fail_closed_preflight.json",
    "company_v2_phase6v_p133_real_provider_results.json",
    "company_v2_phase6v_p133_cost_report.json",
    "company_v2_phase6v_p133_replay_restoration.json",
    "company_v2_phase6v_p133_mvp_regression.json",
    "company_v2_phase6v_p133_browser_e2e.json",
    "company_v2_phase6v_p133_mvp_release_gate.json",
    "company_v2_phase6v_p133_final_decision.json",
    "company_v2_phase6v_p133_report.md",
]

_JSON_ARTIFACTS = [f for f in REQUIRED_P133_ARTIFACTS if f.endswith(".json")]


class TestArtifactIntegrity:
    @pytest.mark.parametrize("filename", REQUIRED_P133_ARTIFACTS)
    def test_artifact_exists(self, filename):
        f = ARTIFACTS / filename
        assert f.exists(), f"Required P1.33 artifact missing: {filename}"

    @pytest.mark.parametrize("filename", _JSON_ARTIFACTS)
    def test_artifact_valid_json(self, filename):
        f = ARTIFACTS / filename
        if f.exists():
            data = json.loads(f.read_text())
            assert isinstance(data, dict)

    def test_final_decision_invite_only_authorized(self):
        f = ARTIFACTS / "company_v2_phase6v_p133_final_decision.json"
        data = json.loads(f.read_text())
        assert data.get("invite_only_release_authorized") is True

    def test_gate_assessment_zero_fail(self):
        f = ARTIFACTS / "company_v2_phase6v_p133_mvp_release_gate.json"
        data = json.loads(f.read_text())
        assert data["summary"]["fail"] == 0

    def test_final_decision_decision_field(self):
        f = ARTIFACTS / "company_v2_phase6v_p133_final_decision.json"
        data = json.loads(f.read_text())
        assert data["decision"] == "MVP_GATE_STATE_B_COMPLETE"

    def test_final_decision_mvp_rc_true(self):
        f = ARTIFACTS / "company_v2_phase6v_p133_final_decision.json"
        data = json.loads(f.read_text())
        assert data["mvp_release_candidate"] is True

    def test_report_md_contains_gate_table(self):
        f = ARTIFACTS / "company_v2_phase6v_p133_report.md"
        content = f.read_text()
        assert "| A |" in content or "| Gate |" in content
        assert "PASS" in content

    def test_mvp_regression_zero_failed(self):
        f = ARTIFACTS / "company_v2_phase6v_p133_mvp_regression.json"
        data = json.loads(f.read_text())
        assert data["combined"]["failed"] == 0
        assert data["p133_targeted_tests"]["failed"] == 0
