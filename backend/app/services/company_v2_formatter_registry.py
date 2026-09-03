from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.company_v2_field_metadata import get_field_metadata


PRICE_FIELDS = {"latest_price", "recent_close", "open", "high", "low", "close"}
PERCENT_FIELDS = {
    "pct_chg",
    "turnover",
    "roe",
    "gross_margin",
    "net_margin",
    "revenue_yoy",
    "net_profit_yoy",
    "eps_yoy",
    "ocf_to_np",
    "ocf_to_revenue",
    "cashflow_revenue_ratio",
    "debt_ratio",
    "current_assets_to_assets",
    "non_current_assets_to_assets",
    "parent_net_profit_yoy",
    "net_profit_parent_yoy",
    "dupont_income_margin",
}
ALREADY_PERCENT_FIELDS = {"pct_chg", "turnover"}
RATIO_FIELDS = {
    "pe_ttm",
    "pb",
    "ps_ttm",
    "pcf_ncf_ttm",
    "current_ratio",
    "quick_ratio",
    "cash_ratio",
    "equity_multiplier",
    "asset_turnover",
    "inventory_turnover",
    "receivable_turnover",
    "total_asset_turnover",
    "dupont_net_profit_factor",
    "dupont_asset_turn",
}
MONEY_FIELDS = {
    "market_cap",
    "float_market_cap",
    "amount",
    "revenue",
    "net_profit",
    "net_profit_parent",
    "operating_cashflow",
    "gross_profit",
}
SHARE_FIELDS = {"volume", "total_share", "float_share"}
INTEGER_FIELDS = {"documents_count", "chunks_count", "embedding_count"}


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() in ("", "—", "--", "nan", "NaN", "None", "null"):
        return True
    if isinstance(value, float) and value != value:
        return True
    return False


def _to_decimal(value: Any) -> Decimal | None:
    if _is_empty(value):
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _field_display_type(field_name: str, display_type: str | None) -> str:
    if display_type:
        return display_type
    meta = get_field_metadata(field_name)
    if meta:
        if meta.semantic_type in {"percentage_fraction", "percentage_points"}:
            return "percent"
        if meta.semantic_type == "currency":
            return "money" if field_name not in PRICE_FIELDS else "price"
        if meta.semantic_type in {"ratio", "multiple"}:
            return meta.semantic_type
        if meta.semantic_type == "count":
            return "integer"
    if field_name in PRICE_FIELDS:
        return "price"
    if field_name in PERCENT_FIELDS:
        return "percent"
    if field_name in RATIO_FIELDS:
        return "ratio"
    if field_name in MONEY_FIELDS:
        return "money"
    if field_name in SHARE_FIELDS:
        return "shares"
    if field_name in INTEGER_FIELDS:
        return "integer"
    return "raw"


def _compact_number(number: Decimal, unit_pairs: list[tuple[Decimal, str]], precision: int) -> str:
    abs_number = abs(number)
    for threshold, suffix in unit_pairs:
        if abs_number >= threshold:
            return f"{number / threshold:.{precision}f}{suffix}"
    return f"{number:.{precision}f}"


def format_field(
    field_name: str,
    raw_value: Any,
    display_type: str | None = None,
    unit: str | None = None,
    precision: int | None = None,
    *,
    percent_scale: str | None = None,
) -> dict[str, Any]:
    meta = get_field_metadata(field_name)
    resolved_type = _field_display_type(field_name, display_type)
    resolved_precision = precision if precision is not None else (meta.precision if meta else 2)
    semantic_type = meta.semantic_type if meta else resolved_type
    resolved_unit = unit if unit is not None else (meta.unit if meta else None)
    metadata = {
        "raw_value": raw_value,
        "normalized_value": raw_value,
        "display_value": "—",
        "display_type": resolved_type,
        "semantic_type": semantic_type,
        "unit": resolved_unit,
        "precision": resolved_precision,
    }
    if _is_empty(raw_value):
        return metadata

    number = _to_decimal(raw_value)
    if number is None:
        metadata["display_value"] = str(raw_value)
        metadata["display_type"] = resolved_type if resolved_type != "raw" else "string"
        return metadata

    if resolved_type == "price":
        metadata["unit"] = resolved_unit or "CNY"
        metadata["display_value"] = f"{number:.{resolved_precision}f}"
    elif resolved_type == "percent":
        if percent_scale:
            scale = percent_scale
        elif semantic_type == "percentage_points" or field_name in ALREADY_PERCENT_FIELDS:
            scale = "already_percent"
        else:
            scale = "decimal_to_percent"
        display_number = number if scale == "already_percent" else number * Decimal("100")
        metadata["normalized_value"] = float(display_number)
        metadata["unit"] = resolved_unit or "%"
        metadata["display_value"] = f"{display_number:.{resolved_precision}f}%"
        metadata["percent_scale"] = scale
    elif resolved_type in ("ratio", "multiple", "float"):
        metadata["display_value"] = f"{number:.{resolved_precision}f}"
    elif resolved_type == "money":
        metadata["unit"] = resolved_unit or "CNY"
        metadata["display_value"] = _compact_number(
            number,
            [(Decimal("1000000000000"), "万亿"), (Decimal("100000000"), "亿"), (Decimal("10000"), "万")],
            resolved_precision,
        )
    elif resolved_type == "shares":
        metadata["unit"] = resolved_unit or "股"
        metadata["display_value"] = _compact_number(
            number,
            [(Decimal("100000000"), "亿股"), (Decimal("10000"), "万股")],
            resolved_precision,
        )
    elif resolved_type == "integer":
        metadata["display_value"] = f"{number:.0f}"
    elif resolved_type == "days":
        metadata["unit"] = resolved_unit or "天"
        metadata["display_value"] = f"{number:.{resolved_precision}f}天"
    elif resolved_type == "boolean":
        metadata["display_value"] = "是" if bool(raw_value) else "否"
    else:
        metadata["display_value"] = str(raw_value)
    return metadata
