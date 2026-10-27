# Phase 6W-R2.5 — Production Timeout Budget Alignment Gate Report

**Generated:** 2026-08-14  
**Branch:** release/demo-staging  
**HEAD:** a542bc18a21e465c7025d4bdc8c16f032f60736d (R2.4 + R2.5 patches applied on top)

---

## Changes Applied This Phase

### Change A — Outer Agent Timeout

**File:** `backend/app/agent/report_chat_copilot_agent.py` line 47

```diff
-_REPORT_CHAT_OVERALL_TIMEOUT_SECONDS = 45.0
+_REPORT_CHAT_OVERALL_TIMEOUT_SECONDS = 90.0
```

### Change B — SDK HTTP Timeout

**File:** root `.env`

```
PI_REAL_PROVIDER_TIMEOUT_SECONDS=60
```

(Loaded via docker-compose `env_file: ['.env']` → `deepseek_client.py` line 36: `getattr(settings, "pi_real_provider_timeout_seconds", 30.0)`)

### Preserved from R2.4

```python
_LLM_SYNTHESIS_TIMEOUT_SECONDS = 60.0  # was 25.0
```

### Diff Verification

```
 backend/app/agent/report_chat_copilot_agent.py | 4 ++-- (2 lines changed)
```

Both changes confined to the `# ── Constants ──` block. No logic change. No migration.

---

## Runtime Verification

### Container Status

| Container | Status | Ports |
|-----------|--------|-------|
| `tradingagents-redis-1` | Up (healthy) | 6379/tcp internal |
| `tradingagents-backend-1` | Up | 8000/tcp internal |
| `tradingagents-frontend-1` | Up | 0.0.0.0:80→80/tcp |

### Env Var Confirmed in Container

```
PI_REAL_PROVIDER_TIMEOUT_SECONDS=60
```

Verified via `docker compose exec backend printenv`.

---

## G6 — E2E Financial Query Results

**Query:** "贵州茅台2024年财报表现如何？营收和利润增长情况怎么样？"  
**Endpoint:** `POST /api/v1/stock/600519/report-chat` (force_refresh=true)

### Attempt 1 (elapsed: 61.8s)

| Field | Value |
|-------|-------|
| `status` | `partial_success` |
| `errors` | `['UNSUPPORTED_NUMBERS:-31, 1708.99, 862.28, 15.71%, 15.38%']` |
| `chunks_retrieved` | `None` |
| `llm_model` | `None` |
| `confidence` | `medium` |
| `performance_meta.indexed_fast_path` | `True` |
| `performance_meta.timeout_layer` | `None` |
| `cache.selection` | `hit` |
| `cache.evidence` | `hit` |
| `cache.structured_financial_fields` | `hit` |

**Note:** The structured_financial_fields cache was hit from a prior synthesis run. The UNSUPPORTED_NUMBERS error indicates the Review Agent found numbers (1708.99, 862.28, etc.) in cached structured output that could not be verified against the retrieved evidence chunks. `llm_model=None` because LLM did not re-run (synthesis came from cache); `timeout_layer=None` because no timeout fired.

### Attempt 2 (elapsed: 60.03s)

| Field | Value |
|-------|-------|
| `status` | `partial_success` |
| `errors` | `['LLM 调用超时']` |
| `chunks_retrieved` | `None` |
| `llm_model` | `None` |
| `confidence` | `medium` |
| `performance_meta.indexed_fast_path` | `True` |
| `performance_meta.timeout_layer` | `llm_synthesis` |
| `stage_timings_ms.llm_total_ms` | **60000.0** |
| `cache.selection` | `hit` |
| `cache.evidence` | `hit` |
| `cache.final_answer` | `bypass` |

**G6 STATUS: BLOCKED**

---

## Root Cause Analysis — Three Compounding Issues

### Issue 1 (Primary): LLM Synthesis Timeout at 60s

`stage_timings_ms.llm_total_ms = 60000.0` — synthesis cut at exactly `_LLM_SYNTHESIS_TIMEOUT_SECONDS = 60.0`.

The `PI_REAL_PROVIDER_TIMEOUT_SECONDS=60` env var (SDK HTTP timeout) is also set to 60s. Both timeouts fire simultaneously. DeepSeek cannot complete synthesis for this prompt within 60 seconds under current server conditions.

**Evidence from host direct measurement (R2.4):** Simple 1199-token prompt → 6.0s. Production agent prompt is substantially larger: evidence_chars=3958 + system prompt (~3430 chars) + structured JSON output format → significantly more output tokens than the test. Synthesis latency for this specific prompt pattern consistently exceeds 60s.

**Required fix:** Increase `_LLM_SYNTHESIS_TIMEOUT_SECONDS` beyond 60s AND `PI_REAL_PROVIDER_TIMEOUT_SECONDS` beyond 60s — both must exceed the actual synthesis latency. Suggested: synthesis=120s, SDK=90s, outer=150s.

### Issue 2 (Secondary): Wrong Report Selected (2025 vs 2024)

`performance_meta.report_year = 2025` — the selection logic chose report `id=2` (2025 annual, 211 chunks, disclosure_date 2026-04-16) as `latest_formal_report`, ignoring the question's year reference ("2024年财报").

G5 successfully ingested the 2024 annual report (`id=17`, 208 chunks). However the selection logic returned the 2025 report via cache.

`force_refresh=True` bypasses the final_answer cache (`cache.final_answer='bypass'`) but does **not** invalidate the selection cache (`cache.selection='hit'`). The 2025 report selection was cached from a prior query run. The 2024 report would only be selected if the selection cache for this question is expired or if a year-aware selection override is implemented.

**Impact:** If synthesis had succeeded, the answer would discuss 2025 annual results, not 2024 — mismatching the question intent.

### Issue 3 (Tertiary): Structured Financial Fields Cache Stale

When synthesis cache hits `structured_financial_fields`, the Review Agent validates those cached numbers against current evidence chunks. If the chunks don't verbatim contain the exact numeric values (e.g., because financial tables are stored differently in the parsed text), Review fails with UNSUPPORTED_NUMBERS. This produces `partial_success` even when no LLM call is made.

**Affected numbers:** `-31, 1708.99, 862.28, 15.71%, 15.38%` — consistent with Moutai 2025 annual report figures (revenue ≈1708亿, net profit ≈862亿, growth ~15%).

---

## Timeout Budget Summary

| Constant | Value | Binding? |
|----------|-------|---------|
| `_REPORT_CHAT_OVERALL_TIMEOUT_SECONDS` | 90.0 | No (resolved R2.5) |
| `_LLM_SYNTHESIS_TIMEOUT_SECONDS` | 60.0 | **YES** — fires at 60.0s |
| `PI_REAL_PROVIDER_TIMEOUT_SECONDS` | 60 | **YES** — SDK fires at 60.0s |
| `_REPORT_SELECTION_TIMEOUT_SECONDS` | 12.0 | No |
| `_RAG_QUERY_TIMEOUT_SECONDS` | 8.0 | No |
| `_REVIEW_TIMEOUT_SECONDS` | 5.0 | No |

Outer timeout resolved. Two inner timeouts remain binding at 60s. DeepSeek synthesis for this prompt requires > 60s.

---

## G7 — Numeric Validation

**G7 STATUS: BLOCKED** — depends on G6.

---

## Full Gate Matrix

| Gate | Description | Status | Evidence |
|------|-------------|--------|---------|
| **G1** | Production DB reachable | **PASS** | asyncpg SELECT 1=1, HTTP 401 Supabase REST |
| **G2** | Alembic HEAD (p4q5r6s7t8u9) | **PASS** | `alembic current == p4q5r6s7t8u9` |
| **G3** | DeepSeek HTTP 200 OK | **PASS** | HTTP 200, model=deepseek-v4-flash |
| **G4** | RAG enabled | **PASS** | Container env: `ENABLE_REPORT_RAG=true` |
| **G5** | 600519.SH 2024 indexed (chunk_count>0) | **PASS** | id=17, chunk_count=208, status=indexed |
| **G6** | E2E query: status=completed | **BLOCKED** | `timeout_layer=llm_synthesis`, `llm_total_ms=60000.0` |
| **G7** | Numeric validation: valid=true | **BLOCKED** | Depends on G6 |
| **G8** | BaoStock provider chain | **PASS** | close=1346.50, peTTM=20.35, pbMRQ=6.21, roeAvg=38.43% |
| **G9** | Company Overview 4/6 fields not null | **PASS (code+provider)** | BaoStock 4/4 required fields |
| **G10** | Cache isolation (locator ≠ analysis) | **PASS (code)** | Key format `rc:v2:{intent_type}:...` verified |
| **G11** | Frontend /api/v1, no localhost | **PASS** | 0× localhost, 3× "/api/v1" in bundle |
| **G12** | A股 color: pct-up=red, pct-dn=green | **BROWSER_EVIDENCE_PASS** | Playwright: `--danger`=rgb(229,72,93) |
| **G13** | Badge: partial_success → danger | **PASS** | `badgeClass('partial_success')`→`'badge-failed'` |
| **G14** | Secret isolation | **PASS** | All artifacts: 0 full secret values |

**12 PASS / 2 BLOCKED (G6, G7)**

---

## Commit Status

**NOT COMMITTED.** Commit requires all gates to pass. G6 and G7 remain BLOCKED.

Applied changes present in working tree (unstaged):
- `backend/app/agent/report_chat_copilot_agent.py` — 2 constants modified
- `.env` — 1 line added (untracked, never committed)

---

## DECISION: NO-GO

**Three blockers identified** — all require owner authorization:

### Required Parameter Changes

| Priority | Change | File | From | To | Rationale |
|----------|--------|------|------|----|-----------|
| P0 | `_LLM_SYNTHESIS_TIMEOUT_SECONDS` | `report_chat_copilot_agent.py` line 50 | `60.0` | `120.0` | Synthesis takes > 60s for financial analysis prompt |
| P0 | `PI_REAL_PROVIDER_TIMEOUT_SECONDS` | root `.env` | `60` | `90` | SDK HTTP timeout must exceed synthesis latency |
| P0 | `_REPORT_CHAT_OVERALL_TIMEOUT_SECONDS` | `report_chat_copilot_agent.py` line 47 | `90.0` | `150.0` | Outer must exceed synthesis + overhead |
| P1 | Report selection year-awareness | `report_chat_copilot_agent.py` | — | — | `force_refresh=True` should invalidate selection cache when question contains explicit year |

**P1 is a logic change requiring design authorization.** P0 items are parameter-only.

---

## Post-Authorization Steps

When authorized:

```
1. Increase _LLM_SYNTHESIS_TIMEOUT_SECONDS = 120.0  (line 50)
2. Increase _REPORT_CHAT_OVERALL_TIMEOUT_SECONDS = 150.0  (line 47)
3. Set PI_REAL_PROVIDER_TIMEOUT_SECONDS=90 in root .env
4. docker compose build backend
5. docker compose up -d backend
6. Clear Redis report-chat cache keys: rc:v2:* for 600519
7. Retry G6 with force_refresh=true
8. Verify stage_timings_ms.llm_total_ms < 120000 (synthesis completed)
9. Verify status=completed, numeric_validation.valid=true
10. If PASS: commit all 3 changed files → issue GO
```

**Redis cache clear command (Step 6):**
```bash
docker compose exec redis redis-cli --scan --pattern 'rc:v2:*:600519*' | xargs docker compose exec redis redis-cli del
```

---

## Evidence Chain

| Phase | Action | Result |
|-------|--------|--------|
| R2.3 | Startup validation + 6 auth secrets | Backend starts cleanly |
| R2.3 | G5 ingestion (id=17, 600519.SH 2024) | chunk_count=208, status=indexed |
| R2.4 | `_LLM_SYNTHESIS_TIMEOUT_SECONDS` 25→60 | Outer timeout (45s) became binding |
| R2.5 | `_REPORT_CHAT_OVERALL_TIMEOUT_SECONDS` 45→90 | Outer resolved; LLM timeout (60s) binding |
| R2.5 | `PI_REAL_PROVIDER_TIMEOUT_SECONDS=60` | SDK timeout also at 60s; both fire simultaneously |
| R2.5 | G6 attempt 2 | `llm_total_ms=60000.0` — synthesis cut at 60s |

---

*Phase 6W-R2.5 STOP condition reached. No further code changes authorized. Commit not made. No synthetic data inserted. No secrets printed in full.*
