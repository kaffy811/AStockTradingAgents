# Phase 6W-R3.2B Numeric Provenance

Date: 2026-08-21  
Baseline: `3c30787db82bc2a6de14042bbda2895f64f1b623`  
Branch: `release/demo-staging`  
Traffic: `HOLD_1_PERCENT`

## Serial acquisition

The five prescribed questions completed in order with unique sessions. There was no parallel execution, retry, replacement, or Redis flush. Every response was persisted before a wait of at least ten seconds and a successful backend DB/Redis health check.

| Query | Request ID | Selected report | Selection ms | Retrieval ms | S3 chunk IDs | Final status |
|---|---|---|---:|---:|---|---|
| Q1 revenue | `d1f2a4bc` | 17 / 2024 annual | 4343 | 1100.0 | 3663, 3664, 3665, 3666, 3670, 3671 | partial_success |
| Q2 net profit | `5c000075` | 17 / 2024 annual | 4501 | 1089.5 | 3663, 3664, 3665, 3666, 3670, 3671 | completed |
| Q3 profitability | `b8eaa253` | 17 / 2024 annual | 4708 | 1111.4 | 3663, 3664, 3665, 3666, 3670, 3671 | partial_success |
| Q4 operating cash flow | `558d8196` | 17 / 2024 annual | 5485 | 1328.4 | 3665, 3666, 3671, 3672, 3676, 3677 | partial_success |
| Q5 combined | `2bba83af` | 17 / 2024 annual | 4531 | 1661.0 | 3663, 3664, 3665, 3666, 3670, 3671 | partial_success |

All selection caches missed. Final-answer cache was bypassed. Evidence cache was written for every request. Structured-financial-field cache hit for every request. No retrieval timeout occurred.

## S4/S5 diff

| Query | S4 chars | S4 numbers | S5 chars | Preserved | Removed | Preserved units |
|---|---:|---:|---:|---:|---:|---|
| Q1 | 5344 | 146 | 1413 | 45 | 101 | %, 亿元, 元／股 |
| Q2 | 5344 | 146 | 1413 | 45 | 101 | %, 亿元, 元／股 |
| Q3 | 5344 | 146 | 1413 | 45 | 101 | %, 亿元, 元／股 |
| Q4 | 4051 | 178 | 1344 | 56 | 122 | %, 元／股 |
| Q5 | 5344 | 146 | 1413 | 45 | 101 | %, 亿元, 元／股 |

The compactor mechanically removes valid numbers present in S4. Key examples include raw-yuan revenue, net-profit and cash-flow values and their growth rates. Those fields may still reach synthesis through the separately serialized `structured_financial_data`; therefore all five samples meet the literal D1 condition, but none proves that compactor loss caused the observed unsupported tokens.

## Unsupported tokens

| Token | Query | Answer location | S3 content | S4 content | S5 content | Report semantic match | Classification | First introduced |
|---|---|---|---:|---:|---:|---:|---|---|
| 3670 | Q1 | `chunk 3670` in source prose | No | No | No | N/A | F / CHUNK_IDENTIFIER | S6 |
| 3670 | Q3 | `source_chunks ... 3670` | No | No | No | N/A | F / CHUNK_IDENTIFIER | S6 |
| 3670 | Q5 | `source_chunks ... 3670` | No | No | No | N/A | F / CHUNK_IDENTIFIER | S6 |
| 3677 | Q4 | `source_chunk 3677` | No | No | No | N/A | F / CHUNK_IDENTIFIER | S6 |
| 31 | Q4 | comparative period `2023年12月31日` | No | No | No | Yes, annual comparative period end | F / OTHER_METADATA | S6 |

`31` was not classified as a financial claim or B retrieval miss. It is the day component of an LLM-expanded comparative-period date. The report semantics are consistent, but that date was not present in the supplied evidence. It remains unsupported and correctly forces partial status.

No unsupported token was classified as A, B, C, D, E, G, or H. A whole-report search was unnecessary for the chunk identifiers. Treating a matching digit sequence elsewhere in the report as support would be semantically invalid.

## Metadata leakage chain

1. S3 contains raw database primary keys as metadata.
2. `_build_chunks_context()` sends `chunk_id` to the LLM.
3. The system output contract requires `source_chunks[].chunk_id` and illustrates it with a numeric ID.
4. S6 repeats raw IDs in natural-language answer prose in four of five samples.
5. `FundamentalReviewAgent._canonicalize_source_chunks()` rejects structured citation IDs outside `allowed_chunk_ids`, deduplicates valid IDs and canonicalizes metadata. It does not inspect the answer for raw-ID leakage.
6. The answer renderer extracts the model/reviewer answer; it does not concatenate structured citations.
7. The prompt already prohibits citation numbers in prose, but the model disobeys it.
8. The finalizer has no request-aware `retrieved chunk IDs + citation context` quality gate.

`3670` exists as S3 metadata, but it is absent from S4/S5 content and first becomes user-visible answer text at S6. Q2 proves structured citation IDs can remain outside answer prose, while Q1/Q3/Q4/Q5 prove the current contract does not enforce that separation.

Request-local `E1..En` identifiers are feasible: the backend can retain `E1 -> chunk_id` privately, validate the label against this request, validate claim numbers against the mapped evidence, and return canonical source metadata without exposing the database primary key to synthesis.

