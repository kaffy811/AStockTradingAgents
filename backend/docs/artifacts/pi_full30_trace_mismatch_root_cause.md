# P1.6.4 Full30 Trace Mismatch Root Cause (recomputed offline, 6V-P1.6.5)

- Trace mismatch cases (15): `A01, A02, A03, B01, B02, B03, B04, B05, B06, B07, C01, C02, C03, C04, C05`
- Raw diagnostics records retained: `33` (window starts 06:40:04Z; the A01–C05 records written 06:36–06:40 are absent)
- Foreign-execution records in the retained JSONL: `18` with statuses `{'skipped': 5, 'success': 9, 'clarification_required': 3, 'failed': 1}`
- DB corroboration: `49` pi-shadow sessions in the window, `16` duplicated case titles, `0` role-imbalanced sessions

## Root cause categories observed

1. **Diagnostics file replacement by an overlapping second acceptance execution** — the shared JSONL was recreated ~06:40 when a second execution started; the first execution's A01–C05 terminals were lost, so the analyzer found no terminal for those 15 trace ids.
   - affected_case_ids: A01,A02,A03,B01,B02,B03,B04,B05,B06,B07,C01,C02,C03,C04,C05
   - code_path: app/agent_runtime/shadow_diagnostics.py (single shared JSONL, no per-run identity file)
   - fix: per-shadow_run_id atomic record files with terminal exactly-once (`<path>.runs/<run_id>.json`)
   - regression_test: tests/fundamental/test_phase6v_p165_correlation.py::test_terminal_exactly_once_and_core_immutable_after_terminal
2. **Correlation not propagated at shadow task creation** — trace/run ids were generated inside the fire-and-forget task; the runner matched by conversation_id+query_hash+user_hash and could not verify run identity.
   - code_path: app/agents/chat_orchestrator.py `_schedule_pi_official_report_shadow`; scripts/pi_official_report_pdf_live_shadow_acceptance.py `_poll_shadow_diagnostic`
   - fix: X-Pi-Shadow-Correlation header → ContextVar → runner/sink; poll strictly by shadow_run_id
   - regression_test: test_same_query_different_case_not_confused / test_correlation_header_parse_whitelist_and_limits
3. **Skip results carried run_id=null** — `_skip_result` returned run_id=None, so 8 skipped cases had no run identity at all.
   - code_path: app/agent_runtime/shadow_runner.py `_skip_result`
   - fix: skip results always carry a run_id (correlation-supplied when available)
   - regression_test: test_skip_result_carries_run_id
4. **Concurrent duplicate execution contaminating measurement windows** — the second execution's session/message inserts landed inside the first execution's before/after windows (D01..F07): 33 'Pi business writes' and 22 'double writes' were all other-execution rows.
   - fix: acceptance_run_id + row-level owner attribution + serial-only (max_concurrency=1) execution
   - regression_test: test_other_case_writes_not_counted_into_pi_delta

Categories checked and **not** observed: retry reusing shadow_run_id, query-hash-only mismatch inside one execution, tool-event trace namespace divergence, cleanup mutating terminals.

Original P1.6.4 artifacts are preserved unmodified; this document only records the recomputed root cause.
