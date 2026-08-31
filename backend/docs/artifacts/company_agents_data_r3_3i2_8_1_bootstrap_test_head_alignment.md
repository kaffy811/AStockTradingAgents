# Phase 6W-R3.3I.2.8.1 — Bootstrap Test Head Alignment

## Result

`BOOTSTRAP_TEST_HEAD_ALIGNMENT_READY`

Traffic remains `HOLD_1_PERCENT`.

## Assertion audit

The previous assertion at `backend/tests/test_phase6w_r3_3i2_7_2_portable_bootstrap.py:122` compared `alembic current` and `alembic heads` with the literal historical revision `q5r6s7t8u9v0`. Its only purpose was to prove that root-to-head and repeat-upgrade reached the graph's current head; no business contract requires q5 to remain the final revision.

The integrated graph legitimately adds trace-input revision `r6s7t8u9v0w1` after q5. Actual migrations completed successfully, so the literal assertion represented test contract drift.

## Minimal test-only repair

The test now builds an Alembic `Config`, resolves the real revision map through `ScriptDirectory.from_config(config).get_heads()`, and requires exactly one head. Multiple heads fail explicitly with the full resolved tuple. It then requires both CLI outputs to equal the resolved head:

```text
alembic current == resolved single head
alembic heads   == resolved single head
```

No migration implementation, Agent code, dependency, Docker configuration, or runtime behavior changed.

## Dual-graph verification

| Graph | Resolved head | DB current | Result |
|---|---|---|---|
| bootstrap + vector compatibility | `q5r6s7t8u9v0` | `q5r6s7t8u9v0` | pass |
| bootstrap + vector compatibility + trace provenance | `r6s7t8u9v0w1` | `r6s7t8u9v0w1` | pass |

Both graphs used isolated standard PostgreSQL and pgvector databases. The same test source was applied byte-for-byte to both clean worktrees.

## Preserved substantive contracts

- All eight legacy tables remain required before the 3a analysis migration.
- The versioned existing-schema fixture and sentinel-preservation assertion remain unchanged.
- Root-to-head and repeat-upgrade remain mandatory.
- Standard PostgreSQL in both graphs produced TEXT for a2/g5 and no vector HNSW indexes.
- pgvector PostgreSQL in both graphs produced VECTOR(1536), VECTOR(384), and both expected HNSW indexes.
- No test was skipped and no assertion was removed.

## Test results

| Command | Collected | Passed | Failed | Skipped | Duration |
|---|---:|---:|---:|---:|---:|
| bootstrap-only graph: `pytest -q --durations=0 ...portable_bootstrap.py` | 9 | 9 | 0 | 0 | 4.81s |
| integrated graph: `pytest -q --durations=0 ...portable_bootstrap.py` | 9 | 9 | 0 | 0 | 4.72s |

Each run emitted two Alembic configuration deprecation warnings about absent `path_separator`; these are non-failing and unrelated to the head-alignment assertion.

## Safety statement

No production database, container, Supabase instance, or data was accessed or modified. No push, merge, deployment, production migration, or traffic expansion occurred. Traffic remains `HOLD_1_PERCENT`.
