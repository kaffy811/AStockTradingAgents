CompanyV2 Staged Default Rollout

## Default Rules

- Development and staging default to `VITE_COMPANY_TAB_VERSION=v2`.
- Phase 6S production default is explicitly set to `VITE_COMPANY_TAB_VERSION=v2`.
- If production env is unset, frontend code still falls back safely; production deployments must set the env explicitly.
- `VITE_COMPANY_TAB_VERSION=v2` makes the Company tab render CompanyV2.
- `VITE_COMPANY_TAB_VERSION=legacy` keeps the legacy Company tab.
- `VITE_ENABLE_COMPANY_V2=true` remains a validation-only full-page side-by-side switch.
- Production default cutover is explicit: set `VITE_COMPANY_TAB_VERSION=v2`.

## Priority

1. URL query `company_v2=1` forces CompanyV2.
2. URL query `company_v2=0` forces legacy.
3. `VITE_ENABLE_COMPANY_V2=true` opens the full-page CompanyV2 validation path.
4. `VITE_COMPANY_TAB_VERSION=v2|legacy` controls the embedded Company tab.
5. Deployed production default after Phase 6S: `VITE_COMPANY_TAB_VERSION=v2`.

## URL Overrides

- `/stocks/CN/600519?company_v2=1` forces CompanyV2.
- `/stocks/CN/600519?company_v2=0` forces legacy.
- URL query takes priority over environment configuration.

## Rollback

1. Set `VITE_COMPANY_TAB_VERSION=legacy`.
2. Rebuild frontend with `npm run build`.
3. For single-page validation, append `?company_v2=0`.
4. Keep CompanyV2 debug API, logs, and snapshots for diagnosis.

One-line rollback config:

```bash
VITE_COMPANY_TAB_VERSION=legacy
```

Only `VITE_` variables are exposed to the client bundle. Do not place secrets in frontend environment variables.

## Production Gate

Production has switched to `VITE_COMPANY_TAB_VERSION=v2` after cutover gates passed. `company_v2=0` remains the runtime rollback path.

## Known Limitations

- `market_cap` requires share capital data.
- `roa` and `roic` may be absent in free public sources.
- Absolute `revenue` and `net_profit` depend on statement/PDF availability.
- PDF discovery requires reliable CNINFO/SSE/SZSE announcement access.
- Redis unavailable mode is fail-open and may use memory snapshots.

## Compliance

CompanyV2 presents diagnostic and financial data. It is not investment advice and must not output buy/sell instructions, target prices, or guaranteed upside.
