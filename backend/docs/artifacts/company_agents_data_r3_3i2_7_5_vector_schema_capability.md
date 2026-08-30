# Phase 6W-R3.3I.2.7.5 — Vector Schema Capability Repair

## Decision

```text
VECTOR_SCHEMA_CAPABILITY_READY
Traffic: HOLD_1_PERCENT
```

Revision `f4a5b6c7d8e9` now selects the report-chunk embedding schema from the connected database's `pg_extension` state. Python package importability no longer determines whether the migration emits `VECTOR(1536)`.

## Workspace boundary

- Branch: `r33i-vector-schema-capability`.
- Worktree: `/private/tmp/tradingagents-r33i2-7-5-vector-schema`.
- Parent: `4d366ce5bf00406b24b2a90ddeb132e4ae8c46df`; the a2 fallback is inherited and unchanged.
- The legacy bootstrap overlay remains uncommitted in its separate worktree and is absent from this branch diff.
- Main workspace historical changes were not modified.

## f4 schema audit

| Object | Previous behavior | Standard PostgreSQL contract | pgvector contract | Original file lines |
|---|---|---|---|---|
| `report_documents` RAG status columns | Add three nullable columns | unchanged | unchanged | 16–19 |
| `report_chunks.embedding` | Python `pgvector.sqlalchemy` import success selected VECTOR | TEXT | VECTOR(1536) | 21–27, 45 |
| `ix_report_chunks_embedding` | Unconditional HNSW attempt; broad exception swallowed failure | absent | HNSW/vector_cosine_ops | 56–64 |
| Database capability | not checked | `pg_extension` absent | `pg_extension` contains vector | none previously |

Answers:

1. f4 does not need and does not attempt to create the extension. It consumes extension state established before f4.
2. f4 previously duplicated capability intent but used a different, invalid proxy: Python adapter importability. a2 decides whether extension enablement is possible; f4 only reads the resulting database state.
3. Reusing the database catalog is safe and sufficient: `pg_extension` is the authoritative enabled-extension state.
4. Direct f4 DDL is not rerunnable because it adds columns and creates a table. Alembic repeat `upgrade f4` is idempotent because the revision is recorded and not executed again.
5. The preserved contract is VECTOR(1536) plus `ix_report_chunks_embedding` HNSW (`vector_cosine_ops`, m=16, ef_construction=64) when enabled; otherwise nullable TEXT and no vector index.

## Implementation

Changed migration: `backend/alembic/versions/2026_07_06_0004-f4a5b6c7d8e9_add_report_chunks.py`.

- `_database_has_vector()` reads only `pg_extension`.
- A local SQLAlchemy `UserDefinedType` renders the already-installed database type as `vector(1536)` without importing `pgvector.sqlalchemy`.
- `vector_enabled=true` selects VECTOR and creates the existing HNSW index.
- `vector_enabled=false` selects TEXT and skips vector index creation.
- f4 performs no extension DDL, so no extension failure can abort its transaction.
- Non-sensitive reason codes are logged: `VECTOR_ALREADY_ENABLED`, `VECTOR_EXTENSION_UNAVAILABLE`, `TEXT_FALLBACK_SELECTED`, `VECTOR_SCHEMA_SELECTED`.
- Vector dimensions, index parameters, table structure, and downgrade behavior remain unchanged.

## Test environment and scenarios

The true f4 parent `e3f4a5b6c7d8` was created through the audited portable-bootstrap overlay. No bootstrap file was copied into this branch.

| Scenario | Database state at f4 | Result column | Index | SELECT | INSERT/SELECT | Repeat |
|---|---|---|---:|---:|---:|---:|
| Standard PostgreSQL, vector unavailable | extension absent | text | absent | pass | pass | pass |
| pgvector server, non-superuser/no enablement | extension absent | text | absent | pass | pass | pass |
| pgvector already enabled | extension present | vector(1536) | present | pass | pass | pass |
| pgvector available but disabled | extension absent | text | absent | pass | pass | pass |

The last case intentionally selects TEXT: f4's explicit contract is enabled-extension state, not whether the current user could install an available extension. Extension creation remains a2's responsibility.

Disposable containers:

- Standard: `4c05dc9aee8fd17bcb81ac17737a4483d6e350d4d7cab6f62009f20adfbf3f81`, `postgres:16-alpine`.
- pgvector scenarios: `e0274324234d9f252c57dc68fc1969d5415fe54ac0b31b8bfd0400a5b4813ce3`, `pgvector/pgvector:pg16`.

No production database or credentials were used.

## Test commands

| Command | Collected | Passed | Failed | Skipped | Duration |
|---|---:|---:|---:|---:|---:|
| Static run without DB URLs | 6 | 2 | 0 | 4 | 0.04s |
| Four isolated DB scenarios | 6 | 6 | 0 | 0 | 5.51s |
| Final run after reason-code logging adjustment | 6 | 6 | 0 | 0 | 5.36s |

## Scope and safety

- No legacy bootstrap file changed.
- `a2c5e8f1b4d7` is unchanged from parent commit `4d366ce`.
- No Agent, RAG, Prompt, validator, Docker, dependency, lockfile, main, or embedding-provider file changed.
- No production DB, Supabase, Redis, or container was accessed or modified.
- No production migration, push, merge, deployment, or traffic expansion occurred.

## Final status

```text
VECTOR_SCHEMA_CAPABILITY_READY
HOLD_1_PERCENT
```
