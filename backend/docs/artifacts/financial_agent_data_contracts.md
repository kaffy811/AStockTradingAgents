# Financial Agent Data Contracts

Implementation: `backend/app/agents/financial_runtime/contracts.py`

All contracts include:

- `trace_id`
- `schema_version`
- `status`
- `created_at`
- `updated_at`
- `error_code`
- `request_id`
- `completed_at`
- `warnings`
- `metadata`

Allowed terminal/business statuses:

- `success`
- `partial_success`
- `failed`
- `clarification_required`
- `unavailable`
- `cancelled`

Internal in-flight statuses are limited to `pending` and `started`.

## Contracts

- `RuntimeRequest`: raw user query, conversation id, page context, user context.
- `AgentRequest`: runtime request passed into the layered runtime.
- `IntentRoutingResult`: intent, confidence, resolved entities, policy class, clarification options.
- `SecurityEntity`: market, symbol, exchange, ts_code, short/full name, aliases, industry, confidence, match type.
- `FinancialSessionContext`: primary/secondary entities, active report/period, page context, pending clarification, last successful context.
- `ExecutionPlan`: plan id, intent, entities, DAG steps, dependencies, execution mode, timeout budget, user-facing stages.
- `ToolRequest`: capability and parameters.
- `ToolResponse`: data, provenance, freshness, quality, warnings, error, latency.
- `ProvenanceRecord`: source id/type/provider/as-of/retrieved-at metadata.
- `DataFreshness`: as-of, realtime, stale markers.
- `DataQuality`: completeness, applicable/available field counts, conflicts, warnings.
- `AgentResponse`: findings, metrics, conflicts, inferences, limitations, evidence ids.
- `FinancialFact`: label, value, unit, period, entity, evidence ids, provenance.
- `FinancialInference`: explicit inference statement with evidence and limitations.
- `ConflictRecord`: structured conflict between evidence or agent findings.
- `StructuredAnswer`: conclusion, deterministic tables, findings, risks, sources.
- `ComplianceReview`: policy findings, logic findings, structured edit instructions.
- `FinalChatResponse`: final answer, structured answer, tool events, cards, metadata.
- `RuntimeError`: canonical runtime error envelope.

## Evidence Rule

Every financial number in `FinancialFact.value` must include at least one `evidence_id` and provenance. If a metric has no reliable evidence, the renderer omits the metric or shows `暂无可靠证据`; it never fills missing values with `0`.

## Presentation Ownership

The runtime body renderer owns answer body construction. The normal Chat frontend owns the single disclaimer footer. Debug mode may show metadata, but normal mode hides provider names, chunk ids, report ids, cache keys, and internal skill/agent names.
