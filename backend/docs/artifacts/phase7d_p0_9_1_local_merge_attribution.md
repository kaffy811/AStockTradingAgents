# Phase 7D-P0.9.1 Local Merge Failure Attribution

## Decision

`LOCAL_MERGE_REMEDIATION_READY`

The P0.9 HOLD is a process-gate failure caused by an intrinsic history-topology merge conflict. It is not caused by candidate corruption, candidate-tree drift, scope pollution, or pre-existing worktree changes entering the candidate.

No code, commit, index entry or branch pointer was changed in P0.9.1. A detached worktree was created only to read candidate `4434fc60...`.

## First failed gate

- Gate: `STOP_ON_MERGE_CONFLICT`
- Command:

```text
git merge --no-ff --no-edit -m "merge(release): integrate company data and stock research" 4434fc60feb652a7806d286f54c2175b979cbb4b
```

- Exit code: `1`
- Complete original error:

```text
Auto-merging backend/app/agents/chat_orchestrator.py
CONFLICT (content): Merge conflict in backend/app/agents/chat_orchestrator.py
Automatic merge failed; fix conflicts and then commit the result.
```

P0.9 required stopping and reporting when any conflict occurred. Although P0.9 subsequently resolved the file from the approved candidate and created a merge commit whose tree exactly matches the candidate, that later technical result cannot erase the earlier procedural failure.

There was an earlier sandbox-permission pre-attempt error:

```text
fatal: update_ref failed for ref 'ORIG_HEAD': cannot lock ref 'ORIG_HEAD': Unable to create '/Users/kaffy/Documents/TradingAgents/.git/ORIG_HEAD.lock': Operation not permitted
```

That pre-attempt did not change HEAD and was successfully rerun with authorized Git metadata access. It is environmental evidence, not the gate responsible for the final P0.9 HOLD.

## Current identities

| Object | Commit | Tree |
|---|---|---|
| Current branch `release/demo-staging` HEAD | `98c111b684cb19de0e0e92cb46e1d675ef3e8d0a` | `24a9961639dd7d8388fe8353a6e2e7eb8b955f03` |
| Target `release/demo-staging` | `98c111b684cb19de0e0e92cb46e1d675ef3e8d0a` | `24a9961639dd7d8388fe8353a6e2e7eb8b955f03` |
| Candidate P0.7 | `4434fc60feb652a7806d286f54c2175b979cbb4b` | `24a9961639dd7d8388fe8353a6e2e7eb8b955f03` |

Current HEAD parents:

```text
c4a506c0c2fdcf985d779f005788f4059066605a
4434fc60feb652a7806d286f54c2175b979cbb4b
```

The current commit tree is byte-identical to the candidate tree. All five required P0.1/P0.2/P0.4/P0.6/P0.7 SHAs are ancestors of current HEAD.

## Candidate graph from release baseline

```text
* 4434fc6 fix(research-copilot): fail closed unapproved theme queries
* 1c675f7 fix(stock-research): validate grounded eod numeric claims
* c812d4d fix(company-api): enforce public response allowlists
* 27b76bd feat(company-data): add grounded tushare eod gateway
* cdeada4 fix(company): allow safe public financial history
o 5dad722 merge(release): integrate approved AI chat trust slice
```

Original P0.4 `c4a506c...` and replay P0.4 `c812d4d...` both have tree `d821f6804a4a57dace95664e2249024e3d48b717`. They are content-equivalent but not ancestor-related. Preserving both the original P0.1/P0.2/P0.4 SHAs and replay-based P0.6/P0.7 SHAs therefore requires a two-parent history join; Git's three-way merge reports one overlapping-content conflict.

Read-only `git merge-tree --write-tree c4a506c... 4434fc60...` reproduced:

```text
100644 6feaa136d6e7fbbb39ab66e8fe3c4a56d4cc4deb 1 backend/app/agents/chat_orchestrator.py
100644 282375e7b6ce14db7d1ebd692a53ad147ffb5610 2 backend/app/agents/chat_orchestrator.py
100644 605e03f3869b4dafc5d83b5ff197a943158e6d45 3 backend/app/agents/chat_orchestrator.py

Auto-merging backend/app/agents/chat_orchestrator.py
CONFLICT (content): Merge conflict in backend/app/agents/chat_orchestrator.py
```

Exit code: `1`. No conflict was resolved in P0.9.1.

## Complete baseline-to-candidate diff

23 files, 2,153 insertions, 20 deletions; `git diff --check` passes.

```text
A HKNA/update_report/update_137.md
A HKNA/update_report/update_138.md
A HKNA/update_report/update_140.md
A HKNA/update_report/update_142.md
M backend/app/agents/chat_orchestrator.py
M backend/app/datasource/tushare_client.py
M backend/app/routers/company_v2_debug.py
A backend/app/services/stock_eod_numeric_validation.py
A backend/app/services/tushare_eod_gateway.py
A backend/docs/artifacts/phase7d_p0_2_company_and_stock_research_matrix.md
A backend/docs/artifacts/phase7d_p0_2_tushare_eod_gateway.md
A backend/docs/artifacts/phase7d_p0_2_tushare_eod_runtime.json
A backend/docs/artifacts/phase7d_p0_4_public_response_allowlist.md
A backend/docs/artifacts/phase7d_p0_4_public_response_allowlist_matrix.json
A backend/tests/fundamental/test_phase7d_p0_1_public_company_history.py
A backend/tests/fundamental/test_phase7d_p0_2_tushare_eod_gateway.py
A backend/tests/fundamental/test_phase7d_p0_6_stock_eod_numeric_validation.py
A backend/tests/test_phase7d_p0_7_theme_fail_closed.py
M frontend/src/api/companyV2.js
A frontend/src/tests/phase7dP01CompanyModuleIsolation.test.js
A frontend/src/tests/phase7dP02TushareEodCompanyPage.test.js
M frontend/src/tests/researchFulfillment.test.js
M frontend/src/views/CompanyV2View.vue
```

## Worktree attribution

Before this phase's three requested artifacts are created, `git status --short` contained:

- Tracked, unstaged changes: 6.
  - `HKNA/update_report/update_142.md` — originally an untracked local file that collided with the candidate path; P0.9 preserved and restored its original content as an unstaged tracked-path modification.
  - `backend/Dockerfile`
  - `backend/app/main.py`
  - `backend/app/services/report_embedding_provider.py`
  - `backend/pyproject.toml`
  - `backend/uv.lock`
- Untracked files: 109.
- Staged files: 0 (`git diff --cached --quiet` exit code `0`).
- Existing P0.9 temporary artifacts among the 109 untracked files:
  - `backend/docs/artifacts/phase7d_p0_9_local_release_integration.md`
  - `backend/docs/artifacts/phase7d_p0_9_local_release_manifest.json`
  - `HKNA/update_report/update_139.md`
- P0.9.1 adds only the three requested untracked review artifacts listed below.

The candidate diff does not touch the five pre-existing dirty business/config files. The restored `update_142.md` local SHA-256 remains `ece533a81e46eb525f4342d8e7789cb0632be848e9adcd8715996f080c318134`. No dirty file is staged.

## Isolated candidate availability

Detached worktree: `/private/tmp/phase7d_p0_9_1_candidate`

```text
HEAD  4434fc60feb652a7806d286f54c2175b979cbb4b
tree  24a9961639dd7d8388fe8353a6e2e7eb8b955f03
status clean
```

This proves the candidate commit can be checked out, read and hashed independently of the primary worktree. No branch pointer was created or changed.

## Scope contamination check

The baseline-to-candidate path scan contains no Dockerfile/Compose, dependency manifest, lockfile, migration, `.env`, global auth or global Report RAG numeric-validator path. Added-line scans found no Token/API-key/secret value, Authorization/Bearer value, credential-bearing database URL, Tushare news implementation or production call to AKShare/Eastmoney/Sina/Tencent.

References to Eastmoney/Sina/Tencent in the diff are zero-call runtime evidence or negative tests. The Tushare client change removes token-prefix logging and adds only approved EOD methods. `stock_eod_numeric_validation.py` is request-local and separate from the global Report RAG validator.

## Root-cause classification

- Candidate commit missing/corrupt: no.
- Candidate final tree incorrect: no.
- Baseline-to-candidate scope pollution: no.
- Primary worktree dirty changes entered candidate/tree: no.
- Replay content drift: no; original and replay P0.4 trees are identical.
- Merge conflict: yes, exactly one path.
- Root cause: parallel, content-equivalent replay histories plus later edits to the same orchestrator file, combined with the requirement that both sets of original SHAs remain ancestors.

## Minimal remediation

Preferred minimal path: Owner explicitly accepts existing local merge commit `98c111b...` as the integration result after reviewing this attribution. It already has both required parents, contains every required SHA, has the exact approved candidate tree, an empty staging area, preserved dirty files, passing P0.9 regressions, and no push/deployment. Acceptance requires no Git or worktree mutation.

If Owner does not accept that commit because the stop-on-conflict rule was violated, a separate authorization is required to repair the `release/demo-staging` pointer and recreate the integration in an isolated clean worktree. That operation necessarily changes a branch pointer and/or creates a replacement commit and is outside P0.9.1. Do not reset, amend, force-update, push or deploy without that explicit instruction.
