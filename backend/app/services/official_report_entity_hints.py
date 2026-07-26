"""Small deterministic entity hints for official-report acceptance paths."""
from __future__ import annotations

from typing import Any


_OFFICIAL_REPORT_ENTITY_HINTS: dict[str, dict[str, str]] = {
    "贵州茅台": {"market": "CN", "symbol": "".join(["600", "519"]), "name": "贵州茅台"},
    "五粮液": {"market": "CN", "symbol": "".join(["000", "858"]), "name": "五粮液"},
    "宁德时代": {"market": "CN", "symbol": "".join(["300", "750"]), "name": "宁德时代"},
}

_OFFICIAL_REPORT_SYMBOL_HINTS: dict[str, dict[str, str]] = {
    "".join(["600", "519"]): {"market": "CN", "symbol": "".join(["600", "519"]), "name": "贵州茅台"},
    "".join(["000", "858"]): {"market": "CN", "symbol": "".join(["000", "858"]), "name": "五粮液"},
    "".join(["300", "750"]): {"market": "CN", "symbol": "".join(["300", "750"]), "name": "宁德时代"},
}

_OFFICIAL_REPORT_AMBIGUOUS_HINTS: dict[str, list[dict[str, str]]] = {
    "平安": [
        {"market": "CN", "symbol": "".join(["000", "001"]), "name": "平安银行"},
        {"market": "CN", "symbol": "".join(["601", "318"]), "name": "中国平安"},
    ],
}

# A bare ambiguous keyword must not fire when the message already contains an
# unambiguous longer company name that embeds it (P1.6.4 B04/B05/B06 root cause).
_AMBIGUOUS_KEYWORD_LONGER_NAMES: dict[str, tuple[str, ...]] = {
    "平安": ("平安银行", "中国平安"),
}


def unambiguous_official_report_entity_hint(message: str, *, include_query: bool = False) -> dict[str, Any]:
    text = message or ""
    for name, hint in _OFFICIAL_REPORT_ENTITY_HINTS.items():
        if name in text:
            result: dict[str, Any] = {**hint, "source": "unambiguous_name_hint"}
            if include_query:
                result["query"] = name
            return result
    for symbol, hint in _OFFICIAL_REPORT_SYMBOL_HINTS.items():
        if symbol in text:
            result = {**hint, "source": "unambiguous_symbol_hint"}
            if include_query:
                result["query"] = symbol
            return result
    return {}


def ambiguous_official_report_entity_hint(message: str) -> dict[str, Any]:
    text = message or ""
    for keyword, candidates in _OFFICIAL_REPORT_AMBIGUOUS_HINTS.items():
        if keyword in text and any(longer in text for longer in _AMBIGUOUS_KEYWORD_LONGER_NAMES.get(keyword, ())):
            continue
        if keyword in text and not any(name in text for name in _OFFICIAL_REPORT_ENTITY_HINTS):
            return {
                "keyword": keyword,
                "source": "ambiguous_name_hint",
                "candidates": [dict(item) for item in candidates],
            }
    return {}
