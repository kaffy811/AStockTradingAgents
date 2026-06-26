"""
Tests for Phase C9 SkillSpec Loader.

Coverage:
  - load_skill_specs() loads all 6 JSON files
  - Each spec has required fields
  - load_skill_spec(name) returns correct spec or None
  - validate_skill_spec: valid spec returns ok=True, no errors
  - validate_skill_spec: missing field returns error
  - validate_skill_spec: invalid permission_level returns error
  - validate_skill_spec: missing required_tool marks unavailable
  - check_skill_available: True when tools exist, False when missing
  - SPECS_DIR exists
  - Malformed JSON is skipped gracefully (no crash)
  - Unknown spec name returns None
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.agents.chat_skills.spec_loader import (
    ALLOWED_PERMISSION_LEVELS,
    REQUIRED_SPEC_FIELDS,
    SPECS_DIR,
    check_skill_available,
    load_skill_spec,
    load_skill_specs,
    validate_skill_spec,
)


# ── SPECS_DIR existence ────────────────────────────────────────────────────────

def test_specs_dir_exists():
    assert SPECS_DIR.is_dir(), f"specs/ directory should exist at {SPECS_DIR}"


# ── load_skill_specs ───────────────────────────────────────────────────────────

def test_load_skill_specs_returns_7():
    """6 specific-intent skills + 1 general fallback (C15)."""
    specs = load_skill_specs()
    assert len(specs) == 7, f"Expected 7 specs, got {len(specs)}: {list(specs.keys())}"


def test_load_skill_specs_contains_all_names():
    specs = load_skill_specs()
    expected = {
        "stock_anomaly_skill",
        "risk_first_skill",
        "news_catalyst_skill",
        "watchlist_review_skill",
        "industry_hotspot_skill",
        "report_explanation_skill",
        "general_financial_answer_skill",
    }
    assert expected == set(specs.keys())


def test_load_skill_specs_returns_dict():
    specs = load_skill_specs()
    assert isinstance(specs, dict)
    for name, spec in specs.items():
        assert isinstance(spec, dict)
        assert spec.get("name") == name


# ── Required spec fields ───────────────────────────────────────────────────────

@pytest.mark.parametrize("spec_name", [
    "stock_anomaly_skill",
    "risk_first_skill",
    "news_catalyst_skill",
    "watchlist_review_skill",
    "industry_hotspot_skill",
    "report_explanation_skill",
])
def test_spec_has_required_fields(spec_name):
    specs = load_skill_specs()
    spec = specs[spec_name]
    for field in REQUIRED_SPEC_FIELDS:
        assert field in spec, f"spec '{spec_name}' missing required field '{field}'"


@pytest.mark.parametrize("spec_name", [
    "stock_anomaly_skill",
    "risk_first_skill",
    "news_catalyst_skill",
    "watchlist_review_skill",
    "industry_hotspot_skill",
    "report_explanation_skill",
])
def test_spec_enabled_true(spec_name):
    """All 6 C9 specs should ship with enabled=True."""
    specs = load_skill_specs()
    assert specs[spec_name]["enabled"] is True


@pytest.mark.parametrize("spec_name", [
    "stock_anomaly_skill",
    "risk_first_skill",
    "news_catalyst_skill",
    "watchlist_review_skill",
    "industry_hotspot_skill",
    "report_explanation_skill",
])
def test_spec_permission_level_valid(spec_name):
    specs = load_skill_specs()
    perm = specs[spec_name]["permission_level"]
    assert perm in ALLOWED_PERMISSION_LEVELS


@pytest.mark.parametrize("spec_name", [
    "stock_anomaly_skill",
    "risk_first_skill",
    "news_catalyst_skill",
    "watchlist_review_skill",
    "industry_hotspot_skill",
    "report_explanation_skill",
])
def test_spec_has_safety_rules(spec_name):
    specs = load_skill_specs()
    rules = specs[spec_name]["safety_rules"]
    assert isinstance(rules, list)
    assert len(rules) > 0


@pytest.mark.parametrize("spec_name", [
    "stock_anomaly_skill",
    "risk_first_skill",
    "news_catalyst_skill",
    "watchlist_review_skill",
    "industry_hotspot_skill",
    "report_explanation_skill",
])
def test_spec_version_is_c9(spec_name):
    specs = load_skill_specs()
    assert specs[spec_name].get("version") == "c9_v1"


# ── load_skill_spec(name) ──────────────────────────────────────────────────────

def test_load_skill_spec_by_name():
    spec = load_skill_spec("stock_anomaly_skill")
    assert spec is not None
    assert spec["name"] == "stock_anomaly_skill"


def test_load_skill_spec_unknown_returns_none():
    assert load_skill_spec("nonexistent_skill") is None


# ── validate_skill_spec ────────────────────────────────────────────────────────

def test_validate_valid_spec():
    spec = load_skill_spec("stock_anomaly_skill")
    ok, errors = validate_skill_spec(spec)
    assert ok is True
    assert errors == []


def test_validate_missing_required_field():
    spec = {
        "name": "test_skill",
        "enabled": True,
        "required_tools": [],
        # missing permission_level and safety_rules
    }
    ok, errors = validate_skill_spec(spec)
    assert ok is False
    assert any("permission_level" in e or "safety_rules" in e for e in errors)


def test_validate_invalid_permission_level():
    spec = {
        "name": "test",
        "enabled": True,
        "required_tools": [],
        "permission_level": "admin_override",  # invalid
        "safety_rules": ["no_trading_advice"],
    }
    ok, errors = validate_skill_spec(spec)
    assert ok is False
    assert any("permission_level" in e for e in errors)


def test_validate_enabled_not_bool():
    spec = {
        "name": "test",
        "enabled": "yes",  # should be bool
        "required_tools": [],
        "permission_level": "read_only",
        "safety_rules": ["no_trading_advice"],
    }
    ok, errors = validate_skill_spec(spec)
    assert ok is False
    assert any("enabled" in e for e in errors)


def test_validate_missing_required_tool_marks_error():
    """When tool_registry provided and tool missing, errors should include tool name."""
    registry = MagicMock()
    registry._tools = {}  # no tools registered

    spec = {
        "name": "test",
        "enabled": True,
        "required_tools": ["missing_tool"],
        "permission_level": "read_only",
        "safety_rules": ["no_trading_advice"],
    }
    ok, errors = validate_skill_spec(spec, tool_registry=registry)
    assert ok is False
    assert any("missing_tool" in e for e in errors)


def test_validate_tools_present_ok():
    registry = MagicMock()
    registry._tools = {"resolve_stock_tool": object(), "get_quote_tool": object()}

    spec = {
        "name": "test",
        "enabled": True,
        "required_tools": ["resolve_stock_tool", "get_quote_tool"],
        "permission_level": "read_only",
        "safety_rules": ["no_trading_advice"],
    }
    ok, errors = validate_skill_spec(spec, tool_registry=registry)
    assert ok is True


# ── check_skill_available ──────────────────────────────────────────────────────

def test_check_skill_available_true():
    registry = MagicMock()
    registry._tools = {"tool_a": object(), "tool_b": object()}
    spec = {"required_tools": ["tool_a", "tool_b"]}
    assert check_skill_available(spec, registry) is True


def test_check_skill_available_false():
    registry = MagicMock()
    registry._tools = {"tool_a": object()}
    spec = {"required_tools": ["tool_a", "missing_tool"]}
    assert check_skill_available(spec, registry) is False


def test_check_skill_available_no_registry():
    """Without registry, always available."""
    spec = {"required_tools": ["anything"]}
    assert check_skill_available(spec, None) is True


# ── Malformed JSON graceful handling ──────────────────────────────────────────

def test_load_skill_specs_skips_malformed_json():
    """A malformed JSON file in specs/ should be skipped, not crash."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        # Write a valid spec
        (tmp_path / "valid.json").write_text(json.dumps({
            "name": "valid_skill",
            "enabled": True,
            "required_tools": [],
            "permission_level": "read_only",
            "safety_rules": ["no_trading_advice"],
        }))
        # Write malformed JSON
        (tmp_path / "broken.json").write_text("{invalid json}")

        with patch("app.agents.chat_skills.spec_loader.SPECS_DIR", tmp_path):
            specs = load_skill_specs()

        assert "valid_skill" in specs
        # broken.json is skipped
        assert len(specs) == 1
