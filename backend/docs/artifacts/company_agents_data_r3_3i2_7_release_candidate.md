# Phase 6W-R3.3I.2.7 — Minimal Release Integration Candidate

## Final decision

```text
RELEASE_MIGRATION_CONTRACT_NOT_READY
Traffic: HOLD_1_PERCENT
```

The minimum code chain replayed cleanly in an isolated worktree, but both required fresh-database migration paths failed before reaching the new trace migration. Per the phase gate, testing, image construction, and Q3 were not run.

## Workspace boundary

- Main workspace: `/Users/kaffy/Documents/TradingAgents`
- Main HEAD / branch: `b055da8495c54bb37625f0b0e0f94b4d4a627de2` / `release/demo-staging`
- Isolated worktree: `/private/tmp/tradingagents-r33i2-7-rc.r5I4uS`
- Isolated branch: `r33i-release-integration-candidate`
- Integration HEAD: `9f4b516b7c9282bb7ae68d282a262d68cfd21c02`
- Main historical dirty files remained untouched, including `backend/Dockerfile`, `backend/app/main.py`, `backend/app/services/report_embedding_provider.py`, `backend/pyproject.toml`, and `backend/uv.lock`.
- The isolated worktree was clean after replay; `git diff --check` passed.

## Minimum dependency-chain audit

Merge base and release baseline were both `b055da8495c54bb37625f0b0e0f94b4d4a627de2`. The original ancestry also contains forbidden commit `79323b7`; it was not replayed.

| Original commit | Purpose | Required | Migration dependency | Out-of-scope files |
|---|---|---:|---:|---:|
| `5e9977a` | Persist structured evidence provenance and trace inputs | Yes | Adds trace migration based on release head `q5r6s7t8u9v0` | No |
| `28870a` | Derived facts and canonical citation evidence boundary | Yes | No additional migration | No |
| `154c65c` | Request-local `ratio_percentage` formula-span validation | Yes | No additional migration | No |
| `79323b7` | Vector/empty-database portability work | No; explicitly excluded | Contains unrelated bootstrap/vector migration work | Yes for this phase |

Replay results, in order:

| Original | Isolated integration commit | Result |
|---|---|---|
| `5e9977a` | `cecea67` | Clean cherry-pick, no conflict |
| `28870a` | `fb6610c` | Clean cherry-pick, no conflict |
| `154c65c` | `9f4b516` | Clean cherry-pick, no conflict |

The release-to-candidate diff contains only the audited trace/provenance migration and model/service changes, derived-fact/citation integration, strict-serial harness, targeted tests, and their phase artifacts/update reports. It contains no Dockerfile, dependency lock/configuration, embedding provider, warmup, vector migration, or `79323b7` content.

## Migration contract

Two fresh isolated PostgreSQL 16/pgvector containers were used:

| Path | Container | Database | Start | Target | `alembic heads` | First upgrade result | Repeat result |
|---|---|---|---|---|---|---|---|
| A: release baseline → candidate | `e57be907e53172057f04b678b0a0720cc00b7d6e328f85324a6f5a29d2b959db` | `integration_a`, localhost isolated port 15440 | Empty DB, release migration tree | release `q5r6s7t8u9v0`, then candidate `r6s7t8u9v0w1` | Release: `q5r6s7t8u9v0` | Failed before baseline head | Not executed after fail-stop |
| B: empty DB → candidate head | `beeafd1b1748f92e4ecb79032df8b13e5ff4d1b516a19ab68d101a513e996209` | `integration_b`, localhost isolated port 15441 | Empty DB | `r6s7t8u9v0w1` | Candidate: `r6s7t8u9v0w1` | Failed before candidate head | Not executed after fail-stop |

Both first upgrades failed deterministically at legacy migration `3a2f8b4c1d9e`:

```text
asyncpg.exceptions.UndefinedTableError: relation "analysis_reports" does not exist
ALTER TABLE analysis_reports ADD COLUMN stock_name VARCHAR(128)
```

After rollback, `alembic current` reported no installed revision for the candidate empty database. The failure precedes the R3.3I trace migration, so that migration was never exercised. A second mutating upgrade was not run because the phase requires stopping on contract failure; no migration was edited, stamped, skipped, or bypassed.

This demonstrates that the requested minimal chain cannot satisfy the two fresh-database paths on the current release baseline without separate bootstrap remediation. The forbidden `79323b7` was not introduced to conceal or bypass that result.

## Downstream gates

Because Step 3 failed:

- 48 credibility tests: not run.
- Migration contract tests beyond the two direct paths: not run.
- Import/static checks: not run.
- Integration candidate image: not built.
- Image OCI/source/no-bind verification: not applicable.
- Integration Q3: not run.
- Runtime regression/timeout assessment: not applicable.

The isolated branch retains only the three replay commits for audit; it was not merged into `release/demo-staging`.

## Environment and safety evidence

- Isolated migration containers used dedicated databases and localhost ports; no production DB or Redis connection was used.
- Existing production backend remained `c9567bfdfec4` (`tradingagents-backend-1`, up 7 days) during the audit.
- No production container was restarted or replaced.
- No production migration or production data write occurred.
- No push, merge, deployment, or traffic expansion occurred.

## Final status

```text
RELEASE_MIGRATION_CONTRACT_NOT_READY
HOLD_1_PERCENT
```
