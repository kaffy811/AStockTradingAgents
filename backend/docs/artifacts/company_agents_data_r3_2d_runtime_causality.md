# Phase 6W-R3.2D — Runtime Causality

Date: 2026-08-26 (America/New_York)

Traffic: `HOLD_1_PERCENT`

Performance evidence label: `NON-RELEASE-REPRESENTATIVE`

## 1. Release integrity

| Item | Observed value | Conclusion |
|---|---|---|
| Git HEAD | `9c65027eeef5d599ae13083affc926497a4d2432` | Expected D3 commit |
| Branch | `release/demo-staging` | Expected |
| Tracked dirty files | `backend/Dockerfile`, `backend/app/main.py`, `backend/app/services/report_embedding_provider.py`, `backend/pyproject.toml`, `backend/uv.lock` | Preserved; not staged |
| `git diff --check` | PASS | No whitespace error |
| Container | `tradingagents-backend-1`, ID `c9567bfdfec4892823d7a5febd09d1cba2e4fac2ba6dd300082f74bfd0140bee` | Running |
| Container created | `2026-08-23T01:34:13.297204344Z` | Predates current observation |
| Container started | `2026-08-23T01:34:14.117434553Z` | No restart in this phase |
| Image | `tradingagents-backend:latest` / `sha256:48a50ce2435e379c46f0ed0afa1878a5f9c8e9f223dcb418bb4bbc1a944987db` | Exact runtime image identity |
| Image created | `2026-08-23T01:34:12.784755969Z` | Predates current observation |
| Bind mounts | none (`Mounts=[]`) | Host source does not live-overlay `/app` |
| Revision label | absent | Image cannot be cryptographically associated with `9c65027` |

The image is not a clean build of commit `9c65027`. Container hashes for `/app/app/main.py`, the embedding provider, `pyproject.toml`, and `uv.lock` exactly match the current dirty worktree and differ from the corresponding HEAD blobs. Docker history also contains the dirty Dockerfile's `sentence-transformers` sync and E5 model preload layers. Thus the runtime includes the uncommitted dependency and startup-warmup work. All latency and reliability results below are **NON-RELEASE-REPRESENTATIVE** and cannot authorize expansion.

## 2. Runtime configuration versus actual invocation

Runtime configuration is `provider=local`, model `intfloat/multilingual-e5-small`, dimension `384`; installed `sentence-transformers=5.7.0`. This only proves availability/configuration.

Every actual fresh Company V2 request below invoked:

```text
indexed_fast_path
→ _query_indexed_report_db_evidence()
→ company_v2_report_rag_chunks
→ search_mode=indexed_db_lexical
→ provider=indexed_report_db
```

Provider use in the 10-request fresh population:

| Actual provider/path | Requests | Share |
|---|---:|---:|
| `indexed_report_db` / `indexed_db_lexical` | 10 | 100% |
| local sentence-transformer | 0 | 0% |
| `MockReportEmbeddingProvider` | 0 | 0% |

No actual-request evidence supports Mock as a timeout cause. The prior claim “missing sentence-transformers caused Company V2 indexed-fast-path timeout” is **denied for this observed call chain**: the path is lexical SQL and does not invoke either local or Mock embeddings. This does not prove how an older image/path behaved; that historical causality remains unverified.

## 3. Ten unique fresh requests

All requests used unique sessions, `force_refresh=true`, report 17, year 2024 annual, `top_k=6`, and evidence-cache miss. They were issued serially with at least 10 seconds between requests. DB/Redis health was checked between requests. Raw chunk IDs below are diagnostic-only.

| ID | Request ID | Chunks | Selection ms | Retrieval ms | LLM ms | Overall ms | Result |
|---|---|---|---:|---:|---:|---:|---|
| Q1 | `1ba58dca` | 3663,3664,3665,3666,3670,3671 | 5436 | 1354.9 | 27426 | 35116.7 | completed / numeric valid |
| Q2 | `3c1df20a` | 3663,3664,3665,3666,3670,3671 | 5386 | 1250.2 | 18192 | 25620.4 | completed / numeric valid |
| Q3 | `a8daa206` | 3662,3663,3664,3665,3666,3667 | 4981 | 1343.7 | 14193 | 21374.2 | completed / numeric valid |
| Q4 | `a270890d` | 3665,3666,3671,3672,3676,3677 | 5468 | 1316.3 | 21898 | 29546.8 | completed / numeric valid |
| Q5 | `8643383a` | 3665,3666,3671,3672,3676,3677 | 5236 | 1289.8 | 89867 | 97214.5 | partial / unsupported `79.39,121.78` |
| Q6 | `a7e5b325` | 3662,3663,3664,3665,3666,3667 | 5190 | 1418.2 | 13910 | 21293.2 | completed / numeric valid |
| Q7 | `bc220c45` | 3663,3664,3665,3666,3670,3671 | 5455 | 1325.5 | 34007 | 41618.0 | completed / numeric valid |
| Q8 | `0386c022` | 3662,3663,3664,3665,3666,3667 | 5161 | 1232.7 | 21183 | 28387.4 | completed / numeric valid |
| Q9 | `3688f30f` | 3663,3670,3681,3691,3694,3695 | 5252 | 1410.1 | 17539 | 24988.0 | partial / unsupported `12,31` |
| Q10 | `cabb63cd` | 3663,3664,3665,3666,3670,3671 | 5224 | 1485.6 | 34500 | 42025.3 | completed / numeric valid |

Summary: selected report correct 10/10; six chunks 10/10; retrieval timeout 0/10; completed 8/10; partial 2/10; numeric valid 8/10. Retrieval median is `(1325.5+1343.7)/2 = 1334.6 ms`; observed max 1485.6 ms. LLM median is `(21183+21898)/2 = 21540.5 ms`; observed max 89867 ms. Overall median is `(28387.4+29546.8)/2 = 28967.1 ms`; observed max 97214.5 ms. The long Q5 result is synthesis-side, not retrieval-side.

## 4. Cache-only characterization

One separately labelled request outside the 30-request population reused Q10's completed session and answer key. It produced an explicit final-answer cache hit in 4.8 ms: completed, numeric valid, all stage timings zero, no retrieval or LLM call. This is the C cache-hit latency sample and is not mixed with fresh latency.

## 5. Causality conclusion

- Confirmed: current Company V2 fresh path is bounded lexical SQL; 10/10 fresh and 18/18 later observation retrieval calls used it.
- Confirmed: no retrieval timeout occurred in either population.
- Confirmed: LLM/numeric failures remain and are not RAG retrieval timeouts.
- Confirmed: current image includes dirty dependency/warmup changes and is not a pure release image.
- Not confirmed: whether startup warmup caused the absence of first-request timeout. No clean-image A/B exists.
- Not confirmed: whether an older runtime actually invoked Mock. Static fallback capability is not invocation evidence.

Decision: `HOLD_1_PERCENT`.
