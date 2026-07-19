# Legacy Entity Clarification Audit (6V-P1.6.8)

## Data-loss chain before the fix

```json
{
  "resolver_candidates_present": false,
  "legacy_runtime_candidates_present": false,
  "sse_candidates_present": false,
  "persisted_message_candidates_present": false,
  "frontend_candidates_present": false,
  "first_loss_point": "security_entity_resolver — bare short alias (e.g. 平安) matched nothing, so ambiguity was never flagged and the skill fell back to the generic ENTITY_NOT_RESOLVED copy"
}
```

## Fix chain
1. `SecurityEntityResolver.resolve_short_alias_candidates` — generic index-driven short-alias ambiguity (stopworded, 2..8 matches, deterministic ordering, CN>HK>US dedup). No per-company hardcoding: the live index also surfaced 平安电工 (001359) alongside 平安银行/中国平安.
2. `app/services/entity_clarification.py` — structured `entity_selection` contract + deterministic text fallback (no LLM, no URL, no internal status).
3. `report_explanation_skill` — both the resolver-ambiguity branch and the ENTITY_NOT_RESOLVED fallback now emit the contract with `status=clarification_required`.
4. Orchestrator hoists `metadata.response_kind/clarification`; sync response, single SSE terminal event, message persistence (existing JSONB, no migration) and session-detail metadata all carry the sanitized subset.
5. Frontend `ChatClarificationCard` + `utils/clarification.js` render deduplicated candidates, click sends the explicit selection as a normal user turn, refresh restores candidates from persisted metadata.

- Explicit symbols / company names never trigger the alias path (normal resolution wins first).
- Shadow diagnostics remain invisible to users; formal Pi stays disabled.
