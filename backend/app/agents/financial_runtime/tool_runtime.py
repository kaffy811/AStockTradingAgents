"""L2 Financial Data Fabric / Tool Runtime."""
from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any, Awaitable, Callable

from app.agents.financial_runtime.contracts import (
    FinancialSessionContext,
    SecurityEntity,
    STATUS_FAILED,
    STATUS_PARTIAL_SUCCESS,
    STATUS_SUCCESS,
    ToolRequest,
    ToolResponse,
    new_id,
    utc_now,
)
from app.core.database import AsyncSessionLocal
from app.services.company_chat_data_service import company_chat_data_service
from app.services.company_v2_report_evidence_service import company_v2_report_evidence_service
from app.services.official_report_domain_service import official_report_domain_service
from app.services.report_financial_table_extractor_tool import report_financial_table_extractor_tool
from app.services.security_entity_resolver import security_entity_resolver
from app.services.stock_data_service import stock_data_service


ToolHandler = Callable[[ToolRequest, FinancialSessionContext], Awaitable[ToolResponse]]


def _entity_dict(entity: SecurityEntity | dict[str, Any] | None) -> dict[str, Any]:
    if entity is None:
        return {}
    if isinstance(entity, dict):
        return entity
    return asdict(entity)


def _ts_code(entity: SecurityEntity | dict[str, Any] | None) -> str:
    data = _entity_dict(entity)
    if data.get("ts_code"):
        return str(data["ts_code"])
    symbol = str(data.get("symbol") or "")
    market = str(data.get("market") or "CN").upper()
    if market == "CN":
        if symbol.startswith(("6", "5", "9")):
            return f"{symbol}.SH"
        if symbol.startswith(("0", "2", "3")):
            return f"{symbol}.SZ"
        if symbol.startswith(("4", "8")):
            return f"{symbol}.BJ"
    return symbol


def _success(
    req: ToolRequest,
    data: dict[str, Any],
    *,
    latency_ms: int,
    provenance: list[dict[str, Any]] | None = None,
    warnings: list[dict[str, Any]] | None = None,
    quality: dict[str, Any] | None = None,
) -> ToolResponse:
    return ToolResponse(
        trace_id=req.trace_id,
        status=STATUS_SUCCESS,
        tool_call_id=req.tool_call_id,
        capability=req.capability,
        data=data,
        provenance=provenance or [],
        freshness={"as_of": utc_now()},
        quality=quality or {"status": "usable"},
        warnings=warnings or [],
        latency_ms=latency_ms,
    )


def _failure(req: ToolRequest, code: str, message: str, *, latency_ms: int) -> ToolResponse:
    return ToolResponse(
        trace_id=req.trace_id,
        status=STATUS_FAILED,
        error_code=code,
        tool_call_id=req.tool_call_id,
        capability=req.capability,
        error={"code": code, "message": message},
        latency_ms=latency_ms,
        quality={"status": "unavailable"},
    )


def _partial(req: ToolRequest, data: dict[str, Any], *, latency_ms: int, provenance: list[dict[str, Any]] | None = None, warnings: list[dict[str, Any]] | None = None, error_code: str | None = None) -> ToolResponse:
    return ToolResponse(
        trace_id=req.trace_id,
        status=STATUS_PARTIAL_SUCCESS,
        tool_call_id=req.tool_call_id,
        capability=req.capability,
        data=data,
        provenance=provenance or [],
        freshness={"as_of": utc_now()},
        quality={"status": "partial", "warnings": warnings or []},
        warnings=warnings or [],
        error={"code": error_code, "message": error_code} if error_code else None,
        error_code=error_code,
        latency_ms=latency_ms,
    )


class FinancialToolRegistry:
    """Capability registry. Tools call shared domain services, not providers."""

    def __init__(self) -> None:
        self._handlers: dict[str, ToolHandler] = {
            "resolve_security": self.resolve_security,
            "get_market_clock": self.get_market_clock,
            "get_quote_snapshot": self.get_quote_snapshot,
            "get_market_history": self.unavailable_tool,
            "get_company_profile": self.get_company_profile,
            "get_financial_snapshot": self.get_financial_snapshot,
            "get_financial_history": self.get_financial_history,
            "get_cashflow_quality": self.get_financial_history,
            "get_valuation": self.get_financial_history,
            "get_official_reports": self.get_official_reports,
            "get_latest_official_report": self.get_latest_official_report,
            "get_official_report_url": self.get_official_report_url,
            "get_structured_report_financials": self.get_structured_report_financials,
            "query_report_evidence": self.query_report_evidence,
            "compare_financials": self.compare_financials,
            "align_financial_periods": self.compare_financials,
            "compare_financial_fields": self.compare_financials,
            "get_company_news": self.unavailable_tool,
            "get_announcements": self.unavailable_tool,
            "get_market_events": self.unavailable_tool,
            "get_industry_snapshot": self.unavailable_tool,
            "get_peer_companies": self.unavailable_tool,
            "get_industry_benchmark": self.unavailable_tool,
            "get_peers": self.unavailable_tool,
            "get_kline": self.unavailable_tool,
            "get_technical_indicators": self.unavailable_tool,
            "get_capital_flow": self.unavailable_tool,
            "get_watchlist": self.unavailable_tool,
            "update_watchlist": self.unavailable_tool,
        }

    @property
    def capabilities(self) -> list[str]:
        return sorted(self._handlers)

    async def call(self, capability: str, parameters: dict[str, Any], *, trace_id: str, context: FinancialSessionContext) -> ToolResponse:
        req = ToolRequest(
            trace_id=trace_id,
            status="pending",
            tool_call_id=new_id("tool"),
            capability=capability,
            parameters=parameters,
        )
        handler = self._handlers.get(capability, self.unavailable_tool)
        return await handler(req, context)

    async def resolve_security(self, req: ToolRequest, context: FinancialSessionContext) -> ToolResponse:
        started = time.perf_counter()
        query = str(req.parameters.get("query") or "")
        async with AsyncSessionLocal() as db:
            resolved = await security_entity_resolver.resolve(db, query, min_confidence=0.72)
        return _success(req, resolved, latency_ms=int((time.perf_counter() - started) * 1000), provenance=[{"source": "security_entity_resolver"}])

    async def get_market_clock(self, req: ToolRequest, context: FinancialSessionContext) -> ToolResponse:
        started = time.perf_counter()
        return _success(req, {"market": context.active_market or "CN", "is_open": None}, latency_ms=int((time.perf_counter() - started) * 1000))

    async def get_quote_snapshot(self, req: ToolRequest, context: FinancialSessionContext) -> ToolResponse:
        started = time.perf_counter()
        entity = req.parameters.get("entity") or context.primary_entity
        data = _entity_dict(entity)
        symbol = str(data.get("symbol") or "")
        market = str(data.get("market") or "CN").upper()
        if not symbol:
            return _failure(req, "ENTITY_NOT_RESOLVED", "缺少证券实体", latency_ms=int((time.perf_counter() - started) * 1000))
        quote = stock_data_service.get_quote_optional(market, symbol)
        if not quote:
            return _failure(req, "QUOTE_UNAVAILABLE", "行情数据暂不可用", latency_ms=int((time.perf_counter() - started) * 1000))
        return _success(
            req,
            {"entity": data, "quote": quote},
            latency_ms=int((time.perf_counter() - started) * 1000),
            provenance=[{"source": "stock_data_service", "market": market, "symbol": symbol}],
        )

    async def get_company_profile(self, req: ToolRequest, context: FinancialSessionContext) -> ToolResponse:
        started = time.perf_counter()
        entity = req.parameters.get("entity") or context.primary_entity
        data = _entity_dict(entity)
        if not data.get("symbol"):
            return _failure(req, "ENTITY_NOT_RESOLVED", "缺少证券实体", latency_ms=int((time.perf_counter() - started) * 1000))
        domains = await company_chat_data_service.get_company_domains(data)
        return _success(
            req,
            {"entity": data, "profile": domains.get("company_profile") or {}, "availability": domains.get("availability") or {}},
            latency_ms=int((time.perf_counter() - started) * 1000),
            provenance=[{"source": "company_chat_data_service", "capability": "get_company_profile"}],
            warnings=domains.get("warnings") or [],
        )

    async def get_financial_snapshot(self, req: ToolRequest, context: FinancialSessionContext) -> ToolResponse:
        started = time.perf_counter()
        entity = req.parameters.get("entity") or context.primary_entity
        data = _entity_dict(entity)
        symbol = str(data.get("symbol") or "")
        if not symbol:
            return _failure(req, "ENTITY_NOT_RESOLVED", "缺少证券实体", latency_ms=int((time.perf_counter() - started) * 1000))
        domains = await company_chat_data_service.get_company_domains(data)
        payload = {
            "entity": data,
            "dashboard": domains.get("financial_history") or {},
            "financial_fields": domains.get("financial_fields") or {},
            "availability": domains.get("availability") or {},
        }
        status = (domains.get("availability") or {}).get("financial_snapshot")
        if status == "available":
            return _success(req, payload, latency_ms=int((time.perf_counter() - started) * 1000), provenance=[{"source": "company_chat_data_service", "domain": "company_v2"}], warnings=domains.get("warnings") or [])
        if domains.get("quote_snapshot") or domains.get("company_profile"):
            return _partial(req, payload, latency_ms=int((time.perf_counter() - started) * 1000), provenance=[{"source": "company_chat_data_service", "domain": "company_v2"}], warnings=domains.get("warnings") or [{"error_code": "FINANCIAL_DATA_PARTIAL"}], error_code="FINANCIAL_DATA_PARTIAL")
        return _failure(req, "FINANCIAL_SNAPSHOT_UNAVAILABLE", "财务快照暂不可用", latency_ms=int((time.perf_counter() - started) * 1000))

    async def get_financial_history(self, req: ToolRequest, context: FinancialSessionContext) -> ToolResponse:
        return await self.get_financial_snapshot(req, context)

    async def get_official_reports(self, req: ToolRequest, context: FinancialSessionContext) -> ToolResponse:
        started = time.perf_counter()
        timings: dict[str, int] = {
            "resolver_ms": 0,
            "report_selection_ms": 0,
            "db_query_ms": 0,
            "cache_lookup_ms": 0,
            "official_domain_validation_ms": 0,
            "external_network_ms": 0,
            "adapter_overhead_ms": 0,
        }
        entities = req.parameters.get("entities") or [req.parameters.get("entity") or context.primary_entity]
        reports_by_symbol: dict[str, list[dict[str, Any]]] = {}
        async with AsyncSessionLocal() as db:
            if context.active_report_id:
                db_started = time.perf_counter()
                report = await official_report_domain_service.get_official_report_by_id(db, report_id=context.active_report_id)
                timings["db_query_ms"] += int((time.perf_counter() - db_started) * 1000)
                if report:
                    selection_started = time.perf_counter()
                    report_ts_code = str(report.get("ts_code") or "")
                    requested = {_ts_code(entity) for entity in entities if _ts_code(entity)}
                    if not requested or report_ts_code in requested:
                        reports_by_symbol[report_ts_code] = [report]
                    timings["report_selection_ms"] += int((time.perf_counter() - selection_started) * 1000)
                    return _success(
                        req,
                        {"reports_by_symbol": reports_by_symbol, "selection_mode": "active_report_id"},
                        latency_ms=int((time.perf_counter() - started) * 1000),
                        provenance=[{"source": "report_document_service", "selection_mode": "active_report_id"}],
                        quality={"status": "usable", "latency_breakdown": {**timings, "total_ms": int((time.perf_counter() - started) * 1000)}},
                    )
            for entity in entities:
                data = _entity_dict(entity)
                ts_code = _ts_code(data)
                if not ts_code:
                    continue
                db_started = time.perf_counter()
                reports_by_symbol[ts_code] = await official_report_domain_service.list_official_annual_reports(db, ts_code=ts_code, limit=8)
                timings["db_query_ms"] += int((time.perf_counter() - db_started) * 1000)
        return _success(
            req,
            {"reports_by_symbol": reports_by_symbol, "selection_mode": "symbol_annual_list"},
            latency_ms=int((time.perf_counter() - started) * 1000),
            provenance=[{"source": "report_document_service", "selection_mode": "symbol_annual_list"}],
            quality={"status": "usable", "latency_breakdown": {**timings, "total_ms": int((time.perf_counter() - started) * 1000)}},
        )

    async def get_latest_official_report(self, req: ToolRequest, context: FinancialSessionContext) -> ToolResponse:
        started = time.perf_counter()
        reports = await self.get_official_reports(req, context)
        latest_by_symbol = {
            symbol: (items[0] if items else None)
            for symbol, items in (reports.data.get("reports_by_symbol") or {}).items()
        }
        return _success(req, {"latest_by_symbol": latest_by_symbol, "reports": reports.data}, latency_ms=int((time.perf_counter() - started) * 1000), provenance=[{"source": "official_report_domain_service"}])

    async def get_official_report_url(self, req: ToolRequest, context: FinancialSessionContext) -> ToolResponse:
        started = time.perf_counter()
        latest = await self.get_latest_official_report(req, context)
        urls = {
            symbol: ((report or {}).get("pdf_url") or (report or {}).get("official_url"))
            for symbol, report in (latest.data.get("latest_by_symbol") or {}).items()
        }
        return _success(req, {"urls_by_symbol": urls, "latest_by_symbol": latest.data.get("latest_by_symbol") or {}}, latency_ms=int((time.perf_counter() - started) * 1000), provenance=[{"source": "official_report_domain_service"}])

    async def get_structured_report_financials(self, req: ToolRequest, context: FinancialSessionContext) -> ToolResponse:
        started = time.perf_counter()
        try:
            reports_resp = await self.get_official_reports(req, context)
        except Exception as exc:  # noqa: BLE001
            return _partial(req, {"reports": {}, "financial_fields_by_report": {}}, latency_ms=int((time.perf_counter() - started) * 1000), warnings=[{"error_code": "RAG_DATABASE_UNAVAILABLE", "message": str(exc)[:160]}], error_code="RAG_DATABASE_UNAVAILABLE")
        extracted_by_report: dict[str, dict[str, Any]] = {}
        for reports in (reports_resp.data.get("reports_by_symbol") or {}).values():
            if not reports:
                continue
            report = reports[0]
            try:
                evidence = await company_v2_report_evidence_service.query_report_evidence(
                    report_id=int(report["report_id"]),
                    question="主要会计数据和财务指标 营业收入 归属于上市公司股东的净利润 经营活动产生的现金流量净额",
                    top_k=8,
                )
            except Exception as exc:  # noqa: BLE001
                return _partial(req, {"reports": reports_resp.data, "financial_fields_by_report": extracted_by_report}, latency_ms=int((time.perf_counter() - started) * 1000), provenance=[{"source": "report_financial_table_extractor_tool"}], warnings=[{"error_code": "RAG_DATABASE_UNAVAILABLE", "message": str(exc)[:160]}], error_code="RAG_DATABASE_UNAVAILABLE")
            chunks = [
                {
                    "chunk_id": chunk.get("chunk_id"),
                    "rag_document_id": chunk.get("rag_document_id"),
                    "page_start": chunk.get("page_start"),
                    "section_title": chunk.get("section_title"),
                    "content": chunk.get("text_excerpt"),
                }
                for chunk in evidence.get("chunks", [])
            ]
            extracted_by_report[str(report["report_id"])] = report_financial_table_extractor_tool.extract_from_chunks(
                report_id=report["report_id"],
                chunks=chunks,
                report_year=report.get("report_year"),
            )
        if extracted_by_report:
            return _success(req, {"reports": reports_resp.data, "financial_fields_by_report": extracted_by_report}, latency_ms=int((time.perf_counter() - started) * 1000), provenance=[{"source": "report_financial_table_extractor_tool"}])
        return _partial(req, {"reports": reports_resp.data, "financial_fields_by_report": extracted_by_report}, latency_ms=int((time.perf_counter() - started) * 1000), provenance=[{"source": "report_financial_table_extractor_tool"}], error_code="STRUCTURED_REPORT_FIELDS_UNAVAILABLE")

    async def query_report_evidence(self, req: ToolRequest, context: FinancialSessionContext) -> ToolResponse:
        started = time.perf_counter()
        reports_resp = await self.get_official_reports(req, context)
        first_report = next((items[0] for items in (reports_resp.data.get("reports_by_symbol") or {}).values() if items), None)
        if not first_report:
            return _failure(req, "REPORT_NOT_FOUND", "未找到正式报告", latency_ms=int((time.perf_counter() - started) * 1000))
        evidence = await company_v2_report_evidence_service.query_report_evidence(
            report_id=int(first_report["report_id"]),
            question=str(req.parameters.get("question") or ""),
            top_k=6,
        )
        return _success(req, evidence, latency_ms=int((time.perf_counter() - started) * 1000), provenance=[{"source": "company_v2_report_evidence_service"}])

    async def compare_financials(self, req: ToolRequest, context: FinancialSessionContext) -> ToolResponse:
        started = time.perf_counter()
        fields_resp = await self.get_structured_report_financials(req, context)
        rows: list[dict[str, Any]] = []
        by_report = fields_resp.data.get("financial_fields_by_report") or {}
        if fields_resp.status != STATUS_SUCCESS or not by_report:
            entities = req.parameters.get("entities") or [context.primary_entity, *context.secondary_entities]
            fallback = await company_chat_data_service.compare_from_company_data([_entity_dict(e) for e in entities if e])
            return _partial(
                req,
                {"comparison_rows": fallback.get("comparison_rows") or [], "financial_fields": {}, "availability": fallback.get("availability") or {}},
                latency_ms=int((time.perf_counter() - started) * 1000),
                provenance=[{"source": "company_chat_data_service", "fallback": "company_v2_cached_data"}],
                warnings=fallback.get("warnings") or [{"error_code": "RAG_DATABASE_UNAVAILABLE"}],
                error_code="RAG_DATABASE_UNAVAILABLE",
            )
        metrics = ["revenue", "parent_net_profit", "operating_cashflow", "roe", "eps"]
        for metric in metrics:
            row = {"metric": metric, "values": {}, "evidence_ids": []}
            for report_id, payload in by_report.items():
                field = (payload.get("fields") or {}).get(metric)
                if field:
                    row["values"][report_id] = {
                        "value": field.get("normalized_value"),
                        "unit": field.get("unit"),
                        "period": field.get("period_end"),
                        "label": field.get("label"),
                    }
                    if field.get("source_chunk_id"):
                        row["evidence_ids"].append(f"report:{report_id}:chunk:{field['source_chunk_id']}")
                else:
                    row["values"][report_id] = None
            rows.append(row)
        return _success(req, {"comparison_rows": rows, "financial_fields": by_report}, latency_ms=int((time.perf_counter() - started) * 1000), provenance=[{"source": "financial_tool_registry.compare_financials"}])

    async def unavailable_tool(self, req: ToolRequest, context: FinancialSessionContext) -> ToolResponse:
        started = time.perf_counter()
        return _failure(req, "CAPABILITY_NOT_MIGRATED", f"{req.capability} 尚未迁移到 layered_v1", latency_ms=int((time.perf_counter() - started) * 1000))


financial_tool_registry = FinancialToolRegistry()
