#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


FINANCIAL_MODULES = [
    "profitability",
    "growth",
    "cashflow_quality",
    "solvency",
    "operation_capability",
    "dupont",
]
REALTIME_PROVIDERS = {"akshare", "tencent", "sina", "eastmoney"}
RESTRICTED_PATTERNS = [
    "token",
    "secret",
    "local_path",
    "target_price",
    "analyst_rating",
    "建议买入",
    "建议卖出",
    "保证上涨",
]


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() in ("", "—", "--", "nan", "NaN"):
        return True
    if isinstance(value, float) and value != value:
        return True
    return False


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _get_module(payload: dict[str, Any], module_key: str) -> dict[str, Any]:
    module = (payload.get("modules") or {}).get(module_key)
    return module if isinstance(module, dict) else {}


def _visible_fields(module: dict[str, Any]) -> list[str]:
    render = module.get("render") or {}
    visible = render.get("visible_fields") or []
    return visible if isinstance(visible, list) else []


def _fields(module: dict[str, Any]) -> dict[str, Any]:
    normalized = module.get("normalized") or {}
    fields = normalized.get("fields") or {}
    return fields if isinstance(fields, dict) else {}


def _first_row(module: dict[str, Any]) -> dict[str, Any]:
    rows = (module.get("normalized") or {}).get("rows") or []
    return rows[0] if rows and isinstance(rows[0], dict) else {}


def scan_formatter(payload: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for module_key, module in (payload.get("modules") or {}).items():
        field_trace = module.get("field_trace") or {}
        for field_name, field in _fields(module).items():
            if not isinstance(field, dict):
                continue
            raw_value = field.get("raw_value")
            if not _is_number(raw_value):
                continue
            if field.get("display_suppressed") is True:
                continue
            if field.get("display_value") == "—":
                failures.append({
                    "module_key": module_key,
                    "field_name": field_name,
                    "raw_value": raw_value,
                    "display_value": field.get("display_value"),
                    "display_type": field.get("display_type"),
                    "source": field.get("source"),
                    "field_trace": field_trace.get(field_name),
                })
    return failures


def scan_price_semantics(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    quote = _get_module(payload, "quote_overview")
    row = _first_row(quote)
    fields = _fields(quote)
    latest = fields.get("latest_price") if isinstance(fields.get("latest_price"), dict) else {}
    latest_source = row.get("latest_price_source") or latest.get("source")
    price_source = row.get("price_source") or latest_source
    realtime_data_success = any(
        source.get("provider") in REALTIME_PROVIDERS and source.get("data_success") is True
        for source in quote.get("source_chain") or []
        if isinstance(source, dict)
    )
    latest_value = latest.get("value") if isinstance(latest, dict) else row.get("latest_price")

    if price_source == "baostock_kline_fallback" or latest_source == "baostock_kline_fallback" or (
        not realtime_data_success and not _is_empty(latest_value)
    ):
        if row.get("price_is_realtime") is not False:
            failures.append("historical fallback price must set price_is_realtime=false")
        if row.get("price_label") != "最近收盘价":
            failures.append("historical fallback price must use price_label=最近收盘价")
        if row.get("price_data_status") != "historical_fallback":
            failures.append("historical fallback price must use price_data_status=historical_fallback")

    if realtime_data_success and not _is_empty(latest_value):
        if row.get("price_is_realtime") is not True:
            failures.append("realtime provider business success must set price_is_realtime=true")
        if row.get("price_label") != "最新价":
            failures.append("realtime provider business success must use price_label=最新价")
        if row.get("price_data_status") != "realtime":
            failures.append("realtime provider business success must use price_data_status=realtime")
    return failures


def scan_computed_fields(payload: dict[str, Any]) -> dict[str, Any]:
    quote = _get_module(payload, "quote_overview")
    valuation = _get_module(payload, "valuation")
    profitability = _get_module(payload, "profitability")
    profit_fields = _fields(profitability)
    share_capital_available = any(
        isinstance(profit_fields.get(field), dict) and not _is_empty(profit_fields[field].get("value"))
        for field in ("total_share", "float_share")
    )
    result = {
        "market_cap_computed": False,
        "float_market_cap_computed": False,
        "issues": [],
    }
    for module_key, module in (("quote_overview", quote), ("valuation", valuation)):
        fields = _fields(module)
        trace = module.get("field_trace") or {}
        for field_name in ("market_cap", "float_market_cap"):
            field = fields.get(field_name)
            if isinstance(field, dict) and field.get("computed") is True:
                result[f"{field_name}_computed"] = True
                if "*" not in str(field.get("computed_formula") or ""):
                    result["issues"].append(f"{module_key}.{field_name} computed_formula missing")
                trace_item = trace.get(field_name) or {}
                source_fields = trace_item.get("source_fields") or []
                if not any(name in source_fields for name in ("latest_price", "recent_close")):
                    result["issues"].append(f"{module_key}.{field_name} trace missing price source")
                if not any(name in source_fields for name in ("total_share", "float_share")):
                    result["issues"].append(f"{module_key}.{field_name} trace missing share source")
                if field.get("display_value") == "—":
                    result["issues"].append(f"{module_key}.{field_name} display_value missing")
    if share_capital_available:
        for field_name in ("market_cap", "float_market_cap"):
            if not result[f"{field_name}_computed"]:
                result["issues"].extend(["MISSING_COMPUTED_FIELD", "SHARE_CAPITAL_CONTEXT_NOT_REUSED"])
                break
    return result


def scan_coverage_and_trace(payload: dict[str, Any]) -> tuple[list[str], int]:
    failures: list[str] = []
    trace_missing_count = 0
    for module_key, module in (payload.get("modules") or {}).items():
        if not isinstance(module, dict):
            continue
        if "coverage" not in module or not isinstance(module.get("coverage"), dict):
            failures.append(f"{module_key}: coverage missing")
        if "provider_summary" not in module or not isinstance(module.get("provider_summary"), dict):
            failures.append(f"{module_key}: provider_summary missing")
        field_trace = module.get("field_trace") or {}
        for field in _visible_fields(module):
            if field not in field_trace:
                trace_missing_count += 1
                failures.append(f"{module_key}.{field}: field_trace missing")
        diagnosis = module.get("diagnosis") or {}
        if module_key in {"report_documents", "report_rag"} and diagnosis.get("primary_issue") == "OK":
            failures.append(f"{module_key}: empty report/RAG must not diagnose OK")
        missing_map = (module.get("coverage") or {}).get("missing_field_map") or {}
        if any(field in missing_map for field in ("market_cap", "float_market_cap")) and diagnosis.get("primary_issue") == "OK":
            failures.append(f"{module_key}: missing market cap cannot diagnose OK")
    return failures, trace_missing_count


def scan_provider_summary(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    summary = payload.get("summary") or {}
    if "providers_data_success" not in summary:
        failures.append("summary.providers_data_success missing")
    if "provider_data_failure_count" not in summary:
        failures.append("summary.provider_data_failure_count missing")
    for module_key, module in (payload.get("modules") or {}).items():
        provider_summary = module.get("provider_summary") or {}
        for provider, item in provider_summary.items():
            if "success" not in item or "data_success" not in item:
                failures.append(f"{module_key}.{provider}: success/data_success split missing")
    return failures


def scan_sensitive_payload(payload: dict[str, Any]) -> list[str]:
    text = _json_dumps(payload).lower()
    failures = []
    for pattern in RESTRICTED_PATTERNS:
        needle = pattern.lower()
        if needle in {"token", "secret"}:
            if re.search(rf'"[^"]*{needle}[^"]*"\s*:\s*"[^"]+"', text):
                failures.append(pattern)
        elif needle in text:
            failures.append(pattern)
    return failures


def classify_failure(payload: dict[str, Any]) -> list[str]:
    classifications: set[str] = set()
    for module in (payload.get("modules") or {}).values():
        for source in module.get("source_chain") or []:
            code = source.get("error_code") or source.get("reason_code")
            status = source.get("status")
            if code in {"PROVIDER_NETWORK_ERROR", "NETWORK_UNAVAILABLE"} or status == "network_error":
                classifications.add("NETWORK_UNAVAILABLE")
            if code in {"AUTH_REQUIRED", "PROVIDER_AUTH_FAILED"}:
                classifications.add("PROVIDER_AUTH_FAILED")
            if code == "PROVIDER_SCHEMA_CHANGED" or status == "schema_error":
                classifications.add("PROVIDER_SCHEMA_CHANGED")
        if (module.get("diagnosis") or {}).get("primary_issue") == "MAPPING_ERROR":
            classifications.add("NORMALIZER_EMPTY")
    if (payload.get("summary") or {}).get("cache_hit_count", 0) and (payload.get("summary") or {}).get("providers_data_success", 0) == 0:
        classifications.add("CACHE_ONLY_NO_RAW")
    if not classifications:
        classifications.add("DEBUG_SERVICE_BUG")
    return sorted(classifications)


def analyze_payload(payload: dict[str, Any], symbol: str, http_status: int = 200) -> dict[str, Any]:
    summary = payload.get("summary") or {}
    quote = _get_module(payload, "quote_overview")
    quote_row = _first_row(quote)
    report_row = _first_row(_get_module(payload, "report_documents"))
    rag_row = _first_row(_get_module(payload, "report_rag"))
    formatter_failures = scan_formatter(payload)
    price_failures = scan_price_semantics(payload)
    computed_scan = scan_computed_fields(payload)
    coverage_failures, trace_missing_count = scan_coverage_and_trace(payload)
    provider_summary_failures = scan_provider_summary(payload)
    sensitive_failures = scan_sensitive_payload(payload)
    financial_renderable_count = sum(
        1 for module_key in FINANCIAL_MODULES
        if ((_get_module(payload, module_key).get("render") or {}).get("has_displayable_data") is True)
    )
    stale_fallback = any(
        source.get("cache_stale")
        for module in (payload.get("modules") or {}).values()
        for source in module.get("source_chain") or []
        if isinstance(source, dict)
    )

    gate_failure_reasons: list[str] = []
    if http_status != 200:
        gate_failure_reasons.append(f"HTTP_{http_status}")
    if payload.get("schema_version") != "2.0":
        gate_failure_reasons.append("SCHEMA_VERSION_NOT_2_0")
    if summary.get("providers_timeout", 0) > 0 and not stale_fallback:
        gate_failure_reasons.append("PROVIDER_TIMEOUT_WITHOUT_STALE_FALLBACK")
    if summary.get("providers_data_success", 0) < 1:
        gate_failure_reasons.append("NO_PROVIDER_DATA_SUCCESS")
    if summary.get("modules_renderable", 0) < 9:
        gate_failure_reasons.append("MODULES_RENDERABLE_BELOW_9")
    if (_get_module(payload, "quote_overview").get("render") or {}).get("has_displayable_data") is not True:
        gate_failure_reasons.append("QUOTE_OVERVIEW_NOT_RENDERABLE")
    if (_get_module(payload, "valuation").get("render") or {}).get("has_displayable_data") is not True:
        gate_failure_reasons.append("VALUATION_NOT_RENDERABLE")
    if financial_renderable_count < 5:
        gate_failure_reasons.append("FINANCIAL_MODULES_RENDERABLE_BELOW_5")
    for label, failures in (
        ("FORMATTER_SCAN_FAILED", formatter_failures),
        ("PRICE_SEMANTICS_FAILED", price_failures),
        ("COMPUTED_FIELDS_FAILED", computed_scan["issues"]),
        ("COVERAGE_TRACE_FAILED", coverage_failures),
        ("PROVIDER_SUMMARY_FAILED", provider_summary_failures),
        ("SENSITIVE_PAYLOAD_FAILED", sensitive_failures),
    ):
        if failures:
            gate_failure_reasons.append(label)
    if "agent_summary" not in payload:
        gate_failure_reasons.append("AGENT_SUMMARY_MISSING")

    coverage_values = [
        float((module.get("coverage") or {}).get("coverage_pct") or 0)
        for module in (payload.get("modules") or {}).values()
        if isinstance(module, dict) and isinstance(module.get("coverage"), dict)
    ]
    coverage_avg = round(sum(coverage_values) / len(coverage_values), 2) if coverage_values else 0.0

    return {
        "symbol": symbol,
        "request_id": payload.get("request_id"),
        "schema_version": payload.get("schema_version"),
        "providers_attempted": summary.get("providers_attempted", 0),
        "providers_success": summary.get("providers_success", 0),
        "providers_data_success": summary.get("providers_data_success", 0),
        "provider_data_failure_count": summary.get("provider_data_failure_count", 0),
        "providers_timeout": summary.get("providers_timeout", 0),
        "modules_renderable": summary.get("modules_renderable", 0),
        "modules_unavailable": summary.get("modules_unavailable", 0),
        "coverage_avg": coverage_avg,
        "mapping_error_count": summary.get("mapping_error_count", 0),
        "render_rule_error_count": summary.get("render_rule_error_count", 0),
        "trace_missing_count": trace_missing_count,
        "computed_fields_count": (payload.get("agent_summary") or {}).get("computed_fields_count", 0),
        "market_cap_computed": computed_scan["market_cap_computed"],
        "float_market_cap_computed": computed_scan["float_market_cap_computed"],
        "price_data_status": quote_row.get("price_data_status"),
        "price_is_realtime": quote_row.get("price_is_realtime"),
        "price_label": quote_row.get("price_label"),
        "report_status": report_row.get("report_status"),
        "rag_status": rag_row.get("rag_status"),
        "agent_summary.overall_coverage_pct": (payload.get("agent_summary") or {}).get("overall_coverage_pct"),
        "formatter_failures": formatter_failures,
        "price_semantics_failures": price_failures,
        "computed_field_failures": computed_scan["issues"],
        "coverage_diagnosis_failures": coverage_failures,
        "provider_summary_failures": provider_summary_failures,
        "sensitive_payload_failures": sensitive_failures,
        "failure_classification": classify_failure(payload) if summary.get("providers_data_success", 0) == 0 else [],
        "gate_passed": not gate_failure_reasons,
        "gate_failure_reasons": gate_failure_reasons,
    }


async def fetch_direct(market: str, symbol: str, include_raw: bool, force_refresh: bool) -> tuple[int, dict[str, Any]]:
    from app.services.company_v2_debug_service import company_v2_debug_service

    payload = await company_v2_debug_service.build_full(
        market,
        symbol,
        include_raw=include_raw,
        providers=["baostock", "akshare", "tencent", "sina", "eastmoney", "pdf"],
        force_refresh=force_refresh,
        max_raw_chars=20000,
        db=None,
    )
    return 200, payload


def fetch_http(base_url: str, market: str, symbol: str, include_raw: bool, force_refresh: bool) -> tuple[int, dict[str, Any]]:
    root = base_url.rstrip("/")
    params = urlencode({
        "include_raw": str(include_raw).lower(),
        "force_refresh": str(force_refresh).lower(),
        "max_raw_chars": "20000",
    })
    url = f"{root}/api/v2/company/{market}/{symbol}/debug/full?{params}"
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=120) as response:
        body = response.read().decode("utf-8")
        return int(response.status), json.loads(body)


def write_summary_md(path: Path, records: list[dict[str, Any]]) -> None:
    lines = [
        "# CompanyV2 Phase 6P Recapture Summary",
        "",
        "| Symbol | Gate | providers_data_success | modules_renderable | coverage_avg | price_label | failures |",
        "| --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for record in records:
        failures = ", ".join(record.get("gate_failure_reasons") or []) or "—"
        lines.append(
            f"| {record['symbol']} | {'PASS' if record['gate_passed'] else 'FAIL'} | "
            f"{record['providers_data_success']} | {record['modules_renderable']} | "
            f"{record['coverage_avg']} | {record.get('price_label') or '—'} | {failures} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_failure_analysis(path: Path, records: list[dict[str, Any]]) -> None:
    failed = [record for record in records if record.get("failure_classification")]
    if not failed:
        if path.exists():
            path.unlink()
        return
    lines = ["# CompanyV2 Phase 6P Recapture Failure Analysis", ""]
    for record in failed:
        lines.extend([
            f"## {record['symbol']}",
            "",
            f"- classifications: {', '.join(record['failure_classification'])}",
            f"- gate_failure_reasons: {', '.join(record['gate_failure_reasons']) or '—'}",
            f"- providers_data_success: {record['providers_data_success']}",
            f"- modules_renderable: {record['modules_renderable']}",
            "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


async def run_recapture(args: argparse.Namespace) -> list[dict[str, Any]]:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for symbol in args.symbols.split(","):
        symbol = symbol.strip()
        if not symbol:
            continue
        print(f"[START] {args.market}/{symbol}")
        if args.base_url:
            status, payload = fetch_http(args.base_url, args.market, symbol, args.include_raw, args.force_refresh)
        else:
            status, payload = await fetch_direct(args.market, symbol, args.include_raw, args.force_refresh)
        artifact_path = out_dir / f"company_v2_debug_full_{symbol}_phase6p_recapture.json"
        artifact_path.write_text(_json_dumps(payload), encoding="utf-8")
        record = analyze_payload(payload, symbol, http_status=status)
        records.append(record)
        print(
            f"[{'PASS' if record['gate_passed'] else 'FAIL'}] {symbol} "
            f"providers_data_success={record['providers_data_success']} "
            f"modules_renderable={record['modules_renderable']} "
            f"failures={','.join(record['gate_failure_reasons']) or '—'}"
        )
    summary_json = out_dir / "company_v2_phase6p_recapture_summary.json"
    summary_md = out_dir / "company_v2_phase6p_recapture_summary.md"
    failure_md = out_dir / "company_v2_phase6p_recapture_failure_analysis.md"
    summary_json.write_text(_json_dumps({"records": records, "all_gate_passed": all(r["gate_passed"] for r in records)}), encoding="utf-8")
    write_summary_md(summary_md, records)
    write_failure_analysis(failure_md, records)
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recapture CompanyV2 Phase 6P debug JSON and evaluate Real Provider Data Gate.")
    parser.add_argument("--symbols", default="600519,000725,601686")
    parser.add_argument("--market", default="CN")
    parser.add_argument("--include-raw", default="true", choices=["true", "false"])
    parser.add_argument("--force-refresh", default="true", choices=["true", "false"])
    parser.add_argument("--out-dir", default=str(ROOT_DIR / "backend/docs/artifacts"))
    parser.add_argument("--base-url", default="", help="Optional API base URL, e.g. http://127.0.0.1:8000. If omitted, uses in-process service.")
    args = parser.parse_args()
    args.include_raw = args.include_raw == "true"
    args.force_refresh = args.force_refresh == "true"
    return args


def main() -> int:
    records = asyncio.run(run_recapture(parse_args()))
    return 0 if all(record["gate_passed"] for record in records) else 2


if __name__ == "__main__":
    raise SystemExit(main())
