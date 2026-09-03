"""Pi-compatible bounded agent loop."""
from __future__ import annotations

import asyncio
import time
from dataclasses import asdict

from app.agent_runtime.context_transform import PiContextTransform
from app.agent_runtime.contracts import (
    ModelProfile,
    ModelRequest,
    ModelResponse,
    PiAgentMessage,
    PiAgentRunResult,
    PiRuntimeMetrics,
    PiRuntimeRequest,
    PiToolCall,
    STATUS_FAILED,
    STATUS_SUCCESS,
)
from app.agent_runtime.errors import (
    AGENT_CANCELLED,
    AGENT_INTERNAL_ERROR,
    AGENT_MAX_TOOL_CALLS_EXCEEDED,
    AGENT_MAX_TURNS_EXCEEDED,
    AGENT_MODEL_UNAVAILABLE,
    AGENT_TOOL_ARGUMENT_INVALID,
)
from app.agent_runtime.event_stream import PiEventRecorder
from app.agent_runtime.model_gateway import DisabledModelGateway
from app.agent_runtime.tool_adapter import PiFinancialToolAdapter
from app.agent_runtime.tool_executor import PiToolExecutor
from app.agents.financial_runtime.contracts import FinancialSessionContext


class PiAgentLoop:
    def __init__(
        self,
        *,
        tool_adapter: PiFinancialToolAdapter | None = None,
        model_gateway=None,
        context_transform: PiContextTransform | None = None,
    ) -> None:
        self.tool_adapter = tool_adapter or PiFinancialToolAdapter()
        self.tool_executor = PiToolExecutor(self.tool_adapter)
        self.model_gateway = model_gateway or DisabledModelGateway()
        self.context_transform = context_transform or PiContextTransform()

    async def run(
        self,
        *,
        request: PiRuntimeRequest,
        financial_context: FinancialSessionContext,
        messages: list[PiAgentMessage],
        agent_id: str,
        events: PiEventRecorder,
        tool_mode: str = "sequential",
    ) -> PiAgentRunResult:
        started = time.perf_counter()
        metrics = PiRuntimeMetrics()
        allowed_tools = set(request.allowed_tools)
        transformed = self.context_transform.select_messages(messages)
        tool_call_count = 0
        invalid_tool_signatures: set[tuple[str, str]] = set()
        last_model_response = ModelResponse()
        events.emit("run_start", {"agent": agent_id, "mode": request.runtime_mode})

        try:
            for turn_index in range(1, request.budgets.max_turns + 1):
                events.emit("turn_start", {"turn": turn_index})
                events.emit("model_start", {"model_profile": request.model_profile})
                metrics.model_calls += 1

                model_request = ModelRequest(
                    trace_id=request.trace_id,
                    run_id=request.run_id,
                    model_profile=ModelProfile(name=request.model_profile, max_output_tokens=request.budgets.max_output_tokens),
                    messages=transformed,
                    tools=self.tool_adapter.definitions_for(request.allowed_tools),
                    max_output_tokens=request.budgets.max_output_tokens,
                )
                model_response = await self._collect_model_response(model_request, events)
                last_model_response = model_response
                metrics.input_tokens += model_response.input_tokens
                metrics.output_tokens += model_response.output_tokens
                events.emit("model_end", {"status": model_response.status, "tool_calls": len(model_response.tool_calls)})

                if model_response.status != STATUS_SUCCESS:
                    return self._result(
                        request=request,
                        agent_id=agent_id,
                        status=STATUS_FAILED,
                        events=events,
                        metrics=metrics,
                        started=started,
                        turn_count=turn_index,
                        tool_call_count=tool_call_count,
                        error_code=model_response.error_code or AGENT_MODEL_UNAVAILABLE,
                    )

                if not model_response.tool_calls:
                    events.emit("turn_end", {"turn": turn_index, "tool_results": 0})
                    return self._result(
                        request=request,
                        agent_id=agent_id,
                        status=STATUS_SUCCESS,
                        events=events,
                        metrics=metrics,
                        started=started,
                        turn_count=turn_index,
                        tool_call_count=tool_call_count,
                        structured_answer=model_response.structured_output,
                    )

                if tool_call_count + len(model_response.tool_calls) > request.budgets.max_tool_calls:
                    return self._result(
                        request=request,
                        agent_id=agent_id,
                        status=STATUS_FAILED,
                        events=events,
                        metrics=metrics,
                        started=started,
                        turn_count=turn_index,
                        tool_call_count=tool_call_count,
                        error_code=AGENT_MAX_TOOL_CALLS_EXCEEDED,
                    )

                repeated_invalid = [
                    call for call in model_response.tool_calls
                    if call.signature() in invalid_tool_signatures
                ]
                if repeated_invalid:
                    return self._result(
                        request=request,
                        agent_id=agent_id,
                        status=STATUS_FAILED,
                        events=events,
                        metrics=metrics,
                        started=started,
                        turn_count=turn_index,
                        tool_call_count=tool_call_count,
                        error_code=AGENT_TOOL_ARGUMENT_INVALID,
                    )

                for call in model_response.tool_calls:
                    events.emit("tool_call_start", {"tool_call_id": call.id, "tool_name": call.name})

                tool_responses = await self.tool_executor.execute(
                    model_response.tool_calls,
                    trace_id=request.trace_id,
                    context=financial_context,
                    allowed_tools=allowed_tools,
                    max_remaining_calls=request.budgets.max_tool_calls - tool_call_count,
                    max_parallel_tools=request.budgets.max_parallel_tools,
                    mode=tool_mode,
                    events=events,
                )
                metrics.tool_calls += len(tool_responses)
                metrics.tool_failures += sum(1 for resp in tool_responses if resp.status == STATUS_FAILED)
                metrics.tool_validation_failures += sum(1 for resp in tool_responses if resp.error_code == AGENT_TOOL_ARGUMENT_INVALID)
                tool_call_count += len(tool_responses)

                for call, resp in zip(model_response.tool_calls, tool_responses, strict=False):
                    if resp.error_code == AGENT_TOOL_ARGUMENT_INVALID:
                        invalid_tool_signatures.add(call.signature())
                    transformed.append(PiAgentMessage(role="toolResult", content=resp.to_dict()))

                events.emit("turn_end", {"turn": turn_index, "tool_results": len(tool_responses)})

            return self._result(
                request=request,
                agent_id=agent_id,
                status=STATUS_FAILED,
                events=events,
                metrics=metrics,
                started=started,
                turn_count=request.budgets.max_turns,
                tool_call_count=tool_call_count,
                error_code=AGENT_MAX_TURNS_EXCEEDED,
                structured_answer=last_model_response.structured_output,
            )
        except asyncio.CancelledError:
            events.emit("run_cancelled", {"error_code": AGENT_CANCELLED})
            raise
        except Exception as exc:  # noqa: BLE001
            return self._result(
                request=request,
                agent_id=agent_id,
                status=STATUS_FAILED,
                events=events,
                metrics=metrics,
                started=started,
                turn_count=0,
                tool_call_count=tool_call_count,
                error_code=AGENT_INTERNAL_ERROR,
                error_message=str(exc)[:160],
            )

    async def _collect_model_response(self, request: ModelRequest, events: PiEventRecorder) -> ModelResponse:
        text_parts: list[str] = []
        tool_calls: list[PiToolCall] = []
        structured: dict = {}
        async for event in self.model_gateway.stream(request):
            if event.event_type == "text_delta":
                text_parts.append(event.text_delta)
                events.emit("model_text_delta", {"bytes": len(event.text_delta.encode("utf-8"))})
            elif event.event_type == "tool_call" and event.tool_call:
                tool_calls.append(event.tool_call)
            elif event.event_type == "structured_output" and event.structured_output:
                structured.update(event.structured_output)
            elif event.event_type == "error":
                return ModelResponse(status=STATUS_FAILED, error_code=event.error_code or AGENT_MODEL_UNAVAILABLE)
        return ModelResponse(text="".join(text_parts), structured_output=structured, tool_calls=tool_calls)

    def _result(
        self,
        *,
        request: PiRuntimeRequest,
        agent_id: str,
        status: str,
        events: PiEventRecorder,
        metrics: PiRuntimeMetrics,
        started: float,
        turn_count: int,
        tool_call_count: int,
        error_code: str | None = None,
        error_message: str | None = None,
        structured_answer: dict | None = None,
    ) -> PiAgentRunResult:
        metrics.latency_ms = int((time.perf_counter() - started) * 1000)
        error = {"code": error_code, "message": error_message or error_code} if error_code else None
        if status == STATUS_FAILED:
            events.emit("run_failed", {"error_code": error_code})
        else:
            events.emit("run_end", {"status": status})
        return PiAgentRunResult(
            trace_id=request.trace_id,
            run_id=request.run_id,
            status=status,
            agent_id=agent_id,
            turn_count=turn_count,
            tool_call_count=tool_call_count,
            events=events.public_events(debug=True),
            structured_answer=structured_answer or {},
            error=error,
            metrics=metrics,
        )
