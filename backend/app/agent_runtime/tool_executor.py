"""Bounded tool execution for Pi-compatible runtime."""
from __future__ import annotations

import asyncio
from typing import Iterable

from app.agent_runtime.contracts import PiToolCall, PiToolResponse, STATUS_FAILED
from app.agent_runtime.errors import AGENT_MAX_TOOL_CALLS_EXCEEDED, AGENT_TOOL_ARGUMENT_INVALID, AGENT_TOOL_NOT_ALLOWED
from app.agent_runtime.event_stream import PiEventRecorder
from app.agent_runtime.tool_adapter import PiFinancialToolAdapter
from app.agents.financial_runtime.contracts import FinancialSessionContext


class PiToolExecutor:
    def __init__(self, adapter: PiFinancialToolAdapter) -> None:
        self.adapter = adapter

    async def execute(
        self,
        calls: list[PiToolCall],
        *,
        trace_id: str,
        context: FinancialSessionContext,
        allowed_tools: set[str],
        max_remaining_calls: int,
        max_parallel_tools: int,
        mode: str,
        events: PiEventRecorder,
    ) -> list[PiToolResponse]:
        if len(calls) > max_remaining_calls:
            return [
                PiToolResponse(
                    trace_id=trace_id,
                    tool_call_id=call.id,
                    capability=call.name,
                    status=STATUS_FAILED,
                    error_code=AGENT_MAX_TOOL_CALLS_EXCEEDED,
                    error={"code": AGENT_MAX_TOOL_CALLS_EXCEEDED, "message": "tool call budget exceeded"},
                    quality={"status": "unavailable"},
                )
                for call in calls
            ]
        if mode == "parallel" and self._all_parallel_safe(calls, allowed_tools):
            return await self._parallel(
                calls,
                trace_id=trace_id,
                context=context,
                allowed_tools=allowed_tools,
                max_parallel_tools=max_parallel_tools,
                events=events,
            )
        return await self._sequential(
            calls,
            trace_id=trace_id,
            context=context,
            allowed_tools=allowed_tools,
            events=events,
        )

    def _all_parallel_safe(self, calls: Iterable[PiToolCall], allowed_tools: set[str]) -> bool:
        for call in calls:
            definition = self.adapter.get_definition(call.name)
            if not definition or call.name not in allowed_tools or not definition.parallel_safe:
                return False
        return True

    async def _sequential(
        self,
        calls: list[PiToolCall],
        *,
        trace_id: str,
        context: FinancialSessionContext,
        allowed_tools: set[str],
        events: PiEventRecorder,
    ) -> list[PiToolResponse]:
        responses: list[PiToolResponse] = []
        for call in calls:
            events.emit("tool_execution_start", {"tool_call_id": call.id, "tool_name": call.name})
            resp = await self.adapter.execute(call, trace_id=trace_id, context=context, allowed_tools=allowed_tools)
            if resp.error_code in {AGENT_TOOL_NOT_ALLOWED, AGENT_TOOL_ARGUMENT_INVALID}:
                events.emit("tool_call_validation_failed", {"tool_call_id": call.id, "tool_name": call.name, "error_code": resp.error_code})
            events.emit("tool_execution_end", {"tool_call_id": call.id, "tool_name": call.name, "status": resp.status, "latency_ms": resp.latency_ms})
            responses.append(resp)
        return responses

    async def _parallel(
        self,
        calls: list[PiToolCall],
        *,
        trace_id: str,
        context: FinancialSessionContext,
        allowed_tools: set[str],
        max_parallel_tools: int,
        events: PiEventRecorder,
    ) -> list[PiToolResponse]:
        semaphore = asyncio.Semaphore(max(1, max_parallel_tools))

        async def run_one(call: PiToolCall) -> PiToolResponse:
            async with semaphore:
                events.emit("tool_execution_start", {"tool_call_id": call.id, "tool_name": call.name})
                resp = await self.adapter.execute(call, trace_id=trace_id, context=context, allowed_tools=allowed_tools)
                events.emit("tool_execution_end", {"tool_call_id": call.id, "tool_name": call.name, "status": resp.status, "latency_ms": resp.latency_ms})
                return resp

        return list(await asyncio.gather(*(run_one(call) for call in calls)))
