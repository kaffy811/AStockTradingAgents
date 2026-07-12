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

# accounting_type → {field: reason}
# 未列出的字段默认 applicable=True
_NOT_APPLICABLE_RULES: dict[str, dict[str, str]] = {
    "general_industrial": {},
    "utility": {},
    "real_estate": {},
    "unknown": {},
    "bank": {
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
    },
    "insurer": {
        "inventory_turnover": "NOT_APPLICABLE_FOR_INSURER",
        "current_ratio": "NOT_APPLICABLE_FOR_INSURER",
        "quick_ratio": "NOT_APPLICABLE_FOR_INSURER",
        "cash_ratio": "NOT_APPLICABLE_FOR_INSURER",
        "receivable_turnover": "NOT_APPLICABLE_FOR_INSURER",
        "ocf_to_np": "LIMITED_MEANING_FOR_INSURER",
        "ocf_to_revenue": "LIMITED_MEANING_FOR_INSURER",
    },
    "securities": {
        "inventory_turnover": "NOT_APPLICABLE_FOR_SECURITIES",
        "current_ratio": "NOT_APPLICABLE_FOR_SECURITIES",
        "quick_ratio": "NOT_APPLICABLE_FOR_SECURITIES",
        "cash_ratio": "NOT_APPLICABLE_FOR_SECURITIES",
        "receivable_turnover": "NOT_APPLICABLE_FOR_SECURITIES",
    },
}

# 需要谨慎解读（保留展示但加提示）的字段
_CAUTION_RULES: dict[str, dict[str, str]] = {
    "bank": {
        "equity_multiplier": "HIGH_LEVERAGE_IS_NORMAL_FOR_BANK",
        "debt_ratio": "HIGH_DEBT_RATIO_IS_NORMAL_FOR_BANK",
    },
    "insurer": {
        "equity_multiplier": "DUPONT_CAUTION_FOR_INSURER",
        "debt_ratio": "HIGH_DEBT_RATIO_IS_NORMAL_FOR_INSURER",
    },
}

# BaoStock 行业名称关键词 → accounting_type 推断
_INDUSTRY_KEYWORD_MAP: list[tuple[str, str]] = [
    ("银行", "bank"),
    ("保险", "insurer"),
    ("证券", "securities"),
    ("房地产", "real_estate"),
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


def check_field_applicability(field: str, accounting_type: str) -> dict[str, Any]:
    """
    单字段适用性判定。

    Returns:
        {"field", "applicable", "reason", "display_value", "caution"(optional)}
    """
    rules = _NOT_APPLICABLE_RULES.get(accounting_type, {})
    reason = rules.get(field)
    if reason:
        return {
            "field": field,
            "applicable": False,
            "reason": reason,
            "display_value": "N/A",
        }
    caution = _CAUTION_RULES.get(accounting_type, {}).get(field)
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
    field_results = {f: check_field_applicability(f, accounting_type) for f in fields}
    not_applicable = [f for f, r in field_results.items() if not r["applicable"]]
    return {
        "accounting_type": accounting_type,
        "module_key": module_key,
        "fields": field_results,
        "not_applicable_fields": not_applicable,
        "module_applicable": len(not_applicable) < len(fields) or not fields,
    }
