# Phase 6W-R3.3A — Numeric Failure Provenance Audit

Date: 2026-08-26 (America/New_York)

HEAD: `9c65027eeef5d599ae13083affc926497a4d2432`

Branch: `release/demo-staging`

Traffic: `HOLD_1_PERCENT`

## 1. Audit population and evidentiary limit

The population is exactly the 14 R3.2D records with `numeric_validation.valid=false`; none was omitted or substituted. They contain 42 unsupported-token occurrences after preserving thousands separators as part of the token, for example `-1,275.96` and `2,726.00`.

The original R3.2D runner persisted query, request ID, selected report/year, cache/retrieval metadata, final status, and S8 error strings. It did **not** persist the original answer, prompt, retrieved content, compactor input/output, structured facts, citations, or S7 review object. Backend logs and all existing artifacts were searched by the 14 request IDs and contain no recoverable original answer sentences.

Consequently:

- Invalid events: confirmed 14/14.
- Token occurrences in S8: confirmed 42/42.
- Complete original S0–S8 traces: 0/14.
- Original token answer sentences: 0/42 recoverable.
- Original first-introduced stage: 0/42 determinable; earliest preserved stage is S8.
- Original evidence coverage: 0/42 determinable.
- Provenance classification: 42/42 `UNCONFIRMED`, as required when the original snapshots are absent.

New one-time runs are recorded only as supplements. Their text and token behavior are not presented as the original observation.

## 2. Original 14-request matrix

For every row, `sentence=not persisted`, `first introduced=UNCONFIRMED (earliest preserved S8)`, `user-visible=UNCONFIRMED`, `coverage=UNCONFIRMED`, and confidence is low for provenance but high that the invalid event occurred.

| Run | Original request | Report/year | Unsupported tokens preserved in S8 | Classification |
|---|---|---|---|---|
| W2 | `b1c9e518` | 17/2024 | `12`; `2`; `-1,275.96`; `15%` | UNCONFIRMED ×4 |
| W5 | `be143efa` | 17/2024 | `2,726.99` | UNCONFIRMED ×1 |
| W6 | `8d207e5c` | 17/2024 | `12`; `2`; `15%` | UNCONFIRMED ×3 |
| C2 | `3b291b2d` | 17/2024 | `12`; `31` | UNCONFIRMED ×2 |
| Y3 | `53d32a61` | 17/2024 | `2`; `-1275.96` ×2; `15%` | UNCONFIRMED ×4 |
| Y4 | `9ca90af7` | 2/2025 | `1.21%`; `4.53%`; `4.34%`; `33.46%` | UNCONFIRMED ×4 |
| R3 | `a167c86d` | 17/2024 | `12` | UNCONFIRMED ×1 |
| F1 | `a50ca0bc` | 2/2025 | `1.21%`; `4.08%`; `4.53%`; `33.46%`; `-01` | UNCONFIRMED ×5 |
| G1 | `ef099d5c` | 17/2024 | `6`; `2` | UNCONFIRMED ×2 |
| G2 | `4249ea53` | 17/2024 | `12`; `2` ×2 | UNCONFIRMED ×3 |
| G3 | `cbde38fc` | 17/2024 | `12`; `2,726.00`; `2` | UNCONFIRMED ×3 |
| G6 | `067b2be3` | 17/2024 | `1709.0`; `862.3`; `12`; `2`; `2726.99` | UNCONFIRMED ×5 |
| G7 | `6a97fbf6` | 17/2024 | `-01` ×2; `-0.13` | UNCONFIRMED ×3 |
| G9 | `8b761b0d` | 17/2024 | `2`; `-1,275.96` | UNCONFIRMED ×2 |

The machine-readable matrix contains an entry for every occurrence and the mandatory-field disposition. `answer_sentence=null` is explicit rather than filled with a sentence from a different run.

## 3. Classification statistics

| Classification | Original requests conclusively hit | Token occurrences |
|---|---:|---:|
| D1_COMPACTOR_OMISSION | 0 | 0 |
| D2_RETRIEVAL_COVERAGE_GAP | 0 | 0 |
| D3_CITATION_METADATA_LEAK | 0 confirmed | 0 confirmed |
| D4_UNSUPPORTED_FINANCIAL_CLAIM | 0 | 0 |
| D5_DATE_PERIOD_UNIT_OR_FORMAT_MISMATCH | 0 | 0 |
| D6_STRUCTURED_FACTS_EVIDENCE_VERSION_MISMATCH | 0 | 0 |
| D7_OTHER_NON_FINANCIAL_METADATA | 0 | 0 |
| UNCONFIRMED | 14 | 42 |

This does not mean D1–D7 did not occur. It means the original evidence required to distinguish them was not retained. Classifying `15%` as rounding, `-01` as a date fragment, or `2` as metadata without its original sentence would violate the audit rule.

## 4. Controlled supplements

All 14 original queries were attempted exactly once with unique sessions, `force_refresh=true`, atomic S0–S8 persistence, and at least 10 seconds between requests. No automatic retries occurred. These are new runtime samples:

| Original run | New request | New result | New unsupported tokens |
|---|---|---|---|
| W2 | `ca3f33bb` | partial | `2`, `15%`, `2` |
| W5 | `e1b7eec2` | partial, citation validation only | none |
| W6 | `8ad8dcf2` | completed | none |
| C2 | `33f1be00` | LLM timeout | none validated |
| Y3 | `f8ed8fb8` | completed | none |
| Y4 | `d38677b7` | partial | `1.21%`, `4.53%`, `33.46%`, `1.21%`, `4.08%` |
| R3 | `a4195022` | completed | none |
| F1 | `89d609d9` | partial | `1.21%`, `4.08%`, `4.53%`, `33.46%`, `4.34%` |
| G1 | `46ecbee7` | partial | `15%`, `-0.13`, `2` |
| G2 | `8cb17144` | empty LLM response | none validated |
| G3 | `91204159` | empty LLM response | none validated |
| G6 | `61d2ecd0` | partial | `12`, `15%` |
| G7 | `ebf84916` | partial | `2`, `-1`, `275.96` |
| G9 | `6c142357` | report selection failure | none validated |

The supplements demonstrate non-repeatability: identical canonical queries ranged from completed to citation failure, numeric failure, empty response, and selection failure. They also show mechanisms worth a separately authorized future audit. For example, the 2025 percentage tokens in Y4/F1 were absent from the new S3, S4, S5, and LLM-visible prompt and first appeared in the new S6 answer. That is direct evidence about those **new** requests only, not enough to classify original Y4/F1 as D4 or D5.

## 5. D3 regression check

The precise check requires a complete retrieved raw ID plus chunk/citation/source/ID context; a raw digit that merely prefixes `2025` is not a leak.

Across the 14 supplements:

- LLM-visible prompt containing `chunk_id` or `company_v2_report_rag_chunks`: 0.
- Raw retrieved ID in the answer with citation context and full numeric boundaries: 0.
- Citation labels outside `E1..En`: 0.
- Production `citation_metadata_leak=true`: 0.
- Confirmed D3 regression: 0.

The original 14 prompts and answers were not retained, so original D3 status remains unconfirmed. No new P1 D3 regression was observed.

## 6. User-visible unsupported financial numbers

For the original population, whether the unsupported tokens remained in the user-visible degraded answer is `UNCONFIRMED`; the original final answer body is missing. The S8 status was `partial_success`, showing the safety gate did not label the response completed, but it does not reconstruct the exact published body.

The new supplements did contain user-visible unsupported financial numbers in partial responses, including the 2025 decline percentages and rounded/derived values. Those are new-run evidence and remain safely rejected by numeric validation.

## 7. Runtime integrity

| Item | Value |
|---|---|
| Image | `sha256:48a50ce2435e379c46f0ed0afa1878a5f9c8e9f223dcb418bb4bbc1a944987db` |
| Container ID | `c9567bfdfec4892823d7a5febd09d1cba2e4fac2ba6dd300082f74bfd0140bee` |
| Created | `2026-08-23T01:34:13.297204344Z` |
| Bind mounts | none |

Runtime hashes for `main.py`, the embedding provider, `pyproject.toml`, and `uv.lock` match the dirty worktree and differ from HEAD blobs. Docker history includes the dirty dependency/model-preload layers. The running image contains dirty dependency/warmup changes and is not a pure `9c65027` release baseline. Nothing was rebuilt, reverted, staged, committed, deployed, or pushed in this phase.

## 8. Direct-evidence recommendations

No production fix is authorized by this audit because no D1–D7 cause can be assigned to the original population.

The next owner-authorized evidence task should persist the full original response lifecycle before evaluating a fix:

1. Atomically save S0–S8, including the exact user-visible answer and sentence offsets for every numeric token.
2. Persist structured-financial-field values plus report ID/year and an evidence/version hash.
3. Persist S4/S5 token-preservation diffs and retrieved chunk IDs/content hashes.
4. Persist citation/leak-gate and numeric-validator inputs separately from their outputs.
5. Preserve exact numeric token arrays rather than comma-joined error strings, which are ambiguous for thousands separators.

Only after a representative population identifies a dominant directly proven D1–D7 category should the owner authorize a single-scope remediation.

## 9. Gate failures and decision

This phase cannot pass an expansion or remediation gate because:

- 14/14 original invalid requests lack complete provenance snapshots.
- 42/42 token occurrences have no recoverable original answer sentence.
- Current runtime is non-release-representative.
- New supplements reproduced numeric/citation failures, LLM timeout/empty responses, and a report-selection failure.
- No dominant original D1–D7 root cause is directly proven.

Final decision: `HOLD_1_PERCENT`.
