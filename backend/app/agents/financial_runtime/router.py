"""L0 Intent & Safety Router for layered financial chat runtime."""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.financial_runtime.contracts import (
    AgentRequest,
    IntentRoutingResult,
    SecurityEntity,
    STATUS_CLARIFICATION_REQUIRED,
    STATUS_FAILED,
    STATUS_SUCCESS,
)
from app.services.security_entity_resolver import security_entity_resolver


_PROHIBITED_RE = re.compile(
    r"帮我.{0,6}(交易|买入|卖出|下单|购买|清仓)|目标价|稳赚|必涨|内幕|操纵",
    re.IGNORECASE,
)
_COMPARISON_RE = re.compile(r"对比|比较|相比|和.+比|vs\.?|versus", re.IGNORECASE)
_REPORT_RE = re.compile(r"财报|年报|季报|报告表现|经营现金流|官方\s*PDF|PDF\s*在哪|报告链接")
_PDF_RE = re.compile(r"官方\s*PDF|PDF\s*在哪|报告链接|pdf链接", re.IGNORECASE)
_QUOTE_RE = re.compile(r"现在多少|当前价|最新价|报价|股价")
_SNAPSHOT_RE = re.compile(r"基本面|财务快照|盈利能力|资产负债|现金流质量|估值")
_NEWS_RE = re.compile(r"新闻|消息|公告|舆情")
_INDUSTRY_RE = re.compile(r"行业|板块|同行")


def _entity_from_resolver(raw: Any, trace_id: str) -> SecurityEntity:
    data = raw.to_dict() if hasattr(raw, "to_dict") else dict(raw)
    return SecurityEntity(
        trace_id=trace_id,
        status=STATUS_SUCCESS,
        entity_type=data.get("entity_type") or "equity",
        market=data.get("market") or "",
        symbol=data.get("symbol") or "",
        exchange=data.get("exchange") or "",
        ts_code=data.get("ts_code") or "",
        short_name=data.get("short_name") or data.get("name") or "",
        full_name=data.get("full_name") or "",
        aliases=list(data.get("aliases") or []),
        industry=data.get("industry"),
        confidence=float(data.get("confidence") or 0.0),
        match_type=data.get("match_type") or "",
        ambiguity=bool(data.get("ambiguity") or False),
        source=data.get("source") or "security_entity_resolver",
    )


class IntentSafetyRouter:
    """Pure routing plus entity resolution.

    L0 deliberately does not query quotes, reports, news, or financial data.
    """

    async def route(self, db: AsyncSession, request: AgentRequest) -> IntentRoutingResult:
        query = (request.raw_query or "").strip()
        if _PROHIBITED_RE.search(query):
            return IntentRoutingResult(
                trace_id=request.trace_id,
                status=STATUS_FAILED,
                intent="prohibited_or_high_risk",
                intent_confidence=0.99,
                policy_class="prohibited",
                reason="matched_high_risk_trading_or_prediction",
            )

        resolved = await security_entity_resolver.resolve(
            db,
            query,
            context_entities=self._page_context_entities(request.page_context),
            min_confidence=0.72,
        )
        if resolved.get("ambiguity"):
            return IntentRoutingResult(
                trace_id=request.trace_id,
                status=STATUS_CLARIFICATION_REQUIRED,
                intent="ambiguous",
                intent_confidence=0.9,
                policy_class="normal",
                needs_clarification=True,
                clarification_options=list(resolved.get("candidates") or [])[:5],
                reason="security_entity_ambiguous",
            )

        entities = [_entity_from_resolver(entity, request.trace_id) for entity in (resolved.get("entities") or [])]
        intent = self._classify_intent(query, entities)
        return IntentRoutingResult(
            trace_id=request.trace_id,
            status=STATUS_SUCCESS,
            intent=intent,
            intent_confidence=0.88 if intent != "ambiguous" else 0.45,
            resolved_entities=entities,
            policy_class="normal",
            needs_clarification=False,
            reason="rule_based_router_v1",
        )

    def _classify_intent(self, query: str, entities: list[SecurityEntity]) -> str:
        if _PDF_RE.search(query):
            return "official_report_pdf"
        if _COMPARISON_RE.search(query) and (len(entities) >= 2 or re.search(r"它|该股|这家公司|前者|后者", query)):
            return "financial_comparison"
        if _REPORT_RE.search(query):
            return "financial_report"
        if _QUOTE_RE.search(query):
            return "quote_query"
        if _SNAPSHOT_RE.search(query):
            return "company_fundamental"
        if _NEWS_RE.search(query):
            return "news_sentiment"
        if _INDUSTRY_RE.search(query):
            return "industry_analysis"
        if not entities and re.search(r"什么是|如何理解|解释一下", query):
            return "financial_knowledge"
        return "ambiguous" if not entities else "company_fundamental"

    def _page_context_entities(self, page_context: dict[str, Any]) -> list[dict[str, Any]]:
        if not page_context:
            return []
        symbol = page_context.get("symbol") or page_context.get("active_symbol")
        if not symbol:
            return []
        return [{
            "entity_type": "equity",
            "market": page_context.get("market") or page_context.get("active_market") or "",
            "symbol": symbol,
            "short_name": page_context.get("name") or page_context.get("short_name") or symbol,
            "source": "page_context",
        }]


intent_safety_router = IntentSafetyRouter()
