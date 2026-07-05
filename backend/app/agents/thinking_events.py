"""
Thinking Events — C28.1 / C31.1.

Unified schema for all thinking/reasoning events emitted by the system.

C28.1 (original): ThinkingEvent with source-based typing (deepseek_reasoning,
  agent_step, tool_planning, data_quality_review, risk_review, synthesis).

C31.1 (extended): Added `phase` field (9 C31 phases), `agent`, `status`
  (pending/running/completed/failed), `metadata`, and a new factory
  `make_thinking_event()` for the NEW `thinking_event` SSE type.

  Two distinct SSE event types co-exist:
    "thinking"       — legacy, maps to ui_thinking_item (ThinkingEvent.source)
    "thinking_event" — C31 new, maps to ui_thinking_event (ThinkingEvent.phase)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, field_validator


# ── C31.1: Phase enumeration (9 C31 phases) ──────────────────────────────────

THINKING_PHASES = Literal[
    "problem_analysis",    # 问题分析
    "intent_decision",     # 意图识别
    "planning",            # 自主规划
    "task_decomposition",  # 任务拆解
    "agent_dispatch",      # Agent 调度
    "agent_observation",   # 数据观测
    "deep_reasoning",      # 深度思考
    "risk_review",         # 风险审查
    "synthesis",           # 回答生成
]

PHASE_LABELS: dict[str, str] = {
    "problem_analysis":   "问题分析",
    "intent_decision":    "意图识别",
    "planning":           "自主规划",
    "task_decomposition": "任务拆解",
    "agent_dispatch":     "Agent 调度",
    "agent_observation":  "数据观测",
    "deep_reasoning":     "深度思考",
    "risk_review":        "风险审查",
    "synthesis":          "回答生成",
}


class ThinkingEvent(BaseModel):
    """
    Unified event for every "thinking" / "reasoning" signal emitted to the frontend.

    C28.1 fields (legacy — used by "thinking" SSE events):
      source: deepseek_reasoning | agent_step | tool_planning |
              data_quality_review | risk_review | synthesis
      stage:  free-form sub-stage label

    C31.1 additions (used by "thinking_event" SSE events):
      phase:    one of 9 C31 phases (problem_analysis … synthesis)
      agent:    agent name when phase is agent_dispatch/agent_observation
      status:   pending | running | completed | failed
      metadata: optional debug/diagnostic dict (never shown in normal mode)
    """
    type:       Literal["thinking"] = "thinking"
    # C28.1 legacy
    source:     Literal[
                    "deepseek_reasoning",
                    "agent_step",
                    "tool_planning",
                    "data_quality_review",
                    "risk_review",
                    "synthesis",
                ] | None = None
    stage:      str = ""
    # C31.1 new
    phase:      str = ""           # one of THINKING_PHASES
    agent:      str = ""           # agent name (e.g. "IndustryAgent")
    status:     Literal["pending", "running", "completed", "failed"] = "completed"
    metadata:   dict[str, Any] = {}
    # Shared
    title:      str = ""
    content:    str = ""
    is_final:   bool = False
    visible:    bool = True
    importance: Literal["low", "medium", "high"] = "medium"
    timestamp:  str | None = None

    model_config = {"arbitrary_types_allowed": True}

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        return v.strip()

    @field_validator("timestamp", mode="before")
    @classmethod
    def set_timestamp(cls, v):
        if v is None:
            return datetime.now(timezone.utc).isoformat()
        return v


# ── C31.1: Factory for the NEW "thinking_event" SSE type ─────────────────────

def make_thinking_event(
    phase: str,
    title: str,
    content: str,
    *,
    status: str = "completed",
    agent: str = "",
    importance: str = "medium",
    metadata: dict | None = None,
) -> dict:
    """
    C31.1: Produce a payload dict for a `thinking_event` SSE event.

    These are DISTINCT from the legacy `thinking` events — they use `phase`
    (not `source`) and are stored in message.thinkingEvents[] on the frontend.

    Args:
        phase:      One of the 9 C31 phase keys (e.g. "problem_analysis")
        title:      User-visible Chinese label (e.g. "问题分析")
        content:    User-readable Chinese summary (50–300 chars)
        status:     "pending" | "running" | "completed" | "failed"
        agent:      Agent name when applicable (e.g. "IndustryAgent")
        importance: "low" | "medium" | "high"
        metadata:   Debug/diagnostic dict (not shown in normal mode)

    Returns:
        dict ready to pass as payload to event_callback("thinking_event", ...)
    """
    return {
        "phase":      phase,
        "title":      title or PHASE_LABELS.get(phase, phase),
        "content":    content.strip()[:300],  # hard-cap at 300 chars
        "status":     status,
        "agent":      agent,
        "importance": importance,
        "visible":    True,
        "metadata":   metadata or {},
        "timestamp":  datetime.now(timezone.utc).isoformat(),
    }


# ── C28.1: Legacy factory helpers (unchanged — backward compat) ───────────────

def make_agent_step(
    stage: str,
    title: str,
    content: str,
    importance: Literal["low", "medium", "high"] = "medium",
) -> dict:
    """Return a serialized ThinkingEvent dict for an agent-step thinking."""
    ev = ThinkingEvent(
        source="agent_step",
        stage=stage,
        title=title,
        content=content,
        importance=importance,
    )
    return ev.model_dump()


def make_tool_planning(content: str) -> dict:
    ev = ThinkingEvent(
        source="tool_planning",
        stage="tool_planning",
        title="规划数据检索",
        content=content,
        importance="medium",
    )
    return ev.model_dump()


def make_data_quality_review(level: str, reason: str, missing: list[str]) -> dict:
    """Build a data_quality_review thinking event from DataQuality fields."""
    _LEVEL_LABELS = {
        "high": "数据完整",
        "medium": "数据部分完整",
        "low": "数据有限",
        "insufficient": "数据不足",
    }
    label = _LEVEL_LABELS.get(level, "未知")
    parts = [f"数据质量：{label}。{reason}"]
    if missing:
        parts.append(f"缺失：{', '.join(missing[:3])}。")
    content = " ".join(parts)[:200]

    importance: Literal["low", "medium", "high"] = (
        "high" if level in ("low", "insufficient") else "medium"
    )
    ev = ThinkingEvent(
        source="data_quality_review",
        stage="data_quality",
        title="检查数据质量",
        content=content,
        importance=importance,
    )
    return ev.model_dump()


def make_risk_review(flags: list[str]) -> dict:
    if flags:
        content = f"已过滤以下风险项：{', '.join(flags[:3])}。"
    else:
        content = "未发现高风险表述，合规审查通过。"
    ev = ThinkingEvent(
        source="risk_review",
        stage="risk_review",
        title="风险审查",
        content=content,
        importance="medium",
    )
    return ev.model_dump()


def make_synthesis_thinking(has_data: bool) -> dict:
    if has_data:
        content = "将基于已验证数据生成最终回答，缺失数据已在回答中注明。"
    else:
        content = "当前数据不足，将说明数据缺口并提供有限分析。"
    ev = ThinkingEvent(
        source="synthesis",
        stage="synthesis",
        title="生成回答",
        content=content,
        importance="low",
    )
    return ev.model_dump()
