# CompanyV2 Post-Cutover Observation

Phase 6S production default target:

```bash
VITE_COMPANY_TAB_VERSION=v2
```

Legacy Company Tab remains available with `company_v2=0`.

## First Observation Snapshot

Source artifacts:

- `backend/docs/artifacts/company_v2_production_smoke_summary.json`
- `backend/docs/artifacts/company_v2_production_smoke_summary_after_cutover.json`
- `backend/docs/artifacts/company_v2_daily_health_20260709.json`
- `backend/docs/artifacts/company_v2_cutover_readiness_report.json`

| Symbol | Page Open | Scroll Bottom | Provider Data | Provider Timeout | Modules | Quality | Semantic Warnings | Strong Fail | Critical | Rollback |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 600519 | API smoke pass | manual/browser pending | 8 | 0 | 9 | 89 | 2 | 0 | 0 | `company_v2=0` documented |
| 000725 | API smoke pass | manual/browser pending | 8 | 0 | 9 | 94 | 2 | 0 | 0 | `company_v2=0` documented |
| 601686 | API smoke pass | manual/browser pending | 8 | 0 | 9 | 84 | 2 | 0 | 0 | `company_v2=0` documented |

## Observation Status

`stable`

Rationale:

- `modules_renderable >= 8`
- `providers_data_success >= 1`
- `strong_failed_count = 0`
- `critical_validation_failures = 0`
- smoke gate passed
- daily health `pass_count=3`, `fail_count=0`
- rollback route remains documented and available

## Watch Items

- `semantic_warning_count = 6` across the representative three symbols.
- Browser/manual page-open and scroll-bottom verification should be repeated in the deployed production environment.

## Rollback Recommended

`false`

Rollback triggers remain:

- Page cannot open.
- Page cannot scroll.
- `providers_data_success = 0`.
- `modules_renderable < 8`.
- `strong_failed_count > 0`.
- `critical_validation_failures > 0`.
- Forbidden legacy DATA_MODE message reappears.
- `company_v2=0` cannot open legacy.

## Rollback Steps

1. Set `VITE_COMPANY_TAB_VERSION=legacy`.
2. Rebuild frontend.
3. Redeploy frontend.
4. Backend DB rollback is not required.
5. Redis/cache does not need clearing.
6. Preserve debug artifacts and logs.
