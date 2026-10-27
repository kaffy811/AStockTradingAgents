# Phase 6W-R2.2 — Migration Verification

**Generated:** 2026-08-12  
**Branch:** release/demo-staging  
**HEAD:** a542bc18a21e465c7025d4bdc8c16f032f60736d  
**Gate:** G2

---

## Current State: BLOCKED (depends on G1)

Cannot run `alembic current` until production database is reachable.

---

## Expected State

| Item | Expected Value |
|------|---------------|
| `alembic current` | `p4q5r6s7t8u9 (head)` |
| `alembic heads` | `p4q5r6s7t8u9` |
| Migration file | `2026_07_28_0001-p4q5r6s7t8u9_add_email_verified_at.py` |
| Total applied migrations | 25 |

---

## Post-Resume Verification Commands

```bash
cd /Users/kaffy/Documents/TradingAgents/backend
uv run alembic current
uv run alembic heads
```

### Case A: current == heads (expected)

```
# Output:
p4q5r6s7t8u9 (head)
```

Action: Record G2 PASS. Proceed to container restart.

### Case B: current < heads (schema delta)

**STOP. Do NOT run `alembic upgrade head` automatically.**

Action:
1. Record `alembic current` output
2. Record `alembic heads` output  
3. Run `alembic history --verbose` and capture delta
4. Output `company_agents_data_r2_2_migration_plan.md`
5. Wait for project owner authorization
6. Only after explicit authorization: `uv run alembic upgrade head`

### Case C: alembic_version table missing

**STOP.** DB was created fresh or restored from backup without migrations.

Action:
1. Document the gap
2. Await owner authorization
3. Only with explicit authorization: `uv run alembic upgrade head` (applies all 25 migrations)

**Prohibited:**
```bash
# NEVER without authorization
DROP TABLE ...
TRUNCATE ...
DELETE FROM ...
alembic downgrade ...
```

---

## Migration Chain Reference

| # | Revision | File | Purpose |
|---|----------|------|---------|
| 1 | 4b49004d | 2026_05_30_1612 | Baseline schema |
| 2 | 76fe066d | 2026_06_01_0937 | stock_master |
| 3 | 3a2f8b4c | 2026_06_04_0001 | stock_name on analysis_reports |
| 4 | a7c3f91e | 2026_06_04_0002 | auto_saved field |
| 5 | b4d8e2f1 | 2026_06_04_0003 | analysis_scope |
| 6 | c5e9f12a | 2026_06_07_0001 | output_language |
| 7 | d7e3a9b5 | 2026_06_12_0001 | chat tables |
| 8 | e8f3a2c7 | 2026_06_24_0001 | financial_rag tables |
| 9 | f1a4b7c9 | 2026_06_24_0002 | content_hash |
| 10 | a2c5e8f1 | 2026_06_24_0003 | pgvector embedding |
| 11 | b8c3d9e2 | 2026_07_05_0001 | ETL tables |
| 12 | **c1d2e3f4** | 2026_07_06_0001 | **report_documents** ← RAG dep |
| 13 | d2e3f4a5 | 2026_07_06_0002 | report_discovery_fields |
| 14 | e3f4a5b6 | 2026_07_06_0003 | pdf_download_parse_fields |
| 15 | f4a5b6c7 | 2026_07_06_0004 | report_chunks |
| 16 | g5h6i7j8 | 2026_07_06_0005 | embedding dim 384 |
| 17 | h6i7j8k9 | 2026_07_07_0001 | coverage tables |
| 18 | **i7j8k9l0** | 2026_07_11_0001 | **company_v2_rag** ← RAG dep |
| 19 | j8k9l0m1 | 2026_07_12_0001 | fusion_jobs |
| 20 | k9l0m1n2 | 2026_07_13_0001 | worker_foundation |
| 21 | l0m1n2o3 | 2026_07_14_0001 | shadow_observation_index |
| 22 | m1n2o3p4 | 2026_07_26_0001 | pi_real_provider_audit |
| 23 | n2o3p4q5 | 2026_07_26_0002 | mvp_release_tables |
| 24 | o3p4q5r6 | 2026_07_26_0003 | mvp_r12_invite_security |
| 25 | 37cd8a42 | 2026_07_27_1120 | fix invite redeemed_by uuid |
| **26** | **p4q5r6s7t8u9** | **2026_07_28_0001** | **add_email_verified_at ← HEAD** |

RAG-critical: migrations 12 (`report_documents`) and 18 (`company_v2_rag_documents`, `company_v2_rag_chunks`) must both be applied for G5 to be possible.

---

## G2 Verdict

**BLOCKED** — awaiting G1 (database reachable).

*Update this file after `alembic current` matches `alembic heads`.*
