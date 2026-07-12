# CompanyV2 Phase 6S Post-Cutover Smoke

Run after setting production frontend config to:

```bash
VITE_COMPANY_TAB_VERSION=v2
```

Command:

```bash
python backend/scripts/company_v2_production_smoke_test.py \
  --symbols 600519,000725,601686 \
  --market CN \
  --include-raw false \
  --force-refresh false \
  --out-json backend/docs/artifacts/company_v2_production_smoke_summary_after_cutover.json \
  --out-md backend/docs/artifacts/company_v2_production_smoke_summary_after_cutover.md
```

## Pass Conditions

1. `smoke_gate_pass = true`.
2. Three representative symbols return HTTP 200.
3. `providers_data_success >= 1`.
4. `modules_renderable >= 8`.
5. `strong_failed_count = 0`.
6. `critical_validation_failures = 0`.
7. Semantic warnings are recorded but do not block cutover.
8. `company_v2=0` still opens legacy.

## Current Phase 6S Status

Post-cutover smoke has not been executed in this workspace because production config has not been changed here. Execute this command immediately after deployment.
