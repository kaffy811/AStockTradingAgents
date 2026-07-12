# Phase 6B — Free Mode Real Data Validation Report

**Date:** 2026-07-06  
**Phase:** 6B — BaoStock/AkShare Field Schema Mapping + ReportDocumentsPanel  
**Status:** Validated ✓

---

## Environment

| Setting | Value |
|---|---|
| DATA_MODE | `free` |
| ENABLE_BAOSTOCK | `true` |
| ENABLE_AKSHARE | `true` |
| ENABLE_REPORT_PDF | `true` |
| baostock version | 0.9.2 |
| akshare version | 1.18.62 |

---

## BaoStock Real Field Probe (2026-07-06)

BaoStock API field names verified against live API responses. Several mismatches with initial Phase 6A assumptions were found and corrected:

### Actual Field Names (vs. Initial Assumption)

| Module | BaoStock API fn | Field Corrected | Old Name | Actual Name |
|---|---|---|---|---|
| Dupont | `query_dupont_data` | Net profit/op income | `dupontNPI` | `dupontPnitoni` |
| Dupont | `query_dupont_data` | Equity multiplier | `dupontAssMul` | `dupontAssetStoEquity` |
| Dupont | `query_dupont_data` | Asset turnover | `dupontAssTurn` | `dupontAssetTurn` |
| Dupont | `query_dupont_data` | Tax burden | `dupontEbittax` | `dupontTaxBurden` |
| Cashflow | `query_cash_flow_data` | CFO/net profit | `CFOToOI` | `CFOToNP` |

### Unit Convention Fix

BaoStock returns profitability/growth metrics as **decimals** (e.g., `gpMargin: 0.926` = 92.6%), while Tushare returns them as **percentages** (e.g., `grossprofit_margin: 92.6`). All affected tool `fetch_baostock()` methods now multiply by 100:

| Module | Fields Multiplied ×100 |
|---|---|
| profitability | `gross_margin_pct`, `net_margin_pct`, `roe_pct` |
| growth | `net_profit_yoy_pct` |
| solvency | `debt_to_assets_pct` (already correct from Phase 6A) |
| dupont | `roe_pct` (×100); `net_margin_pct` computed from `dupontPnitoni × dupontNitogr × 100` |

---

## Live Data Validation — 3 Stocks × 6 Modules = 18 Calls

All tested via real BaoStock API (baostock 0.9.2) against live data:

| Stock | profitability | growth | solvency | operation | cashflow | dupont |
|---|---|---|---|---|---|---|
| 600519 (贵州茅台) | ✓ 6 rows | ✓ 6 rows | ✓ 6 rows | ✓ 6 rows | ✓ 6 rows | ✓ 2 rows |
| 000725 (京东方A) | ✓ 6 rows | ✓ 6 rows | ✓ 6 rows | ✓ 6 rows | ✓ 6 rows | ✓ 2 rows |
| 600186 (莲花控股) | ✓ 6 rows | ✓ 6 rows | ✓ 6 rows | ✓ 6 rows | ✓ 6 rows | ✓ 2 rows |

**Result: 18/18 HTTP 200 ✓ | source.actual = "baostock" ✓**

### Sample Values for 600519 (贵州茅台, 2026-Q1)

| Module | Field | Value |
|---|---|---|
| profitability | gross_margin_pct | 89.76% |
| profitability | net_margin_pct | 52.22% |
| profitability | roe_pct | 10.57% |
| growth | net_profit_yoy_pct | 1.37% |
| solvency | current_ratio | 7.06 |
| solvency | debt_to_assets_pct | 12.12% |
| dupont (2025-12-31) | roe_pct | 34.46% |
| dupont (2025-12-31) | equity_multiplier | 1.26 |

Values are consistent with publicly known Moutai financials ✓

---

## Field Schema Parity

| Panel | Required Fields | BaoStock Coverage | Notes |
|---|---|---|---|
| Profitability | end_date, gross_margin_pct, net_margin_pct, roe_pct | ✓ | roa_pct/roic_pct = null (no BaoStock source) |
| Growth | end_date, net_profit_yoy_pct | Partial | revenue/net_profit_parent = null; eps = null (growth table has no absolute EPS) |
| Solvency | end_date, debt_to_assets_pct, current_ratio, quick_ratio | ✓ | interest_coverage = null (no interest expense data) |
| Operation | end_date, inv_turn, ar_turn, assets_turn | ✓ | fa_turn/payable_turn = null |
| Cashflow | end_date, ocf_to_np, cash_sales_ratio | Partial | ocf (absolute) = null — BaoStock only provides ratios |
| Dupont | end_date, roe_pct, net_margin_pct, assets_turn, equity_multiplier | ✓ | debt_to_assets = null |

All null fields correctly render as `—` in the frontend (no crash) ✓

---

## ReportDocumentsPanel

- Created: `frontend/src/components/fundamentals/ReportDocumentsPanel.vue`
- Wired into `CompanyFundamentalsPanel.vue`:
  - ANCHOR_SECTIONS: added `{ id: 'report-documents', label: '年报文件', modules: ['report_documents'] }`
  - Section template added after Shareholders section
  - Import added

**Panel behavior:**
- `ENABLE_REPORT_PDF=false`: shows "功能未开启" notice (not a crash, not `partial=True` banner)
- `ENABLE_REPORT_PDF=true` + rows present: renders table with type badge, period_end, title, disclosure_date, parsed status, source_url link
- `ENABLE_REPORT_PDF=true` + rows empty: shows `FundamentalEmptyReason`
- Loading: skeleton animation

**Backend endpoint** (`GET /{market}/{symbol}/fundamentals/modules/report_documents`):
- Always HTTP 200
- Not enabled → `partial=True` + `ENABLE_REPORT_PDF` in `errors[]`
- Enabled but no data → empty `rows[]`

---

## Phase 6B Test Suite

**File:** `tests/fundamental/test_phase6b_free_mode_real_mapping.py`  
**Tests:** 17  
**Result:** 17/17 PASS

| Test | Description |
|---|---|
| test_profitability_baostock_decimal_to_pct | Verifies ×100 conversion for gross/net margin/ROE |
| test_growth_baostock_yoy_decimal_to_pct | Verifies ×100 for YOYNI; eps=None |
| test_solvency_baostock_debt_to_assets_pct | Verifies ×100 for liability_to_asset |
| test_dupont_baostock_field_names | Verifies corrected field names (dupontPnitoni etc.) |
| test_cashflow_baostock_cfo_to_np | Verifies CFOToNP → ocf_to_np (not CFOToOI) |
| test_fetch_with_fallback_free_mode_source | source.actual = "baostock" in free mode |
| test_free_mode_baostock_empty_falls_to_akshare | Graceful fallback chain |
| test_free_mode_both_empty_returns_err_envelope | Both fail → err_envelope |
| test_standard_mode_calls_tushare | Standard mode doesn't call BaoStock |
| test_get_available_modules_free_excludes_standard_only | analyst_ratings absent in free mode |
| test_to_bs_code_sh/sz/no_dot (×3) | Code conversion correctness |
| test_safe_float_handles_empty_string | BaoStock null/edge value handling |
| test_build_api_response_baostock_source | source.actual propagation |
| test_report_documents_not_enabled_returns_partial | Partial envelope when PDF disabled |
| test_profitability_panel_field_schema_parity | All panel-expected fields present |

---

## Known Gaps (BaoStock Coverage)

| Gap | Affected Field | Impact | Resolution |
|---|---|---|---|
| No absolute revenue | `growth.revenue`, `growth.net_profit_parent` | Growth bars show only YoY % (no absolute) | Frontend shows `—` gracefully |
| No absolute OCF | `cashflow_quality.ocf` | FCF/core profit ratio unavailable | Shows OCF ratio only |
| No interest expense | `solvency.interest_coverage` | Cannot compute IC | Shows `—` with explanation |
| No payables data | `operation_capability.payable_turn/days` | CCC unavailable | Shows `—` with explanation |
| Dupont: no D/A ratio | `dupont.debt_to_assets` | Missing leverage detail | Shows `—` |
| Dupont: quarterly only | Annual data derived from Q4 rows | Only 2 annual rows (vs 8 for Tushare) | Frontend handles ≥1 row |

---

## Regression Results

| Check | Result |
|---|---|
| Backend tests (pytest) | **2091/2091 PASS** |
| Frontend build | ✓ clean, 2.45s |
| Phase 6B tests | **17/17 PASS** |
| 18-module live probe | **18/18 HTTP 200** |
| source.actual = "baostock" | ✓ all 18 |
| Frontend renders null as `—` | ✓ (FundamentalEmptyReason) |

---

## Updated AkShare Validation Table

The following BaoStock modules now have real data validation. AkShare serves as fallback when BaoStock is empty.

| Module | 600519 | 000725 | 600186 | Field parity | Notes |
|---|---|---|---|---|---|
| profitability | ✓ 6 rows | ✓ 6 rows | ✓ 6 rows | Partial | roa/roic null |
| growth | ✓ 6 rows | ✓ 6 rows | ✓ 6 rows | Partial | revenue/eps null |
| solvency | ✓ 6 rows | ✓ 6 rows | ✓ 6 rows | Partial | interest_coverage null |
| operation_capability | ✓ 6 rows | ✓ 6 rows | ✓ 6 rows | Partial | payable fields null |
| cashflow_quality | ✓ 6 rows | ✓ 6 rows | ✓ 6 rows | Partial | OCF absolute null |
| dupont | ✓ 2 rows | ✓ 2 rows | ✓ 2 rows | Partial | D/A null |

**Phase 6B validation status:** ✓ Complete  
**DATA_MODE=free recommended for:** Development/demo environments without Tushare Pro subscription
