# Financial Agent Tool Registry

Implementation: `backend/app/agents/financial_runtime/tool_runtime.py`

## Capability List

- `resolve_security`
- `get_market_clock`
- `get_quote_snapshot`
- `get_market_history`
- `get_kline`
- `get_technical_indicators`
- `get_company_profile`
- `get_financial_snapshot`
- `get_financial_history`
- `get_cashflow_quality`
- `get_valuation`
- `get_capital_flow`
- `get_official_reports`
- `get_latest_official_report`
- `get_official_report_url`
- `get_structured_report_financials`
- `query_report_evidence`
- `get_company_news`
- `get_announcements`
- `get_market_events`
- `get_industry_snapshot`
- `get_peer_companies`
- `get_industry_benchmark`
- `get_peers`
- `compare_financials`
- `align_financial_periods`
- `compare_financial_fields`
- `get_watchlist`
- `update_watchlist`

## Shared Service Reuse

- security resolution: `security_entity_resolver`
- quote snapshot: `stock_data_service`
- Company profile / financial snapshot / history for Chat: `company_chat_data_service`
- Company V2 financial snapshot/history domain source: `company_v2_history_service`
- official reports: `official_report_domain_service`
- report evidence: `company_v2_report_evidence_service`
- structured report fields: `report_financial_table_extractor_tool`

## Boundary Rules

- Tools may call shared domain services.
- Tools do not call LLMs.
- Tools materialize DTOs and close DB sessions before returning.
- Agents consume only `ToolResponse`; they do not call repositories, providers, or SQLAlchemy sessions.
- Chat does not call its own HTTP endpoints.
