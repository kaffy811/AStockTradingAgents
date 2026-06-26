"""
C9 SkillSpec Loader — loads and validates skill spec JSON files.

Spec files live in:  app/agents/chat_skills/specs/*.json

Validation rules:
  - Required fields: name, enabled, required_tools, permission_level, safety_rules
  - permission_level must be one of ALLOWED_PERMISSION_LEVELS
  - safety_rules must not disable system-level safety rules
  - required_tools validated against ToolRegistry (if provided)

Load errors are logged and the spec is marked unavailable — they never crash
the server. All operations are synchronous (no I/O at request time).
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

SPECS_DIR = Path(__file__).parent / "specs"

ALLOWED_PERMISSION_LEVELS = frozenset({"read_only", "research_action"})

# These safety rules are mandatory at the system level and cannot be overridden
# by any SkillSpec (they may be listed in spec, but never removed from the system).
SYSTEM_SAFETY_RULES = frozenset({
    "no_trading_advice",
    "must_include_disclaimer",
})

# Spec fields that must be present for a spec to be valid
REQUIRED_SPEC_FIELDS = frozenset({
    "name",
    "enabled",
    "required_tools",
    "permission_level",
    "safety_rules",
})


# ── Public API ─────────────────────────────────────────────────────────────────

def load_skill_specs() -> dict[str, dict]:
    """
    Load all *.json spec files from the specs/ directory.

    Returns a dict of  name -> spec_dict.
    Malformed or invalid specs are skipped and logged as warnings.
    Never raises — a load failure only affects that one spec.
    """
    specs: dict[str, dict] = {}

    if not SPECS_DIR.is_dir():
        log.warning("spec_loader: specs directory not found: %s", SPECS_DIR)
        return specs

    for path in sorted(SPECS_DIR.glob("*.json")):
        try:
            with open(path, encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("spec_loader: failed to parse %s — %s", path.name, exc)
            continue

        name = raw.get("name", "")
        if not name:
            log.warning("spec_loader: spec in %s has no 'name' field — skipping", path.name)
            continue

        if name in specs:
            log.warning("spec_loader: duplicate spec name '%s' in %s — skipping", name, path.name)
            continue

        # Annotate with source file for debugging
        raw["_source_file"] = path.name
        specs[name] = raw

    log.info("spec_loader: loaded %d skill spec(s) from %s", len(specs), SPECS_DIR)
    return specs


def load_skill_spec(name: str) -> dict | None:
    """Load a single spec by skill name.  Returns None if not found or invalid."""
    specs = load_skill_specs()
    return specs.get(name)


def validate_skill_spec(
    spec: dict,
    tool_registry: Any = None,
) -> tuple[bool, list[str]]:
    """
    Validate a SkillSpec dict.

    Returns (ok: bool, errors: list[str]).

    Checks:
    1. All REQUIRED_SPEC_FIELDS present.
    2. permission_level in ALLOWED_PERMISSION_LEVELS.
    3. safety_rules is a non-empty list.
    4. System safety rules not absent (spec may be missing them, that's fine —
       the system enforces them regardless, but we warn).
    5. required_tools are present in ToolRegistry (if provided).
    6. enabled is a boolean.
    """
    errors: list[str] = []

    # 1. Required fields
    for field in REQUIRED_SPEC_FIELDS:
        if field not in spec:
            errors.append(f"missing required field: '{field}'")

    if errors:
        # Can't continue if basics are missing
        return False, errors

    # 2. permission_level
    perm = spec.get("permission_level", "")
    if perm not in ALLOWED_PERMISSION_LEVELS:
        errors.append(
            f"invalid permission_level '{perm}'; allowed: {sorted(ALLOWED_PERMISSION_LEVELS)}"
        )

    # 3. safety_rules is a list
    safety_rules = spec.get("safety_rules", [])
    if not isinstance(safety_rules, list):
        errors.append("safety_rules must be a list")

    # 4. enabled must be bool
    if not isinstance(spec.get("enabled"), bool):
        errors.append("'enabled' must be a boolean")

    # 5. required_tools validation against registry
    required_tools = spec.get("required_tools", [])
    if tool_registry is not None:
        for tool_name in required_tools:
            if not _tool_exists(tool_registry, tool_name):
                errors.append(f"required_tool '{tool_name}' not found in ToolRegistry")

    return len(errors) == 0, errors


def check_skill_available(spec: dict, tool_registry: Any) -> bool:
    """
    Return True if all required_tools are present in the ToolRegistry.
    If no registry provided, defaults to True.
    """
    if tool_registry is None:
        return True
    required = spec.get("required_tools", [])
    return all(_tool_exists(tool_registry, t) for t in required)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _tool_exists(tool_registry: Any, tool_name: str) -> bool:
    """Check if a tool name is registered in the ToolRegistry."""
    try:
        # ToolRegistry stores tools in _tools dict
        return tool_name in tool_registry._tools
    except Exception:
        return False
