"""L1 context builder and execution planner."""
from __future__ import annotations

from typing import Any

from app.agents.financial_runtime.contracts import (
    ExecutionPlan,
    FinancialSessionContext,
    IntentRoutingResult,
    PlanStep,
    SecurityEntity,
    STATUS_SUCCESS,
    new_id,
)


def _context_entity(memory_context: Any) -> SecurityEntity | None:
    for entity in getattr(memory_context, "active_entities", []) or []:
        if getattr(entity, "type", "") != "stock" or not getattr(entity, "code", ""):
            continue
        return SecurityEntity(
            trace_id="context",
            status=STATUS_SUCCESS,
            entity_type="equity",
            market=getattr(entity, "market", "") or "CN",
            symbol=getattr(entity, "code", "") or "",
            short_name=getattr(entity, "name", "") or getattr(entity, "code", ""),
            source="conversation_context",
        )
    return None


class FinancialContextBuilder:
    def build(
        self,
        *,
        trace_id: str,
        routing: IntentRoutingResult,
        page_context: dict[str, Any] | None = None,
        memory_context: Any = None,
    ) -> FinancialSessionContext:
        explicit = list(routing.resolved_entities or [])
        context_primary = _context_entity(memory_context)
        pronoun = self._has_pronoun(getattr(memory_context, "resolved_query", "") or "")
        primary = explicit[0] if explicit else (context_primary if pronoun or not explicit else None)
        secondary = explicit[1:]
        if routing.intent == "financial_comparison" and context_primary and explicit:
            secondary = explicit
            primary = context_primary
            dedup: dict[tuple[str, str], SecurityEntity] = {}
            for item in [primary, *secondary]:
                dedup[(item.market, item.symbol)] = item
            values = list(dedup.values())
            primary = values[0] if values else primary
            secondary = values[1:]
        return FinancialSessionContext(
            trace_id=trace_id,
            status=STATUS_SUCCESS,
            primary_entity=primary,
            secondary_entities=secondary,
            active_market=(primary.market if primary else ""),
            active_symbol=(primary.symbol if primary else ""),
            active_report_id=self._memory_report_id(memory_context),
            active_report_year=self._memory_report_year(memory_context),
            active_report_type=self._memory_report_type(memory_context),
            active_period=None,
            last_intent=routing.intent,
            page_context=page_context or {},
            last_successful_context=getattr(memory_context, "raw_context", None),
        )

    def _has_pronoun(self, query: str) -> bool:
        return any(token in query for token in ("它", "该股", "这家公司", "这只股票", "前者", "后者"))

    def _memory_report_id(self, memory_context: Any) -> int | None:
        prefs = getattr(memory_context, "user_preferences", {}) or {}
        try:
            return int(prefs.get("last_report_id")) if prefs.get("last_report_id") else None
        except (TypeError, ValueError):
            return None

    def _memory_report_year(self, memory_context: Any) -> int | None:
        prefs = getattr(memory_context, "user_preferences", {}) or {}
        try:
            return int(prefs.get("last_report_year")) if prefs.get("last_report_year") else None
        except (TypeError, ValueError):
            return None

    def _memory_report_type(self, memory_context: Any) -> str | None:
        prefs = getattr(memory_context, "user_preferences", {}) or {}
        return prefs.get("last_report_type")


class ExecutionPlanner:
    def plan(self, *, trace_id: str, routing: IntentRoutingResult, context: FinancialSessionContext) -> ExecutionPlan:
        plan_id = new_id("plan")
        intent = routing.intent
        steps: list[PlanStep]
        stages: list[str]
        mode = "serial"
        budget = 15000

        if intent == "quote_query":
            steps = [PlanStep("quote", "get_quote_snapshot", parameters={"entity": context.primary_entity})]
            stages = ["识别公司", "获取行情", "生成回答"]
            budget = 3000
        elif intent in {"official_report_pdf", "financial_report_pdf"}:
            steps = [PlanStep("report_url", "get_official_report_url", parameters={"entity": context.primary_entity}, timeout_ms=3000)]
            stages = ["识别公司", "定位正式报告", "生成回答"]
            budget = 3000
        elif intent == "financial_comparison":
            entities = [e for e in [context.primary_entity, *context.secondary_entities] if e]
            steps = [
                PlanStep("reports", "get_official_reports", parameters={"entities": entities}),
                PlanStep("financials", "get_structured_report_financials", depends_on=["reports"], parameters={"entities": entities}),
                PlanStep("compare", "compare_financials", depends_on=["financials"], parameters={"entities": entities}),
            ]
            stages = ["解析比较对象", "对齐报告年度", "构建对比表", "生成解读"]
            mode = "dag"
        elif intent == "financial_report":
            steps = [
                PlanStep("reports", "get_official_reports", parameters={"entity": context.primary_entity}),
                PlanStep("financials", "get_structured_report_financials", depends_on=["reports"], parameters={"entity": context.primary_entity}),
                PlanStep("evidence", "query_report_evidence", depends_on=["reports"], parameters={"entity": context.primary_entity}),
            ]
            stages = ["定位正式报告", "检索财务数据", "生成分析"]
        else:
            steps = [PlanStep("snapshot", "get_financial_snapshot", parameters={"entity": context.primary_entity})]
            stages = ["识别公司", "获取财务快照", "生成回答"]

        return ExecutionPlan(
            trace_id=trace_id,
            status=STATUS_SUCCESS,
            plan_id=plan_id,
            intent=intent,
            entities=[e for e in [context.primary_entity, *context.secondary_entities] if e],
            steps=steps,
            dependencies={step.step_id: step.depends_on for step in steps},
            execution_mode=mode,
            timeout_budget_ms=budget,
            ui_stages=stages,
        )


financial_context_builder = FinancialContextBuilder()
execution_planner = ExecutionPlanner()
