# Financial Agent Shadow Summary

- Mode: `hermetic_contract`
- Shadow sample count: `23`
- Intent match: `1.0`
- Entity match: `1.0`
- Unsupported numeric facts: `0`
- Context corruption: `0`
- Message double write: `0`
- Default full local passed: `True`
- Layered enabled: `False`

## Gate Decision

`do_not_enable_layered_v1`

## Blockers

- real_legacy_vs_layered_shadow_not_run
- browser_acceptance_not_recorded
- live_security_master_sampling_not_run
- full_backend_live_external_tests_are_excluded_from_default_and_require_separate_environment

This artifact is a contract gate, not a live browser acceptance report.
