"""Generic comparison intent parser for financial chat."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.financial_conversation_context import FinancialConversationContext
from app.services.security_entity_resolver import SecurityEntity, security_entity_resolver


_DIMENSION_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("revenue", ("营收", "收入", "营业收入")),
    ("profitability", ("盈利", "利润", "净利润", "ROE", "毛利率", "净利率")),
    ("cashflow", ("现金流", "经营现金流")),
    ("valuation", ("估值", "PE", "PB", "市盈率", "市净率")),
    ("asset_quality", ("不良率", "资产质量", "拨备", "资本充足率")),
)


@dataclass(frozen=True)
class ComparisonIntent:
    entities: list[dict[str, Any]]
    comparison_type: str
    dimensions: list[str] = field(default_factory=list)
    time_alignment: str = "latest_common_annual"
    benchmark: str | None = None
    needs_clarification: bool = False
    clarification_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "entities": self.entities,
            "comparison_type": self.comparison_type,
            "dimensions": self.dimensions,
            "time_alignment": self.time_alignment,
            "benchmark": self.benchmark,
            "needs_clarification": self.needs_clarification,
            "clarification_message": self.clarification_message,
        }


class ComparisonIntentParser:
    async def parse(
        self,
        db: AsyncSession | None,
        query: str,
        *,
        context: FinancialConversationContext | None = None,
        max_entities: int = 5,
    ) -> ComparisonIntent:
        context_entities = []
        if context and context.primary_entity:
            context_entities.append(context.primary_entity)
            context_entities.extend(context.secondary_entities)
        resolved = await security_entity_resolver.resolve(
            db,
            query,
            context_entities=context_entities,
            min_confidence=0.72,
        )
        if resolved.get("ambiguity"):
            candidates = resolved.get("candidates") or []
            names = "、".join(
                f"{c.get('short_name') or c.get('symbol')}（{c.get('market')}/{c.get('symbol')}）"
                for c in candidates[:5]
            )
            return ComparisonIntent(
                entities=[],
                comparison_type="financial_comparison",
                dimensions=self._dimensions(query),
                needs_clarification=True,
                clarification_message=f"你提到的证券名称存在歧义，可能指：{names}。请明确选择。",
            )
        entities: list[SecurityEntity] = list(resolved.get("entities") or [])
        if len(entities) > max_entities:
            return ComparisonIntent(
                entities=[e.to_dict() for e in entities[:max_entities]],
                comparison_type="financial_comparison",
                dimensions=self._dimensions(query),
                needs_clarification=True,
                clarification_message=f"本次识别到 {len(entities)} 个标的，请缩小到 {max_entities} 个以内再比较。",
            )
        return ComparisonIntent(
            entities=[e.to_dict() for e in entities],
            comparison_type=self._comparison_type(query),
            dimensions=self._dimensions(query),
            benchmark="industry" if "行业" in query or "同行" in query else None,
        )

    def _comparison_type(self, query: str) -> str:
        if any(token in query for token in ("财报", "年报", "季报", "现金流", "ROE", "净利润", "营收")):
            return "financial_report"
        if any(token in query for token in ("估值", "PE", "PB")):
            return "valuation"
        return "financial_comparison"

    def _dimensions(self, query: str) -> list[str]:
        dimensions = [
            key
            for key, tokens in _DIMENSION_KEYWORDS
            if any(token in query for token in tokens)
        ]
        return dimensions or ["revenue", "profitability", "cashflow"]


comparison_intent_parser = ComparisonIntentParser()
