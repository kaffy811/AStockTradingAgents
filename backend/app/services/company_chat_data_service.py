"""Shared Company V2 data adapter for Chat tools.

Chat must reuse the same domain services and caches that power the Company page.
This adapter keeps domain availability separate so one missing area, such as
market history, cannot incorrectly erase quote/profile/financial snapshot data.
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.services.company_v2_history_service import build_company_history_dashboard
from app.services.financial_metric_comparability import (
    accounting_scope_for,
    financial_metric_comparability_service,
    infer_period_type,
    metric_normalizer,
    value_type_for,
)
from app.services.stock_data_service import stock_data_service


CHAT_COMPANY_DATA_ERROR_CODES = {
    "RAG_DATABASE_UNAVAILABLE": "RAG_DATABASE_UNAVAILABLE",
    "HISTORICAL_MARKET_DATA_UNAVAILABLE": "HISTORICAL_MARKET_DATA_UNAVAILABLE",
    "ENTITY_NOT_RESOLVED": "ENTITY_NOT_RESOLVED",
    "FINANCIAL_DATA_PARTIAL": "FINANCIAL_DATA_PARTIAL",
}

_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "revenue": ("revenue", "operating_revenue", "or", "营业收入"),
    "parent_net_profit": ("parent_net_profit", "np_parent_company_owners", "归母净利润"),
    "roe": ("roe", "dupont_roe", "weighted_roe", "净资产收益率"),
    "operating_cashflow": ("operating_cashflow", "net_operate_cash_flow", "cfo", "经营现金流"),
    "total_assets": ("total_assets", "asset", "总资产"),
    "parent_equity": ("parent_equity", "equity", "归母净资产"),
    "eps": ("eps", "basic_eps", "每股收益"),
}


def _entity_dict(entity: dict[str, Any]) -> dict[str, Any]:
    market = str(entity.get("market") or "CN").upper()
    symbol = str(entity.get("symbol") or "")
    return {
        **entity,
        "market": market,
        "symbol": symbol,
        "name": entity.get("name") or entity.get("short_name") or symbol,
        "short_name": entity.get("short_name") or entity.get("name") or symbol,
    }


def _first_value(row: dict[str, Any], aliases: tuple[str, ...]) -> tuple[str, Any] | tuple[None, None]:
    for key in aliases:
        if key in row and row.get(key) not in (None, ""):
            return key, row.get(key)
    return None, None


def _metric_from_row(row: dict[str, Any], field: str, *, source: str) -> dict[str, Any] | None:
    source_key, value = _first_value(row, _FIELD_ALIASES.get(field, (field,)))
    if value in (None, ""):
        return None
    period = row.get("period") or row.get("period_end") or row.get("date")
    raw_item = {
        "field": field,
        "raw_value": value,
        "normalized_value": value,
        "unit": "元/股" if field == "eps" else ("CNY" if field != "roe" else None),
        "period_end": period,
        "period_type": row.get("period_type") or row.get("report_period_type") or infer_period_type(period),
        "report_year": row.get("report_year") or (int(str(period)[:4]) if str(period or "")[:4].isdigit() else None),
        "accounting_scope": accounting_scope_for(field),
        "value_type": value_type_for(field),
        "source": source,
        "source_key": source_key or field,
        "source_type": "company_history",
        "evidence_id": f"{source}:{field}:{period or 'latest'}",
    }
    return metric_normalizer.normalize(raw_item, field)


def _financial_candidates_from_dashboard(dashboard: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    modules = dashboard.get("modules") or {}
    rows_by_module: list[tuple[str, dict[str, Any]]] = []
    for module_key in ("profitability", "growth", "cashflow_quality", "solvency", "operation_capability", "dupont"):
        module = modules.get(module_key) or {}
        for row in module.get("history") or []:
            if isinstance(row, dict):
                enriched = dict(row)
                enriched.setdefault("period_type", row.get("report_period_type") or module.get("period_type"))
                rows_by_module.append((module_key, enriched))
        latest = module.get("latest") or {}
        if latest:
            enriched = dict(latest)
            enriched.setdefault("period_type", latest.get("report_period_type") or module.get("period_type"))
            rows_by_module.append((module_key, enriched))
    candidates: dict[str, list[dict[str, Any]]] = {field: [] for field in _FIELD_ALIASES}
    for field in _FIELD_ALIASES:
        for module_key, row in rows_by_module:
            item = _metric_from_row(row, field, source=f"company_v2_history.{module_key}")
            if item:
                candidates[field].append(item)
    return candidates


def _select_metric_candidate(
    candidates: list[dict[str, Any]],
    *,
    target_period_type: str | None,
    target_report_year: int | None,
    allow_fallback: bool,
) -> dict[str, Any] | None:
    if not candidates:
        return None

    def valid_unit(item: dict[str, Any]) -> bool:
        return item.get("validation_status") in {"verified", "normalized"}

    exact = []
    if target_period_type is not None or target_report_year is not None:
        exact = [
            item for item in candidates
            if (target_period_type is None or item.get("period_type") == target_period_type)
            and (target_report_year is None or item.get("report_year") == target_report_year)
            and valid_unit(item)
        ]
    if exact:
        exact.sort(key=lambda item: str(item.get("period_end") or ""), reverse=True)
        selected = dict(exact[0])
        selected["selection_reason"] = "target_period_exact_match"
        return selected

    if not allow_fallback:
        return {
            "validation_status": "unverified",
            "warnings": ["TARGET_PERIOD_UNAVAILABLE"],
            "selection_reason": "no_target_period_match",
            "candidates": [
                {
                    "period_end": item.get("period_end"),
                    "period_type": item.get("period_type"),
                    "report_year": item.get("report_year"),
                    "source_id": item.get("source_id"),
                    "validation_status": item.get("validation_status"),
                    "warnings": item.get("warnings") or [],
                }
                for item in candidates[:5]
            ],
        }

    available = [item for item in candidates if valid_unit(item)]
    available.sort(key=lambda item: str(item.get("period_end") or ""), reverse=True)
    if available:
        selected = dict(available[0])
        selected["selection_reason"] = "latest_available_fallback"
        return selected
    return None


class CompanyChatDataService:
    async def get_company_domains(self, entity: dict[str, Any], *, force_refresh: bool = False) -> dict[str, Any]:
        entity_data = _entity_dict(entity)
        market = entity_data["market"]
        symbol = entity_data["symbol"]
        if not symbol:
            return {
                "entity": entity_data,
                "availability": {"entity": "unavailable"},
                "error_code": CHAT_COMPANY_DATA_ERROR_CODES["ENTITY_NOT_RESOLVED"],
            }

        quote = await asyncio.to_thread(stock_data_service.get_quote_optional, market, symbol)
        history: dict[str, Any] = {}
        history_error = ""
        try:
            history = await build_company_history_dashboard(
                market,
                symbol,
                period="annual",
                force_refresh=force_refresh,
                include_stock_basic=True,
            )
        except Exception as exc:  # noqa: BLE001 - domain adapter returns availability, not raw errors
            history_error = f"{type(exc).__name__}: {str(exc)[:160]}"

        stock_basic = history.get("stock_basic") or {}
        financial_candidates = _financial_candidates_from_dashboard(history)
        financial_fields = {
            field: selected
            for field, values in financial_candidates.items()
            if (selected := _select_metric_candidate(
                values,
                target_period_type=None,
                target_report_year=None,
                allow_fallback=True,
            ))
        }
        modules = history.get("modules") or {}
        financial_history_available = any((m.get("history") for m in modules.values() if isinstance(m, dict)))
        availability = {
            "quote_snapshot": "available" if quote else "unavailable",
            "market_history": "unavailable",
            "company_profile": "available" if stock_basic or entity_data else "unavailable",
            "financial_snapshot": "available" if financial_fields else "unavailable",
            "financial_history": "available" if financial_history_available else ("partial" if financial_fields else "unavailable"),
        }
        warnings = []
        if history_error:
            warnings.append({
                "error_code": CHAT_COMPANY_DATA_ERROR_CODES["FINANCIAL_DATA_PARTIAL"],
                "message": "财务历史服务暂时不可用，已保留可用的公司与行情数据。",
            })
        return {
            "entity": entity_data,
            "quote_snapshot": quote,
            "company_profile": stock_basic or entity_data,
            "financial_fields": financial_fields,
            "financial_metric_candidates": financial_candidates,
            "financial_history": history,
            "availability": availability,
            "warnings": warnings,
            "as_of": history.get("generated_at") or (quote or {}).get("trade_date"),
        }

    async def get_financial_metrics(
        self,
        entity: dict[str, Any],
        requested_metrics: list[str],
        *,
        target_period_type: str | None = None,
        target_report_year: int | None = None,
        allow_fallback: bool = False,
    ) -> dict[str, Any]:
        domain = await self.get_company_domains(entity)
        candidates = domain.get("financial_metric_candidates") or {}
        selected: dict[str, Any] = {}
        unavailable: dict[str, Any] = {}
        for metric in requested_metrics:
            item = _select_metric_candidate(
                candidates.get(metric) or [],
                target_period_type=target_period_type,
                target_report_year=target_report_year,
                allow_fallback=allow_fallback,
            )
            if item and item.get("normalized_value") is not None and item.get("validation_status") in {"verified", "normalized"}:
                selected[metric] = item
            else:
                unavailable[metric] = item or {
                    "validation_status": "unverified",
                    "warnings": ["METRIC_UNAVAILABLE"],
                    "selection_reason": "no_candidate",
                }
        return {
            **domain,
            "financial_fields": selected,
            "unavailable_metrics": unavailable,
            "selection_request": {
                "target_period_type": target_period_type,
                "target_report_year": target_report_year,
                "allow_fallback": allow_fallback,
            },
        }

    async def compare_from_company_data(
        self,
        entities: list[dict[str, Any]],
        *,
        target_period_type: str | None = None,
        target_report_year: int | None = None,
        allow_fallback: bool = False,
    ) -> dict[str, Any]:
        requested_metrics = [
            "revenue",
            "parent_net_profit",
            "roe",
            "operating_cashflow",
            "total_assets",
            "parent_equity",
            "eps",
        ]
        domains = await asyncio.gather(*[
            self.get_financial_metrics(
                entity,
                requested_metrics,
                target_period_type=target_period_type,
                target_report_year=target_report_year,
                allow_fallback=allow_fallback,
            )
            for entity in entities[:5]
        ])
        rows: list[dict[str, Any]] = []
        per_entity_available: list[int] = [0 for _ in domains]
        candidate_common_count = 0
        verified_common_count = 0
        excluded_metrics: list[dict[str, Any]] = []
        for field, label in (
            ("revenue", "营业收入"),
            ("parent_net_profit", "归母净利润"),
            ("roe", "净资产收益率"),
            ("operating_cashflow", "经营现金流"),
            ("total_assets", "总资产"),
            ("parent_equity", "归母净资产"),
            ("eps", "基本每股收益"),
        ):
            values = []
            evidence_ids = []
            for domain in domains:
                item = (domain.get("financial_fields") or {}).get(field)
                values.append(item)
                if item and item.get("evidence_id"):
                    evidence_ids.append(item["evidence_id"])
                    index = len(values) - 1
                    if index < len(per_entity_available):
                        per_entity_available[index] += 1
            comparability = {"comparable": False, "reason_codes": ["MISSING_VALUE"]}
            if len(values) >= 2 and values[0] and values[1]:
                candidate_common_count += 1
                comparability = financial_metric_comparability_service.compare(values[0], values[1])
                if comparability["comparable"]:
                    verified_common_count += 1
                else:
                    excluded_metrics.append({"metric": field, "reason": ",".join(comparability["reason_codes"])})
            rows.append({
                "field": field,
                "label": label,
                "values": values,
                "evidence_ids": evidence_ids,
                "comparability": comparability,
            })
        usable = any(row["evidence_ids"] for row in rows)
        period_alignment = "unknown"
        if len(domains) >= 2:
            left_periods = {
                str((row["values"][0] or {}).get("period_end"))
                for row in rows
                if len(row.get("values") or []) > 0 and (row["values"][0] or {}).get("period_end")
            }
            right_periods = {
                str((row["values"][1] or {}).get("period_end"))
                for row in rows
                if len(row.get("values") or []) > 1 and (row["values"][1] or {}).get("period_end")
            }
            if left_periods and right_periods:
                period_alignment = "same_year" if left_periods & right_periods else "different_period"
        return {
            "status": "partial_success" if usable else "failed",
            "entities": [domain.get("entity") for domain in domains],
            "domains": domains,
            "comparison_rows": rows,
            "availability": {str((domain.get("entity") or {}).get("symbol")): domain.get("availability") for domain in domains},
            "comparison_summary": {
                "requested_metric_count": len(rows),
                "left_available_metric_count": per_entity_available[0] if per_entity_available else 0,
                "right_available_metric_count": per_entity_available[1] if len(per_entity_available) > 1 else 0,
                "left_non_null_count": per_entity_available[0] if per_entity_available else 0,
                "right_non_null_count": per_entity_available[1] if len(per_entity_available) > 1 else 0,
                "candidate_common_count": candidate_common_count,
                "verified_common_count": verified_common_count,
                "common_metric_count": verified_common_count,
                "excluded_metrics": excluded_metrics,
                "period_alignment": period_alignment,
                "financial_values_verified": verified_common_count > 0,
                "report_text_verified": False,
            },
            "per_entity": [
                {
                    "entity": domain.get("entity"),
                    "report_selection": {"status": "unavailable", "report_id": None, "period": None},
                    "financial_snapshot": {
                        "status": "success" if (domain.get("financial_fields") or {}) else "unavailable",
                        "metrics": list((domain.get("financial_fields") or {}).values()),
                    },
                    "rag_evidence": {"status": "unavailable", "chunk_count": 0},
                    "availability": {
                        "company_profile": bool(domain.get("company_profile")),
                        "financial_snapshot": bool(domain.get("financial_fields")),
                        "financial_history": domain.get("availability", {}).get("financial_history") in {"available", "partial"},
                        "official_report": False,
                        "rag_chunks": False,
                    },
                }
                for domain in domains
            ],
            "warnings": [
                {
                    "error_code": "RAG_DATABASE_UNAVAILABLE",
                    "message": "报告原文核验暂不可用，以下先使用 Company 页面已缓存的结构化数据。",
                }
            ],
        }


company_chat_data_service = CompanyChatDataService()
