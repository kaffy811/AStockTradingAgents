"""Extract core official disclosure fields from CNINFO annual report text.

Phase 6T-J2: table-level unit context. Monetary units are resolved with an
explicit precedence (inline > table-level declaration in scope > unknown) and
NEVER guessed from value magnitude or defaulted to 元. Unknown units are
surfaced as unit_source="unknown" so fusion can refuse value_conflict.
"""
from __future__ import annotations

import re
from typing import Any

# Bumped whenever unit detection/normalization semantics change; participates
# in the fusion cache key so stale pre-fix results can never be reused.
OFFICIAL_EXTRACTOR_VERSION = "official-extractor-unit-context-v2"

AMOUNT_UNITS = {
    "元": 1.0,
    "千元": 1e3,
    "万元": 1e4,
    "百万元": 1e6,
    "亿元": 1e8,
}

# Longest-first alternation so 百万元/千元 are not shadowed by 万元/元.
_AMOUNT_UNIT_ALT = "亿元|百万元|万元|千元|元"
# Table/inline unit declaration, e.g. 单位：千元 / 单位: 人民币万元
_UNIT_DECL_RE = re.compile(rf"单位[：:\s]*(?:人民币)?\s*({_AMOUNT_UNIT_ALT})")

FIELD_SEMANTICS: dict[str, dict[str, Any]] = {
    "revenue": {
        "official_field_name": "营业收入",
        "english_name": "Operating revenue / Revenue",
        "official_table": "合并利润表 / 主要会计数据",
        "standard_aliases": ["营业收入", "Operating revenue", "Revenue"],
        "fallback_aliases": ["营业总收入", "一、营业收入"],
        "not_same_as": ["主营业务收入"],
    },
    "net_profit_parent": {
        "official_field_name": "归属于母公司股东的净利润",
        "english_name": "Net profit attributable to shareholders of the parent company",
        "official_table": "合并利润表 / 主要会计数据",
        "standard_aliases": [
            "归属于母公司股东的净利润",
            "归属于上市公司股东的净利润",
            "归属于母公司所有者的净利润",
            "Net profit attributable to shareholders of the parent company",
            "Net profit attributable to owners of the parent",
        ],
        "forbidden_aliases": ["净利润", "total net profit"],
    },
    "net_profit": {
        "official_field_name": "净利润",
        "english_name": "Net profit",
        "official_table": "合并利润表",
        "standard_aliases": ["净利润", "Net profit"],
        "not_same_as": ["归属于上市公司股东的净利润", "扣除非经常性损益的净利润"],
    },
    "operating_cashflow": {
        "official_field_name": "经营活动产生的现金流量净额",
        "english_name": "Net cash flows from operating activities",
        "official_table": "合并现金流量表 / 主要会计数据",
        "standard_aliases": [
            "经营活动产生的现金流量净额",
            "经营活动现金流量净额",
            "Net cash flows from operating activities",
            "Net cash flow from operating activities",
        ],
    },
    "eps_basic": {
        "official_field_name": "基本每股收益",
        "english_name": "Basic earnings per share",
        "official_table": "主要财务指标",
        "standard_aliases": ["基本每股收益", "基本每股收益（元/股）", "Basic earnings per share", "Basic EPS"],
    },
    "roe_weighted": {
        "official_field_name": "加权平均净资产收益率",
        "english_name": "Weighted average return on equity",
        "official_table": "主要财务指标",
        "standard_aliases": ["加权平均净资产收益率"],
    },
    "total_assets": {
        "official_field_name": "总资产",
        "english_name": "Total assets",
        "official_table": "资产负债表 / 主要会计数据",
        "standard_aliases": ["资产总计", "资产总额", "总资产"],
    },
    "equity_parent": {
        "official_field_name": "归属于母公司股东权益",
        "english_name": "Equity attributable to owners of the parent",
        "official_table": "资产负债表 / 主要会计数据",
        "standard_aliases": ["归属于上市公司股东的所有者权益", "归属于母公司股东权益", "归属于上市公司股东的净资产", "归母净资产"],
    },
    "total_share": {
        "official_field_name": "总股本",
        "english_name": "Total share capital",
        "official_table": "股本 / 利润分配说明",
        "standard_aliases": ["总股本"],
    },
    "float_share": {
        "official_field_name": "流通股本",
        "english_name": "Float share capital",
        "official_table": "股本结构",
        "standard_aliases": ["流通股本"],
    },
}

FIELD_ALIASES: dict[str, list[str]] = {
    field: [*meta.get("standard_aliases", []), *meta.get("fallback_aliases", [])]
    for field, meta in FIELD_SEMANTICS.items()
}


FIELD_PATTERNS: dict[str, list[str]] = {
    "revenue": [r"营业(?:总)?收入[：:\s]*([\-0-9,，.]+)\s*(亿元|百万元|万元|千元|元)?"],
    "net_profit_parent": [r"归属于(?:上市公司|母公司)股东的净\s*利润[：:\s]*([\-0-9,，.]+)\s*(亿元|百万元|万元|千元|元)?", r"归母净\s*利润[：:\s]*([\-0-9,，.]+)\s*(亿元|百万元|万元|千元|元)?"],
    "net_profit": [r"净\s*利润[：:\s]*([\-0-9,，.]+)\s*(亿元|百万元|万元|千元|元)?"],
    "operating_cashflow": [r"经营活动(?:产生的)?现金流量净额[：:\s]*([\-0-9,，.]+)\s*(亿元|百万元|万元|千元|元)?"],
    "total_assets": [r"资产总(?:计|额)[：:\s]*([\-0-9,，.]+)\s*(亿元|百万元|万元|千元|元)?", r"总资产[：:\s]*([\-0-9,，.]+)\s*(亿元|百万元|万元|千元|元)?"],
    "equity_parent": [r"归属于(?:上市公司|母公司)股东的(?:所有者)?权益[：:\s]*([\-0-9,，.]+)\s*(亿元|百万元|万元|千元|元)?", r"归母净资产[：:\s]*([\-0-9,，.]+)\s*(亿元|百万元|万元|千元|元)?"],
    "eps_basic": [r"基本每股收益[（(]元[／/]股[）)]?[：:\s]*([\-0-9,，.]+)", r"基本每股收益[：:\s]*([\-0-9,，.]+)\s*元"],
    "roe_weighted": [r"加权平均净资产收益率(?:[（(]\s*%?\s*[）)])?[：:\s]*([\-0-9,，.]+)\s*%?"],
    "total_share": [r"总股本[：:\s]*([\-0-9,，.]+)\s*(亿股|万股|股)?"],
    "float_share": [r"流通股本[：:\s]*([\-0-9,，.]+)\s*(亿股|万股|股)?"],
}


def _alias_regex(alias: str) -> str:
    if re.search(r"[A-Za-z]", alias):
        return re.escape(alias).replace(r"\ ", r"\s+")
    return r"\s*".join(re.escape(ch) for ch in alias if not ch.isspace())


def _field_patterns(field: str) -> list[tuple[str, str]]:
    aliases = FIELD_ALIASES.get(field) or []
    if not aliases:
        return [(pattern, pattern) for pattern in FIELD_PATTERNS.get(field, [])]
    output: list[tuple[str, str]] = []
    for alias in aliases:
        alias_re = _alias_regex(alias)
        if field == "eps_basic":
            pattern = rf"{alias_re}(?:[（(][^）)]*[）)])?[：:\s]*([\-0-9,，.]+)(?:\s*元)?"
        elif field == "roe_weighted":
            pattern = rf"{alias_re}(?:[（(]\s*%?\s*[）)])?[：:\s]*([\-0-9,，.]+)\s*%?"
        elif field in {"total_share", "float_share"}:
            pattern = rf"{alias_re}[：:\s]*([\-0-9,，.]+)\s*(亿股|万股|股)?"
        else:
            pattern = rf"{alias_re}[：:\s]*([\-0-9,，.]+)\s*(亿元|百万元|万元|千元|元)?"
        output.append((alias, pattern))
    output.extend((pattern, pattern) for pattern in FIELD_PATTERNS.get(field, []))
    return output


def _num(raw: str) -> float | None:
    try:
        return float(str(raw).replace(",", "").replace("，", ""))
    except Exception:
        return None


def _scale(unit: str | None, *, field: str) -> tuple[float | None, str | None]:
    """Return (scale, normalized_unit). Monetary unit=None -> (None, None): the
    unit is UNKNOWN and must not be guessed (no default 元)."""
    if field in {"eps_basic"}:
        return 1.0, "CNY/share"
    if field == "roe_weighted":
        return 0.01, "%"
    if field in {"total_share", "float_share"}:
        if unit == "亿股":
            return 1e8, "shares"
        if unit == "万股":
            return 1e4, "shares"
        return 1.0, "shares"
    if unit is None:
        return None, None
    unit = str(unit).replace("人民币", "").strip()
    if unit in AMOUNT_UNITS:
        return AMOUNT_UNITS[unit], "CNY"
    return None, None


def _table_scope_unit(text: str, start: int, field: str) -> dict[str, Any] | None:
    """Resolve the nearest table-level unit declaration in scope.

    Scope rule: only declarations BEFORE the value on the SAME page are
    considered, and the nearest declaration wins — a later 单位： declaration
    starts a new table scope, so earlier ones never leak across tables. No
    cross-page or cross-report inheritance, no magnitude-based guessing.
    """
    if field in {"eps_basic", "roe_weighted", "total_share", "float_share"}:
        return None
    window_start = max(0, start - 800)
    window = text[window_start:start]
    last = None
    for match in _UNIT_DECL_RE.finditer(window):
        last = match
    if not last:
        return None
    decl_pos = window_start + last.start()
    return {
        "unit": last.group(1),
        "unit_source": "table_level",
        "unit_evidence_text": re.sub(r"\s+", " ", last.group(0)).strip()[:40],
        "unit_evidence_offset": decl_pos,
    }


def _excerpt(text: str, start: int, end: int, max_chars: int = 200) -> str:
    left = max(0, start - 70)
    right = min(len(text), end + 130)
    return re.sub(r"\s+", " ", text[left:right]).strip()[:max_chars]


def _column_label(field: str, unit_raw: str | None) -> str | None:
    if field == "eps_basic":
        return "2024年度 / 本期发生额 / 元/股"
    if field == "roe_weighted":
        return "2024年度 / 本期发生额 / %"
    if unit_raw:
        return f"2024年度 / 本期发生额 / {unit_raw}"
    return "2024年度 / 本期发生额"


def _evidence_note(field: str, alias: str, confidence: float) -> str:
    if field == "revenue" and alias == "营业总收入":
        return "matched fallback alias 营业总收入; compare with provider revenue only after confirming revenue definition."
    if confidence < 0.75:
        return "unit or table context is incomplete; treat extraction as low confidence."
    return "matched official annual-report alias."


def extract_official_fields(parsed: dict[str, Any] | list[dict[str, Any]] | str, *, report_id: str | int = "") -> dict[str, Any]:
    if isinstance(parsed, str):
        pages = [{"page": 1, "text": parsed}]
    elif isinstance(parsed, dict):
        pages = parsed.get("text_pages") or []
    else:
        pages = parsed

    official_fields: dict[str, dict[str, Any]] = {}
    for field in FIELD_PATTERNS:
        for page in pages:
            text = page.get("text") or ""
            for alias, pattern in _field_patterns(field):
                match = re.search(pattern, text, flags=re.IGNORECASE)
                if not match:
                    continue
                evidence = _excerpt(text, match.start(), match.end())
                if field == "net_profit" and ("非经常性损益" in evidence or "归属于" in evidence):
                    continue
                if field == "net_profit_parent" and not any(token in evidence for token in ("归属于", "归母", "parent", "Parent", "owners of the parent")):
                    continue
                raw_value = _num(match.group(1))
                if raw_value is None:
                    continue
                # Unit precedence: inline unit next to the value > table-level
                # declaration in scope > unknown. Never default to 元.
                inline_unit = match.group(2) if len(match.groups()) >= 2 else None
                unit_raw = inline_unit
                unit_source = "inline" if inline_unit else None
                unit_evidence_text = inline_unit if inline_unit else None
                unit_evidence_page = page.get("page") if inline_unit else None
                unit_scope: dict[str, Any] | None = None
                if unit_raw is None:
                    unit_scope = _table_scope_unit(text, match.start(), field)
                    if unit_scope:
                        unit_raw = unit_scope["unit"]
                        unit_source = unit_scope["unit_source"]
                        unit_evidence_text = unit_scope["unit_evidence_text"]
                        unit_evidence_page = page.get("page")
                scale, normalized_unit = _scale(unit_raw, field=field)
                if scale is None and field not in {"eps_basic", "roe_weighted", "total_share", "float_share"}:
                    # Monetary unit UNKNOWN: expose raw value only; fusion must
                    # not compare it against CNY structured values.
                    unit_source = "unknown"
                    value = raw_value
                    normalized_unit = None
                    unit_raw = None
                    unit_confidence = 0.0
                else:
                    value = raw_value * (scale if scale is not None else 1.0)
                    unit_confidence = 1.0 if unit_source == "inline" else (0.9 if unit_source == "table_level" else 0.8)
                confidence = 0.85 if (unit_source in {"inline", "table_level"} or field in {"eps_basic", "roe_weighted"}) else 0.55
                semantics = FIELD_SEMANTICS.get(field, {})
                official_fields[field] = {
                    "value": value,
                    "raw_value": raw_value,
                    "unit": normalized_unit,
                    "raw_unit": unit_raw,
                    "unit_scale": scale,
                    "unit_source": unit_source or ("intrinsic" if field in {"eps_basic", "roe_weighted", "total_share", "float_share"} else "unknown"),
                    "unit_confidence": unit_confidence if field not in {"eps_basic", "roe_weighted", "total_share", "float_share"} else 1.0,
                    "unit_evidence_text": unit_evidence_text,
                    "unit_evidence_page": unit_evidence_page,
                    "table_scope_id": (f"p{page.get('page')}#u{unit_scope['unit_evidence_offset']}" if unit_scope else None),
                    "classification_hint": "unit_context_missing" if unit_source == "unknown" else None,
                    "confidence": confidence,
                    "source": "cninfo_pdf",
                    "page": page.get("page"),
                    "evidence_excerpt": evidence,
                    "official_field_name": semantics.get("official_field_name", field),
                    "matched_alias": alias if alias in FIELD_ALIASES.get(field, []) else semantics.get("official_field_name", field),
                    "official_table": semantics.get("official_table"),
                    "official_row_label": alias if alias in FIELD_ALIASES.get(field, []) else semantics.get("official_field_name", field),
                    "official_column_label": _column_label(field, unit_raw),
                    "evidence_note": _evidence_note(field, alias, confidence),
                    "field_semantics": semantics,
                    "verified": True,
                    "report_id": str(report_id),
                }
                break
            if field in official_fields:
                break
        if field not in official_fields:
            official_fields[field] = None
    return {"report_id": str(report_id), "official_fields": official_fields}


company_v2_official_field_extractor = extract_official_fields
