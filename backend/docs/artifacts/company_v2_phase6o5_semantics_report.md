CompanyV2 Phase 6O-5 Semantics Polish Report

## Staged Default

- Development/staging default: `VITE_COMPANY_TAB_VERSION=v2`.
- Production default: `legacy` when the variable is unset.
- URL override remains highest priority:
  - `company_v2=1` forces CompanyV2.
  - `company_v2=0` forces legacy.

## Semantics Fixes

- `report_documents`:
  - `documents_count > 0` is renderable.
  - `documents_count == 0` returns `REPORT_PDF_NOT_FOUND` and is not shown as OK.
- `report_rag`:
  - `chunks_count > 0` and `embedding_count > 0` are required for OK.
  - `documents_count > 0` with zero chunks/embeddings returns `REPORT_NOT_INGESTED`.
  - `documents_count == 0` returns `REPORT_PDF_NOT_FOUND`.
- `ai_analysis_status`:
  - Structured data summary is separated from report RAG availability.
- Quote fallback:
  - Real-time source labels price as `最新价`.
  - BaoStock/history fallback labels price as `最近收盘价`.
- Financial ratios:
  - Backend keeps raw normalized values.
  - Backend adds `raw_value`, `display_value`, and `display_type`.
  - Percent fields are displayed as percent strings.

## Three-Stock Page Acceptance Baseline

The user-provided manual text acceptance remains the baseline for page-level module counts:

| Symbol | providers_success | providers_timeout | modules_renderable | modules_unavailable | baostock_aggregate_calls |
| --- | ---: | ---: | ---: | ---: | ---: |
| 600519 | 4 | 0 | 11 | 0 | 1 |
| 000725 | 10 | 0 | 11 | 0 | 1 |
| 601686 | 10 | 0 | 11 | 0 | 1 |

Phase 6O-5 did not re-query public data providers. The after-mapping snapshots remain available for field-level comparison, while report/RAG semantic changes are covered by focused regression tests.

## Validation

- `pytest backend/tests/fundamental/test_phase6o5_company_v2_semantics_polish.py -q`: passed.
- `pytest -q` from `backend/`: passed.
- `npm run test`: passed.
- `npm run build`: passed.
