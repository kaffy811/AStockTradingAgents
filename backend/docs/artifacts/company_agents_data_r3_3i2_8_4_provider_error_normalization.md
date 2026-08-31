# Phase 6W-R3.3I.2.8.4 — Safe Provider Error Normalization Repair

## Final status

`PROVIDER_ERROR_MAPPING_READY`

Traffic: `HOLD_1_PERCENT`.

## Workspace boundary

- Clean temporary worktree: `/private/tmp/tradingagents-r33i2-8-4-provider`.
- Branch: `r33i-provider-error-normalization`.
- Base HEAD: `c9072802cbccb5adf561a36574646c791d5cc560`.
- Initial `git status --short`: empty.
- Initial and final pre-commit `git diff --check`: clean.
- The main workspace and its historical dirty files were not modified.

Allowed implementation scope:

- `backend/app/llm/deepseek_client.py`
- Direct provider normalization tests
- One direct report-chat S6/S8 regression test
- This artifact and `HKNA/update_report/update_113.md`

No Agent business logic, timeout, retry count, Prompt, RAG, citation, numeric validator, migration, Docker, dependency, or lockfile was changed.

## Implementation

`backend/app/llm/deepseek_client.py:29-116` now defines an immutable, allowlisted `ProviderErrorRecord`, `NormalizedProviderError`, and the shared `normalize_provider_error()` classifier.

| Input | Category | HTTP status | Retryable | Safe reason |
|---|---|---:|---:|---|
| `APIConnectionError` | `connection` | null | true | `PROVIDER_CONNECTION_FAILED` |
| `APITimeoutError` | `connection` | null | true | `PROVIDER_TIMEOUT` |
| `APIStatusError` 401 | `http_status` | 401 | false | `PROVIDER_AUTHENTICATION_FAILED` |
| `APIStatusError` 429 | `http_status` | 429 | true | `PROVIDER_RATE_LIMITED` |
| `APIStatusError` 5xx | `http_status` | actual status | true | `PROVIDER_HTTP_ERROR` |
| SDK response validation / local payload contract error | `provider_payload` | null | false | `PROVIDER_PAYLOAD_INVALID` |
| Unknown local exception | `local_client` | null | false | `PROVIDER_CLIENT_ERROR` |

The only `status_code` read is inside the typed `APIStatusError` branch at line 96. Connection and timeout branches never probe it. No network error is converted to HTTP 500.

Provider codes are retained only when they match the bounded allowlist `[A-Za-z0-9_.-]{1,64}`. Exception messages, request objects, headers, bodies, and provider URLs are not copied into the safe record or rendered public exception.

### Non-streaming

`DeepSeekClient.chat()` at lines 163-192 maps SDK and local response-contract failures through the shared classifier and raises `NormalizedProviderError` using `raise ... from exc`. The original exception remains the internal cause, while callers/logs receive only safe classification fields.

Existing success and token-usage behavior remains unchanged. A response with missing content is now explicitly classified as `provider_payload`.

### Streaming

`DeepSeekClient._stream_generator()` at lines 291-297 uses the same classifier. Its error event contains a safe message plus the same six-field `provider_error` record. It no longer reads `APIError.status_code` generically.

## Security assertions

Mock errors deliberately contained a fake API key, Authorization header, private request body, and credential-bearing URL. Tests prove none appears in normalized exception strings or streaming error content. Raw SDK payloads are not serialized.

No real provider request or Q3 request was issued.

## Tests

All final gate commands used local mock exceptions and dummy test-only configuration. They made no provider or database connection.

| Command | Collected | Passed | Failed | Skipped / deselected | Duration | Result |
|---|---:|---:|---:|---:|---:|---|
| normalization unit suite | 9 | 9 | 0 | 0 | 0.16s | pass |
| existing DeepSeek + provider-control DeepSeek selection | 184 | 10 | 0 | 174 deselected | 0.28s | pass |
| report-chat trace/S8 suite | 19 | 19 | 0 | 0 | 0.56s | pass |
| combined normalization + C14 + trace regression | 36 | 36 | 0 | 0 | 0.55s | pass |
| `py_compile` on the three changed Python files | n/a | n/a | 0 | n/a | <1s | pass |
| Ruff on the three changed Python files after removing one pre-existing unused test import | n/a | n/a | 0 | n/a | <1s | pass |

Audit completeness: the first combined run without `AI_API_KEY`/`DEEPSEEK_API_KEY` collected 36 tests and reported 28 passed / 8 failed in 0.91s because the report-chat helper correctly stopped at its configuration gate. Re-running with dummy test-only keys produced 36/36 pass. A later root-directory command used backend-relative paths and collected 0 tests three times; it was corrected by running from `backend/`. Neither setup error invoked a provider.

The S8 regression injects `NormalizedProviderError` into the existing mocked report-chat pipeline and proves:

- S6 is failed with `REPORT_LLM_SYNTHESIS_FAILED`.
- The safe reason `PROVIDER_CONNECTION_FAILED` is retained.
- Neither `AttributeError` nor the old missing-`status_code` message appears.
- S8 returns truthful `partial_success` with `partial=true`.

## Commit boundary

The intended independent commit message is:

```text
fix(llm): normalize provider transport errors safely
```

The commit whitelist is limited to the DeepSeek client, two direct test files, this artifact, and `HKNA/update_report/update_113.md`.

## Operational declarations

- No real Q3 or LLM request was executed.
- No production database, Redis, container, or Supabase was accessed or modified.
- No timeout, retry policy, Prompt, RAG, Agent business logic, citation, or numeric validation behavior was changed.
- No push, merge, deploy, migration, or traffic expansion occurred.
- Traffic remains `HOLD_1_PERCENT`.
