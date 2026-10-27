# Phase 6W-R3.3E — Empty Database Bootstrap Migration Contract

Date: 2026-08-27

Decision: `BOOTSTRAP_CONTRACT_NOT_READY`

Traffic: `HOLD_1_PERCENT`

## Migration graph and root audit

The graph is a single linear chain from root `4b49004d01a6` to head `q5r6s7t8u9v0`. The relevant prefix is:

```text
4b49004d01a6 (root, baseline existing schema, upgrade=pass)
→ 76fe066db8b1 (creates stock_master)
→ 3a2f8b4c1d9e (first ALTER of analysis_reports)
→ a7c3f91e2b85
→ b4d8e2f1a6c9
→ c5e9f12a3b87
→ d7e3a9b5c2f8
→ e8f3a2c7d4b1
→ f1a4b7c9d2e5
→ a2c5e8f1b4d7 (pgvector migration)
→ ...
→ p4q5r6s7t8u9
→ q5r6s7t8u9v0 (head)
```

`analysis_reports` has no creating migration. Its original source was the pre-Alembic/existing schema produced historically outside the migration chain, consistent with the root docstring and empty `upgrade()`. The current root is therefore an existing-schema marker, not an empty-database bootstrap.

## Complete legacy-schema gap

Cross-checking ORM tables against explicit `op.create_table` history identified an entire baseline gap, not one table:

- `app_users`
- `analysis_reports`
- `watchlist_items`
- `industry_master`
- `stock_industry_map`
- `industry_hot_stock_snapshot`
- `company_v2_report_rag_documents`
- `company_v2_report_rag_chunks`

Later migrations explicitly create `stock_master`, chat tables, financial RAG tables, ETL/coverage tables, `report_documents`, `report_chunks`, fusion/audit/MVP tables, and R3.3B trace tables. Several later revisions assume the missing baseline tables already exist: analysis-report column migrations, chat foreign keys to `app_users`, MVP user-column migrations, and Company V2 RAG persistence alterations.

## Attempted repair design and why it was withdrawn

A draft explicit root bootstrap migration was tested. It used only versioned `op.create_table`, indexes, constraints, UUID/JSONB types, and foreign keys; it did not import runtime ORM models or call `Base.metadata.create_all`. The existing no-op baseline was temporarily pointed at the new root. This design passed the original `analysis_reports` failure and all legacy-table-dependent revisions.

The draft was withdrawn after full-chain testing found a second independent blocker in the already-published revision `a2c5e8f1b4d7`:

1. On pgvector-enabled PostgreSQL, the revision enables/detects the database vector type and imports `pgvector.sqlalchemy`, but the committed dependency set does not contain the Python `pgvector` package: `ModuleNotFoundError`.
2. On standard PostgreSQL, `CREATE EXTENSION vector` fails. The revision catches the exception inside Alembic's transaction, but PostgreSQL leaves the transaction aborted; the intended TEXT fallback then fails with `InFailedSQLTransactionError`.

Fixing either branch requires changing an already-published migration's transaction/type handling or changing project dependencies. Both are explicitly outside this phase's allowed commit scope. Leaving only the legacy bootstrap would not make `alembic upgrade head` pass, so no partial migration change was retained.

## Isolated PostgreSQL evidence

Two fresh disposable PostgreSQL 16 databases were used; neither was production and neither contained seed/report/user data.

| Database image | Result |
|---|---|
| `pgvector/pgvector:pg16` | Legacy bootstrap passed; failed at `a2c5e8f1b4d7` because Python `pgvector` is absent |
| `postgres:16-alpine` | Legacy bootstrap passed; failed at `a2c5e8f1b4d7` because caught extension DDL error aborted the transaction |

Both disposable containers and anonymous volumes were removed. No production database was contacted or modified.

## Contract gates

| Gate | Result |
|---|---|
| Empty DB root→head | FAIL at `a2c5e8f1b4d7` |
| Repeat `upgrade head` | NOT RUN |
| `current == heads == q5r6s7t8u9v0` | FAIL / unreachable |
| Required business/RAG/trace tables | NOT FULLY REACHABLE |
| Existing-schema compatibility | Static ancestor compatibility design confirmed; runtime gate incomplete |
| Automated migration contract tests | NOT ADDED because production implementation could not satisfy scope |
| Candidate import/health | NOT RUN because candidate image does not contain a passing migration contract |
| `git diff --check` | PASS |

No code or migration change remains from the failed draft. No commit was created.

## Required follow-up authorization

A narrowly expanded migration remediation must authorize one of:

- making published revision `a2c5e8f1b4d7` transaction-safe and independent of an undeclared Python type adapter; or
- adding the required pinned Python pgvector dependency plus a verified pgvector-only database contract.

That remediation should include the explicit legacy bootstrap migration described above and actual PostgreSQL tests for both empty and already-versioned schemas. Until both blockers are resolved, the candidate environment and R3.3D attribution remain blocked.

Final state: `BOOTSTRAP_CONTRACT_NOT_READY` / `HOLD_1_PERCENT`.
