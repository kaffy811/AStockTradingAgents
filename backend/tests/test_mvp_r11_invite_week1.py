"""
Phase MVP-R1.1 — Invite-Only Launch & Week-1 Validation
Targeted test suite
"""
import json
import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND))

ARTIFACTS = BACKEND / "docs" / "artifacts"


# ---------------------------------------------------------------------------
# Settings — Quota and Wave Config
# ---------------------------------------------------------------------------

class TestMvpSettingsQuota:
    def test_settings_has_daily_quota_per_user(self):
        from app.core.config import Settings
        s = Settings()
        assert hasattr(s, "mvp_daily_quota_per_user")

    def test_daily_quota_per_user_default_10(self):
        from app.core.config import Settings
        s = Settings()
        assert s.mvp_daily_quota_per_user == 10

    def test_settings_has_global_daily_quota(self):
        from app.core.config import Settings
        s = Settings()
        assert hasattr(s, "mvp_global_daily_quota")

    def test_global_daily_quota_default_300(self):
        from app.core.config import Settings
        s = Settings()
        assert s.mvp_global_daily_quota == 300

    def test_settings_has_max_concurrent_per_user(self):
        from app.core.config import Settings
        s = Settings()
        assert hasattr(s, "mvp_max_concurrent_per_user")

    def test_max_concurrent_per_user_default_1(self):
        from app.core.config import Settings
        s = Settings()
        assert s.mvp_max_concurrent_per_user == 1

    def test_settings_has_max_invited_users(self):
        from app.core.config import Settings
        s = Settings()
        assert hasattr(s, "mvp_max_invited_users")

    def test_max_invited_users_default_50(self):
        from app.core.config import Settings
        s = Settings()
        assert s.mvp_max_invited_users == 50

    def test_wave1_max_users_default_10(self):
        from app.core.config import Settings
        s = Settings()
        assert s.mvp_wave1_max_users == 10

    def test_wave2_max_users_default_30(self):
        from app.core.config import Settings
        s = Settings()
        assert s.mvp_wave2_max_users == 30

    def test_wave3_max_users_default_50(self):
        from app.core.config import Settings
        s = Settings()
        assert s.mvp_wave3_max_users == 50


# ---------------------------------------------------------------------------
# Settings — Access Control and Kill Switches
# ---------------------------------------------------------------------------

class TestMvpSettingsAccessControl:
    def test_public_registration_disabled_by_default(self):
        from app.core.config import Settings
        s = Settings()
        assert s.mvp_public_registration_enabled is False

    def test_new_invites_enabled_by_default(self):
        from app.core.config import Settings
        s = Settings()
        assert s.mvp_new_invites_enabled is True

    def test_new_login_enabled_by_default(self):
        from app.core.config import Settings
        s = Settings()
        assert s.mvp_new_login_enabled is True

    def test_new_chat_enabled_by_default(self):
        from app.core.config import Settings
        s = Settings()
        assert s.mvp_new_chat_enabled is True

    def test_kill_invites_false_by_default(self):
        from app.core.config import Settings
        s = Settings()
        assert s.mvp_kill_invites is False

    def test_kill_login_false_by_default(self):
        from app.core.config import Settings
        s = Settings()
        assert s.mvp_kill_login is False

    def test_kill_chat_false_by_default(self):
        from app.core.config import Settings
        s = Settings()
        assert s.mvp_kill_chat is False


# ---------------------------------------------------------------------------
# Router — New Endpoints
# ---------------------------------------------------------------------------

class TestMvpRouterNewEndpoints:
    def test_quota_check_endpoint_registered(self):
        from app.routers.mvp import router
        paths = [r.path for r in router.routes]
        assert any("quota" in p for p in paths), f"No quota endpoint found in {paths}"

    def test_wave_status_endpoint_registered(self):
        from app.routers.mvp import router
        paths = [r.path for r in router.routes]
        assert any("wave" in p for p in paths), f"No wave endpoint found in {paths}"

    def test_quota_check_response_schema(self):
        from app.routers.mvp import QuotaCheckResponse
        r = QuotaCheckResponse(allowed=True, daily_used=3, daily_limit=10)
        assert r.allowed is True
        assert r.daily_used == 3

    def test_quota_check_response_blocked(self):
        from app.routers.mvp import QuotaCheckResponse
        r = QuotaCheckResponse(
            allowed=False,
            reason="今日测试额度已用完，请明天继续使用。",
            daily_used=10,
            daily_limit=10,
        )
        assert r.allowed is False
        assert r.reason is not None
        assert "额度" in r.reason or "quota" in r.reason.lower()

    def test_wave_status_response_schema(self):
        from app.routers.mvp import WaveStatusResponse
        r = WaveStatusResponse(
            current_wave=0,
            max_invited_users=50,
            wave_limits={"wave1": 10, "wave2": 30, "wave3": 50},
            new_invites_enabled=True,
            new_login_enabled=True,
            new_chat_enabled=True,
            kill_switches={"kill_invites": False, "kill_login": False, "kill_chat": False},
        )
        assert r.current_wave == 0
        assert r.max_invited_users == 50


# ---------------------------------------------------------------------------
# Provider State
# ---------------------------------------------------------------------------

class TestStateBProvider:
    def test_real_provider_disabled(self):
        from app.core.config import Settings
        s = Settings()
        assert s.pi_real_provider_enabled is False

    def test_kill_switch_active(self):
        from app.core.config import Settings
        s = Settings()
        assert s.pi_real_provider_kill_switch is True

    def test_staging_key_not_set(self):
        assert os.environ.get("DEEPSEEK_API_KEY_STAGING", "") == ""

    def test_provider_mode_staging_replay(self):
        from app.core.config import Settings
        s = Settings()
        assert s.pi_canary_provider_mode == "staging_replay"

    def test_gate_blocked_state_b(self):
        from app.llm.factory import check_real_provider_gate
        result = check_real_provider_gate()
        assert result["gate_pass"] is False


# ---------------------------------------------------------------------------
# Artifact Integrity
# ---------------------------------------------------------------------------

REQUIRED_ARTIFACTS = [
    "company_v2_mvp_r11_preflight.json",
    "company_v2_mvp_r11_runtime_probe.json",
    "company_v2_mvp_r11_invite_configuration.json",
    "company_v2_mvp_r11_quota_configuration.json",
    "company_v2_mvp_r11_feedback_validation.json",
    "company_v2_mvp_r11_analytics_validation.json",
    "company_v2_mvp_r11_monitoring_validation.json",
    "company_v2_mvp_r11_kill_switch_drill.json",
    "company_v2_mvp_r11_launch_gate.json",
    "company_v2_mvp_r11_day1.json",
    "company_v2_mvp_r11_day2.json",
    "company_v2_mvp_r11_day3.json",
    "company_v2_mvp_r11_day4.json",
    "company_v2_mvp_r11_day5.json",
    "company_v2_mvp_r11_day6.json",
    "company_v2_mvp_r11_day7.json",
    "company_v2_mvp_r11_week1_review.md",
    "company_v2_mvp_r11_post_launch_backlog.md",
    "company_v2_mvp_r11_final_decision.json",
    "company_v2_mvp_r11_report.md",
]

class TestArtifactIntegrity:
    @pytest.mark.parametrize("filename", REQUIRED_ARTIFACTS)
    def test_artifact_exists(self, filename):
        f = ARTIFACTS / filename
        assert f.exists(), f"Missing artifact: {filename}"

    @pytest.mark.parametrize("filename", [f for f in REQUIRED_ARTIFACTS if f.endswith(".json")])
    def test_artifact_valid_json(self, filename):
        f = ARTIFACTS / filename
        if f.exists():
            data = json.loads(f.read_text())
            assert isinstance(data, dict)

    def test_launch_gate_16_pass(self):
        f = ARTIFACTS / "company_v2_mvp_r11_launch_gate.json"
        data = json.loads(f.read_text())
        assert data["summary"]["pass"] == 16
        assert data["summary"]["fail"] == 0

    def test_final_decision_wave1_authorized(self):
        f = ARTIFACTS / "company_v2_mvp_r11_final_decision.json"
        data = json.loads(f.read_text())
        assert data["wave1_authorized"] is True
        assert data["invite_users_may_be_added"] is True

    def test_final_decision_real_ai_not_advertised(self):
        f = ARTIFACTS / "company_v2_mvp_r11_final_decision.json"
        data = json.loads(f.read_text())
        assert data["real_ai_provider_may_be_advertised"] is False

    def test_final_decision_no_further_phases(self):
        f = ARTIFACTS / "company_v2_mvp_r11_final_decision.json"
        data = json.loads(f.read_text())
        assert data["further_pre_launch_phases_required"] is False

    def test_day_reports_not_prefilled(self):
        """Day reports must have null values (not fake data)"""
        for day in range(1, 8):
            f = ARTIFACTS / f"company_v2_mvp_r11_day{day}.json"
            if f.exists():
                data = json.loads(f.read_text())
                users = data.get("users", {})
                # daily_active should be null (not fake non-zero number)
                assert users.get("daily_active") is None, \
                    f"day{day}.json daily_active should be null (not prefilled)"

    def test_kill_switch_drill_all_pass(self):
        f = ARTIFACTS / "company_v2_mvp_r11_kill_switch_drill.json"
        data = json.loads(f.read_text())
        switches = data.get("switches_verified", [])
        assert len(switches) >= 5, "At least 5 kill switches must be verified"
        for sw in switches:
            assert sw["result"] == "PASS", f"Switch {sw['switch']} not PASS"

    def test_quota_config_correct_values(self):
        f = ARTIFACTS / "company_v2_mvp_r11_quota_configuration.json"
        data = json.loads(f.read_text())
        assert data["quota_settings"]["mvp_daily_quota_per_user"] == 10
        assert data["quota_settings"]["mvp_global_daily_quota"] == 300

    def test_public_registration_disabled_in_invite_config(self):
        f = ARTIFACTS / "company_v2_mvp_r11_invite_configuration.json"
        data = json.loads(f.read_text())
        access = data.get("access_control", {})
        assert access.get("mvp_public_registration_enabled") is False

    def test_runtime_probe_no_drift(self):
        f = ARTIFACTS / "company_v2_mvp_r11_runtime_probe.json"
        data = json.loads(f.read_text())
        assert data["drift_detected"] is False
        assert data["gate_l1_result"] == "PASS"
