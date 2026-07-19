# official_report_pdf Pi Blocker Subset Summary (6V-P1.6.5)

- Mode: `blocker_subset` (not a formal Full30)
- Acceptance run: `acc_99739f63b615`
- Commit SHA: `dd2082b5391c60320727254065401656d61733e2`
- Manifest hash: `b92cef60132038f66d7b024a6647123c8aa2660db1f95bd08aac73e3413c47a0`
- Planned / executed / accepted / review / failed: `26` / `26` / `14` / `12` / `0`
- Trace mismatch / terminal missing: `0` / `0`
- Pi business writes / double writes / unknown writes / other-case writes: `0` / `0` / `0` / `0`
- Status match: `0.6923`; safety correctness: `1.0`
- Clarification applicable/correct: `2` / `2` (rate `1.0`)
- Status-specific provenance completeness: `1.0`
- Deadline expected/unexpected: `0` / `0`
- raw500/raw503: `0` / `0`
- Subset passed: `True`
- Recommended to retry Full30: `True`
- Formal Pi path remains disabled: `pi_executor_enabled=false`, `authorized_agents=[]`, decision `do_not_enable_pi_compatible`.

| Case | Type | Decision | Legacy | Pi(norm) | TraceMatch | PiWrites | DoubleWrites | Prov |
| --- | --- | --- | --- | --- | --- | ---: | ---: | --- |
| A01 | multi_turn_current_report | pass | success | success | True | 0 | 0 | True |
| A02 | multi_turn_current_report | pass | success | success | True | 0 | 0 | True |
| A03 | multi_turn_current_report | pass | success | success | True | 0 | 0 | True |
| B01 | explicit_company_name | pass | success | success | True | 0 | 0 | True |
| B02 | explicit_company_name | review | success | success | True | 0 | 0 | True |
| B03 | explicit_company_name | pass | success | success | True | 0 | 0 | True |
| B04 | explicit_company_name | pass | unavailable | unavailable | True | 0 | 0 | True |
| B05 | explicit_company_name | review | success | success | True | 0 | 0 | True |
| B06 | explicit_company_name | pass | unavailable | unavailable | True | 0 | 0 | True |
| B07 | explicit_company_name | pass | unavailable | unavailable | True | 0 | 0 | True |
| C01 | explicit_stock_code | pass | success | success | True | 0 | 0 | True |
| C02 | explicit_stock_code | pass | success | success | True | 0 | 0 | True |
| C03 | explicit_stock_code | pass | success | success | True | 0 | 0 | True |
| C04 | explicit_stock_code | pass | unavailable | unavailable | True | 0 | 0 | True |
| C05 | explicit_stock_code | review | success | success | True | 0 | 0 | True |
| D01 | report_type | review | success | unsupported | True | 0 | 0 | True |
| D02 | report_type | review | success | unsupported | True | 0 | 0 | True |
| D03 | report_type | review | success | unsupported | True | 0 | 0 | True |
| D04 | report_type | review | success | unsupported | True | 0 | 0 | True |
| D05 | report_type | review | success | unsupported | True | 0 | 0 | True |
| E01 | ambiguity | pass | clarification_required | clarification_required | True | 0 | 0 | True |
| E02 | ambiguity | pass | clarification_required | clarification_required | True | 0 | 0 | True |
| F02 | missing | review | success | unavailable | True | 0 | 0 | True |
| F04 | missing | review | success | unavailable | True | 0 | 0 | True |
| F05 | missing | review | success | unavailable | True | 0 | 0 | True |
| F07 | missing | review | success | success | True | 0 | 0 | True |
