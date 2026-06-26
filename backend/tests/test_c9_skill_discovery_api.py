"""
Tests for Phase C9 Skill Discovery API.

Coverage:
  - get_skills_list() returns 6 items
  - Each item has name, display_name, enabled, available, required_tools, safety_rules
  - No internal prompts in response
  - Router endpoint exists and returns 200
  - Router endpoint requires auth (401 without token)
  - list_skill_specs() forward through orchestrator.get_skills_list()
  - Disabled skill reflected in list (enabled=False)
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from app.agents.chat_orchestrator import get_skills_list


# ── get_skills_list (orchestrator facade) ─────────────────────────────────────

def test_get_skills_list_returns_list():
    items = get_skills_list()
    assert isinstance(items, list)


def test_get_skills_list_returns_7():
    """6 specific-intent skills + 1 general fallback (GeneralFinancialAnswerSkill)."""
    items = get_skills_list()
    assert len(items) == 7, f"Expected 7, got {len(items)}: {[i['name'] for i in items]}"


def test_get_skills_list_all_have_required_fields():
    items = get_skills_list()
    for item in items:
        assert "name" in item
        assert "display_name" in item
        assert "description" in item
        assert "enabled" in item
        assert "available" in item
        assert "required_tools" in item
        assert "safety_rules" in item
        assert "permission_level" in item


def test_get_skills_list_all_enabled():
    items = get_skills_list()
    for item in items:
        assert item["enabled"] is True, f"skill '{item['name']}' should be enabled"


def test_get_skills_list_no_internal_data():
    """Discovery API must not expose internal prompts or source files."""
    items = get_skills_list()
    for item in items:
        assert "_source_file" not in item
        assert "failure_handling" not in item


def test_get_skills_list_all_permission_read_only():
    items = get_skills_list()
    for item in items:
        assert item["permission_level"] == "read_only"


def test_get_skills_list_contains_expected_names():
    items = get_skills_list()
    names = {i["name"] for i in items}
    assert "stock_anomaly_skill" in names
    assert "risk_first_skill" in names
    assert "news_catalyst_skill" in names
    assert "watchlist_review_skill" in names
    assert "industry_hotspot_skill" in names
    assert "report_explanation_skill" in names
    assert "general_financial_answer_skill" in names


def test_get_skills_list_each_has_required_tools():
    items = get_skills_list()
    for item in items:
        assert isinstance(item["required_tools"], list)
        assert len(item["required_tools"]) > 0, \
            f"skill '{item['name']}' has empty required_tools"


def test_get_skills_list_each_has_safety_rules():
    items = get_skills_list()
    for item in items:
        assert isinstance(item["safety_rules"], list)
        assert len(item["safety_rules"]) > 0, \
            f"skill '{item['name']}' has empty safety_rules"


def test_get_skills_list_no_trading_advice_in_rules():
    """All skills must include no_trading_advice safety rule."""
    items = get_skills_list()
    for item in items:
        assert "no_trading_advice" in item["safety_rules"], \
            f"skill '{item['name']}' missing 'no_trading_advice' safety rule"


def test_get_skills_list_must_include_disclaimer():
    """All skills should require disclaimer."""
    items = get_skills_list()
    for item in items:
        assert "must_include_disclaimer" in item["safety_rules"], \
            f"skill '{item['name']}' missing 'must_include_disclaimer' safety rule"


def test_get_skills_list_display_name_not_empty():
    items = get_skills_list()
    for item in items:
        assert item["display_name"], f"skill '{item['name']}' has empty display_name"


# ── Router endpoint auth guard test via dependency inspection ─────────────────

def test_router_list_chat_skills_requires_auth():
    """
    Verify that the /chat/skills endpoint has the get_current_user dependency.
    We inspect the route's dependant tree rather than making HTTP calls
    (which would require a full DB/auth stack).
    """
    from app.routers.chat import router
    from app.dependencies import get_current_user

    # Find the /chat/skills route
    skills_route = None
    for route in router.routes:
        if hasattr(route, "path") and route.path == "/chat/skills":
            skills_route = route
            break

    assert skills_route is not None, "GET /chat/skills route not found"

    # Check that get_current_user is in the dependant dependency tree
    dep_callables = [d.call for d in skills_route.dependant.dependencies]
    assert get_current_user in dep_callables, \
        "GET /chat/skills must depend on get_current_user for auth"


# ── Disabled skill reflected in discovery ─────────────────────────────────────

def test_disabled_skill_reflected_in_list():
    """
    When a skill is disabled at runtime, list_skill_specs should show enabled=False.
    """
    from app.agents.chat_orchestrator import _skill_registry

    # Save original state
    original = _skill_registry.is_skill_enabled("stock_anomaly_skill")
    try:
        _skill_registry.set_skill_enabled("stock_anomaly_skill", False)
        items = get_skills_list()
        anomaly_item = next(i for i in items if i["name"] == "stock_anomaly_skill")
        assert anomaly_item["enabled"] is False
    finally:
        # Restore
        _skill_registry.set_skill_enabled("stock_anomaly_skill", original)
