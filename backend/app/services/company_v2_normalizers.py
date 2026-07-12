from __future__ import annotations

from typing import Any

from app.services.company_v2_financial_field_definition_registry import (
    build_field_definition_match,
    get_provider_field_definition,
)


def _get(row: dict[str, Any], *names: str) -> tuple[Any, str | None]:
    lower = {str(k).lower(): k for k in row.keys()}
    for name in names:
        if name in row:
            return row.get(name), name
        key = lower.get(name.lower())
        if key is not None:
            return row.get(key), key
    return None, None


def _set(out: dict[str, Any], source_map: dict[str, str], field: str, row: dict[str, Any], *names: str) -> None:
    value, source = _get(row, *names)
    if value is None or value == "":
        return
    out[field] = value
    if source:
        source_map[field] = source
        out[f"{field}_source"] = "baostock_aggregate"
        metadata = get_provider_field_definition(source)
        out[f"{field}_provider_definition"] = metadata["provider_definition"]
        out[f"{field}_matched_label"] = metadata["matched_label"]
        out[f"{field}_value_basis"] = metadata["value_basis"]
        out[f"{field}_field_definition_match"] = build_field_definition_match(field, {
            "provider_definition": metadata["provider_definition"],
            "matched_label": metadata["matched_label"],
            "structured_field_name": source,
        }).get("match_type", "unknown")


def _with_meta(row: dict[str, Any], source_map: dict[str, str]) -> dict[str, Any]:
    row["source"] = "baostock_aggregate"
    row["source_field_map"] = source_map
    return row


def normalize_baostock_table(module_key: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        out: dict[str, Any] = {}
        source_map: dict[str, str] = {}
        _set(out, source_map, "period", raw, "statDate", "stat_date")
        _set(out, source_map, "stat_date", raw, "statDate", "stat_date")
        _set(out, source_map, "publish_date", raw, "pubDate", "pub_date")

        if module_key == "profitability":
            _set(out, source_map, "roe", raw, "roeAvg", "roe_avg")
            _set(out, source_map, "net_margin", raw, "npMargin", "net_margin")
            _set(out, source_map, "gross_margin", raw, "gpMargin", "gross_margin")
            _set(out, source_map, "net_profit", raw, "netProfit", "net_profit")
            _set(out, source_map, "eps_ttm", raw, "epsTTM", "eps_ttm")
            _set(out, source_map, "revenue", raw, "MBRevenue", "mb_revenue")
            _set(out, source_map, "total_share", raw, "totalShare", "total_share")
            _set(out, source_map, "float_share", raw, "liqaShare", "liqa_share")
        elif module_key == "growth":
            _set(out, source_map, "equity_yoy", raw, "YOYEquity", "yoy_equity")
            _set(out, source_map, "asset_yoy", raw, "YOYAsset", "yoy_asset")
            _set(out, source_map, "net_profit_yoy", raw, "YOYNI", "yoy_ni")
            _set(out, source_map, "eps_yoy", raw, "YOYEPSBasic", "yoy_eps")
            _set(out, source_map, "parent_net_profit_yoy", raw, "YOYPNI", "yoy_pni")
            # Phase 6T-E 修复：YOYEquity 是净资产同比，不得标注为 revenue_yoy（营收同比）；
            # YOYEPSBasic 是每股收益同比，不得标注为 eps_basic（基本每股收益）。
            # BaoStock growth 表无营收同比字段，不伪造。
        elif module_key == "cashflow_quality":
            _set(out, source_map, "current_assets_to_assets", raw, "CAToAsset", "ca_to_asset")
            _set(out, source_map, "non_current_assets_to_assets", raw, "NCAToAsset", "nca_to_asset")
            _set(out, source_map, "tangible_assets_to_assets", raw, "tangibleAssetToAsset", "tangible_to_asset")
            _set(out, source_map, "ebitda_to_liability", raw, "ebITDAToLiability", "ebit_to_interest")
            _set(out, source_map, "ocf_to_revenue", raw, "CFOToOR", "cfo_to_or")
            _set(out, source_map, "ocf_to_np", raw, "CFOToNP", "cfo_to_np")
            _set(out, source_map, "ocf_to_growth", raw, "CFOToGr", "cfo_to_gr")
            _set(out, source_map, "cashflow_revenue_ratio", raw, "CFOToGr", "cfo_to_gr")
        elif module_key == "solvency":
            _set(out, source_map, "current_ratio", raw, "currentRatio", "current_ratio")
            _set(out, source_map, "quick_ratio", raw, "quickRatio", "quick_ratio")
            _set(out, source_map, "cash_ratio", raw, "cashRatio", "cash_ratio")
            _set(out, source_map, "liability_yoy", raw, "YOYLiability", "yoy_liability")
            _set(out, source_map, "debt_ratio", raw, "liabilityToAsset", "liability_to_asset")
            _set(out, source_map, "equity_multiplier", raw, "assetToEquity", "asset_to_equity")
        elif module_key == "operation_capability":
            _set(out, source_map, "receivable_turnover", raw, "NRTurnRatio", "nr_turn_ratio")
            _set(out, source_map, "receivable_turnover_days", raw, "NRTurnDays", "nr_turn_days")
            _set(out, source_map, "inventory_turnover", raw, "INVTurnRatio", "inv_turn_ratio")
            _set(out, source_map, "inventory_turnover_days", raw, "INVTurnDays", "inv_turn_days")
            _set(out, source_map, "current_asset_turnover", raw, "CATurnRatio", "ca_turn_ratio")
            _set(out, source_map, "asset_turnover", raw, "AssetTurnRatio", "asset_turn_ratio")
            _set(out, source_map, "total_asset_turnover", raw, "AssetTurnRatio", "asset_turn_ratio")
        elif module_key == "dupont":
            _set(out, source_map, "roe", raw, "dupontROE", "dupont_roe")
            _set(out, source_map, "equity_multiplier", raw, "dupontAssetStoEquity", "dupont_am")
            _set(out, source_map, "asset_turnover", raw, "dupontAssetTurn", "dupont_at")
            _set(out, source_map, "net_margin", raw, "dupontPnitoni", "dupont_npi")
            _set(out, source_map, "net_income_to_gross_revenue", raw, "dupontNitogr", "dupont_nitogr")
            _set(out, source_map, "tax_burden", raw, "dupontTaxBurden", "dupont_tax")
            _set(out, source_map, "interest_burden", raw, "dupontIntburden", "dupont_int")
            _set(out, source_map, "ebit_to_gross_revenue", raw, "dupontEbittogr", "dupont_ebittogr")
        if source_map:
            normalized.append(_with_meta(out, source_map))
    return normalized


def normalize_baostock_aggregate(module_key: str, aggregate: dict[str, Any]) -> list[dict[str, Any]]:
    table_key = {
        "profitability": "profit",
        "growth": "growth",
        "cashflow_quality": "cash_flow",
        "solvency": "balance",
        "operation_capability": "operation",
        "dupont": "dupont",
    }.get(module_key)
    if not table_key:
        return []
    rows = aggregate.get(table_key) or []
    return normalize_baostock_table(module_key, rows if isinstance(rows, list) else [])
