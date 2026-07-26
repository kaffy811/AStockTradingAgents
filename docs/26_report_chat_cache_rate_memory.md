# Phase 6K — 问财报缓存 / 速率限制 / 会话记忆 / 运行稳定性

## Overview

Phase 6K adds production-readiness features to the Phase 6J 问财报 Q&A Copilot:

1. **Redis TTL cache** — Deduplicate identical questions; 30-minute TTL by default
2. **Sliding-window rate limiting** — 10 req/min, 100 req/hour per session/IP; Redis-backed, fail-open
3. **Session memory** — Inject prior turns per (session_id, ts_code) for conversational follow-ups
4. **Question normalization** — Whitespace collapsing, Unicode NFC, fullwidth punctuation → ASCII
5. **Prompt injection detection** — Block CN+EN jailbreak patterns before LLM call
6. **Conversation-aware query expansion** — Short follow-ups inherit keywords from prior turn

All new features fail-open: if Redis is unavailable, the system continues normally.

---

## Architecture

```
POST /api/v1/stock/{code}/report-chat
        │
        ▼
Rate Limit check (Redis INCR+EXPIRE, 429 if exceeded)
        │
        ▼
ReportChatCopilotAgent.chat(..., force_refresh, session_id, use_memory)
  ├── 0a. Normalize question (whitespace + Unicode + punctuation)
  ├── 0b. Detect prompt injection → hard reject (no LLM/RAG)
  ├── 1.  Classify question → reject (investment advice keywords)
  ├── 2.  Resolve ts_code
  ├── 3.  Cache read (skip if force_refresh=True)  ← Phase 6K
  ├── 4.  Load session memory for (session_id, ts_code)  ← Phase 6K
  ├── 5.  Expand query (conversation-aware if short follow-up)  ← Phase 6K
  ├── 6.  RAG retrieval
  ├── 7.  LLM call (with memory context injected into prompt)
  ├── 8.  FundamentalReviewAgent compliance review
  ├── 9.  Extract final answer
  └── 10. Write to cache + append turn to session memory  ← Phase 6K
```

---

## New API Request Fields

```json
{
  "question":      "公司的现金流质量如何？",
  "report_types":  ["annual"],
  "years":         [2024, 2023],
  "top_k":         6,
  "force_refresh": false,
  "session_id":    "abc123-session-id",
  "use_memory":    true
}
```

| Field | Default | Description |
|-------|---------|-------------|
| `force_refresh` | false | Bypass Redis cache; force fresh LLM call |
| `session_id` | null | Client session ID for memory isolation (CN stock only) |
| `use_memory` | true | Inject prior turns from session memory into LLM prompt |

`session_id` must match `^[a-zA-Z0-9_\-:\.]{1,128}$` — otherwise silently discarded.

---

## New API Response Fields

```json
{
  "answer": "…",
  "cache_meta": {
    "hit":         false,
    "key":         "rc:v1:600519.SH:abc12345:def012ef",
    "ttl_seconds": 1800,
    "created_at":  1752000000
  },
  "memory_meta": {
    "session_id":   "abc123",
    "turns_loaded": 2,
    "context_used": true
  },
  "safety_meta": {
    "normalized":                true,
    "prompt_injection_detected": false
  },
  "rate_limit_meta": {
    "allowed":            true,
    "limit_minute":       10,
    "limit_hour":         100,
    "remaining_minute":   9,
    "remaining_hour":     99,
    "retry_after_seconds": null
  }
}
```

---

## Rate Limit Response Headers

Every successful response includes:

```
X-RateLimit-Limit-Minute: 10
X-RateLimit-Remaining-Minute: 9
X-RateLimit-Limit-Hour: 100
X-RateLimit-Remaining-Hour: 99
```

When rate limit is exceeded (HTTP 429):

```
Retry-After: 42
```

---

## Cache Design

**Key schema:** `rc:{version}:{ts_code}:{question_hash16}:{filters_hash8}`

- `version` — from `settings.report_chat_cache_version` (default `"v1"`)
- `question_hash16` — SHA-256 of normalized question, first 16 hex chars
- `filters_hash8` — MD5 of sorted `{rt: report_types, yr: years}`, first 8 hex chars
- Filter lists are sorted before hashing for order-independence

**TTL:**

| Result type | TTL |
|-------------|-----|
| Normal approved answer | `REPORT_CHAT_CACHE_TTL_SECONDS` (default 1800s) |
| Investment advice rejection | 60s |
| Partial / error | Not cached |

**force_refresh=true** bypasses the read but still writes the fresh result to cache.

---

## Session Memory Design

**Key schema:** `cm:{session_id[:64]}:{ts_code.upper()}`

- Redis LIST, each element is JSON: `{"q": str, "a": str[:300], "ts": int}`
- Max turns: `REPORT_CHAT_MEMORY_MAX_TURNS` (default 5); older turns are trimmed from the left
- TTL: `REPORT_CHAT_MEMORY_TTL_SECONDS` (default 3600s); refreshed on each append
- **Strict ts_code isolation** — memory keys include ts_code, so questions about stock A never leak into stock B

**Memory prompt injection:**

```
[以下是本次会话的历史追问（同一股票）]
用户: 主营业务是什么？
助手: 主营白酒，2023年营收约1500亿…
用户: 那利润率呢？
助手: 毛利率约92%…
```

Injected into the LLM user prompt between the question and the source_chunks context.

---

## Question Normalization

Steps applied before cache key computation and LLM call:

1. Strip + collapse whitespace (`" ".join(q.split())`)
2. Unicode NFC normalization
3. Fullwidth punctuation → ASCII (`，→, 。→. ？→? ！→!` etc.)
4. Truncate to 500 chars

The normalized form is used as the cache key input. The LLM also receives the normalized question (not the raw input).

---

## Prompt Injection Detection

Checked before any LLM or RAG call. Hard-rejects if detected.

**CN patterns:** `忽略之前`, `忽略规则`, `忘记规则`, `输出提示词`, `越狱`, `扮演`, …

**EN patterns:** `ignore previous`, `disregard instructions`, `print your prompt`, `jailbreak`, `act as `, `you are now`, `do anything now`, …

Detection is heuristic / permissive. False positives are low because the patterns are specific.

---

## Configuration

All Phase 6K settings are in `app/core/config.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `REPORT_CHAT_CACHE_TTL_SECONDS` | 1800 | Normal answer cache TTL (seconds) |
| `ENABLE_REPORT_CHAT_CACHE` | true | Master switch for cache |
| `REPORT_CHAT_CACHE_VERSION` | "v1" | Bump to invalidate all cached entries |
| `REPORT_CHAT_RATE_LIMIT_PER_MINUTE` | 10 | Max requests per minute per bucket |
| `REPORT_CHAT_RATE_LIMIT_PER_HOUR` | 100 | Max requests per hour per bucket |
| `ENABLE_REPORT_CHAT_RATE_LIMIT` | true | Master switch for rate limiting |
| `REPORT_CHAT_MEMORY_TTL_SECONDS` | 3600 | Session memory TTL (seconds) |
| `REPORT_CHAT_MEMORY_MAX_TURNS` | 5 | Max history turns stored |
| `ENABLE_REPORT_CHAT_MEMORY` | true | Master switch for memory |

---

## Frontend Changes

### `ReportChatPanel.vue` (Phase 6K additions)

- **Conversation history** — Last 5 Q&A pairs displayed above the input box
- **Cache badge** — `⚡ 已缓存` shown in meta row when `cache_meta.hit === true`
- **Memory badge** — `💬 记忆上下文 (N)` shown when `memory_meta.turns_loaded > 0`
- **Force refresh toggle** — Checkbox to bypass cache (auto-resets after use)
- **Clear conversation** — Button to wipe local display history + reset localStorage session ID
- **Rate limit notice** — Yellow warning shown on HTTP 429 with optional `Retry-After` countdown
- **IME guard** — `compositionstart/compositionend` prevents premature Enter-to-send during CJK input
- **session_id management** — Generated once per stock code, stored in `localStorage`

### i18n additions (5 new keys per locale × 6 locales = 30 keys)

| Key | zh-CN |
|-----|-------|
| `rcp_cache_hit` | ⚡ 已缓存 |
| `rcp_memory_active` | 记忆上下文 |
| `rcp_force_refresh` | 忽略缓存重新检索 |
| `rcp_clear_history` | 清除对话 |
| `rcp_rate_limit` | 请求过于频繁，请稍后再试 |

---

## Security & Compliance

| Property | Implementation |
|----------|---------------|
| Prompt injection | Detect + hard-reject before LLM (no RAG/LLM cost) |
| Memory isolation | Redis key includes ts_code; different stocks cannot share memory |
| Cache key collision | Hashes include ts_code + question + filters; different stocks cannot hit each other's cache |
| Rate limit bucket | session_id (preferred) → IP → "anon"; cannot be spoofed without knowing target's session |
| session_id sanity | Router validates `^[a-zA-Z0-9_\-:\.]{1,128}$`; malformed IDs discarded |
| Redis failure | All features fail-open; no data lost, no error surfaced to user |

---

## Files Changed

### New
- `app/agent/report_chat_cache.py` — Redis TTL cache
- `app/services/rate_limit_service.py` — Fixed-window rate limiter
- `app/agent/report_chat_session_memory.py` — Redis LIST session memory
- `tests/fundamental/test_phase6k_report_chat_cache_rate_memory.py` — 20 tests
- `docs/26_report_chat_cache_rate_memory.md` — This document

### Modified
- `app/core/config.py` — 9 new settings
- `app/agent/report_chat_copilot_agent.py` — Normalization, injection detection, cache, memory integration
- `app/routers/report_chat.py` — `force_refresh`/`session_id`/`use_memory` params, rate limit headers
- `frontend/src/components/fundamentals/ReportChatPanel.vue` — History, badges, controls
- `frontend/src/locales/{zh-CN,en-US,zh-TW,ja-JP,ko-KR,es-ES}.js` — 5 new keys each

---

## Tests

20 tests in `tests/fundamental/test_phase6k_report_chat_cache_rate_memory.py` — **20/20 PASS**.

Full suite: 489/489 PASS (includes Phase 6J 22/22).

Frontend: build clean (195 modules).

---

## Known Limitations

- Rate limit bucket is per session_id or IP — not per authenticated user (auth layer not wired in this router)
- Session memory is not encrypted at rest (Redis plaintext); acceptable for non-PII financial Q&A content
- Cache hit responses do not re-check compliance (review_audit is from the original answer's write time)
- Memory context adds tokens to every follow-up prompt; with 5 turns × 300 chars this is ~1500 extra chars, acceptable for flash model
