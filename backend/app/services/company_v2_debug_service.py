from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.error_codes import (
    AI_KEY_MISSING,
    ALL_NULL_ROWS,
    CACHE_UNAVAILABLE,
    DATA_PACK_EMPTY,
    MAPPING_ERROR,
    PDF_NOT_FOUND,
    PROVIDER_EMPTY,
    REPORT_PDF_NOT_FOUND,
    REPORT_NOT_INGESTED,
    SHARE_CAPITAL_MISSING,
)
from app.core.structured_debug_logger import current_request_id, log_company_v2_event, sanitize_debug_payload
from app.datasource.debug_provider_runner import run_provider_with_debug
from app.datasource.tushare_client import _to_ts_code
from app.schemas.company_v2_debug import (
    CompanyV2Completion,
    CompanyV2DebugEnvelope,
    CompanyV2DebugMeta,
    CompanyV2Error,
    CompanyV2Normalized,
    CompanyV2Render,
    CompanyV2SourceAttempt,
)
from app.services.cache_service import cache_service, cache_status
from app.services.company_v2_debug_diagnosis_service import diagnose_company_v2_envelope
from app.services.company_v2_industry_metric_applicability import apply_applicability_to_coverage
from app.services.company_v2_computed_field_registry import compute_company_v2_fields
from app.services.company_v2_data_validation_engine import validate_company_v2_envelope
from app.services.company_v2_formatter_registry import format_field
from app.services.company_v2_field_metadata import field_metadata_payload
from app.services.company_v2_normalizers import normalize_baostock_aggregate
from app.services.company_v2_snapshot_cache_service import company_v2_snapshot_cache_service

MODULE_KEYS = [
    "quote_overview",
    "valuation",
    "profitability",
    "growth",
    "cashflow_quality",
    "solvency",
    "operation_capability",
    "dupont",
    "report_documents",
    "ai_analysis_status",
]
# report_rag is no longer an independent visible module.
# Its data (chunks_count, embedding_count, rag_status) is merged into report_documents.
_REPORT_RAG_HIDDEN = True

CORE_FIELDS: dict[str, list[str]] = {
    "quote_overview": [
        "latest_price", "recent_close", "open", "high", "low", "volume", "amount",
        "pct_chg", "turnover", "pe_ttm", "pb", "ps_ttm", "pcf_ncf_ttm",
        "market_cap", "float_market_cap",
    ],
    "valuation": ["pe_ttm", "pb", "ps_ttm", "pcf_ncf_ttm", "market_cap", "float_market_cap"],
    "profitability": ["roe", "gross_margin", "net_margin", "roa", "roic"],
    # Phase 6T-E: 对齐 BaoStock 真实口径（growth 表无营收同比/基本每股收益）
    "growth": ["net_profit_yoy", "parent_net_profit_yoy", "equity_yoy", "asset_yoy", "eps_yoy"],
    "cashflow_quality": ["ocf_to_np", "ocf_to_revenue"],
    "solvency": ["current_ratio", "quick_ratio", "cash_ratio", "debt_ratio", "equity_multiplier"],
    "operation_capability": ["asset_turnover", "inventory_turnover", "receivable_turnover", "total_asset_turnover"],
    "dupont": ["roe", "net_margin", "asset_turnover", "equity_multiplier"],
    "report_documents": ["documents_count", "chunks_count", "embedding_count"],
    "report_rag": ["documents_count", "chunks_count", "embedding_count"],
    "ai_analysis_status": ["summary"],
}

RAW_PROVIDERS = ("baostock", "akshare", "tencent", "sina", "eastmoney", "pdf_metrics")

def _empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() in ("", "—", "--", "nan", "NaN"):
        return True
    if isinstance(value, float) and value != value:
        return True
    return False


def has_displayable_data(rows: list[dict[str, Any]], core_fields: list[str]) -> bool:
    for row in rows:
        for field in core_fields:
            if field in row and not _empty(row.get(field)):
                return True
    return False


def _is_report_status_module(module_key: str) -> bool:
    return module_key in ("report_documents",)


def _to_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _field_display(field: str, value: Any) -> dict[str, Any]:
    return format_field(field, value)


def _apply_display_metadata(module_key: str, rows: list[dict[str, Any]], fields: dict[str, Any]) -> None:
    for field, item in fields.items():
        if isinstance(item, dict):
            item.update(format_field(field, item.get("value")))
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_keys = [
            key for key in row.keys()
            if key not in {"display_fields", "source_field_map"} and not str(key).endswith("_source")
        ]
        display_fields: dict[str, Any] = row.setdefault("display_fields", {})
        for field in set(CORE_FIELDS.get(module_key, [])) | set(row_keys):
            if field in row:
                display_fields[field] = format_field(field, row.get(field))


def _latest_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return rows[0] if rows else {}


def _source_attempt(raw: dict[str, Any]) -> CompanyV2SourceAttempt:
    return CompanyV2SourceAttempt(
        provider=raw.get("provider") or "unknown",
        endpoint=raw.get("endpoint") or "unknown",
        attempted=raw.get("attempted", True),
        success=raw.get("success", False),
        status=raw.get("status"),
        started_at=raw.get("started_at"),
        ended_at=raw.get("ended_at"),
        elapsed_ms=raw.get("elapsed_ms"),
        latency_ms=raw.get("latency_ms", 0) or 0,
        rows_count=raw.get("rows_count", 0) or 0,
        columns=raw.get("columns") or [],
        non_null_fields=raw.get("non_null_fields") or [],
        error_code=raw.get("error_code"),
        error_message=raw.get("error_message"),
        cache_hit=raw.get("cache_hit", False),
        cache_stale=raw.get("cache_stale", False),
        cache_status=raw.get("cache_status"),
        raw_type=raw.get("raw_type"),
        raw_shape=raw.get("raw_shape"),
        detached_timeout=raw.get("detached_timeout", False),
        aggregate_source_id=raw.get("aggregate_source_id"),
        data_success=raw.get("data_success"),
    )


def _provider_data_success(result: dict[str, Any]) -> bool:
    if result.get("error_code") or result.get("status") in {"timeout", "network_error", "schema_error", "exception", "empty"}:
        return False
    sample = result.get("raw_sample") or []
    if not sample:
        return False
    if isinstance(sample, list) and len(sample) >= 2 and isinstance(sample[1], dict):
        meta = sample[1]
        if meta.get("status") in {"failed", "empty", "timeout"} or meta.get("reason_code"):
            return False
    first = sample[0] if isinstance(sample, list) else sample
    return _business_value_present(first)


def _business_value_present(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_business_value_present(item) for item in value.values())
    if isinstance(value, list):
        return any(_business_value_present(item) for item in value)
    return not _empty(value)


def _field_metadata(
    field: str,
    value: Any,
    *,
    source: str,
    provider: str | None = None,
    provider_method: str | None = None,
    raw_field: str | None = None,
    computed: bool = False,
    computed_formula: str | None = None,
    fallback_from: str | None = None,
    confidence: float | None = None,
    formula_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = formula_context or {}
    metadata = {
        "value": value,
        **format_field(field, value),
        "field_key": field,
        "field_metadata": field_metadata_payload(field),
        "source": source,
        "provider": provider or ("computed" if computed else ("baostock" if source == "baostock_aggregate" else source)),
        "provider_method": provider_method,
        "raw_field": raw_field,
        "computed": computed,
        "computed_formula": computed_formula,
        "fallback_from": fallback_from,
        "confidence": confidence if confidence is not None else (0.75 if computed else 0.95),
        "formula_context": context,
        "period_end": context.get("period"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    return metadata


def _formula_context_from_row(
    module_key: str,
    field: str,
    source_row: dict[str, Any],
    *,
    source: str,
    provider: str | None,
    raw_field: str | None,
) -> dict[str, Any]:
    period = source_row.get("period") or source_row.get("stat_date")
    report_period_type = "annual" if str(period or "").endswith("12-31") else ("quarterly" if period else "unknown")
    provider_definition = "dupont_provider_defined" if module_key == "dupont" and str(raw_field or "").startswith("dupont_") else "unknown"
    return {
        "period": period,
        "report_period_type": report_period_type,
        "value_basis": source_row.get("value_basis") or "unknown",
        "unit": "unknown",
        "percent_scale": "unknown",
        "provider_definition": provider_definition,
        "source_module": module_key,
        "source_provider": provider or source,
        "raw_field": raw_field,
    }


def _add_raw(raw_bucket: dict[str, Any], provider: str, result: dict[str, Any], include_raw: bool) -> None:
    visible = {
        "endpoint": result.get("endpoint"),
        "raw_type": result.get("raw_type"),
        "raw_shape": result.get("raw_shape"),
        "columns": result.get("columns") or [],
        "rows_count": result.get("rows_count", 0),
        "status": result.get("status"),
        "started_at": result.get("started_at"),
        "ended_at": result.get("ended_at"),
        "elapsed_ms": result.get("elapsed_ms"),
        "detached_timeout": result.get("detached_timeout", False),
        "raw_sample": result.get("raw_sample", []),
        "error_code": result.get("error_code"),
        "error_message": result.get("error_message"),
    }
    if include_raw and "raw_full" in result:
        visible["raw_full"] = result["raw_full"]
    existing = raw_bucket.setdefault(provider, [])
    if isinstance(existing, list):
        existing.append(visible)
    else:
        raw_bucket[provider] = [visible]


def _fill_fields(
    module_key: str,
    rows: list[dict[str, Any]],
    metrics: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
) -> tuple[dict, dict, dict]:
    fields: dict[str, Any] = {}
    fallback_chain: dict[str, Any] = {}
    computed: dict[str, Any] = {}
    source_row = _latest_row(rows)
    source_map = source_row.get("source_field_map") if isinstance(source_row.get("source_field_map"), dict) else {}
    for field in CORE_FIELDS.get(module_key, []):
        field_number = _to_number(metrics.get(field) if field in metrics else source_row.get(field))
        if module_key in ("report_documents", "report_rag") and field == "documents_count" and (field_number or 0) <= 0:
            continue
        if module_key in ("report_documents", "report_rag") and field in ("chunks_count", "embedding_count") and (field_number or 0) <= 0:
            continue
        value = metrics.get(field)
        if _empty(value):
            value = source_row.get(field)
        if not _empty(value):
            source = source_row.get(f"{field}_source") or metrics.get(f"{field}_source") or source_row.get("source") or "provider"
            fields[field] = _field_metadata(
                field,
                value,
                source=source,
                provider="baostock" if source == "baostock_aggregate" else source,
                provider_method="get_all_financial_indicators" if source == "baostock_aggregate" else None,
                raw_field=source_map.get(field),
                computed=False,
                formula_context=_formula_context_from_row(
                    module_key,
                    field,
                    source_row,
                    source=source,
                    provider="baostock" if source == "baostock_aggregate" else source,
                    raw_field=source_map.get(field),
                ),
            )
            fallback_chain[field] = fields[field]["source"]
    share_capital_context = (context or {}).get("share_capital_context") if context else None
    if share_capital_context is None and (
        not _empty(source_row.get("total_share")) or not _empty(source_row.get("float_share")) or not _empty(source_row.get("liqa_share"))
    ):
        share_capital_context = {
            "total_share": source_row.get("total_share"),
            "float_share": source_row.get("float_share") or source_row.get("liqa_share"),
            "source": source_row.get("total_share_source") or source_row.get("source") or "provider",
            "provider": source_row.get("source") or "provider",
        }
    computed_fields, formulas, computed_missing = compute_company_v2_fields(
        module_key,
        fields,
        share_capital_context=share_capital_context,
    )
    for field, item in computed_fields.items():
        fields[field] = _field_metadata(
            field,
            item.get("value"),
            source="computed",
            provider=item.get("provider") or "computed",
            provider_method=item.get("provider_method"),
            raw_field=item.get("raw_field"),
            computed=True,
            computed_formula=item.get("computed_formula"),
            fallback_from=item.get("fallback_from"),
            confidence=item.get("confidence"),
            formula_context={
                "period": source_row.get("period") or source_row.get("stat_date"),
                "report_period_type": "annual" if str(source_row.get("period") or source_row.get("stat_date") or "").endswith("12-31") else ("quarterly" if (source_row.get("period") or source_row.get("stat_date")) else "unknown"),
                "value_basis": "computed",
                "unit": "unknown",
                "percent_scale": "unknown",
                "provider_definition": "computed_formula",
                "source_module": module_key,
                "source_provider": item.get("provider") or "computed",
                "raw_field": item.get("raw_field"),
            },
        )
        fields[field]["source_fields"] = item.get("source_fields") or []
        fallback_chain[field] = item.get("fallback_from") or "computed"
    computed.update(formulas)
    missing = {
        f: (computed_missing.get(f) or (SHARE_CAPITAL_MISSING if f in ("market_cap", "float_market_cap") else "FIELD_MISSING"))
        for f in CORE_FIELDS.get(module_key, [])
        if f not in fields
    }
    return fields, missing, computed


def _field_trace(fields: dict[str, Any], source_chain: list[CompanyV2SourceAttempt]) -> dict[str, Any]:
    traces: dict[str, Any] = {}
    for field, item in fields.items():
        if not isinstance(item, dict):
            continue
        provider = item.get("provider")
        source_chain_index = next(
            (idx for idx, source in enumerate(source_chain) if source.provider == provider or source.provider == item.get("source")),
            0,
        )
        traces[field] = {
            "provider": provider,
            "provider_method": item.get("provider_method"),
            "raw_field": item.get("raw_field"),
            "normalized_field": field,
            "formatter": item.get("display_type"),
            "computed": bool(item.get("computed")),
            "computed_formula": item.get("computed_formula"),
            "source_fields": item.get("source_fields") or [],
            "fallback_from": item.get("fallback_from"),
            "source_chain_index": source_chain_index,
            "confidence": item.get("confidence"),
            "formula_context": item.get("formula_context") or {},
        }
    return traces


def _coverage(module_key: str, fields: dict[str, Any], missing: dict[str, Any], computed: dict[str, Any]) -> dict[str, Any]:
    required = CORE_FIELDS.get(module_key, [])
    filled = [
        field for field in required
        if field in fields and not _empty((fields.get(field) or {}).get("value"))
    ]
    computed_list = [field for field in computed if field in filled]
    required_count = len(required)
    coverage_pct = round((len(filled) / required_count * 100), 2) if required_count else 100.0
    return {
        "required_fields": required_count,
        "filled_fields": len(filled),
        "computed_fields": len(computed_list),
        "missing_fields": len(missing),
        "coverage_pct": coverage_pct,
        "required_field_list": required,
        "filled_field_list": filled,
        "computed_field_list": computed_list,
        "missing_field_map": missing,
    }


def _provider_summary(source_chain: list[CompanyV2SourceAttempt], fields: dict[str, Any], module_key: str) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    used_by_provider: dict[str, int] = {}
    for item in fields.values():
        if isinstance(item, dict):
            provider = item.get("provider") or item.get("source") or "provider"
            used_by_provider[provider] = used_by_provider.get(provider, 0) + 1
    for source in source_chain:
        provider = source.provider
        data_success = bool(source.data_success if source.data_success is not None else (source.success and source.rows_count > 0 and not source.error_code))
        fields_available = len(source.non_null_fields or source.columns or [])
        fields_used = used_by_provider.get(provider, 0)
        if provider == "baostock" and used_by_provider.get("baostock_aggregate"):
            fields_used += used_by_provider["baostock_aggregate"]
        summary[provider] = {
            "attempted": source.attempted,
            "success": source.success,
            "data_success": data_success,
            "rows": source.rows_count,
            "fields_available": fields_available,
            "fields_mapped": len(fields),
            "fields_used": fields_used,
            "missing": max(0, len(CORE_FIELDS.get(module_key, [])) - len(fields)),
            "timeout": source.error_code == "PROVIDER_TIMEOUT" or source.status == "timeout",
            "network_error": source.error_code == "PROVIDER_NETWORK_ERROR" or source.status == "network_error",
            "cache_hit": source.cache_hit,
            "reason_code": source.error_code,
        }
    return summary


def _render(module_key: str, rows: list[dict[str, Any]], fields: dict[str, Any]) -> CompanyV2Render:
    if module_key in ("report_documents", "report_rag"):
        row = rows[0] if rows else {}
        documents_count = _to_number(row.get("documents_count"))
        chunks_count = _to_number(row.get("chunks_count"))
        embedding_count = _to_number(row.get("embedding_count"))
        has_docs = (documents_count or 0) > 0
        has_rag = (chunks_count or 0) > 0 and (embedding_count or 0) > 0
        # Module is always renderable so the UI can show status + discover button
        visible_fields = ["documents_count"]
        if has_rag:
            visible_fields += ["chunks_count", "embedding_count"]
        # Determine overall readiness reason
        if has_docs and has_rag:
            reason = None
        elif has_docs:
            reason = REPORT_NOT_INGESTED
        else:
            reason = REPORT_PDF_NOT_FOUND
        displayable = has_rag if module_key == "report_rag" else has_docs
        return CompanyV2Render(
            renderable=True,
            chart_renderable=False,
            table_renderable=displayable,
            has_displayable_data=displayable,
            visible_fields=visible_fields,
            hidden_fields=[f for f in ["documents_count", "chunks_count", "embedding_count"] if f not in visible_fields],
            reason=reason,
        )
    core = CORE_FIELDS.get(module_key, [])
    render_rows = rows or [{k: v.get("value") for k, v in fields.items()}]
    ok = has_displayable_data(render_rows, core)
    visible = [f for f in core if f in fields and not _empty(fields[f].get("value"))]
    hidden = [f for f in core if f not in visible]
    return CompanyV2Render(
        renderable=ok,
        chart_renderable=ok and len(visible) >= 2 and len(render_rows) >= 2,
        table_renderable=ok and bool(render_rows),
        has_displayable_data=ok,
        visible_fields=visible,
        hidden_fields=hidden,
        reason=None if ok else ALL_NULL_ROWS,
    )


class CompanyV2DebugService:
    def __init__(self) -> None:
        self._memory_cache: dict[str, dict[str, Any]] = {}

    def _cache_key(self, market: str, symbol: str, module_key: str) -> str:
        return f"company_v2:v6p_quality:{market.upper()}:{symbol}:{module_key}"

    def _provider_timeout(self, provider: str) -> float:
        provider = provider.lower()
        if provider == "baostock":
            return float(getattr(settings, "company_v2_provider_timeout_baostock_seconds", 20.0))
        if provider == "akshare":
            return float(getattr(settings, "company_v2_provider_timeout_akshare_seconds", 12.0))
        if provider in ("cninfo", "sse", "szse", "pdf", "pdf_metrics", "eastmoney", "sina", "tencent"):
            return float(getattr(settings, "company_v2_provider_timeout_http_seconds", 8.0))
        return float(getattr(settings, "company_v2_provider_timeout_seconds", 8.0))

    def _timeout_envelope(
        self,
        market: str,
        symbol: str,
        module_key: str,
        *,
        max_raw_chars: int,
        reason: str,
    ) -> CompanyV2DebugEnvelope:
        env = self._base_envelope(market, symbol, module_key, max_raw_chars)
        env.ok = False
        env.partial = True
        env.errors.append(CompanyV2Error(layer="provider", error_code="PROVIDER_TIMEOUT", message=reason))
        env.source_chain.append(CompanyV2SourceAttempt(
            provider="module",
            endpoint=module_key,
            attempted=True,
            success=False,
            status="timeout",
            error_code="PROVIDER_TIMEOUT",
            error_message=reason,
        ))
        env.render = CompanyV2Render(reason="PROVIDER_TIMEOUT")
        env.diagnosis = diagnose_company_v2_envelope(env)
        return env

    async def _read_cache(self, key: str, force_refresh: bool) -> tuple[dict[str, Any] | None, bool, str]:
        if force_refresh:
            return None, False, cache_status()
        cached = await cache_service.get_json(key)
        if cached is None:
            cached = self._memory_cache.get(key)
        return cached, cached is not None, cache_status()

    async def _write_cache(self, key: str, payload: dict[str, Any], ttl: int) -> None:
        self._memory_cache[key] = payload
        await cache_service.set_json(key, payload, ttl)

    def _base_envelope(
        self,
        market: str,
        symbol: str,
        module_key: str,
        max_raw_chars: int,
    ) -> CompanyV2DebugEnvelope:
        return CompanyV2DebugEnvelope(
            request_id=current_request_id(),
            market=market.upper(),
            symbol=symbol,
            ts_code=_to_ts_code(market.upper(), symbol),
            module_key=module_key,
            data_mode=getattr(settings, "data_mode", "free"),
            raw={provider: [] for provider in RAW_PROVIDERS},
            debug=CompanyV2DebugMeta(enabled=True, max_raw_chars=max_raw_chars),
        )

    async def build_module(
        self,
        market: str,
        symbol: str,
        module_key: str,
        *,
        include_raw: bool = False,
        providers: list[str] | None = None,
        force_refresh: bool = False,
        max_raw_chars: int = 20000,
        db: AsyncSession | None = None,
        context: dict[str, Any] | None = None,
        max_validation_checks: int | None = None,
    ) -> CompanyV2DebugEnvelope:
        env = self._base_envelope(market, symbol, module_key, max_raw_chars)
        providers = providers or ["baostock", "akshare", "tencent", "sina", "eastmoney", "pdf"]
        cache_key = self._cache_key(market, symbol, module_key)
        cached, hit, cstatus = await self._read_cache(cache_key, force_refresh)
        if cstatus == "unavailable":
            env.errors.append(CompanyV2Error(layer="cache", error_code=CACHE_UNAVAILABLE, message="Redis cache unavailable"))
        if hit and cached:
            env.stale = bool(cached.get("stale", False))
            env.source_chain.append(CompanyV2SourceAttempt(
                provider="cache", endpoint=cache_key, attempted=True, success=True,
                rows_count=1, cache_hit=True, cache_stale=env.stale, cache_status=cstatus,
            ))
            env.normalized = CompanyV2Normalized(**cached.get("normalized", {}))
            env.completion = CompanyV2Completion(**cached.get("completion", {}))
            env.render = CompanyV2Render(**cached.get("render", {}))
            env.field_trace = cached.get("field_trace", {})
            env.coverage = cached.get("coverage", {})
            env.provider_summary = cached.get("provider_summary", {})
            env.agent_summary = cached.get("agent_summary", {})
            env.validation_summary = cached.get("validation_summary", {})
            env.validation_checks = cached.get("validation_checks", [])
            env.ok = env.render.has_displayable_data
            env.partial = False
            env.diagnosis = diagnose_company_v2_envelope(env)
            if not env.validation_summary:
                self._apply_validation(env, max_validation_checks=max_validation_checks)
            return env

        async def _load_uncached() -> None:
            if module_key in ("report_documents", "report_rag"):
                await self._build_report_module(env, db=db, include_raw=include_raw, max_raw_chars=max_raw_chars, force_refresh=force_refresh)
            elif module_key == "ai_analysis_status":
                self._build_ai_status(env)
            elif module_key in ("quote_overview", "valuation"):
                await self._build_quote(env, providers, include_raw, max_raw_chars, context=context)
            else:
                await self._build_financial(env, providers, include_raw, max_raw_chars, context=context)

        try:
            module_timeout = float(getattr(settings, "company_v2_debug_module_timeout_seconds", 20.0))
            if module_key not in ("quote_overview", "valuation", "report_documents", "report_rag", "ai_analysis_status"):
                module_timeout = max(module_timeout, self._provider_timeout("baostock") + 5.0)
            await asyncio.wait_for(
                _load_uncached(),
                timeout=module_timeout,
            )
        except asyncio.TimeoutError:
            env.errors.append(CompanyV2Error(
                layer="provider",
                error_code="PROVIDER_TIMEOUT",
                message=f"Module debug exceeded {getattr(settings, 'company_v2_debug_module_timeout_seconds', 20.0)}s",
            ))
            env.source_chain.append(CompanyV2SourceAttempt(
                provider="module",
                endpoint=module_key,
                attempted=True,
                success=False,
                status="timeout",
                error_code="PROVIDER_TIMEOUT",
            ))

        fields, missing, computed = _fill_fields(module_key, env.normalized.rows, env.normalized.metrics, context=context)
        _apply_display_metadata(module_key, env.normalized.rows, fields)
        env.normalized.fields = fields
        env.completion = CompanyV2Completion(
            filled_fields=fields,
            still_missing_fields=missing,
            computed_fields={field: fields.get(field, formula) for field, formula in computed.items()},
            fallback_chain={k: v.get("source") for k, v in fields.items()},
        )
        env.render = _render(module_key, env.normalized.rows, fields)
        env.field_trace = _field_trace(fields, env.source_chain)
        env.coverage = _coverage(module_key, fields, missing, computed)
        env.provider_summary = _provider_summary(env.source_chain, fields, module_key)
        env.ok = env.render.has_displayable_data or module_key == "ai_analysis_status"
        env.partial = bool(missing) or bool(env.errors)
        if module_key in ("report_documents", "report_rag") and not env.render.has_displayable_data:
            expected_report_error = REPORT_NOT_INGESTED if env.render.reason == REPORT_NOT_INGESTED else REPORT_PDF_NOT_FOUND
            accepted_errors = (expected_report_error, PDF_NOT_FOUND) if expected_report_error == REPORT_PDF_NOT_FOUND else (expected_report_error,)
            if not any(error.error_code in accepted_errors for error in env.errors):
                env.errors.append(CompanyV2Error(
                    layer="provider",
                    error_code=expected_report_error,
                    message=(
                        "Report documents exist but RAG chunks or embeddings are not yet indexed"
                        if expected_report_error == REPORT_NOT_INGESTED
                        else "No confirmed report PDF documents indexed"
                    ),
                ))
        elif not env.render.has_displayable_data and module_key != "ai_analysis_status":
            env.errors.append(CompanyV2Error(layer="render", error_code=ALL_NULL_ROWS, message="No displayable core fields after completion"))
        env.stage = "final"
        env.diagnosis = diagnose_company_v2_envelope(env)
        env.agent_summary = self._agent_summary({module_key: env.model_dump()})
        self._apply_validation(env, max_validation_checks=max_validation_checks)
        ttl = 300 if module_key in ("quote_overview", "valuation") else 7 * 86400
        await self._write_cache(cache_key, {
            "normalized": env.normalized.model_dump(),
            "completion": env.completion.model_dump(),
            "render": env.render.model_dump(),
            "field_trace": env.field_trace,
            "coverage": env.coverage,
            "provider_summary": env.provider_summary,
            "agent_summary": env.agent_summary,
            "validation_summary": env.validation_summary,
            "validation_checks": env.validation_checks,
        }, ttl)
        return env

    async def _build_quote(
        self,
        env: CompanyV2DebugEnvelope,
        providers: list[str],
        include_raw: bool,
        max_raw_chars: int,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        ts_code = env.ts_code
        rows: list[dict[str, Any]] = []
        quote_entry = (context or {}).get("quote_overview")
        if env.module_key == "valuation" and isinstance(quote_entry, dict):
            for source in quote_entry.get("source_chain") or []:
                source_data = source.model_dump() if hasattr(source, "model_dump") else dict(source)
                source_data["cache_hit"] = True
                source_data["cache_status"] = source_data.get("cache_status") or cache_status()
                env.source_chain.append(_source_attempt(source_data))
            env.raw = quote_entry.get("raw") or env.raw
            quote_rows = quote_entry.get("rows") or []
            env.normalized.rows = quote_rows
            env.normalized.metrics = quote_rows[0] if quote_rows else {}
            return
        if "akshare" in providers or "eastmoney" in providers:
            from app.datasource.company_v2_sources import get_akshare_quote_provider
            akshare_quote_provider = get_akshare_quote_provider()
            result = await run_provider_with_debug(
                "akshare", "stock_zh_a_spot_em", akshare_quote_provider.fetch, (ts_code,), {},
                include_raw=include_raw, max_raw_chars=max_raw_chars, request_id=env.request_id,
                symbol=env.symbol, module_key=env.module_key,
                timeout_seconds=self._provider_timeout("akshare"),
            )
            result["data_success"] = _provider_data_success(result)
            env.source_chain.append(_source_attempt(result))
            _add_raw(env.raw, "akshare", result, include_raw)
            sample = result.get("raw_sample") or []
            if result.get("data_success") and sample:
                data = sample[0]
                if isinstance(data, dict) and not _empty(data.get("latest_price")):
                    rows.append({
                        "latest_price": data.get("latest_price"),
                        "price_is_realtime": True,
                        "price_label": "最新价",
                        "price_as_of": data.get("trade_date") or data.get("date"),
                        "price_data_status": "realtime",
                        "price_source": "akshare_spot_em",
                        "pct_chg": data.get("change_pct"),
                        "turnover": data.get("turnover_rate"),
                        "pe_ttm": data.get("pe") or data.get("pe_ttm"),
                        "pb": data.get("pb"),
                        "market_cap": data.get("market_cap"),
                        "float_market_cap": data.get("circ_mv"),
                        "latest_price_source": "akshare_spot_em",
                        "price_label_source": "akshare_spot_em",
                    })
        if "baostock" in providers:
            from app.datasource.baostock_client import baostock_client
            result = await run_provider_with_debug(
                "baostock", "query_history_k_data_plus", baostock_client.get_recent_close, (ts_code,), {},
                include_raw=include_raw, max_raw_chars=max_raw_chars, request_id=env.request_id,
                symbol=env.symbol, module_key=env.module_key,
                timeout_seconds=self._provider_timeout("baostock"),
            )
            result["data_success"] = _provider_data_success(result)
            env.source_chain.append(_source_attempt(result))
            _add_raw(env.raw, "baostock", result, include_raw)
            sample = result.get("raw_sample") or []
            if result.get("data_success") and sample and isinstance(sample[0], dict):
                row = sample[0]
                rows.append({
                    "recent_close": row.get("close"),
                    "latest_price": row.get("close"),
                    "price_is_realtime": False,
                    "price_label": "最近收盘价",
                    "price_as_of": row.get("date") or row.get("trade_date"),
                    "price_data_status": "historical_fallback",
                    "price_source": "baostock_kline_fallback",
                    "pct_chg": row.get("change_pct"),
                    "turnover": row.get("turnover_rate"),
                    "pe_ttm": row.get("pe_ttm"),
                    "pb": row.get("pb"),
                    "ps_ttm": row.get("ps_ttm"),
                    "pcf_ncf_ttm": row.get("pcf_ttm"),
                    "latest_price_source": "baostock_kline_fallback",
                    "price_label_source": "baostock_kline_fallback",
                })
        env.normalized.rows = [self._merge_rows(rows)] if rows else []
        env.normalized.metrics = env.normalized.rows[0] if env.normalized.rows else {}
        if env.normalized.metrics and _empty(env.normalized.metrics.get("price_data_status")):
            env.normalized.metrics["price_data_status"] = "unavailable"
        if context is not None and env.module_key == "quote_overview":
            context["quote_overview"] = {
                "rows": env.normalized.rows,
                "raw": env.raw,
                "source_chain": env.source_chain,
            }

    async def _build_financial(
        self,
        env: CompanyV2DebugEnvelope,
        providers: list[str],
        include_raw: bool,
        max_raw_chars: int,
        *,
        context: dict[str, Any] | None = None,
    ) -> None:
        ts_code = env.ts_code
        rows: list[dict[str, Any]] = []
        baostock_reused = False
        if "baostock" in providers and context is not None and "baostock_aggregate" not in context:
            await self._prepare_baostock_aggregate(
                env.market,
                env.symbol,
                include_raw=include_raw,
                force_refresh=bool(context.get("force_refresh", False)),
                max_raw_chars=max_raw_chars,
                context=context,
            )
        aggregate_entry = (context or {}).get("baostock_aggregate")
        if "baostock" in providers and isinstance(aggregate_entry, dict):
            result = dict(aggregate_entry.get("result") or {})
            result["cache_hit"] = bool(aggregate_entry.get("cache_hit"))
            result["cache_stale"] = bool(aggregate_entry.get("cache_stale"))
            result["cache_status"] = aggregate_entry.get("cache_status")
            result["aggregate_source_id"] = aggregate_entry.get("aggregate_source_id")
            result["data_success"] = _business_value_present(aggregate_entry.get("raw"))
            env.source_chain.append(_source_attempt(result))
            _add_raw(env.raw, "baostock", result, include_raw)
            aggregate_raw = aggregate_entry.get("raw")
            if isinstance(aggregate_raw, dict):
                rows.extend(normalize_baostock_aggregate(env.module_key, aggregate_raw))
                baostock_reused = True
        if "baostock" in providers and not baostock_reused:
            from app.datasource.baostock_client import baostock_client
            result = await run_provider_with_debug(
                "baostock", "get_all_financial_indicators", baostock_client.get_all_financial_indicators,
                (ts_code,), {"n_quarters": 8}, include_raw=include_raw, max_raw_chars=max_raw_chars,
                request_id=env.request_id, symbol=env.symbol, module_key=env.module_key,
                timeout_seconds=self._provider_timeout("baostock"),
            )
            result["aggregate_source_id"] = f"baostock:get_all_financial_indicators:{ts_code}"
            result["data_success"] = _provider_data_success(result)
            env.source_chain.append(_source_attempt(result))
            _add_raw(env.raw, "baostock", result, include_raw)
            aggregate_raw = self._extract_baostock_aggregate_raw(result)
            if isinstance(aggregate_raw, dict):
                rows.extend(normalize_baostock_aggregate(env.module_key, aggregate_raw))
            else:
                rows.extend(self._normalize_baostock_financial(env.module_key, result.get("raw_sample") or []))
        if rows and has_displayable_data(rows, CORE_FIELDS.get(env.module_key, [])):
            merged = self._merge_rows(rows)
            env.normalized.rows = [merged] if merged else []
            env.normalized.metrics = merged
            return
        if "akshare" in providers:
            from app.datasource.company_v2_sources import get_akshare_financial_providers
            akshare_statement_provider, akshare_indicator_provider = get_akshare_financial_providers()
            for endpoint, fn in (
                ("statements", akshare_statement_provider.fetch),
                ("financial_indicator", akshare_indicator_provider.fetch),
            ):
                result = await run_provider_with_debug(
                    "akshare", endpoint, fn, (ts_code,), {}, include_raw=include_raw,
                    max_raw_chars=max_raw_chars, request_id=env.request_id,
                    symbol=env.symbol, module_key=env.module_key,
                    timeout_seconds=self._provider_timeout("akshare"),
                )
                result["data_success"] = _provider_data_success(result)
                env.source_chain.append(_source_attempt(result))
                _add_raw(env.raw, "akshare", result, include_raw)
                rows.extend(self._normalize_akshare_financial(env.module_key, result.get("raw_sample") or []))
        merged = self._merge_rows(rows)
        env.normalized.rows = [merged] if merged else []
        env.normalized.metrics = merged

    def _normalize_baostock_financial(self, module_key: str, sample: list[Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for item in sample:
            if not isinstance(item, dict):
                continue
            raw = item.get("value") if isinstance(item.get("value"), dict) else item
            if not isinstance(raw, dict):
                continue
            table = {
                "profitability": raw.get("profit", []),
                "growth": raw.get("growth", []),
                "cashflow_quality": raw.get("cash_flow", []),
                "solvency": raw.get("balance", []),
                "operation_capability": raw.get("operation", []),
                "dupont": raw.get("dupont", []),
            }.get(module_key, [])
            if isinstance(table, list):
                for row in table[:3]:
                    if not isinstance(row, dict):
                        continue
                    out.append({
                        "roe": row.get("roe_avg") or row.get("dupont_roe"),
                        "gross_margin": row.get("gross_margin"),
                        "net_margin": row.get("net_margin") or row.get("dupont_nitogr"),
                        "revenue": row.get("mb_revenue"),
                        # Phase 6T-E 修复：yoy_equity 是净资产同比，不再误标为 revenue_yoy；
                        # yoy_eps 是每股收益同比，不再误标为 eps_basic。
                        "net_profit_parent": row.get("net_profit"),
                        "net_profit_yoy": row.get("yoy_ni"),
                        "parent_net_profit_yoy": row.get("yoy_pni"),
                        "ocf_to_np": row.get("cfo_to_np"),
                        "ocf_to_revenue": row.get("cfo_to_gr") or row.get("cfo_to_or"),
                        "cashflow_revenue_ratio": row.get("cfo_to_or") or row.get("cfo_to_gr"),
                        "current_ratio": row.get("current_ratio"),
                        "quick_ratio": row.get("quick_ratio"),
                        "cash_ratio": row.get("cash_ratio"),
                        "debt_ratio": row.get("liability_to_asset"),
                        "equity_multiplier": row.get("asset_to_equity") or row.get("dupont_am"),
                        "asset_turnover": row.get("asset_turn_ratio") or row.get("dupont_at"),
                        "inventory_turnover": row.get("inv_turn_ratio"),
                        "receivable_turnover": row.get("nr_turn_ratio"),
                        "total_asset_turnover": row.get("asset_turn_ratio"),
                        "dupont_net_profit_factor": row.get("dupont_npi"),
                        "dupont_income_margin": row.get("dupont_nitogr"),
                        "net_margin": (
                            round(float(row.get("dupont_npi")) * float(row.get("dupont_nitogr")), 6)
                            if row.get("dupont_npi") is not None and row.get("dupont_nitogr") is not None
                            else row.get("net_margin")
                        ),
                    })
        return out

    def _normalize_akshare_financial(self, module_key: str, sample: list[Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for item in sample:
            raw = item.get("value") if isinstance(item, dict) and isinstance(item.get("value"), dict) else item
            if not isinstance(raw, dict):
                continue
            row = {
                "roe": raw.get("roe"),
                "gross_margin": raw.get("gross_margin"),
                "net_margin": raw.get("net_margin"),
                "roa": raw.get("roa"),
                "revenue": raw.get("revenue"),
                "net_profit_parent": raw.get("net_profit_parent"),
                "operating_cashflow": raw.get("operating_cashflow"),
                "ocf_to_np": raw.get("ocf_to_np"),
                "current_ratio": raw.get("current_ratio"),
                "debt_ratio": raw.get("debt_ratio"),
                "asset_turnover": raw.get("asset_turnover"),
                "inventory_turnover": raw.get("inventory_turnover"),
            }
            if row.get("operating_cashflow") is not None and raw.get("revenue"):
                row["ocf_to_revenue"] = row["operating_cashflow"] / raw["revenue"]
                row["cashflow_revenue_ratio"] = row["ocf_to_revenue"]
            if raw.get("total_liabilities") is not None and raw.get("total_assets"):
                row["debt_ratio"] = raw["total_liabilities"] / raw["total_assets"]
            if raw.get("current_assets") is not None and raw.get("current_liabilities"):
                row["current_ratio"] = raw["current_assets"] / raw["current_liabilities"]
            out.append(row)
        return out

    def _merge_rows(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for row in rows:
            for key, value in row.items():
                if key not in merged and not _empty(value):
                    merged[key] = value
                    if not key.endswith("_source"):
                        merged[f"{key}_source"] = row.get(f"{key}_source") or "provider"
        return merged

    async def _build_report_module(
        self,
        env: CompanyV2DebugEnvelope,
        *,
        db: AsyncSession | None,
        include_raw: bool,
        max_raw_chars: int,
        force_refresh: bool,
    ) -> None:
        attempts = await self.discover_reports(env.market, env.symbol, db=db, force_refresh=force_refresh)
        env.raw["pdf_metrics"] = {"discovery_attempts": attempts}
        env.source_chain.append(CompanyV2SourceAttempt(
            provider="pdf_metrics", endpoint="discovery", attempted=True,
            success=any(a.get("candidate_count", 0) > 0 for a in attempts),
            rows_count=sum(a.get("candidate_count", 0) for a in attempts),
        ))
        counts = {"documents_count": 0, "chunks_count": 0, "embedding_count": 0}
        if db is not None:
            try:
                counts["documents_count"] = (await db.execute(text("SELECT COUNT(*) FROM report_documents WHERE ts_code=:ts_code"), {"ts_code": env.ts_code})).scalar() or 0
                counts["chunks_count"] = (await db.execute(text("SELECT COUNT(*) FROM report_chunks WHERE ts_code=:ts_code"), {"ts_code": env.ts_code})).scalar() or 0
                counts["embedding_count"] = (await db.execute(text("SELECT COUNT(*) FROM report_chunks WHERE ts_code=:ts_code AND embedding IS NOT NULL"), {"ts_code": env.ts_code})).scalar() or 0
            except Exception as exc:
                env.errors.append(CompanyV2Error(layer="cache", error_code=CACHE_UNAVAILABLE, message=str(exc)[:200]))
        # report_documents now holds both doc counts AND rag status (report_rag merged)
        counts["report_status"] = "FOUND" if counts["documents_count"] > 0 else "EMPTY"
        if counts["documents_count"] <= 0:
            counts["pdf_status"] = "not_found"
            counts["rag_status"] = "not_ingested"
        elif counts["chunks_count"] > 0 and counts["embedding_count"] > 0:
            counts["pdf_status"] = "found"
            counts["rag_status"] = "ready"
        else:
            counts["pdf_status"] = "found"
            counts["rag_status"] = "not_ingested"
        env.normalized.rows = [counts]
        env.normalized.metrics = counts
        if counts["documents_count"] <= 0:
            env.errors.append(CompanyV2Error(
                layer="provider",
                error_code=REPORT_PDF_NOT_FOUND,
                message="No confirmed report PDF documents indexed",
            ))
        elif counts["chunks_count"] <= 0 or counts["embedding_count"] <= 0:
            env.errors.append(CompanyV2Error(
                layer="provider",
                error_code=REPORT_NOT_INGESTED,
                message="Report documents exist but RAG chunks or embeddings are not yet indexed",
            ))

    async def discover_reports(self, market: str, symbol: str, *, db: AsyncSession | None, force_refresh: bool) -> list[dict[str, Any]]:
        years = [date.today().year - 1]
        attempts: list[dict[str, Any]] = []
        if market.upper() != "CN":
            return attempts
        provider_defs = [
            ("cninfo", "app.tools.reports.cninfo_report_search_tool", "cninfo_tool"),
            ("sse", "app.tools.reports.sse_report_search_tool", "sse_tool"),
            ("szse", "app.tools.reports.szse_report_search_tool", "szse_tool"),
        ]
        for year in years:
            for provider, module_name, attr in provider_defs:
                query = {"symbol": symbol, "year": year, "report_type": "annual"}
                try:
                    mod = __import__(module_name, fromlist=[attr])
                    tool = getattr(mod, attr)
                    candidates = await asyncio.wait_for(
                        tool.search(symbol, "", "annual", year),
                        timeout=self._provider_timeout(provider),
                    )
                    attempts.append({
                        "provider": provider,
                        "year": year,
                        "report_type": "annual",
                        "query": query,
                        "status": "ok" if candidates else "empty",
                        "candidate_count": len(candidates),
                        "top_candidates": sanitize_debug_payload(candidates[:3], max_chars=2000),
                        "error_code": None if candidates else PDF_NOT_FOUND,
                    })
                    if candidates:
                        break
                except asyncio.TimeoutError:
                    attempts.append({
                        "provider": provider,
                        "year": year,
                        "report_type": "annual",
                        "query": query,
                        "status": "timeout",
                        "candidate_count": 0,
                        "top_candidates": [],
                        "error_code": "PROVIDER_TIMEOUT",
                        "error_message": f"Provider call exceeded {self._provider_timeout(provider):g}s",
                    })
                except Exception as exc:
                    attempts.append({
                        "provider": provider,
                        "year": year,
                        "report_type": "annual",
                        "query": query,
                        "status": "failed",
                        "candidate_count": 0,
                        "top_candidates": [],
                        "error_code": "PROVIDER_NETWORK_ERROR",
                        "error_message": str(exc)[:200],
                    })
            if any(a.get("candidate_count", 0) > 0 for a in attempts):
                break
        return attempts

    def _build_ai_status(self, env: CompanyV2DebugEnvelope) -> None:
        has_key = bool(getattr(settings, "ai_api_key", None))
        summary = "结构化财务数据摘要可用；年报 RAG 尚未接入。"
        env.normalized.rows = [{
            "summary": summary,
            "structured_summary_available": True,
            "rag_available": False,
            "ai_enabled": bool(getattr(settings, "ai_enabled", False)),
            "ai_key_configured": has_key,
        }]
        env.normalized.metrics = env.normalized.rows[0]
        if not has_key:
            env.errors.append(CompanyV2Error(layer="auth", error_code=AI_KEY_MISSING, message="AI provider key is not configured"))
        if not env.normalized.metrics:
            env.errors.append(CompanyV2Error(layer="mapping", error_code=DATA_PACK_EMPTY, message="No structured fields for summary"))

    async def build_full(
        self,
        market: str,
        symbol: str,
        *,
        include_raw: bool,
        providers: list[str] | None,
        force_refresh: bool,
        max_raw_chars: int,
        db: AsyncSession | None,
        max_validation_checks: int | None = None,
        history: bool = False,
        period: str = "annual",
        start_year: int | None = None,
        end_year: int | None = None,
    ) -> dict[str, Any]:
        ts_code = _to_ts_code(market.upper(), symbol)
        full_cache_key = company_v2_snapshot_cache_service.make_key(
            "full", ts_code, "v6u_d2_history" if history else "v6u_d2_quality",
            ",".join(providers or []), str(include_raw), str(max_raw_chars),
            str(max_validation_checks), str(history), period, str(start_year), str(end_year)
        )
        cached_full, full_hit, full_stale, full_cache_status = await company_v2_snapshot_cache_service.get(
            full_cache_key, force_refresh=force_refresh
        )
        if full_hit and isinstance(cached_full, dict):
            cached_full["cache_hit"] = True
            cached_full["cache_stale"] = full_stale
            cached_full["cache_status"] = full_cache_status
            summary = cached_full.setdefault("summary", {})
            if isinstance(summary, dict):
                summary["cache_hit"] = True
                summary["cache_stale"] = full_stale
            if "validation_summary" not in cached_full:
                validation = validate_company_v2_envelope(cached_full)
                cached_full["validation_summary"] = validation["validation_summary"]
                cached_full["validation_checks"] = validation["validation_checks"]
                self._merge_validation_agent_summary(
                    cached_full.setdefault("agent_summary", {}),
                    validation["validation_summary"],
                    validation["validation_checks"],
                )
            log_company_v2_event(self._production_log_event(cached_full, latency_ms=0))
            return cached_full

        modules: dict[str, Any] = {}
        started = asyncio.get_running_loop().time()
        full_timeout = float(getattr(settings, "company_v2_debug_full_timeout_seconds", 45.0))
        timed_out = False
        context: dict[str, Any] = {"provider_calls_count": {}, "force_refresh": force_refresh}
        active_providers = providers or ["baostock", "akshare", "tencent", "sina", "eastmoney", "pdf"]
        if "baostock" in active_providers:
            try:
                await asyncio.wait_for(
                    self._prepare_baostock_aggregate(
                        market,
                        symbol,
                        include_raw=include_raw,
                        force_refresh=force_refresh,
                        max_raw_chars=max_raw_chars,
                        context=context,
                    ),
                    timeout=min(self._provider_timeout("baostock") + 2.0, full_timeout),
                )
            except asyncio.TimeoutError:
                context.setdefault("provider_calls_count", {})["baostock_aggregate"] = 1

        for module_key in MODULE_KEYS:
            remaining = full_timeout - (asyncio.get_running_loop().time() - started)
            if remaining <= 0:
                timed_out = True
                modules[module_key] = self._timeout_envelope(
                    market, symbol, module_key, max_raw_chars=max_raw_chars,
                    reason=f"debug/full exceeded {full_timeout:g}s before {module_key} started",
                ).model_dump()
                continue
            try:
                env = await asyncio.wait_for(
                    self.build_module(
                        market, symbol, module_key,
                        include_raw=include_raw,
                        providers=providers,
                        force_refresh=force_refresh,
                        max_raw_chars=max_raw_chars,
                        db=db,
                        context=context,
                        max_validation_checks=max_validation_checks,
                    ),
                    timeout=max(0.1, remaining),
                )
                modules[module_key] = env.model_dump()
            except asyncio.TimeoutError:
                timed_out = True
                modules[module_key] = self._timeout_envelope(
                    market, symbol, module_key, max_raw_chars=max_raw_chars,
                    reason=f"debug/full exceeded {full_timeout:g}s while waiting for {module_key}",
                ).model_dump()
            except Exception as exc:
                env = self._timeout_envelope(
                    market, symbol, module_key, max_raw_chars=max_raw_chars,
                    reason=f"Module failed: {type(exc).__name__}: {str(exc)[:200]}",
                )
                env.errors[0].error_code = "PROVIDER_EXCEPTION"
                modules[module_key] = env.model_dump()
        summary = self._summary(modules)
        provider_calls_count = context.get("provider_calls_count") or {}
        summary["provider_calls_count"] = provider_calls_count
        aggregate_source_ids = {
            source.get("aggregate_source_id")
            for module in modules.values()
            for source in module.get("source_chain", [])
            if source.get("aggregate_source_id")
        }
        financial_rendered = any(
            (modules.get(module_key, {}).get("render") or {}).get("has_displayable_data")
            for module_key in ("profitability", "growth", "cashflow_quality", "solvency", "operation_capability", "dupont")
        )
        summary["baostock_aggregate_calls"] = (
            len(aggregate_source_ids)
            or int(provider_calls_count.get("baostock_aggregate", 0) or 0)
            or (1 if financial_rendered else 0)
        )
        agent_summary = self._agent_summary(modules)
        payload = {
            "schema_version": "2.0",
            "schema_features": [
                "formatter_registry",
                "field_trace",
                "coverage",
                "provider_summary",
                "computed_field_registry",
                "report_status_machine",
                "data_validation_engine",
            ],
            "request_id": current_request_id(),
            "market": market.upper(),
            "symbol": symbol,
            "ts_code": ts_code,
            "data_mode": getattr(settings, "data_mode", "free"),
            "partial": timed_out or any(m.get("partial") for m in modules.values()),
            "summary": summary,
            "agent_summary": agent_summary,
            "modules": modules,
        }
        if history:
            try:
                from app.services.company_v2_history_service import build_company_history_dashboard
                history_payload = await build_company_history_dashboard(
                    market,
                    symbol,
                    period=period,
                    start_year=start_year,
                    end_year=end_year,
                    force_refresh=force_refresh,
                )
                payload["history"] = history_payload
                payload["stock_basic"] = history_payload.get("stock_basic") or {}
                for module_key, history_module in (history_payload.get("modules") or {}).items():
                    if module_key in modules and isinstance(modules[module_key], dict):
                        modules[module_key]["latest"] = history_module.get("latest") or {}
                        modules[module_key]["history"] = history_module.get("history") or []
                        modules[module_key]["period_type"] = history_module.get("period_type") or period
                        modules[module_key]["chart_contract"] = history_module.get("chart_contract") or {}
                        modules[module_key]["history_coverage"] = history_module.get("history_coverage") or {}
                        # Phase 6T-E: 审计/契约校验/行业适用性透传
                        modules[module_key]["history_quality"] = history_module.get("history_quality") or {}
                        modules[module_key]["chart_contract_validation"] = history_module.get("chart_contract_validation") or {}
                        modules[module_key]["metric_applicability"] = history_module.get("metric_applicability") or {}
                        if modules[module_key].get("coverage"):
                            modules[module_key]["coverage"] = apply_applicability_to_coverage(
                                modules[module_key]["coverage"],
                                modules[module_key]["metric_applicability"],
                            )
                        if modules[module_key].get("metric_applicability", {}).get("module_status") == "not_applicable":
                            modules[module_key].setdefault("render", {})["reason"] = "NOT_APPLICABLE_FOR_INDUSTRY"
            except Exception as exc:
                payload.setdefault("warnings", []).append({
                    "layer": "history",
                    "error_code": "HISTORY_ERROR",
                    "message": str(exc)[:200],
                })
        validation = validate_company_v2_envelope(payload, max_validation_checks=max_validation_checks)
        payload["validation_summary"] = validation["validation_summary"]
        payload["validation_checks"] = validation["validation_checks"]
        # Phase 6T-E: 顶层性能摘要（真实测量）
        history_perf = (payload.get("history") or {}).get("performance_summary") or {}
        payload["performance_summary"] = {
            "total_latency_ms": int((asyncio.get_running_loop().time() - started) * 1000),
            "history_latency_ms": history_perf.get("total_latency_ms", 0),
            "provider_latency_ms": history_perf.get("provider_latency_ms", 0),
            "history_rows_total": history_perf.get("history_rows_total", 0),
            "baostock_aggregate_calls": summary.get("baostock_aggregate_calls", 0),
            "cache_hit": False,
        }
        self._merge_validation_agent_summary(payload["agent_summary"], validation["validation_summary"], validation["validation_checks"])
        log_company_v2_event(
            self._production_log_event(
                payload,
                latency_ms=int((asyncio.get_running_loop().time() - started) * 1000),
            )
        )
        await company_v2_snapshot_cache_service.set(full_cache_key, payload, ttl=30 * 60)
        return payload

    async def _prepare_baostock_aggregate(
        self,
        market: str,
        symbol: str,
        *,
        include_raw: bool,
        force_refresh: bool,
        max_raw_chars: int,
        context: dict[str, Any],
    ) -> None:
        ts_code = _to_ts_code(market.upper(), symbol)
        aggregate_source_id = f"baostock:get_all_financial_indicators:{ts_code}"
        key = company_v2_snapshot_cache_service.make_key("provider", ts_code, "baostock", "get_all_financial_indicators", "n8")
        cached, hit, stale, cstatus = await company_v2_snapshot_cache_service.get(key, force_refresh=force_refresh)
        if hit and isinstance(cached, dict):
            result = dict(cached.get("result") or {})
            result["cache_hit"] = True
            result["cache_stale"] = stale
            result["cache_status"] = cstatus
            result["data_success"] = _business_value_present(cached.get("raw"))
            context["baostock_aggregate"] = {
                "result": result,
                "raw": cached.get("raw"),
                "cache_hit": True,
                "cache_stale": stale,
                "cache_status": cstatus,
                "aggregate_source_id": aggregate_source_id,
            }
            self._update_share_capital_context(context, cached.get("raw"), source="baostock_aggregate_cache")
            context.setdefault("provider_calls_count", {})["baostock_aggregate"] = 0
            return

        from app.datasource.baostock_client import baostock_client

        context.setdefault("provider_calls_count", {})["baostock_aggregate"] = 1
        result = await run_provider_with_debug(
            "baostock",
            "get_all_financial_indicators",
            baostock_client.get_all_financial_indicators,
            (ts_code,),
            {"n_quarters": 8},
            include_raw=True,
            max_raw_chars=max_raw_chars,
            request_id=current_request_id(),
            symbol=symbol,
            module_key="baostock_aggregate",
            timeout_seconds=self._provider_timeout("baostock"),
        )
        result["aggregate_source_id"] = aggregate_source_id
        result["data_success"] = _provider_data_success(result)
        raw = self._extract_baostock_aggregate_raw(result)
        if (not result.get("success")) and result.get("error_code") == "PROVIDER_TIMEOUT":
            stale_cached, stale_hit, _, stale_status = await company_v2_snapshot_cache_service.get(key, force_refresh=False)
            if stale_hit and isinstance(stale_cached, dict) and isinstance(stale_cached.get("raw"), dict):
                stale_result = dict(stale_cached.get("result") or result)
                stale_result["success"] = True
                stale_result["status"] = "success"
                stale_result["cache_hit"] = True
                stale_result["cache_stale"] = True
                stale_result["cache_status"] = stale_status
                stale_result["aggregate_source_id"] = aggregate_source_id
                context["baostock_aggregate"] = {
                    "result": stale_result,
                    "raw": stale_cached.get("raw"),
                    "cache_hit": True,
                    "cache_stale": True,
                    "cache_status": stale_status,
                    "aggregate_source_id": aggregate_source_id,
                }
                self._update_share_capital_context(context, stale_cached.get("raw"), source="baostock_aggregate_stale")
                return
        if result.get("success") and isinstance(raw, dict):
            await company_v2_snapshot_cache_service.set(
                key,
                {"result": result, "raw": raw},
                ttl=7 * 86400,
            )
        context["baostock_aggregate"] = {
            "result": result,
            "raw": raw,
            "cache_hit": False,
            "cache_stale": False,
            "cache_status": cstatus,
            "aggregate_source_id": aggregate_source_id,
        }
        self._update_share_capital_context(context, raw, source="baostock_aggregate")

    def _extract_baostock_aggregate_raw(self, result: dict[str, Any]) -> dict[str, Any] | None:
        for key in ("raw_full", "raw_sample"):
            value = result.get(key)
            candidates = value if isinstance(value, list) else [value]
            for item in candidates:
                if isinstance(item, dict) and isinstance(item.get("value"), dict):
                    return item["value"]
                if isinstance(item, dict) and any(table in item for table in ("profit", "growth", "cash_flow", "balance", "operation", "dupont")):
                    return item
        return None

    def _update_share_capital_context(self, context: dict[str, Any], aggregate_raw: Any, *, source: str) -> None:
        if not isinstance(aggregate_raw, dict):
            return
        profit_rows = aggregate_raw.get("profit") or []
        if not isinstance(profit_rows, list):
            return
        for row in profit_rows:
            if not isinstance(row, dict):
                continue
            total_share = row.get("totalShare") or row.get("total_share")
            float_share = row.get("liqaShare") or row.get("liqa_share")
            if _empty(total_share) and _empty(float_share):
                continue
            context["share_capital_context"] = {
                "total_share": total_share,
                "float_share": float_share,
                "source": source,
                "provider": "baostock",
                "provider_method": "get_all_financial_indicators",
                "as_of": row.get("statDate") or row.get("stat_date"),
            }
            return

    def _summary(self, modules: dict[str, Any]) -> dict[str, Any]:
        attempts = [
            source
            for module in modules.values()
            for source in module.get("source_chain", [])
            if source.get("provider") != "cache"
        ]
        source_errors = [source.get("error_code") for source in attempts if source.get("error_code")]
        module_issue_sets = []
        for module in modules.values():
            issues = {
                error.get("error_code")
                for error in module.get("errors", [])
                if error.get("error_code")
            }
            primary_issue = (module.get("diagnosis") or {}).get("primary_issue")
            if primary_issue:
                issues.add(primary_issue)
            module_issue_sets.append(issues)

        def _module_issue_count(error_code: str) -> int:
            return sum(1 for issues in module_issue_sets if error_code in issues)

        return {
            "providers_attempted": len(attempts),
            "providers_success": sum(1 for s in attempts if s.get("success")),
            "providers_data_success": sum(1 for s in attempts if s.get("data_success") is True or (s.get("data_success") is None and s.get("success") and s.get("rows_count", 0) > 0 and not s.get("error_code"))),
            "provider_data_failure_count": sum(1 for s in attempts if s.get("success") and s.get("data_success") is False),
            "providers_timeout": sum(1 for s in attempts if s.get("error_code") == "PROVIDER_TIMEOUT" or s.get("status") == "timeout"),
            "providers_failed": sum(1 for s in attempts if (not s.get("success")) and s.get("error_code") not in (None, "PROVIDER_EMPTY", "PROVIDER_TIMEOUT")),
            "modules_renderable": sum(1 for m in modules.values() if (m.get("render") or {}).get("has_displayable_data")),
            "modules_unavailable": sum(1 for m in modules.values() if not (m.get("render") or {}).get("has_displayable_data")),
            "cache_hit_count": sum(1 for m in modules.values() for s in m.get("source_chain", []) if s.get("cache_hit")),
            "cache_stale_count": sum(1 for m in modules.values() for s in m.get("source_chain", []) if s.get("cache_stale")),
            "cache_unavailable_count": _module_issue_count("CACHE_UNAVAILABLE") + source_errors.count("CACHE_UNAVAILABLE"),
            "report_pdf_not_found_count": _module_issue_count("REPORT_PDF_NOT_FOUND"),
            "report_not_ingested_count": _module_issue_count("REPORT_NOT_INGESTED"),
            "mapping_error_count": _module_issue_count("MAPPING_ERROR"),
            "render_rule_error_count": _module_issue_count("RENDER_RULE_ERROR"),
            "fallback_to_legacy_count": 0,
        }

    def _agent_summary(self, modules: dict[str, Any]) -> dict[str, Any]:
        module_values = list(modules.values())
        coverage_values = [
            float((module.get("coverage") or {}).get("coverage_pct") or 0)
            for module in module_values
            if isinstance(module, dict) and module.get("coverage")
        ]
        diagnosis_tags: list[str] = []
        missing_critical: list[str] = []
        computed_count = 0
        mapping_ok = 0
        provider_health_scores: list[float] = []
        for module in module_values:
            if not isinstance(module, dict):
                continue
            diagnosis = module.get("diagnosis") or {}
            for tag in diagnosis.get("tags") or [diagnosis.get("primary_issue")]:
                if tag and tag not in diagnosis_tags:
                    diagnosis_tags.append(tag)
            coverage = module.get("coverage") or {}
            missing_map = coverage.get("missing_field_map") or {}
            for field in ("market_cap", "float_market_cap"):
                if field in missing_map and field not in missing_critical:
                    missing_critical.append(field)
            computed_count += int(coverage.get("computed_fields") or 0)
            if diagnosis.get("primary_issue") not in {"MAPPING_ERROR", "MAPPING_OR_RENDER_ERROR"}:
                mapping_ok += 1
            provider_summary = module.get("provider_summary") or {}
            if provider_summary:
                provider_health_scores.append(
                    sum(1 for item in provider_summary.values() if item.get("data_success")) / max(1, len(provider_summary)) * 100
                )
        overall_coverage = round(sum(coverage_values) / len(coverage_values), 2) if coverage_values else 0.0
        mapping_quality = round(mapping_ok / len(module_values) * 100, 2) if module_values else 0.0
        provider_health = round(sum(provider_health_scores) / len(provider_health_scores), 2) if provider_health_scores else 0.0
        recommended_next_actions: list[str] = []
        if missing_critical:
            recommended_next_actions.append("Enable share capital provider or reuse BaoStock total_share for market_cap.")
        if overall_coverage < 60:
            recommended_next_actions.append("Limit automated analysis to data-availability caveats until coverage improves.")
        return {
            "overall_coverage_pct": overall_coverage,
            "mapping_quality_pct": mapping_quality,
            "provider_health_pct": provider_health,
            "computed_fields_count": computed_count,
            "missing_critical_fields": missing_critical,
            "diagnosis_tags": diagnosis_tags,
            "recommended_next_actions": recommended_next_actions,
        }

    def _production_log_event(self, payload: dict[str, Any], *, latency_ms: int) -> dict[str, Any]:
        summary = payload.get("summary") or {}
        validation_summary = payload.get("validation_summary") or {}
        agent_summary = payload.get("agent_summary") or {}
        return {
            "event_name": "company_v2_debug_full_completed",
            "request_id": payload.get("request_id") or current_request_id(),
            "market": payload.get("market"),
            "symbol": payload.get("symbol"),
            "ts_code": payload.get("ts_code"),
            "schema_version": payload.get("schema_version", "2.0"),
            "latency_ms": latency_ms,
            "partial": bool(payload.get("partial")),
            "providers_data_success": summary.get("providers_data_success", 0),
            "providers_timeout": summary.get("providers_timeout", 0),
            "modules_renderable": summary.get("modules_renderable", 0),
            "coverage_avg": agent_summary.get("overall_coverage_pct", 0),
            "validation_status": validation_summary.get("status"),
            "data_quality_score": validation_summary.get("data_quality_score", 0),
            "strong_failed_count": validation_summary.get("strong_failed_count", 0),
            "semantic_warning_count": validation_summary.get("semantic_warning_count", 0),
            "critical_validation_failures": validation_summary.get("critical_failures", 0),
            "fallback_to_legacy": False,
        }

    def _apply_validation(self, env: CompanyV2DebugEnvelope, *, max_validation_checks: int | None = None) -> None:
        validation = validate_company_v2_envelope(env, max_validation_checks=max_validation_checks)
        env.validation_summary = validation["validation_summary"]
        env.validation_checks = validation["validation_checks"]
        self._merge_validation_agent_summary(env.agent_summary, env.validation_summary, env.validation_checks)

    @staticmethod
    def _merge_validation_agent_summary(
        agent_summary: dict[str, Any],
        validation_summary: dict[str, Any],
        validation_checks: list[dict[str, Any]],
    ) -> None:
        agent_summary["data_quality_score"] = validation_summary.get("data_quality_score", 0)
        agent_summary["validation_status"] = validation_summary.get("status", "pass")
        agent_summary["critical_validation_failures"] = validation_summary.get("critical_failures", 0)
        tags: list[str] = []
        for check in validation_checks:
            if check.get("status") in ("warning", "fail"):
                tag = check.get("check_id")
                if tag and tag not in tags:
                    tags.append(tag)
        agent_summary["validation_tags"] = tags


company_v2_debug_service = CompanyV2DebugService()
