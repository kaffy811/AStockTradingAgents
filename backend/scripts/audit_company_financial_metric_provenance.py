"""Audit Company V2 financial metric provenance for Chat fallback.

Usage:
  python scripts/audit_company_financial_metric_provenance.py --market CN --symbol 000858 --report-year 2025

The script reads the same CompanyChatDataService adapter used by Chat fallback.
It does not print secrets, database URLs, JWTs, provider tokens, or user data.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.company_chat_data_service import company_chat_data_service
from app.services.financial_metric_comparability import metric_normalizer


DEFAULT_METRICS = [
    "revenue",
    "parent_net_profit",
    "roe",
    "operating_cashflow",
    "total_assets",
    "parent_equity",
    "eps",
]


def _safe_candidate(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "metric_id": item.get("metric_id"),
        "metric": item.get("metric"),
        "raw_value": item.get("raw_value"),
        "raw_unit": item.get("raw_unit"),
        "normalized_value": item.get("normalized_value"),
        "normalized_unit": item.get("normalized_unit"),
        "period_end": item.get("period_end"),
        "period_type": item.get("period_type"),
        "report_year": item.get("report_year"),
        "accounting_scope": item.get("accounting_scope"),
        "value_type": item.get("value_type"),
        "source_id": item.get("source_id"),
        "source_type": item.get("source_type"),
        "source": item.get("source"),
        "source_key": item.get("source_key"),
        "as_of": item.get("as_of"),
        "validation_status": item.get("validation_status"),
        "warnings": item.get("warnings") or [],
        "selection_reason": item.get("selection_reason"),
    }


def _audit_metric(
    *,
    metric: str,
    selected: dict[str, Any] | None,
    unavailable: dict[str, Any] | None,
    candidates: list[dict[str, Any]],
    entity: dict[str, Any],
    retrieved_at: str,
) -> dict[str, Any]:
    item = selected or unavailable or {}
    normalized = metric_normalizer.normalize(item, metric) if item and item.get("raw_value") is not None else item
    raw = {
        "value": normalized.get("raw_value") if normalized else None,
        "unit": normalized.get("raw_unit") if normalized else None,
        "source_key": normalized.get("source_key") if normalized else None,
        "source_payload_path": f"CompanyChatDataService.financial_metric_candidates.{metric}",
        "period_end": normalized.get("period_end") if normalized else None,
        "period_type": normalized.get("period_type") if normalized else None,
        "report_year": normalized.get("report_year") if normalized else None,
        "value_type": normalized.get("value_type") if normalized else None,
    }
    normalization = {
        "normalized_value": normalized.get("normalized_value") if normalized else None,
        "normalized_unit": normalized.get("normalized_unit") if normalized else None,
        "rule": _normalization_rule(normalized or {}),
        "warnings": normalized.get("warnings") if normalized else ["METRIC_UNAVAILABLE"],
    }
    provenance = {
        "service": "CompanyChatDataService",
        "repository": "company_v2_history_service.build_company_history_dashboard",
        "table_or_provider": normalized.get("source") if normalized else None,
        "record_id": normalized.get("source_id") if normalized else None,
        "retrieved_at": retrieved_at,
        "as_of": normalized.get("as_of") if normalized else None,
    }
    validation = {
        "status": normalized.get("validation_status") if normalized else "unverified",
        "reason_codes": normalized.get("warnings") if normalized else ["METRIC_UNAVAILABLE"],
    }
    return {
        "entity": entity,
        "metric": metric,
        "raw": raw,
        "normalization": normalization,
        "provenance": provenance,
        "validation": validation,
        "candidates": [_safe_candidate(candidate) for candidate in candidates[:10]],
        "conflict": _conflict_audit(metric, candidates),
    }


def _normalization_rule(item: dict[str, Any]) -> str:
    raw_unit = item.get("raw_unit")
    normalized_unit = item.get("normalized_unit")
    if raw_unit == "ratio" and normalized_unit == "percent":
        return "percentage_fraction x 100"
    if raw_unit in {"percent", "%"} and normalized_unit == "percent":
        return "percentage points unchanged"
    if raw_unit in {"亿元", "万元", "元", "CNY"} and normalized_unit == "CNY":
        return f"{raw_unit} -> CNY scale"
    if raw_unit in {"元/股", "CNY/share"}:
        return "per-share value unchanged"
    return "unverified"


def _conflict_audit(metric: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    by_period: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        period = str(candidate.get("period_end") or "unknown")
        by_period.setdefault(period, []).append(candidate)
    conflicts = []
    for period, items in by_period.items():
        values = {
            (
                str(item.get("normalized_unit")),
                round(float(item.get("normalized_value")), 4)
            )
            for item in items
            if item.get("normalized_value") is not None
        }
        if len(values) > 1:
            conflicts.append({
                "metric": metric,
                "period_end": period,
                "candidates": [_safe_candidate(item) for item in items],
                "selected": None,
                "status": "conflict",
                "reason": "SAME_PERIOD_VALUE_MISMATCH",
            })
    return {"status": "conflict" if conflicts else "consistent", "items": conflicts}


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    metrics = [args.metric] if args.metric else DEFAULT_METRICS
    target_period_type = args.period_type
    result = await company_chat_data_service.get_financial_metrics(
        {"market": args.market, "symbol": args.symbol, "name": args.symbol},
        metrics,
        target_period_type=target_period_type,
        target_report_year=args.report_year,
        allow_fallback=args.allow_fallback,
    )
    entity = result.get("entity") or {"market": args.market, "symbol": args.symbol}
    retrieved_at = datetime.now(timezone.utc).isoformat()
    candidates_by_metric = result.get("financial_metric_candidates") or {}
    selected = result.get("financial_fields") or {}
    unavailable = result.get("unavailable_metrics") or {}
    audits = [
        _audit_metric(
            metric=metric,
            selected=selected.get(metric),
            unavailable=unavailable.get(metric),
            candidates=candidates_by_metric.get(metric) or [],
            entity=entity,
            retrieved_at=retrieved_at,
        )
        for metric in metrics
    ]
    return {
        "schema_version": "1.0",
        "generated_at": retrieved_at,
        "request": {
            "market": args.market,
            "symbol": args.symbol,
            "metric": args.metric,
            "report_year": args.report_year,
            "period_type": target_period_type,
            "allow_fallback": args.allow_fallback,
        },
        "entity": entity,
        "service_chain": [
            "Company page controller -> company_v2_history_service.build_company_history_dashboard",
            "Chat fallback -> CompanyChatDataService -> same company_v2_history_service",
            "MetricNormalizer -> FinancialMetricComparabilityService",
        ],
        "metrics": audits,
        "availability": result.get("availability") or {},
        "warnings": result.get("warnings") or [],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", default="CN")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--metric")
    parser.add_argument("--report-year", type=int)
    parser.add_argument("--period-type", default="annual")
    parser.add_argument("--allow-fallback", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    with contextlib.redirect_stdout(sys.stderr):
        payload = asyncio.run(_run(args))
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
