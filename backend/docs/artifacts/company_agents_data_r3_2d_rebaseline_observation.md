# Phase 6W-R3.2D — R3.1 Re-baseline Observation

Date: 2026-08-26 (America/New_York)

Baseline HEAD: `9c65027eeef5d599ae13083affc926497a4d2432`

Runtime evidence: `NON-RELEASE-REPRESENTATIVE`

Traffic: `HOLD_1_PERCENT`

## 1. Population and limitation

The R3.1 report preserved the batch shape but not its exact 30-request manifest. This run therefore reproduces the documented population shape—A6, B3, C5, D2, E4, F1, G9—and does not claim a byte-for-byte request replay. Thirty requests ran in one foreground process, strictly serially, with atomic per-request persistence and 10-second spacing. No failed request was retried.

The image cannot be tied to a clean `9c65027` build and contains the existing dirty Docker/dependency/warmup files. All results are non-release-representative.

## 2. Aggregate results

| Metric | R3.1 historical | R3.2D |
|---|---:|---:|
| Requests | 30 | 30 |
| completed | mixed; cache path 17/17, cold 3/9 | 8/30 |
| partial_success | cold 4/9 | 22/30 |
| failed HTTP/client | reported timeouts/errors | 0/30 |
| RAG retrieval timeout | about 4/8 fresh evidence requests | 0/30 |
| LLM timeout | observed R2 | 1/30 (`Y2`) |
| numeric validation invalid | cold 4/9 | 14/30 |
| numeric validation null | not normalized | 7/30, mainly empty LLM responses/timeout |
| wrong report year | 0 | 0 |

Status by batch:

| Batch | N | Completed | Partial | RAG timeout | LLM timeout | Numeric invalid |
|---|---:|---:|---:|---:|---:|---:|
| A | 6 | 0 | 6 | 0 | 0 | 3 |
| B | 3 | 2 | 1 | 0 | 0 | 1 |
| C | 5 | 1 | 4 | 0 | 1 | 2 |
| D | 2 | 2 | 0 | 0 | 0 | 0 |
| E | 4 | 2 | 2 | 0 | 0 | 1 |
| F | 1 | 0 | 1 | 0 | 0 | 1 |
| G | 9 | 1 | 8 | 0 | 0 | 6 |

## 3. Actual path and cache distribution

| Route actually used | Count | Provider |
|---|---:|---|
| Fresh lexical DB call | 18 | `indexed_report_db` / `indexed_db_lexical` |
| Evidence-cache hit, no retrieval call | 12 | origin lexical; no provider invoked in request |
| Local sentence-transformer call | 0 | — |
| Mock provider call | 0 | — |

No final-answer cache hit occurred within the 30 requests. The first seed failed to create a successful final answer and session isolation prevented treating later requests as final-cache hits. Therefore nominal A/G cache labels are not used as proof of final cache behavior. A separate, explicitly excluded cache-only probe produced `final_answer=hit` in 4.8 ms.

Retrieval-only latency for the 18 actual DB calls: sorted range 652.1–2180.6 ms; median `(782.9+815.3)/2 = 799.1 ms`; no timeout. Fresh full-synthesis overall latency: 9.38–92.76 s, median `(39.41+41.73)/2 = 40.57 s`. Evidence-cache-with-synthesis latency: 9.41–84.13 s, median `(12.31+12.48)/2 = 12.39 s`. These populations must not be mixed with the 4.8 ms final-answer cache hit.

The 30-request diagnostic retained overall and retrieval timings but not exact per-request `llm_total_ms`; LLM timeout classification comes from response errors. Exact LLM timing distribution is available for the independent 10-fresh population: median 21.54 s, max 89.87 s. This limitation is recorded rather than back-calculating LLM time from overall latency.

## 4. Per-request observation

`e-cache` means evidence was reused and no retrieval provider ran in that request.

| Run | Request | Report/year | Retrieval path | Retrieval ms | Overall ms | Timeout | Result |
|---|---|---|---|---:|---:|---|---|
| W1 | `a8c8ddf2` | 17/2024 | lexical | 1152.2 | 17137.5 | none | partial, empty LLM |
| W2 | `b1c9e518` | 17/2024 | e-cache | 0 | 50677.3 | none | partial, citation/numeric |
| W3 | `c561c15c` | 17/2024 | e-cache | 0 | 9406.0 | none | partial, empty LLM |
| W4 | `1e8b52a7` | 17/2024 | e-cache | 0 | 9644.0 | none | partial, empty LLM |
| W5 | `be143efa` | 17/2024 | e-cache | 0 | 11017.2 | none | partial, citation/numeric |
| W6 | `8d207e5c` | 17/2024 | e-cache | 0 | 16462.0 | none | partial, numeric |
| C1 | `63e0a7dd` | 17/2024 | lexical | 1096.5 | 58803.9 | none | completed |
| C2 | `3b291b2d` | 17/2024 | lexical | 1056.3 | 69542.0 | none | partial, numeric |
| C3 | `99312be8` | 17/2024 | lexical | 874.9 | 74533.1 | none | completed |
| Y1 | `2487df52` | 17/2024 | lexical | 815.3 | 41726.1 | none | partial, citation |
| Y2 | `2b1d19bd` | 2/2025 | lexical | 752.7 | 92755.7 | LLM | partial, LLM timeout |
| Y3 | `53d32a61` | 17/2024 | lexical | 839.8 | 39408.9 | none | partial, citation/numeric |
| Y4 | `9ca90af7` | 2/2025 | lexical | 717.0 | 74736.1 | none | partial, numeric |
| Y5 | `d0ad25d3` | 17/2024 | lexical | 738.0 | 60493.0 | none | completed |
| D1 | `4770497f` | 17/2024 | lexical | 865.4 | 11131.5 | none | completed |
| D2 | `b873f320` | 17/2024 | lexical | 1051.1 | 35143.5 | none | completed |
| R1 | `682656ad` | 17/2024 | lexical | 760.4 | 44252.0 | none | completed |
| R2 | `128b5bbd` | 17/2024 | lexical | 652.1 | 9375.3 | none | partial, empty LLM |
| R3 | `a167c86d` | 17/2024 | lexical | 654.5 | 34814.5 | none | partial, numeric |
| R4 | `4fa441cb` | 17/2024 | lexical | 782.9 | 23547.2 | none | completed |
| F1 | `a50ca0bc` | 2/2025 | lexical | 709.5 | 73357.9 | none | partial, numeric |
| G1 | `ef099d5c` | 17/2024 | e-cache | 0 | 33690.4 | none | partial, citation/numeric |
| G2 | `4249ea53` | 17/2024 | e-cache | 0 | 36494.3 | none | partial, citation/numeric |
| G3 | `cbde38fc` | 17/2024 | e-cache | 0 | 12478.3 | none | partial, numeric |
| G4 | `fa77e78f` | 17/2024 | e-cache | 0 | 12310.1 | none | partial, empty LLM |
| G5 | `a95afb5d` | 17/2024 | e-cache | 0 | 9955.6 | none | partial, empty LLM |
| G6 | `067b2be3` | 17/2024 | lexical | 2180.6 | 16277.6 | none | partial, citation/numeric |
| G7 | `6a97fbf6` | 17/2024 | e-cache | 0 | 84132.4 | none | partial, citation/numeric |
| G8 | `1a24dc19` | 17/2024 | lexical | 725.7 | 36334.6 | none | completed |
| G9 | `8b761b0d` | 17/2024 | e-cache | 0 | 43604.5 | none | partial, citation/numeric |

## 5. Confirmed causes and rejected assumptions

- The old fresh-RAG timeout was not reproduced: 0/10 in the independent fresh population and 0/18 actual retrieval calls in this observation.
- Current failures are principally synthesis/citation/numeric quality failures. One explicit LLM timeout occurred. They must not be attributed to retrieval.
- Mock/local embeddings were not invoked. The sentence-transformers-missing hypothesis is therefore not a cause of the currently observed Company V2 path.
- The absence of current retrieval timeouts cannot be causally assigned to sentence-transformers installation or startup warmup because the lexical path bypasses embeddings and no clean runtime A/B exists.
- D3 containment remains committed, but citation-validation failures still occur in this non-release-representative runtime and require a separately authorized diagnosis; no code was changed here.

## 6. Gate

HOLD conditions met:

1. Runtime image cannot be associated with a clean committed SHA and contains dirty changes.
2. Numeric validation failures occurred.
3. An LLM timeout occurred.
4. Final-cache population was not reproducible within the historical 30-request shape because the original exact manifest was unavailable and the seed did not produce a final cached answer.

No production code, Dockerfile, dependency, configuration, secret, timeout, cache, retrieval, validator, image, deployment, commit, push, or traffic setting was changed.

Final decision: `HOLD_1_PERCENT`.
