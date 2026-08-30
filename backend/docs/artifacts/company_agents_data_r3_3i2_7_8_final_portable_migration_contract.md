# Phase 6W-R3.3I.2.7.8 — Final Portable Migration Contract Closure

## Result

`FULL_PORTABLE_MIGRATION_CONTRACT_READY`

Traffic remains `HOLD_1_PERCENT`.

## Workspace and commit boundary

- Baseline: `b055da8495c54bb37625f0b0e0f94b4d4a627de2` (`release/demo-staging`).
- Isolated worktree: `/private/tmp/tradingagents-r33i2-7-8-final`.
- Isolated branch: `r33i-final-portable-migration-contract`.
- Original vector commits, replayed without modification and in order:
  - `4d366ce5bf00406b24b2a90ddeb132e4ae8c46df` (replay `242606c`): transaction-safe a2 capability fallback.
  - `3982f7851d95c0b762b9e7c967e8c79d8b308742` (replay `b05d253`): f4 database capability selection.
  - `33de17f6a3579dc5bd0fe6a0683c761072fe3de6` (replay `c33131f`): g5 database capability and data contract.
- Bootstrap-only pending changes before the final commit:
  - `backend/alembic/versions/2026_05_29_0001-r3e4f5g6h7i8_bootstrap_legacy_schema.py`
  - `backend/alembic/versions/2026_05_30_1612-4b49004d01a6_baseline_existing_schema.py`
  - `backend/tests/test_phase6w_r3_3i2_7_2_portable_bootstrap.py`
  - this artifact and `HKNA/update_report/update_110.md`.
- Excluded: Agent code, Dockerfile, `main.py`, embedding provider, `pyproject.toml`, `uv.lock`, production resources, and all main-worktree historical dirty files.

## Bootstrap contract

- `r3e4f5g6h7i8` is the new Alembic root (`down_revision = None`).
- Existing-schema baseline `4b49004d01a6` now follows `r3e4f5g6h7i8`.
- The bootstrap creates only absent legacy tables and never drops, truncates, replaces, or populates them.
- Eight required tables are present before `3a2f8b4c1d9e`: `app_users`, `analysis_reports`, `watchlist_items`, `industry_master`, `stock_industry_map`, `industry_hot_stock_snapshot`, `company_v2_report_rag_documents`, and `company_v2_report_rag_chunks`.
- Downgrade is deliberately non-destructive and leaves legacy data intact.

## Isolated database identities

| Scenario | Container | Image ID | Database | Start | Target |
|---|---|---|---|---|---|
| A standard / empty | `9d81f07758884d8a47ee5e866f2983e6a72239dab7c9bf7eb2ecb855f437ca8b` | `sha256:57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777` | `r33i_empty` on localhost:15450 | root | `q5r6s7t8u9v0` |
| B standard / fixture | same standard container | same | `r33i_fixture` on localhost:15450 | `r3e4f5g6h7i8` fixture | `q5r6s7t8u9v0` |
| C pgvector / empty | `e3762603c895c1a465c936deb4db118f7e62e1a064c97554927538b758742a72` | `sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b` | `r33i_empty` on localhost:15451 | root | `q5r6s7t8u9v0` |
| D pgvector / fixture | same pgvector container | same | `r33i_fixture` on localhost:15451 | `r3e4f5g6h7i8` fixture | `q5r6s7t8u9v0` |

Both containers use Docker-managed data volumes only; there is no source bind mount. They are isolated localhost test services and are not production databases.

## Four-scenario results

| Check | A | B | C | D |
|---|---|---|---|---|
| root/fixture → head | pass | pass | pass | pass |
| head → head | pass | pass | pass | pass |
| current == heads | `q5r6s7t8u9v0` | `q5r6s7t8u9v0` | `q5r6s7t8u9v0` | `q5r6s7t8u9v0` |
| legacy tables before 3a | 8/8 | 8/8 | 8/8 | 8/8 |
| a2 final type / index | TEXT / none | TEXT / none | VECTOR(1536) / HNSW | VECTOR(1536) / HNSW |
| f4→g5 final report embedding | TEXT / none | TEXT / none | VECTOR(384) / HNSW | VECTOR(384) / HNSW |
| fixture sentinel | n/a | preserved | n/a | preserved |
| SELECT probe | pass | pass | pass | pass |
| INSERT / SELECT probe | pass | pass | pass | pass |
| transaction aborted | false | false | false | false |

The Alembic execution log proves `r3e4f5g6h7i8` ran before `4b49004d01a6`, and `analysis_reports` therefore existed before `3a2f8b4c1d9e` altered it. The full chain continued beyond g5 through durable trace head `q5r6s7t8u9v0`.

## Test commands

All commands used `PYENV_VERSION=3.11.8`, the isolated URLs above, and the isolated worktree as both bootstrap fixture and portable overlay backend.

| Command | Collected | Passed | Failed | Skipped | Duration |
|---|---:|---:|---:|---:|---:|
| `pytest -q --durations=0 backend/tests/test_phase6w_r3_3i2_7_2_portable_bootstrap.py` | 9 | 9 | 0 | 0 | 4.51s |
| `pytest -q --durations=0 backend/tests/test_phase6w_r3_3i2_7_3_vector_fallback.py` | 6 | 6 | 0 | 0 | 5.04s |
| `pytest -q --durations=0 backend/tests/test_phase6w_r3_3i2_7_5_vector_schema_capability.py` | 6 | 6 | 0 | 0 | 5.17s |
| `pytest -q --durations=0 backend/tests/test_phase6w_r3_3i2_7_7_g5_vector_capability.py` | 6 | 6 | 0 | 0 | 5.34s |
| combined full migration contract suite (all four files) | 27 | 27 | 0 | 0 | 19.74s |

## Safety and release statement

- No production database, Supabase instance, Redis, container, or image was accessed or modified.
- No production migration was executed.
- No Agent or application business logic changed.
- No push, merge, deployment, or traffic expansion occurred.
- The isolated branch is technically ready for owner review only.
- Traffic remains `HOLD_1_PERCENT`.
