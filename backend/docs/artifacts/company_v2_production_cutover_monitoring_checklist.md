# CompanyV2 Production Cutover Monitoring Checklist

Legacy Company Tab remains available throughout cutover. Do not delete legacy during this phase.

## Pre-Cutover

1. `pytest -q` pass.
2. `npm run test` pass.
3. `npm run build` pass.
4. Production smoke test pass.
5. Semantic warnings documented.
6. Rollback env ready.
7. Legacy fallback verified.
8. CompanyV2 debug/full latency acceptable.
9. No forbidden legacy DATA_MODE message.
10. No restricted investment-advice wording.
11. `strong_failed_count = 0`.
12. `critical_validation_failures = 0`.

## Cutover

1. Set `VITE_COMPANY_TAB_VERSION=v2`.
2. Build frontend.
3. Deploy.
4. Run smoke test.
5. Open `/stocks/CN/600519`, `/stocks/CN/000725`, `/stocks/CN/601686`.
6. Confirm `company_v2=0` rollback works.
7. Confirm logs show `company_v2_debug_full_completed`.

## Post-Cutover 24-48h

1. Monitor provider timeout.
2. Monitor `modules_renderable`.
3. Monitor `data_quality_score`.
4. Monitor semantic warning trend.
5. Monitor fallback-to-legacy count.
6. Monitor frontend console/page errors.
7. Keep legacy available.
8. Do not delete legacy.

## Rollback Triggers

1. `modules_renderable < 8` for representative stocks.
2. `providers_data_success = 0`.
3. debug/full p95 `> 30s`.
4. `strong_failed_count > 0` across several symbols.
5. `critical_validation_failures > 0`.
6. Frontend page cannot scroll.
7. Forbidden legacy DATA_MODE message reappears.
8. User-visible page crash.
9. Repeated fallback-to-legacy.

## Rollback Steps

1. Set `VITE_COMPANY_TAB_VERSION=legacy`.
2. Rebuild/deploy frontend.
3. Use `company_v2=0` for immediate diagnostic rollback.
4. Backend DB rollback is not required.
5. Preserve artifacts/logs.
6. Create incident report.
