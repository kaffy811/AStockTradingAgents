# Financial Agent Runtime Architecture

Phase 6U-E1 introduces an additive layered runtime behind `CHAT_RUNTIME_MODE=legacy|layered_v1|shadow`.

## Legacy Responsibility Map

- `chat_orchestrator`: intent routing, memory/context, skill arbitration, tool dispatch, fallback ownership.
- `Skill`: intent matching, data access, agent dispatch, answer text construction, sometimes source/disclaimer ownership.
- `Agent`: evidence retrieval, synthesis, Markdown generation, sometimes repository access.
- `Streaming`: event contract, persistence, fallback, answer guards.

This overlap caused repeated agent display, entity/report context loss, fallback contamination, duplicated disclaimers, and DB lifecycle issues.

## New Seven-Layer Runtime

```mermaid
flowchart TD
  UI[Chat UI / SSE] --> LM1[L-1 Runtime Reliability]
  LM1 --> L0[L0 Intent & Safety Router]
  L0 -->|clarify| UI
  L0 --> L1[L1 Context Builder & Execution Planner]
  L1 --> L2[L2 Financial Data Fabric / Tool Runtime]
  L2 --> Services[Shared Domain Services]
  L2 --> L3[L3 Domain Analysis Agents]
  L3 --> L4[L4 Fact Fusion & Drafting]
  L4 --> L5[L5 Compliance Gate & Presentation]
  L5 --> UI
```

## L-1 Runtime Reliability

E1 reuses the E0/E0.1 primitives instead of reimplementing them:

- `AuthPrincipal`
- `RequestDeadline`
- DB connection mode / transaction pooler policy
- Auth TTL cache and singleflight
- auth DB circuit breaker
- structured 503 contracts such as `AUTH_DATABASE_UNAVAILABLE`
- frontend retry behavior that keeps login state

The layered runtime receives verified user context from the existing Chat entrypoint. It does not read JWTs, does not query `User` ORM, and does not own message persistence.

## Tool DAG, Retry, Circuit Breaker

```mermaid
flowchart LR
  Plan[ExecutionPlan] --> A[get_official_reports]
  A --> B[get_structured_report_financials]
  A --> C[query_report_evidence]
  B --> D[compare_financials]
  C --> E[FinancialReportAnalysisAgent]
  D --> F[MultiCompanyFinancialComparisonAgent]

  subgraph RetryPolicy
    DB[DB query: one safe retry]
    RAG[RAG: cache -> DB -> partial evidence]
    Quote[Quote: primary -> fallback provider]
    LLM[LLM: one main call + optional lightweight fallback]
  end

  subgraph CircuitBreaker
    Closed[closed] --> Open[open]
    Open --> Half[half_open]
    Half --> Closed
  end
```

## DB Lifecycle

```mermaid
sequenceDiagram
  participant Tool as L2 Tool
  participant DB as AsyncSessionLocal
  participant Agent as L3 Agent
  participant LLM as LLM

  Tool->>DB: open short session
  Tool->>DB: query/materialize DTO
  Tool->>DB: close session
  Tool->>Agent: ToolResponse DTO
  Agent->>LLM: optional synthesis from DTO only
```

Agents, planners, SSE, and LLM calls must not hold `AsyncSession`.

## Runtime Modes

- `CHAT_RUNTIME_MODE=legacy`: production default. Layered runtime is not executed.
- `CHAT_RUNTIME_MODE=shadow`: legacy answers users; layered runtime runs read-only in the background.
- `CHAT_RUNTIME_MODE=layered_v1`: only intents listed in `CHAT_LAYERED_INTENTS` use the new runtime; unmigrated intents fall back to legacy.

Current migrated intents:

- `financial_report`
- `financial_comparison`
- `official_report_pdf`
- `financial_snapshot`
- `quote_query`

## First Migrated Scenarios

- explicit company report analysis
- multi-turn report comparison
- official PDF lookup
- company financial snapshot Q&A
- simple quote query

All other scenarios remain on legacy unless `CHAT_RUNTIME_MODE=layered_v1` is explicitly enabled and the runtime can handle the request.
