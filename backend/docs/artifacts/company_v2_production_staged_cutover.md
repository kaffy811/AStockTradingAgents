# CompanyV2 Production Staged Cutover

CompanyV2 production cutover is controlled by frontend environment configuration and URL overrides. Legacy Company Tab remains available as the rollback path.

## Production Configurations

### Legacy Default

```bash
VITE_COMPANY_TAB_VERSION=legacy
```

This keeps the legacy Company Tab as production default.

### CompanyV2 Production Default

```bash
VITE_COMPANY_TAB_VERSION=v2
```

This is the Phase 6S production default. It only affects the Company Tab; top quote cards, K-line chart, news, peers, and other tabs are unchanged.

### URL Overrides

- `company_v2=0`: force legacy rollback for the current URL.
- `company_v2=1`: force CompanyV2 validation path for the current URL.

URL overrides have higher priority than `VITE_COMPANY_TAB_VERSION`.

## Staged Rollout Levels

### Level 0: Legacy Only
- `VITE_COMPANY_TAB_VERSION=legacy`
- `company_v2=1` is used only for debugging.

### Level 1: Dev/Staging Default V2
- Dev/staging default to CompanyV2.
- Production remains legacy.

### Level 2: Production Opt-In V2
- Production default remains legacy.
- Specific sessions use `company_v2=1`.

### Level 3: Production Default V2
- `VITE_COMPANY_TAB_VERSION=v2`
- `company_v2=0` remains available for rollback.
- This is the Phase 6S achieved level.

### Level 4: Legacy Deprecated Runtime Fallback
- Enter only after a stable production observation window.
- Legacy remains runtime fallback.
- No code deletion in Phase 6S.

## Safety Rules

- Do not hardcode production default v2 in frontend code.
- Do not place secrets in `VITE_` variables.
- Keep legacy route and runtime fallback available.
- Keep debug artifacts and logs after cutover.
