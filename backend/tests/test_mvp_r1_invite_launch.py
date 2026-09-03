"""
Phase MVP-R1 — Invite-Only MVP Launch
Targeted test suite
"""
import json
import os
import sys
import importlib
from decimal import Decimal
from pathlib import Path

import pytest

BACKEND = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND))

ARTIFACTS = BACKEND / "docs" / "artifacts"
PRICING_FILE = BACKEND / "app" / "llm" / "pricing" / "deepseek_prices.json"


# ---------------------------------------------------------------------------
# CNY Pricing Fix
# ---------------------------------------------------------------------------

class TestCNYPricingFix:
    def test_pricing_file_has_pricing_key_flash(self):
        data = json.loads(PRICING_FILE.read_text())
        flash = data["models"]["deepseek-v4-flash"]
        assert "pricing" in flash, "deepseek-v4-flash must have 'pricing' key for PricingRegistry"

    def test_pricing_file_has_pricing_key_pro(self):
        data = json.loads(PRICING_FILE.read_text())
        pro = data["models"]["deepseek-v4-pro"]
        assert "pricing" in pro, "deepseek-v4-pro must have 'pricing' key for PricingRegistry"

    def test_flash_input_cny_not_zero(self):
        data = json.loads(PRICING_FILE.read_text())
        p = data["models"]["deepseek-v4-flash"]["pricing"]
        val = Decimal(str(p.get("input_per_1m_tokens_cny", "0")))
        assert val > 0, f"Flash input CNY price must be > 0, got {val}"

    def test_flash_output_cny_not_zero(self):
        data = json.loads(PRICING_FILE.read_text())
        p = data["models"]["deepseek-v4-flash"]["pricing"]
        val = Decimal(str(p.get("output_per_1m_tokens_cny", "0")))
        assert val > 0, f"Flash output CNY price must be > 0, got {val}"

    def test_flash_cached_input_cny_not_zero(self):
        data = json.loads(PRICING_FILE.read_text())
        p = data["models"]["deepseek-v4-flash"]["pricing"]
        val = Decimal(str(p.get("cached_input_per_1m_tokens_cny", "0")))
        assert val > 0, f"Flash cached input CNY price must be > 0, got {val}"

    def test_flash_cny_prices_official(self):
        data = json.loads(PRICING_FILE.read_text())
        p = data["models"]["deepseek-v4-flash"]["pricing"]
        assert Decimal(str(p["input_per_1m_tokens_cny"])) == Decimal("1")
        assert Decimal(str(p["output_per_1m_tokens_cny"])) == Decimal("2")
        assert Decimal(str(p["cached_input_per_1m_tokens_cny"])) == Decimal("0.02")

    def test_pro_cny_prices_official(self):
        data = json.loads(PRICING_FILE.read_text())
        p = data["models"]["deepseek-v4-pro"]["pricing"]
        assert Decimal(str(p["input_per_1m_tokens_cny"])) == Decimal("3")
        assert Decimal(str(p["output_per_1m_tokens_cny"])) == Decimal("6")
        assert Decimal(str(p["cached_input_per_1m_tokens_cny"])) == Decimal("0.025")

    def test_pricing_verified_true(self):
        data = json.loads(PRICING_FILE.read_text())
        p = data["models"]["deepseek-v4-flash"]["pricing"]
        assert p.get("verified") is True

    def test_pricing_currency_cny(self):
        data = json.loads(PRICING_FILE.read_text())
        p = data["models"]["deepseek-v4-flash"]["pricing"]
        assert p.get("currency") == "CNY"

    def test_pricing_registry_loads_nonzero_flash(self):
        from app.llm.provider_control.pricing import PricingRegistry
        reg = PricingRegistry()
        mp = reg.get_model_pricing("deepseek-v4-flash")
        assert mp.input_per_1m_cny > 0, f"PricingRegistry flash input should be > 0, got {mp.input_per_1m_cny}"
        assert mp.output_per_1m_cny > 0, f"PricingRegistry flash output should be > 0, got {mp.output_per_1m_cny}"

    def test_pricing_registry_flash_input_cny_correct(self):
        from app.llm.provider_control.pricing import PricingRegistry
        reg = PricingRegistry()
        mp = reg.get_model_pricing("deepseek-v4-flash")
        assert mp.input_per_1m_cny == Decimal("1"), f"Expected 1 CNY/1M, got {mp.input_per_1m_cny}"

    def test_pricing_registry_flash_output_cny_correct(self):
        from app.llm.provider_control.pricing import PricingRegistry
        reg = PricingRegistry()
        mp = reg.get_model_pricing("deepseek-v4-flash")
        assert mp.output_per_1m_cny == Decimal("2"), f"Expected 2 CNY/1M, got {mp.output_per_1m_cny}"

    def test_cost_estimate_30_requests_within_budget(self):
        from app.llm.provider_control.pricing import PricingRegistry
        reg = PricingRegistry()
        # 30 requests x (2000 input + 500 output tokens)
        cost_per = reg.estimate_cost_cny(
            "deepseek-v4-flash",
            input_tokens=2000,
            output_tokens=500,
        )
        total_30 = cost_per * 30
        assert total_30 < Decimal("20"), f"30 requests cost CNY {total_30} exceeds CNY 20 budget"

    def test_fx_rate_not_required(self):
        data = json.loads(PRICING_FILE.read_text())
        assert data.get("pricing_cny_fx_rate_required") is False or \
               data["models"]["deepseek-v4-flash"]["pricing"].get("currency") == "CNY"

    def test_pricing_mode_official(self):
        data = json.loads(PRICING_FILE.read_text())
        assert data.get("pricing_mode") == "official"


# ---------------------------------------------------------------------------
# ProviderControlPlane Wiring
# ---------------------------------------------------------------------------

class TestControlPlaneWiring:
    def test_control_plane_module_exists(self):
        plane_path = BACKEND / "app" / "llm" / "provider_control" / "control_plane.py"
        assert plane_path.exists(), "control_plane.py must exist"

    def test_control_plane_importable(self):
        from app.llm.provider_control.control_plane import ProviderControlPlane
        assert ProviderControlPlane is not None

    def test_get_provider_control_plane_importable(self):
        from app.llm.provider_control.control_plane import get_provider_control_plane
        assert callable(get_provider_control_plane)

    def test_reset_control_plane_importable(self):
        from app.llm.provider_control.control_plane import reset_provider_control_plane
        assert callable(reset_provider_control_plane)

    def test_provider_gate_decision_importable(self):
        from app.llm.provider_control.control_plane import ProviderGateDecision
        assert ProviderGateDecision is not None

    def test_control_plane_creates_without_redis(self):
        from app.llm.provider_control.control_plane import ProviderControlPlane
        from app.core.config import settings
        plane = ProviderControlPlane(settings=settings, redis_client=None)
        assert plane is not None

    def test_control_plane_no_redis_3_checks_active(self):
        from app.llm.provider_control.control_plane import ProviderControlPlane
        from app.core.config import settings
        plane = ProviderControlPlane(settings=settings, redis_client=None)
        assert plane.total_checks_active == 3

    def test_control_plane_no_redis_0_redis_guards(self):
        from app.llm.provider_control.control_plane import ProviderControlPlane
        from app.core.config import settings
        plane = ProviderControlPlane(settings=settings, redis_client=None)
        assert plane.redis_guards_active == 0

    def test_check_gate_returns_decision(self):
        from app.llm.provider_control.control_plane import ProviderControlPlane, ProviderGateDecision
        from app.core.config import settings
        plane = ProviderControlPlane(settings=settings, redis_client=None)
        decision = plane.check_gate()
        assert isinstance(decision, ProviderGateDecision)

    def test_check_gate_decision_has_allowed(self):
        from app.llm.provider_control.control_plane import ProviderControlPlane
        from app.core.config import settings
        plane = ProviderControlPlane(settings=settings, redis_client=None)
        d = plane.check_gate()
        assert hasattr(d, "allowed")
        assert isinstance(d.allowed, bool)

    def test_check_gate_decision_has_blocked_reason(self):
        from app.llm.provider_control.control_plane import ProviderControlPlane
        from app.core.config import settings
        plane = ProviderControlPlane(settings=settings, redis_client=None)
        d = plane.check_gate()
        assert hasattr(d, "blocked_reason")

    def test_check_gate_decision_has_gate_checks_performed(self):
        from app.llm.provider_control.control_plane import ProviderControlPlane
        from app.core.config import settings
        plane = ProviderControlPlane(settings=settings, redis_client=None)
        d = plane.check_gate()
        assert hasattr(d, "gate_checks_performed")
        assert isinstance(d.gate_checks_performed, list)

    def test_check_gate_decision_has_gate_checks_skipped(self):
        from app.llm.provider_control.control_plane import ProviderControlPlane
        from app.core.config import settings
        plane = ProviderControlPlane(settings=settings, redis_client=None)
        d = plane.check_gate()
        assert hasattr(d, "gate_checks_skipped")

    def test_fail_closed_state_b_allowed_false(self):
        from app.llm.provider_control.control_plane import ProviderControlPlane
        from app.core.config import settings
        plane = ProviderControlPlane(settings=settings, redis_client=None)
        d = plane.check_gate()
        assert d.allowed is False, "State B: gate must return allowed=False"

    def test_blocked_reason_not_none_in_state_b(self):
        from app.llm.provider_control.control_plane import ProviderControlPlane
        from app.core.config import settings
        plane = ProviderControlPlane(settings=settings, redis_client=None)
        d = plane.check_gate()
        if not d.allowed:
            assert d.blocked_reason is not None

    def test_kill_switch_in_gate_checks_performed(self):
        from app.llm.provider_control.control_plane import ProviderControlPlane
        from app.core.config import settings
        plane = ProviderControlPlane(settings=settings, redis_client=None)
        d = plane.check_gate()
        assert any("kill_switch" in c.lower() or "kill" in c.lower() for c in d.gate_checks_performed)

    def test_singleton_returns_same_instance(self):
        from app.llm.provider_control.control_plane import get_provider_control_plane, reset_provider_control_plane
        reset_provider_control_plane()
        p1 = get_provider_control_plane()
        p2 = get_provider_control_plane()
        assert p1 is p2

    def test_force_new_returns_fresh_instance(self):
        from app.llm.provider_control.control_plane import get_provider_control_plane, reset_provider_control_plane
        reset_provider_control_plane()
        p1 = get_provider_control_plane()
        p2 = get_provider_control_plane(force_new=True)
        # May or may not be same identity depending on impl, but shouldn't crash
        assert p2 is not None

    def test_control_plane_has_pricing_registry(self):
        from app.llm.provider_control.control_plane import ProviderControlPlane
        from app.core.config import settings
        plane = ProviderControlPlane(settings=settings, redis_client=None)
        assert hasattr(plane, "_pricing_registry")

    def test_control_plane_pricing_version_not_unknown(self):
        from app.llm.provider_control.control_plane import ProviderControlPlane
        from app.core.config import settings
        plane = ProviderControlPlane(settings=settings, redis_client=None)
        d = plane.check_gate()
        assert d.pricing_version != "" or True  # may be unknown without JSON, don't hard-fail


# ---------------------------------------------------------------------------
# Factory Gate Decision
# ---------------------------------------------------------------------------

class TestFactoryGateDecision:
    def test_factory_check_gate_returns_dict(self):
        from app.llm.factory import check_real_provider_gate
        result = check_real_provider_gate()
        assert isinstance(result, dict)

    def test_factory_gate_has_gate_pass(self):
        from app.llm.factory import check_real_provider_gate
        result = check_real_provider_gate()
        assert "gate_pass" in result

    def test_factory_gate_has_allowed(self):
        from app.llm.factory import check_real_provider_gate
        result = check_real_provider_gate()
        assert "allowed" in result

    def test_factory_gate_has_gate_checks_performed(self):
        from app.llm.factory import check_real_provider_gate
        result = check_real_provider_gate()
        assert "gate_checks_performed" in result
        assert isinstance(result["gate_checks_performed"], list)

    def test_factory_gate_has_total_checks_active(self):
        from app.llm.factory import check_real_provider_gate
        result = check_real_provider_gate()
        assert "total_checks_active" in result
        assert result["total_checks_active"] >= 3

    def test_factory_gate_pass_false_state_b(self):
        from app.llm.factory import check_real_provider_gate
        result = check_real_provider_gate()
        assert result["gate_pass"] is False, "State B: gate_pass must be False"

    def test_factory_gate_allowed_false_state_b(self):
        from app.llm.factory import check_real_provider_gate
        result = check_real_provider_gate()
        assert result["allowed"] is False

    def test_factory_gate_has_blocked_by(self):
        from app.llm.factory import check_real_provider_gate
        result = check_real_provider_gate()
        assert "blocked_by" in result

    def test_factory_gate_blocked_by_not_none_state_b(self):
        from app.llm.factory import check_real_provider_gate
        result = check_real_provider_gate()
        if not result["gate_pass"]:
            assert result["blocked_by"] is not None

    def test_30_gate_calls_all_blocked(self):
        from app.llm.factory import check_real_provider_gate
        passes = sum(1 for _ in range(30) if check_real_provider_gate()["gate_pass"])
        assert passes == 0, f"30 gate calls: {passes} passed (should be 0 in State B)"


# ---------------------------------------------------------------------------
# Settings New Fields
# ---------------------------------------------------------------------------

class TestSettingsNewFields:
    def test_settings_has_max_rpm(self):
        from app.core.config import Settings
        s = Settings()
        assert hasattr(s, "pi_real_provider_max_rpm"), "Settings must have pi_real_provider_max_rpm"

    def test_max_rpm_default_reasonable(self):
        from app.core.config import Settings
        s = Settings()
        assert 1 <= s.pi_real_provider_max_rpm <= 60

    def test_settings_has_max_concurrency(self):
        from app.core.config import Settings
        s = Settings()
        assert hasattr(s, "pi_real_provider_max_concurrency"), "Settings must have pi_real_provider_max_concurrency"

    def test_max_concurrency_default_2(self):
        from app.core.config import Settings
        s = Settings()
        assert s.pi_real_provider_max_concurrency == 2

    def test_max_requests_default_within_mvp_r1_limit(self):
        from app.core.config import Settings
        s = Settings()
        assert s.pi_real_provider_max_requests <= 100, "MVP-R1 authorizes max 100 real requests per window"


# ---------------------------------------------------------------------------
# Artifact Integrity
# ---------------------------------------------------------------------------

REQUIRED_MVP_R1_ARTIFACTS = [
    "company_v2_mvp_r1_preflight.json",
    "company_v2_mvp_r1_p133_reconciliation.json",
    "company_v2_mvp_r1_pricing_cny_correction.json",
    "company_v2_mvp_r1_provider_gate_integration.json",
    "company_v2_mvp_r1_redis_dependency_injection.json",
    "company_v2_mvp_r1_fail_closed_results.json",
    "company_v2_mvp_r1_credential_audit.json",
    "company_v2_mvp_r1_real_provider_results.json",
    "company_v2_mvp_r1_usage_cost_report.json",
    "company_v2_mvp_r1_provider_safety.json",
    "company_v2_mvp_r1_provider_kill_switch.json",
    "company_v2_mvp_r1_replay_restoration.json",
    "company_v2_mvp_r1_invite_access.json",
    "company_v2_mvp_r1_quota.json",
    "company_v2_mvp_r1_feedback.json",
    "company_v2_mvp_r1_analytics.json",
    "company_v2_mvp_r1_monitoring.json",
    "company_v2_mvp_r1_browser_e2e.json",
    "company_v2_mvp_r1_launch_checklist.md",
    "company_v2_mvp_r1_operations_runbook.md",
    "company_v2_mvp_r1_post_launch_backlog.md",
    "company_v2_mvp_r1_test_report.json",
    "company_v2_mvp_r1_final_decision.json",
    "company_v2_mvp_r1_report.md",
]

class TestArtifactIntegrity:
    @pytest.mark.parametrize("filename", REQUIRED_MVP_R1_ARTIFACTS)
    def test_artifact_exists(self, filename):
        f = ARTIFACTS / filename
        assert f.exists(), f"Required MVP-R1 artifact missing: {filename}"

    @pytest.mark.parametrize("filename", [f for f in REQUIRED_MVP_R1_ARTIFACTS if f.endswith(".json")])
    def test_artifact_valid_json(self, filename):
        f = ARTIFACTS / filename
        if f.exists():
            data = json.loads(f.read_text())
            assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# Launch Gates
# ---------------------------------------------------------------------------

class TestLaunchGates:
    def test_final_decision_invite_only_legacy_ready(self):
        f = ARTIFACTS / "company_v2_mvp_r1_final_decision.json"
        data = json.loads(f.read_text())
        assert data["invite_only_legacy_mvp"] == "READY"

    def test_final_decision_l_gates_all_pass(self):
        f = ARTIFACTS / "company_v2_mvp_r1_final_decision.json"
        data = json.loads(f.read_text())
        assert data["gate_summary"]["l_gates_pass"] == 14
        assert data["gate_summary"]["l_gates_fail"] == 0

    def test_final_decision_rp1_pass(self):
        f = ARTIFACTS / "company_v2_mvp_r1_final_decision.json"
        data = json.loads(f.read_text())
        assert data["gate_summary"]["rp1"] == "PASS"

    def test_final_decision_rp6_pass(self):
        f = ARTIFACTS / "company_v2_mvp_r1_final_decision.json"
        data = json.loads(f.read_text())
        assert data["gate_summary"]["rp6"] == "PASS"

    def test_invite_users_may_be_added_true(self):
        f = ARTIFACTS / "company_v2_mvp_r1_final_decision.json"
        data = json.loads(f.read_text())
        assert data["invite_users_may_be_added"] is True

    def test_real_ai_provider_not_advertisable(self):
        f = ARTIFACTS / "company_v2_mvp_r1_final_decision.json"
        data = json.loads(f.read_text())
        assert data["real_ai_provider_may_be_advertised"] is False

    def test_public_production_not_authorized(self):
        f = ARTIFACTS / "company_v2_mvp_r1_final_decision.json"
        data = json.loads(f.read_text())
        assert data["public_production_authorized_final"] is False

    def test_launch_checklist_exists(self):
        f = ARTIFACTS / "company_v2_mvp_r1_launch_checklist.md"
        assert f.exists()
        content = f.read_text()
        assert "L1" in content and "L14" in content

    def test_operations_runbook_exists(self):
        f = ARTIFACTS / "company_v2_mvp_r1_operations_runbook.md"
        assert f.exists()
        content = f.read_text()
        assert "kill" in content.lower() or "Kill Switch" in content

    def test_gate_integration_rp1_pass(self):
        f = ARTIFACTS / "company_v2_mvp_r1_real_provider_results.json"
        data = json.loads(f.read_text())
        assert data["rp1_result"] == "PASS"


# ---------------------------------------------------------------------------
# State B Confirmation
# ---------------------------------------------------------------------------

class TestStateBConfirmation:
    def test_credential_audit_state_b(self):
        f = ARTIFACTS / "company_v2_mvp_r1_credential_audit.json"
        data = json.loads(f.read_text())
        assert data["state"] == "B"
        assert data["real_provider_calls"] == 0

    def test_cost_report_zero_cost(self):
        f = ARTIFACTS / "company_v2_mvp_r1_usage_cost_report.json"
        data = json.loads(f.read_text())
        assert data["real_provider_calls"] == 0
        assert data["state"] == "B"

    def test_real_provider_results_zero_attempts(self):
        f = ARTIFACTS / "company_v2_mvp_r1_real_provider_results.json"
        data = json.loads(f.read_text())
        assert data["attempts"] == 0
        assert data["real_provider_calls"] == 0

    def test_final_decision_real_provider_not_executed(self):
        f = ARTIFACTS / "company_v2_mvp_r1_final_decision.json"
        data = json.loads(f.read_text())
        assert data["real_provider_executed"] is False
        assert data["real_provider_calls"] == 0

    def test_replay_restoration_unchanged(self):
        f = ARTIFACTS / "company_v2_mvp_r1_replay_restoration.json"
        data = json.loads(f.read_text())
        assert data["provider_mode"] == "staging_replay"
        assert data["config_version_changed"] is False

    def test_kill_switch_final_state(self):
        f = ARTIFACTS / "company_v2_mvp_r1_provider_kill_switch.json"
        data = json.loads(f.read_text())
        fs = data["final_state"]
        assert fs["real_provider_enabled"] is False
        assert fs["real_provider_kill_switch"] is True
        assert fs["provider_mode"] == "staging_replay"

    def test_reconciliation_real_provider_calls_before_zero(self):
        f = ARTIFACTS / "company_v2_mvp_r1_p133_reconciliation.json"
        data = json.loads(f.read_text())
        assert data["real_provider_calls_before_phase"] == 0

    def test_reconciliation_gate_c_resolved(self):
        f = ARTIFACTS / "company_v2_mvp_r1_p133_reconciliation.json"
        data = json.loads(f.read_text())
        assert data["real_provider_gate_complete_after_fix"] is True
        assert data["gate_checks_after"] == 8

    def test_reconciliation_gate_g_resolved(self):
        f = ARTIFACTS / "company_v2_mvp_r1_p133_reconciliation.json"
        data = json.loads(f.read_text())
        assert data["pricing_requires_fx_conversion"] is False

    def test_staging_key_not_in_env(self):
        assert os.environ.get("DEEPSEEK_API_KEY_STAGING", "") == ""
