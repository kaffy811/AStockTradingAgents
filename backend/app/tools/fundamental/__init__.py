"""
app/tools/fundamental — 基本面数据工具层（Phase 2C）

MODULE_CATALOG 字段说明：
  seq        : 排序序号（正式模块按功能分组编号；alias 从 101 起）
  key        : 唯一模块 key，也是 TOOL_REGISTRY 的主 key
  name_zh    : 中文名称
  name_en    : 英文名称
  phase      : 实现阶段
  requires_llm : 是否依赖 LLM（确定性工具均为 False）
  cache_ttl  : Redis 缓存 TTL（秒）
  status     : available / legacy / planned / hidden
  display    : True = 在 /api/v1/modules 中展示；False = 仅供路由访问（alias）
  alias_of   : 如果是 alias，指向规范 key；否则为 None
  group      : 功能分组名称（display=True 条目必填）
  group_seq  : 功能分组排序（1-8）

/api/v1/modules 仅返回 display=True 且 status != "hidden" 的条目。
兼容路由 /api/v1/stock/{code}/modules/{module_id} 支持所有 TOOL_REGISTRY key（含 alias）。
"""

from app.tools.fundamental.base import BaseFundamentalTool, FundamentalToolError
from app.tools.fundamental.quote_snapshot import QuoteSnapshotTool
from app.tools.fundamental.financial_summary import FinancialSummaryTool
from app.tools.fundamental.income_statement import IncomeStatementTool
from app.tools.fundamental.balance_sheet import BalanceSheetTool
from app.tools.fundamental.cashflow_health import CashflowHealthTool
from app.tools.fundamental.valuation import ValuationTool
from app.tools.fundamental.dupont import DupontTool
from app.tools.fundamental.cashflow_quality import CashflowQualityTool
from app.tools.fundamental.growth import GrowthTool
from app.tools.fundamental.profitability import ProfitabilityTool
from app.tools.fundamental.expense_analysis import ExpenseAnalysisTool
from app.tools.fundamental.asset_structure import AssetStructureTool
from app.tools.fundamental.solvency import SolvencyTool
from app.tools.fundamental.operation_capability import OperationCapabilityTool
from app.tools.fundamental.capital_occupation import CapitalOccupationTool
from app.tools.fundamental.industry_rank import IndustryRankTool
from app.tools.fundamental.main_business import MainBusinessTool
from app.tools.fundamental.dividend_history import DividendHistoryTool
from app.tools.fundamental.major_holders import MajorHoldersTool
from app.tools.fundamental.equity_structure import EquityStructureTool
from app.tools.fundamental.announcements import AnnouncementsTool
from app.tools.fundamental.analyst_ratings import AnalystRatingsTool

__all__ = [
    "BaseFundamentalTool",
    "FundamentalToolError",
    "QuoteSnapshotTool",
    "FinancialSummaryTool",
    "IncomeStatementTool",
    "BalanceSheetTool",
    "CashflowHealthTool",
    "ValuationTool",
    "DupontTool",
    "CashflowQualityTool",
    "GrowthTool",
    "ProfitabilityTool",
    "ExpenseAnalysisTool",
    "AssetStructureTool",
    "SolvencyTool",
    "OperationCapabilityTool",
    "CapitalOccupationTool",
    "IndustryRankTool",
    "MainBusinessTool",
    "DividendHistoryTool",
    "MajorHoldersTool",
    "EquityStructureTool",
    "AnnouncementsTool",
    "AnalystRatingsTool",
]

# ── 工具注册表（module_key → 工具类） ─────────────────────────────────────────
# 支持 Phase 1 原始 key、Phase 1.5 新 key、Phase 2A 新 key、Phase 2B key 和 Phase 2C key
# 包含全部别名（alias），以支持兼容路由
TOOL_REGISTRY: dict[str, type[BaseFundamentalTool]] = {
    # ── Phase 1.5 规范 key ────────────────────────────────────────────
    "snapshot":              QuoteSnapshotTool,
    "financial_summary":     FinancialSummaryTool,
    "valuation":             ValuationTool,
    "dupont":                DupontTool,
    "cashflow_quality":      CashflowQualityTool,
    # ── Phase 2A 规范 key ─────────────────────────────────────────────
    "growth":                GrowthTool,
    "profitability":         ProfitabilityTool,
    "expense_analysis":      ExpenseAnalysisTool,
    "asset_structure":       AssetStructureTool,
    "solvency":              SolvencyTool,
    "operation_capability":  OperationCapabilityTool,
    "capital_occupation":    CapitalOccupationTool,
    # ── Phase 2B 规范 key ─────────────────────────────────────────────
    "industry_rank":         IndustryRankTool,
    # ── Phase 2C 规范 key ─────────────────────────────────────────────
    "main_business":         MainBusinessTool,
    "dividend_history":      DividendHistoryTool,
    "major_holders":         MajorHoldersTool,
    "equity_structure":      EquityStructureTool,
    "announcements":         AnnouncementsTool,
    "analyst_ratings":       AnalystRatingsTool,
    # ── Phase 1 遗留 key（仍可访问，status=legacy）──────────────────
    "income_statement":      IncomeStatementTool,
    "balance_sheet":         BalanceSheetTool,
    # ── Alias（兼容路由支持，display=False，status=hidden）──────────
    "quote_snapshot":        QuoteSnapshotTool,    # → snapshot
    "cashflow_health":       CashflowHealthTool,   # → cashflow_quality（此工具已有独立实现）
    "cashflow":              CashflowQualityTool,  # → cashflow_quality
    "growth_metrics":        GrowthTool,           # → growth
    "profit_quality":        ProfitabilityTool,    # → profitability
    "operating_efficiency":  OperationCapabilityTool,  # → operation_capability
    "industry_ranking":      IndustryRankTool,     # → industry_rank
    "peer_rank":             IndustryRankTool,     # → industry_rank
    "industry_position":     IndustryRankTool,     # → industry_rank
    # ── Phase 2C Alias ────────────────────────────────────────────────
    "dividend":              DividendHistoryTool,  # → dividend_history
    "holders":               MajorHoldersTool,     # → major_holders
    "shareholders":          MajorHoldersTool,     # → major_holders
    "events":                AnnouncementsTool,    # → announcements
    "forecast_rating":       AnalystRatingsTool,   # → analyst_ratings
    "rating":                AnalystRatingsTool,   # → analyst_ratings
}

# ── 模块目录（Phase 2C 完整版） ───────────────────────────────────────────────
#
# display=True  → 出现在 /api/v1/modules（前端目录）
# display=False → 仅通过路由访问（alias / hidden）
# status=hidden → 同上，双重保险（list_modules() 同时检查 display 和 status）
#
# group_seq / group 分组：
#   1=概览  2=财务分析  3=资产负债  4=同行对比  5=股东分红  6=事件观点  7=交易辅助  8=AI分析
#
MODULE_CATALOG: list[dict] = [
    # ══════════════════════════════════════════════════════════════════
    # group_seq=1  概览
    # ══════════════════════════════════════════════════════════════════
    {
        "seq": 1, "key": "snapshot", "name_zh": "基础信息与行情", "name_en": "Quote Snapshot",
        "phase": 1, "requires_llm": False, "cache_ttl": 60,
        "status": "available", "display": True, "alias_of": None,
        "group": "概览", "group_seq": 1,
        # ── Phase 2D 渲染契约字段 ──
        "render_type": "metric_cards", "chart_type": "none",
        "table_primary_key": None, "default_limit": 1,
        "supports_period": False, "supports_export": True,
        "field_labels": {
            "name": "公司名称", "industry": "行业", "price": "最新价",
            "pe_ttm": "PE(TTM)", "pb": "PB", "total_mv": "总市值",
            "circ_mv": "流通市值", "change_pct": "涨跌幅",
        },
        "unit_hints": {
            "price": "元", "total_mv": "万元", "circ_mv": "万元",
            "pe_ttm": "倍", "pb": "倍", "change_pct": "%",
        },
        "description": "行情基础信息快照，含价格、市值、估值比率",
        "data_freshness": "daily", "disclaimer_type": "data_only",
    },
    {
        "seq": 2, "key": "financial_summary", "name_zh": "财报核心数据", "name_en": "Financial Summary",
        "phase": 1, "requires_llm": False, "cache_ttl": 14400,
        "status": "available", "display": True, "alias_of": None,
        "group": "概览", "group_seq": 1,
        # ── Phase 2D 渲染契约字段 ──
        "render_type": "metric_cards", "chart_type": "none",
        "table_primary_key": "end_date", "default_limit": 4,
        "supports_period": True, "supports_export": True,
        "field_labels": {
            "end_date": "报告期", "revenue": "营收", "net_profit": "净利润",
            "roe": "ROE", "eps": "EPS", "gross_margin": "毛利率",
        },
        "unit_hints": {
            "revenue": "元", "net_profit": "元",
            "roe": "%", "gross_margin": "%", "eps": "元/股",
        },
        "description": "最新财报核心数据汇总，含营收、净利润、ROE",
        "data_freshness": "quarterly", "disclaimer_type": "data_only",
    },
    # ══════════════════════════════════════════════════════════════════
    # group_seq=2  财务分析
    # ══════════════════════════════════════════════════════════════════
    {
        "seq": 3, "key": "valuation", "name_zh": "估值分位", "name_en": "Valuation Percentile",
        "phase": 1, "requires_llm": False, "cache_ttl": 3600,
        "status": "available", "display": True, "alias_of": None,
        "group": "财务分析", "group_seq": 2,
        # ── Phase 2D 渲染契约字段 ──
        "render_type": "chart_table", "chart_type": "line",
        "table_primary_key": "trade_date", "default_limit": 8,
        "supports_period": False, "supports_export": True,
        "field_labels": {
            "trade_date": "交易日", "pe_ttm": "PE(TTM)", "pb": "PB",
            "ps_ttm": "PS(TTM)", "pe_percentile": "PE历史分位", "pb_percentile": "PB历史分位",
        },
        "unit_hints": {
            "pe_ttm": "倍", "pb": "倍", "ps_ttm": "倍",
            "pe_percentile": "%", "pb_percentile": "%",
        },
        "description": "估值历史分位（PE/PB/PS TTM），反映当前估值贵贱程度",
        "data_freshness": "daily", "disclaimer_type": "not_investment_advice",
    },
    {
        "seq": 4, "key": "dupont", "name_zh": "杜邦分析", "name_en": "DuPont Analysis",
        "phase": 1, "requires_llm": False, "cache_ttl": 14400,
        "status": "available", "display": True, "alias_of": None,
        "group": "财务分析", "group_seq": 2,
        # ── Phase 2D 渲染契约字段 ──
        "render_type": "chart_table", "chart_type": "bar",
        "table_primary_key": "end_date", "default_limit": 8,
        "supports_period": True, "supports_export": True,
        "field_labels": {
            "end_date": "报告期", "roe": "ROE", "net_margin": "净利率",
            "asset_turnover": "资产周转率", "equity_multiplier": "权益乘数",
        },
        "unit_hints": {
            "roe": "%", "net_margin": "%", "asset_turnover": "次/年",
        },
        "description": "杜邦分解：ROE = 净利率 × 资产周转率 × 权益乘数",
        "data_freshness": "quarterly", "disclaimer_type": "data_only",
    },
    {
        "seq": 5, "key": "cashflow_quality", "name_zh": "现金流质量", "name_en": "Cashflow Quality",
        "phase": 1, "requires_llm": False, "cache_ttl": 14400,
        "status": "available", "display": True, "alias_of": None,
        "group": "财务分析", "group_seq": 2,
        # ── Phase 2D 渲染契约字段 ──
        "render_type": "chart_table", "chart_type": "bar",
        "table_primary_key": "end_date", "default_limit": 8,
        "supports_period": True, "supports_export": True,
        "field_labels": {
            "end_date": "报告期", "ocf": "经营现金流", "net_profit": "净利润",
            "cash_cover_ratio": "现金含量", "free_cashflow": "自由现金流",
        },
        "unit_hints": {
            "ocf": "元", "net_profit": "元",
            "free_cashflow": "元", "cash_cover_ratio": "%",
        },
        "description": "经营现金流质量：现金含量=OCF/净利润，衡量利润真实性",
        "data_freshness": "quarterly", "disclaimer_type": "data_only",
    },
    {
        "seq": 6, "key": "growth", "name_zh": "成长性指标", "name_en": "Growth Metrics",
        "phase": 2, "requires_llm": False, "cache_ttl": 14400,
        "status": "available", "display": True, "alias_of": None,
        "group": "财务分析", "group_seq": 2,
        # ── Phase 2D 渲染契约字段 ──
        "render_type": "chart_table", "chart_type": "bar",
        "table_primary_key": "end_date", "default_limit": 8,
        "supports_period": True, "supports_export": True,
        "field_labels": {
            "end_date": "报告期", "revenue": "营收",
            "revenue_yoy_pct": "营收同比", "net_profit_parent": "归母净利润",
            "net_profit_yoy_pct": "净利润同比", "deduct_net_profit_yoy_pct": "扣非净利润同比",
        },
        "unit_hints": {
            "revenue": "元", "net_profit_parent": "元",
            "revenue_yoy_pct": "%", "net_profit_yoy_pct": "%",
            "deduct_net_profit_yoy_pct": "%",
        },
        "description": "成长性趋势：营收/净利润/扣非净利润同比增速",
        "data_freshness": "quarterly", "disclaimer_type": "data_only",
    },
    {
        "seq": 7, "key": "profitability", "name_zh": "盈利质量", "name_en": "Profitability",
        "phase": 2, "requires_llm": False, "cache_ttl": 14400,
        "status": "available", "display": True, "alias_of": None,
        "group": "财务分析", "group_seq": 2,
        # ── Phase 2D 渲染契约字段 ──
        "render_type": "chart_table", "chart_type": "line",
        "table_primary_key": "end_date", "default_limit": 8,
        "supports_period": True, "supports_export": True,
        "field_labels": {
            "end_date": "报告期", "gross_margin": "毛利率", "net_margin": "净利率",
            "roe": "ROE", "roa": "ROA", "expense_ratio": "期间费用率",
        },
        "unit_hints": {
            "gross_margin": "%", "net_margin": "%",
            "roe": "%", "roa": "%", "expense_ratio": "%",
        },
        "description": "盈利质量：毛利率/净利率/ROE/ROA 多维对比",
        "data_freshness": "quarterly", "disclaimer_type": "data_only",
    },
    {
        "seq": 8, "key": "expense_analysis", "name_zh": "费用结构", "name_en": "Expense Analysis",
        "phase": 2, "requires_llm": False, "cache_ttl": 14400,
        "status": "available", "display": True, "alias_of": None,
        "group": "财务分析", "group_seq": 2,
        # ── Phase 2D 渲染契约字段 ──
        "render_type": "chart_table", "chart_type": "stacked_bar",
        "table_primary_key": "end_date", "default_limit": 8,
        "supports_period": True, "supports_export": True,
        "field_labels": {
            "end_date": "报告期", "sell_exp_ratio": "销售费用率",
            "admin_exp_ratio": "管理费用率", "fin_exp_ratio": "财务费用率",
            "rd_exp_ratio": "研发费用率", "total_exp_ratio": "合计费用率",
        },
        "unit_hints": {
            "sell_exp_ratio": "%", "admin_exp_ratio": "%",
            "fin_exp_ratio": "%", "rd_exp_ratio": "%", "total_exp_ratio": "%",
        },
        "description": "费用结构分析：四项费用率拆分，观察成本管控趋势",
        "data_freshness": "quarterly", "disclaimer_type": "data_only",
    },
    {
        "seq": 9, "key": "main_business", "name_zh": "主营业务构成", "name_en": "Main Business",
        "phase": 2, "requires_llm": False, "cache_ttl": 86400,
        "status": "available", "display": True, "alias_of": None,
        "group": "财务分析", "group_seq": 2,
        # ── Phase 2D 渲染契约字段 ──
        "render_type": "table", "chart_type": "pie",
        "table_primary_key": "bz_item", "default_limit": 2,
        "supports_period": True, "supports_export": True,
        "field_labels": {
            "bz_item": "业务线", "bz_sales": "销售额", "bz_profit": "利润",
            "bz_cost": "成本", "sales_ratio_pct": "收入占比", "end_date": "报告期",
        },
        "unit_hints": {
            "bz_sales": "元", "bz_profit": "元",
            "bz_cost": "元", "sales_ratio_pct": "%",
        },
        "description": "主营业务构成：各产品线收入占比及利润拆分",
        "data_freshness": "quarterly", "disclaimer_type": "data_only",
    },
    {
        "seq": 10, "key": "income_statement", "name_zh": "利润表趋势", "name_en": "Income Statement",
        "phase": 1, "requires_llm": False, "cache_ttl": 14400,
        "status": "legacy", "display": True, "alias_of": None,
        "group": "财务分析", "group_seq": 2,
        # ── Phase 2D 渲染契约字段 ──
        "render_type": "table", "chart_type": "bar",
        "table_primary_key": "end_date", "default_limit": 8,
        "supports_period": True, "supports_export": True,
        "field_labels": {}, "unit_hints": {},
        "description": "（遗留）详细利润表报表数据",
        "data_freshness": "quarterly", "disclaimer_type": "data_only",
    },
    # ══════════════════════════════════════════════════════════════════
    # group_seq=3  资产负债
    # ══════════════════════════════════════════════════════════════════
    {
        "seq": 11, "key": "asset_structure", "name_zh": "资产结构", "name_en": "Asset Structure",
        "phase": 2, "requires_llm": False, "cache_ttl": 14400,
        "status": "available", "display": True, "alias_of": None,
        "group": "资产负债", "group_seq": 3,
        # ── Phase 2D 渲染契约字段 ──
        "render_type": "chart_table", "chart_type": "stacked_bar",
        "table_primary_key": "end_date", "default_limit": 8,
        "supports_period": True, "supports_export": True,
        "field_labels": {
            "end_date": "报告期", "total_assets": "总资产",
            "current_assets": "流动资产", "non_current_assets": "非流动资产",
            "current_asset_ratio_pct": "流动资产比例",
            "goodwill": "商誉", "intangible_assets": "无形资产",
        },
        "unit_hints": {
            "total_assets": "元", "current_assets": "元",
            "non_current_assets": "元", "current_asset_ratio_pct": "%",
            "goodwill": "元", "intangible_assets": "元",
        },
        "description": "资产结构：流动/非流动资产构成，商誉和无形资产占比",
        "data_freshness": "quarterly", "disclaimer_type": "data_only",
    },
    {
        "seq": 12, "key": "solvency", "name_zh": "偿债能力", "name_en": "Solvency",
        "phase": 2, "requires_llm": False, "cache_ttl": 14400,
        "status": "available", "display": True, "alias_of": None,
        "group": "资产负债", "group_seq": 3,
        # ── Phase 2D 渲染契约字段 ──
        "render_type": "chart_table", "chart_type": "line",
        "table_primary_key": "end_date", "default_limit": 8,
        "supports_period": True, "supports_export": True,
        "field_labels": {
            "end_date": "报告期", "debt_to_assets": "资产负债率",
            "current_ratio": "流动比率", "quick_ratio": "速动比率",
            "interest_coverage": "利息保障倍数",
        },
        "unit_hints": {
            "debt_to_assets": "%", "current_ratio": "倍",
            "quick_ratio": "倍", "interest_coverage": "倍",
        },
        "description": "偿债能力：负债率/流动/速动比率，反映短期和长期偿债压力",
        "data_freshness": "quarterly", "disclaimer_type": "data_only",
    },
    {
        "seq": 13, "key": "operation_capability", "name_zh": "营运能力", "name_en": "Operation Capability",
        "phase": 2, "requires_llm": False, "cache_ttl": 14400,
        "status": "available", "display": True, "alias_of": None,
        "group": "资产负债", "group_seq": 3,
        # ── Phase 2D 渲染契约字段 ──
        "render_type": "chart_table", "chart_type": "line",
        "table_primary_key": "end_date", "default_limit": 8,
        "supports_period": True, "supports_export": True,
        "field_labels": {
            "end_date": "报告期", "asset_turnover": "总资产周转率",
            "ar_turnover": "应收账款周转率", "inv_turnover": "存货周转率",
            "op_cycle": "营业周期",
        },
        "unit_hints": {
            "asset_turnover": "次/年", "ar_turnover": "次/年",
            "inv_turnover": "次/年", "op_cycle": "天",
        },
        "description": "营运能力：资产/存货/应收账款周转率，衡量资产使用效率",
        "data_freshness": "quarterly", "disclaimer_type": "data_only",
    },
    {
        "seq": 14, "key": "capital_occupation", "name_zh": "资金占用", "name_en": "Capital Occupation",
        "phase": 2, "requires_llm": False, "cache_ttl": 14400,
        "status": "available", "display": True, "alias_of": None,
        "group": "资产负债", "group_seq": 3,
        # ── Phase 2D 渲染契约字段 ──
        "render_type": "chart_table", "chart_type": "bar",
        "table_primary_key": "end_date", "default_limit": 8,
        "supports_period": True, "supports_export": True,
        "field_labels": {
            "end_date": "报告期", "accounts_receivable": "应收账款",
            "prepayments": "预付款项", "accounts_payable": "应付账款",
            "advance_receipts": "预收款项", "net_capital_occupied": "净资金占用",
        },
        "unit_hints": {
            "accounts_receivable": "元", "prepayments": "元",
            "accounts_payable": "元", "advance_receipts": "元",
            "net_capital_occupied": "元",
        },
        "description": "资金占用分析：上下游资金占用关系，反映供应链议价能力",
        "data_freshness": "quarterly", "disclaimer_type": "data_only",
    },
    {
        "seq": 15, "key": "balance_sheet", "name_zh": "资产负债表关键指标", "name_en": "Balance Sheet",
        "phase": 1, "requires_llm": False, "cache_ttl": 14400,
        "status": "legacy", "display": True, "alias_of": None,
        "group": "资产负债", "group_seq": 3,
        # ── Phase 2D 渲染契约字段 ──
        "render_type": "table", "chart_type": "bar",
        "table_primary_key": "end_date", "default_limit": 8,
        "supports_period": True, "supports_export": True,
        "field_labels": {}, "unit_hints": {},
        "description": "（遗留）详细资产负债表报表数据",
        "data_freshness": "quarterly", "disclaimer_type": "data_only",
    },
    # ══════════════════════════════════════════════════════════════════
    # group_seq=4  同行对比
    # ══════════════════════════════════════════════════════════════════
    {
        "seq": 16, "key": "industry_rank", "name_zh": "行业排名", "name_en": "Industry Rank",
        "phase": 2, "requires_llm": False, "cache_ttl": 3600,
        "status": "available", "display": True, "alias_of": None,
        "group": "同行对比", "group_seq": 4,
        # ── Phase 2D 渲染契约字段 ──
        "render_type": "chart_table", "chart_type": "radar",
        "table_primary_key": "metric", "default_limit": 13,
        "supports_period": False, "supports_export": True,
        "field_labels": {
            "metric": "指标", "value": "当期值", "peer_count": "同行数量",
            "rank": "行业排名", "percentile": "行业分位", "industry": "行业",
        },
        "unit_hints": {"percentile": "%", "rank": "名"},
        "description": "行业排名分位：13项财务指标在申万L1行业中的百分位",
        "data_freshness": "daily", "disclaimer_type": "data_only",
    },
    {
        "seq": 17, "key": "peer_valuation", "name_zh": "同行业估值对比", "name_en": "Peer Valuation",
        "phase": 2, "requires_llm": False, "cache_ttl": 3600,
        "status": "planned", "display": True, "alias_of": None,
        "group": "同行对比", "group_seq": 4,
        # ── Phase 2D 渲染契约字段 ──
        "render_type": "placeholder", "chart_type": "none",
        "table_primary_key": None, "default_limit": 0,
        "supports_period": False, "supports_export": False,
        "field_labels": {}, "unit_hints": {},
        "description": "（计划中）同行业估值对比",
        "data_freshness": "daily", "disclaimer_type": "data_only",
    },
    {
        "seq": 18, "key": "peer_financial", "name_zh": "同行业财务对比", "name_en": "Peer Financial",
        "phase": 2, "requires_llm": False, "cache_ttl": 3600,
        "status": "planned", "display": True, "alias_of": None,
        "group": "同行对比", "group_seq": 4,
        # ── Phase 2D 渲染契约字段 ──
        "render_type": "placeholder", "chart_type": "none",
        "table_primary_key": None, "default_limit": 0,
        "supports_period": False, "supports_export": False,
        "field_labels": {}, "unit_hints": {},
        "description": "（计划中）同行业财务对比",
        "data_freshness": "daily", "disclaimer_type": "data_only",
    },
    # ══════════════════════════════════════════════════════════════════
    # group_seq=5  股东分红
    # ══════════════════════════════════════════════════════════════════
    {
        "seq": 19, "key": "major_holders", "name_zh": "大股东持股", "name_en": "Major Holders",
        "phase": 2, "requires_llm": False, "cache_ttl": 86400,
        "status": "available", "display": True, "alias_of": None,
        "group": "股东分红", "group_seq": 5,
        # ── Phase 2D 渲染契约字段 ──
        "render_type": "table", "chart_type": "bar",
        "table_primary_key": "holder_name", "default_limit": 5,
        "supports_period": False, "supports_export": True,
        "field_labels": {
            "holder_name": "股东名称", "hold_amount": "持股数量",
            "hold_ratio_pct": "持股比例", "end_date": "披露日",
            "holder_num": "股东户数", "holder_num_change": "户数变化",
        },
        "unit_hints": {
            "hold_amount": "股", "hold_ratio_pct": "%", "holder_num": "户",
        },
        "description": "十大流通股东及股东户数趋势",
        "data_freshness": "quarterly", "disclaimer_type": "data_only",
    },
    {
        "seq": 20, "key": "equity_structure", "name_zh": "股权结构", "name_en": "Equity Structure",
        "phase": 2, "requires_llm": False, "cache_ttl": 86400,
        "status": "available", "display": True, "alias_of": None,
        "group": "股东分红", "group_seq": 5,
        # ── Phase 2D 渲染契约字段 ──
        "render_type": "metric_cards", "chart_type": "donut",
        "table_primary_key": None, "default_limit": 1,
        "supports_period": False, "supports_export": True,
        "field_labels": {
            "total_share_wan": "总股本", "float_share_wan": "流通股本",
            "free_share_wan": "自由流通股", "total_mv_wan": "总市值",
            "circ_mv_wan": "流通市值", "float_ratio_pct": "流通比例",
            "free_ratio_pct": "自由流通比例",
        },
        "unit_hints": {
            "total_share_wan": "万股", "float_share_wan": "万股",
            "free_share_wan": "万股", "total_mv_wan": "万元",
            "circ_mv_wan": "万元", "float_ratio_pct": "%", "free_ratio_pct": "%",
        },
        "description": "股权结构快照：总股本/流通股/自由流通股及各类市值",
        "data_freshness": "daily", "disclaimer_type": "data_only",
    },
    {
        "seq": 21, "key": "dividend_history", "name_zh": "分红历史", "name_en": "Dividend History",
        "phase": 2, "requires_llm": False, "cache_ttl": 86400,
        "status": "available", "display": True, "alias_of": None,
        "group": "股东分红", "group_seq": 5,
        # ── Phase 2D 渲染契约字段 ──
        "render_type": "table", "chart_type": "bar",
        "table_primary_key": "end_date", "default_limit": 10,
        "supports_period": False, "supports_export": True,
        "field_labels": {
            "end_date": "报告期", "ex_date": "除权日", "pay_date": "派息日",
            "cash_div": "每股现金分红(税前)", "cash_div_tax": "每股现金分红(税后)",
            "stk_div": "每股送股", "div_proc": "状态",
        },
        "unit_hints": {
            "cash_div": "元/股", "cash_div_tax": "元/股", "stk_div": "股/股",
        },
        "description": "历史分红记录：每股现金分红、送股比例、除权日",
        "data_freshness": "annual", "disclaimer_type": "data_only",
    },
    # ══════════════════════════════════════════════════════════════════
    # group_seq=6  事件观点
    # ══════════════════════════════════════════════════════════════════
    {
        "seq": 22, "key": "announcements", "name_zh": "近期公告摘要", "name_en": "Announcements",
        "phase": 2, "requires_llm": False, "cache_ttl": 1800,
        "status": "available", "display": True, "alias_of": None,
        "group": "事件观点", "group_seq": 6,
        # ── Phase 2D 渲染契约字段 ──
        "render_type": "timeline", "chart_type": "timeline",
        "table_primary_key": "ann_date", "default_limit": 5,
        "supports_period": False, "supports_export": False,
        "field_labels": {
            "ann_date": "披露日", "end_date": "报告期", "type": "预告类型",
            "p_change_min": "净利润变化下限", "p_change_max": "净利润变化上限",
            "summary": "摘要",
        },
        "unit_hints": {"p_change_min": "%", "p_change_max": "%"},
        "description": "近期业绩预告与快报摘要",
        "data_freshness": "daily", "disclaimer_type": "estimated",
    },
    {
        "seq": 23, "key": "analyst_ratings", "name_zh": "研报评级汇总", "name_en": "Analyst Ratings",
        "phase": 2, "requires_llm": False, "cache_ttl": 7200,
        "status": "available", "display": True, "alias_of": None,
        "group": "事件观点", "group_seq": 6,
        # ── Phase 2D 渲染契约字段 ──
        "render_type": "mixed", "chart_type": "bar",
        "table_primary_key": "ann_date", "default_limit": 8,
        "supports_period": False, "supports_export": False,
        "field_labels": {
            "type": "预告类型", "sentiment": "情绪倾向",
            "p_change_min": "净利润变化下限", "p_change_max": "净利润变化上限",
            "ann_date": "披露日", "yoy_net_profit": "快报净利润同比",
        },
        "unit_hints": {
            "p_change_min": "%", "p_change_max": "%", "yoy_net_profit": "%",
        },
        "description": "业绩预期汇总（基于业绩预告类型映射）。注意：本模块非机构买卖评级，不代表投资建议。",
        "data_freshness": "daily", "disclaimer_type": "estimated",
    },
    # ══════════════════════════════════════════════════════════════════
    # group_seq=7  交易辅助
    # ══════════════════════════════════════════════════════════════════
    {
        "seq": 24, "key": "technical_snapshot", "name_zh": "技术面指标快照", "name_en": "Technical Snapshot",
        "phase": 2, "requires_llm": False, "cache_ttl": 14400,
        "status": "planned", "display": True, "alias_of": None,
        "group": "交易辅助", "group_seq": 7,
        # ── Phase 2D 渲染契约字段 ──
        "render_type": "placeholder", "chart_type": "none",
        "table_primary_key": None, "default_limit": 0,
        "supports_period": False, "supports_export": False,
        "field_labels": {}, "unit_hints": {},
        "description": "（计划中）技术面指标快照",
        "data_freshness": "daily", "disclaimer_type": "data_only",
    },
    {
        "seq": 25, "key": "fund_flow", "name_zh": "资金流向", "name_en": "Fund Flow",
        "phase": 2, "requires_llm": False, "cache_ttl": 3600,
        "status": "planned", "display": True, "alias_of": None,
        "group": "交易辅助", "group_seq": 7,
        # ── Phase 2D 渲染契约字段 ──
        "render_type": "placeholder", "chart_type": "none",
        "table_primary_key": None, "default_limit": 0,
        "supports_period": False, "supports_export": False,
        "field_labels": {}, "unit_hints": {},
        "description": "（计划中）资金流向",
        "data_freshness": "daily", "disclaimer_type": "data_only",
    },
    {
        "seq": 26, "key": "margin_trading", "name_zh": "融资融券", "name_en": "Margin Trading",
        "phase": 2, "requires_llm": False, "cache_ttl": 14400,
        "status": "planned", "display": True, "alias_of": None,
        "group": "交易辅助", "group_seq": 7,
        # ── Phase 2D 渲染契约字段 ──
        "render_type": "placeholder", "chart_type": "none",
        "table_primary_key": None, "default_limit": 0,
        "supports_period": False, "supports_export": False,
        "field_labels": {}, "unit_hints": {},
        "description": "（计划中）融资融券",
        "data_freshness": "daily", "disclaimer_type": "data_only",
    },
    # ══════════════════════════════════════════════════════════════════
    # group_seq=8  AI分析
    # ══════════════════════════════════════════════════════════════════
    {
        "seq": 27, "key": "ai_analysis", "name_zh": "AI 智能解析", "name_en": "AI Analysis",
        "phase": 3, "requires_llm": True, "cache_ttl": 86400,
        "status": "planned", "display": True, "alias_of": None,
        "group": "AI分析", "group_seq": 8,
        # ── Phase 2D 渲染契约字段 ──
        "render_type": "ai_card", "chart_type": "none",
        "table_primary_key": None, "default_limit": 0,
        "supports_period": False, "supports_export": False,
        "field_labels": {}, "unit_hints": {},
        "description": "AI智能解析（计划中）",
        "data_freshness": "daily", "disclaimer_type": "ai_generated",
    },
    # ══════════════════════════════════════════════════════════════════
    # 隐藏别名（display=False，status=hidden）
    # 不出现在 /api/v1/modules，但路由层仍支持访问
    # ══════════════════════════════════════════════════════════════════
    {
        "seq": 101, "key": "quote_snapshot", "name_zh": "行情快照（旧）", "name_en": "Quote Snapshot (legacy)",
        "phase": 1, "requires_llm": False, "cache_ttl": 60,
        "status": "hidden", "display": False, "alias_of": "snapshot",
    },
    {
        "seq": 102, "key": "cashflow_health", "name_zh": "现金流健康度（旧）", "name_en": "Cashflow Health (legacy)",
        "phase": 1, "requires_llm": False, "cache_ttl": 14400,
        "status": "hidden", "display": False, "alias_of": "cashflow_quality",
    },
    {
        "seq": 103, "key": "cashflow", "name_zh": "现金流质量（别名）", "name_en": "Cashflow Quality (alias)",
        "phase": 1, "requires_llm": False, "cache_ttl": 14400,
        "status": "hidden", "display": False, "alias_of": "cashflow_quality",
    },
    {
        "seq": 104, "key": "growth_metrics", "name_zh": "成长性指标（别名）", "name_en": "Growth Metrics (alias)",
        "phase": 2, "requires_llm": False, "cache_ttl": 14400,
        "status": "hidden", "display": False, "alias_of": "growth",
    },
    {
        "seq": 105, "key": "profit_quality", "name_zh": "盈利质量（别名）", "name_en": "Profitability (alias)",
        "phase": 2, "requires_llm": False, "cache_ttl": 14400,
        "status": "hidden", "display": False, "alias_of": "profitability",
    },
    {
        "seq": 106, "key": "operating_efficiency", "name_zh": "营运能力（别名）", "name_en": "Operation Capability (alias)",
        "phase": 2, "requires_llm": False, "cache_ttl": 14400,
        "status": "hidden", "display": False, "alias_of": "operation_capability",
    },
    {
        "seq": 107, "key": "industry_ranking", "name_zh": "行业排名（旧 key）", "name_en": "Industry Rank (alias)",
        "phase": 2, "requires_llm": False, "cache_ttl": 3600,
        "status": "hidden", "display": False, "alias_of": "industry_rank",
    },
    {
        "seq": 108, "key": "peer_rank", "name_zh": "行业排名（别名）", "name_en": "Industry Rank (alias)",
        "phase": 2, "requires_llm": False, "cache_ttl": 3600,
        "status": "hidden", "display": False, "alias_of": "industry_rank",
    },
    {
        "seq": 109, "key": "industry_position", "name_zh": "行业排名（别名）", "name_en": "Industry Rank (alias)",
        "phase": 2, "requires_llm": False, "cache_ttl": 3600,
        "status": "hidden", "display": False, "alias_of": "industry_rank",
    },
    # ── Phase 2C 新增别名（seq 110-115）────────────────────────────────
    {
        "seq": 110, "key": "dividend", "name_zh": "分红历史（别名）", "name_en": "Dividend History (alias)",
        "phase": 2, "requires_llm": False, "cache_ttl": 86400,
        "status": "hidden", "display": False, "alias_of": "dividend_history",
    },
    {
        "seq": 111, "key": "holders", "name_zh": "大股东持股（别名）", "name_en": "Major Holders (alias)",
        "phase": 2, "requires_llm": False, "cache_ttl": 86400,
        "status": "hidden", "display": False, "alias_of": "major_holders",
    },
    {
        "seq": 112, "key": "shareholders", "name_zh": "大股东持股（别名2）", "name_en": "Major Holders (alias)",
        "phase": 2, "requires_llm": False, "cache_ttl": 86400,
        "status": "hidden", "display": False, "alias_of": "major_holders",
    },
    {
        "seq": 113, "key": "events", "name_zh": "近期公告摘要（别名）", "name_en": "Announcements (alias)",
        "phase": 2, "requires_llm": False, "cache_ttl": 1800,
        "status": "hidden", "display": False, "alias_of": "announcements",
    },
    {
        "seq": 114, "key": "forecast_rating", "name_zh": "研报评级汇总（别名）", "name_en": "Analyst Ratings (alias)",
        "phase": 2, "requires_llm": False, "cache_ttl": 7200,
        "status": "hidden", "display": False, "alias_of": "analyst_ratings",
    },
    {
        "seq": 115, "key": "rating", "name_zh": "研报评级汇总（别名2）", "name_en": "Analyst Ratings (alias)",
        "phase": 2, "requires_llm": False, "cache_ttl": 7200,
        "status": "hidden", "display": False, "alias_of": "analyst_ratings",
    },
]

# ── 模块 key → name_zh 快速查找（包含 alias key） ─────────────────────────────
MODULE_NAME_MAP: dict[str, str] = {m["key"]: m["name_zh"] for m in MODULE_CATALOG}
