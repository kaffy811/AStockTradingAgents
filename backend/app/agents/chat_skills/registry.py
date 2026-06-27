"""
SkillRegistry — Phase C9 (OpenClaw-style Skill Registry).

C6: Basic registry with priority-ordered skill selection.
C9: Spec-aware registry.
    - Loads SkillSpec JSON files on init.
    - Skills with enabled=False are excluded from selection.
    - Skills with unavailable required_tools are marked unavailable.
    - list_skill_specs() returns spec metadata for the discovery API.
    - PlannerExecutor's select_by_name() respects enabled/available.
    - Injecting skill_spec_version into SkillResult.metadata after run().
"""
from __future__ import annotations

import logging

from app.agents.chat_skills.base import BaseSkill, SkillContext, SkillResult
from app.agents.financial_safety_postprocessor import sanitize_financial_answer
from app.agents.chat_skills.spec_loader import (
    check_skill_available,
    load_skill_specs,
    validate_skill_spec,
)

log = logging.getLogger(__name__)


class SkillRegistry:
    def __init__(self, tool_registry=None) -> None:
        self._skills: list[BaseSkill] = []
        self._tool_registry = tool_registry

        # C9: specs dict keyed by skill name
        self._specs: dict[str, dict] = load_skill_specs()

        # C9: availability dict — True if all required_tools exist
        self._available: dict[str, bool] = {}

        # C9: runtime enabled overrides (starts from spec file values)
        self._enabled_overrides: dict[str, bool] = {}

        # Validate all loaded specs (log warnings; never crash)
        for name, spec in self._specs.items():
            ok, errors = validate_skill_spec(spec, tool_registry)
            if not ok:
                log.warning(
                    "SkillRegistry: spec '%s' has validation errors: %s", name, errors
                )
            available = check_skill_available(spec, tool_registry)
            self._available[name] = available
            if not available:
                log.warning(
                    "SkillRegistry: skill '%s' marked unavailable (missing required tools)", name
                )

    # ── Registration ──────────────────────────────────────────────────────────

    def register(self, skill: BaseSkill) -> None:
        self._skills.append(skill)
        self._skills.sort(key=lambda s: s.priority)

        # If no spec loaded for this skill, mark as available (Python-class-only mode)
        if skill.name not in self._available:
            self._available[skill.name] = True

    # ── Listing ───────────────────────────────────────────────────────────────

    def list_skills(self) -> list[BaseSkill]:
        return list(self._skills)

    def list_skill_specs(self) -> list[dict]:
        """
        Return public spec metadata for all registered skills.
        Merges spec file data with runtime enabled/available state.
        Internal implementation details (prompt text, _source_file) are excluded.
        """
        result: list[dict] = []
        for skill in self._skills:
            spec = self._specs.get(skill.name, {})
            result.append({
                "name":             skill.name,
                "display_name":     spec.get("display_name", skill.name),
                "display_name_en":  spec.get("display_name_en", skill.name),
                "description":      spec.get("description", skill.description),
                "version":          spec.get("version", ""),
                "enabled":          self.is_skill_enabled(skill.name),
                "available":        self._available.get(skill.name, True),
                "category":         spec.get("category", "financial_research"),
                "permission_level": spec.get("permission_level", skill.safety_level),
                "required_tools":   spec.get("required_tools", skill.required_tools),
                "optional_tools":   spec.get("optional_tools", getattr(skill, "optional_tools", [])),
                "intent_examples":  spec.get("intent_examples", skill.intent_examples),
                "safety_rules":     spec.get("safety_rules", []),
                # NOT exposing: _source_file, internal prompts, failure_handling detail
            })
        return result

    def get_skill_spec(self, name: str) -> dict | None:
        """Return the raw spec dict for a skill (or None)."""
        return self._specs.get(name)

    # ── Enabled / Available ───────────────────────────────────────────────────

    def is_skill_enabled(self, name: str) -> bool:
        """Return True if the skill is enabled (spec default, overridable at runtime)."""
        if name in self._enabled_overrides:
            return self._enabled_overrides[name]
        spec = self._specs.get(name)
        if spec is not None:
            return bool(spec.get("enabled", True))
        return True  # Python-class-only skills default to enabled

    def is_skill_available(self, name: str) -> bool:
        """Return True if all required_tools are present in ToolRegistry."""
        return self._available.get(name, True)

    def set_skill_enabled(self, name: str, enabled: bool) -> None:
        """
        Runtime toggle for a skill's enabled state.
        This is in-memory only — restarting the server resets to spec file values.
        """
        self._enabled_overrides[name] = enabled
        log.info("SkillRegistry: skill '%s' set enabled=%s", name, enabled)

    # ── Selection ─────────────────────────────────────────────────────────────

    def select_skill(self, message: str, context: SkillContext) -> BaseSkill | None:
        """Return the first enabled+available skill that can handle the message."""
        for skill in self._skills:
            if not self.is_skill_enabled(skill.name):
                continue
            if not self.is_skill_available(skill.name):
                continue
            if skill.can_handle(message, context):
                return skill
        return None

    def select_by_name(self, name: str) -> "BaseSkill | None":
        """
        Return the registered skill with the given name.
        Returns None if disabled, unavailable, or not found.
        """
        for skill in self._skills:
            if skill.name == name:
                if not self.is_skill_enabled(skill.name):
                    log.warning(
                        "SkillRegistry: select_by_name('%s') refused — skill disabled", name
                    )
                    return None
                if not self.is_skill_available(skill.name):
                    log.warning(
                        "SkillRegistry: select_by_name('%s') refused — skill unavailable", name
                    )
                    return None
                return skill
        return None

    # ── Run ───────────────────────────────────────────────────────────────────

    async def run(self, message: str, context: SkillContext) -> SkillResult | None:
        skill = self.select_skill(message, context)
        if skill is None:
            return None
        try:
            result = await skill.run(message, context)
            # C9: inject spec metadata into SkillResult
            spec = self._specs.get(skill.name, {})
            result.metadata = {
                **result.metadata,
                "skill_spec_version": spec.get("version", ""),
                "skill_enabled":      self.is_skill_enabled(skill.name),
                "skill_available":    self.is_skill_available(skill.name),
            }
            # C26: sanitize answer text before returning to orchestrator
            if result.answer:
                result.answer = sanitize_financial_answer(result.answer)
            # C27: enrich data_quality and sources from tool_events
            if result.tool_events:
                from app.agents.answer_metadata import (
                    build_answer_metadata,
                    add_data_boundary_declaration,
                )
                meta = build_answer_metadata(result.tool_events)
                result.metadata["data_quality"] = meta["data_quality"]
                result.metadata["sources_c27"]  = meta["sources"]
                if result.answer:
                    result.answer = add_data_boundary_declaration(
                        result.answer, meta["data_quality"]
                    )
            return result
        except Exception as exc:
            log.exception("SkillRegistry: unexpected error in skill %s", skill.name)
            # C25.11: Domain-owning skills (e.g. report reading) must NOT fall back
            # to the generic answerer — they handle their own error path internally.
            # If such a skill somehow still raises, return a safe SkillResult directly.
            _EXCLUSIVE_SKILLS = {"report_explanation_skill"}
            if skill.name in _EXCLUSIVE_SKILLS:
                return SkillResult(
                    ok=False,
                    skill_name=skill.name,
                    answer=(
                        "报告读取过程中遇到技术问题，请稍后重试。"
                        "\n\n_仅供研究参考，不构成投资建议。_"
                    ),
                    error=str(exc),
                )
            # C14: try DeepSeek-backed fallback before returning an opaque error
            try:
                from app.agents.chat_skills.general_financial_answer_skill import GeneralFinancialAnswerSkill
                fallback = GeneralFinancialAnswerSkill()
                fallback_result = await fallback.run(message, context)
                fallback_result.error = str(exc)
                return fallback_result
            except Exception as fallback_exc:
                log.warning(
                    "SkillRegistry: fallback skill also failed for %s: %s",
                    skill.name, fallback_exc,
                )
                return SkillResult(
                    ok=False,
                    skill_name=skill.name,
                    answer=(
                        "研究数据获取受限，请稍后重试或尝试其他问题。"
                        "\n\n_仅供研究参考，不构成投资建议。_"
                    ),
                    error=str(exc),
                )
