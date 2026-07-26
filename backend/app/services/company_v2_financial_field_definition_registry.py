"""Financial field definition registry for CompanyV2 verification semantics."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FinancialFieldDefinition:
    key: str
    canonical_name: str
    aliases: tuple[str, ...]
    incompatible_definitions: tuple[str, ...] = ()
    requires_period_basis: bool = False
    display_name: str | None = None
    definition_text: str | None = None
    expected_unit: str | None = None
    value_basis: str = "unknown"
    comparable_with: tuple[str, ...] = ()
    incompatible_with: tuple[str, ...] = ()
    industry_applicability: tuple[str, ...] = ("all",)
    official_report_labels: tuple[str, ...] = ()
    provider_labels: tuple[str, ...] = ()


FIELD_DEFINITIONS: dict[str, FinancialFieldDefinition] = {
    "revenue": FinancialFieldDefinition(
        key="revenue",
        canonical_name="营业收入",
        aliases=("operating revenue",),
        incompatible_definitions=("营业总收入", "total_operating_revenue", "主营业务收入", "main_business_revenue"),
        display_name="营业收入",
        definition_text="企业在经营活动中形成的收入，不等同于主营业务收入。",
        expected_unit="CNY",
        value_basis="annual_cumulative",
        comparable_with=("total_operating_revenue",),
        incompatible_with=("main_business_revenue",),
        official_report_labels=("营业收入", "营业总收入"),
        provider_labels=("revenue", "MBRevenue", "mb_revenue"),
    ),
    "total_operating_revenue": FinancialFieldDefinition(
        key="total_operating_revenue",
        canonical_name="营业总收入",
        aliases=("total operating revenue",),
        incompatible_definitions=("营业收入", "operating revenue", "主营业务收入", "main_business_revenue"),
        display_name="营业总收入",
        definition_text="营业收入总额口径。",
        expected_unit="CNY",
        value_basis="annual_cumulative",
        comparable_with=("revenue",),
        official_report_labels=("营业总收入",),
    ),
    "main_business_revenue": FinancialFieldDefinition(
        key="main_business_revenue",
        canonical_name="主营业务收入",
        aliases=("main business revenue",),
        incompatible_definitions=("营业收入", "operating revenue", "营业总收入", "total_operating_revenue"),
        display_name="主营业务收入",
        definition_text="主营业务形成的收入，不等同于营业收入。",
        expected_unit="CNY",
        value_basis="annual_cumulative",
        incompatible_with=("revenue", "total_operating_revenue"),
        official_report_labels=("主营业务收入",),
        provider_labels=("MBRevenue", "mb_revenue"),
    ),
    "net_profit": FinancialFieldDefinition(
        key="net_profit",
        canonical_name="净利润",
        aliases=("net profit",),
        incompatible_definitions=(
            "归属于上市公司股东的净利润",
            "归母净利润",
            "net_profit_parent",
            "扣除非经常性损益后的归属于上市公司股东的净利润",
            "扣非归母净利润",
            "net_profit_parent_excl_nonrecurring",
        ),
        display_name="净利润",
        definition_text="归属于合并口径的净利润，不等同于归属于上市公司股东的净利润。",
        expected_unit="CNY",
        value_basis="annual_cumulative",
        comparable_with=("net_profit_parent", "net_profit_parent_excl_nonrecurring"),
        incompatible_with=("net_profit_parent",),
        official_report_labels=("净利润",),
        provider_labels=("netProfit", "net_profit"),
    ),
    "net_profit_parent": FinancialFieldDefinition(
        key="net_profit_parent",
        canonical_name="归属于上市公司股东的净利润",
        aliases=("归母净利润", "net profit attributable to shareholders of the listed company"),
        incompatible_definitions=("净利润", "net_profit", "含少数股东", "扣非归母净利润", "net_profit_parent_excl_nonrecurring"),
        display_name="归属于上市公司股东的净利润",
        definition_text="归属于上市公司股东的净利润。",
        expected_unit="CNY",
        value_basis="annual_cumulative",
        comparable_with=("net_profit",),
        incompatible_with=("net_profit", "main_business_revenue"),
        official_report_labels=("归属于上市公司股东的净利润", "归属于母公司股东的净利润"),
    ),
    "net_profit_parent_excl_nonrecurring": FinancialFieldDefinition(
        key="net_profit_parent_excl_nonrecurring",
        canonical_name="扣除非经常性损益后的归属于上市公司股东的净利润",
        aliases=("扣非归母净利润",),
        incompatible_definitions=("净利润", "net_profit", "归母净利润", "net_profit_parent"),
        display_name="扣非归母净利润",
        definition_text="扣除非经常性损益后的归属于上市公司股东的净利润。",
        expected_unit="CNY",
        value_basis="annual_cumulative",
        official_report_labels=("扣除非经常性损益后的归属于上市公司股东的净利润",),
    ),
    "operating_cashflow": FinancialFieldDefinition(
        key="operating_cashflow",
        canonical_name="经营活动产生的现金流量净额",
        aliases=("net cash flow from operating activities",),
        display_name="经营活动产生的现金流量净额",
        definition_text="经营活动产生的现金流量净额。",
        expected_unit="CNY",
        value_basis="annual_cumulative",
        official_report_labels=("经营活动产生的现金流量净额", "经营活动现金流量净额"),
    ),
    "total_assets": FinancialFieldDefinition(
        key="total_assets",
        canonical_name="资产总计",
        aliases=("total assets",),
        display_name="总资产",
        definition_text="资产负债表中的资产总计。",
        expected_unit="CNY",
        value_basis="point_in_time",
        official_report_labels=("资产总计", "总资产"),
    ),
    "equity_parent": FinancialFieldDefinition(
        key="equity_parent",
        canonical_name="归属于上市公司股东的净资产",
        aliases=("归母净资产",),
        incompatible_definitions=("所有者权益合计",),
        display_name="归属于上市公司股东的净资产",
        definition_text="归属于上市公司股东的所有者权益，不等同于所有者权益合计。",
        expected_unit="CNY",
        value_basis="point_in_time",
        official_report_labels=("归属于上市公司股东的净资产", "归属于上市公司股东的所有者权益", "归属于母公司股东权益"),
    ),
    "eps_basic": FinancialFieldDefinition(
        key="eps_basic",
        canonical_name="基本每股收益",
        aliases=("basic EPS",),
        display_name="基本每股收益",
        definition_text="归属于普通股股东的基本每股收益。",
        expected_unit="CNY/share",
        value_basis="annual_cumulative",
        official_report_labels=("基本每股收益", "基本每股收益（元／股）"),
    ),
    "roe": FinancialFieldDefinition(
        key="roe",
        canonical_name="净资产收益率",
        aliases=("ROE", "return on equity"),
        incompatible_definitions=("加权平均净资产收益率", "roe_weighted", "摊薄净资产收益率", "roe_diluted"),
        display_name="净资产收益率",
        definition_text="净资产收益率，需与加权平均净资产收益率区分。",
        expected_unit="%",
        value_basis="annual_cumulative",
        comparable_with=("roe_weighted",),
        incompatible_with=("roe_weighted", "roe_diluted"),
        official_report_labels=("净资产收益率",),
        provider_labels=("roe",),
    ),
    "roe_weighted": FinancialFieldDefinition(
        key="roe_weighted",
        canonical_name="加权平均净资产收益率",
        aliases=("weighted average ROE",),
        incompatible_definitions=("净资产收益率", "ROE", "roe", "unknown_roe", "摊薄净资产收益率", "roe_diluted"),
        display_name="加权平均净资产收益率",
        definition_text="加权平均净资产收益率。",
        expected_unit="%",
        value_basis="annual_cumulative",
        comparable_with=("roe",),
        incompatible_with=("roe", "roe_diluted"),
        official_report_labels=("加权平均净资产收益率",),
        provider_labels=("roeAvg", "roe_avg", "roe"),
    ),
    "roe_diluted": FinancialFieldDefinition(
        key="roe_diluted",
        canonical_name="摊薄净资产收益率",
        aliases=("diluted ROE",),
        incompatible_definitions=("加权平均净资产收益率", "roe_weighted", "unknown_roe"),
        display_name="摊薄净资产收益率",
        definition_text="摊薄净资产收益率。",
        expected_unit="%",
        value_basis="annual_cumulative",
        official_report_labels=("摊薄净资产收益率",),
    ),
    "total_share": FinancialFieldDefinition(
        key="total_share",
        canonical_name="总股本",
        aliases=("期末普通股股份总数",),
        incompatible_definitions=("当前股本", "实时股本", "流通股本"),
        requires_period_basis=True,
        display_name="总股本",
        definition_text="报告期末总股本，通常为时点值。",
        expected_unit="shares",
        value_basis="point_in_time",
        official_report_labels=("总股本", "期末普通股股份总数"),
        provider_labels=("totalShare", "total_share"),
    ),
    "float_share": FinancialFieldDefinition(
        key="float_share",
        canonical_name="流通股本",
        aliases=("无限售条件股份",),
        incompatible_definitions=("总股本", "限售股本"),
        requires_period_basis=True,
        display_name="流通股本",
        definition_text="报告期末流通在外股份数量，通常为时点值。",
        expected_unit="shares",
        value_basis="point_in_time",
        official_report_labels=("流通股本", "无限售条件股份"),
        provider_labels=("liqaShare", "liqa_share"),
    ),
}


PROVIDER_FIELD_DEFINITIONS: dict[str, dict[str, str]] = {
    "MBRevenue": {
        "provider_definition": "main_business_revenue",
        "matched_label": "主营业务收入",
        "value_basis": "annual_cumulative",
    },
    "mb_revenue": {
        "provider_definition": "main_business_revenue",
        "matched_label": "主营业务收入",
        "value_basis": "annual_cumulative",
    },
    "netProfit": {
        "provider_definition": "net_profit",
        "matched_label": "净利润",
        "value_basis": "annual_cumulative",
    },
    "net_profit": {
        "provider_definition": "net_profit",
        "matched_label": "净利润",
        "value_basis": "annual_cumulative",
    },
    "roeAvg": {
        "provider_definition": "unknown_roe",
        "matched_label": "roeAvg",
        "value_basis": "annual_cumulative",
    },
    "roe_avg": {
        "provider_definition": "unknown_roe",
        "matched_label": "roeAvg",
        "value_basis": "annual_cumulative",
    },
    "totalShare": {
        "provider_definition": "total_share",
        "matched_label": "总股本",
        "value_basis": "point_in_time",
    },
    "total_share": {
        "provider_definition": "total_share",
        "matched_label": "总股本",
        "value_basis": "point_in_time",
    },
    "liqaShare": {
        "provider_definition": "float_share",
        "matched_label": "流通股本",
        "value_basis": "point_in_time",
    },
    "liqa_share": {
        "provider_definition": "float_share",
        "matched_label": "流通股本",
        "value_basis": "point_in_time",
    },
}


def get_field_definition(field: str) -> FinancialFieldDefinition | None:
    return FIELD_DEFINITIONS.get(field)


def get_provider_field_definition(provider_field_name: str | None) -> dict[str, str]:
    if not provider_field_name:
        return {
            "provider_definition": "unknown",
            "matched_label": "",
            "value_basis": "unknown",
        }
    return PROVIDER_FIELD_DEFINITIONS.get(str(provider_field_name), {
        "provider_definition": "unknown",
        "matched_label": str(provider_field_name),
        "value_basis": "unknown",
    })


def field_definition_keys() -> list[str]:
    return list(FIELD_DEFINITIONS)


def get_field_profile(field: str) -> dict[str, Any]:
    definition = get_field_definition(field)
    if not definition:
        return {
            "key": field,
            "canonical_name": field,
            "display_name": field,
            "expected_unit": None,
            "value_basis": "unknown",
            "official_report_labels": [],
            "provider_labels": [],
            "aliases": [],
            "incompatible_definitions": [],
        }
    return {
        "key": definition.key,
        "canonical_name": definition.canonical_name,
        "display_name": definition.display_name or definition.canonical_name,
        "definition_text": definition.definition_text,
        "expected_unit": definition.expected_unit,
        "value_basis": definition.value_basis,
        "official_report_labels": list(definition.official_report_labels),
        "provider_labels": list(definition.provider_labels),
        "aliases": list(definition.aliases),
        "incompatible_definitions": list(definition.incompatible_definitions),
        "comparable_with": list(definition.comparable_with),
        "incompatible_with": list(definition.incompatible_with),
        "industry_applicability": list(definition.industry_applicability),
    }


def _contains_token(text: str, token: str) -> bool:
    if not token:
        return False
    return token.lower() in text.lower()


def build_field_definition_match(field: str, entry: dict[str, Any] | None = None) -> dict[str, Any]:
    definition = get_field_definition(field)
    entry = entry or {}
    if not definition:
        return {
            "status": "unknown",
            "match_type": "unknown",
            "field": field,
            "matched_label": entry.get("matched_label") or "",
            "provider_definition": entry.get("provider_definition") or "unknown",
            "reason": "field definition not registered",
        }

    provider_definition = str(entry.get("provider_definition") or "")
    matched_label = str(entry.get("matched_label") or "")
    text_parts = [
        provider_definition,
        matched_label,
        str(entry.get("official_field_name") or ""),
        str(entry.get("structured_field_name") or ""),
        str(entry.get("reason") or ""),
        str(entry.get("evidence_excerpt") or ""),
    ]
    haystack = " ".join(text_parts)

    incompatible = [
        token for token in definition.incompatible_definitions
        if _contains_token(haystack, token)
    ]
    if incompatible:
        return {
            "status": "definition_mismatch",
            "match_type": "incompatible",
            "field": field,
            "canonical_name": definition.canonical_name,
            "matched_label": matched_label or incompatible[0],
            "provider_definition": provider_definition or "unknown",
            "incompatible_labels": incompatible,
            "reason": "field definition text indicates a different financial concept",
        }

    if provider_definition == field or matched_label == definition.canonical_name:
        return {
            "status": "matched",
            "match_type": "exact",
            "field": field,
            "canonical_name": definition.canonical_name,
            "matched_label": matched_label or definition.canonical_name,
            "provider_definition": provider_definition or field,
        }

    aliases = [
        alias for alias in definition.aliases
        if _contains_token(haystack, alias)
    ]
    if aliases:
        return {
            "status": "matched",
            "match_type": "alias",
            "field": field,
            "canonical_name": definition.canonical_name,
            "matched_label": matched_label or aliases[0],
            "provider_definition": provider_definition or "unknown",
        }

    return {
        "status": "unknown",
        "match_type": "unknown",
        "field": field,
        "canonical_name": definition.canonical_name,
        "matched_label": matched_label,
        "provider_definition": provider_definition or "unknown",
        "reason": "field definition could not be confirmed from available labels",
    }


company_v2_financial_field_definition_registry = FIELD_DEFINITIONS
