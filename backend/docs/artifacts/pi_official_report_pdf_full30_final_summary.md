# official_report_pdf_pi_v1 Full30 Final Summary

- Phase: `6V-P1.6.4`
- Environment: `local_live`
- Commit SHA: `e0dee3ebe133f74c3437748561e5476d74f10e6e`
- Manifest hash: `a913b31fd283841e048ca17d8e4afe93150d2cebe7818f14736fe92c2edd9434`
- Planned / executed / accepted: `30 / 30 / 10`
- Review / failed samples: `20 / 0`
- Scenario counts: `{'multi_turn_current_report': 3, 'explicit_company_name': 7, 'explicit_stock_code': 6, 'report_type': 5, 'ambiguity': 2, 'missing': 7}`
- Status match: `0.4333`
- Entity/year/type match: `1.0 / 1.0 / 1.0`
- Source/PDF URL match: `1.0 / 0.9667`
- Provenance completeness: `0.7`
- Clarification correctness: `0.4333`
- Deterministic LLM calls: `0`
- Tool call distribution: `{'0': 18, '1': 12}`
- Pi latency p50/p95 ms: `0.0 / 2768.4`
- Tool latency p50/p95 ms: `1046.0 / 2573.05`
- Resolver warm full scans / rebuilds: `0 / 0`
- Pi business writes / context mutations / double writes: `33 / 0 / 22`
- Terminal missing / diagnostics timeout / agent deadline exceeded: `15 / 0 / 2`
- Raw500/raw503: `0 / 0`
- Browser acceptance: `not_run`
- npm ci: `passed after lockfile commit e0dee3e`
- Backend full: `3379 passed, 15 skipped`
- Frontend: `679 passed`, build `passed`
- Shadow passed: `False`
- Recommended for next authorization: `False`
- Formal Pi path: `disabled`, `authorized_agents=[]`

## Blockers

- Full30 Gate thresholds were not met.
- status_match_rate below 99%.
- provenance_completeness_rate below 100%.
- pi_business_write_delta was non-zero.
- assistant_double_write_count was non-zero.
- browser acceptance not run because Full30 had core blockers.
