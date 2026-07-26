# CompanyV2 Phase 6S Pre-Cutover Gate

Production default must remain legacy unless every gate item passes.

## Required Checks

1. `pytest -q` passes.
2. `npm run test` passes.
3. `npm run build` passes.
4. Production smoke test passes.
5. Daily health `pass_count >= 3`.
6. Daily health `fail_count = 0`.
7. `providers_data_success >= 1`.
8. `modules_renderable >= 8`.
9. `strong_failed_count = 0`.
10. `critical_validation_failures = 0`.
11. `data_quality_score >= 70`.
12. `mapping_error_count = 0`.
13. `render_rule_error_count = 0`.
14. `trace_missing_count = 0`.
15. No forbidden legacy DATA_MODE message.
16. No restricted investment-advice wording.
17. `company_v2=0` rollback route verified.
18. Legacy Company Tab remains accessible.

## Failure Policy

If any item fails:

1. Do not switch production default to CompanyV2.
2. Keep `VITE_COMPANY_TAB_VERSION=legacy`.
3. Output `failure_reasons`.
4. Keep artifacts/logs for diagnosis.
