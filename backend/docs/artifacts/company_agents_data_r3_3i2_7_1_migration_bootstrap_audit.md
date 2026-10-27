# Phase 6W-R3.3I.2.7.1 — Legacy Migration Bootstrap Contract Audit

## Decision

```text
MIGRATION_BOOTSTRAP_REMEDIATION_READY
Traffic: HOLD_1_PERCENT
```

Recommended contract: **A. Portable Empty-DB Bootstrap**. The repository explicitly documents `alembic upgrade head` as the first-deploy production workflow, while production disables `Base.metadata.create_all`. The current migration graph violates that contract because its root is only an existing-schema marker.

## Audit boundary

- HEAD: `b055da8495c54bb37625f0b0e0f94b4d4a627de2`
- Branch: `release/demo-staging`
- This was a source/history-only audit. No database was connected.
- Historical dirty files and prior artifacts were not modified.

## `analysis_reports` contract

The current graph begins with `4b49004d01a6`, whose docstring says “baseline existing schema” and whose `upgrade()` and `downgrade()` are no-ops. Revision `76fe066db8b1` then creates only `stock_master`; revision `3a2f8b4c1d9e` immediately alters `analysis_reports` without any prior Alembic creation of that table.

| Object | First definition file:line | First migration reference file:line | Theoretical creation order | Current actual order | Violation |
|---|---|---|---|---|---:|
| `analysis_reports` ORM | `backend/app/models/analysis_report.py:16` (`__tablename__` at 17) | `backend/alembic/versions/2026_06_04_0001-3a2f8b4c1d9e_add_stock_name_to_analysis_reports.py:23` | Create base table, then add `stock_name` | No Alembic create; first action is ALTER | Yes |
| `analysis_reports.stock_name` | ORM line 37 | `3a2f8b4c1d9e...py:24` | Base table → column migration | ALTER follows no-op baseline | Yes |
| `analysis_reports.auto_saved` | ORM line 38 | `2026_06_04_0002-a7c3f91e2b85...py:22` | Base table → stock_name → auto_saved | Base table absent | Yes |
| `analysis_reports.analysis_scope` | ORM line 39 | `2026_06_04_0003-b4d8e2f1a6c9...py:22` | Base table → preceding columns → analysis_scope | Base table absent | Yes |
| `analysis_reports.output_language` | ORM line 40 | `2026_06_07_0001-c5e9f12a3b87...py:22` | Base table → preceding columns → output_language | Base table absent | Yes |
| Alembic baseline | `2026_05_30_1612-4b49004d01a6_baseline_existing_schema.py:17` | Same file, `upgrade()` line 23 | Versioned legacy schema before additive migrations | Root revision performs no DDL | Yes for empty DB |

The missing contract is broader than one table. Static history shows these legacy tables were historically created outside Alembic and are absent from the current root DDL: `app_users`, `analysis_reports`, `watchlist_items`, `industry_master`, `stock_industry_map`, `industry_hot_stock_snapshot`, `company_v2_report_rag_documents`, and `company_v2_report_rag_chunks`.

### Required answers

1. **Was `analysis_reports` in an unmanaged legacy schema?** Yes. The no-op “existing schema” root, ORM history, startup `create_all`, and absence of any `op.create_table("analysis_reports")` in the release chain establish this.
2. **Is an early creating migration missing?** Yes. Alembic needs a versioned definition of the complete pre-baseline legacy schema before `4b49004d01a6`/`3a2f8b4c1d9e`.
3. **Does `3a2f8b4c1d9e` assume pre-provisioning?** Yes. Its first operation is an unconditional `op.add_column` on `analysis_reports`.
4. **Is empty bootstrap a formal contract?** Yes. `backend/.env.example:11-16` says first deploy runs `alembic upgrade head`; `backend/app/core/config.py:186-188` and `backend/app/core/database.py:82-89` say production relies exclusively on Alembic. Development `create_all` is explicitly a convenience, not the production schema contract.
5. **Minimum prerequisite of an existing production/Supabase schema:** before the first additive revision, all eight legacy tables, their primary/foreign keys, uniqueness constraints and indexes must match the versioned legacy definition; the database must then carry a truthful Alembic revision compatible with that schema. Merely having `analysis_reports` is insufficient. No production schema was queried in this audit.

The historical `.env.example` suggestion to `stamp head` after `create_all` describes legacy takeover, but stamping is not a reproducible schema constructor and cannot be used for clean candidate databases.

## `79323b7` decomposition

| File/group | Category | Purpose | Directly bootstrap-related | Needed in release candidate | Reason |
|---|---|---|---:|---:|---|
| `2026_05_29_0001-r3e4f5g6h7i8_bootstrap_legacy_schema.py` | A | Creates the eight pre-Alembic tables | Yes | Yes, after focused review | Supplies missing root DDL |
| `2026_05_30_1612-4b49004d01a6_baseline_existing_schema.py` | A | Reparents no-op baseline to the explicit legacy root | Yes | Yes | Makes creation precede `3a2f8b4c1d9e` |
| `a2c5e8f1b4d7`, `f4a5b6c7d8e9`, `g5h6i7j8k9l0` migrations | B | Make vector DDL depend on DB capability and preserve TEXT fallback | No | Separately required for full empty-DB contract | Empty bootstrap otherwise reaches a second, independent vector failure |
| `app/migration_support/*` | B | Catalog-based vector capability/type helper | No | Only with separately audited B commit | Runtime support for the three vector revisions |
| `pyproject.toml`, `uv.lock` | C | Add `pgvector` Python adapter | No | Only if B retains `pgvector.sqlalchemy.Vector` | Direct runtime dependency on pgvector-enabled PostgreSQL; not part of A |
| `test_r33e_vector_migration_contract.py` | B | Standard/pgvector DB and repeat-upgrade contract | No | Yes with B, updated to candidate head | Required migration verification |
| update report and R3.3E2 artifact | D | Historical documentation | No | No | Not executable remediation |

`backend/Dockerfile` was not changed by `79323b7`. The commit nevertheless combines A, B, C, tests, and historical documentation, so cherry-picking it wholesale is not a minimum release integration.

## Contract selection

### Recommended: A — Portable Empty-DB Bootstrap

```text
empty PostgreSQL database
→ alembic upgrade head
→ complete schema
→ second alembic upgrade head is a no-op
```

This is the only recommendation consistent with the repository's declared first-deploy process, disposable candidate environments, and `ENABLE_CREATE_ALL=false` production behavior.

### Why Existing-Schema Baseline is not suitable

There is no checked-in, versioned, repeatable, non-production legacy schema constructor independent of ORM `create_all`. A contract that says “the tables must already exist” would preserve the exact hidden prerequisite that caused the failure. Production currently having tables would demonstrate one environment's state, not a portable bootstrap contract.

### History and compatibility rules

- A new explicit legacy root revision can be added before `4b49004d01a6`, but connecting it requires changing the published baseline's `down_revision`. Thus the graph history changes even though additive revisions such as `3a2f8b4c1d9e` need not be rewritten.
- A new revision appended at current head cannot repair an earlier failing ALTER and is therefore not a valid bootstrap fix.
- Already-deployed databases at a descendant revision must not rerun the new ancestor. Alembic ancestry validation plus schema-shape preflight must prove they remain at their existing revision and upgrade forward normally.
- The legacy root should use deterministic versioned DDL, not runtime ORM imports or `Base.metadata.create_all`.
- Do not make the root broadly `IF NOT EXISTS`: that can silently accept a partially incompatible schema. Existing-schema compatibility should be verified explicitly before stamping/reconciliation.
- Downgrade scope and destructive behavior must be documented and tested only on disposable databases.

## Proposed minimum remediation (not implemented)

The Agent credibility chain and migration remediation must remain separate commits. The migration work should itself be split so legacy bootstrap is reviewable independently from vector portability.

| Proposed file | Proposed change | Purpose | Deployed-DB risk | Empty-DB effect |
|---|---|---|---|---|
| New focused legacy bootstrap revision | Version the eight missing legacy tables, constraints, FKs and indexes | Supply actual root schema | Medium: ancestry/history must be validated; DDL must not run on already-versioned descendants | Allows early additive migrations to run |
| `2026_05_30_1612-4b49004d01a6_baseline_existing_schema.py` | Point `down_revision` to new legacy root only | Establish correct order | Medium: changes published graph ancestry; requires current/head compatibility tests | Orders create before ALTER |
| New legacy bootstrap contract test | Test exact table/constraint shape, empty DB, release-baseline path, and repeat upgrade | Prevent hidden preconditions | None outside disposable DB | Verifies A |
| Three existing vector migrations plus a migration-only helper | Separately repair capability detection and transaction-safe standard-PostgreSQL fallback | Remove second independent empty-head blocker | Medium: edits published migrations; validate already-versioned DB is unchanged | Lets both PostgreSQL variants reach head |
| `pyproject.toml` and `uv.lock` (conditional) | Add pinned `pgvector` only if the selected B implementation imports its SQLAlchemy type | Satisfy proven migration runtime dependency | Dependency/image change; separate approval | Required only for pgvector type adapter path |
| Vector migration contract test | Run full chain twice on `postgres:16` and `pgvector/pgvector:pg16` | Verify capability portability and idempotence | None outside disposable DB | Verifies B |

Required acceptance matrix for the subsequent implementation:

- Standard PostgreSQL: empty DB → candidate head; release baseline → candidate head; repeat upgrade.
- pgvector PostgreSQL: the same three paths.
- Existing deployed-schema fixture at every affected takeover boundary: current revision remains valid and no legacy tables/data are recreated or dropped.
- `alembic current == alembic heads == candidate head` after every successful path.
- No manual table creation, stamp-only shortcut, production dump, or production credentials.

The bootstrap portion is now sufficiently bounded for implementation planning, but release integration remains blocked until both A and the separately audited vector portability contract pass.

## Safety declaration

```text
No migration code changed.
No production database accessed or modified.
No push, merge, deploy, or traffic expansion occurred.
Traffic remains HOLD_1_PERCENT.
```

## Final status

```text
MIGRATION_BOOTSTRAP_REMEDIATION_READY
HOLD_1_PERCENT
```
