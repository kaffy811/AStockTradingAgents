from __future__ import annotations

import json

from app.services.company_v2_data_validation_engine import _summary, validate_company_v2_envelope
from app.services.company_v2_debug_service import company_v2_debug_service


def _field(value):
    return {
        "value": value,
        "raw_value": value,
        "normalized_value": value,
        "display_value": str(value),
        "source": "baostock_aggregate",
    }


def _module(module_key: str, fields: dict[str, dict]):
    return {
        "module_key": module_key,
        "normalized": {
            "rows": [{key: item["value"] for key, item in fields.items()}],
            "fields": fields,
            "metrics": {},
        },
        "raw": {},
        "source_chain": [],
        "render": {"has_displayable_data": True, "visible_fields": list(fields)},
        "coverage": {"coverage_pct": 100},
        "field_trace": {key: {"normalized_field": key} for key in fields},
        "provider_summary": {},
        "diagnosis": {"primary_issue": "OK", "tags": ["OK"]},
    }


def _payload(**overrides):
    modules = {
        "quote_overview": _module(
            "quote_overview",
            {
                "latest_price": _field(10),
                "recent_close": _field(10),
                "market_cap": _field(1000),
                "float_market_cap": _field(800),
            },
        ),
        "valuation": _module(
            "valuation",
            {
                "pe_ttm": _field(12),
                "pb": _field(1.2),
                "ps_ttm": _field(3),
                "pcf_ncf_ttm": _field(-2),
                "market_cap": _field(1000),
                "float_market_cap": _field(800),
            },
        ),
        "profitability": _module(
            "profitability",
            {
                "revenue": _field(200),
                "net_profit": _field(20),
                "net_margin": _field(0.1),
                "gross_profit": _field(80),
                "gross_margin": _field(0.4),
                "total_share": _field(100),
                "float_share": _field(80),
            },
        ),
        "dupont": _module(
            "dupont",
            {
                "roe": _field(0.1),
                "net_margin": _field(0.1),
                "asset_turnover": _field(0.5),
                "equity_multiplier": _field(2),
            },
        ),
        "solvency": _module(
            "solvency",
            {
                "current_ratio": _field(2),
                "quick_ratio": _field(1.5),
                "cash_ratio": _field(0.5),
                "debt_ratio": _field(0.5),
                "equity_multiplier": _field(2),
            },
        ),
        "operation_capability": _module(
            "operation_capability",
            {
                "inventory_turnover": _field(5),
                "receivable_turnover": _field(100),
                "asset_turnover": _field(0.5),
            },
        ),
        "cashflow_quality": _module(
            "cashflow_quality",
            {
                "ocf_to_np": _field(1.2),
                "ocf_to_revenue": _field(0.12),
            },
        ),
    }
    for key, value in overrides.items():
        modules[key] = value
    return {"schema_version": "2.0", "agent_summary": {}, "modules": modules}


def _checks_by_id(result):
    return {check["check_id"]: check for check in result["validation_checks"]}


def _check(result, check_id, module_key=None):
    for item in result["validation_checks"]:
        if item["check_id"] == check_id and (module_key is None or item["module_key"] == module_key):
            return item
    raise AssertionError(f"missing check {check_id} {module_key or ''}")


def test_market_cap_formula_pass_and_warning():
    result = validate_company_v2_envelope(_payload())
    assert _check(result, "market_cap_formula", "quote_overview")["status"] == "pass"

    payload = _payload()
    payload["modules"]["quote_overview"]["normalized"]["fields"]["market_cap"]["value"] = 1030
    result = validate_company_v2_envelope(payload)
    assert _check(result, "market_cap_formula", "quote_overview")["status"] == "warning"


def test_float_market_cap_lte_market_cap_fails_when_inverted():
    payload = _payload()
    payload["modules"]["quote_overview"]["normalized"]["fields"]["float_market_cap"]["value"] = 1200
    result = validate_company_v2_envelope(payload)
    assert _checks_by_id(result)["float_market_cap_lte_market_cap"]["status"] == "fail"


def test_dupont_formula_pass_and_warning():
    result = validate_company_v2_envelope(_payload())
    assert _checks_by_id(result)["dupont_roe_formula"]["status"] == "pass"

    payload = _payload()
    payload["modules"]["dupont"]["normalized"]["fields"]["roe"]["value"] = 0.112
    result = validate_company_v2_envelope(payload)
    assert _checks_by_id(result)["dupont_roe_formula"]["status"] == "warning"


def test_profitability_margin_checks():
    result = validate_company_v2_envelope(_payload())
    checks = _checks_by_id(result)
    assert checks["net_margin_formula"]["status"] == "pass"
    assert checks["gross_margin_formula"]["status"] == "pass"


def test_solvency_order_and_equity_formula_checks():
    result = validate_company_v2_envelope(_payload())
    checks = _checks_by_id(result)
    assert checks["current_ratio_gte_quick_ratio"]["status"] == "pass"
    assert checks["quick_ratio_gte_cash_ratio"]["status"] == "pass"
    assert checks["equity_multiplier_debt_ratio_formula"]["status"] == "pass"


def test_negative_valuation_multiple_is_quality_warning_only():
    payload = _payload()
    payload["modules"]["valuation"]["normalized"]["fields"]["pe_ttm"]["value"] = -3
    result = validate_company_v2_envelope(payload)
    check = _checks_by_id(result)["pe_ttm_sanity"]
    assert check["status"] == "warning"
    assert check["severity"] == "warning"
    assert "投资" not in json.dumps(result, ensure_ascii=False)


def test_provider_conflict_check_detects_large_difference():
    payload = _payload()
    payload["modules"]["quote_overview"]["raw"] = {
        "eastmoney": [{"raw_sample": [{"latest_price": 10}]}],
        "sina": [{"raw_sample": [{"latest_price": 12}]}],
    }
    result = validate_company_v2_envelope(payload)
    assert _checks_by_id(result)["latest_price_provider_conflict"]["status"] == "fail"


def test_skipped_check_does_not_reduce_score_and_warning_reduces_score():
    skipped = validate_company_v2_envelope({"schema_version": "2.0", "modules": {}})
    assert skipped["validation_summary"]["data_quality_score"] == 100

    payload = _payload()
    payload["modules"]["valuation"]["normalized"]["fields"]["pb"]["value"] = 80
    warned = validate_company_v2_envelope(payload)
    assert warned["validation_summary"]["data_quality_score"] < 100


def test_critical_failure_sets_summary_fail():
    result = _summary([{
        "check_id": "x",
        "module_key": "x",
        "status": "fail",
        "severity": "critical",
    }])
    assert result["status"] == "fail"
    assert result["critical_failures"] == 1


def test_agent_summary_can_be_enriched_with_validation_fields():
    validation = validate_company_v2_envelope(_payload())
    agent_summary = {}
    company_v2_debug_service._merge_validation_agent_summary(
        agent_summary,
        validation["validation_summary"],
        validation["validation_checks"],
    )
    assert "data_quality_score" in agent_summary
    assert "validation_status" in agent_summary
    assert "critical_validation_failures" in agent_summary


def test_validation_output_has_no_sensitive_debug_keys():
    payload = _payload()
    payload["modules"]["quote_overview"]["raw"] = {"x": [{"raw_sample": [{"local_path": "/tmp/a"}]}]}
    result = validate_company_v2_envelope(payload)
    text = json.dumps(result, ensure_ascii=False)
    assert "local_path" not in text
    assert "secret" not in text.lower()
    assert "token" not in text.lower()
