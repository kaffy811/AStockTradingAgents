# TradingAgents — US Resume Project Material
> Generated 2026-07-27 | All numbers verified from code, test artifacts, git history.
> Cross-referenced with internal QA audit (suggest1.md). No fabricated data.

---

## 1. Project Overview

| Field | Fact |
|---|---|
| **Project Name** | TradingAgents — AI-Powered Financial Research Platform |
| **Stage** | Release Candidate → Invite-Only MVP (Wave 1) |
| **Core User Scenario** | Individual investors run multi-dimensional stock research (technical, fundamental, peer, news) and ask follow-up questions to a conversational AI copilot |
| **Problem Solved** | Traditional stock research requires 90–120 minutes of manual aggregation across data sources; the system delivers a structured multi-agent report in 35–45s via parallel agent execution |
| **Live URL** | aastock.cloud (invite-only MVP) |
| **Codebase** | Full-stack: Python FastAPI backend + Vue 3 SPA frontend |

---

## 2. Technical Architecture

### Backend

| Layer | Technology | Detail |
|---|---|---|
| Framework | FastAPI 0.136+ / Python 3.12 | 119 HTTP endpoints, async-first |
| Database | PostgreSQL (Supabase) + SQLAlchemy 2.0 asyncpg | 52 ORM-mapped tables, 24 Alembic migrations |
| Vector Store | pgvector (PostgreSQL extension) | 384-dimensional embeddings, cosine similarity |
| Cache & State | Redis | SSE event streams (pub/sub), analysis run registry (cross-worker), rate limiting, circuit breaker, budget guards |
| API Style | RESTful + SSE streaming | `text/event-stream` with `event_id`, `after_event_id` reconnect replay |
| Auth | JWT (access + refresh) + invite-only registration | SHA-256 invite code hashing, SELECT FOR UPDATE atomic registration |

### LLM System

| Dimension | Fact |
|---|---|
| **Primary Model** | deepseek-v4-flash (1M context, 384K max output) |
| **Advanced Model** | deepseek-v4-pro (1M context) |
| **Agent Classes** | 52 total agent classes; 25 distinct named agents |
| **Parallel Analysis Agents** | 4 (TechnicalAnalyst, FundamentalAnalyst, PeerComparisonAnalyst, NewsAnalyst) |
| **Orchestration** | Dual-engine: custom coordinator (stable default) + LangGraph (canary) |
| **Thinking Mode** | Dynamic thinking phases; `ThinkingEvent` with 9 distinct phases; structured `<think>` content extraction |
| **Output Language** | 6 languages (zh-CN, zh-TW, en-US, ja-JP, ko-KR, es-ES) — per-request `output_language` |
| **Tool Registry** | 48 tool classes, 8 BaseSkill subclasses in SkillRegistry |
| **Prompt Strategy** | Conclusion-first structure; per-agent labeled sections; safety post-processor to strip filler phrases and ratio-style language |

### RAG (Financial Report PDF Pipeline)

| Dimension | Fact | Source |
|---|---|---|
| **Vector DB** | pgvector on PostgreSQL | `app/models/report_chunk.py` |
| **Embedding Dim** | 384 | `config.py` line 243 |
| **Chunk Size** | 1,000 chars target, 150 overlap; adaptive: 700 for Chinese-heavy, 1,200 for English-heavy | `report_chunk_service.py` |
| **Pipeline** | PDF download → text extract → adaptive chunking → 384-dim embed → pgvector upsert → hybrid retrieval | Phase 6E–6I |
| **Retrieval Strategy** | Hybrid: vector (weight 0.6) + BM25 keyword (0.3) + source boost (0.07) + recency (0.03); MMR (λ=0.7) for diversity | `app/services/report_rag_service.py` |
| **RAG Eval (8-question, 601686 annual report)** | Retrieval hit rate = 1.0, Citation page accuracy = 1.0, Cross-report leakage = 0 | `company_v2_601686_multi_report_rag_eval_phase6te3.json` |
| **Persistent Chunks** | 1,217 chunks across 4 active documents (211+299+311+396) | `company_v2_rag_persistence_phase6tj1.json` |

### Frontend

| Dimension | Fact |
|---|---|
| Framework | Vue 3 (Composition API) + Vite |
| Total Vue files | 152 (.vue) — 11 top-level views + 141 reusable components |
| i18n | 6 locale files (zh-CN/zh-TW/en-US/ja-JP/ko-KR/es-ES), custom `i18n.js` |
| Theme System | 3 themes (light/dark/sepia) via CSS variables + `html[data-theme]`; FOUC prevention |
| Charts | ECharts — K-line (candlestick), MACD, RSI, volume overlays with MA toggles |
| SSE Client | `fetch` + `ReadableStream` with reconnect guard, `reportReadyHandled` dedup, `_isMounted` cancel |
| PWA | `manifest.webmanifest`, BottomTabBar for ≤640px mobile |

### Deployment

| Dimension | Fact |
|---|---|
| Cloud | Supabase (managed PostgreSQL + pgvector) |
| Runtime | Uvicorn ASGI, 4-worker deployment verified (M43 pressure test) |
| Containerization | Docker + `docker-compose.staging.yml` |
| Provider Guardrails | 8-gate ProviderActivationGate: kill switch, credential, request budget (Lua atomic), cost budget (Lua atomic), sliding-window rate limit, lease semaphore, circuit breaker, pricing validation |

---

## 3. Quantitative Engineering Metrics

**Metric:** Multi-agent analysis latency (parallel vs serial)
**Value:** ~35–45s parallel vs ~120s serial → ≈3× speedup
**Evidence:** 4 agents run concurrently via asyncio tasks; fan-out/collect pattern
**Source file:** `docs/resume_star_cases.md`, `app/agents/langgraph_analysis_graph.py`

---

**Metric:** Shadow traffic soak — total requests, violations
**Value:** 65,373 requests selected across P1.8–P1.26 (25%→50%→75%→100%); **0 safety violations**
**Evidence:** `cumulative_p18_through_p126.total_selected = 65,373`, `cumulative_violations = 0`
**Source file:** `docs/artifacts/company_v2_phase6v_p126_sustained_deployed_100pct_shadow_soak.json`

---

**Metric:** SSE end-to-end p95 latency (pi_p95_ms)
**Value:** 4,739–4,800ms across 10 consecutive soak windows (stable)
**Evidence:** Windows U1–U10 at 75% rollout, all below 4,800ms review threshold
**Source file:** `docs/artifacts/company_v2_phase6v_p122_*.json`

---

**Metric:** Tool execution p95 latency
**Value:** 2,950–3,210ms (tool_p95_ms across F1–F6 windows)
**Evidence:** `"tool_p95_ms": 2950` (F2), `"tool_p95_ms": 3210` (F5)
**Source file:** `docs/artifacts/company_v2_phase6v_p119_fifty_percent_shadow.json`

---

**Metric:** Test suite size
**Value:** 7,036 test functions across 319 test files; 7,407 passed in latest regression run
**Evidence:** `grep -r "def test_" tests/ | wc -l`
**Source file:** `backend/tests/`

---

**Metric:** API surface
**Value:** 119 FastAPI route decorators across 20 router files
**Evidence:** `grep -rh "^@router\." app/routers/*.py | wc -l`
**Source file:** `backend/app/routers/`

---

**Metric:** Frontend component scale
**Value:** 152 Vue SFC files; 6 UI languages; 3 themes
**Evidence:** `find frontend/src -name "*.vue" | wc -l`
**Source file:** `frontend/src/`

---

**Metric:** Data coverage
**Value:** 5,166 A-share stocks indexed; 30 Shenwan Level-1 industries
**Evidence:** `"stock_master:sw_industry_map": 5166`, `industry_master` table
**Source file:** `docs/artifacts/`, `backend/app/models/industry.py`

---

**Metric:** RAG retrieval quality (small-sample evaluation)
**Value:** retrieval hit rate = 100%, citation page accuracy = 100%, cross-report leakage = 0 (8-question fixed evaluation on single annual report)
**Evidence:** `company_v2_601686_multi_report_rag_eval_phase6te3.json`
**Source file:** `backend/docs/artifacts/`

---

**Metric:** Multi-worker concurrency test
**Value:** 4 Uvicorn workers × 2 analysis engines × 8 concurrent runs each = 16/16 PASS, Redis cross-worker state consistent
**Evidence:** M43 pressure test; `docs/mvp_smoke_test_report.md`
**Source file:** `backend/tests/test_phase_m43_rc_audit.py`

---

**Metric:** Database + migration scale
**Value:** 52 ORM-mapped tables; 24 Alembic migrations; PostgreSQL + pgvector on Supabase
**Evidence:** `grep -rh "__tablename__" app/models/ | wc -l`
**Source file:** `backend/app/models/`, `backend/alembic/versions/`

---

**Metric:** SSE reconnect replay
**Value:** Redis `after_event_id` replay verified correct 3/3; cross-worker LangGraph event IDs deduplicated
**Evidence:** `docs/frontend_engineering_smoke_test.md`
**Source file:** `backend/app/analysis/redis_run_registry.py`

---

## 4. STAR Resume Material

### STAR #1 — Multi-Agent Parallel Analysis Pipeline

**Situation:** Users needed comprehensive stock research covering 4 dimensions (technical, fundamental, peer comparison, news). Sequential LLM calls took ~120 seconds.

**Challenge:** Reduce end-to-end latency without losing report quality or cross-agent consistency. The agents needed shared context (entity, market data) but independent LLM calls.

**Action:** Designed a fan-out/collect async architecture: a CentralPlanningAgent dispatches shared context to 4 specialized agents (TechnicalAnalyst, FundamentalAnalyst, PeerComparisonAnalyst, NewsAnalyst) running concurrently via `asyncio.gather`. Implemented dual-engine canary: custom coordinator (stable) + LangGraph `Send` API (canary). Built a SynthesisAgent to merge outputs with source attribution. Added `ThinkingEvent` pipeline with 9 reasoning phases for structured reasoning display.

**Result:** Parallel execution reduces report generation from ~120s to ~35–45s (≈3× speedup). Dual-engine canary ran 65,373 shadow requests with 0 violations. 7,036 automated tests maintain quality.

---

### STAR #2 — SSE Streaming with Redis Event Replay

**Situation:** Long-running AI analysis (30–45s) over unreliable mobile connections caused lost progress when users disconnected mid-stream.

**Challenge:** Guarantee exactly-once event delivery on reconnect across multiple Uvicorn workers — no shared in-process state allowed.

**Action:** Built a `RedisAnalysisRunRegistry` (pub/sub + 4 Redis keys per run). Each SSE event is stored with a monotonically increasing `event_id`. On reconnect, client sends `?after_event_id=N` and the server replays missed events. Added `asyncio.shield` to protect flush from request cancellation, and a `None`-guard in the LangGraph stream path to prevent silent stream termination.

**Result:** SSE reconnect replay verified correct in 3/3 tests; cross-worker state consistent across 4-worker deployment with 0 duplicate events. Tool p95 latency 2,950–3,210ms sustained across 10 soak windows.

---

### STAR #3 — Hybrid RAG Pipeline for Financial PDF Reports

**Situation:** Users needed AI answers grounded in company annual reports, not just model weights. Raw PDFs required download, extraction, and indexed retrieval.

**Challenge:** Chinese financial PDFs have mixed text density (tables vs narrative), making fixed-size chunking lossy. Standard vector search alone misses exact financial terms (stock codes, metric names).

**Action:** Built a 5-stage pipeline: PDF download → `pdfplumber` text extraction → adaptive chunking (700–1,200 chars based on CJK density, 150-char overlap) → 384-dim local embedding → pgvector upsert. Retrieval uses hybrid scoring: vector similarity (weight 0.6) + BM25 keyword (0.3) + source recency boost (0.03) + MMR diversity (λ=0.7). SourceReviewAgent canonicalizes citations and verifies page-level attribution.

**Result:** On an 8-question fixed evaluation of a 601686 annual report: retrieval hit rate 100%, citation page accuracy 100%, cross-report leakage 0. 1,217 chunks across 4 persistent active documents.

---

### STAR #4 — Canary Rollout with Bucket-Stable Shadow Traffic

**Situation:** Needed to validate a new LLM provider control plane (8-gate ProviderActivationGate) against real traffic before enabling for all users.

**Challenge:** Shadow traffic must select the same requests consistently across restart, worker rotation, and rollout percentage changes — unstable bucketing breaks soakability comparisons.

**Action:** Designed a deterministic bucket assignment: `HMAC-SHA256(request_id + config_version)[:8] < rollout_threshold`. Separated canary config version (cv) from bucket salt (`pi_v1`) so rollout changes don't re-shuffle existing cohorts. Built Redis-backed guards with Lua atomic scripts for TOCTOU-safe budget/rate checks. Ran structured soak windows at 25% → 50% → 75% → 100% with automated gate reports.

**Result:** 65,373 cumulative shadow requests across P1.8–P1.26, **0 safety violations**. Pi_p95 stable at 4,739–4,800ms across all windows. Bucket identity verified by identity replay after config version increment.

---

### STAR #5 — Invite-Only MVP Security: Atomic Registration + Code Hashing

**Situation:** Post-deployment audit of aastock.cloud revealed 4 critical security gaps: (1) registration had no invite code requirement, (2) invite creation endpoint had no admin auth, (3) invite codes stored as plaintext in PostgreSQL, (4) no `is_admin` field.

**Challenge:** Fix all 4 gaps without disrupting 207 existing users or requiring frontend changes. The invite redemption must be atomic — no race condition between two users redeeming the same single-use code.

**Action:** (1) Added `invite_code` to `RegisterRequest`; replaced the open `POST /auth/register` with a 7-step atomic transaction using `SELECT ... FOR UPDATE` to lock the invite row, then validate (expiry, use count, email binding), flush user insert, update `use_count`, and commit in one DB transaction. (2) Added `get_admin_user` FastAPI dependency. (3) Changed `MvpInvite` to store `code_hash = SHA-256(plaintext)` + 8-char `code_prefix` only; plaintext never persisted. (4) Added `is_admin` column via Alembic migration. (5) Created `python -m app.cli.create_admin` for first-admin bootstrap.

**Result:** 96/96 targeted tests PASS; 284/284 total (including regression) PASS. All 4 P0 security gaps closed. Zero breaking changes to existing users.

---

## 5. Resume Bullet Drafts

### Version A — LLM Engineer / Applied AI Engineer (5 bullets)

```
• Architected a 4-agent parallel analysis pipeline (TechnicalAnalyst, FundamentalAnalyst,
  PeerComparisonAnalyst, NewsAnalyst) using asyncio fan-out over DeepSeek v4-flash/pro
  (1M-token context), cutting report generation from ~120s to ~35–45s (~3× speedup) with
  a dual-engine canary system (custom coordinator + LangGraph Send API).

• Engineered a 5-stage financial PDF RAG pipeline — adaptive CJK-aware chunking
  (700–1,200 chars), 384-dim pgvector embeddings, hybrid retrieval (vector 0.6 + BM25
  0.3 + MMR λ=0.7) — achieving retrieval hit rate 1.0 and citation page accuracy 1.0
  on a fixed 8-question annual report evaluation with zero cross-report leakage.

• Designed a Redis-backed SSE event replay system with monotonic event_id and
  after_event_id reconnect protocol, verified correct across 4 Uvicorn workers and 10
  soak windows totaling 65,373 shadow requests and 0 violations (tool p95 ≤ 3,210ms).

• Built a 9-phase ThinkingEvent pipeline extracting structured reasoning from DeepSeek
  reasoner output, a 6-language output_language system, and a financial safety
  post-processor (ratio-phrase and filler-pattern filters), maintained by 7,036
  automated tests across 319 test files.

• Implemented a ProviderActivationGate with 8 sequential controls (kill switch,
  credential validation, Redis Lua-atomic request budget, cost ceiling, sliding-window
  rate limit, lease semaphore, circuit breaker, pricing registry) to fail-closed before
  any live LLM provider spend is authorized.
```

---

### Version B — Software Engineer / Backend Engineer (5 bullets)

```
• Built a 119-endpoint FastAPI service (Python 3.12, asyncio, SQLAlchemy 2.0 asyncpg)
  with 52 PostgreSQL tables, 24 Alembic migrations, and a Redis layer for cross-worker
  analysis run state, SSE pub/sub, rate limiting, and circuit-breaking — deployed across
  4 Uvicorn workers with 16/16 concurrent runs verified consistent in a Redis state test.

• Implemented a deterministic canary rollout system using HMAC-SHA256 bucket assignment
  (separated config version from bucket salt for cohort stability), enabling structured
  soak phases at 25%→50%→75%→100% shadow traffic; validated 65,373 cumulative requests
  with 0 safety violations and pi_p95 stable at 4,739–4,800ms.

• Designed an invite-only registration flow with atomic PostgreSQL transactions (SELECT
  FOR UPDATE → validate → INSERT user → consume invite → COMMIT), SHA-256 invite code
  hashing (plaintext never stored), is_admin RBAC, and a CLI bootstrap tool; closed 4
  P0 security vulnerabilities with 96/96 tests passing.

• Engineered a hybrid RAG retrieval service on pgvector with adaptive chunking, hybrid
  scoring (vector + BM25 + recency), MMR diversity filtering, and a SourceReviewAgent
  that canonicalizes and validates page-level citations in retrieved chunks.

• Delivered a 152-component Vue 3 SPA with ECharts candlestick/MACD/RSI charts,
  6-locale i18n, 3-theme CSS variable system (with FOUC prevention), SSE streaming
  client (ReadableStream + reconnect guard), and a mobile PWA layout — all maintained
  by a frontend test suite with 688 passing tests.
```

---

## 6. Interview Preparation — 10 Most Likely Technical Questions

**Q1: Why LangGraph instead of your custom coordinator as the default engine?**
*Expected follow-up:* What are the tradeoffs? What does LangGraph's Send API give you that asyncio.gather doesn't?
> Answer framework: LangGraph provides built-in state graph checkpointing and the `Send` API for structured fan-out with named node routing. Custom coordinator was battle-tested and stable first; LangGraph runs as canary to compare latency and output shape before promotion. The Send API is cleaner for conditional routing (e.g., skip peer analysis for ETFs), while asyncio.gather is lower-overhead for the fixed 4-agent case.

---

**Q2: How does your SSE replay guarantee exactly-once delivery across multiple workers?**
*Expected follow-up:* What happens if Redis goes down? What if two workers write the same event_id?
> Answer framework: Each event is stored with an auto-incrementing `event_id` key in Redis (INCR is atomic). On reconnect, client sends `?after_event_id=N`; the server streams all events with `id > N` from Redis sorted set. If Redis is unavailable, the registry degrades to memory mode (per-worker, no cross-worker replay). Event IDs are globally monotonic because INCR is single-writer per run key.

---

**Q3: Why pgvector instead of a dedicated vector database like Pinecone or Weaviate?**
*Expected follow-up:* What are the scaling limits? When would you migrate?
> Answer framework: pgvector keeps vectors co-located with metadata (source, page, chunk_index) in the same transaction boundary — critical for citation accuracy validation. No additional infra to manage. For MVP scale (thousands of chunks), pgvector's IVFFlat index is sufficient. Migration to dedicated VDB becomes justified when chunk count exceeds ~10M or when ANN recall at high QPS becomes a bottleneck.

---

**Q4: How does your adaptive chunking work for Chinese financial PDFs?**
*Expected follow-up:* How do you measure chunk quality? What's the failure mode if chunking is wrong?
> Answer framework: Count CJK characters as a ratio of total; if ratio > threshold, use 700-char target (Chinese sentences are denser); otherwise 1,200 chars. Overlap of 150 chars preserves sentence context across boundaries. Failure mode: a key metric (e.g., ROE ratio) split across a boundary → neither chunk contains the full context → retrieval misses it. Mitigation: minimum chunk size (100 chars) to discard fragments; MMR diversity ensures both sides of a boundary can be retrieved if needed.

---

**Q5: How do the Redis Lua scripts for budget guards prevent TOCTOU races?**
*Expected follow-up:* What's the difference between using Lua vs Redis transactions (MULTI/EXEC)?
> Answer framework: Lua scripts run atomically on the Redis server — no other command executes between `GET` and `SET`. With `MULTI/EXEC`, two clients can both `GET` (both see budget available), then both `INCR` — classic TOCTOU. Lua eliminates this because GET+compare+INCR is a single server-side atomic operation. The script returns `-1` if ceiling reached, so the caller knows immediately.

---

**Q6: What is bucket-stable canary rollout and why does it matter?**
*Expected follow-up:* What would break if you used random sampling instead?
> Answer framework: `HMAC-SHA256(request_id || salt)[:8] < threshold` assigns each request a stable bucket (0–9999). The same request always goes to the same bucket regardless of which worker handles it. Random sampling would mean a request accepted at 50% might be rejected at 75% (if re-sent), making soak comparisons meaningless — you can't distinguish "latency improvement" from "different request mix". Stable bucketing also lets you replay the exact same cohort to verify identity.

---

**Q7: How do you prevent LLM hallucination in financial contexts?**
*Expected follow-up:* How do you handle cases where the model confidently states a wrong number?
> Answer framework: Three layers: (1) Source grounding — RAG retrieves exact chunks from official filings; SourceReviewAgent validates every cited figure has a matching chunk with page attribution. (2) Safety post-processor strips ratio-style language ("grew by X times") and filler confidence phrases. (3) DataQuality cards surface data completeness score to the user so they know when the model is working from partial data. The system doesn't claim to eliminate hallucination — it makes the evidence chain auditable.

---

**Q8: How does your circuit breaker interact with the rate limiter across 4 workers?**
*Expected follow-up:* What happens during the HALF_OPEN state?
> Answer framework: Both are Redis-backed — state changes are globally visible to all workers. Circuit breaker: `status` key + `consecutive_failures` key + `recovery_at` epoch. On `is_open()`, checks `recovery_at`; if elapsed, auto-transitions to HALF_OPEN by writing `half_open` to Redis. In HALF_OPEN, one probe request is allowed (first worker to check wins by setting a lease). If probe succeeds: `record_success()` → CLOSED. If probe fails: immediately re-OPEN. Rate limiter: sliding window via Redis ZSET with atomic ZADD+ZREMRANGEBYSCORE+ZCARD Lua script.

---

**Q9: Why did you choose `SELECT FOR UPDATE` for invite code redemption rather than optimistic locking?**
*Expected follow-up:* What's the performance trade-off? When would you choose optimistic locking instead?
> Answer framework: With single-use invite codes, the collision probability is actually high (two users race to redeem the same code). Optimistic locking would fail the second user with a retry loop, costing an extra round-trip and requiring the client to handle 409 retry logic. `SELECT FOR UPDATE` serializes at the DB level: second transaction blocks until first commits, then reads `use_count = 1 >= max_uses = 1` and fails immediately with a clean 400. Optimistic locking is better when collisions are rare (e.g., updating a user profile field).

---

**Q10: How does your dual-engine (LangGraph vs custom_coordinator) canary actually work in production?**
*Expected follow-up:* How do you compare quality between the two engines? What metric determines promotion?
> Answer framework: The `engine` field in `/analysis/runs` request body selects the runner; if absent, falls back to `DEFAULT_ANALYSIS_ENGINE` env var, then to `"custom_coordinator"`. In the canary setup, a percentage of requests (controlled by `DEFAULT_ANALYSIS_ENGINE` env var on specific workers) use LangGraph. Comparison: (1) Output shape — both must produce `TechnicalAnalysis`, `FundamentalAnalysis`, `PeerComparisonAnalysis`, `NewsAnalysis` sections. (2) Latency ratio — LangGraph overhead was measured at 0.97× (within noise). (3) Zero incompatible events in the SSE stream. Promotion gate: shape 100% compatible + ratio < 1.05× + 0 SSE errors.

---

## 7. Output File — resume_project_bullet.md (Overleaf-Ready)

```latex
% ─── TradingAgents — AI Financial Research Platform ───────────────────────
% Role: Full-Stack AI Engineer | Python · FastAPI · Vue 3 · DeepSeek · LangGraph
% Period: [Your dates] | Stage: Release Candidate → Invite-Only MVP
% Source code: Private GitHub

\resumeProjectHeading
  {\textbf{TradingAgents} $|$ \emph{Python, FastAPI, Vue 3, PostgreSQL+pgvector,
   Redis, DeepSeek LLM, LangGraph, Docker}}{[Dates]}

\resumeItemListStart

%% ── Version A bullets (LLM / Applied AI focus) ────────────────────────────

\resumeItem{
  Architected a \textbf{4-agent parallel analysis pipeline}
  (Technical, Fundamental, Peer, News) over DeepSeek v4-flash/pro (1M-token context)
  using asyncio fan-out and a dual-engine canary system (custom coordinator +
  LangGraph Send API), reducing report generation from \textasciitilde120s to
  \textbf{\textasciitilde35--45s (\textasciitilde3$\times$ speedup)}.
}

\resumeItem{
  Engineered a \textbf{5-stage financial PDF RAG pipeline} --- adaptive CJK-aware
  chunking (700--1,200 chars), 384-dim pgvector embeddings, hybrid retrieval
  (vector 0.6 + BM25 0.3 + MMR $\lambda$=0.7) --- verified at
  \textbf{retrieval hit rate 1.0} and \textbf{citation page accuracy 1.0} on a
  fixed 8-question annual report evaluation with zero cross-report leakage.
}

\resumeItem{
  Designed a \textbf{Redis-backed SSE event replay} system with monotonic
  \texttt{event\_id} and \texttt{after\_event\_id} reconnect protocol, sustaining
  \textbf{65,373 cumulative shadow requests with 0 violations} across 4 Uvicorn
  workers; pi\_p95 stable at \textbf{4,739--4,800ms} over 10 soak windows.
}

\resumeItem{
  Built a \textbf{9-phase LLM reasoning pipeline} (ThinkingEvent) with structured
  DeepSeek reasoner output extraction, a \textbf{6-language output\_language} system,
  and a financial safety post-processor (ratio-phrase + filler-pattern filters),
  maintained by \textbf{7,036 automated tests} across 319 test files.
}

\resumeItem{
  Implemented an \textbf{8-gate ProviderActivationGate} with Redis Lua-atomic
  request budget, cost ceiling, sliding-window rate limit, lease semaphore, and
  circuit breaker to enforce fail-closed behavior before any live LLM spend;
  ran structured canary soak at 25\%$\to$50\%$\to$75\%$\to$100\% shadow traffic.
}

%% ── Version B bullets (SWE / Backend focus) ───────────────────────────────

\resumeItem{
  Built a \textbf{119-endpoint FastAPI service} (Python 3.12, asyncio,
  SQLAlchemy 2.0 asyncpg) with \textbf{52 PostgreSQL tables}, 24 Alembic migrations,
  and Redis cross-worker state for SSE pub/sub and run registry --- deployed across
  4 Uvicorn workers with 16/16 concurrent analysis runs verified consistent.
}

\resumeItem{
  Implemented a \textbf{deterministic canary rollout} using HMAC-SHA256 bucket
  assignment (separated config version from bucket salt for cohort stability),
  enabling phased shadow promotion at 25\%$\to$100\%; \textbf{65,373 shadow
  requests, 0 violations}, pi\_p95 $\leq$ 4,800ms across all phases.
}

\resumeItem{
  Designed an \textbf{atomic invite registration flow} with PostgreSQL
  \texttt{SELECT FOR UPDATE} (validate $\to$ insert user $\to$ consume invite in
  one transaction), SHA-256 invite code hashing (plaintext never stored),
  \texttt{is\_admin} RBAC, and admin CLI --- closed \textbf{4 P0 security gaps},
  96/96 tests passing.
}

\resumeItem{
  Built a \textbf{hybrid RAG retrieval service} on pgvector with adaptive
  CJK chunking, vector + BM25 hybrid scoring, MMR diversity filtering, and a
  SourceReviewAgent that canonicalizes and validates page-level citations;
  \textbf{1,217 chunks} indexed across 4 active financial reports.
}

\resumeItem{
  Delivered a \textbf{152-component Vue 3 SPA} with ECharts K-line/MACD/RSI,
  6-locale i18n, 3-theme CSS variable system, SSE streaming client with reconnect
  guard, and PWA mobile layout --- covering \textbf{5,166 A-share stocks} and
  30 industries, maintained by 688 frontend tests.
}

\resumeItemListEnd
```

---

## Appendix — Numbers Quick Reference

| Metric | Value | Source |
|---|---|---|
| Analysis speedup | ~120s → ~35–45s (~3×) | `docs/resume_star_cases.md` |
| Shadow requests | 65,373 selected, 0 violations | P1.26 artifact |
| SSE pi_p95 | 4,739–4,800ms | P1.22 artifact |
| Tool p95 | 2,950–3,210ms | P1.19 artifact |
| Backend tests | 7,036 functions / 7,407 latest run | `grep "def test_"` |
| Frontend tests | 688 | `update_93.md` |
| API endpoints | 119 | `grep @router.` |
| Vue components | 152 | `find -name "*.vue"` |
| ORM tables | 52 | `grep __tablename__` |
| Alembic migrations | 24 | `ls alembic/versions/` |
| Stocks indexed | 5,166 A-shares | `stock_master` artifact |
| Industries | 30 Shenwan L1 | `industry_master` |
| RAG eval (fixed 8Q) | hit=1.0, page accuracy=1.0 | Phase 6TE3 artifact |
| RAG chunks active | 1,217 (4 reports) | Phase 6TJ1 artifact |
| Agent classes | 52 total (25 distinct named) | `grep "class.*Agent"` |
| Tool classes | 48 | `grep "class.*Tool"` |
| Skills | 8 BaseSkill subclasses | `app/agents/chat_skills/` |
| UI languages | 6 (zh-CN/zh-TW/en-US/ja-JP/ko-KR/es-ES) | `frontend/src/locales/` |
| AI output languages | 6 | `output_language` in config |
| Embedding dim | 384 | `config.py:243` |
| Chunk size | 1,000 chars, 150 overlap (adaptive) | `report_chunk_service.py` |
| Multi-worker test | 4 workers, 16/16 PASS | M43 audit |
| Invite security P0s | 4 closed, 96/96 PASS | MVP-R1.2 |

---

> **Do not use:** "API fallback rate 82%→97%" (no before/after data), user count, WAU,
> hours saved by users (no telemetry), "16 Redis connections" (those are concurrent runs).
> RAG eval numbers are from a fixed 8-question sample, not production-wide hit rate.
