# CompanyV2 Legacy Company Tab Inventory

## Policy

Legacy Company Tab is frozen. It remains available only as a runtime fallback while CompanyV2 is staged and validated.

Status labels:

- `keep`: active CompanyV2 or rollout control surface.
- `migrate`: logic should move to CompanyV2 before legacy deletion.
- `freeze`: legacy code retained with no new feature work.
- `deprecate_later`: historical/optional surface retained during rollout.
- `remove_after_prod_cutover`: delete only after production v2 is stable and deletion criteria pass.

Allowed legacy changes:

- Security fixes.
- Crash fixes.
- Severe rollback blockers.

Not allowed in legacy:

- New data sources.
- New financial modules.
- Non-blocking UI polish.
- New field mapping work unless required for rollback safety.

## Frontend Legacy Entry Points

| File | Status | Notes |
| --- | --- | --- |
| `frontend/src/views/StockDetailView.vue` | keep | Runtime switch keeps both `CompanyV2View` and lazy legacy `CompanyFundamentalsPanel`; `company_v2=0` forces legacy. |
| `frontend/src/components/CompanyFundamentalsPanel.vue` | freeze | Legacy Company Tab root. Keep until production v2 is stable for a full regression cycle. |
| `frontend/src/components/CompanyFundamentalsToolbar.vue` | freeze | Legacy Company Tab toolbar. |
| `frontend/src/components/CompanyOverviewCards.vue` | freeze | Legacy overview cards. |
| `frontend/src/components/FundamentalModuleCard.vue` | freeze | Legacy generic module card. |
| `frontend/src/components/FundamentalModuleRenderer.vue` | freeze | Legacy module renderer. |
| `frontend/src/components/fundamentals/*.vue` | freeze | Legacy panel set; do not add new CompanyV2 functionality here. |
| `frontend/src/components/fundamentals/DataSourceBanner.vue` | deprecate_later | Legacy banner component. CompanyV2 must not use it; legacy auth/cache crash fixes are allowed. |
| `frontend/src/components/fundamentals/FundamentalFallbackTable.vue` | freeze | Legacy fallback table; CompanyV2 uses its own table. |
| `frontend/src/components/fundamentals/UnavailableModulesPanel.vue` | freeze | Legacy unavailable module list. |

## Frontend Legacy Data / Adapter Files

| File | Status | Notes |
| --- | --- | --- |
| `frontend/src/api/fundamentals.js` | freeze | Legacy fundamentals API client. CompanyV2 uses `frontend/src/api/companyV2.js`. |
| `frontend/src/utils/fundamentalAdapters.js` | freeze | Legacy render adapter. CompanyV2 uses DebugEnvelope `normalized/completion/render`. |
| `frontend/src/composables/*fundamental*` | freeze | Legacy helper surface if present. |

## Backend Legacy API / Tooling

| File | Status | Notes |
| --- | --- | --- |
| `backend/app/routers/fundamentals.py` | freeze | Legacy fundamentals routes. |
| `backend/app/routers/fundamentals_compat.py` | freeze | Legacy compatibility routes and diagnostics. |
| `backend/app/tools/fundamental/base.py` | freeze | Contains deprecated generic DATA_MODE fallback message; CompanyV2 must not call this for UI attribution. |
| `backend/app/tools/fundamental/*.py` | freeze | Legacy module tools with BaoStock/AkShare fallback comments/errors. |
| `backend/app/aggregator/envelope.py` | freeze | Legacy DataEnvelope flow. |

## CompanyV2 Primary Path

| File | Status | Notes |
| --- | --- | --- |
| `frontend/src/views/CompanyV2View.vue` | keep | Primary Company tab implementation in dev/staging. |
| `frontend/src/components/company-v2/*` | keep | Primary CompanyV2 UI components. |
| `frontend/src/api/companyV2.js` | keep | CompanyV2 debug API client. |
| `backend/app/routers/company_v2_debug.py` | keep | CompanyV2 debug API. |
| `backend/app/services/company_v2_debug_service.py` | keep | CompanyV2 orchestration, completion, render semantics. |
| `backend/app/services/company_v2_normalizers.py` | keep | CompanyV2 normalized mapping. |
| `backend/app/services/company_v2_debug_diagnosis_service.py` | keep | CompanyV2 diagnosis classifier. |
| `backend/app/services/company_v2_snapshot_cache_service.py` | keep | CompanyV2 debug snapshot cache. |

## Tests

| File / Pattern | Status | Notes |
| --- | --- | --- |
| `backend/tests/fundamental/test_phase6o*_company_v2*.py` | keep | CompanyV2 regression suite. |
| `frontend/src/tests/companyV2*.test.js` | keep | CompanyV2 source-level rollout tests. |
| `backend/tests/fundamental/test_phase6n*_*.py` | freeze | Legacy/free-mode regression tests; keep until deletion stage. |
| `test_stock_detail.py` | deprecate_later | Optional Playwright script; root pytest no longer collects it by default. |

## Docs

| File / Pattern | Status | Notes |
| --- | --- | --- |
| `backend/docs/artifacts/company_v2_*.md` | keep | Current CompanyV2 rollout/deprecation artifacts. |
| `docs/11_rc2_validation_report.md` | deprecate_later | Historical legacy Company Tab/DataSourceBanner validation. |
| `docs/12_release_notes_rc2.md` | deprecate_later | Historical legacy rollout notes. |
| `docs/13_akshare_fallback_validation_plan.md` | deprecate_later | Historical AkShare fallback plan. |
| `docs/14_zero_cost_data_strategy.md` | deprecate_later | Legacy free-mode strategy references. |
| `docs/27_phase6n8b_delivery_report.md` | deprecate_later | Legacy DataSourceBanner/free-mode error docs. |

## Feature Flags

| Flag | Status | Notes |
| --- | --- | --- |
| `VITE_COMPANY_TAB_VERSION=legacy|v2` | keep | Default Company tab version. Phase 6S production default is `v2`; `legacy` remains rollback config. |
| `company_v2=1` | keep | URL override to force CompanyV2. |
| `company_v2=0` | keep | URL override to force legacy rollback. |
| `VITE_ENABLE_COMPANY_V2=true` | deprecate_later | Full-page side-by-side override retained for validation. |
