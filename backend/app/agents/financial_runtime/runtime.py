"""Layered financial agent runtime facade."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from typing import Any, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.financial_runtime.compliance import compliance_gate
from app.agents.financial_runtime.contracts import (
    AgentRequest,
    AgentResponse,
    FinalChatResponse,
    STATUS_CLARIFICATION_REQUIRED,
    STATUS_FAILED,
    STATUS_PARTIAL_SUCCESS,
    STATUS_SUCCESS,
    STATUS_UNAVAILABLE,
    ToolResponse,
    new_id,
)
from app.agents.financial_runtime.domain_agents import (
    FinancialReportAnalysisAgent,
    FundamentalAnalysisAgent,
    MultiCompanyFinancialComparisonAgent,
    QuoteAnalysisAgent,
)
from app.agents.financial_runtime.drafting import answer_renderer, structured_answer_builder
from app.agents.financial_runtime.planner import execution_planner, financial_context_builder
from app.agents.financial_runtime.router import intent_safety_router
from app.agents.financial_runtime.tool_runtime import financial_tool_registry
from app.core.config import settings
from app.core.database import AsyncSessionLocal

log = logging.getLogger(__name__)

EventCallback = Callable[[str, dict[str, Any]], Any]


class FinancialAgentRuntime:
    async def run(
        self,
        *,
        raw_query: str,
        db: AsyncSession,
        user_id: str,
        conversation_id: str = "",
        page_context: dict[str, Any] | None = None,
        memory_context: Any = None,
        event_callback: EventCallback | None = None,
    ) -> FinalChatResponse:
        trace_id = new_id("trace")
        request = AgentRequest(
            trace_id=trace_id,
            status="started",
            raw_query=raw_query,
            conversation_id=conversation_id,
            page_context=page_context or {},
            user_context={"user_id": user_id},
        )
        await self._emit(event_callback, "thinking_event", {"phase": "runtime_l0", "title": "问题分析", "content": "正在识别公司和研究意图", "status": "running"})
        routing = await intent_safety_router.route(db, request)
        if routing.needs_clarification:
            answer = "你提到的证券名称存在歧义，请选择具体标的。"
            return FinalChatResponse(
                trace_id=trace_id,
                status=STATUS_CLARIFICATION_REQUIRED,
                answer=answer,
                metadata={"runtime": "layered_v1", "routing": routing.to_dict()},
            )
        if routing.intent == "prohibited_or_high_risk":
            return FinalChatResponse(
                trace_id=trace_id,
                status=STATUS_FAILED,
                error_code="POLICY_BLOCKED",
                answer="该请求涉及高风险交易或确定性预测，无法提供此类结论。",
                metadata={"runtime": "layered_v1", "routing": routing.to_dict()},
            )
        if not self._intent_enabled(routing.intent):
            return FinalChatResponse(
                trace_id=trace_id,
                status=STATUS_UNAVAILABLE,
                error_code="INTENT_NOT_MIGRATED",
                answer="",
                metadata={"runtime": "layered_v1", "routing": routing.to_dict(), "fallback_to_legacy": True},
            )

        context = financial_context_builder.build(
            trace_id=trace_id,
            routing=routing,
            page_context=page_context or {},
            memory_context=memory_context,
        )
        plan = execution_planner.plan(trace_id=trace_id, routing=routing, context=context)
        await self._emit(event_callback, "thinking_event", {
            "phase": "runtime_plan",
            "title": "执行过程",
            "content": "；".join(plan.ui_stages),
            "status": "running",
            "stages": plan.ui_stages,
        })
        if not plan.entities and routing.intent not in {"financial_knowledge"}:
            return FinalChatResponse(
                trace_id=trace_id,
                status=STATUS_FAILED,
                error_code="ENTITY_NOT_RESOLVED",
                answer="没有识别到明确的公司或股票代码，请补充证券名称或代码。",
                metadata={"runtime": "layered_v1", "routing": routing.to_dict(), "plan": plan.to_dict()},
            )

        tool_responses = await self._execute_tools(plan, context, trace_id, event_callback)
        agent_response = await self._run_agent(routing.intent, trace_id, tool_responses)
        tool_data = {resp.capability: resp.data for resp in tool_responses.values()}
        structured = structured_answer_builder.build(
            trace_id=trace_id,
            intent=routing.intent,
            agent_response=agent_response,
            tool_data=tool_data,
        )
        review = compliance_gate.review(structured)
        answer = review.edit_instructions[0]["replacement"] if review.edit_instructions else answer_renderer.render(structured)
        status = STATUS_SUCCESS if review.passed and agent_response.status == STATUS_SUCCESS else (STATUS_PARTIAL_SUCCESS if agent_response.status == STATUS_PARTIAL_SUCCESS else STATUS_FAILED)
        return FinalChatResponse(
            trace_id=trace_id,
            status=status,
            error_code=None if status != STATUS_FAILED else (agent_response.error_code or "RUNTIME_FAILED"),
            answer=answer,
            structured_answer=structured,
            tool_events=[self._tool_event(resp) for resp in tool_responses.values()],
            metadata={
                "runtime": "layered_v1",
                "routing": routing.to_dict(),
                "context": context.to_dict(),
                "plan": plan.to_dict(),
                "agent_response": agent_response.to_dict(),
                "compliance_review": review.to_dict(),
            },
        )

    async def shadow(
        self,
        *,
        raw_query: str,
        db: AsyncSession,
        user_id: str,
        conversation_id: str = "",
        page_context: dict[str, Any] | None = None,
        memory_context: Any = None,
    ) -> dict[str, Any]:
        try:
            result = await asyncio.wait_for(
                self.run(
                    raw_query=raw_query,
                    db=db,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    page_context=page_context,
                    memory_context=memory_context,
                    event_callback=None,
                ),
                timeout=8.0,
            )
            return {"status": result.status, "error_code": result.error_code, "metadata": result.metadata}
        except Exception as exc:  # noqa: BLE001
            log.debug("layered runtime shadow failed: %s", exc)
            return {"status": "failed", "error_code": type(exc).__name__}

    async def shadow_with_new_session(
        self,
        *,
        raw_query: str,
        user_id: str,
        conversation_id: str = "",
        page_context: dict[str, Any] | None = None,
        memory_context: Any = None,
    ) -> dict[str, Any]:
        async with AsyncSessionLocal() as db:
            return await self.shadow(
                raw_query=raw_query,
                db=db,
                user_id=user_id,
                conversation_id=conversation_id,
                page_context=page_context,
                memory_context=memory_context,
            )

    async def _execute_tools(self, plan, context, trace_id: str, event_callback: EventCallback | None) -> dict[str, ToolResponse]:
        responses: dict[str, ToolResponse] = {}
        pending = {step.step_id: step for step in plan.steps}
        while pending:
            ready = [
                step
                for step in pending.values()
                if all(dep in responses for dep in (step.depends_on or []))
            ]
            if not ready:
                for step_id, step in list(pending.items()):
                    responses[step_id] = ToolResponse(
                        trace_id=trace_id,
                        status=STATUS_FAILED,
                        tool_call_id=new_id("tool"),
                        capability=step.capability,
                        error_code="PLAN_DEPENDENCY_UNRESOLVED",
                        error={"code": "PLAN_DEPENDENCY_UNRESOLVED", "message": "ExecutionPlan dependency graph could not progress"},
                        quality={"status": "unavailable"},
                    )
                    pending.pop(step_id, None)
                break

            batch = await asyncio.gather(
                *[self._run_tool_step(step, context, trace_id, event_callback) for step in ready],
            )
            for step, resp in zip(ready, batch, strict=False):
                responses[step.step_id] = resp
                pending.pop(step.step_id, None)
        return responses

    async def _run_tool_step(self, step, context, trace_id: str, event_callback: EventCallback | None) -> ToolResponse:
        await self._emit(event_callback, "tool_started", {"capability": step.capability, "step_id": step.step_id})
        try:
            resp = await asyncio.wait_for(
                financial_tool_registry.call(
                    step.capability,
                    {**(step.parameters or {}), "question": context.last_intent},
                    trace_id=trace_id,
                    context=context,
                ),
                timeout=max(0.001, float(step.timeout_ms or 5000) / 1000),
            )
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            resp = ToolResponse(
                trace_id=trace_id,
                status=STATUS_FAILED,
                tool_call_id=new_id("tool"),
                capability=step.capability,
                error_code="TOOL_TIMEOUT",
                error={"code": "TOOL_TIMEOUT", "message": f"{step.capability} exceeded {step.timeout_ms}ms"},
                latency_ms=int(step.timeout_ms or 0),
                quality={"status": "unavailable"},
            )
        await self._emit(event_callback, "tool_completed", {"capability": step.capability, "status": resp.status, "latency_ms": resp.latency_ms})
        return resp

    async def _run_agent(self, intent: str, trace_id: str, tool_responses: dict[str, ToolResponse]):
        if intent == "quote_query":
            return await QuoteAnalysisAgent().run(trace_id=trace_id, tool_responses=tool_responses)
        if intent == "financial_comparison":
            return await MultiCompanyFinancialComparisonAgent().run(trace_id=trace_id, tool_responses=tool_responses)
        if intent == "financial_report":
            return await FinancialReportAnalysisAgent().run(trace_id=trace_id, tool_responses=tool_responses)
        if intent in {"official_report_pdf", "financial_report_pdf"}:
            report_url = next((resp for resp in tool_responses.values() if resp.capability == "get_official_report_url"), None)
            return AgentResponse(
                trace_id=trace_id,
                status=STATUS_SUCCESS if report_url and report_url.status == STATUS_SUCCESS else STATUS_FAILED,
                error_code=None if report_url and report_url.status == STATUS_SUCCESS else "REPORT_NOT_FOUND",
                agent_run_id=new_id("agent"),
                agent_type="official_report_pdf",
                findings=[{"type": "official_report_url"}],
            )
        return await FundamentalAnalysisAgent().run(trace_id=trace_id, tool_responses=tool_responses)

    def _tool_event(self, response: ToolResponse) -> dict[str, Any]:
        return {
            "name": response.capability,
            "status": "success" if response.status == STATUS_SUCCESS else ("partial_success" if response.status == STATUS_PARTIAL_SUCCESS else "error"),
            "detail": response.error.get("message") if response.error else response.capability,
            "latency_ms": response.latency_ms,
            "event_type": "tool_completed",
        }

    async def _emit(self, callback: EventCallback | None, event_type: str, payload: dict[str, Any]) -> None:
        if callback is None:
            return
        try:
            result = callback(event_type, payload)
            if hasattr(result, "__await__"):
                await result
        except Exception:
            log.debug("layered runtime callback failed for %s", event_type)

    def _intent_enabled(self, intent: str) -> bool:
        configured = {
            item.strip()
            for item in str(getattr(settings, "chat_layered_intents", "") or "").split(",")
            if item.strip()
        }
        aliases = {
            "financial_report_pdf": "official_report_pdf",
            "company_fundamental": "financial_snapshot",
        }
        return intent in configured or aliases.get(intent) in configured


financial_agent_runtime = FinancialAgentRuntime()
