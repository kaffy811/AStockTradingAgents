"""L3 domain analysis agents.

Agents consume ToolResponse DTOs only. They do not parse security names, query
databases, call providers, append disclaimers, render final Markdown, or persist
messages.
"""
from __future__ import annotations

from typing import Any

from app.agents.financial_runtime.contracts import (
    AgentResponse,
    FinancialFact,
    STATUS_FAILED,
    STATUS_PARTIAL_SUCCESS,
    STATUS_SUCCESS,
    ToolResponse,
    new_id,
)


def _tool(responses: dict[str, ToolResponse], capability: str) -> ToolResponse | None:
    return next((resp for resp in responses.values() if resp.capability == capability), None)


class FinancialReportAnalysisAgent:
    agent_type = "financial_report_analysis"

    async def run(self, *, trace_id: str, tool_responses: dict[str, ToolResponse]) -> AgentResponse:
        reports = _tool(tool_responses, "get_official_reports")
        fields = _tool(tool_responses, "get_structured_report_financials")
        evidence = _tool(tool_responses, "query_report_evidence")
        if not reports or reports.status != STATUS_SUCCESS:
            return AgentResponse(trace_id=trace_id, status=STATUS_FAILED, error_code="REPORT_NOT_FOUND", agent_run_id=new_id("agent"), agent_type=self.agent_type, error={"code": "REPORT_NOT_FOUND"})

        metrics: list[FinancialFact] = []
        for report_id, payload in ((fields.data if fields else {}).get("financial_fields_by_report") or {}).items():
            for field_key, item in (payload.get("fields") or {}).items():
                evidence_id = f"report:{report_id}:chunk:{item.get('source_chunk_id')}" if item.get("source_chunk_id") else f"report:{report_id}"
                metrics.append(FinancialFact(
                    trace_id=trace_id,
                    status=STATUS_SUCCESS,
                    fact_id=f"fact_{field_key}_{report_id}",
                    label=item.get("label") or field_key,
                    value=item.get("normalized_value"),
                    unit=item.get("unit") or "",
                    period=item.get("period_end"),
                    evidence_ids=[evidence_id],
                    provenance=[{"source": "official_report_structured_table", "report_id": report_id}],
                ))
        findings = []
        if metrics:
            findings.append({"type": "structured_metrics", "message": f"已提取 {len(metrics)} 个正式报告指标。"})
        chunks = ((evidence.data if evidence else {}).get("chunks") or [])
        if chunks:
            findings.append({"type": "report_evidence", "message": f"检索到 {len(chunks)} 条报告证据。"})
        return AgentResponse(
            trace_id=trace_id,
            status=STATUS_SUCCESS if metrics or chunks else STATUS_PARTIAL_SUCCESS,
            agent_run_id=new_id("agent"),
            agent_type=self.agent_type,
            findings=findings,
            metrics=metrics,
            limitations=[] if metrics else ["结构化指标证据不足，需查看报告原文片段。"],
            evidence_ids=[e for fact in metrics for e in fact.evidence_ids],
        )


class MultiCompanyFinancialComparisonAgent:
    agent_type = "multi_company_financial_comparison"

    async def run(self, *, trace_id: str, tool_responses: dict[str, ToolResponse]) -> AgentResponse:
        comparison = _tool(tool_responses, "compare_financials")
        if not comparison or comparison.status not in {STATUS_SUCCESS, STATUS_PARTIAL_SUCCESS}:
            return AgentResponse(trace_id=trace_id, status=STATUS_FAILED, error_code="COMPARISON_DATA_UNAVAILABLE", agent_run_id=new_id("agent"), agent_type=self.agent_type)
        rows = comparison.data.get("comparison_rows") or []
        evidence_ids = sorted({eid for row in rows for eid in (row.get("evidence_ids") or [])})
        return AgentResponse(
            trace_id=trace_id,
            status=STATUS_SUCCESS if rows and comparison.status == STATUS_SUCCESS else STATUS_PARTIAL_SUCCESS,
            agent_run_id=new_id("agent"),
            agent_type=self.agent_type,
            findings=[{"type": "comparison_table", "rows": rows}],
            evidence_ids=evidence_ids,
            limitations=[] if rows else ["可比结构化字段不足。"],
        )


class FundamentalAnalysisAgent:
    agent_type = "fundamental_analysis"

    async def run(self, *, trace_id: str, tool_responses: dict[str, ToolResponse]) -> AgentResponse:
        snapshot = _tool(tool_responses, "get_financial_snapshot")
        if not snapshot or snapshot.status not in {STATUS_SUCCESS, STATUS_PARTIAL_SUCCESS}:
            return AgentResponse(trace_id=trace_id, status=STATUS_FAILED, error_code="SNAPSHOT_UNAVAILABLE", agent_run_id=new_id("agent"), agent_type=self.agent_type)
        dashboard = snapshot.data.get("dashboard") or {}
        modules = dashboard.get("modules") or {}
        findings = [
            {"type": "module_available", "module": key, "latest_period": (value.get("latest") or {}).get("period")}
            for key, value in modules.items()
            if isinstance(value, dict) and value.get("latest")
        ][:6]
        return AgentResponse(trace_id=trace_id, status=STATUS_SUCCESS if findings else STATUS_PARTIAL_SUCCESS, agent_run_id=new_id("agent"), agent_type=self.agent_type, findings=findings)


class QuoteAnalysisAgent:
    agent_type = "quote_analysis"

    async def run(self, *, trace_id: str, tool_responses: dict[str, ToolResponse]) -> AgentResponse:
        quote = _tool(tool_responses, "get_quote_snapshot")
        if not quote or quote.status != STATUS_SUCCESS:
            return AgentResponse(trace_id=trace_id, status=STATUS_FAILED, error_code="QUOTE_UNAVAILABLE", agent_run_id=new_id("agent"), agent_type=self.agent_type)
        q = quote.data.get("quote") or {}
        return AgentResponse(
            trace_id=trace_id,
            status=STATUS_SUCCESS,
            agent_run_id=new_id("agent"),
            agent_type=self.agent_type,
            findings=[{"type": "quote", "quote": q, "entity": quote.data.get("entity") or {}}],
        )
