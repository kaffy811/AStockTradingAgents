from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "backend/scripts/recapture_company_v2_phase6p.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("recapture_company_v2_phase6p", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _field(value, display_value=None, *, computed=False, formula=None, source="baostock_aggregate"):
    return {
        "value": value,
        "raw_value": value,
        "normalized_value": value,
        "display_value": display_value if display_value is not None else str(value),
        "display_type": "money" if computed else "float",
        "source": "computed" if computed else source,
        "provider": "computed" if computed else "baostock",
        "raw_field": None if computed else "raw",
        "computed": computed,
        "computed_formula": formula,
        "confidence": 0.75 if computed else 0.95,
    }


def _module(module_key, fields, *, visible=None, primary_issue="OK", data_success=True):
    visible = visible or list(fields)
    return {
        "module_key": module_key,
        "source_chain": [{
            "provider": "baostock",
            "endpoint": "get_all_financial_indicators",
            "success": True,
            "data_success": data_success,
            "rows_count": 1,
        }],
        "normalized": {"rows": [dict((k, v["value"]) for k, v in fields.items())], "fields": fields, "metrics": {}},
        "render": {"renderable": True, "has_displayable_data": bool(visible), "table_renderable": bool(visible), "visible_fields": visible},
        "coverage": {
            "required_fields": max(len(visible), 1),
            "filled_fields": len(visible),
            "computed_fields": sum(1 for item in fields.values() if item.get("computed")),
            "missing_fields": 0,
            "coverage_pct": 100,
            "missing_field_map": {},
        },
        "field_trace": {
            key: {
                "provider": value.get("provider"),
                "raw_field": value.get("raw_field"),
                "normalized_field": key,
                "formatter": value.get("display_type"),
                "computed": value.get("computed"),
                "computed_formula": value.get("computed_formula"),
                "source_fields": ["latest_price", "total_share"] if value.get("computed") else [],
            }
            for key, value in fields.items()
        },
        "provider_summary": {"baostock": {"success": True, "data_success": data_success}},
        "diagnosis": {"primary_issue": primary_issue, "tags": [primary_issue], "coverage_pct": 100},
    }


def _payload():
    quote_fields = {
        "latest_price": _field(4.96, "4.96", source="baostock_kline_fallback"),
        "market_cap": _field(4960, "4960.00", computed=True, formula="latest_price * total_share"),
        "float_market_cap": _field(4464, "4464.00", computed=True, formula="latest_price * float_share"),
    }
    quote = _module("quote_overview", quote_fields, primary_issue="OK_WITH_FALLBACK")
    quote["normalized"]["rows"][0].update({
        "price_is_realtime": False,
        "price_label": "最近收盘价",
        "price_data_status": "historical_fallback",
        "price_source": "baostock_kline_fallback",
        "latest_price_source": "baostock_kline_fallback",
    })
    quote["normalized"]["metrics"] = quote["normalized"]["rows"][0]
    valuation = _module("valuation", {
        "pe_ttm": _field(10.85, "10.85"),
        "market_cap": quote_fields["market_cap"],
        "float_market_cap": quote_fields["float_market_cap"],
    })
    modules = {"quote_overview": quote, "valuation": valuation}
    for key in ["profitability", "growth", "cashflow_quality", "solvency", "operation_capability"]:
        modules[key] = _module(key, {"roe": _field(0.1, "10.00%")})
    modules["dupont"] = _module("dupont", {"roe": _field(0.1, "10.00%")}, visible=[])
    modules["report_documents"] = _module("report_documents", {}, visible=[], primary_issue="REPORT_PDF_NOT_FOUND")
    modules["report_documents"]["normalized"]["rows"] = [{"documents_count": 0, "report_status": "EMPTY"}]
    modules["report_rag"] = _module("report_rag", {}, visible=[], primary_issue="REPORT_PDF_NOT_FOUND")
    modules["report_rag"]["normalized"]["rows"] = [{"documents_count": 0, "chunks_count": 0, "embedding_count": 0, "rag_status": "REPORT_PDF_NOT_FOUND"}]
    modules["ai_analysis_status"] = _module("ai_analysis_status", {"summary": _field("structured summary", "structured summary", source="deterministic")})
    return {
        "schema_version": "2.0",
        "request_id": "r1",
        "summary": {
            "providers_attempted": 8,
            "providers_success": 8,
            "providers_data_success": 6,
            "provider_data_failure_count": 2,
            "providers_timeout": 0,
            "modules_renderable": 9,
            "modules_unavailable": 2,
            "mapping_error_count": 0,
            "render_rule_error_count": 0,
        },
        "agent_summary": {"overall_coverage_pct": 88.5, "computed_fields_count": 2},
        "modules": modules,
    }


def test_gate_passes_with_schema_metadata_and_computed_fields():
    gate = _load_gate()
    result = gate.analyze_payload(_payload(), "600519")
    assert result["schema_version"] == "2.0"
    assert result["agent_summary.overall_coverage_pct"] == 88.5
    assert result["providers_data_success"] == 6
    assert result["market_cap_computed"] is True
    assert result["float_market_cap_computed"] is True
    assert result["gate_passed"] is True


def test_numeric_raw_display_dash_fails_formatter_scan():
    gate = _load_gate()
    payload = _payload()
    payload["modules"]["quote_overview"]["normalized"]["fields"]["latest_price"]["display_value"] = "—"
    result = gate.analyze_payload(payload, "600519")
    assert "FORMATTER_SCAN_FAILED" in result["gate_failure_reasons"]
    assert result["formatter_failures"][0]["field_name"] == "latest_price"


def test_akshare_wrapper_success_business_failed_provider_summary_split():
    gate = _load_gate()
    payload = _payload()
    payload["modules"]["quote_overview"]["provider_summary"]["akshare"] = {
        "success": True,
        "data_success": False,
        "reason_code": "NETWORK_UNAVAILABLE",
    }
    assert gate.scan_provider_summary(payload) == []
    assert payload["modules"]["quote_overview"]["provider_summary"]["akshare"]["success"] is True
    assert payload["modules"]["quote_overview"]["provider_summary"]["akshare"]["data_success"] is False


def test_baostock_fallback_price_semantics_are_required():
    gate = _load_gate()
    payload = _payload()
    assert gate.scan_price_semantics(payload) == []
    payload["modules"]["quote_overview"]["normalized"]["rows"][0]["price_label"] = "最新价"
    assert gate.scan_price_semantics(payload)


def test_field_trace_must_cover_visible_fields_and_coverage_exists():
    gate = _load_gate()
    payload = _payload()
    del payload["modules"]["quote_overview"]["field_trace"]["latest_price"]
    result = gate.analyze_payload(payload, "600519")
    assert result["trace_missing_count"] == 1
    assert "COVERAGE_TRACE_FAILED" in result["gate_failure_reasons"]


def test_missing_computed_field_emits_failure_reasons():
    gate = _load_gate()
    payload = _payload()
    payload["modules"]["profitability"]["normalized"]["fields"]["total_share"] = _field(1000, "1000")
    for module_key in ["quote_overview", "valuation"]:
        payload["modules"][module_key]["normalized"]["fields"].pop("market_cap", None)
        payload["modules"][module_key]["field_trace"].pop("market_cap", None)
    result = gate.analyze_payload(payload, "600519")
    assert "COMPUTED_FIELDS_FAILED" in result["gate_failure_reasons"]
    assert "MISSING_COMPUTED_FIELD" in result["computed_field_failures"]
    assert "SHARE_CAPITAL_CONTEXT_NOT_REUSED" in result["computed_field_failures"]


def test_report_documents_and_rag_empty_are_not_ok():
    gate = _load_gate()
    payload = _payload()
    payload["modules"]["report_documents"]["diagnosis"]["primary_issue"] = "OK"
    payload["modules"]["report_rag"]["diagnosis"]["primary_issue"] = "OK"
    result = gate.analyze_payload(payload, "600519")
    assert "COVERAGE_TRACE_FAILED" in result["gate_failure_reasons"]


def test_gate_failure_reasons_and_failure_classification_for_no_provider_data():
    gate = _load_gate()
    payload = _payload()
    payload["summary"]["providers_data_success"] = 0
    payload["modules"]["quote_overview"]["source_chain"].append({
        "provider": "akshare",
        "success": True,
        "data_success": False,
        "rows_count": 2,
        "error_code": "PROVIDER_NETWORK_ERROR",
    })
    result = gate.analyze_payload(payload, "600519")
    assert "NO_PROVIDER_DATA_SUCCESS" in result["gate_failure_reasons"]
    assert "NETWORK_UNAVAILABLE" in result["failure_classification"]


def test_sensitive_payload_scan_detects_forbidden_debug_keys():
    gate = _load_gate()
    payload = _payload()
    payload["modules"]["quote_overview"]["raw"] = {"x": {"local_path": "/tmp/a.pdf"}}
    result = gate.analyze_payload(payload, "600519")
    assert "SENSITIVE_PAYLOAD_FAILED" in result["gate_failure_reasons"]
    assert "local_path" in result["sensitive_payload_failures"]
