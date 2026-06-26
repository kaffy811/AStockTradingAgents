"""
C7 PlannerExecutor — executes a PlannerResult step by step.

Responsibilities:
  1. Run skill steps via SkillRegistry.select_by_name()
  2. Merge tool_events and cards from all steps
  3. For action steps: create C5 confirmation (NOT execute directly)
  4. Handle clarification steps inline
  5. Generate a final_summary from aggregated skill results
  6. Return ExecutionResult with full metadata audit trail

Safety rules enforced here:
  - Action steps never execute writes; they only produce a pending confirmation
  - Forbidden financial phrases are stripped from the synthesized answer
  - _DISCLAIMER is always appended
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.agents.chat_confirmation import make_confirmation
from app.agents.chat_planner.base import ExecutionResult, PlannerResult, PlanStep
from app.agents.chat_skills.base import SkillContext, SkillResult, _DISCLAIMER, _extract_stock_hint
from app.agents.chat_events import safe_emit

if TYPE_CHECKING:
    from app.agents.chat_skills.registry import SkillRegistry

log = logging.getLogger(__name__)

_FORBIDDEN_PHRASES = ["买入", "卖出", "持有", "目标价", "必涨", "稳赚", "抄底", "追涨"]


class PlannerExecutor:
    """Executes a PlannerResult produced by RuleBasedPlanner."""

    def __init__(self, skill_registry: "SkillRegistry") -> None:
        self._registry = skill_registry

    async def execute(
        self,
        plan: PlannerResult,
        message: str,
        context: SkillContext,
    ) -> ExecutionResult:
        all_events: list  = []
        all_cards: list   = []
        skill_results: list[SkillResult] = []
        confirmation: dict | None = None
        step_records: list[dict] = []
        skills_used: list[str]   = []
        tools_used: list[str]    = []

        for step in plan.steps:
            record: dict = {
                "step_id":   step.step_id,
                "type":      step.step_type,
                "name":      step.name,
                "status":    "pending",
            }

            if step.step_type == "skill":
                skill = self._registry.select_by_name(step.name)
                if skill is None:
                    step.status = "failed"
                    record["status"] = "failed"
                    record["error"]  = f"Skill '{step.name}' not registered"
                    step_records.append(record)
                    continue

                step.status = "running"
                await safe_emit(context.event_callback, "planner_step_started", {
                    "step_id": step.step_id,
                    "step_type": step.step_type,
                    "name": step.name,
                    "status": "running",
                    "source": "planner_executor",
                })
                try:
                    result = await skill.run(message, context)
                    step.status = "completed" if result.ok else "failed"
                    all_events.extend(result.tool_events)
                    all_cards.extend(result.cards)
                    skill_results.append(result)
                    skills_used.append(step.name)
                    tools_used.extend(e["name"] for e in result.tool_events)
                    await safe_emit(context.event_callback, "planner_step_completed", {
                        "step_id": step.step_id,
                        "step_type": step.step_type,
                        "name": step.name,
                        "status": step.status,
                        "source": "planner_executor",
                    })
                except Exception as exc:
                    log.exception("PlannerExecutor: skill '%s' raised", step.name)
                    step.status = "failed"
                    record["error"] = str(exc)
                    await safe_emit(context.event_callback, "planner_step_completed", {
                        "step_id": step.step_id,
                        "step_type": step.step_type,
                        "name": step.name,
                        "status": "failed",
                        "source": "planner_executor",
                    })

                record["status"] = step.status

            elif step.step_type == "action" and step.requires_confirmation:
                # DO NOT execute — create a pending confirmation only
                action_type = step.metadata.get("action_type", "add_watchlist")
                hint = _extract_stock_hint(message)

                if action_type == "add_watchlist":
                    if not hint:
                        step.status = "skipped"
                        record["status"] = "skipped"
                        record["note"] = "无法识别目标股票，跳过加入自选操作"
                        step_records.append(record)
                        continue
                    stock_desc = (
                        f"**{hint.get('name', hint.get('symbol', '该股票'))}"
                        f"（{hint.get('market', 'CN')}/{hint.get('symbol', '')}）**"
                    )
                    confirmation = make_confirmation(
                        action_type="add_watchlist",
                        text=(
                            f"研究摘要已完成。如你仍希望将 {stock_desc} 加入自选股，"
                            "请确认下方操作。"
                        ),
                        params=hint,
                    )

                elif action_type == "create_compare":
                    confirmation = make_confirmation(
                        action_type="create_compare",
                        text="请确认发起对比，或说明要为哪只股票生成报告。",
                        params={},
                    )

                step.status = "waiting_confirmation"
                record["status"] = "waiting_confirmation"

            elif step.step_type == "clarification":
                step.status = "completed"
                record["status"] = "completed"
                record["reason"] = step.metadata.get("reason", "需要用户补充信息")

            elif step.step_type == "final_summary":
                # Synthesized below — mark as completed
                step.status = "completed"
                record["status"] = "completed"

            step_records.append(record)

        # Generate synthesized answer
        answer = self._synthesize(skill_results, plan, confirmation)

        # Safety: strip forbidden phrases from answer
        for phrase in _FORBIDDEN_PHRASES:
            answer = answer.replace(phrase, "")

        return ExecutionResult(
            ok=True,
            answer=answer,
            tool_events=all_events,
            cards=all_cards,
            steps=step_records,
            confirmation=confirmation,
            metadata={
                "planner_used":     True,
                "plan_intent_type": plan.intent_type,
                "steps":            step_records,
                "skills_used":      list(dict.fromkeys(skills_used)),   # preserve order, dedupe
                "tools_used":       list(dict.fromkeys(tools_used)),
                "safety_flags":     list(plan.safety_flags),
            },
        )

    # ── Answer synthesis ──────────────────────────────────────────────────────

    def _synthesize(
        self,
        skill_results: list[SkillResult],
        plan: PlannerResult,
        confirmation: dict | None,
    ) -> str:
        if not skill_results:
            if plan.intent_type == "clarification":
                reason = (
                    plan.steps[0].metadata.get("reason", "")
                    if plan.steps else ""
                )
                return (
                    f"需要更多信息才能继续：{reason}\n\n"
                    "请告诉我具体的股票代码或研究目标，例如：688146、中船特气。"
                    + _DISCLAIMER
                )
            return "处理请求时未获取到有效数据，请稍后重试。" + _DISCLAIMER

        label = _INTENT_LABELS.get(plan.intent_type, plan.intent_type)
        parts: list[str] = [f"## 多步骤研究摘要（{label}）\n"]

        # ── 综合结论：first skill ─────────────────────────────────────────────
        parts.append("### 综合结论")
        first_lines = _extract_body_lines(skill_results[0].answer, limit=4)
        parts.extend(first_lines or ["（数据获取中）"])
        parts.append("")

        # ── 主要风险：second skill (if exists) ───────────────────────────────
        if len(skill_results) >= 2:
            parts.append("### 主要风险")
            risk_lines = _extract_body_lines(skill_results[1].answer, limit=3)
            parts.extend(risk_lines or ["（风险数据不足）"])
            parts.append("")

        # ── 后续观察：from all skills ─────────────────────────────────────────
        parts.append("### 后续观察")
        obs = _extract_obs_lines(skill_results)
        if obs:
            parts.extend(obs[:3])
        else:
            parts.append("1. 建议结合基本面进一步核查上述发现")
        parts.append("")

        # ── Pending action prompt ─────────────────────────────────────────────
        if confirmation:
            parts.append("### 待确认操作")
            parts.append(confirmation.get("text", ""))
            parts.append("")

        # ── Clarification prompt from plan steps ─────────────────────────────
        clarify_steps = [
            s for s in plan.steps
            if s.step_type == "clarification"
        ]
        if clarify_steps:
            reason = clarify_steps[0].metadata.get("reason", "")
            parts.append(f"> **需要补充信息：** {reason}")
            parts.append("")

        parts.append(_DISCLAIMER.strip())
        return "\n".join(parts)


# ── Module helpers ─────────────────────────────────────────────────────────────

_INTENT_LABELS: dict[str, str] = {
    "anomaly_then_risk":     "异动分析 + 风险研究",
    "report_then_risk":      "报告解读 + 风险研究",
    "watchlist_scan":        "自选股巡检",
    "industry_then_stocks":  "行业热点 + 个股研究",
    "research_then_action":  "研究摘要 + 确认操作",
    "compare_then_report":   "股票对比",
    "clarification":         "需要澄清",
}


def _extract_body_lines(text: str, limit: int = 4) -> list[str]:
    """Extract non-header, non-disclaimer body lines from a skill answer."""
    lines: list[str] = []
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        if line.startswith("_") and "仅供研究" in line:
            continue
        lines.append(line)
        if len(lines) >= limit:
            break
    return lines


def _extract_obs_lines(skill_results: list[SkillResult]) -> list[str]:
    """Find numbered observation lines from skill answers."""
    obs: list[str] = []
    for sr in skill_results:
        capturing = False
        for raw in sr.answer.split("\n"):
            line = raw.strip()
            if "后续观察" in line or "后续关注" in line:
                capturing = True
                continue
            if capturing and (line.startswith("1.") or line.startswith("2.") or line.startswith("3.")):
                obs.append(line)
            elif capturing and line.startswith("#"):
                break
    return obs
