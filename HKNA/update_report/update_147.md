# Phase 7D-P0.9.1 local merge attribution

Final decision: `LOCAL_MERGE_REMEDIATION_READY`.

- First failed gate: `STOP_ON_MERGE_CONFLICT`.
- Original merge exited `1` with a content conflict in `backend/app/agents/chat_orchestrator.py`.
- Read-only `git merge-tree` reproduced the same single-file conflict with exit `1`.
- Current `release/demo-staging` HEAD is `98c111b...`; its tree exactly equals candidate tree `24a996...` and contains all five required SHAs.
- Candidate `4434fc60...` was successfully checked out into a clean detached worktree and independently produced tree `24a996...`.
- Baseline-to-candidate diff remains 23 files and contains no prohibited Docker/dependency/lockfile/migration/credential/provider-config/Tushare-news/public-scraper/global-RAG-validator change.
- Primary worktree has 6 tracked unstaged changes, 109 pre-existing untracked files before this phase's artifacts, and 0 staged files. Dirty files did not cause the merge conflict or enter the candidate tree.
- Root cause: two parallel content-equivalent P0.1–P0.4 histories, followed by P0.6/P0.7 edits to the same orchestrator file, while requiring both histories' SHAs to remain ancestors.
- Minimal remediation: Owner may explicitly accept existing local merge commit `98c111b...`; this requires no further Git mutation. Otherwise separate authorization is required to repair the branch pointer and recreate integration in an isolated worktree.
- No code change, commit, branch-pointer update, push, merge, deployment, Docker build, migration, rollout or destructive Git action was performed in P0.9.1.
