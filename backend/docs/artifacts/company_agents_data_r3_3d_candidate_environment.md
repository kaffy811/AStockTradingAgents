# Phase 6W-R3.3D-Prep — Isolated Candidate Verification Environment

Date: 2026-08-27 (America/New_York)

Decision: `CANDIDATE_ENVIRONMENT_NOT_READY`

Traffic: `HOLD_1_PERCENT`

## Outcome

Owner authorization was used to create a new disposable PostgreSQL/pgvector container, Redis container, and dedicated network. The candidate image's complete Alembic upgrade failed deterministically on the empty database before the backend was started. No workaround, schema stamp, manual table creation, report ingestion, trace write, production access, or user request was performed. The failed disposable environment and its anonymous volumes were then removed.

## Candidate image

- Tag: `tradingagents-backend:rc-b055da8`
- Image ID / digest: `sha256:fb9b69812eec90fd280eaf36c2a2d557a129f4ff25afa62e67f9787f969fba29`
- OCI revision: `b055da8495c54bb37625f0b0e0f94b4d4a627de2`
- E1 image revision: PASS
- The image was used only as an ephemeral Alembic runner on the isolated network.
- Candidate backend service was not started after the migration gate failed.

## Disposable isolation identity

| Resource | Identity | Isolation evidence | Final state |
|---|---|---|---|
| Network | `tradingagents-r33d_net` / `0425af97e5b50474bdcbba4f650889c70d1d7c975322502bd5b7f76778d3c078` | Dedicated bridge; no production container attached | Removed |
| PostgreSQL | `r33d-postgres` / `1a91df069d016e06fb7997793d5838b3165ce6c6f8fc7b0f24b2c8f55e1ba081` | Only candidate network; `5432/tcp` had no host binding | Removed with anonymous volume |
| PostgreSQL image | `pgvector/pgvector:pg16` / `sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b` | New empty local database, not reused staging/prod | Image retained locally |
| Redis | `r33d-redis` / `9f93d93ba704820f22f84329f634fa8b0e4c0a4d148d5775773903c327f4eb95` | Only candidate network; `6379/tcp` had no host binding | Removed with anonymous volume |
| Redis image | `redis:7-alpine` / `sha256:6ab0b6e7381779332f97b8ca76193e45b0756f38d4c0dcda72dbb3c32061ab99` | Independent empty cache | Existing image retained |
| Backend | not created | Stopped at migration gate | Not created |

PostgreSQL readiness returned `accepting connections`; Redis returned `PONG`. Neither service exposed a host port, used a production network, or reused a production volume/cache namespace.

## Migration evidence

Required: `alembic current == alembic heads == q5r6s7t8u9v0`.

The exact candidate image ran Alembic against empty `tradingagents_r33d` on the dedicated network. Isolated trust authentication was confined to the non-host-exposed bridge; no production connection string was used.

Observed sequence:

```text
upgrade -> 4b49004d01a6  baseline existing schema
upgrade 4b49004d01a6 -> 76fe066db8b1  add stock master
upgrade 76fe066db8b1 -> 3a2f8b4c1d9e  add stock_name to analysis_reports
```

Direct failure:

```text
asyncpg.exceptions.UndefinedTableError: relation "analysis_reports" does not exist
ALTER TABLE analysis_reports ADD COLUMN stock_name VARCHAR(128)
```

The failed transaction did not leave an `alembic_version` table. A read-only post-failure query returned `relation "alembic_version" does not exist`.

This directly proves that the candidate migration chain does not bootstrap the required schema from a genuinely empty PostgreSQL database: the baseline represents an existing-schema baseline and does not create `analysis_reports`, while the later revision assumes it exists.

No `create_all`, manual SQL, schema copy, Alembic stamp, revision skip, migration edit, or production schema export was used. E3: FAIL.

## CNINFO ingestion and trace verification

Both were not started because E3 failed.

| Required evidence | Result |
|---|---|
| Official CNINFO URL / PDF SHA-256 | Not acquired |
| Report document ID / parse status | Not created / not run |
| Chunk count / active index | Not available |
| Ingestion timestamp | Not available |
| Trace table write/read | Not run |
| S0–S8 readability | Not run |

No production report/chunk was copied, no mock or synthetic report was created, and no manual chunk insert occurred.

## Gate matrix

| Gate | Result | Direct evidence |
|---|---|---|
| E1 candidate revision `b055da8` | PASS | OCI label and image digest verified |
| E2 no backend source bind mount | NOT RUN | Backend not created; migration runner had no source mount |
| E3 DB at `q5r6s7t8u9v0` | FAIL | Empty-DB Alembic upgrade failed on missing `analysis_reports` |
| E4 Redis isolated | PASS for created resource | Dedicated container/network, no host port; later removed |
| E5 official 2024 report present | NOT RUN | Blocked by E3 |
| E6 CNINFO ingestion complete | NOT RUN | Blocked by E3 |
| E7 trace tables writable/readable | NOT RUN | Blocked by E3 |
| E8 no production access/change | PASS | Dedicated resources only; production identity unchanged |
| E9 no secret output | PASS | No secret value logged or written to artifact |

## Production preservation

- Container ID: `c9567bfdfec4892823d7a5febd09d1cba2e4fac2ba6dd300082f74bfd0140bee`
- Image: `sha256:48a50ce2435e379c46f0ed0afa1878a5f9c8e9f223dcb418bb4bbc1a944987db`
- Created: `2026-08-23T01:34:13.297204344Z`
- Started: `2026-08-23T01:34:14.117434553Z`
- Status: running
- Bind mounts: none

These values match the pre-phase identity. No production container was stopped, restarted, replaced, attached to the candidate network, or exposed to candidate traffic. Final discovery confirmed no remaining `r33d` container or `tradingagents-r33d` network.

## Entry decision for R3.3D attribution

The environment does not authorize the 15-query numeric-attribution run. A separate Owner-approved remediation is required for the empty-database bootstrap contract. It must resolve the baseline-versus-existing-schema migration assumption without using production schema/data, then recreate the environment from empty and prove `alembic current == alembic heads == q5r6s7t8u9v0` before ingestion.

No production code, migration, validator, prompt, retrieval, cache, or timeout was modified. No commit, push, deployment, production migration, or traffic change occurred.

Final state: `CANDIDATE_ENVIRONMENT_NOT_READY` / `HOLD_1_PERCENT`.
