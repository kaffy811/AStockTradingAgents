# CompanyV2 Production Cutover Checklist

## Pre-Cutover

- [ ] `pytest -q` passes from repo root.
- [ ] `cd frontend && npm run test` passes.
- [ ] `cd frontend && npm run build` passes.
- [ ] Root pytest does not collect legacy Playwright scripts as unit tests.
- [ ] Manual browser acceptance passes for `600519`, `000725`, and `601686`.
- [ ] Production env is checked.
- [ ] Rollback env is checked.
- [ ] Rollout, monitoring, rollback, and deprecation docs are updated.
- [ ] Debug responses do not expose secret/token/local_path.
- [ ] CompanyV2 source/payload contains no target price, analyst rating, buy/sell, or guaranteed-upside wording.
- [ ] Legacy Company Tab remains accessible with `company_v2=0`.

## Cutover

1. Set:

```bash
VITE_COMPANY_TAB_VERSION=v2
```

2. Build frontend:

```bash
npm run build
```

3. Deploy frontend bundle.
4. Smoke test:
   - `/stocks/CN/600519`
   - `/stocks/CN/000725`
   - `/stocks/CN/601686`
5. Confirm rollback URL works:
   - `/stocks/CN/600519?company_v2=0`

## Post-Cutover

- [ ] Monitor 24–48 hours.
- [ ] Check `providers_timeout`.
- [ ] Check `modules_renderable`.
- [ ] Check user-reported scroll issues.
- [ ] Check console/network errors.
- [ ] Keep legacy available.
- [ ] Do not delete legacy yet.

## Cutover Hold Conditions

- Browser acceptance cannot be completed.
- `modules_renderable` drops below 10 on representative symbols.
- `providers_timeout` persists without stale fallback.
- Any old legacy DATA_MODE message appears in CompanyV2.
- `company_v2=0` rollback fails.
