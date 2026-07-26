"""Provider + endpoint + field registry for financial metric provenance.

The registry is intentionally keyed by provider, endpoint, and source field.
Different providers may use the same field name with different semantics, so
Company V2 and Chat must not rely on field-name-only unit inference.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ProviderFieldDefinition:
    provider: str
    endpoint: str
    field: str
    canonical_metric: str
    raw_unit: str
    normalized_unit: str
    value_type: str
    period_semantics: str
    accounting_scope: str
    normalization_rule: str
    cumulative: bool | None = None

    def payload(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "endpoint": self.endpoint,
            "field": self.field,
            "canonical_metric": self.canonical_metric,
            "raw_unit": self.raw_unit,
            "normalized_unit": self.normalized_unit,
            "value_type": self.value_type,
            "period_semantics": self.period_semantics,
            "accounting_scope": self.accounting_scope,
            "normalization_rule": self.normalization_rule,
            "is_cumulative": self.cumulative,
            "schema_version": "financial_metric_v1",
        }


def _d(
    endpoint: str,
    field: str,
    canonical_metric: str,
    raw_unit: str,
    normalized_unit: str,
    value_type: str,
    period_semantics: str,
    accounting_scope: str = "consolidated",
    normalization_rule: str = "identity",
    cumulative: bool | None = None,
) -> ProviderFieldDefinition:
    return ProviderFieldDefinition(
        provider="baostock",
        endpoint=endpoint,
        field=field,
        canonical_metric=canonical_metric,
        raw_unit=raw_unit,
        normalized_unit=normalized_unit,
        value_type=value_type,
        period_semantics=period_semantics,
        accounting_scope=accounting_scope,
        normalization_rule=normalization_rule,
        cumulative=cumulative,
    )


PROVIDER_FIELD_REGISTRY: dict[tuple[str, str, str], ProviderFieldDefinition] = {
    ("baostock", "query_profit_data", "mb_revenue"): _d("query_profit_data", "mb_revenue", "revenue", "CNY", "CNY", "flow", "report_period_cumulative", cumulative=True),
    ("baostock", "query_profit_data", "net_profit"): _d("query_profit_data", "net_profit", "net_profit", "CNY", "CNY", "flow", "report_period_cumulative", cumulative=True),
    ("baostock", "query_profit_data", "roe_avg"): _d("query_profit_data", "roe_avg", "roe", "ratio", "percent", "ratio", "report_period", normalization_rule="percentage_fraction x 100"),
    ("baostock", "query_profit_data", "gross_margin"): _d("query_profit_data", "gross_margin", "gross_margin", "ratio", "percent", "ratio", "report_period", normalization_rule="percentage_fraction x 100"),
    ("baostock", "query_profit_data", "net_margin"): _d("query_profit_data", "net_margin", "net_margin", "ratio", "percent", "ratio", "report_period", normalization_rule="percentage_fraction x 100"),
    ("baostock", "query_profit_data", "eps_ttm"): _d("query_profit_data", "eps_ttm", "eps", "CNY/share", "CNY/share", "per_share", "ttm"),
    ("baostock", "query_profit_data", "total_share"): _d("query_profit_data", "total_share", "total_share", "shares", "shares", "count", "point_in_time"),
    ("baostock", "query_profit_data", "liqa_share"): _d("query_profit_data", "liqa_share", "float_share", "shares", "shares", "count", "point_in_time"),
    ("baostock", "query_growth_data", "yoy_ni"): _d("query_growth_data", "yoy_ni", "net_profit_yoy", "ratio", "percent", "ratio", "report_period", normalization_rule="percentage_fraction x 100"),
    ("baostock", "query_growth_data", "yoy_pni"): _d("query_growth_data", "yoy_pni", "parent_net_profit_yoy", "ratio", "percent", "ratio", "report_period", accounting_scope="parent", normalization_rule="percentage_fraction x 100"),
    ("baostock", "query_growth_data", "yoy_eps"): _d("query_growth_data", "yoy_eps", "eps_yoy", "ratio", "percent", "ratio", "report_period", normalization_rule="percentage_fraction x 100"),
    ("baostock", "query_growth_data", "yoy_equity"): _d("query_growth_data", "yoy_equity", "equity_yoy", "ratio", "percent", "ratio", "report_period", normalization_rule="percentage_fraction x 100"),
    ("baostock", "query_growth_data", "yoy_asset"): _d("query_growth_data", "yoy_asset", "asset_yoy", "ratio", "percent", "ratio", "report_period", normalization_rule="percentage_fraction x 100"),
    ("baostock", "query_balance_data", "current_ratio"): _d("query_balance_data", "current_ratio", "current_ratio", "ratio", "ratio", "ratio", "point_in_time"),
    ("baostock", "query_balance_data", "quick_ratio"): _d("query_balance_data", "quick_ratio", "quick_ratio", "ratio", "ratio", "ratio", "point_in_time"),
    ("baostock", "query_balance_data", "cash_ratio"): _d("query_balance_data", "cash_ratio", "cash_ratio", "ratio", "ratio", "ratio", "point_in_time"),
    ("baostock", "query_balance_data", "liability_to_asset"): _d("query_balance_data", "liability_to_asset", "debt_ratio", "ratio", "percent", "ratio", "point_in_time", normalization_rule="percentage_fraction x 100"),
    ("baostock", "query_balance_data", "asset_to_equity"): _d("query_balance_data", "asset_to_equity", "equity_multiplier", "multiple", "multiple", "ratio", "point_in_time"),
    ("baostock", "query_operation_data", "asset_turn_ratio"): _d("query_operation_data", "asset_turn_ratio", "asset_turnover", "ratio", "ratio", "ratio", "report_period"),
    ("baostock", "query_operation_data", "inv_turn_ratio"): _d("query_operation_data", "inv_turn_ratio", "inventory_turnover", "ratio", "ratio", "ratio", "report_period"),
    ("baostock", "query_operation_data", "nr_turn_ratio"): _d("query_operation_data", "nr_turn_ratio", "receivable_turnover", "ratio", "ratio", "ratio", "report_period"),
    ("baostock", "query_cash_flow_data", "cfo_to_np"): _d("query_cash_flow_data", "cfo_to_np", "ocf_to_np", "ratio", "percent", "ratio", "report_period", normalization_rule="percentage_fraction x 100"),
    ("baostock", "query_cash_flow_data", "cfo_to_gr"): _d("query_cash_flow_data", "cfo_to_gr", "ocf_to_revenue", "ratio", "percent", "ratio", "report_period", normalization_rule="percentage_fraction x 100"),
    ("baostock", "query_cash_flow_data", "cfo_to_or"): _d("query_cash_flow_data", "cfo_to_or", "cashflow_revenue_ratio", "ratio", "percent", "ratio", "report_period", normalization_rule="percentage_fraction x 100"),
    ("baostock", "query_dupont_data", "dupont_roe"): _d("query_dupont_data", "dupont_roe", "roe", "ratio", "percent", "ratio", "report_period", normalization_rule="percentage_fraction x 100"),
    ("baostock", "query_dupont_data", "dupont_npi"): _d("query_dupont_data", "dupont_npi", "dupont_net_profit_factor", "ratio", "ratio", "ratio", "report_period"),
    ("baostock", "query_dupont_data", "dupont_nitogr"): _d("query_dupont_data", "dupont_nitogr", "dupont_income_margin", "ratio", "percent", "ratio", "report_period", normalization_rule="percentage_fraction x 100"),
    ("baostock", "query_dupont_data", "dupont_at"): _d("query_dupont_data", "dupont_at", "asset_turnover", "ratio", "ratio", "ratio", "report_period"),
    ("baostock", "query_dupont_data", "dupont_am"): _d("query_dupont_data", "dupont_am", "equity_multiplier", "multiple", "multiple", "ratio", "point_in_time"),
}


NORMALIZED_FIELD_TO_PROVIDER_FIELD: dict[tuple[str, str], dict[str, str]] = {
    ("profitability", "revenue"): {"endpoint": "query_profit_data", "field": "mb_revenue"},
    ("profitability", "net_profit"): {"endpoint": "query_profit_data", "field": "net_profit"},
    ("profitability", "net_profit_parent"): {"endpoint": "query_profit_data", "field": "net_profit"},
    ("profitability", "roe"): {"endpoint": "query_profit_data", "field": "roe_avg"},
    ("profitability", "gross_margin"): {"endpoint": "query_profit_data", "field": "gross_margin"},
    ("profitability", "net_margin"): {"endpoint": "query_profit_data", "field": "net_margin"},
    ("profitability", "eps_ttm"): {"endpoint": "query_profit_data", "field": "eps_ttm"},
    ("growth", "main_business_revenue"): {"endpoint": "query_profit_data", "field": "mb_revenue"},
    ("growth", "net_profit"): {"endpoint": "query_profit_data", "field": "net_profit"},
    ("growth", "net_profit_yoy"): {"endpoint": "query_growth_data", "field": "yoy_ni"},
    ("growth", "parent_net_profit_yoy"): {"endpoint": "query_growth_data", "field": "yoy_pni"},
    ("growth", "net_profit_parent_yoy"): {"endpoint": "query_growth_data", "field": "yoy_pni"},
    ("growth", "eps_yoy"): {"endpoint": "query_growth_data", "field": "yoy_eps"},
    ("growth", "equity_yoy"): {"endpoint": "query_growth_data", "field": "yoy_equity"},
    ("growth", "asset_yoy"): {"endpoint": "query_growth_data", "field": "yoy_asset"},
    ("solvency", "current_ratio"): {"endpoint": "query_balance_data", "field": "current_ratio"},
    ("solvency", "quick_ratio"): {"endpoint": "query_balance_data", "field": "quick_ratio"},
    ("solvency", "cash_ratio"): {"endpoint": "query_balance_data", "field": "cash_ratio"},
    ("solvency", "debt_ratio"): {"endpoint": "query_balance_data", "field": "liability_to_asset"},
    ("solvency", "equity_multiplier"): {"endpoint": "query_balance_data", "field": "asset_to_equity"},
    ("operation_capability", "asset_turnover"): {"endpoint": "query_operation_data", "field": "asset_turn_ratio"},
    ("operation_capability", "inventory_turnover"): {"endpoint": "query_operation_data", "field": "inv_turn_ratio"},
    ("operation_capability", "receivable_turnover"): {"endpoint": "query_operation_data", "field": "nr_turn_ratio"},
    ("cashflow_quality", "ocf_to_np"): {"endpoint": "query_cash_flow_data", "field": "cfo_to_np"},
    ("cashflow_quality", "ocf_to_revenue"): {"endpoint": "query_cash_flow_data", "field": "cfo_to_gr"},
    ("cashflow_quality", "cashflow_revenue_ratio"): {"endpoint": "query_cash_flow_data", "field": "cfo_to_or"},
    ("dupont", "roe"): {"endpoint": "query_dupont_data", "field": "dupont_roe"},
    ("dupont", "net_margin"): {"endpoint": "derived", "field": "dupont_npi_x_dupont_nitogr"},
    ("dupont", "asset_turnover"): {"endpoint": "query_dupont_data", "field": "dupont_at"},
    ("dupont", "equity_multiplier"): {"endpoint": "query_dupont_data", "field": "dupont_am"},
    ("dupont", "dupont_net_profit_factor"): {"endpoint": "query_dupont_data", "field": "dupont_npi"},
    ("dupont", "dupont_income_margin"): {"endpoint": "query_dupont_data", "field": "dupont_nitogr"},
    ("dupont", "dupont_npi"): {"endpoint": "query_dupont_data", "field": "dupont_npi"},
    ("dupont", "dupont_nitogr"): {"endpoint": "query_dupont_data", "field": "dupont_nitogr"},
}


def get_provider_field_definition(provider: str, endpoint: str, field: str) -> ProviderFieldDefinition | None:
    return PROVIDER_FIELD_REGISTRY.get((provider, endpoint, field))


def get_normalized_field_definition(module_key: str, normalized_field: str, *, provider: str = "baostock") -> ProviderFieldDefinition | None:
    mapping = NORMALIZED_FIELD_TO_PROVIDER_FIELD.get((module_key, normalized_field))
    if not mapping:
        return None
    endpoint = mapping["endpoint"]
    if endpoint == "derived":
        return None
    return get_provider_field_definition(provider, endpoint, mapping["field"])


def provider_registry_payload() -> list[dict[str, Any]]:
    return [definition.payload() for definition in PROVIDER_FIELD_REGISTRY.values()]
