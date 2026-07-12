# CompanyV2 Legacy Company Tab Deprecation Plan

## Current State

- Dev/staging default: CompanyV2.
- Production default: legacy unless explicitly configured.
- Legacy Company Tab remains available through `company_v2=0`.
- CompanyV2 remains available through `company_v2=1`.

## Legacy Freeze Policy

Legacy is frozen and is no longer the main development path.

Allowed:

- Security fixes.
- Crash fixes.
- Severe production rollback blockers.

Not allowed:

- New data source integrations.
- New financial modules.
- Non-blocking UI polish.
- New field mapping work that only benefits legacy.

All new Company Tab work goes to CompanyV2.

## Staged Rollout

1. Keep `VITE_COMPANY_TAB_VERSION=v2` in development/staging.
2. Validate representative symbols: `600519`, `000725`, `601686`.
3. Confirm scroll, console, network, module renderability, source-chain visibility, and rollback URL.
4. Keep production at `legacy` until the production rollout gate passes.

## Production Cutover Conditions

Production may switch to CompanyV2 when:

1. Dev/staging v2 completes manual acceptance for representative symbols.
2. Page can scroll to bottom sentinel.
3. Browser console has no blocking errors.
4. Network has no 401 storm.
5. `modules_renderable >= 10`.
6. `providers_timeout = 0` or stale fallback is used.
7. `baostock_aggregate_calls = 1`.
8. Report/PDF/RAG empty states are semantically correct.
9. No legacy generic DATA_MODE message appears in CompanyV2.
10. Core modules render data or provide exact reasons.
11. `company_v2=0` successfully rolls back to legacy.
12. Rollback requires only setting `VITE_COMPANY_TAB_VERSION=legacy` and rebuilding.

## Rollback Plan

Use runtime rollback before code rollback:

```bash
VITE_COMPANY_TAB_VERSION=legacy
```

or per URL:

```text
/stocks/CN/600519?company_v2=0
```

Rollback notes:

- No database migration rollback is needed.
- Do not delete CompanyV2 cache.
- Keep debug logs and snapshots.
- Use CompanyV2 debug API to diagnose the incident after rollback.

## Legacy Deletion Criteria

Do not delete legacy until all criteria pass:

1. Production default v2 is stable for at least one complete regression cycle.
2. Representative and broader sample stocks pass page acceptance.
3. No known user workflow depends on legacy.
4. Playwright or a documented manual browser acceptance flow is fixed in CI/QA.
5. CompanyV2 report/PDF/RAG empty states are stable.
6. Repo tests no longer need legacy-specific exceptions.
7. Docs are updated to remove legacy as a runtime fallback.
8. Rollback strategy changes from runtime legacy to git revert.
9. A final archive tag is created before deletion.

## Known Limitations

- `market_cap` and `float_market_cap` depend on share capital availability.
- `roa` and `roic` may still be missing from free public sources.
- Absolute `revenue` and `net_profit` depend on financial statements, PDF extraction, or additional sources.
- PDF discovery requires reliable announcement/report discovery.
- Redis unavailable mode falls back to memory/fail-open behavior.

## Compliance

CompanyV2 is a research/data diagnostics view. It must not output buy/sell instructions, target prices, guaranteed upside, or investment recommendations.
