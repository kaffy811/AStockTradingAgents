# Phase 6W-R3.3I.2.7.7 — Migration-Wide Vector Capability Audit and g5 Repair

## Decision

```text
VECTOR_MIGRATION_COVERAGE_READY
Traffic: HOLD_1_PERCENT
```

The complete Alembic graph contains three vector-schema migrations. a2 and f4 are covered by independent commits; g5 was the only remaining Python-import-based blocker. g5 now uses `pg_extension`, preserves standard PostgreSQL TEXT data, and retains the published VECTOR dimension-reset contract on pgvector.

## Static inventory

Inventory was run against `3982f7851d95c0b762b9e7c967e8c79d8b308742`, which contains parent commit `4d366ce`.

| Revision | File | Vector behavior | Capability source | Classification | Status |
|---|---|---|---|---|---|
| `e8f3a2c7d4b1` | `2026_06_24_0001...financial_rag_tables.py` | Creates only a TEXT placeholder; vector references are comments | none needed | SAFE_NO_VECTOR | safe |
| `a2c5e8f1b4d7` | `2026_06_24_0003...pgvector_embedding.py` | Optional extension enablement, VECTOR(1536)/TEXT, HNSW | `pg_extension`, `pg_available_extensions`, savepoint | SAFE_DATABASE_CATALOG | fixed by `4d366ce` |
| `f4a5b6c7d8e9` | `2026_07_06_0004...report_chunks.py` | VECTOR(1536)/TEXT and HNSW | `pg_extension` | SAFE_DATABASE_CATALOG | fixed by `3982f785` |
| `g5h6i7j8k9l0` | `2026_07_06_0005...embedding_to_384.py` | Replaces embedding with VECTOR(384)/TEXT and rebuilds HNSW | previously Python importability | UNSAFE_PYTHON_IMPORT / UNSAFE_UNGUARDED_DDL | fixed in this phase |

Search terms covered VECTOR/vector type syntax, pgvector imports, extension DDL/catalogs, HNSW and ivfflat. No later revision contains vector schema behavior. Therefore no scope expansion was required.

## g5 data contract

- g5 operates on an existing `report_chunks` table created by f4.
- Published VECTOR behavior is deliberately destructive for the embedding column: vector(1536) is dropped and vector(384) is added because dimensions are incompatible. Existing vector values cannot be recovered; business rows remain.
- It resets `embedding_model`/`embed_error`, and changes report documents from `embedded` to `chunked` for re-embedding.
- Standard PostgreSQL already has TEXT. There is no dimensional schema conversion, so dropping/re-adding the TEXT column was unnecessary and would destroy valid fallback data.
- Extension available but not enabled follows the f4 contract: TEXT. g5 does not create extensions.
- Alembic repeat upgrade is safe because the recorded revision prevents re-execution.

No table is dropped or truncated. VECTOR embedding values are reset exactly as the published migration documented; TEXT values are now preserved.

## Implementation

Branch: `r33i-g5-vector-capability`, parent `3982f7851d95c0b762b9e7c967e8c79d8b308742`.

Changed migration: `backend/alembic/versions/2026_07_06_0005-g5h6i7j8k9l0_migrate_embedding_to_384.py`.

- `_database_has_vector()` reads `pg_extension`.
- Local SQLAlchemy type rendering removes any Python pgvector adapter dependency.
- Enabled extension: drop old vector column, create vector(384), rebuild HNSW.
- Disabled extension: retain an existing TEXT column and its values; create TEXT only if the column is absent; no vector index.
- Downgrade uses the same database capability: vector resets to 1536; TEXT is preserved.
- Removed broad exception swallowing from column and HNSW DDL.
- Reason codes contain no secrets: `VECTOR_ALREADY_ENABLED`, `VECTOR_EXTENSION_UNAVAILABLE`, `TEXT_FALLBACK_PRESERVED`, `VECTOR_384_SCHEMA_SELECTED`.

## Four-scenario validation

The audited full-chain overlay established the true f4 parent state without adding bootstrap files to this branch.

| Scenario | g5 result type | Index | Existing row | Existing embedding | SQL probes | Repeat |
|---|---|---:|---|---|---|---|
| Standard PostgreSQL, unavailable | text | absent | preserved | `preserve-text-embedding` preserved | pass | pass |
| Extension available but non-enabled/non-superuser | text | absent | preserved | TEXT preserved | pass | pass |
| pgvector enabled | vector(384) | present | preserved | reset to NULL per dimension contract | pass | pass |
| pgvector available then disabled | text | absent | preserved | NULL where extension removal removed the old column | pass | pass |

Post-test direct evidence:

- Standard: type `text`, sentinel value preserved, HNSW absent, SELECT 1 passed.
- pgvector: type `vector(384)`, row count preserved, HNSW present, SELECT 1 passed.
- Every scenario performed a post-upgrade INSERT/SELECT and repeat `alembic upgrade g5h6i7j8k9l0`.

## Tests

| Command | Collected | Passed | Failed | Skipped | Duration |
|---|---:|---:|---:|---:|---:|
| Static inventory/contract without DB URLs | 6 | 2 | 0 | 4 | 0.04s |
| Four isolated g5 capability/data scenarios | 6 | 6 | 0 | 0 | 5.51s |

## Scope and safety

- No bootstrap file changed.
- a2 and f4 remain unchanged from parent commits.
- No Agent, RAG, Prompt, validator, Docker, dependency, lockfile, main, or embedding-provider file changed.
- No production DB, Supabase resource, Redis, or container was accessed or modified.
- No production migration, push, merge, deployment, or traffic expansion occurred.

## Final status

```text
VECTOR_MIGRATION_COVERAGE_READY
HOLD_1_PERCENT
```
