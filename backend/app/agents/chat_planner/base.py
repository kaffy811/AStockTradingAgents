"""
C7 Controlled Planner — data structures.

PlanStep       — a single step in a research plan
PlannerResult  — the plan produced by RuleBasedPlanner
ExecutionResult— the final output after PlannerExecutor runs all steps
"""
from __future__ import annotations

import uuid as _uuid_mod
from dataclasses import dataclass, field


@dataclass
class PlanStep:
    step_id: str
    step_type: str      # "skill" | "action" | "clarification" | "final_summary"
    name: str           # skill name (e.g. "stock_anomaly_skill") or action type
    status: str = "pending"
    # pending | running | completed | failed | waiting_confirmation | skipped
    input_hint: str | None = None
    requires_confirmation: bool = False
    depends_on: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @staticmethod
    def make_id(prefix: str = "step") -> str:
        return f"{prefix}_{_uuid_mod.uuid4().hex[:6]}"


@dataclass
class PlannerResult:
    ok: bool
    intent_type: str   # "anomaly_then_risk" | "report_then_risk" | "watchlist_scan" |
                       # "industry_then_stocks" | "research_then_action" |
                       # "compare_then_report" | "clarification" | "unknown"
    steps: list[PlanStep]
    reason: str | None = None
    error: str | None = None
    safety_flags: list[str] = field(default_factory=list)


@dataclass
class ExecutionResult:
    ok: bool
    answer: str
    tool_events: list = field(default_factory=list)
    cards: list = field(default_factory=list)
    steps: list[dict] = field(default_factory=list)   # serialized step statuses
    metadata: dict = field(default_factory=dict)
    confirmation: dict | None = None
    error: str | None = None
