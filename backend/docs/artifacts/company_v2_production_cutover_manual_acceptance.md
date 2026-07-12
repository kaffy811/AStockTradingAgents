# CompanyV2 Production Cutover Manual Acceptance

Environment:

- Date: 2026-07-09
- Frontend setting: `VITE_COMPANY_TAB_VERSION=v2`
- Phase 6S cutover sets production default to CompanyV2 through `VITE_COMPANY_TAB_VERSION=v2`; legacy remains available with `company_v2=0`.
- Browser automation status: blocked — browser runtime reported no available browsers (`agent.browsers.list() == []`).
- Local backend smoke: FastAPI started with `ENABLE_CREATE_ALL=false ENABLE_TUSHARE=false` for cutover API checks.
- Local frontend smoke: Vite started with `VITE_COMPANY_TAB_VERSION=v2`.

## Checklist Per Symbol

| Check | 600519 | 000725 | 601686 |
| --- | --- | --- | --- |
| Defaults to CompanyV2 | blocked: no browser | blocked: no browser | blocked: no browser |
| Page scrolls to bottom | blocked: no browser | blocked: no browser | blocked: no browser |
| Bottom sentinel visible | blocked: no browser | blocked: no browser | blocked: no browser |
| Console has no blocking error | blocked: no browser | blocked: no browser | blocked: no browser |
| Network has no 401 storm | blocked: no browser | blocked: no browser | blocked: no browser |
| `/debug/full` returns 200 | pass | pass | pass |
| `providers_timeout = 0` | fail: 3 | pass: 0 | pass: 0 |
| `modules_renderable >= 10` | fail: 7 | fail: 9 | fail: 7 |
| `baostock_aggregate_calls = 1` | pass | pass | pass |
| `quote_overview` displays | API evidence only | API evidence only | API evidence only |
| `valuation` displays | API evidence only | API evidence only | API evidence only |
| `profitability` displays | API evidence only | API evidence only | API evidence only |
| `growth` displays | API evidence only | API evidence only | API evidence only |
| `cashflow_quality` displays | API evidence only | API evidence only | API evidence only |
| `solvency` displays | API evidence only | API evidence only | API evidence only |
| `operation_capability` displays | API evidence only | API evidence only | API evidence only |
| `dupont` displays | API evidence only | API evidence only | API evidence only |
| `report_documents` empty state semantic is correct | pass: `REPORT_PDF_NOT_FOUND` | pass: `REPORT_PDF_NOT_FOUND` | pass: `REPORT_PDF_NOT_FOUND` |
| `report_rag` empty state semantic is correct | pass: `REPORT_PDF_NOT_FOUND` | pass: `REPORT_PDF_NOT_FOUND` | pass: `REPORT_PDF_NOT_FOUND` |
| `company_v2=0` returns legacy | blocked: no browser | blocked: no browser | blocked: no browser |

## Notes

- Do not infer data availability from UI labels alone; use DebugPanel JSON and `/debug/full`.
- Do not treat report/RAG empty as OK.
- Do not treat BaoStock/history close as real-time price.
- Record request IDs for failures.

## Result

Not passed for production cutover. Browser/manual validation is blocked by unavailable browser automation in this environment, and local API smoke did not meet `modules_renderable >= 10` for all three symbols. Use a real dev/staging browser and the normal network/provider environment before production cutover.

## Local API Smoke Summary

| Symbol | HTTP | providers_timeout | modules_renderable | baostock_aggregate_calls | mapping_error_count | report_pdf_not_found_count |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 600519 | 200 | 3 | 7 | 1 | 1 | 1 |
| 000725 | 200 | 0 | 9 | 1 | 0 | 2 |
| 601686 | 200 | 0 | 7 | 1 | 0 | 2 |
