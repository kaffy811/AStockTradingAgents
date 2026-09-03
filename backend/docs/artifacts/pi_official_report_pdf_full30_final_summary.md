# official_report_pdf_pi_v1 Full30 Final Summary

- Phase: `6V-P1.6.6`
- Environment: `local_live`
- Commit SHA: `086083186d49f89368b3dabcc91c3713a92a951d`
- Manifest hash: `68c3c9d1221ddd7939ce42805ace239222175cd569f91c382d75243c10761518`
- Execution: `serial (max_concurrency=1)` with correlation envelope + per-run diagnostics
- Planned / executed / accepted: `30 / 30 / 15`
- Review / failed samples: `15 / 0`
- Status match: `0.6333`
- Entity/year/type match: `1.0 / 1.0 / 1.0`
- Source/PDF URL match: `1.0 / 0.8667`
- Status-specific provenance completeness: `1.0`
- Safety correctness: `1.0`
- Clarification applicable/correct: `2 / 2` (rate `1.0`)
- Trace mismatch / terminal missing / stale ignored: `0 / 0 / 0`
- Pi business writes / double writes / unknown writes / other-case writes: `0 / 0 / 0 / 0`
- Deadline expected/unexpected: `0 / 0`
- Deterministic LLM calls: `0`
- raw500/raw503: `0 / 0`
- Resolver warm full scans / rebuilds: `0 / 0`
- Pi latency p50/p95 ms: `933 / 1444`
- Browser acceptance: `not_run` (requires authenticated manual browser session)
- Shadow passed: `False`
- Recommended for next authorization: `False`
- Formal Pi path: `disabled`, `authorized_agents=[]`

## Blockers

- status_match_rate below 99% threshold: 15 review cases are documented safe behavior differences (Pi unsupported/unavailable vs Legacy claimed success; Legacy wrong-year documents on B02/B05/C05/F07).
- browser acceptance not_run: requires an authenticated manual browser session.

## Review cases (documented safe behavior differences)

| Case | Legacy | Pi | Reason |
| --- | --- | --- | --- |
| B02 | success | success | pdf_url_mismatch |
| B05 | success | success | pdf_url_mismatch |
| C05 | success | success | pdf_url_mismatch |
| D01 | success | unsupported | status_mismatch legacy=success pi=unsupported (pi_safe) |
| D02 | success | unsupported | status_mismatch legacy=success pi=unsupported (pi_safe) |
| D03 | success | unsupported | status_mismatch legacy=success pi=unsupported (pi_safe) |
| D04 | success | unsupported | status_mismatch legacy=success pi=unsupported (pi_safe) |
| D05 | success | unsupported | status_mismatch legacy=success pi=unsupported (pi_safe) |
| F01 | success | unavailable | status_mismatch legacy=success pi=unavailable (pi_safe) |
| F02 | success | unavailable | status_mismatch legacy=success pi=unavailable (pi_safe) |
| F03 | success | unavailable | status_mismatch legacy=success pi=unavailable (pi_safe) |
| F04 | success | unavailable | status_mismatch legacy=success pi=unavailable (pi_safe) |
| F05 | success | unavailable | status_mismatch legacy=success pi=unavailable (pi_safe) |
| F06 | success | unavailable | status_mismatch legacy=success pi=unavailable (pi_safe) |
| F07 | success | success | pdf_url_mismatch |
