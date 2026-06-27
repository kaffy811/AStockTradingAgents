"""
Thinking Events — C28.1.

Unified schema for all thinking/reasoning events emitted by the system.
Distinguishes model reasoning (deepseek_reasoning) from agent-step summaries.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, field_validator


class ThinkingEvent(BaseModel):
    """
    Unified event for every "thinking" / "reasoning" signal emitted to the frontend.

    source values:
      deepseek_reasoning  — raw model reasoning_content (R1-style models)
      agent_step          — system-generated research step summary
      tool_planning       — pre-tool data-retrieval planning note
      data_quality_review — data quality assessment note
      risk_review         — risk-compliance review note
      synthesis           — final synthesis / generation phase note
    """
    type:       Literal["thinking"] = "thinking"
    source:     Literal[
                    "deepseek_reasoning",
                    "agent_step",
                    "tool_planning",
                    "data_quality_review",
                    "risk_review",
                    "synthesis",
                ]
    stage:      str = ""
    title:      str = ""
    content:    str = ""
    is_final:   bool = False
    visible:    bool = True
    importance: Literal["low", "medium", "high"] = "medium"
    timestamp:  str | None = None

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        # Strip and allow empty — callers should filter out before emitting
        return v.strip()

    @field_validator("timestamp", mode="before")
    @classmethod
    def set_timestamp(cls, v):
        if v is None:
            return datetime.now(timezone.utc).isoformat()
        return v


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

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
