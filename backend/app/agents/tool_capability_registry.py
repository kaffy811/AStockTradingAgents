"""Canonical tool capability registry for financial agents."""
from __future__ import annotations


CAPABILITIES: dict[str, dict[str, object]] = {
    "resolve_security": {"tool": "resolve_stock_tool", "fresh_data": False},
    "get_quote": {"tool": "get_quote_tool", "fresh_data": True},
    "get_company_profile": {"tool": "company_profile_service", "fresh_data": False},
    "get_financial_snapshot": {"tool": "company_v2_snapshot", "fresh_data": False},
    "get_financial_history": {"tool": "company_v2_history", "fresh_data": False},
    "get_official_reports": {"tool": "company_v2_reports", "fresh_data": False},
    "get_structured_report_fields": {"tool": "report_financial_table_extractor", "fresh_data": False},
    "query_report_rag": {"tool": "company_v2_report_rag", "fresh_data": False},
    "compare_companies": {"tool": "report_comparison_skill", "fresh_data": False},
    "get_industry_benchmark": {"tool": "industry_classification_service", "fresh_data": False},
    "get_news": {"tool": "get_latest_news_tool", "fresh_data": True},
    "get_technical_indicators": {"tool": "get_kline_summary_tool", "fresh_data": True},
}


def get_capability(name: str) -> dict[str, object] | None:
    return CAPABILITIES.get(name)
