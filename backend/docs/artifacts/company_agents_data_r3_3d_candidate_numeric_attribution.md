# Phase 6W-R3.3D — Controlled Candidate Runtime & Numeric Failure Attribution

Date: 2026-08-27 (America/New_York)

## Decision

`ROOT_CAUSE_NOT_READY`

Traffic: `HOLD_1_PERCENT`

The controlled runtime did not start. The mandatory isolated-database preflight failed before any candidate container, Redis namespace, network, port, trace, or Company V2 request was created.

## Candidate image integrity

- Tag: `tradingagents-backend:rc-b055da8`
- Image ID / local digest: `sha256:fb9b69812eec90fd280eaf36c2a2d557a129f4ff25afa62e67f9787f969fba29`
- OCI revision: `b055da8495c54bb37625f0b0e0f94b4d4a627de2`
- Created: `2026-08-27T23:52:59.229679127Z`
- Pure-commit content provenance: previously passed in `company_agents_data_r3_3c_release_image_provenance.md`.

No candidate runtime container was created, so container ID, runtime source hash, health, trace-module runtime state, port binding, and Redis namespace are `NOT_CREATED — PREFLIGHT_BLOCKED`. This is not presented as runtime acceptance.

## Isolated database preflight

The only explicitly isolated local database discovered was the existing staging service defined by `docker-compose.staging.yml`:

- Container: `tradingagents-p125-staging-postgres-1`
- Compose project: `tradingagents-p125-staging`
- Compose service: `postgres`
- Image: `postgres:16-alpine`
- Created: `2026-08-10T13:56:25.941790044Z`
- State: running / healthy
- Host exposure: loopback-only `127.0.0.1:15432`
- Network: `tradingagents-p125-staging_net`
- Volume: `tradingagents-p125-staging_postgres_data`
- Repository definition explicitly identifies it as isolated staging and not shared with dev/prod.

The required read-only migration query was executed inside that database container using its existing internal connection identity; no credential value was printed:

```sql
select version_num from alembic_version;
```

Direct result:

```text
ERROR: relation "alembic_version" does not exist
```

Therefore the database cannot prove schema revision `q5r6s7t8u9v0`. Absence of the Alembic version table fails the phase's mandatory condition. The remaining read-only data checks in that command were not executed because `ON_ERROR_STOP=1` stopped at the first failing statement.

No production database was inspected or connected. No migration or schema write was performed. The candidate was not pointed at this unqualified database.

## Runtime sample set

| Required | Executed | Reason |
|---:|---:|---|
| 15 unique serial Company V2 questions | 0 | Mandatory isolated DB revision unavailable |
| S0–S8 traces | 0 | Candidate runtime intentionally not started |
| Numeric-invalid tokens attributed | 0 | No runtime sample exists |

No automatic retry, sample selection, cache manipulation, user traffic, or production trace write occurred.

## S0–S8 coverage

Coverage is `0/15`, not because the trace implementation failed, but because the environment gate stopped before S0 request acceptance. There are no trace IDs, request IDs, final answers, unsupported tokens, token sentences, or first-observed stages to classify.

## Attribution matrix

| Classification | Token occurrences | Directly proven runtime samples |
|---|---:|---:|
| `D1_COMPACTOR_OMISSION` | 0 | 0 |
| `D2_RETRIEVAL_COVERAGE_GAP` | 0 | 0 |
| `D3_CITATION_METADATA_LEAK` | 0 | 0 |
| `D4_UNSUPPORTED_FINANCIAL_CLAIM` | 0 | 0 |
| `D5_DATE_PERIOD_UNIT_OR_FORMAT_MISMATCH` | 0 | 0 |
| `D6_STRUCTURED_FACTS_EVIDENCE_VERSION_MISMATCH` | 0 | 0 |
| `D7_OTHER_NON_FINANCIAL_METADATA` | 0 | 0 |
| `UNCONFIRMED` | 0 | 0 |

Zero counts mean no sample was run; they do not mean the causes were disproved. No numeric remediation is authorized.

## D3 and safety gates

- D3 regression runtime check: `NOT_RUN — PREFLIGHT_BLOCKED`
- Raw chunk ID in candidate answer: no candidate answer exists
- Numeric guard bypass: no request executed
- Report-year mismatch: no request executed
- Secret leakage: no secrets were read or printed; environment inspection listed key names only
- Production traffic exposure: none

## Production-container preservation

Final read-only identity check:

- Container ID: `c9567bfdfec4892823d7a5febd09d1cba2e4fac2ba6dd300082f74bfd0140bee`
- Image: `sha256:48a50ce2435e379c46f0ed0afa1878a5f9c8e9f223dcb418bb4bbc1a944987db`
- Created: `2026-08-23T01:34:13.297204344Z`
- Started: `2026-08-23T01:34:14.117434553Z`
- State: running
- Bind mounts: none

No stop, restart, replacement, deployment, compose lifecycle operation, or traffic change was performed. No container with the reserved R3.3D naming prefix exists.

## Next step requiring Owner authorization

Provision or identify a non-production database that:

1. has an independently verifiable `alembic_version = q5r6s7t8u9v0`;
2. contains the official `report_id=17`, 2024 annual report and its indexed RAG chunks;
3. permits isolated candidate trace writes;
4. is explicitly not the production database.

Creating/upgrading such a database would require schema/data operations expressly forbidden in this phase. After Owner supplies that environment or separately authorizes its preparation, R3.3D can restart from the preflight and run the fixed 15-query population once.

No code was changed, committed, pushed, deployed, or released. Final decision: `HOLD_1_PERCENT`.
