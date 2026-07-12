from __future__ import annotations

import json

from app.services.company_v2_data_validation_engine import validate_company_v2_envelope


def _field(value, *, module="profitability", raw_field=None, period="2026-03-31", basis="cumulative", provider_definition="provider_defined"):
    return {
        "value": value,
        "raw_value": value,
        "display_value": str(value),
        "provider": "baostock",
        "raw_field": raw_field,
        "formula_context": {
            "period": period,
            "report_period_type": "quarterly",
            "value_basis": basis,
            "unit": "decimal",
            "percent_scale": "decimal",
            "provider_definition": provider_definition,
            "source_module": module,
            "source_provider": "baostock",
            "raw_field": raw_field,
        },
    }


def _module(module_key, fields):
    return {
        "module_key": module_key,
        "normalized": {"fields": fields, "rows": [{key: item["value"] for key, item in fields.items()}]},
        "render": {"has_displayable_data": True, "visible_fields": list(fields)},
    }


def _payload(profitability=None, dupont=None):
    return {
        "schema_version": "2.0",
        "modules": {
            "profitability": profitability or _module("profitability", {
                "net_margin": _field(0.1, raw_field="npMargin"),
                "net_profit": _field(10, raw_field="netProfit"),
                "revenue": _field(100, raw_field="MBRevenue"),
            }),
            "dupont": dupont or _module("dupont", {
                "roe": _field(0.1, module="dupont", raw_field="dupontROE", provider_definition="simple_formula"),
                "net_margin": _field(0.1, module="dupont", raw_field="dupontPnitoni", provider_definition="simple_formula"),
                "asset_turnover": _field(0.5, module="dupont", raw_field="dupontAssetTurn", provider_definition="simple_formula"),
                "equity_multiplier": _field(2, module="dupont", raw_field="dupontAssetStoEquity", provider_definition="simple_formula"),
            }),
        },
    }


def _check(result, check_id):
    return next(check for check in result["validation_checks"] if check["check_id"] == check_id)


def test_net_margin_strong_check_pass():
    check = _check(validate_company_v2_envelope(_payload()), "net_margin_formula")
    assert check["check_strength"] == "strong"
    assert check["status"] == "pass"


def test_net_margin_period_mismatch_skipped():
    module = _module("profitability", {
        "net_margin": _field(0.1, period="2026-03-31"),
        "net_profit": _field(10, period="2026-06-30"),
        "revenue": _field(100, period="2026-03-31"),
    })
    check = _check(validate_company_v2_envelope(_payload(profitability=module)), "net_margin_formula")
    assert check["status"] == "skipped"
    assert "PERIOD_MISMATCH" in check["tags"]


def test_net_margin_unknown_basis_is_weak_warning():
    module = _module("profitability", {
        "net_margin": _field(0.5, basis="unknown"),
        "net_profit": _field(10, basis="unknown"),
        "revenue": _field(100, basis="unknown"),
    })
    result = validate_company_v2_envelope(_payload(profitability=module))
    check = _check(result, "net_margin_formula")
    assert check["check_strength"] == "weak"
    assert check["status"] == "warning"
    assert result["validation_summary"]["status"] == "warning"


def test_net_margin_cross_module_source_is_weak_warning():
    module = _module("profitability", {
        "net_margin": _field(0.5, module="profitability"),
        "net_profit": _field(10, module="income_statement"),
        "revenue": _field(100, module="income_statement"),
    })
    check = _check(validate_company_v2_envelope(_payload(profitability=module)), "net_margin_formula")
    assert check["check_strength"] == "weak"
    assert check["status"] == "warning"
    assert "CROSS_MODULE_MIXED_SOURCE" in check["tags"]


def test_dupont_same_module_strong_check_and_strong_fail():
    pass_check = _check(validate_company_v2_envelope(_payload()), "dupont_roe_formula")
    assert pass_check["check_strength"] == "strong"
    assert pass_check["status"] == "pass"

    dupont = _module("dupont", {
        "roe": _field(0.4, module="dupont", provider_definition="simple_formula"),
        "net_margin": _field(0.1, module="dupont", provider_definition="simple_formula"),
        "asset_turnover": _field(0.5, module="dupont", provider_definition="simple_formula"),
        "equity_multiplier": _field(2, module="dupont", provider_definition="simple_formula"),
    })
    result = validate_company_v2_envelope(_payload(dupont=dupont))
    check = _check(result, "dupont_roe_formula")
    assert check["check_strength"] == "strong"
    assert check["status"] == "fail"
    assert result["validation_summary"]["status"] == "fail"


def test_dupont_cross_module_mixed_source_is_weak_warning():
    dupont = _module("dupont", {
        "roe": _field(0.4, module="dupont", provider_definition="simple_formula"),
        "net_margin": _field(0.1, module="profitability", provider_definition="simple_formula"),
        "asset_turnover": _field(0.5, module="operation_capability", provider_definition="simple_formula"),
        "equity_multiplier": _field(2, module="solvency", provider_definition="simple_formula"),
    })
    check = _check(validate_company_v2_envelope(_payload(dupont=dupont)), "dupont_roe_formula")
    assert check["check_strength"] == "weak"
    assert check["status"] == "warning"
    assert "CROSS_MODULE_MIXED_SOURCE" in check["tags"]


def test_dupont_provider_defined_fields_are_semantic_warning():
    dupont = _module("dupont", {
        "roe": _field(0.02, module="dupont", raw_field="dupont_roe", provider_definition="dupont_provider_defined"),
        "net_margin": _field(0.9, module="dupont", raw_field="dupont_npi", provider_definition="dupont_provider_defined"),
        "asset_turnover": _field(0.4, module="dupont", raw_field="dupont_at", provider_definition="dupont_provider_defined"),
        "equity_multiplier": _field(3, module="dupont", raw_field="dupont_am", provider_definition="dupont_provider_defined"),
    })
    result = validate_company_v2_envelope(_payload(dupont=dupont))
    check = _check(result, "dupont_roe_formula")
    assert check["check_strength"] == "weak"
    assert check["status"] == "warning"
    assert "DUPONT_PROVIDER_DEFINED" in check["tags"]
    assert result["validation_summary"]["semantic_warning_count"] >= 1


def test_check_strength_and_formula_context_exist_in_evidence():
    result = validate_company_v2_envelope(_payload())
    check = _check(result, "net_margin_formula")
    assert check["check_strength"] == "strong"
    assert check["evidence"][0]["formula_context"][0]["period"] == "2026-03-31"


def test_no_sensitive_or_restricted_wording_in_validation_output():
    text = json.dumps(validate_company_v2_envelope(_payload()), ensure_ascii=False)
    for word in ["secret", "token", "local_path", "目标价", "保证上涨"]:
        assert word not in text
