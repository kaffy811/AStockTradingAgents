"""Official report PDF Pi-compatible shadow agent."""
from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any

from app.agent_runtime.capability_manifest import official_report_pdf_manifest
from app.agent_runtime.contracts import (
    PiAgentRunResult,
    PiRuntimeMetrics,
    PiRuntimeRequest,
    PiToolCall,
    STATUS_SUCCESS,
    STATUS_UNAVAILABLE,
    new_id,
)
from app.agent_runtime.event_stream import PiEventRecorder
from app.agent_runtime.tool_adapter import PiFinancialToolAdapter
from app.agent_runtime.tool_executor import PiToolExecutor
from app.agent_runtime.url_utils import official_domain_verified
from app.agents.financial_runtime.compliance import compliance_gate
from app.agents.financial_runtime.contracts import (
    FinancialSessionContext,
    STATUS_SUCCESS as FIN_STATUS_SUCCESS,
    StructuredAnswer,
)


class OfficialReportPdfAgent:
    agent_id = official_report_pdf_manifest.agent_id

    def __init__(self, *, tool_adapter: PiFinancialToolAdapter | None = None) -> None:
        self.tool_adapter = tool_adapter or PiFinancialToolAdapter()
        self.tool_executor = PiToolExecutor(self.tool_adapter)

    async def run(
        self,
        *,
        request: PiRuntimeRequest,
        financial_context: FinancialSessionContext,
        events: PiEventRecorder,
    ) -> PiAgentRunResult:
        started = time.perf_counter()
        metrics = PiRuntimeMetrics()
        events.emit("run_start", {"agent": self.agent_id, "mode": request.runtime_mode})
        events.emit("turn_start", {"turn": 1, "path": "deterministic"})

        entity = self._primary_entity(request, financial_context)
        if not entity:
            return self._finish(
                request=request,
                events=events,
                metrics=metrics,
                started=started,
                status=STATUS_UNAVAILABLE,
                error_code="ENTITY_NOT_RESOLVED",
                structured=self._unavailable_structured(request.trace_id),
            )

        report_year = self._report_year(request, financial_context)
        report_type = self._report_type(request, financial_context)
        if report_type and report_type != "annual":
            return self._finish(
                request=request,
                events=events,
                metrics=metrics,
                started=started,
                status=STATUS_UNAVAILABLE,
                error_code="REPORT_TYPE_UNSUPPORTED",
                structured=self._unavailable_structured(request.trace_id),
            )
        call = PiToolCall(
            id=new_id("toolcall"),
            name="get_official_reports",
            arguments={"entity": entity, "report_year": report_year, "report_type": report_type or "annual"},
        )
        events.emit("tool_call_start", {"tool_call_id": call.id, "tool_name": call.name})
        responses = await self.tool_executor.execute(
            [call],
            trace_id=request.trace_id,
            context=financial_context,
            allowed_tools=set(official_report_pdf_manifest.allowed_tools),
            max_remaining_calls=request.budgets.max_tool_calls,
            max_parallel_tools=1,
            mode="sequential",
            events=events,
        )
        metrics.tool_calls = 1
        tool_response = responses[0]
        metrics.tool_latency_breakdown = {
            **(tool_response.quality.get("latency_breakdown") or {}),
            "adapter_total_ms": tool_response.latency_ms,
        }
        if tool_response.status != STATUS_SUCCESS:
            return self._finish(
                request=request,
                events=events,
                metrics=metrics,
                started=started,
                status=STATUS_UNAVAILABLE,
                error_code=tool_response.error_code or "REPORT_TOOL_UNAVAILABLE",
                structured=self._unavailable_structured(request.trace_id),
                tool_call_count=1,
            )
        report = self._select_report(tool_response.data, entity=entity, report_year=report_year, report_type=report_type)
        if not report:
            return self._finish(
                request=request,
                events=events,
                metrics=metrics,
                started=started,
                status=STATUS_UNAVAILABLE,
                error_code="REPORT_NOT_FOUND",
                structured=self._unavailable_structured(request.trace_id),
                tool_call_count=1,
            )

        pdf_url = report.get("pdf_url") or report.get("official_url")
        source_page_url = report.get("source_page_url") or report.get("source_url")
        official_verified = official_domain_verified(pdf_url) or official_domain_verified(source_page_url)
        if not pdf_url or not official_verified:
            return self._finish(
                request=request,
                events=events,
                metrics=metrics,
                started=started,
                status=STATUS_UNAVAILABLE,
                error_code="OFFICIAL_PDF_UNAVAILABLE" if not pdf_url else "OFFICIAL_DOMAIN_UNVERIFIED",
                structured=self._unavailable_structured(request.trace_id),
                tool_call_count=1,
            )

        structured = StructuredAnswer(
            trace_id=request.trace_id,
            status=FIN_STATUS_SUCCESS,
            title="官方报告入口",
            conclusion=f"已找到 {report.get('report_year') or report_year or '指定'} 年正式年度报告，可通过官方 PDF 入口查看。",
            findings=[report.get("title") or "正式年度报告"],
            sources=[{
                "label": "官方 PDF",
                "url": pdf_url,
                "source_type": "official_report",
                "provider": "official_report_domain_service",
                "period": report.get("period_end"),
                "report_year": report.get("report_year"),
                "report_type": report.get("report_type") or report_type or "annual",
                "source_page_url": source_page_url,
                "official_domain_verified": official_verified,
            }],
        )
        events.emit("turn_end", {"turn": 1, "status": STATUS_SUCCESS})
        events.emit("compliance_start", {})
        review = compliance_gate.review(structured)
        events.emit("compliance_end", {"passed": review.passed})
        status = STATUS_SUCCESS if review.passed else STATUS_UNAVAILABLE
        events.emit("run_end", {"status": status})
        return PiAgentRunResult(
            trace_id=request.trace_id,
            run_id=request.run_id,
            status=status,
            agent_id=self.agent_id,
            turn_count=1,
            tool_call_count=1,
            events=events.public_events(debug=True),
            findings=[{
                "type": "official_report_pdf",
                "market": entity.get("market") or "CN",
                "symbol": entity.get("symbol") or self._symbol_from_ts_code(report.get("ts_code")),
                "ts_code": entity.get("ts_code") or report.get("ts_code"),
                "company_name": entity.get("short_name") or entity.get("full_name") or "",
                "report_year": report.get("report_year"),
                "report_type": report.get("report_type") or report_type or "annual",
                "source_page_url": source_page_url,
                "pdf_url": pdf_url,
                "official_url": pdf_url,
                "official_domain_verified": official_verified,
            }],
            evidence_ids=[self._evidence_id(entity, report)],
            structured_answer=asdict(structured),
            error=None if review.passed else {"code": "COMPLIANCE_REJECTED", "message": "compliance rejected output"},
            metrics=self._metrics(metrics, started),
        )

    def _primary_entity(self, request: PiRuntimeRequest, context: FinancialSessionContext) -> dict[str, Any] | None:
        if request.entities:
            return request.entities[0]
        if context.primary_entity:
            return asdict(context.primary_entity)
        entity = request.context.get("primary_entity")
        return entity if isinstance(entity, dict) else None

    def _report_year(self, request: PiRuntimeRequest, context: FinancialSessionContext) -> int | None:
        value = request.context.get("report_year") or context.active_report_year
        try:
            return int(value) if value else None
        except (TypeError, ValueError):
            return None

    def _report_type(self, request: PiRuntimeRequest, context: FinancialSessionContext) -> str | None:
        value = request.context.get("report_type") or context.active_report_type
        if not value:
            return None
        normalized = str(value).strip().lower()
        aliases = {
            "yearly": "annual",
            "annual_report": "annual",
            "年报": "annual",
            "年度报告": "annual",
            "semi_annual": "semi",
            "half": "semi",
            "半年报": "semi",
            "中报": "semi",
            "q1": "q1",
            "一季报": "q1",
            "第一季度": "q1",
            "q3": "q3",
            "三季报": "q3",
            "第三季度": "q3",
        }
        return aliases.get(normalized, normalized)

    def _select_report(self, data: dict[str, Any], *, entity: dict[str, Any], report_year: int | None, report_type: str | None) -> dict[str, Any] | None:
        reports_by_symbol = data.get("reports_by_symbol") or {}
        candidates: list[dict[str, Any]] = []
        for reports in reports_by_symbol.values():
            candidates.extend([item for item in reports if isinstance(item, dict)])
        if report_year is not None:
            candidates = [item for item in candidates if item.get("report_year") == report_year]
        if report_type:
            candidates = [item for item in candidates if (item.get("report_type") or "annual") == report_type]
        if not candidates:
            return None
        return sorted(candidates, key=lambda item: (item.get("report_year") or 0, str(item.get("period_end") or "")), reverse=True)[0]

    def _unavailable_structured(self, trace_id: str) -> dict[str, Any]:
        return asdict(StructuredAnswer(
            trace_id=trace_id,
            status=STATUS_UNAVAILABLE,
            title="官方报告入口",
            conclusion="暂未找到可验证的官方报告 PDF。",
            sources=[],
        ))

    def _finish(
        self,
        *,
        request: PiRuntimeRequest,
        events: PiEventRecorder,
        metrics: PiRuntimeMetrics,
        started: float,
        status: str,
        error_code: str,
        structured: dict[str, Any],
        tool_call_count: int = 0,
    ) -> PiAgentRunResult:
        events.emit("turn_end", {"turn": 1, "status": status, "error_code": error_code})
        events.emit("run_end", {"status": status, "error_code": error_code})
        return PiAgentRunResult(
            trace_id=request.trace_id,
            run_id=request.run_id,
            status=status,
            agent_id=self.agent_id,
            turn_count=1,
            tool_call_count=tool_call_count,
            events=events.public_events(debug=True),
            structured_answer=structured,
            error={"code": error_code, "message": error_code},
            metrics=self._metrics(metrics, started),
        )

    def _metrics(self, metrics: PiRuntimeMetrics, started: float) -> PiRuntimeMetrics:
        metrics.latency_ms = int((time.perf_counter() - started) * 1000)
        return metrics

    def _evidence_id(self, entity: dict[str, Any], report: dict[str, Any]) -> str:
        symbol = entity.get("ts_code") or entity.get("symbol") or "unknown"
        year = report.get("report_year") or "unknown"
        return f"official_report:{symbol}:{year}"

    def _symbol_from_ts_code(self, ts_code: Any) -> str:
        text = str(ts_code or "")
        return text.split(".", 1)[0] if "." in text else text
