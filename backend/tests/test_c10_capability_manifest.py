"""
test_c10_capability_manifest.py — Phase C10 Capability Manifest validation tests.

Validates that:
1. Both manifest files exist and are parseable
2. Manifest JSON matches expected capability counts
3. All declared tools exist in ToolRegistry
4. All declared skills have corresponding Python files and JSON specs
5. Manifest version matches SkillSpec version
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

DOCS_DIR = Path(__file__).parent.parent.parent / "docs"
MANIFEST_MD = DOCS_DIR / "chat_agent_capability_manifest.md"
MANIFEST_JSON = DOCS_DIR / "chat_agent_capability_manifest.json"
SPECS_DIR = Path(__file__).parent.parent / "app" / "agents" / "chat_skills" / "specs"
SKILLS_DIR = Path(__file__).parent.parent / "app" / "agents" / "chat_skills"


# ---------------------------------------------------------------------------
# Section 1: File existence
# ---------------------------------------------------------------------------

class TestManifestFileExistence:

    def test_manifest_md_exists(self):
        """Markdown manifest file must exist."""
        assert MANIFEST_MD.exists(), f"Missing: {MANIFEST_MD}"

    def test_manifest_json_exists(self):
        """JSON manifest file must exist."""
        assert MANIFEST_JSON.exists(), f"Missing: {MANIFEST_JSON}"

    def test_manifest_md_nonempty(self):
        """Markdown manifest must not be empty."""
        assert MANIFEST_MD.stat().st_size > 500

    def test_manifest_json_valid_json(self):
        """JSON manifest must parse without errors."""
        with open(MANIFEST_JSON) as f:
            data = json.load(f)
        assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# Section 2: JSON manifest content
# ---------------------------------------------------------------------------

class TestManifestJSONContent:

    @pytest.fixture(scope="class")
    def manifest(self):
        with open(MANIFEST_JSON) as f:
            return json.load(f)

    def test_manifest_has_version(self, manifest):
        assert "version" in manifest
        assert manifest["version"].startswith("c")

    def test_manifest_has_status(self, manifest):
        assert "status" in manifest

    def test_manifest_tools_count(self, manifest):
        """Manifest declares 9 read-only tools."""
        assert manifest["tools"]["count"] == 9

    def test_manifest_action_count(self, manifest):
        """Manifest declares 3 action tools."""
        assert manifest["tools"]["action_count"] == 3

    def test_manifest_skills_count(self, manifest):
        """Manifest declares 6 skills."""
        assert manifest["skills"]["count"] == 6

    def test_manifest_skills_spec_version(self, manifest):
        """Manifest skill spec version is c9_v1."""
        assert manifest["skills"]["spec_version"] == "c9_v1"

    def test_manifest_planner_compound_intents(self, manifest):
        """Manifest declares 6 compound intents."""
        assert manifest["planner"]["compound_intent_count"] == 6

    def test_manifest_planner_max_steps(self, manifest):
        """Manifest declares MAX_STEPS = 5."""
        assert manifest["planner"]["max_steps"] == 5

    def test_manifest_i18n_locales(self, manifest):
        """Manifest declares 6 locales."""
        assert len(manifest["i18n"]["locales"]) == 6

    def test_manifest_safety_disclaimer_present(self, manifest):
        """Manifest has disclaimer text."""
        assert "不构成投资建议" in manifest["safety"]["disclaimer_text"]

    def test_manifest_trading_patterns_count(self, manifest):
        """Manifest declares 9 trading-blocked patterns."""
        assert manifest["safety"]["trading_guard"]["pattern_count"] == 9

    def test_manifest_api_endpoints_count(self, manifest):
        """Manifest declares 7 API endpoints."""
        assert len(manifest["api"]["endpoints"]) == 7

    def test_manifest_all_tools_have_name(self, manifest):
        """All tool items have a 'name' field."""
        for item in manifest["tools"]["items"]:
            assert "name" in item
            assert item["name"]

    def test_manifest_all_skills_have_required_tools(self, manifest):
        """All skill items declare required_tools."""
        for item in manifest["skills"]["items"]:
            assert "required_tools" in item
            assert len(item["required_tools"]) >= 1


# ---------------------------------------------------------------------------
# Section 3: Cross-validate manifest against actual codebase
# ---------------------------------------------------------------------------

class TestManifestCodebaseAlignment:

    def test_spec_files_match_manifest_count(self):
        """Number of spec JSON files: 6 specific-intent + 1 general fallback (C15)."""
        spec_files = list(SPECS_DIR.glob("*.json"))
        assert len(spec_files) == 7, f"Expected 7 spec files, found {len(spec_files)}"

    def test_declared_skills_have_spec_files(self):
        """All 6 skill names from manifest have corresponding spec JSON files."""
        expected_skill_names = [
            "stock_anomaly",
            "risk_first",
            "news_catalyst",
            "watchlist_review",
            "industry_hotspot",
            "report_explanation",
        ]
        for name in expected_skill_names:
            spec_path = SPECS_DIR / f"{name}.json"
            assert spec_path.exists(), f"Missing spec: {spec_path}"

    def test_declared_skills_have_python_files(self):
        """All 6 skill names have corresponding Python skill files."""
        expected_skill_files = [
            "stock_anomaly_skill.py",
            "risk_first_skill.py",
            "news_catalyst_skill.py",
            "watchlist_review_skill.py",
            "industry_hotspot_skill.py",
            "report_explanation_skill.py",
        ]
        for fname in expected_skill_files:
            py_path = SKILLS_DIR / fname
            assert py_path.exists(), f"Missing skill file: {py_path}"

    def test_spec_files_load_as_valid_json(self):
        """All spec files load without JSON errors."""
        for spec_file in SPECS_DIR.glob("*.json"):
            with open(spec_file) as f:
                data = json.load(f)
            assert "name" in data, f"{spec_file.name} missing 'name'"
            assert "enabled" in data, f"{spec_file.name} missing 'enabled'"

    def test_tool_registry_has_nine_tools(self):
        """ToolRegistry initializes with at least 9 tools (10 after Phase 2E-4 GetIndustryNewsTool)."""
        from app.agents.chat_orchestrator import _registry
        assert len(_registry._tools) >= 9

    def test_skill_registry_has_seven_skills(self):
        """SkillRegistry has 7 skills: 6 specific-intent + 1 general fallback (C15)."""
        from app.agents.chat_orchestrator import _skill_registry
        assert len(_skill_registry.list_skills()) == 7

    def test_readiness_checklist_exists(self):
        """Readiness checklist document must exist."""
        checklist = DOCS_DIR / "chat_agent_readiness_checklist.md"
        assert checklist.exists(), f"Missing: {checklist}"

    def test_evaluation_report_exists(self):
        """Evaluation report document must exist."""
        report = DOCS_DIR / "chat_agent_evaluation_report.md"
        assert report.exists(), f"Missing: {report}"
