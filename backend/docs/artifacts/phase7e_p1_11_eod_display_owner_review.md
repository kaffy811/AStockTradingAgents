# Phase 7E-P1.11 EOD Display Normalization Owner Release Review

## Decision

`OWNER_RELEASE_APPROVAL_READY`

This is a read-only technical release review. No existing code or commit was changed and no push, merge, deployment, restart, migration, cleanup, or traffic action was performed.

## Candidate identity

- Baseline: `1ec336dbea817627ce49ef54da3dedfa84a7aef9`
- Candidate: `dbf2073eb06a4206dea604a7156acae461c6bb35`
- Candidate parent: the baseline exactly
- Candidate tree: `e4eaacd0377422df0c1a22dd0b0e358f8555cd95`
- `merge-base --is-ancestor`: PASS

The diff contains 7 files, 442 insertions, and 8 deletions: one display service, the minimal orchestrator display projection connection, two test files, and three P1.9 audit/update files.

## Scope review

The application delta only introduces deterministic EOD display projection and its failure metadata. Existing canonical evidence is passed into `make_request_local_evidence`; the new service copies that evidence and appends display metadata. The answer renderer consumes `display_value` and `display_unit`.

No diff exists in Tushare Gateway/provider retrieval, the numeric-validator implementation, symbol resolver, route selection, cache or timeout code, news, RAG, Docker/Compose, dependencies/lockfiles, environment/Token configuration, database/migrations, or Nginx. Direct baseline/candidate blob checks also match for the Gateway, numeric validator, resolver, Nginx file, and backend/frontend lockfiles.

## Display contract

The backend uses `Decimal`, deterministic multiplication, and `quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)`:

| Canonical | Factor | Display |
|---|---:|---|
| `CNY` | 1 | 元 |
| `%` | 1 | % |
| `multiple` | 1 | 倍 |
| `CNY_thousand` | 0.00001 | 亿元 |
| `CNY_10k` | 0.0001 | 亿元 |
| `lot` | 0.0001 | 万手 |

`7,616,584.07 lot × 0.0001 = 761.658407 万手`, rounded to `761.66 万手`. The positive test asserts this exact result and separately asserts that the unit does not contain “股”, preventing the tenfold error and lot/share confusion.

Every accepted projection retains `canonical_value`, `canonical_unit`, `source`, `as_of`, `report_period`, and `request_local_evidence_id`, and adds `display_value`, `display_unit`, `rounding_policy`, and `evidence_id`. Answer construction uses only label, display value/unit, date/report period, and public source. It does not interpolate evidence IDs or request-local IDs. Machine units and unformatted high-precision canonical representations are not rendered; where an identity conversion naturally has the same numeric value (for example `5.55 CNY -> 5.55 元`), that equality is the deterministic display result, not raw metadata leakage.

Unknown or mismatched units fail closed. Present rejected facts result in controlled `partial`/`unavailable`, and their raw value is omitted. Wrong rounding and magnitude remain rejected by the unchanged request-level validator.

## Verification

- Candidate P1.9 record: backend related 108 passed; frontend targeted 24 passed; frontend full 769 passed; production build, compile, JSON, secret scan, and diff check passed.
- Independent owner-review backend subset: 30 passed after supplying only in-memory/non-secret fixture Settings.
- Independent frontend fulfillment subset: 16 passed.
- Independent full frontend run: 70 files / 769 tests passed with `maxWorkers=1`; zero worker timeout.
- Independent production build: PASS (971 modules; only the pre-existing large-chunk advisory).
- Python compile, JSON validation, candidate `git diff --check`, and secret scan: PASS.

For audit completeness, the first backend invocation lacked required test Settings and stopped at import with eight missing-settings errors. The first isolated frontend copy omitted the sibling candidate backend path used by five source-inspection tests and therefore produced five `ENOENT` failures. Neither reached a failing business assertion. After correcting only the temporary harness environment, backend passed 30/30 and frontend passed 769/769.

## Fixture runtime

P1.10 executed all three queries in a candidate backend container using committed sanitized fixtures and `Mounts=[]`:

- `CN/000725 公司资料 + EOD`: fulfilled, 5/5 checked claims.
- `贵州茅台近期情况`: fulfilled, 18/18 checked claims.
- `600519 财务指标、ROE、估值`: fulfilled, 18/18 checked claims.

Each returned `numeric_validation.valid=true` and `unsupported_tokens=[]`. LLM, live Tushare, Tushare news, AKShare, Eastmoney, Sina, and Tencent calls were all zero.

## Pure-image evidence

| Image | Digest | Platform | OCI revision | Mounts |
|---|---|---|---|---|
| backend | `sha256:265d76aa96bcae741de7af4f9797d56069d13629259558f4de1a6cf0c68d9961` | `linux/amd64` | candidate full SHA | `[]` |
| frontend | `sha256:179b56bdee4c0d19e0f58d4abd668a6c9a83ec8a717e588d419401fee5f638c8` | `linux/amd64` | candidate full SHA | `[]` |

Candidate/image SHA-256 values match for `chat_orchestrator.py`, `stock_eod_display.py`, and the frontend Nginx artifact. Image Config.Env, labels, and full histories contain no business Token, Authorization value, Tushare credential, or complete database connection string.

## Owner boundary

The candidate is technically ready to request release integration. This review does not itself authorize or perform merge, push, image transfer, or deployment.
