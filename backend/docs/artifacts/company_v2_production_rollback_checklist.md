# CompanyV2 Production Rollback Checklist

## Rollback Triggers

Rollback CompanyV2 to legacy if any of these persist beyond quick triage:

1. CompanyV2 page cannot open.
2. `modules_renderable` broadly falls below 8.
3. `providers_timeout` rises sharply.
4. `/debug/full` p95 latency exceeds the rollout threshold.
5. Users cannot scroll to the bottom sentinel.
6. Browser console errors persist across representative stocks.
7. Core modules such as quote, valuation, profitability, growth, cashflow, solvency, operation, or dupont are missing without specific reason.
8. Legacy generic DATA_MODE text appears in CompanyV2.
9. Any safety, auth, or permission anomaly appears.

## Rollback Steps

1. Set:

```bash
VITE_COMPANY_TAB_VERSION=legacy
```

2. Rebuild and deploy the frontend bundle.
3. For temporary single-session rollback, use:

```text
/stocks/CN/600519?company_v2=0
```

4. Do not roll back database migrations.
5. Do not clear Redis or memory snapshot cache.
6. Keep CompanyV2 debug API enabled for admin/dev diagnosis.
7. Preserve debug snapshots, request IDs, frontend logs, and backend structured logs.
8. Record an incident report before changing mappings.

## Incident Report Fields

- Start/end time.
- Affected market/symbol(s).
- Frontend route and build version.
- `request_id`.
- `summary.providers_timeout`.
- `summary.modules_renderable`.
- `summary.baostock_aggregate_calls`.
- `summary.mapping_error_count`.
- `summary.render_rule_error_count`.
- `diagnosis.primary_issue` by module.
- Whether `company_v2=0` restored legacy.
- Screenshots or manual notes for scroll/console/network.
