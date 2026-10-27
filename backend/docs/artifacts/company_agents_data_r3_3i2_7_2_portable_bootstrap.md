# Phase 6W-R3.3I.2.7.2 — Portable Empty-DB Bootstrap Remediation

## Final decision

```text
PORTABLE_BOOTSTRAP_NOT_READY
Traffic: HOLD_1_PERCENT
```

The isolated bootstrap implementation fixes the legacy-schema ordering defect and passes the full pgvector PostgreSQL path, including repeat upgrade and existing-data preservation. It cannot satisfy the required standard PostgreSQL path because published vector revision `a2c5e8f1b4d7` aborts the migration transaction after a failed `CREATE EXTENSION vector`. Vector changes are explicitly outside this phase, so no commit was created.

## Workspace boundary

- Main workspace HEAD/branch: `b055da8495c54bb37625f0b0e0f94b4d4a627de2` / `release/demo-staging`.
- Isolated worktree: `/private/tmp/tradingagents-r33i2-7-2-bootstrap`.
- Isolated branch: `r33i-migration-bootstrap`.
- Main historical dirty changes were not modified.
- No Agent, RAG, prompt, citation, derived-fact, numeric validator, vector migration, Docker, dependency, embedding, `pyproject.toml`, or `uv.lock` file was changed.

## Locked legacy-schema contract

The proposed root uses only fields traceable to the pre-Alembic ORM/schema contract. Columns added by later migrations are intentionally not present in the root.

| Legacy table | Root fields | Keys | Required root indexes | First later migration use |
|---|---|---|---|---|
| `app_users` | id, username, email, hashed_password, is_active, created_at, updated_at | PK id; UNIQUE username/email | username, email | `d7e3a9b5c2f8` FK; later user columns |
| `analysis_reports` | id, user_id, market, symbol, report_type, report_md, sections, report_metadata, warnings, agents, created_at, updated_at | PK id; FK user_id → app_users | user_id, symbol, `(user_id, created_at)` | `3a2f8b4c1d9e` adds stock_name |
| `watchlist_items` | id, user_id, market, symbol, name, note, sort_order, created_at, updated_at | PK id; FK user_id; UNIQUE user/market/symbol | user_id, user/order | legacy runtime table |
| `industry_master` | id, market, industry_code, industry_name, industry_level, parent_code, source, created_at, updated_at | PK id; UNIQUE market/code/source | market, code, market/code | ETL/runtime consumers |
| `stock_industry_map` | id, market, symbol, stock_name, industry_code, industry_name, industry_level, source, is_primary, created_at, updated_at | PK id; UNIQUE market/symbol/code/source | market, symbol, code, composite lookup indexes | ETL/runtime consumers |
| `industry_hot_stock_snapshot` | id, market, industry_code, industry_name, trade_date, rank, symbol, stock_name, score fields, version/source, timestamps | PK id; UNIQUE market/code/date/symbol/version | market/code/date and symbol/date lookups | ETL/runtime consumers |
| `company_v2_report_rag_documents` | pre-generation report metadata and timestamps | PK id | UNIQUE report_id | `i7j8k9l0m1n2` adds generation fields and rewrites index |
| `company_v2_report_rag_chunks` | document/report IDs, page/chunk text metadata, TEXT embedding, timestamp | PK id; FK document_id | document_id, report_id, text_hash | RAG persistence/runtime consumers |

No test-only table, financial fixture, mock company, or financial row is created.

## Proposed migration graph implementation

Draft files in the isolated worktree only:

- New root: `backend/alembic/versions/2026_05_29_0001-r3e4f5g6h7i8_bootstrap_legacy_schema.py`.
- Reparented no-op baseline: `4b49004d01a6.down_revision = r3e4f5g6h7i8`.
- Contract tests: `backend/tests/test_phase6w_r3_3i2_7_2_portable_bootstrap.py`.

Resulting prefix:

```text
r3e4f5g6h7i8 legacy bootstrap
→ 4b49004d01a6 existing-schema marker
→ 76fe066db8b1 stock_master
→ 3a2f8b4c1d9e analysis_reports.stock_name
→ ...
→ q5r6s7t8u9v0
```

Safety properties of the draft:

- Each legacy table is created only when absent.
- Existing tables are neither dropped, truncated, replaced, nor altered by the bootstrap.
- The root contains no INSERT/data seeding.
- Downgrade is intentionally a no-op because these tables predate Alembic ownership; it never deletes legacy/user data.
- Databases already at `4b49004d01a6` or descendants do not execute the newly linked ancestor. A current release-head database remains at `q5r6s7t8u9v0` and `upgrade head` is a no-op.

## Isolated database evidence

| Environment | Container ID | Image | Database | Start | Target |
|---|---|---|---|---|---|
| Standard | `4f6fc858fb12d395dd4e97411784d1001ed15fdb77d0658c15da49c417513fec` | `postgres:16-alpine` | `bootstrap_standard`, localhost 15442 | empty | `q5r6s7t8u9v0` |
| pgvector | `ecd314344a63b26d68ef8b33cc4b27e2f42bfae37fc8bded01ecb0df5bc80e6c` | `pgvector/pgvector:pg16` | `bootstrap_vector`, localhost 15443 | empty | `q5r6s7t8u9v0` |
| Existing-schema fixture | same isolated pgvector container | `pgvector/pgvector:pg16` | `bootstrap_existing` / test DB | versioned root `r3e4f5g6h7i8` | `q5r6s7t8u9v0` |

No production or Supabase connection was used.

## Migration acceptance results

| Path | Current | Heads | Result | Evidence |
|---|---|---|---|---|
| Empty pgvector DB → head | `q5r6s7t8u9v0 (head)` | `q5r6s7t8u9v0 (head)` | PASS | All eight legacy tables and expected analysis columns/indexes exist |
| pgvector head → head | unchanged | same | PASS | Repeat upgrade emitted no revisions |
| Versioned legacy fixture → head | `q5r6s7t8u9v0 (head)` | same | PASS | Sentinel `app_users` row survived |
| Existing release head → candidate graph head | `q5r6s7t8u9v0 (head)` | same | PASS/no-op | Candidate changes only ancestry below current revision |
| Empty standard PostgreSQL → head | no current revision after rollback | `q5r6s7t8u9v0 (head)` | FAIL | Published vector revision aborts transaction |
| Standard repeat upgrade | not run | same | BLOCKED | First upgrade did not reach head |

The standard path progressed through the new bootstrap and all four `analysis_reports` column revisions. First failure:

```text
revision: a2c5e8f1b4d7
CREATE EXTENSION IF NOT EXISTS vector
→ extension unavailable
→ PostgreSQL transaction aborted
→ ALTER TABLE financial_document_chunks ADD COLUMN embedding_vector TEXT
→ InFailedSQLTransactionError
```

This is the independently known vector-portability defect. The bootstrap did not introduce it, and this phase did not modify or bypass it.

On the successful pgvector path:

- Eight required legacy tables existed at head.
- `analysis_reports` contained root fields plus stock_name, auto_saved, analysis_scope and output_language.
- Required analysis/document indexes existed.
- Legacy and financial table row counts were zero after empty bootstrap.
- The only preservation sentinel was a non-financial user row in a disposable DB; it remained after upgrade.

## Test results

| Command | Collected | Passed | Failed | Skipped | Duration |
|---|---:|---:|---:|---:|---:|
| Static bootstrap contract test before real DB wiring | 6 | 6 | 0 | 0 | 0.02s |
| Full migration contract test with standard, pgvector and existing-schema URLs | 9 | 8 | 1 | 0 | 3.51s |

The failing assertion is exactly `test_empty_database_reaches_head_and_repeat_is_noop[R33I_BOOTSTRAP_STANDARD_URL]`; pgvector empty/repeat and versioned existing-schema preservation tests passed.

## Commit decision

No commit was created because Step 4/5 were not fully green. The isolated branch retains an unstaged draft for audit. Making the standard path pass requires a separately authorized vector-portability remediation and is prohibited in this phase.

## Safety declaration

```text
No production database accessed or modified.
No production container or Supabase resource changed.
No push, merge, deploy, or traffic expansion occurred.
No production migration executed.
Traffic remains HOLD_1_PERCENT.
```

## Final status

```text
PORTABLE_BOOTSTRAP_NOT_READY
HOLD_1_PERCENT
```
