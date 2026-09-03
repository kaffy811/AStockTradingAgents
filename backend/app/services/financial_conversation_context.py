"""Canonical financial conversation context shared by chat agents."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FinancialConversationContext:
    primary_entity: dict[str, Any] | None = None
    secondary_entities: list[dict[str, Any]] = field(default_factory=list)
    active_market: str = ""
    active_symbol: str = ""
    active_report_id: int | None = None
    active_report_year: int | None = None
    active_report_type: str | None = None
    last_intent: str = ""
    last_skill: str = ""
    comparison_dimension: str | None = None
    time_scope: str | None = None
    resolved_pronouns: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary_entity": self.primary_entity,
            "secondary_entities": self.secondary_entities,
            "active_market": self.active_market,
            "active_symbol": self.active_symbol,
            "active_report_id": self.active_report_id,
            "active_report_year": self.active_report_year,
            "active_report_type": self.active_report_type,
            "last_intent": self.last_intent,
            "last_skill": self.last_skill,
            "comparison_dimension": self.comparison_dimension,
            "time_scope": self.time_scope,
            "resolved_pronouns": self.resolved_pronouns,
        }


def build_financial_context_from_memory(memory_context: Any) -> FinancialConversationContext:
    entities = []
    for entity in getattr(memory_context, "active_entities", []) or []:
        if getattr(entity, "type", "") == "stock" and getattr(entity, "code", ""):
            entities.append({
                "entity_type": "equity",
                "market": getattr(entity, "market", "") or "",
                "symbol": getattr(entity, "code", "") or "",
                "short_name": getattr(entity, "name", "") or getattr(entity, "code", ""),
            })
    primary = entities[0] if entities else None
    user_preferences = getattr(memory_context, "user_preferences", {}) or {}
    report_id = user_preferences.get("last_report_id")
    try:
        report_id = int(report_id) if report_id else None
    except (TypeError, ValueError):
        report_id = None
    return FinancialConversationContext(
        primary_entity=primary,
        secondary_entities=entities[1:],
        active_market=(primary or {}).get("market", ""),
        active_symbol=(primary or {}).get("symbol", ""),
        active_report_id=report_id,
        last_intent=getattr(memory_context, "last_intent", "") or "",
    )
