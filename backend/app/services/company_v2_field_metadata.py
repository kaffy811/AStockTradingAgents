from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class CompanyV2FieldMetadata:
    label: str
    semantic_type: str
    scale: float = 1.0
    precision: int = 2
    source_field: str | None = None
    period_required: bool = True
    formula: str | None = None
    aliases: tuple[str, ...] = field(default_factory=tuple)
    unit: str | None = None


FIELD_METADATA: dict[str, CompanyV2FieldMetadata] = {
    "latest_price": CompanyV2FieldMetadata("最新价", "currency", unit="CNY"),
    "recent_close": CompanyV2FieldMetadata("最近收盘价", "currency", unit="CNY"),
    "pct_chg": CompanyV2FieldMetadata("涨跌幅", "percentage_points", source_field="pctChg", unit="%"),
    "turnover": CompanyV2FieldMetadata("换手率", "percentage_points", source_field="turn", unit="%"),
    "amount": CompanyV2FieldMetadata("成交额", "currency", unit="CNY"),
    "market_cap": CompanyV2FieldMetadata("总市值", "currency", unit="CNY"),
    "float_market_cap": CompanyV2FieldMetadata("流通市值", "currency", unit="CNY"),
    "pe_ttm": CompanyV2FieldMetadata("市盈率 TTM", "multiple", period_required=False),
    "pb": CompanyV2FieldMetadata("市净率", "multiple", period_required=False),
    "ps_ttm": CompanyV2FieldMetadata("市销率 TTM", "multiple", period_required=False),
    "pcf_ncf_ttm": CompanyV2FieldMetadata("市现率 TTM", "multiple", period_required=False),
    "roe": CompanyV2FieldMetadata("净资产收益率", "percentage_fraction", source_field="roeAvg", unit="%"),
    "gross_margin": CompanyV2FieldMetadata("毛利率", "percentage_fraction", source_field="gpMargin", unit="%"),
    "net_margin": CompanyV2FieldMetadata("净利率", "percentage_fraction", source_field="npMargin", unit="%", formula="net_profit / revenue"),
    "revenue": CompanyV2FieldMetadata("营业收入", "currency", source_field="MBRevenue", unit="CNY"),
    "main_business_revenue": CompanyV2FieldMetadata("主营业务收入", "currency", source_field="MBRevenue", unit="CNY"),
    "net_profit": CompanyV2FieldMetadata("净利润", "currency", source_field="netProfit", unit="CNY"),
    "net_profit_parent": CompanyV2FieldMetadata("归母净利润", "currency", source_field="netProfit", unit="CNY"),
    "net_profit_yoy": CompanyV2FieldMetadata("净利润同比", "percentage_fraction", source_field="YOYNI", unit="%"),
    "parent_net_profit_yoy": CompanyV2FieldMetadata("归母净利润同比", "percentage_fraction", source_field="YOYPNI", aliases=("net_profit_parent_yoy",), unit="%"),
    "net_profit_parent_yoy": CompanyV2FieldMetadata("归母净利润同比", "percentage_fraction", source_field="YOYPNI", aliases=("parent_net_profit_yoy",), unit="%"),
    "equity_yoy": CompanyV2FieldMetadata("净资产同比", "percentage_fraction", source_field="YOYEquity", unit="%"),
    "asset_yoy": CompanyV2FieldMetadata("总资产同比", "percentage_fraction", source_field="YOYAsset", unit="%"),
    "eps_yoy": CompanyV2FieldMetadata("每股收益同比", "percentage_fraction", source_field="YOYEPSBasic", unit="%"),
    "ocf_to_np": CompanyV2FieldMetadata("经营现金流/净利润", "percentage_fraction", source_field="CFOToNP", unit="%"),
    "ocf_to_revenue": CompanyV2FieldMetadata("经营现金流/收入", "percentage_fraction", source_field="CFOToGr", aliases=("cashflow_revenue_ratio",), unit="%"),
    "cashflow_revenue_ratio": CompanyV2FieldMetadata("经营现金流/收入", "percentage_fraction", source_field="CFOToOR", aliases=("ocf_to_revenue",), unit="%"),
    "current_assets_to_assets": CompanyV2FieldMetadata("流动资产占总资产", "percentage_fraction", source_field="CAToAsset", unit="%"),
    "non_current_assets_to_assets": CompanyV2FieldMetadata("非流动资产占总资产", "percentage_fraction", source_field="NCAToAsset", unit="%"),
    "debt_ratio": CompanyV2FieldMetadata("资产负债率", "percentage_fraction", source_field="liabilityToAsset", unit="%"),
    "current_ratio": CompanyV2FieldMetadata("流动比率", "ratio", source_field="currentRatio"),
    "quick_ratio": CompanyV2FieldMetadata("速动比率", "ratio", source_field="quickRatio"),
    "cash_ratio": CompanyV2FieldMetadata("现金比率", "ratio", source_field="cashRatio"),
    "equity_multiplier": CompanyV2FieldMetadata("权益乘数", "multiple", source_field="assetToEquity"),
    "asset_turnover": CompanyV2FieldMetadata("总资产周转率", "ratio", source_field="AssetTurnRatio"),
    "total_asset_turnover": CompanyV2FieldMetadata("总资产周转率", "ratio", source_field="AssetTurnRatio"),
    "inventory_turnover": CompanyV2FieldMetadata("存货周转率", "ratio", source_field="INVTurnRatio"),
    "receivable_turnover": CompanyV2FieldMetadata("应收账款周转率", "ratio", source_field="NRTurnRatio"),
    "dupont_roe": CompanyV2FieldMetadata("杜邦 ROE", "percentage_fraction", source_field="dupontROE", unit="%"),
    "dupont_net_profit_factor": CompanyV2FieldMetadata("净利润/利润总额", "ratio", source_field="dupontPnitoni"),
    "dupont_income_margin": CompanyV2FieldMetadata("利润总额/收入", "percentage_fraction", source_field="dupontNitogr", unit="%"),
    "dupont_asset_turn": CompanyV2FieldMetadata("总资产周转率", "ratio", source_field="dupontAssetTurn"),
    "dupont_em": CompanyV2FieldMetadata("权益乘数", "multiple", source_field="dupontAssetStoEquity"),
    "documents_count": CompanyV2FieldMetadata("报告文件数", "count", period_required=False, precision=0),
    "chunks_count": CompanyV2FieldMetadata("年报片段数", "count", period_required=False, precision=0),
    "embedding_count": CompanyV2FieldMetadata("向量片段数", "count", period_required=False, precision=0),
}


def get_field_metadata(field_key: str) -> CompanyV2FieldMetadata | None:
    if field_key in FIELD_METADATA:
        return FIELD_METADATA[field_key]
    for meta in FIELD_METADATA.values():
        if field_key in meta.aliases:
            return meta
    return None


def field_metadata_payload(field_key: str) -> dict[str, Any]:
    meta = get_field_metadata(field_key)
    if meta is None:
        return {
            "label": field_key,
            "semantic_type": "raw",
            "scale": 1.0,
            "precision": 2,
            "source_field": None,
            "period_required": False,
            "formula": None,
            "aliases": [],
        }
    return {
        "label": meta.label,
        "semantic_type": meta.semantic_type,
        "scale": meta.scale,
        "precision": meta.precision,
        "source_field": meta.source_field,
        "period_required": meta.period_required,
        "formula": meta.formula,
        "aliases": list(meta.aliases),
        "unit": meta.unit,
    }
