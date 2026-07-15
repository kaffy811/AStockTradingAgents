from __future__ import annotations

from itertools import combinations
from typing import Any

from app.schemas.company_v2_debug import CompanyV2DebugEnvelope


Check = dict[str, Any]

SEMANTIC_WARNING_TAGS = {
    "PERIOD_MISMATCH",
    "CUMULATIVE_VS_SINGLE_PERIOD_MISMATCH",
    "TTM_VS_QUARTER_MISMATCH",
    "PROVIDER_ACCOUNTING_DEFINITION_DIFFERENT",
    "CROSS_MODULE_MIXED_SOURCE",
    "VALIDATION_FORMULA_NOT_APPLICABLE",
    "DUPONT_PROVIDER_DEFINED",
    "DUPONT_CROSS_MODULE_MIXED_SOURCE",
    "DUPONT_FORMULA_WEAK_CHECK",
    "DUPONT_FORMULA_MISMATCH",
    "CFO_TO_NP_DENOMINATOR_SENSITIVE",
    "ACCOUNTING_DEFINITION_DIFFERENCE",
    "FORMULA_CONTEXT_MISSING",
}


def _payload(envelope: CompanyV2DebugEnvelope | dict[str, Any]) -> dict[str, Any]:
    return envelope.model_dump() if isinstance(envelope, CompanyV2DebugEnvelope) else envelope


def _module(data: dict[str, Any], module_key: str) -> dict[str, Any]:
    modules = data.get("modules")
    if isinstance(modules, dict):
        item = modules.get(module_key)
        return item if isinstance(item, dict) else {}
    return data if data.get("module_key") == module_key else {}


def _fields(module: dict[str, Any]) -> dict[str, Any]:
    return ((module.get("normalized") or {}).get("fields") or {}) if isinstance(module, dict) else {}


def _rows(module: dict[str, Any]) -> list[dict[str, Any]]:
    rows = (module.get("normalized") or {}).get("rows") or []
    return [row for row in rows if isinstance(row, dict)]


def _field_value(module: dict[str, Any], field: str) -> Any:
    item = _fields(module).get(field)
    if isinstance(item, dict) and "value" in item:
        return item.get("value")
    for row in _rows(module):
        if field in row:
            return row.get(field)
    return None


def _field_item(module: dict[str, Any], field: str) -> dict[str, Any]:
    item = _fields(module).get(field)
    return item if isinstance(item, dict) else {}


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number != number else number


def _relative_diff_pct(expected: float, actual: float) -> float:
    denominator = max(abs(expected), abs(actual), 1e-12)
    return abs(actual - expected) / denominator * 100


def _status_from_diff(diff: float, pass_pct: float, warning_pct: float) -> str:
    if diff <= pass_pct:
        return "pass"
    if diff <= warning_pct:
        return "warning"
    return "fail"


def _severity_from_status(status: str, fail_severity: str = "error") -> str:
    if status == "pass":
        return "info"
    if status == "warning":
        return "warning"
    if status == "fail":
        return fail_severity
    return "info"


def _check(
    check_id: str,
    module_key: str,
    *,
    status: str,
    severity: str,
    field: str | None = None,
    expected: Any = None,
    actual: Any = None,
    relative_diff_pct: float | None = None,
    tolerance_pct: float | None = None,
    evidence: list[Any] | None = None,
    recommended_fix: list[str] | None = None,
    check_strength: str = "strong",
    tags: list[str] | None = None,
) -> Check:
    if check_strength in {"weak", "informational"} and status == "fail":
        status = "warning"
        severity = "warning" if check_strength == "weak" else "info"
    return {
        "check_id": check_id,
        "module_key": module_key,
        "check_strength": check_strength,
        "severity": severity,
        "status": status,
        "field": field,
        "expected": expected,
        "actual": actual,
        "relative_diff_pct": None if relative_diff_pct is None else round(relative_diff_pct, 4),
        "tolerance_pct": tolerance_pct,
        "tags": tags or [],
        "evidence": evidence or [],
        "recommended_fix": recommended_fix or [],
    }


def _infer_report_period_type(period: Any) -> str:
    text = str(period or "")
    if text.endswith("12-31"):
        return "annual"
    if text:
        return "quarterly"
    return "unknown"


def _field_formula_context(module: dict[str, Any], module_key: str, field: str) -> dict[str, Any]:
    item = _field_item(module, field)
    row = _rows(module)[0] if _rows(module) else {}
    context = item.get("formula_context") if isinstance(item.get("formula_context"), dict) else {}
    period = context.get("period") or row.get("period") or row.get("stat_date")
    raw_field = context.get("raw_field") or item.get("raw_field")
    unit = context.get("unit") or item.get("unit") or item.get("display_type") or "unknown"
    percent_scale = context.get("percent_scale") or item.get("percent_scale") or "unknown"
    provider_definition = context.get("provider_definition")
    if not provider_definition and isinstance(raw_field, str) and raw_field.startswith("dupont_"):
        provider_definition = "dupont_provider_defined"
    return {
        "period": period,
        "report_period_type": context.get("report_period_type") or row.get("report_period_type") or _infer_report_period_type(period),
        "value_basis": context.get("value_basis") or row.get("value_basis") or "unknown",
        "unit": unit,
        "percent_scale": percent_scale,
        "provider_definition": provider_definition or context.get("provider_definition") or "unknown",
        "source_module": context.get("source_module") or module_key,
        "source_provider": context.get("source_provider") or item.get("provider") or row.get("source") or "unknown",
        "raw_field": raw_field,
        "normalized_field": field,
        "publish_date": context.get("publish_date") or row.get("publish_date") or row.get("pub_date"),
    }


def _contexts_same_period(contexts: list[dict[str, Any]]) -> bool:
    periods = {ctx.get("period") for ctx in contexts if ctx.get("period")}
    return len(periods) <= 1


def _contexts_known_same_basis(contexts: list[dict[str, Any]]) -> bool:
    bases = {ctx.get("value_basis") for ctx in contexts}
    return len(bases) == 1 and "unknown" not in bases


def _formula_strength_from_contexts(contexts: list[dict[str, Any]], *, allow_provider_defined: bool = False) -> tuple[str, list[str], str | None]:
    if not _contexts_same_period(contexts):
        return "skipped", ["PERIOD_MISMATCH"], "period mismatch"
    bases = {ctx.get("value_basis") for ctx in contexts}
    if len(bases - {"unknown"}) > 1:
        return "skipped", ["CUMULATIVE_VS_SINGLE_PERIOD_MISMATCH"], "value basis mismatch"
    if any(ctx.get("provider_definition") == "dupont_provider_defined" for ctx in contexts):
        tags = ["DUPONT_PROVIDER_DEFINED", "ACCOUNTING_DEFINITION_DIFFERENCE"] if allow_provider_defined else ["PROVIDER_ACCOUNTING_DEFINITION_DIFFERENT"]
        return "weak", tags, None
    if not _contexts_known_same_basis(contexts):
        return "weak", ["FORMULA_CONTEXT_MISSING"], None
    source_modules = {ctx.get("source_module") for ctx in contexts}
    if len(source_modules) > 1:
        return "weak", ["CROSS_MODULE_MIXED_SOURCE"], None
    return "strong", [], None


def _extract_share_capital(data: dict[str, Any], field: str) -> float | None:
    for module_key in ("quote_overview", "valuation", "profitability"):
        value = _num(_field_value(_module(data, module_key), field))
        if value is not None:
            return value
    raw_names = {
        "total_share": ("total_share", "totalShare"),
        "float_share": ("float_share", "liqa_share", "liqaShare"),
    }[field]
    for module in (data.get("modules") or {}).values():
        raw = module.get("raw") if isinstance(module, dict) else None
        if not isinstance(raw, dict):
            continue
        for provider_items in raw.values():
            items = provider_items if isinstance(provider_items, list) else [provider_items]
            for item in items:
                if not isinstance(item, dict):
                    continue
                for raw_key in ("raw_full", "raw_sample"):
                    for raw_item in item.get(raw_key) or []:
                        if isinstance(raw_item, dict):
                            profit_rows = raw_item.get("profit") if isinstance(raw_item.get("profit"), list) else [raw_item]
                            for row in profit_rows:
                                if not isinstance(row, dict):
                                    continue
                                for name in raw_names:
                                    value = _num(row.get(name))
                                    if value is not None:
                                        return value
    return None


def _price_for_market_cap(data: dict[str, Any]) -> tuple[float | None, str | None]:
    quote = _module(data, "quote_overview")
    row = _rows(quote)[0] if _rows(quote) else {}
    if row.get("price_is_realtime") is False:
        price = _num(_field_value(quote, "recent_close"))
        if price is not None:
            return price, "recent_close"
    price = _num(_field_value(quote, "latest_price"))
    if price is not None:
        return price, "latest_price"
    price = _num(_field_value(quote, "recent_close"))
    return (price, "recent_close") if price is not None else (None, None)


def _market_cap_checks(data: dict[str, Any]) -> list[Check]:
    checks: list[Check] = []
    price, price_field = _price_for_market_cap(data)
    for module_key in ("quote_overview", "valuation"):
        module = _module(data, module_key)
        for field, share_field in (("market_cap", "total_share"), ("float_market_cap", "float_share")):
            actual = _num(_field_value(module, field))
            share = _extract_share_capital(data, share_field)
            check_id = f"{field}_formula"
            if price is None or share is None or actual is None:
                checks.append(_check(
                    check_id, module_key, status="skipped", severity="info", field=field,
                    evidence=[{"price_field": price_field, "price": price, share_field: share, "actual": actual}],
                    recommended_fix=["surface source fields in field_trace when formula validation is skipped"],
                ))
                continue
            expected = price * share
            diff = _relative_diff_pct(expected, actual)
            status = _status_from_diff(diff, 1.0, 5.0)
            checks.append(_check(
                check_id, module_key, status=status, severity=_severity_from_status(status),
                field=field, expected=expected, actual=actual, relative_diff_pct=diff,
                tolerance_pct=1.0,
                evidence=[{"price_field": price_field, "price": price, share_field: share}],
                recommended_fix=[] if status == "pass" else ["verify share capital source and price date alignment"],
            ))
    market_cap = _num(_field_value(_module(data, "quote_overview"), "market_cap"))
    float_market_cap = _num(_field_value(_module(data, "quote_overview"), "float_market_cap"))
    if market_cap is None or float_market_cap is None:
        checks.append(_check("float_market_cap_lte_market_cap", "quote_overview", status="skipped", severity="info", field="float_market_cap"))
    else:
        ratio = (float_market_cap - market_cap) / max(abs(market_cap), 1e-12) * 100
        status = "pass" if float_market_cap <= market_cap else ("warning" if ratio <= 5 else "fail")
        checks.append(_check(
            "float_market_cap_lte_market_cap", "quote_overview", status=status,
            severity=_severity_from_status(status), field="float_market_cap",
            expected=f"<= {market_cap}", actual=float_market_cap,
            relative_diff_pct=max(0.0, ratio), tolerance_pct=0.0,
            recommended_fix=[] if status == "pass" else ["check float share and total share mapping"],
        ))
    return checks


def _ratio_formula_check(
    check_id: str,
    module_key: str,
    target_field: str,
    numerator_field: str,
    denominator_field: str,
    data: dict[str, Any],
    *,
    pass_pct: float,
    warning_pct: float,
    fail_severity: str = "error",
    force_strength: str | None = None,
) -> Check:
    module = _module(data, module_key)
    target = _num(_field_value(module, target_field))
    numerator = _num(_field_value(module, numerator_field))
    denominator = _num(_field_value(module, denominator_field))
    contexts = [
        _field_formula_context(module, module_key, target_field),
        _field_formula_context(module, module_key, numerator_field),
        _field_formula_context(module, module_key, denominator_field),
    ]
    strength, tags, skip_reason = _formula_strength_from_contexts(contexts)
    if force_strength:
        strength = force_strength
    if target is None or numerator is None or denominator in (None, 0):
        tags = tags or ["FORMULA_CONTEXT_MISSING"]
        return _check(
            check_id, module_key, status="skipped", severity="info", field=target_field,
            evidence=[{"formula_context": contexts}],
            check_strength="informational", tags=tags,
            recommended_fix=["align period and value_basis before validating net_margin"],
        )
    if skip_reason:
        return _check(
            check_id, module_key, status="skipped", severity="info", field=target_field,
            evidence=[{"formula_context": contexts, "reason": skip_reason}],
            check_strength="informational", tags=tags,
            recommended_fix=["align period and value_basis before validating net_margin"],
        )
    expected = numerator / denominator
    diff = _relative_diff_pct(expected, target)
    status = _status_from_diff(diff, pass_pct, warning_pct)
    severity = _severity_from_status(status, fail_severity)
    if strength == "weak" and status == "fail":
        status = "warning"
        severity = "warning"
    if strength == "weak" and "FORMULA_CONTEXT_MISSING" not in tags:
        tags.append("FORMULA_CONTEXT_MISSING")
    return _check(
        check_id, module_key, status=status, severity=severity,
        field=target_field, expected=expected, actual=target, relative_diff_pct=diff, tolerance_pct=pass_pct,
        evidence=[{
            numerator_field: numerator,
            denominator_field: denominator,
            "formula_context": contexts,
        }],
        check_strength=strength,
        tags=tags,
        recommended_fix=[] if status == "pass" else [
            "align period and value_basis before validating net_margin",
            "inspect BaoStock field definition",
            "avoid cross-module strong formula check",
        ],
    )


def _dupont_check(data: dict[str, Any]) -> Check:
    module = _module(data, "dupont")
    roe = _num(_field_value(module, "roe"))
    net_margin = _num(_field_value(module, "net_margin"))
    asset_turnover = _num(_field_value(module, "asset_turnover"))
    equity_multiplier = _num(_field_value(module, "equity_multiplier"))
    contexts = [
        _field_formula_context(module, "dupont", "roe"),
        _field_formula_context(module, "dupont", "net_margin"),
        _field_formula_context(module, "dupont", "asset_turnover"),
        _field_formula_context(module, "dupont", "equity_multiplier"),
    ]
    strength, tags, skip_reason = _formula_strength_from_contexts(contexts, allow_provider_defined=True)
    if strength == "weak":
        tags = list(dict.fromkeys([*tags, "DUPONT_FORMULA_WEAK_CHECK"]))
    if None in (roe, net_margin, asset_turnover, equity_multiplier):
        return _check(
            "dupont_roe_formula", "dupont", status="skipped", severity="info", field="roe",
            evidence=[{"formula_context": contexts}],
            check_strength="informational",
            tags=tags or ["FORMULA_CONTEXT_MISSING"],
        )
    if skip_reason:
        return _check(
            "dupont_roe_formula", "dupont", status="skipped", severity="info", field="roe",
            evidence=[{"formula_context": contexts, "reason": skip_reason}],
            check_strength="informational",
            tags=tags,
            recommended_fix=["compare provider definitions for Dupont components"],
        )
    expected = net_margin * asset_turnover * equity_multiplier
    diff = _relative_diff_pct(expected, roe)
    status = _status_from_diff(diff, 5.0, 15.0)
    severity = _severity_from_status(status)
    if status == "fail":
        tags = list(dict.fromkeys([*tags, "DUPONT_FORMULA_MISMATCH"]))
    return _check(
        "dupont_roe_formula", "dupont", status=status, severity=severity,
        field="roe", expected=expected, actual=roe, relative_diff_pct=diff, tolerance_pct=5.0,
        evidence=[{
            "roe": roe,
            "net_margin": net_margin,
            "asset_turnover": asset_turnover,
            "equity_multiplier": equity_multiplier,
            "computed_roe": expected,
            "formula_context": contexts,
        }],
        check_strength=strength,
        tags=tags,
        recommended_fix=[] if status == "pass" else ["do not render Dupont decomposition chart until period and formula semantics are aligned"],
    )


def _valuation_checks(data: dict[str, Any]) -> list[Check]:
    module = _module(data, "valuation") or _module(data, "quote_overview")
    checks: list[Check] = []
    thresholds = {
        "pe_ttm": (300, "NEGATIVE_OR_INVALID_PE"),
        "pb": (50, "NON_POSITIVE_PB"),
        "ps_ttm": (100, "NEGATIVE_PS"),
    }
    for field, (upper, negative_tag) in thresholds.items():
        value = _num(_field_value(module, field))
        if value is None:
            checks.append(_check(f"{field}_sanity", "valuation", status="skipped", severity="info", field=field))
        elif value <= 0:
            checks.append(_check(f"{field}_sanity", "valuation", status="warning", severity="warning", field=field, actual=value, evidence=[negative_tag]))
        elif value > upper:
            checks.append(_check(f"{field}_sanity", "valuation", status="warning", severity="warning", field=field, actual=value, evidence=["EXTREME_VALUATION_MULTIPLE"]))
        else:
            checks.append(_check(f"{field}_sanity", "valuation", status="pass", severity="info", field=field, actual=value))
    pcf = _num(_field_value(module, "pcf_ncf_ttm"))
    if pcf is None:
        checks.append(_check("pcf_ncf_ttm_sanity", "valuation", status="skipped", severity="info", field="pcf_ncf_ttm"))
    elif pcf < 0:
        checks.append(_check("pcf_ncf_ttm_sanity", "valuation", status="warning", severity="info", field="pcf_ncf_ttm", actual=pcf, evidence=["CASHFLOW_VALUATION_NEGATIVE"]))
    else:
        checks.append(_check("pcf_ncf_ttm_sanity", "valuation", status="pass", severity="info", field="pcf_ncf_ttm", actual=pcf))
    return checks


def _solvency_checks(data: dict[str, Any]) -> list[Check]:
    module = _module(data, "solvency")
    current = _num(_field_value(module, "current_ratio"))
    quick = _num(_field_value(module, "quick_ratio"))
    cash = _num(_field_value(module, "cash_ratio"))
    debt = _num(_field_value(module, "debt_ratio"))
    equity_multiplier = _num(_field_value(module, "equity_multiplier"))
    checks: list[Check] = []
    if current is None or quick is None:
        checks.append(_check("current_ratio_gte_quick_ratio", "solvency", status="skipped", severity="info"))
    else:
        status = "pass" if current >= quick else "warning"
        checks.append(_check("current_ratio_gte_quick_ratio", "solvency", status=status, severity=_severity_from_status(status), expected=f">= {quick}", actual=current))
    if quick is None or cash is None:
        checks.append(_check("quick_ratio_gte_cash_ratio", "solvency", status="skipped", severity="info"))
    else:
        status = "pass" if quick >= cash else "warning"
        checks.append(_check("quick_ratio_gte_cash_ratio", "solvency", status=status, severity=_severity_from_status(status), expected=f">= {cash}", actual=quick))
    if debt is None:
        checks.append(_check("debt_ratio_range", "solvency", status="skipped", severity="info", field="debt_ratio"))
    else:
        status = "pass" if 0 <= debt <= 1.5 else "warning"
        checks.append(_check("debt_ratio_range", "solvency", status=status, severity=_severity_from_status(status), field="debt_ratio", actual=debt))
    if equity_multiplier is None:
        checks.append(_check("equity_multiplier_range", "solvency", status="skipped", severity="info", field="equity_multiplier"))
    else:
        status = "pass" if equity_multiplier >= 1 else "warning"
        checks.append(_check("equity_multiplier_range", "solvency", status=status, severity=_severity_from_status(status), field="equity_multiplier", actual=equity_multiplier))
    if debt is None or equity_multiplier is None or debt >= 1:
        checks.append(_check("equity_multiplier_debt_ratio_formula", "solvency", status="skipped", severity="info"))
    else:
        expected = 1 / (1 - debt)
        diff = _relative_diff_pct(expected, equity_multiplier)
        status = "pass" if diff <= 15 else "warning"
        checks.append(_check("equity_multiplier_debt_ratio_formula", "solvency", status=status, severity=_severity_from_status(status), expected=expected, actual=equity_multiplier, relative_diff_pct=diff, tolerance_pct=15.0))
    return checks


def _operation_checks(data: dict[str, Any]) -> list[Check]:
    module = _module(data, "operation_capability")
    checks: list[Check] = []
    for field in ("inventory_turnover", "receivable_turnover", "asset_turnover"):
        value = _num(_field_value(module, field))
        if value is None:
            checks.append(_check(f"{field}_sanity", "operation_capability", status="skipped", severity="info", field=field))
        elif value < 0:
            checks.append(_check(f"{field}_sanity", "operation_capability", status="warning", severity="warning", field=field, actual=value))
        elif field == "receivable_turnover" and value > 1000:
            checks.append(_check(f"{field}_sanity", "operation_capability", status="warning", severity="info", field=field, actual=value, evidence=["POSSIBLE_ACCOUNTING_STRUCTURE"]))
        else:
            checks.append(_check(f"{field}_sanity", "operation_capability", status="pass", severity="info", field=field, actual=value))
    return checks


def _cashflow_checks(data: dict[str, Any]) -> list[Check]:
    module = _module(data, "cashflow_quality")
    profit = _module(data, "profitability")
    checks: list[Check] = []
    ocf_to_np = _num(_field_value(module, "ocf_to_np"))
    ocf_to_revenue = _num(_field_value(module, "ocf_to_revenue")) or _num(_field_value(module, "cashflow_revenue_ratio"))
    net_profit = _num(_field_value(profit, "net_profit"))
    if ocf_to_np is None:
        checks.append(_check("ocf_to_np_sanity", "cashflow_quality", status="skipped", severity="info", field="ocf_to_np"))
    elif ocf_to_np > 5 or ocf_to_np < -5 or (net_profit is not None and net_profit > 0 and ocf_to_np < 0):
        checks.append(_check(
            "ocf_to_np_sanity",
            "cashflow_quality",
            status="warning",
            severity="warning",
            field="ocf_to_np",
            actual=ocf_to_np,
            evidence=[{
                "warning": "由于净利润基数较小，该比例波动较大",
                "denominator_available": net_profit is not None,
                "net_profit": net_profit,
            }],
            tags=["CFO_TO_NP_DENOMINATOR_SENSITIVE"],
        ))
    else:
        checks.append(_check("ocf_to_np_sanity", "cashflow_quality", status="pass", severity="info", field="ocf_to_np", actual=ocf_to_np))
    if ocf_to_revenue is None:
        checks.append(_check("ocf_to_revenue_sanity", "cashflow_quality", status="skipped", severity="info", field="ocf_to_revenue"))
    elif ocf_to_revenue < -1 or ocf_to_revenue > 2:
        checks.append(_check("ocf_to_revenue_sanity", "cashflow_quality", status="warning", severity="warning", field="ocf_to_revenue", actual=ocf_to_revenue))
    else:
        checks.append(_check("ocf_to_revenue_sanity", "cashflow_quality", status="pass", severity="info", field="ocf_to_revenue", actual=ocf_to_revenue))
    return checks


def _provider_conflict_checks(data: dict[str, Any]) -> list[Check]:
    checks: list[Check] = []
    for field in ("latest_price", "recent_close", "pe_ttm", "pb", "ps_ttm"):
        values: list[tuple[str, float]] = []
        for module in (data.get("modules") or {}).values():
            raw = module.get("raw") if isinstance(module, dict) else None
            if not isinstance(raw, dict):
                continue
            for provider, provider_items in raw.items():
                items = provider_items if isinstance(provider_items, list) else [provider_items]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    for raw_key in ("raw_sample", "raw_full"):
                        samples = item.get(raw_key) or []
                        for sample in samples:
                            if not isinstance(sample, dict):
                                continue
                            candidates = {
                                field,
                                "close" if field in ("latest_price", "recent_close") else field,
                                "change_pct" if field == "pct_chg" else field,
                                "pcf_ttm" if field == "pcf_ncf_ttm" else field,
                            }
                            for candidate in candidates:
                                value = _num(sample.get(candidate))
                                if value is not None:
                                    values.append((provider, value))
                                    break
        unique_by_provider: dict[str, float] = {}
        for provider, value in values:
            unique_by_provider.setdefault(provider, value)
        pairs = list(combinations(unique_by_provider.items(), 2))
        if not pairs:
            checks.append(_check(f"{field}_provider_conflict", "provider_conflict", status="skipped", severity="info", field=field))
            continue
        worst: Check | None = None
        for (provider_a, value_a), (provider_b, value_b) in pairs:
            diff = _relative_diff_pct(value_a, value_b)
            status = "pass" if diff <= 1 else ("warning" if diff <= 5 else "fail")
            check = _check(
                f"{field}_provider_conflict", "provider_conflict", status=status,
                severity=_severity_from_status(status), field=field, expected=value_a, actual=value_b,
                relative_diff_pct=diff, tolerance_pct=1.0,
                evidence=[{"provider_a": provider_a, "provider_b": provider_b, "value_a": value_a, "value_b": value_b}],
                recommended_fix=[] if status == "pass" else ["compare provider timestamps and field definitions"],
            )
            if worst is None or {"fail": 3, "warning": 2, "pass": 1}[check["status"]] > {"fail": 3, "warning": 2, "pass": 1}[worst["status"]]:
                worst = check
        checks.append(worst or _check(f"{field}_provider_conflict", "provider_conflict", status="skipped", severity="info", field=field))
    return checks


def _summary(checks: list[Check]) -> dict[str, Any]:
    checks_total = len(checks)
    warning_count = sum(1 for check in checks if check["status"] == "warning")
    failed = [check for check in checks if check["status"] == "fail"]
    critical_failures = sum(1 for check in failed if check["severity"] == "critical")
    strong_failures = sum(1 for check in failed if check.get("check_strength", "strong") == "strong")
    error_failures = sum(
        1
        for check in failed
        if check["severity"] in ("error", "critical") and check.get("check_strength", "strong") == "strong"
    )
    weak_warning_count = sum(1 for check in checks if check.get("check_strength") == "weak" and check["status"] == "warning")
    semantic_warning_count = sum(
        1
        for check in checks
        if check["status"] == "warning" and any(tag in SEMANTIC_WARNING_TAGS for tag in check.get("tags", []))
    )
    skipped_due_to_context_count = sum(
        1
        for check in checks
        if check["status"] == "skipped" and any(tag in SEMANTIC_WARNING_TAGS for tag in check.get("tags", []))
    )
    formula_context_missing_count = sum(1 for check in checks if "FORMULA_CONTEXT_MISSING" in check.get("tags", []))
    score = 100
    for check in checks:
        if check["status"] == "fail" and check["severity"] == "critical":
            score -= 25
        elif check["status"] == "fail" and check["severity"] == "error":
            score -= 15
        elif check["status"] == "warning" and check.get("check_strength") == "weak":
            score -= 3
        elif check["status"] == "warning":
            score -= 5
        elif check["severity"] == "info" and check["status"] == "fail":
            score -= 1
    status = "fail" if critical_failures or error_failures else ("warning" if warning_count else "pass")
    return {
        "status": status,
        "data_quality_score": max(0, round(score, 2)),
        "checks_total": checks_total,
        "checks_passed": sum(1 for check in checks if check["status"] == "pass"),
        "checks_warning": warning_count,
        "checks_failed": len(failed),
        "checks_skipped": sum(1 for check in checks if check["status"] == "skipped"),
        "critical_failures": critical_failures,
        "strong_failed_count": strong_failures,
        "weak_warning_count": weak_warning_count,
        "semantic_warning_count": semantic_warning_count,
        "skipped_due_to_context_count": skipped_due_to_context_count,
        "formula_context_missing_count": formula_context_missing_count,
    }


def validate_company_v2_envelope(
    envelope: CompanyV2DebugEnvelope | dict[str, Any],
    *,
    max_validation_checks: int | None = None,
) -> dict[str, Any]:
    data = _payload(envelope)
    checks: list[Check] = []
    checks.extend(_market_cap_checks(data))
    checks.append(_dupont_check(data))
    checks.append(_ratio_formula_check("net_margin_formula", "profitability", "net_margin", "net_profit", "revenue", data, pass_pct=3.0, warning_pct=10.0))
    checks.append(_ratio_formula_check("gross_margin_formula", "profitability", "gross_margin", "gross_profit", "revenue", data, pass_pct=3.0, warning_pct=10.0, fail_severity="warning"))
    checks.extend(_valuation_checks(data))
    checks.extend(_solvency_checks(data))
    checks.extend(_operation_checks(data))
    checks.extend(_cashflow_checks(data))
    checks.extend(_provider_conflict_checks(data))
    summary = _summary(checks)
    visible_checks = checks[:max_validation_checks] if max_validation_checks else checks
    return {"validation_summary": summary, "validation_checks": visible_checks}
