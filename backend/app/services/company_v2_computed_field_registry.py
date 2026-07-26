from __future__ import annotations

from typing import Any


def _empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() in ("", "—", "--", "nan", "NaN"):
        return True
    if isinstance(value, float) and value != value:
        return True
    return False


def _num(value: Any) -> float | None:
    if _empty(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if number != number else number


def compute_company_v2_fields(
    module_key: str,
    fields: dict[str, dict[str, Any]],
    *,
    share_capital_context: dict[str, Any] | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, str], dict[str, str]]:
    computed: dict[str, dict[str, Any]] = {}
    formulas: dict[str, str] = {}
    missing: dict[str, str] = {}

    if module_key not in ("quote_overview", "valuation"):
        return computed, formulas, missing

    price = _num((fields.get("latest_price") or {}).get("value"))
    price_field = "latest_price"
    if price is None:
        price = _num((fields.get("recent_close") or {}).get("value"))
        price_field = "recent_close"

    share_ctx = share_capital_context or {}
    total_share = _num((fields.get("total_share") or {}).get("value")) or _num(share_ctx.get("total_share"))
    float_share = _num((fields.get("float_share") or {}).get("value")) or _num(share_ctx.get("float_share"))
    share_source = share_ctx.get("source") or "share_capital_context"

    if "market_cap" not in fields:
        if price is not None and total_share is not None:
            computed["market_cap"] = {
                "value": price * total_share,
                "source": "computed",
                "provider": share_ctx.get("provider") or "computed",
                "provider_method": share_ctx.get("provider_method"),
                "raw_field": None,
                "computed": True,
                "computed_formula": f"{price_field} * total_share",
                "source_fields": [price_field, "total_share"],
                "fallback_from": share_source,
                "confidence": 0.75,
            }
            formulas["market_cap"] = f"{price_field} * total_share"
        else:
            missing["market_cap"] = "SHARE_CAPITAL_MISSING"

    if "float_market_cap" not in fields:
        if price is not None and float_share is not None:
            computed["float_market_cap"] = {
                "value": price * float_share,
                "source": "computed",
                "provider": share_ctx.get("provider") or "computed",
                "provider_method": share_ctx.get("provider_method"),
                "raw_field": None,
                "computed": True,
                "computed_formula": f"{price_field} * float_share",
                "source_fields": [price_field, "float_share"],
                "fallback_from": share_source,
                "confidence": 0.75,
            }
            formulas["float_market_cap"] = f"{price_field} * float_share"
        else:
            missing["float_market_cap"] = "SHARE_CAPITAL_MISSING"

    if "pct_chg" not in fields:
        latest_price = _num((fields.get("latest_price") or {}).get("value"))
        recent_close = _num((fields.get("recent_close") or {}).get("value"))
        if latest_price is not None and recent_close not in (None, 0):
            computed["pct_chg"] = {
                "value": (latest_price / recent_close - 1) * 100,
                "source": "computed",
                "provider": "computed",
                "computed": True,
                "computed_formula": "(latest_price / recent_close - 1) * 100",
                "source_fields": ["latest_price", "recent_close"],
                "confidence": 0.7,
            }
            formulas["pct_chg"] = "(latest_price / recent_close - 1) * 100"

    return computed, formulas, missing
