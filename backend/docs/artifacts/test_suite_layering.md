# Test Suite Layering

Phase 6U-E1.1 separates local deterministic tests from live external tests.

## Markers

- `unit`: hermetic unit tests with no external services.
- `integration_local`: local integration tests using fakes, in-memory stores, or local-only resources.
- `integration_live`: tests requiring configured live services.
- `live_external`: tests requiring external network, DNS, Supabase, CNINFO, BaoStock, or live RAG worker.
- `soak`: long-running soak/stress tests.
- `live_supabase`: legacy marker for Supabase-backed tests; treated as `integration_live` + `live_external`.

## Commands

Default local suite:

```bash
pytest -q
```

Live integration suite:

```bash
pytest -q -m integration_live
```

External network suite:

```bash
pytest -q -m live_external
```

Soak suite:

```bash
pytest -q -m soak
```

## Default Exclusions

`pytest -q` skips tests marked `integration_live`, `live_external`, `live_supabase`, or `soak`.

These tests must not wait for DNS, Supabase pooler, CNINFO, BaoStock, or live RAG worker timeouts in the default suite.

## Current Live External Classification

The former 15 default failures are now classified as live external:

- `test_phase6tj1_*` database RAG repository persistence tests: live Supabase/RAG DB.
- `test_phase6tr_worker_foundation_live.py`: live Supabase worker claim/lease tests.
- `test_phase6ts_shadow_soak_live.py`: live Supabase shadow soak/restart tests.

They should be run only in an environment with configured live external dependencies.
