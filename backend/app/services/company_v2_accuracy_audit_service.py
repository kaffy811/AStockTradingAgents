"""
app/services/company_v2_accuracy_audit_service.py — CompanyV2 数据准确性审计（Phase 6T-A）

对 CompanyV2 DebugEnvelope 中的字段按来源分级：

1. official_disclosure_verified  — 与 CNINFO 年报 PDF 字段核验一致
2. official_disclosure_conflict  — 与 CNINFO 年报 PDF 字段冲突
3. official_disclosure_found_but_unparsed — 找到 PDF 但尚未解析/核验
4. public_provider_verified      — 来自公开源，未与 PDF 核验
5. computed_from_verified_source — 由 official verified 字段计算
6. computed_from_public_provider — 由公开源字段计算
7. unverified                    — 缺少可靠来源或抽取失败

安全原则：
- 不把 BaoStock/AkShare 标为 official_disclosure_verified
- 当前无 CNINFO 年报核验前，只能标 public_provider_verified / computed_from_public_provider
- 不生成投资建议
- 不编造准确性评级
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

# ── 字段来源分级规则 ────────────────────────────────────────────────────────────

# 公开数据源标识（provider 名称 → 可靠性分类）
_PUBLIC_PROVIDERS = {
    "baostock": "public_provider",
    "baostock_aggregate": "public_provider",
    "akshare": "optional_public_adapter",
    "akshare_spot_em": "optional_public_adapter",
    "eastmoney": "optional_public_adapter",
    "tencent": "optional_public_adapter",
    "sina": "optional_public_adapter",
    "computed": "derived",
}

# 官方披露来源
_OFFICIAL_PROVIDERS = {
    "cninfo": "official_disclosure",
    "sse": "official_disclosure",
    "szse": "official_disclosure",
    "pdf_metrics": "official_disclosure",
}

# 已知的 computed 字段（通过公式推算）
_COMPUTED_FIELDS = {
    "market_cap",
    "float_market_cap",
}

# 已知的 derived 字段（从公开数据推算，不直接等于原始披露值）
_DERIVED_FIELDS = {
    "price_is_realtime",
    "price_label",
    "price_data_status",
    "price_source",
    "price_label_source",
    "price_as_of",
}

# 行情类字段（公开源可验证，但非年报核验）
_QUOTE_FIELDS = {
    "latest_price", "recent_close", "open", "high", "low",
    "volume", "amount", "pct_chg", "turnover",
    "pe_ttm", "pb", "ps_ttm", "pcf_ncf_ttm",
}

# 财务类字段（年报核验后升级为 official_disclosure_verified）
_FINANCIAL_FIELDS = {
    "revenue", "net_profit_parent", "gross_margin", "net_margin",
    "roe", "roa", "roic", "revenue_yoy", "net_profit_yoy",
    "eps_basic", "operating_cashflow", "ocf_to_np", "ocf_to_revenue",
    "cashflow_revenue_ratio", "current_ratio", "quick_ratio", "cash_ratio",
    "debt_ratio", "equity_multiplier", "asset_turnover", "inventory_turnover",
    "receivable_turnover", "total_asset_turnover",
    "net_margin_pct", "gross_margin_pct", "roe_pct", "roa_pct", "roic_pct",
}

# 冲突阈值（相对差异 > 5% 视为 conflict）
_CONFLICT_THRESHOLD = 0.05


def _classify_field_source(
    field: str,
    item: dict[str, Any],
    has_official_pdf: bool,
) -> str:
    """返回单字段的来源分类。"""
    if item.get("computed", False):
        if field in _COMPUTED_FIELDS:
            return "computed_from_public_provider"
        return "computed_from_public_provider"

    provider = item.get("provider") or item.get("source") or ""
    provider_lower = str(provider).lower()

    # 官方披露来源
    for official_key in _OFFICIAL_PROVIDERS:
        if official_key in provider_lower:
            if has_official_pdf and field in _FINANCIAL_FIELDS:
                return "official_disclosure_verified"
            return "public_provider_verified"  # 有来源但未通过 PDF 核验

    # 公开数据源
    for pub_key in _PUBLIC_PROVIDERS:
        if pub_key in provider_lower:
            if field in _COMPUTED_FIELDS:
                return "computed_from_public_provider"
            return "public_provider_verified"

    # 无法识别来源
    if not provider or provider in ("", "unknown", "provider"):
        return "unverified"

    return "public_provider_verified"


def _detect_conflicts(
    fields: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """检测多源同字段冲突。当前为单源环境，预留扩展接口。"""
    # TODO: 当接入多源聚合后，在此对比相同字段的不同来源值
    return []


def audit_envelope(
    envelope: dict[str, Any],
    *,
    has_official_pdf: bool = False,
    official_verification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    对单个 CompanyV2 DebugEnvelope 做准确性审计。

    Parameters:
        envelope: CompanyV2DebugEnvelope.model_dump() 格式的 dict
        has_official_pdf: 是否已接入经确认的 CNINFO 年报 PDF（升级部分字段）

    Returns:
        accuracy_audit dict
    """
    module_key = envelope.get("module_key", "unknown")
    normalized = envelope.get("normalized") or {}
    fields: dict[str, dict] = normalized.get("fields") or {}

    verified_fields: list[str] = []
    unverified_fields: list[str] = []
    computed_fields_list: list[str] = []
    official_fields: list[str] = []
    notes: list[str] = []

    field_verdicts: dict[str, str] = {}
    verification_fields = (official_verification or envelope.get("official_verification") or {}).get("fields") or {}

    for field, item in fields.items():
        if not isinstance(item, dict):
            continue
        verification_entry = verification_fields.get(field)
        provider_lower = str(item.get("provider") or item.get("source") or "").lower()
        is_official_provider = any(official_key in provider_lower for official_key in _OFFICIAL_PROVIDERS)
        if isinstance(verification_entry, dict) and verification_entry.get("status") == "verified":
            classification = "official_disclosure_verified"
        elif isinstance(verification_entry, dict) and verification_entry.get("status") == "conflict":
            classification = "official_disclosure_conflict"
        elif has_official_pdf and is_official_provider and field in _FINANCIAL_FIELDS:
            classification = "official_disclosure_verified"
        elif has_official_pdf and field in _FINANCIAL_FIELDS and not official_verification:
            classification = "official_disclosure_found_but_unparsed"
        else:
            classification = _classify_field_source(field, item, has_official_pdf)
        field_verdicts[field] = classification

        if classification == "official_disclosure_verified":
            official_fields.append(field)
            verified_fields.append(field)
        elif classification == "official_disclosure_conflict":
            unverified_fields.append(field)
        elif classification == "official_disclosure_found_but_unparsed":
            unverified_fields.append(field)
        elif classification == "public_provider_verified":
            verified_fields.append(field)
        elif classification == "computed_from_public_provider":
            computed_fields_list.append(field)
        else:
            unverified_fields.append(field)

    # 特殊字段说明
    if "market_cap" in field_verdicts or "float_market_cap" in field_verdicts:
        notes.append(
            "market_cap / float_market_cap 为推算值（最近收盘价 × 股本），"
            "非实时交易所行情，标记为 computed_from_public_provider。"
        )

    price_fields_present = {f for f in _QUOTE_FIELDS if f in field_verdicts}
    if price_fields_present:
        notes.append(
            f"行情字段（{', '.join(sorted(price_fields_present))}）"
            "来自公开数据源聚合，可能存在延迟，标记为 public_provider_verified。"
        )

    if not has_official_pdf and any(f in _FINANCIAL_FIELDS for f in verified_fields):
        notes.append(
            "财务指标字段当前来源为公开数据源，尚未通过 CNINFO 年报 PDF 核验。"
            "接入年报 PDF 后部分字段将升级为 official_disclosure_verified。"
        )

    conflicts = _detect_conflicts(fields)
    for field, entry in verification_fields.items():
        if isinstance(entry, dict) and entry.get("status") == "conflict":
            conflicts.append({"field": field, "source": "cninfo_pdf", "status": "official_disclosure_conflict"})

    # 综合状态
    if official_fields:
        status = "partially_verified"
    elif not fields:
        status = "unverified"
    elif unverified_fields and len(unverified_fields) >= len(verified_fields):
        status = "unverified"
    elif conflicts:
        status = "conflict"
    elif verified_fields:
        status = "partially_verified"
    else:
        status = "unverified"

    return {
        "module_key": module_key,
        "status": status,
        "source_reliability": {
            "baostock": "public_provider",
            "akshare": "optional_public_adapter",
            "cninfo": "official_disclosure",
            "computed": "derived",
        },
        "verified_fields": sorted(set(verified_fields)),
        "official_disclosure_fields": sorted(set(official_fields)),
        "unverified_fields": sorted(set(unverified_fields)),
        "computed_fields": sorted(set(computed_fields_list)),
        "source_conflicts": conflicts,
        "field_verdicts": field_verdicts,
        "notes": notes,
        "has_official_pdf": has_official_pdf,
        "official_verification_status": (official_verification or {}).get("status"),
        "disclaimer": (
            "当前数据来自公开数据源聚合与计算，最终以交易所/巨潮资讯披露文件为准。"
            "数据质量状态仅反映字段一致性，不代表真实性完全确认。"
        ),
    }


def audit_full_debug(
    debug_data: dict[str, Any],
    *,
    has_official_pdf: bool = False,
) -> dict[str, Any]:
    """
    对 CompanyV2 FullDebug 结果（包含多个模块）做全局准确性审计。

    Parameters:
        debug_data: /api/v2/company/{market}/{symbol}/debug/full 的响应
        has_official_pdf: 是否已接入 CNINFO 年报 PDF
    """
    modules = debug_data.get("modules") or {}
    module_audits: dict[str, dict] = {}
    all_verified: list[str] = []
    all_unverified: list[str] = []
    all_computed: list[str] = []
    all_official: list[str] = []

    for module_key, envelope in modules.items():
        if not isinstance(envelope, dict):
            continue
        audit = audit_envelope(envelope, has_official_pdf=has_official_pdf)
        module_audits[module_key] = audit
        all_verified.extend(audit["verified_fields"])
        all_unverified.extend(audit["unverified_fields"])
        all_computed.extend(audit["computed_fields"])
        all_official.extend(audit["official_disclosure_fields"])

    overall_status: str
    if all_official:
        overall_status = "partially_verified"
    elif not all_verified and not all_computed:
        overall_status = "unverified"
    elif all_unverified:
        overall_status = "partially_verified"
    else:
        overall_status = "partially_verified"  # no full verification without PDF

    return {
        "status": overall_status,
        "has_official_pdf": has_official_pdf,
        "source_reliability": {
            "baostock": "public_provider",
            "akshare": "optional_public_adapter",
            "cninfo": "official_disclosure",
            "computed": "derived",
        },
        "verified_fields": sorted(set(all_verified)),
        "official_disclosure_fields": sorted(set(all_official)),
        "unverified_fields": sorted(set(all_unverified)),
        "computed_fields": sorted(set(all_computed)),
        "source_conflicts": [],
        "module_audits": module_audits,
        "notes": [
            "当前数据来自公开数据源聚合与计算，最终以交易所/巨潮资讯披露文件为准。",
            "Data Quality 状态仅判断字段一致性，不代表真实性完全确认。",
            "price_label=最近收盘价 时，数据为 BaoStock 历史 K 线回退，非实时行情。",
            "market_cap / float_market_cap 为推算值，标记为 computed_from_public_provider。",
        ],
        "disclaimer": (
            "数据来源：公开数据源聚合、CNINFO 公告文件及系统计算。"
            "行情可能存在延迟，财务数据最终以交易所及巨潮资讯披露文件为准。"
            "本页面不构成投资建议。"
        ),
    }


# 单例
company_v2_accuracy_audit_service = audit_full_debug
