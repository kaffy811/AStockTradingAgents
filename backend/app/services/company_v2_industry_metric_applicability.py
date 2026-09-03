"""
app/services/company_v2_industry_metric_applicability.py — Phase 6T-E 金融行业适用性规则

目的：避免银行、保险、证券公司被普通工业企业指标误判。
不适用指标应显示 N/A，而不是 0、缺失错误或"数据异常"。

输出示例：
{
  "field": "inventory_turnover",
  "applicable": false,
  "reason": "NOT_APPLICABLE_FOR_BANK",
  "display_value": "N/A"
}

安全原则：
- 不把不适用指标当作数据错误
- 不把缺失值当 0
- 不提供投资建议
"""
from __future__ import annotations

from typing import Any

# Public profile names used by Company V2 page/product UI.
PROFILE_GENERAL = "general_corporate"
PROFILE_BANK = "bank"
PROFILE_INSURANCE = "insurance"
PROFILE_SECURITIES = "securities"
PROFILE_REAL_ESTATE = "real_estate"

_PROFILE_ALIASES = {
    "general_industrial": PROFILE_GENERAL,
    "general_corporate": PROFILE_GENERAL,
    "unknown": "unknown",
    "utility": "utility",
    "bank": PROFILE_BANK,
    "insurer": PROFILE_INSURANCE,
    "insurance": PROFILE_INSURANCE,
    "securities": PROFILE_SECURITIES,
    "real_estate": PROFILE_REAL_ESTATE,
}

BANK_RECOMMENDED_METRICS: tuple[str, ...] = (
    "roa",
    "roe",
    "net_interest_margin",
    "net_interest_spread",
    "non_performing_loan_ratio",
    "provision_coverage_ratio",
    "loan_provision_ratio",
    "capital_adequacy_ratio",
    "tier1_capital_adequacy_ratio",
    "core_tier1_capital_adequacy_ratio",
    "cost_income_ratio",
    "deposit_balance_yoy",
    "loan_balance_yoy",
    "special_mention_loan_ratio",
    "overdue_loan_ratio",
)

_PROFILE_RECOMMENDED_METRICS: dict[str, tuple[str, ...]] = {
    PROFILE_BANK: BANK_RECOMMENDED_METRICS,
    PROFILE_INSURANCE: (
        "roe",
        "roa",
        "embedded_value",
        "new_business_value",
        "solvency_adequacy_ratio",
        "combined_ratio",
        "premium_income",
    ),
    PROFILE_SECURITIES: (
        "roe",
        "roa",
        "net_capital",
        "risk_coverage_ratio",
        "brokerage_income",
        "investment_income",
    ),
    PROFILE_REAL_ESTATE: (
        "revenue",
        "gross_margin",
        "net_margin",
        "debt_ratio",
        "net_debt_ratio",
        "cash_short_debt_ratio",
        "contract_sales",
    ),
}

# accounting profile → {field: reason}
# 未列出的字段默认 applicable=True
_NOT_APPLICABLE_RULES: dict[str, dict[str, str]] = {
    PROFILE_GENERAL: {},
    "utility": {},
    PROFILE_REAL_ESTATE: {},
    "unknown": {},
    PROFILE_BANK: {
        # 银行无存货概念
        "inventory_turnover": "NOT_APPLICABLE_FOR_BANK",
        # 银行资产负债结构下流动/速动/现金比率不按普通企业含义展示
        "current_ratio": "NOT_APPLICABLE_FOR_BANK",
        "quick_ratio": "NOT_APPLICABLE_FOR_BANK",
        "cash_ratio": "NOT_APPLICABLE_FOR_BANK",
        # 银行经营现金流受吸收存款影响，不适合作为质量核心评价
        "ocf_to_np": "LIMITED_MEANING_FOR_BANK",
        "ocf_to_revenue": "LIMITED_MEANING_FOR_BANK",
        "receivable_turnover": "NOT_APPLICABLE_FOR_BANK",
        # 普通企业毛利率不适合作为银行默认盈利能力指标
        "gross_margin": "NOT_APPLICABLE_FOR_BANK",
    },
    PROFILE_INSURANCE: {
        "inventory_turnover": "NOT_APPLICABLE_FOR_INSURER",
        "current_ratio": "NOT_APPLICABLE_FOR_INSURER",
        "quick_ratio": "NOT_APPLICABLE_FOR_INSURER",
        "cash_ratio": "NOT_APPLICABLE_FOR_INSURER",
        "receivable_turnover": "NOT_APPLICABLE_FOR_INSURER",
        "gross_margin": "NOT_APPLICABLE_FOR_INSURER",
        "ocf_to_np": "LIMITED_MEANING_FOR_INSURER",
        "ocf_to_revenue": "LIMITED_MEANING_FOR_INSURER",
    },
    PROFILE_SECURITIES: {
        "inventory_turnover": "NOT_APPLICABLE_FOR_SECURITIES",
        "current_ratio": "NOT_APPLICABLE_FOR_SECURITIES",
        "quick_ratio": "NOT_APPLICABLE_FOR_SECURITIES",
        "cash_ratio": "NOT_APPLICABLE_FOR_SECURITIES",
        "receivable_turnover": "NOT_APPLICABLE_FOR_SECURITIES",
        "gross_margin": "NOT_APPLICABLE_FOR_SECURITIES",
    },
}

# 需要谨慎解读（保留展示但加提示）的字段
_CAUTION_RULES: dict[str, dict[str, str]] = {
    PROFILE_BANK: {
        "equity_multiplier": "HIGH_LEVERAGE_IS_NORMAL_FOR_BANK",
        "debt_ratio": "HIGH_DEBT_RATIO_IS_NORMAL_FOR_BANK",
    },
    PROFILE_INSURANCE: {
        "equity_multiplier": "DUPONT_CAUTION_FOR_INSURER",
        "debt_ratio": "HIGH_DEBT_RATIO_IS_NORMAL_FOR_INSURER",
    },
}

# BaoStock 行业名称关键词 → accounting_type 推断
_INDUSTRY_KEYWORD_MAP: list[tuple[str, str]] = [
    ("银行", "bank"),
    ("保险", "insurer"),
    ("证券", PROFILE_SECURITIES),
    ("房地产", PROFILE_REAL_ESTATE),
    ("电信", "utility"),
    ("电力", "utility"),
    ("燃气", "utility"),
    ("水务", "utility"),
]


def infer_accounting_type(industry: str | None, symbol: str = "") -> str:
    """
    从行业名称推断特殊会计口径类型；验收样本中已有明确定义时优先。
    """
    from app.services.company_v2_acceptance_universe import get_acceptance_stock
    stock = get_acceptance_stock(symbol) if symbol else None
    if stock:
        return stock.special_accounting_type
    text = str(industry or "")
    for kw, acct_type in _INDUSTRY_KEYWORD_MAP:
        if kw in text:
            return acct_type
    return "general_industrial" if text else "unknown"


def normalize_profile(accounting_type: str | None) -> str:
    return _PROFILE_ALIASES.get(str(accounting_type or "").strip(), str(accounting_type or "").strip() or "unknown")


def get_industry_metric_profile(accounting_type: str | None) -> dict[str, Any]:
    profile = normalize_profile(accounting_type)
    return {
        "profile": profile,
        "recommended_metrics": list(_PROFILE_RECOMMENDED_METRICS.get(profile, ())),
        "not_applicable_rules": dict(_NOT_APPLICABLE_RULES.get(profile, {})),
        "caution_rules": dict(_CAUTION_RULES.get(profile, {})),
    }


def check_field_applicability(field: str, accounting_type: str) -> dict[str, Any]:
    """
    单字段适用性判定。

    Returns:
        {"field", "applicable", "reason", "display_value", "caution"(optional)}
    """
    profile = normalize_profile(accounting_type)
    rules = _NOT_APPLICABLE_RULES.get(profile, {})
    reason = rules.get(field)
    if reason:
        return {
            "field": field,
            "applicable": False,
            "reason": reason,
            "display_value": "N/A",
        }
    caution = _CAUTION_RULES.get(profile, {}).get(field)
    result: dict[str, Any] = {
        "field": field,
        "applicable": True,
        "reason": "",
        "display_value": None,
    }
    if caution:
        result["caution"] = caution
    return result


def build_module_applicability(
    module_key: str,
    fields: list[str],
    accounting_type: str,
) -> dict[str, Any]:
    """
    模块级适用性汇总。

    Returns:
        {
          "accounting_type": str,
          "module_key": str,
          "fields": {field: applicability_dict},
          "not_applicable_fields": [...],
          "module_applicable": bool,   # 全部字段不适用时 False
        }
    """
    profile = normalize_profile(accounting_type)
    field_results = {f: check_field_applicability(f, profile) for f in fields}
    not_applicable = [f for f, r in field_results.items() if not r["applicable"]]
    applicable = [f for f, r in field_results.items() if r["applicable"]]
    return {
        "accounting_type": profile,
        "industry_profile": profile,
        "module_key": module_key,
        "fields": field_results,
        "applicable_fields": applicable,
        "not_applicable_fields": not_applicable,
        "recommended_metrics": list(_PROFILE_RECOMMENDED_METRICS.get(profile, ())),
        "module_status": "not_applicable" if fields and not applicable else "partial",
        "module_applicable": len(not_applicable) < len(fields) or not fields,
    }


def apply_applicability_to_coverage(
    coverage: dict[str, Any],
    applicability: dict[str, Any],
) -> dict[str, Any]:
    """Recompute coverage denominator using only applicable fields."""
    required = list(coverage.get("required_field_list") or [])
    filled = list(coverage.get("filled_field_list") or [])
    missing_map = dict(coverage.get("missing_field_map") or {})
    not_applicable = set(applicability.get("not_applicable_fields") or [])
    applicable_required = [field for field in required if field not in not_applicable]
    applicable_filled = [field for field in filled if field in applicable_required]
    applicable_missing_map = {
        field: reason
        for field, reason in missing_map.items()
        if field in applicable_required
    }
    required_count = len(applicable_required)
    coverage_pct = round(len(applicable_filled) / required_count * 100, 2) if required_count else 100.0
    status = "not_applicable" if required and not required_count else (
        "complete" if coverage_pct == 100 else ("partial" if required_count else "unavailable")
    )
    adjusted = dict(coverage)
    adjusted.update({
        "required_fields": required_count,
        "filled_fields": len(applicable_filled),
        "missing_fields": len(applicable_missing_map),
        "coverage_pct": coverage_pct,
        "required_field_list": applicable_required,
        "filled_field_list": applicable_filled,
        "missing_field_map": applicable_missing_map,
        "not_applicable_fields": sorted(not_applicable),
        "not_applicable_count": len(not_applicable),
        "applicable_coverage_status": status,
    })
    return adjusted
