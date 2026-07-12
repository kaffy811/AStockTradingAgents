from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


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
    resolved_type = _field_display_type(field_name, display_type)
    resolved_precision = 2 if precision is None else precision
    metadata = {
        "raw_value": raw_value,
        "normalized_value": raw_value,
        "display_value": "—",
        "display_type": resolved_type,
        "unit": unit,
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
        metadata["unit"] = unit or "CNY"
        metadata["display_value"] = f"{number:.{resolved_precision}f}"
    elif resolved_type == "percent":
        scale = percent_scale or ("already_percent" if field_name in ALREADY_PERCENT_FIELDS else "decimal_to_percent")
        display_number = number if scale == "already_percent" else number * Decimal("100")
        metadata["unit"] = unit or "%"
        metadata["display_value"] = f"{display_number:.{resolved_precision}f}%"
        metadata["percent_scale"] = scale
    elif resolved_type in ("ratio", "multiple", "float"):
        metadata["display_value"] = f"{number:.{resolved_precision}f}"
    elif resolved_type == "money":
        metadata["unit"] = unit or "CNY"
        metadata["display_value"] = _compact_number(
            number,
            [(Decimal("1000000000000"), "万亿"), (Decimal("100000000"), "亿"), (Decimal("10000"), "万")],
            resolved_precision,
        )
    elif resolved_type == "shares":
        metadata["unit"] = unit or "股"
        metadata["display_value"] = _compact_number(
            number,
            [(Decimal("100000000"), "亿股"), (Decimal("10000"), "万股")],
            resolved_precision,
        )
    elif resolved_type == "integer":
        metadata["display_value"] = f"{number:.0f}"
    elif resolved_type == "days":
        metadata["unit"] = unit or "天"
        metadata["display_value"] = f"{number:.{resolved_precision}f}天"
    elif resolved_type == "boolean":
        metadata["display_value"] = "是" if bool(raw_value) else "否"
    else:
        metadata["display_value"] = str(raw_value)
    return metadata
