# CompanyV2 Production Rollout Gate

CompanyV2 may become the production default only after all gate checks pass.

## Required Gate Checks

1. Dev/staging uses `VITE_COMPANY_TAB_VERSION=v2`.
2. Manual page acceptance completed for `600519`, `000725`, and `601686`.
3. Page scroll reaches `data-testid="company-v2-bottom-sentinel"`.
4. Browser console has no blocking errors.
5. Network panel has no 401 storm.
6. `summary.modules_renderable >= 10`.
7. `summary.providers_timeout = 0`, or timed-out providers have stale cache fallback.
8. `summary.baostock_aggregate_calls = 1`.
9. `report_documents` and `report_rag` empty states use `REPORT_PDF_NOT_FOUND` / `REPORT_NOT_INGESTED`, not OK.
10. CompanyV2 payload and UI do not contain the legacy generic DATA_MODE message.
11. `quote_overview`, `valuation`, `profitability`, `growth`, `cashflow_quality`, `solvency`, `operation_capability`, and `dupont` render data or show a specific reason.
12. `/stocks/CN/{symbol}?company_v2=0` falls back to legacy.
13. Production rollback is one frontend config change: `VITE_COMPANY_TAB_VERSION=legacy`.

## Production Cutover

Set:

```bash
VITE_COMPANY_TAB_VERSION=v2
```

Then rebuild and deploy the frontend bundle.

## Rollback

If CompanyV2 causes a production issue:

1. Set `VITE_COMPANY_TAB_VERSION=legacy`.
2. Rebuild and redeploy frontend.
3. For immediate single-session validation, use `?company_v2=0`.
4. Do not roll back database migrations.
5. Do not delete CompanyV2 debug cache.
6. Keep CompanyV2 debug API enabled for admin/dev diagnosis.
7. Preserve logs and snapshots.

## Incident Checklist

- Record affected symbol(s), market, user-visible symptom, request ID, and timestamp.
- Save `/api/v2/company/{market}/{symbol}/debug/full?include_raw=false` output.
- Check `summary.providers_timeout`, `summary.modules_renderable`, and diagnosis `primary_issue`.
- Confirm whether `company_v2=0` restores the legacy page.
- File a CompanyV2 issue with debug JSON evidence before changing mappings.

This document is a rollout gate only. It does not authorize deleting legacy code.
