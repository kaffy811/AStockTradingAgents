# CompanyV2 Phase 6S Rollback Verification

Verify these URLs after production cutover:

1. Production default v2:
   - `/stocks/CN/600519`
2. Forced legacy:
   - `/stocks/CN/600519?company_v2=0`
3. Forced v2:
   - `/stocks/CN/600519?company_v2=1`

## Expected Results

1. Forced legacy opens the legacy Company Tab.
2. Forced v2 opens CompanyV2.
3. Legacy and CompanyV2 do not share UI state that corrupts either path.
4. Embedded CompanyV2 load failure still falls back to legacy.
5. Main page remains scrollable to the bottom sentinel.

## Rollback Procedure

```bash
VITE_COMPANY_TAB_VERSION=legacy
```

Then rebuild and redeploy frontend.

Backend DB rollback is not required. Redis or memory snapshot cache does not need clearing. Preserve debug artifacts and logs for incident review.
