"""L4 Fact Fusion & deterministic answer rendering."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.agents.financial_runtime.contracts import (
    AgentResponse,
    FinancialFact,
    STATUS_FAILED,
    STATUS_SUCCESS,
    StructuredAnswer,
)


class FinancialFactGraph:
    def __init__(self) -> None:
        self.facts: list[FinancialFact] = []
        self.conflicts: list[dict[str, Any]] = []

    def add_agent_response(self, response: AgentResponse) -> None:
        self.facts.extend(response.metrics)
        self.conflicts.extend(response.conflicts)


class ConflictResolver:
    def resolve(self, graph: FinancialFactGraph) -> dict[str, Any]:
        if graph.conflicts:
            return {"conflict_state": "divergent", "conflicts": graph.conflicts}
        return {"conflict_state": "none", "conflicts": []}


class StructuredAnswerBuilder:
    def build(self, *, trace_id: str, intent: str, agent_response: AgentResponse, tool_data: dict[str, Any]) -> StructuredAnswer:
        if intent == "quote_query":
            return self._quote(trace_id, agent_response)
        if intent == "financial_comparison":
            return self._comparison(trace_id, agent_response)
        if intent in {"official_report_pdf", "financial_report_pdf"}:
            return self._pdf(trace_id, tool_data)
        if intent == "financial_report":
            return self._report(trace_id, agent_response, tool_data)
        return self._fundamental(trace_id, agent_response)

    def _quote(self, trace_id: str, response: AgentResponse) -> StructuredAnswer:
        quote = (response.findings[0] if response.findings else {}).get("quote") or {}
        entity = (response.findings[0] if response.findings else {}).get("entity") or {}
        name = entity.get("short_name") or entity.get("name") or entity.get("symbol") or "该证券"
        price = quote.get("current_price") or quote.get("price") or "暂无"
        pct = quote.get("pct_change") or quote.get("change_pct") or "暂无"
        return StructuredAnswer(
            trace_id=trace_id,
            status=STATUS_SUCCESS,
            title=f"{name}行情",
            conclusion=f"{name}当前价 {price}，涨跌幅 {pct}。",
            findings=["行情数据来自现有行情服务，实时性以数据源返回时间为准。"],
            sources=[{"label": "行情服务", "source_type": "quote"}],
        )

    def _pdf(self, trace_id: str, tool_data: dict[str, Any]) -> StructuredAnswer:
        latest_by_symbol = (tool_data.get("get_official_report_url") or {}).get("latest_by_symbol") or {}
        urls_by_symbol = (tool_data.get("get_official_report_url") or {}).get("urls_by_symbol") or {}
        report = next((item for item in latest_by_symbol.values() if item), None)
        pdf_url = next((url for url in urls_by_symbol.values() if url), None)
        if not report:
            return StructuredAnswer(trace_id=trace_id, status=STATUS_FAILED, error_code="REPORT_NOT_FOUND", title="官方报告", conclusion="当前没有找到该公司的正式年度报告。")
        return StructuredAnswer(
            trace_id=trace_id,
            status=STATUS_SUCCESS,
            title="官方报告入口",
            conclusion=f"已找到 {report.get('report_year')} 年正式年度报告，可通过官方 PDF 入口查看。",
            findings=[report.get("title") or "正式年度报告"],
            sources=[{"label": "官方 PDF", "url": pdf_url or report.get("pdf_url"), "source_type": "official_report"}],
        )

    def _report(self, trace_id: str, response: AgentResponse, tool_data: dict[str, Any]) -> StructuredAnswer:
        rows = [
            {"指标": fact.label, "数值": fact.value, "单位": fact.unit, "报告期": fact.period}
            for fact in response.metrics[:6]
        ]
        conclusion = "已基于正式报告结构化字段和报告证据生成财报摘要。" if rows else "已找到报告证据，但结构化指标不足。"
        sources = self._sources_from_facts(response.metrics)
        return StructuredAnswer(
            trace_id=trace_id,
            status=response.status,
            title="财报表现",
            conclusion=conclusion,
            tables=[{"columns": ["指标", "数值", "单位", "报告期"], "rows": rows}] if rows else [],
            findings=[item.get("message", "") for item in response.findings if item.get("message")],
            risks=list(response.limitations),
            sources=sources,
        )

    def _comparison(self, trace_id: str, response: AgentResponse) -> StructuredAnswer:
        comparison = next((item for item in response.findings if item.get("type") == "comparison_table"), {})
        rows = []
        for row in comparison.get("rows") or []:
            values = row.get("values") or {}
            rendered = {"指标": row.get("metric")}
            for report_id, value in values.items():
                rendered[str(report_id)] = "暂无可靠证据" if value is None else f"{value.get('value')} {value.get('unit') or ''}".strip()
            rows.append(rendered)
        columns = sorted({key for row in rows for key in row})
        if "指标" in columns:
            columns.remove("指标")
            columns.insert(0, "指标")
        return StructuredAnswer(
            trace_id=trace_id,
            status=response.status,
            title="财报对比",
            conclusion="已按正式报告结构化字段生成对比表，缺失值不填 0。",
            tables=[{"columns": columns, "rows": rows}] if rows else [],
            risks=list(response.limitations),
            sources=[{"label": "正式年度报告结构化字段", "source_type": "official_report"}],
        )

    def _fundamental(self, trace_id: str, response: AgentResponse) -> StructuredAnswer:
        return StructuredAnswer(
            trace_id=trace_id,
            status=response.status,
            title="财务快照",
            conclusion="已从 Company V2 财务历史服务获取可用模块。",
            findings=[f"{item.get('module')}：{item.get('latest_period') or '最新可用期'}" for item in response.findings],
            risks=list(response.limitations),
            sources=[{"label": "Company V2 财务历史服务", "source_type": "company_v2"}],
        )

    def _sources_from_facts(self, facts: list[FinancialFact]) -> list[dict[str, Any]]:
        sources: dict[str, dict[str, Any]] = {}
        for fact in facts:
            for provenance in fact.provenance:
                key = str(provenance)
                sources[key] = {"label": "正式报告结构化表格", **provenance}
        return list(sources.values()) or [{"label": "正式报告证据", "source_type": "official_report"}]


class AnswerRenderer:
    """Deterministic Markdown renderer. It is the sole body renderer."""

    def render(self, answer: StructuredAnswer) -> str:
        parts = [f"**{answer.conclusion}**"]
        for table in answer.tables:
            parts.append(self._table(table.get("columns") or [], table.get("rows") or []))
        if answer.findings:
            parts.append("主要发现：\n" + "\n".join(f"- {item}" for item in answer.findings[:5] if item))
        if answer.risks:
            parts.append("风险与限制：\n" + "\n".join(f"- {item}" for item in answer.risks[:5] if item))
        if answer.sources:
            labels = []
            for source in answer.sources[:5]:
                label = source.get("label") or source.get("source_type") or "数据来源"
                url = source.get("url")
                labels.append(f"- {label}" + (f"：{url}" if url else ""))
            parts.append("<details><summary>查看数据来源</summary>\n\n" + "\n".join(labels) + "\n\n</details>")
        return "\n\n".join(part for part in parts if part).strip()

    def _table(self, columns: list[str], rows: list[dict[str, Any]]) -> str:
        if not columns or not rows:
            return ""
        header = "| " + " | ".join(columns) + " |"
        sep = "| " + " | ".join("---" for _ in columns) + " |"
        body = [
            "| " + " | ".join(str(row.get(col, "暂无可靠证据")) for col in columns) + " |"
            for row in rows
        ]
        return "\n".join([header, sep, *body])


structured_answer_builder = StructuredAnswerBuilder()
answer_renderer = AnswerRenderer()
