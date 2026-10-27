# Phase 6W-R3.2B Fix Decision

## Evidence decision matrix

| Decision | Literal matches | Causal matches for unsupported failures | Decision |
|---|---:|---:|---|
| D1: number present at S4 but removed at S5 | 5 | 0 | Compactor loss is real, but do not modify until a missing claim is tied to it |
| D2: requested claim exists in report but absent from S3 | 0 | 0 | Do not change retrieval |
| D3: citation metadata appears in answer prose | 4 | 4 | Proven and eligible for minimal repair |
| D4: genuine unsupported financial fabrication | 0 | 0 | Guard remains unchanged |

The Q4 `31` token is unsupported date metadata, not a D2 evidence slot and not D4 fabrication. No report-wide financial-token lookup established a missing requested dimension.

## Authorized minimal D3 repair

Evidence is sufficient: five complete S0-S8 traces exist and four independently show metadata leakage. A subsequent implementation phase is authorized to make only this bounded repair:

1. Serialize model-facing evidence with request-local IDs `E1..En`; omit raw database chunk IDs from the model prompt.
2. Keep `E1 -> raw chunk_id` mapping inside the request scope.
3. Replace model-facing `source_chunks[].chunk_id` with `citations[].evidence_id` and `claim`.
4. Validate that `evidence_id` exists and that claim numbers occur in the mapped evidence. Semantic validation must be deterministic and conservative; unresolved claims are removed or degraded.
5. Resolve valid labels back to canonical backend source metadata only after validation.
6. Add `CITATION_METADATA_LEAK` when answer prose contains one of the current retrieval's raw IDs in citation context. Do not treat arbitrary four-digit integers as IDs.
7. Preserve the existing numeric validator, canonicalization, report selection, retrieval, top_k, timeouts, cache TTL, review and partial-success behavior.

No production code was changed in this acquisition phase.

## Startup warmup A/B plan

Status: `UNRESOLVED — NO COMMIT`.

Build A from the current image and B from the same HEAD without the uncommitted startup warmup. Hold database, connection settings, resources and retrieval question constant. For each arm, perform at least five fully cold container starts, ensure selection/evidence cache miss, and execute exactly one retrieval-only request. Alternate A/B runs and record startup duration, warmup duration, first selection latency, first retrieval latency, connection errors and pool usage.

This controlled evidence does not currently exist. `backend/app/main.py` has no demonstrated necessity and must not enter the dependency commit.

## Release decision

- Minimal D3 implementation in a later phase: authorized.
- Implementation in this acquisition phase: not performed.
- Commit/push: none.
- Traffic: `HOLD_1_PERCENT`.

