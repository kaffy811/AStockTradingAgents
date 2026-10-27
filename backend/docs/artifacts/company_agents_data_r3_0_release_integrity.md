# Phase 6W-R3.0 — Release Integrity Gate

**Generated:** 2026-08-14  
**Phase:** R3.0 — Production 1% Canary Release

---

## Step 1 — Git Release Integrity

### Branch
```
release/demo-staging
```

### HEAD SHA
```
3c30787db82bc2a6de14042bbda2895f64f1b623
```

Required: `3c30787` — **MATCH**

### HEAD Commit
```
fix(report-agent): align production timeout budget + fix numeric validation false positives
 backend/app/agent/report_chat_copilot_agent.py     | 140 +++++-
 backend/app/agent/report_context.py                |   6 +-
 backend/app/agents/specialist_analysis_utils.py    |  10 +-
 backend/docs/artifacts/.../r2_6_e2e_optimization.md| 181 ++++
 backend/tests/test_phase6w_r2_6_synthesis_optimization.py | 484 +++
 5 files changed, 808 insertions(+), 13 deletions(-)
```

### Working Tree State
```
?? (untracked) backend/docs/artifacts/company_agents_data_r1_7_* (prior phases)
?? (untracked) backend/docs/artifacts/company_agents_data_r2_1_*
?? (untracked) backend/docs/artifacts/company_agents_data_r2_2_*
?? (untracked) backend/docs/artifacts/company_agents_data_r2_3_*
?? (untracked) backend/docs/artifacts/company_agents_data_r2_4_final_go_gate.md
?? (untracked) backend/docs/artifacts/company_agents_data_r2_5_final_go_gate.md
?? (untracked) backend/docs/artifacts/company_agents_data_r2_*.md (prior phase docs)
?? (untracked) memory/project_phase6w_r14_staging_smoke.md
```

**No tracked file modifications.** All untracked items are read-only documentation artifacts from prior phases or memory files. No uncommitted business-code changes.

### Test Baseline
```
R2.6 tests: 18/18 PASS
Full regression: 8,722 PASS / 21 pre-existing FAIL / 15 SKIP
New failures introduced by R2.6: 0
```

Pre-existing failures are snapshot-assertion tests from phases P127/P131/P132 (stale count values, schema renames). Unrelated to R2.6 changes.

### Release Candidate Status
```
RELEASE CANDIDATE — GO
```

R2.6 resolved all G1–G14 gate blockers. Commit `3c30787` is the sole release candidate. No amend or rewrite of history performed.

---

*No business logic changes. No migration. No secret printed in full.*
