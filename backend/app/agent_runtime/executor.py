"""Pi-compatible financial agent executor."""
from __future__ import annotations

import asyncio
import time

from app.agent_runtime.agents.official_report_pdf_agent import OfficialReportPdfAgent
from app.agent_runtime.capability_manifest import agent_manifests
from app.agent_runtime.contracts import (
    PiAgentRunResult,
    PiRuntimeMetrics,
    PiRuntimeRequest,
    STATUS_CANCELLED,
    STATUS_FAILED,
)
from app.agent_runtime.errors import AGENT_CANCELLED, AGENT_DEADLINE_EXCEEDED, AGENT_INTERNAL_ERROR
from app.agent_runtime.event_stream import PiEventRecorder
from app.agent_runtime.metrics import runtime_metrics_sink
from app.agent_runtime.tool_adapter import PiFinancialToolAdapter
from app.agents.financial_runtime.contracts import FinancialSessionContext


class PiCompatibleAgentExecutor:
    def __init__(self, *, tool_adapter: PiFinancialToolAdapter | None = None) -> None:
        self.tool_adapter = tool_adapter or PiFinancialToolAdapter()
        self._agents = {
            "official_report_pdf_pi_v1": OfficialReportPdfAgent(tool_adapter=self.tool_adapter),
        }

    async def run(
        self,
        *,
        request: PiRuntimeRequest,
        financial_context: FinancialSessionContext,
    ) -> PiAgentRunResult:
        started = time.perf_counter()
        events = PiEventRecorder(trace_id=request.trace_id, run_id=request.run_id)
        manifest = agent_manifests.get("official_report_pdf_pi_v1")
        if not manifest or request.intent not in manifest.supported_intents:
            return self._failure(request, events, started, AGENT_INTERNAL_ERROR)
        if request.runtime_mode != "shadow" or not request.read_only:
            return self._failure(request, events, started, AGENT_INTERNAL_ERROR)

        request.allowed_tools = [tool for tool in request.allowed_tools if tool in manifest.allowed_tools]
        request.budgets.max_turns = min(request.budgets.max_turns, manifest.max_turns)
        request.budgets.max_tool_calls = min(request.budgets.max_tool_calls, manifest.max_tool_calls)
        request.budgets.deadline_ms = min(request.budgets.deadline_ms, manifest.deadline_ms)

        try:
            result = await asyncio.wait_for(
                self._agents[manifest.agent_id].run(request=request, financial_context=financial_context, events=events),
                timeout=max(0.001, request.budgets.deadline_ms / 1000),
            )
            self._record_metrics(result)
            return result
        except asyncio.CancelledError:
            events.emit("run_cancelled", {"error_code": AGENT_CANCELLED})
            runtime_metrics_sink.increment("agent_cancelled")
            raise
        except asyncio.TimeoutError:
            runtime_metrics_sink.increment("deadline_exceeded")
            return self._failure(request, events, started, AGENT_DEADLINE_EXCEEDED)
        except Exception:  # noqa: BLE001
            return self._failure(request, events, started, AGENT_INTERNAL_ERROR)

    def _failure(
        self,
        request: PiRuntimeRequest,
        events: PiEventRecorder,
        started: float,
        code: str,
    ) -> PiAgentRunResult:
        events.emit("run_failed", {"error_code": code})
        metrics = PiRuntimeMetrics(latency_ms=int((time.perf_counter() - started) * 1000))
        result = PiAgentRunResult(
            trace_id=request.trace_id,
            run_id=request.run_id,
            status=STATUS_CANCELLED if code == AGENT_CANCELLED else STATUS_FAILED,
            agent_id="official_report_pdf_pi_v1",
            events=events.public_events(debug=True),
            error={"code": code, "message": code},
            metrics=metrics,
        )
        self._record_metrics(result)
        return result

    def _record_metrics(self, result: PiAgentRunResult) -> None:
        runtime_metrics_sink.increment("agent_runs")
        if result.status == "success":
            runtime_metrics_sink.increment("agent_success")
        elif result.status == "partial_success":
            runtime_metrics_sink.increment("agent_partial")
        elif result.status == "cancelled":
            runtime_metrics_sink.increment("agent_cancelled")
        else:
            runtime_metrics_sink.increment("agent_failed")
        runtime_metrics_sink.increment("turns", result.turn_count)
        runtime_metrics_sink.increment("tool_calls", result.tool_call_count)
