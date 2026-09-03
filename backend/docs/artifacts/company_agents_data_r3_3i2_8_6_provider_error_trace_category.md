# Phase 6W-R3.3I.2.8.6 — Provider Error Trace Category Propagation Repair

## Final status

`PROVIDER_ERROR_TRACE_CATEGORY_READY`

Traffic remains `HOLD_1_PERCENT`.

No real Q3 or LLM request was executed.

## Workspace boundary

- Clean temporary worktree: `/private/tmp/tradingagents-r33i2-8-6-provider-trace`.
- Branch: `r33i-provider-error-trace-category`.
- Base HEAD: `d0290990ea98003d53a11a3e5b8495a42b3c1d2e`.
- Initial `git status --short`: empty.
- Initial and final pre-commit `git diff --check`: clean.
- Main workspace and historical dirty changes were not modified.

The implementation diff is restricted to `backend/app/agent/report_chat_copilot_agent.py`, its direct trace durability tests, this phase artifact, and `HKNA/update_report/update_114.md`.

## Loss-point attribution

Frozen pre-fix flow:

| Stage | Category value | File:line | Correct |
|---|---|---|---:|
| Provider normalizer | `connection` | `backend/app/llm/deepseek_client.py:82-87` | yes |
| Report-chat catch | hard-coded `provider_error` | pre-fix `backend/app/agent/report_chat_copilot_agent.py:1796-1798` | no |
| S6 payload builder | `provider_error` | pre-fix `backend/app/agent/report_chat_copilot_agent.py:1814` | no |
| Persisted trace row | `provider_error` | `backend/app/services/report_analysis_trace_service.py:160-172` persisted its input correctly | no upstream value |

The first category loss was the broad report-chat catch branch. It ignored `NormalizedProviderError.record` and replaced every non-empty, non-JSON, non-outer-timeout exception with the generic `provider_error`. The trace recorder did not cause the loss; it faithfully redacted and persisted the already-wrong payload.

## Minimal repair

`backend/app/agent/report_chat_copilot_agent.py:57-59,290-307` now defines a report-chat-local allowlist and `_provider_error_trace_fields()`.

The helper accepts only `NormalizedProviderError` and copies only:

```text
provider_error_category
provider_error_retryable
provider_error_http_status
provider_error_code
provider_error_reason_code
provider_error_exception_type
```

Allowed normalized categories are exactly `connection`, `http_status`, `provider_payload`, and `local_client`. An unnormalized or invalid record produces no fields and uses the legacy `provider_error` fallback.

At `report_chat_copilot_agent.py:1820-1836`, the catch branch now prefers the normalized category. At lines 1842-1855 the allowlisted values are included in the S6 payload before the existing trace recorder redaction/persistence boundary.

The resulting mapping is:

| Input | S6 category | HTTP status | Retryable |
|---|---|---:|---:|
| Normalized connection | `connection` | null | true |
| Normalized HTTP 429 | `http_status` | 429 | true |
| Normalized HTTP 401 | `http_status` | 401 | false |
| Normalized provider payload | `provider_payload` | null | false |
| Normalized unknown/local client | `local_client` | null | false |
| Legacy unnormalized exception | `provider_error` | absent | absent |

Timeout, retry, Prompt, RAG, citation, numeric validation, derived facts, and provider classification semantics were not changed. The final API status remains truthful `partial_success` after synthesis failure.

## Secret boundary

Normalized exceptions expose only the safe contract. For legacy unnormalized exceptions, report-chat now logs only category and exception type and persists a fixed `LLM 调用失败` message instead of raw exception text. A test exception containing a fake API key, Authorization/Bearer value, private provider URL, and body marker did not appear in the S6 payload.

The trace recorder's existing redaction remains defense in depth; no raw headers, URL, body, request, or provider payload was newly added.

## Tests

All tests use mocks and dummy test-only configuration. No external provider or database request was made.

| Command/suite | Collected | Passed | Failed | Skipped | Duration |
|---|---:|---:|---:|---:|---:|
| trace/category durability suite | 24 | 24 | 0 | 0 | 0.56s |
| provider normalization stream/non-stream suite | 9 | 9 | 0 | 0 | 0.16s |
| D3, derived facts, structured operands, citation and numeric regression | 28 | 28 | 0 | 0 | 0.20s |
| combined final targeted gate | 61 | 61 | 0 | 0 | 0.58s |
| `py_compile` on changed Python files | n/a | n/a | 0 | n/a | <1s |
| scoped Ruff (`--ignore F401`) | n/a | n/a | 0 | n/a | <1s |

Unscoped Ruff identified one baseline unused import at `report_chat_copilot_agent.py:2074`, outside this repair. It was not modified. The scoped check passed without new lint findings.

Tests prove:

- Connection, HTTP 429/401, provider payload, and local-client categories reach S6 unchanged.
- Optional HTTP status and retryability are preserved.
- Stream and non-stream provider classification remains identical through the existing provider suite.
- Legacy fallback is generic and does not persist the injected secret/header/body/URL.
- S8 remains `partial_success`.
- Existing D3 containment, citation, numeric validation, structured operands, and derived-fact trace fields remain green.

## Commit boundary

The independent commit message is:

```text
fix(agent-audit): preserve normalized provider error category
```

Only the report-chat trace mapping, direct tests, this artifact, and update report are eligible. No provider client, migration, Agent business strategy, Docker, dependency, or historical dirty file is included.

## Operational declarations

- No real Q3 or LLM request was executed.
- No production DB, container, Redis, or Supabase was accessed or modified.
- No push, merge, deploy, migration, or traffic expansion occurred.
- Traffic remains `HOLD_1_PERCENT`.
