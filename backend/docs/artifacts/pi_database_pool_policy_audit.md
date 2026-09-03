# Database Pool Policy Audit

Phase: 6V-P1.6.3

Root cause: the previous pool test imported the global engine and always expected PostgreSQL `AsyncAdaptedQueuePool`. In backend full, the test environment uses `sqlite aiosqlite file URL`, where the project policy correctly resolves to `NullPool`.

Fix: added `resolve_database_pool_policy(...)` and made both `app.core.database` and `DatabaseCompanyV2ReportRagRepository` use it. Tests now cover SQLite memory/file, PostgreSQL default/queue/null/session-pooler modes, invalid strategy, and SQL echo/hide parameter policy without opening a PostgreSQL network connection.

Results: pool tests passed twice under SQLite and once with a PostgreSQL-style URL. Backend full passed.
