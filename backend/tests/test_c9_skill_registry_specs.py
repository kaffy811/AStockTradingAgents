"""
Tests for Phase C9 SkillRegistry spec-awareness.

Coverage:
  - list_skill_specs() returns 6 items
  - Each item has name, display_name, enabled, available, required_tools, safety_rules
  - enabled=False skill excluded from select_skill
  - disabled skill excluded from select_by_name (returns None)
  - set_skill_enabled runtime toggle works
  - SkillResult.metadata contains skill_spec_version after run()
  - unavailable skill excluded from selection
  - C6 backward compat: register/list_skills/run all still work
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.agents.chat_skills.base import SkillContext, SkillResult
from app.agents.chat_skills.registry import SkillRegistry
from app.agents.chat_skills.stock_anomaly_skill import StockAnomalySkill
from app.agents.chat_skills.risk_first_skill import RiskFirstSkill
from app.agents.chat_skills.news_catalyst_skill import NewsCatalystSkill
from app.agents.chat_skills.watchlist_review_skill import WatchlistReviewSkill
from app.agents.chat_skills.industry_hotspot_skill import IndustryHotspotSkill
from app.agents.chat_skills.report_explanation_skill import ReportExplanationSkill


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_registry(tool_registry=None) -> SkillRegistry:
    sreg = SkillRegistry(tool_registry=tool_registry)
    for skill in [
        ReportExplanationSkill(),
        WatchlistReviewSkill(),
        IndustryHotspotSkill(),
        RiskFirstSkill(),
        StockAnomalySkill(),
        NewsCatalystSkill(),
    ]:
        sreg.register(skill)
    return sreg


def _make_context() -> SkillContext:
    ctx = MagicMock(spec=SkillContext)
    ctx.tool_registry = MagicMock()
    ctx.db = AsyncMock()
    ctx.user_id = "user-123"
    return ctx


# ── list_skill_specs ───────────────────────────────────────────────────────────

def test_list_skill_specs_returns_6():
    sreg = _make_registry()
    specs = sreg.list_skill_specs()
    assert len(specs) == 6


def test_list_skill_specs_public_fields():
    sreg = _make_registry()
    for spec in sreg.list_skill_specs():
        assert "name" in spec
        assert "display_name" in spec
        assert "description" in spec
        assert "enabled" in spec
        assert "available" in spec
        assert "required_tools" in spec
        assert "safety_rules" in spec
        assert "permission_level" in spec


def test_list_skill_specs_no_internal_fields():
    """Discovery API should not expose internal implementation details."""
    sreg = _make_registry()
    for spec in sreg.list_skill_specs():
        assert "_source_file" not in spec
        assert "failure_handling" not in spec  # internal


def test_list_skill_specs_all_enabled_by_default():
    sreg = _make_registry()
    for spec in sreg.list_skill_specs():
        assert spec["enabled"] is True


# ── is_skill_enabled / set_skill_enabled ──────────────────────────────────────

def test_is_skill_enabled_default_true():
    sreg = _make_registry()
    assert sreg.is_skill_enabled("stock_anomaly_skill") is True


def test_set_skill_enabled_false():
    sreg = _make_registry()
    sreg.set_skill_enabled("stock_anomaly_skill", False)
    assert sreg.is_skill_enabled("stock_anomaly_skill") is False


def test_set_skill_enabled_re_enable():
    sreg = _make_registry()
    sreg.set_skill_enabled("stock_anomaly_skill", False)
    sreg.set_skill_enabled("stock_anomaly_skill", True)
    assert sreg.is_skill_enabled("stock_anomaly_skill") is True


# ── select_skill respects enabled ─────────────────────────────────────────────

def test_select_skill_skips_disabled():
    sreg = _make_registry()
    # Disable the StockAnomalySkill which handles "688146 异动" pattern
    sreg.set_skill_enabled("stock_anomaly_skill", False)
    ctx = _make_context()
    result = sreg.select_skill("中船特气最近为什么涨这么多", ctx)
    # stock_anomaly_skill disabled; should not be selected
    if result is not None:
        assert result.name != "stock_anomaly_skill"


def test_select_skill_returns_enabled_skill():
    sreg = _make_registry()
    ctx = _make_context()
    skill = sreg.select_skill("中船特气最近为什么涨这么多", ctx)
    assert skill is not None
    assert skill.name == "stock_anomaly_skill"
    assert sreg.is_skill_enabled(skill.name) is True


# ── select_by_name respects enabled ───────────────────────────────────────────

def test_select_by_name_disabled_returns_none():
    sreg = _make_registry()
    sreg.set_skill_enabled("stock_anomaly_skill", False)
    result = sreg.select_by_name("stock_anomaly_skill")
    assert result is None


def test_select_by_name_enabled_returns_skill():
    sreg = _make_registry()
    result = sreg.select_by_name("stock_anomaly_skill")
    assert result is not None
    assert result.name == "stock_anomaly_skill"


def test_select_by_name_unknown_returns_none():
    sreg = _make_registry()
    assert sreg.select_by_name("nonexistent_skill") is None


# ── unavailable skill ─────────────────────────────────────────────────────────

def test_unavailable_skill_excluded_from_select_by_name():
    sreg = _make_registry()
    # Manually mark as unavailable (simulates missing required tool at init)
    sreg._available["stock_anomaly_skill"] = False
    result = sreg.select_by_name("stock_anomaly_skill")
    assert result is None


def test_unavailable_skill_excluded_from_select_skill():
    sreg = _make_registry()
    sreg._available["stock_anomaly_skill"] = False
    ctx = _make_context()
    result = sreg.select_skill("中船特气最近为什么涨这么多", ctx)
    if result is not None:
        assert result.name != "stock_anomaly_skill"


# ── skill_spec_version in SkillResult.metadata ────────────────────────────────

@pytest.mark.asyncio
async def test_run_injects_skill_spec_version():
    """After registry.run(), SkillResult.metadata should contain skill_spec_version."""
    sreg = _make_registry()

    # Mock the actual skill.run() to return a minimal SkillResult
    original_run = StockAnomalySkill.run
    async def mock_run(self, message, context):
        return SkillResult(
            ok=True,
            skill_name=self.name,
            answer="mock answer _仅供研究参考，不构成投资建议。_",
        )

    StockAnomalySkill.run = mock_run
    try:
        ctx = _make_context()
        result = await sreg.run("中船特气最近为什么涨这么多", ctx)
        assert result is not None
        assert "skill_spec_version" in result.metadata
        assert result.metadata["skill_spec_version"] == "c9_v1"
        assert result.metadata["skill_enabled"] is True
        assert result.metadata["skill_available"] is True
    finally:
        StockAnomalySkill.run = original_run


@pytest.mark.asyncio
async def test_run_returns_none_for_disabled_skill():
    sreg = _make_registry()
    # Disable ALL skills
    for skill in sreg.list_skills():
        sreg.set_skill_enabled(skill.name, False)
    ctx = _make_context()
    result = await sreg.run("中船特气为什么涨", ctx)
    assert result is None


# ── C6 backward compat: list_skills ──────────────────────────────────────────

def test_list_skills_returns_all_6():
    sreg = _make_registry()
    skills = sreg.list_skills()
    assert len(skills) == 6


def test_list_skills_sorted_by_priority():
    sreg = _make_registry()
    skills = sreg.list_skills()
    priorities = [s.priority for s in skills]
    assert priorities == sorted(priorities)


# ── get_skill_spec ─────────────────────────────────────────────────────────────

def test_get_skill_spec_returns_dict():
    sreg = _make_registry()
    spec = sreg.get_skill_spec("stock_anomaly_skill")
    assert spec is not None
    assert spec["name"] == "stock_anomaly_skill"


def test_get_skill_spec_unknown_returns_none():
    sreg = _make_registry()
    assert sreg.get_skill_spec("unknown") is None
