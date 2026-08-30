# Phase 6W-R3.3I.2.7.3 — Standard PostgreSQL Vector Fallback Repair

## Decision

```text
VECTOR_FALLBACK_READY
Traffic: HOLD_1_PERCENT
```

Revision `a2c5e8f1b4d7` now makes its vector/TEXT decision from database catalogs and contains recoverable extension/index DDL inside savepoints. Standard PostgreSQL continues with TEXT after unavailable or permission-denied extension creation; pgvector PostgreSQL retains VECTOR and HNSW behavior.

## Workspace boundary

- Base HEAD: `b055da8495c54bb37625f0b0e0f94b4d4a627de2`.
- Branch: `r33i-vector-fallback`.
- Clean worktree: `/private/tmp/tradingagents-r33i2-7-3-vector`.
- The uncommitted legacy bootstrap remains only in `/private/tmp/tradingagents-r33i2-7-2-bootstrap` on `r33i-migration-bootstrap`; none of its files are in this change.
- Main-workspace historical dirty changes and prior Agent commits were not modified.

## Transaction-path attribution

Original flow in `a2c5e8f1b4d7`:

1. `CREATE EXTENSION IF NOT EXISTS vector` ran in Alembic's outer PostgreSQL transaction.
2. A broad `except Exception` swallowed the client exception.
3. PostgreSQL nevertheless kept the transaction in failed state.
4. `_pgvector_available()` reused the failed connection.
5. TEXT `ALTER TABLE ... ADD COLUMN` then failed with `InFailedSQLTransactionError`.

The extension status questions are now separated:

- Installed/enabled: query `pg_extension`.
- Available on server: query `pg_available_extensions`.
- Creation permission: determined only by a real creation attempt when available but disabled.
- Failed creation: rolled back to a nested transaction/savepoint before TEXT fallback.
- Python package availability is never used as database capability.

## Implementation

Changed file: `backend/alembic/versions/2026_06_24_0003-a2c5e8f1b4d7_add_pgvector_embedding.py`.

- `_extension_enabled()` reads `pg_extension`.
- `_extension_available()` reads `pg_available_extensions`.
- `_enable_vector_if_safe()` returns `(enabled, reason_code)` and uses `conn.begin_nested()` for `CREATE EXTENSION vector`.
- SQLSTATE `42501` maps to `VECTOR_EXTENSION_PERMISSION_DENIED`; other recovered create errors map to `VECTOR_EXTENSION_CREATE_FAILED_RECOVERED`.
- TEXT fallback is selected only when the database capability result is false.
- VECTOR type rendering is local SQLAlchemy `UserDefinedType`; it does not import or infer capability from `pgvector.sqlalchemy`.
- HNSW creation is also savepoint-protected so a recoverable index failure cannot poison later migration operations.
- Logs emit stable reason codes only, never connection strings, credentials, or raw database errors.

Reason codes:

```text
VECTOR_ALREADY_ENABLED
VECTOR_EXTENSION_AVAILABLE
VECTOR_EXTENSION_UNAVAILABLE
VECTOR_EXTENSION_PERMISSION_DENIED
VECTOR_EXTENSION_CREATE_FAILED_RECOVERED
TEXT_FALLBACK_SELECTED
```

No vector dimensions, index parameters, table/column names, or embedding schema design changed.

## Isolated database matrix

Prerequisite tables through parent revision `f1a4b7c9d2e5` were created by the prior phase's versioned bootstrap migration worktree. The vector branch did not copy or modify those bootstrap files.

| Scenario | Container / database | Extension before a2 | Result type | HNSW | Post-migration SQL | Repeat a2 |
|---|---|---|---|---:|---|---|
| Standard PostgreSQL, extension unavailable | `4c05dc9aee8...` / `vector_standard` | unavailable | `text` | false | SELECT 1 and INSERT/SELECT passed | passed |
| pgvector server, non-superuser cannot create | `e0274324234...` / `vector_permission`, role `vectorlimited` | available, disabled | `text` | false | SELECT 1 and INSERT/SELECT passed | passed |
| pgvector, already enabled | `e0274324234...` / `vector_enabled` | enabled | `vector` | true | SELECT 1 and INSERT/SELECT passed | passed |
| pgvector, available and creatable | `e0274324234...` / `vector_available` | available, disabled | `vector` | true | SELECT 1 and INSERT/SELECT passed | passed |

The permission-denied database remained without the vector extension, proving that fallback did not silently enable it. Both VECTOR scenarios contained the extension and expected HNSW index.

## Tests

| Command | Collected | Passed | Failed | Skipped | Duration |
|---|---:|---:|---:|---:|---:|
| Static run without database URLs | 6 | 2 | 0 | 4 | 0.16s |
| First real run before versioned prerequisite fixture was wired | 6 | 2 | 4 | 0 | 1.83s |
| Final four-scenario isolated DB run with versioned parent fixture | 6 | 6 | 0 | 0 | 5.08s |

The intermediate four failures occurred at the earlier missing-legacy-table revision, not in a2; the test harness was corrected to build the parent schema through the versioned bootstrap fixture rather than copying bootstrap code into this branch.

Final tests prove:

- catalog-based capability detection;
- no Python-package capability inference;
- standard/unavailable TEXT fallback;
- permission-denied TEXT fallback;
- already-enabled VECTOR path;
- available-and-creatable VECTOR path;
- expected vector index behavior;
- usable transaction via SELECT and INSERT/SELECT;
- repeat upgrade no-op.

## Scope and safety

- No bootstrap migration was modified on this branch.
- No Agent, RAG, Prompt, citation, numeric validator, Docker, embedding provider, `pyproject.toml`, or `uv.lock` file changed.
- No production database, Supabase resource, Redis, or container was accessed or modified.
- No production migration was executed.
- No push, merge, deployment, or traffic expansion occurred.

## Final status

```text
VECTOR_FALLBACK_READY
HOLD_1_PERCENT
```
