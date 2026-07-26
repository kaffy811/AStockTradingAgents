# Update 57 - Phase 6U-D6.4 DB/RAG Follow-up

## Summary
- Confirmed the failing path is not global database unavailability: the app uses `AsyncSessionLocal`, while the failing live RAG tests and long Chat/RAG calls use `DatabaseCompanyV2ReportRagRepository`.
- Corrected the misleading PostgreSQL pool comment in `backend/app/core/database.py`: the app currently uses `AsyncAdaptedQueuePool`, not `NullPool`.
- Added configurable database pool settings with `pool_pre_ping=True`, bounded pool size/overflow, pool recycle, pool checkout timeout, and asyncpg command timeout.
- Reworked `DatabaseCompanyV2ReportRagRepository` so repository instances share one daemon event loop and one AsyncEngine/sessionmaker per database URL instead of creating a private loop and pool per instance.
- Wrapped repository `_run(...)` execution with in-loop `asyncio.wait_for`; timeout now raises structured `RAG_DB_QUERY_TIMEOUT`, cancels the task, and discards the shared loop/engine so later requests are not poisoned by a stuck operation.
- Added `close_shared_resources()` for deterministic test/app shutdown cleanup.
- Hardened the batch insert live test by cleaning its isolated `report_id` before asserting batch statistics.

## Validation
- `pytest backend/tests/fundamental/test_phase6tm_connection_pool_reuse.py -q`: `3 passed`
- Live Supabase DB subset with external network:
  - `pytest backend/tests/fundamental/test_phase6tm_connection_pool_reuse.py backend/tests/fundamental/test_phase6tj1_no_memory_fallback.py backend/tests/fundamental/test_phase6tj1_batch_insert.py backend/tests/fundamental/test_phase6tj1_chunk_persistence.py backend/tests/fundamental/test_phase6tj1_database_rag_repository.py backend/tests/fundamental/test_phase6tj1_document_persistence.py backend/tests/fundamental/test_phase6tj1_idempotency.py backend/tests/fundamental/test_phase6tj1_restart_read.py backend/tests/fundamental/test_phase6tj1_transaction_rollback.py -q`: `12 passed`
- D6.4 resolver/chat-display focused backend:
  - `pytest backend/tests/fundamental/test_phase6u_d6_4_security_index_chat_display.py -q`: `7 passed`

## Notes
- Sandbox network cannot resolve the Supabase pooler host; live DB validation required escalated network execution.
- No migration added.
- No public API field was removed.
- Prompt, Stage 3, auto_run, and rollout settings were not changed.
