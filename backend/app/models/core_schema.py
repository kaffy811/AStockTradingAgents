"""
app/models/core_schema.py — 核心数据字段注册表（Phase 6N-6）

CoreFieldRegistry 定义所有核心字段的元数据：
  - 字段分类（quote / valuation / income / balance / cashflow / indicators / rag）
  - 首选数据源顺序
  - 是否可计算（computed）
  - 计算公式（formula）
  - 依赖字段
  - 是否允许 null（不允许时缺失须提供 reason_code）

CoverageAuditService 使用此注册表计算每只股票的字段完整率。
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ── 字段定义 ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FieldSpec:
    name:             str
    category:         str
    nullable:         bool          = False       # 允许 null（如 dividend_yield 可能为 0/None）
    provider_chain:   list[str]     = field(default_factory=list)
    computed:         bool          = False
    formula:          str           = ""
    dependencies:     list[str]     = field(default_factory=list)
    description:      str           = ""


# ── 注册表 ────────────────────────────────────────────────────────────────────

CORE_FIELDS: dict[str, FieldSpec] = {

    # ── 行情（quote）────────────────────────────────────────────────────────

    "latest_price": FieldSpec(
        name="latest_price",
        category="quote",
        provider_chain=["tushare_daily", "tencent", "sina", "eastmoney", "kline_proxy"],
        description="最新价（收盘价或实时）",
    ),
    "change_pct": FieldSpec(
        name="change_pct",
        category="quote",
        provider_chain=["tushare_daily", "tencent", "sina", "eastmoney"],
        computed=True,
        formula="close / pre_close - 1",
        dependencies=["close", "pre_close"],
        description="涨跌幅 %",
    ),
    "volume": FieldSpec(
        name="volume",
        category="quote",
        provider_chain=["tushare_daily", "tencent", "sina", "eastmoney"],
        description="成交量（手）",
    ),
    "amount": FieldSpec(
        name="amount",
        category="quote",
        nullable=True,
        provider_chain=["tushare_daily", "eastmoney"],
        description="成交额（元）",
    ),
    "trade_date": FieldSpec(
        name="trade_date",
        category="quote",
        provider_chain=["tushare_daily", "tencent", "sina"],
        description="交易日期",
    ),

    # ── 估值（valuation）────────────────────────────────────────────────────

    "pe_ttm": FieldSpec(
        name="pe_ttm",
        category="valuation",
        nullable=True,
        provider_chain=["tushare_daily_basic", "eastmoney", "akshare"],
        description="市盈率（TTM）",
    ),
    "pb": FieldSpec(
        name="pb",
        category="valuation",
        provider_chain=["tushare_daily_basic", "eastmoney", "akshare"],
        description="市净率",
    ),
    "market_cap": FieldSpec(
        name="market_cap",
        category="valuation",
        provider_chain=["tushare_daily_basic", "eastmoney"],
        computed=True,
        formula="latest_price * total_share",
        dependencies=["latest_price", "total_share"],
        description="总市值（元）",
    ),
    "total_share": FieldSpec(
        name="total_share",
        category="valuation",
        provider_chain=["tushare_daily_basic"],
        description="总股本（万股）",
    ),
    "float_share": FieldSpec(
        name="float_share",
        category="valuation",
        provider_chain=["tushare_daily_basic"],
        description="流通股本（万股）",
    ),
    "turnover_rate": FieldSpec(
        name="turnover_rate",
        category="valuation",
        nullable=True,
        provider_chain=["tushare_daily_basic"],
        description="换手率 %",
    ),
    "dividend_yield": FieldSpec(
        name="dividend_yield",
        category="valuation",
        nullable=True,
        provider_chain=["tushare_daily_basic", "eastmoney"],
        description="股息率 %",
    ),

    # ── 利润表（income）──────────────────────────────────────────────────────

    "revenue": FieldSpec(
        name="revenue",
        category="income",
        provider_chain=["tushare_income", "baostock_profit", "akshare"],
        description="营业收入",
    ),
    "gross_profit": FieldSpec(
        name="gross_profit",
        category="income",
        provider_chain=["tushare_income"],
        computed=True,
        formula="revenue - cost_of_revenue",
        dependencies=["revenue", "cost_of_revenue"],
        description="毛利润",
    ),
    "operating_profit": FieldSpec(
        name="operating_profit",
        category="income",
        provider_chain=["tushare_income"],
        description="营业利润",
    ),
    "net_profit": FieldSpec(
        name="net_profit",
        category="income",
        provider_chain=["tushare_income", "baostock_profit"],
        description="净利润（含少数股东权益）",
    ),
    "net_profit_parent": FieldSpec(
        name="net_profit_parent",
        category="income",
        provider_chain=["tushare_income", "baostock_profit"],
        description="归母净利润",
    ),

    # ── 资产负债表（balance）────────────────────────────────────────────────

    "total_assets": FieldSpec(
        name="total_assets",
        category="balance",
        provider_chain=["tushare_balance", "baostock_balance"],
        description="总资产",
    ),
    "total_liabilities": FieldSpec(
        name="total_liabilities",
        category="balance",
        provider_chain=["tushare_balance", "baostock_balance"],
        description="总负债",
    ),
    "total_equity": FieldSpec(
        name="total_equity",
        category="balance",
        provider_chain=["tushare_balance", "baostock_balance"],
        description="股东权益合计",
    ),
    "current_assets": FieldSpec(
        name="current_assets",
        category="balance",
        provider_chain=["tushare_balance"],
        description="流动资产",
    ),
    "current_liabilities": FieldSpec(
        name="current_liabilities",
        category="balance",
        provider_chain=["tushare_balance"],
        description="流动负债",
    ),

    # ── 现金流量表（cashflow）───────────────────────────────────────────────

    "operating_cashflow": FieldSpec(
        name="operating_cashflow",
        category="cashflow",
        provider_chain=["tushare_cashflow", "baostock_cash_flow"],
        description="经营活动现金净流量",
    ),
    "investing_cashflow": FieldSpec(
        name="investing_cashflow",
        category="cashflow",
        nullable=True,
        provider_chain=["tushare_cashflow"],
        description="投资活动现金净流量",
    ),
    "financing_cashflow": FieldSpec(
        name="financing_cashflow",
        category="cashflow",
        nullable=True,
        provider_chain=["tushare_cashflow"],
        description="筹资活动现金净流量",
    ),

    # ── 财务指标（indicators）───────────────────────────────────────────────

    "roe": FieldSpec(
        name="roe",
        category="indicators",
        provider_chain=["tushare_fina_indicator", "baostock_dupont"],
        computed=True,
        formula="net_profit_parent / avg_parent_equity",
        dependencies=["net_profit_parent", "total_equity"],
        description="净资产收益率（加权）%",
    ),
    "roa": FieldSpec(
        name="roa",
        category="indicators",
        provider_chain=["tushare_fina_indicator"],
        computed=True,
        formula="net_profit / avg_total_assets",
        dependencies=["net_profit", "total_assets"],
        description="总资产收益率 %",
    ),
    "gross_margin": FieldSpec(
        name="gross_margin",
        category="indicators",
        provider_chain=["tushare_fina_indicator", "baostock_profit"],
        computed=True,
        formula="gross_profit / revenue",
        dependencies=["gross_profit", "revenue"],
        description="毛利率 %",
    ),
    "net_margin": FieldSpec(
        name="net_margin",
        category="indicators",
        provider_chain=["tushare_fina_indicator", "baostock_profit"],
        computed=True,
        formula="net_profit / revenue",
        dependencies=["net_profit", "revenue"],
        description="净利率 %",
    ),
    "revenue_growth": FieldSpec(
        name="revenue_growth",
        category="indicators",
        provider_chain=["tushare_fina_indicator", "baostock_growth"],
        description="营业收入同比增长率 %",
    ),
    "net_profit_growth": FieldSpec(
        name="net_profit_growth",
        category="indicators",
        provider_chain=["tushare_fina_indicator", "baostock_growth"],
        description="净利润同比增长率 %",
    ),
    "debt_ratio": FieldSpec(
        name="debt_ratio",
        category="indicators",
        provider_chain=["tushare_fina_indicator", "baostock_balance"],
        computed=True,
        formula="total_liabilities / total_assets",
        dependencies=["total_liabilities", "total_assets"],
        description="资产负债率 %",
    ),
    "current_ratio": FieldSpec(
        name="current_ratio",
        category="indicators",
        provider_chain=["tushare_fina_indicator", "baostock_balance"],
        computed=True,
        formula="current_assets / current_liabilities",
        dependencies=["current_assets", "current_liabilities"],
        description="流动比率",
    ),
    "asset_turnover": FieldSpec(
        name="asset_turnover",
        category="indicators",
        provider_chain=["tushare_fina_indicator", "baostock_operation"],
        computed=True,
        formula="revenue / avg_total_assets",
        dependencies=["revenue", "total_assets"],
        description="总资产周转率（次）",
    ),
    "ocf_to_np": FieldSpec(
        name="ocf_to_np",
        category="indicators",
        provider_chain=["tushare_fina_indicator", "baostock_cash_flow"],
        computed=True,
        formula="operating_cashflow / net_profit",
        dependencies=["operating_cashflow", "net_profit"],
        description="经营现金流/净利润（盈利质量）",
    ),
    "dupont_equity_multiplier": FieldSpec(
        name="dupont_equity_multiplier",
        category="indicators",
        provider_chain=["baostock_dupont"],
        computed=True,
        formula="total_assets / total_equity",
        dependencies=["total_assets", "total_equity"],
        description="杜邦权益乘数",
    ),

    # ── 年报 / RAG ─────────────────────────────────────────────────────────

    "latest_annual_report": FieldSpec(
        name="latest_annual_report",
        category="rag",
        nullable=True,
        provider_chain=["report_documents"],
        description="最新年报文件（PDF）",
    ),
    "latest_interim_report": FieldSpec(
        name="latest_interim_report",
        category="rag",
        nullable=True,
        provider_chain=["report_documents"],
        description="最新中报文件（PDF）",
    ),
    "documents_count": FieldSpec(
        name="documents_count",
        category="rag",
        provider_chain=["report_documents"],
        description="已入库年报文件数",
    ),
    "chunks_count": FieldSpec(
        name="chunks_count",
        category="rag",
        provider_chain=["report_chunks"],
        description="已切片 chunk 数",
    ),
    "embedding_count": FieldSpec(
        name="embedding_count",
        category="rag",
        provider_chain=["report_chunks"],
        description="已向量化 chunk 数",
    ),
    "rag_status": FieldSpec(
        name="rag_status",
        category="rag",
        provider_chain=["report_chunks"],
        description="RAG 可用状态（ready/not_indexed/empty/unknown）",
    ),
}


# ── 分类汇总 ──────────────────────────────────────────────────────────────────

FIELD_CATEGORIES: dict[str, list[str]] = {}
for _spec in CORE_FIELDS.values():
    FIELD_CATEGORIES.setdefault(_spec.category, []).append(_spec.name)


def get_fields_by_category(category: str) -> list[FieldSpec]:
    """返回某类别下的所有字段 FieldSpec。"""
    return [CORE_FIELDS[n] for n in FIELD_CATEGORIES.get(category, [])]


def get_non_nullable_fields() -> list[FieldSpec]:
    """返回所有不允许 null、缺失时必须提供 reason_code 的字段。"""
    return [s for s in CORE_FIELDS.values() if not s.nullable]


def get_computed_fields() -> list[FieldSpec]:
    """返回所有可计算字段。"""
    return [s for s in CORE_FIELDS.values() if s.computed]
