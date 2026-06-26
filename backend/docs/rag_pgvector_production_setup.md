# RAG + pgvector Production Setup Guide

**Phase 2D.5 — Financial Knowledge Base: Production Enablement**

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Database Setup — pgvector Extension](#2-database-setup--pgvector-extension)
3. [Alembic Migration](#3-alembic-migration)
4. [Environment Variables](#4-environment-variables)
5. [Embedding Provider Configuration](#5-embedding-provider-configuration)
6. [Batch Retry Configuration](#6-batch-retry-configuration)
7. [Healthcheck Endpoint](#7-healthcheck-endpoint)
8. [Initial Embedding Backfill](#8-initial-embedding-backfill)
9. [RAG Search Weights Tuning](#9-rag-search-weights-tuning)
10. [MMR Diversity Settings](#10-mmr-diversity-settings)
11. [Running the Eval Suite](#11-running-the-eval-suite)
12. [Monitoring and Observability](#12-monitoring-and-observability)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| PostgreSQL | ≥ 14 | Required for `pgvector` |
| pgvector extension | ≥ 0.5.0 | Install from [pgvector/pgvector](https://github.com/pgvector/pgvector) |
| Python | ≥ 3.11 | Already required by this project |
| OpenAI API Key | — | Required for production embeddings; `mock` provider works for CI |

### Install pgvector on PostgreSQL (Ubuntu/Debian)

```bash
# Install build dependencies
sudo apt-get install -y postgresql-server-dev-14 build-essential git

# Clone and build pgvector
git clone https://github.com/pgvector/pgvector.git
cd pgvector
make
sudo make install

# Enable extension in your target database
psql -U postgres -d tradingagents -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### Install pgvector on macOS (Homebrew)

```bash
brew install pgvector
# Then in psql:
psql -U postgres -d tradingagents -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### Verify installation

```sql
SELECT * FROM pg_extension WHERE extname = 'vector';
-- Should return one row
```

---

## 2. Database Setup — pgvector Extension

The schema migration (`a2c5e8f1b4d7`) handles extension creation automatically with graceful fallback. If `pgvector` is not installed, the migration falls back to `TEXT` for the `embedding_vector` column and vector search becomes unavailable (keyword RAG still works).

**Columns added to `financial_document_chunks`:**

| Column | Type | Notes |
|---|---|---|
| `embedding_vector` | `vector(1536)` | Cosine-similarity search; falls back to `TEXT` |
| `embedding_model` | `VARCHAR(100)` | e.g. `text-embedding-3-small` |
| `embedded_at` | `TIMESTAMPTZ` | Timestamp of last embedding |

**Index created:**

```sql
CREATE INDEX ON financial_document_chunks
  USING hnsw (embedding_vector vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
```

The HNSW index provides sub-millisecond ANN (approximate nearest neighbour) search at scale.

---

## 3. Alembic Migration

```bash
# From the backend directory
uv run alembic upgrade head
```

The migration chain:
1. `d7e3a9b5c2f8` — Chat sessions/messages tables (Phase C3)
2. `a2c5e8f1b4d7` — pgvector embedding columns (Phase 2C)

Verify the migration ran correctly:

```bash
uv run alembic current
# Should show: a2c5e8f1b4d7 (head)
```

---

## 4. Environment Variables

Add the following to your `.env` file:

```dotenv
# ── Embedding Configuration ────────────────────────────────────────────────
# Provider: mock (CI/test), openai (production)
EMBEDDING_PROVIDER=openai

# OpenAI embedding model (default: text-embedding-3-small, 1536 dims)
EMBEDDING_MODEL=text-embedding-3-small

# Max texts per API call
EMBEDDING_BATCH_SIZE=64

# Batch-level retry settings (Phase 2D.5)
EMBEDDING_BATCH_RETRY_COUNT=2
EMBEDDING_BATCH_RETRY_BACKOFF_SECONDS=1.5
EMBEDDING_BATCH_TIMEOUT_SECONDS=30.0

# ── RAG Hybrid Search Weights ──────────────────────────────────────────────
RAG_VECTOR_WEIGHT=0.6
RAG_KEYWORD_WEIGHT=0.3
RAG_SOURCE_BOOST_WEIGHT=0.07
RAG_RECENCY_BOOST_WEIGHT=0.03

# ── MMR Diversity Settings ─────────────────────────────────────────────────
RAG_MMR_ENABLED=true
RAG_MMR_LAMBDA=0.7
RAG_MMR_MAX_PER_DOC=2

# ── OpenAI API Key ─────────────────────────────────────────────────────────
OPENAI_API_KEY=sk-your-key-here
```

---

## 5. Embedding Provider Configuration

### Mock Provider (CI / Development)

- No external API calls
- Deterministic SHA-256 PRNG embeddings
- Identical input always produces identical output
- L2-normalised (cosine similarity works correctly)
- Set `EMBEDDING_PROVIDER=mock`

### OpenAI Provider (Production)

- Model: `text-embedding-3-small` (1536 dims, $0.02/1M tokens)
- Requires `OPENAI_API_KEY`
- Internal request-level retry (3 attempts with exponential backoff)
- Batch-level retry for each sub-batch (configurable via env, Phase 2D.5)
- Texts truncated to 32,764 chars (~8,191 tokens) before API call

### DeepSeek Provider (Stub)

- Currently falls back to mock (DeepSeek embedding API not yet released)
- Will be updated when the endpoint is available

---

## 6. Batch Retry Configuration

Phase 2D.5 added per-batch retry logic for the OpenAI provider. This handles transient network errors without failing the entire document ingestion.

```
Retry logic (per batch):
  1st attempt  — immediate
  2nd attempt  — after BACKOFF seconds (default 1.5s)
  3rd attempt  — after BACKOFF * 2 seconds (default 3.0s)
  After 3 attempts — raises RuntimeError; ingest marks embedding as failed
```

The ingest layer (`financial_document_ingest.py`) catches embedding failures and stores `NULL` in `embedding_vector`, adding `"embedding_failed"` to the document's warnings. Keyword RAG still works for these documents; they will be picked up by the backfill job.

**Configuration:**

| Variable | Default | Description |
|---|---|---|
| `EMBEDDING_BATCH_RETRY_COUNT` | `2` | Additional retries after initial attempt |
| `EMBEDDING_BATCH_RETRY_BACKOFF_SECONDS` | `1.5` | Initial backoff (doubles each retry) |
| `EMBEDDING_BATCH_TIMEOUT_SECONDS` | `30.0` | Per-batch HTTP timeout |

---

## 7. Healthcheck Endpoint

Use the pgvector healthcheck to verify the production environment before enabling vector search:

```python
from app.agents.rag_healthcheck import check_pgvector_ready

health = await check_pgvector_ready(db)
# Returns:
# {
#     "ok":                   bool,
#     "extension_installed":  bool,
#     "embedding_column_exists": bool,
#     "vector_index_exists":  bool,
#     "chunks_total":         int,
#     "chunks_embedded":      int,
#     "embedding_coverage":   float,  # 0.0–1.0
#     "warnings":             list[str],
# }
```

Or via the admin API (if wired up):

```bash
curl http://localhost:8000/admin/rag/health
```

### Embedding Coverage Thresholds

| Coverage | Recommendation |
|---|---|
| `≥ 0.9` | Enable `EMBEDDING_PROVIDER=openai`, set `search_mode=hybrid` |
| `0.5 – 0.9` | Run backfill job; use `search_mode=hybrid` (graceful fallback for missing vectors) |
| `< 0.5` | Run backfill job; consider `search_mode=keyword` until backfill completes |
| `0.0` | pgvector not installed or migration not run |

---

## 8. Initial Embedding Backfill

After deploying with `EMBEDDING_PROVIDER=openai`, backfill existing chunks:

```bash
# Dry run — see how many chunks need embedding
uv run scripts/backfill_embeddings.py --dry-run

# Backfill all chunks (will prompt for confirmation)
uv run scripts/backfill_embeddings.py

# Backfill without confirmation prompt
uv run scripts/backfill_embeddings.py --yes

# Backfill in batches of 32 (lower API load)
uv run scripts/backfill_embeddings.py --batch-size 32

# Backfill only a specific stock
uv run scripts/backfill_embeddings.py --symbol AAPL --market US

# Limit to 1000 chunks for gradual rollout
uv run scripts/backfill_embeddings.py --limit 1000 --yes
```

**Estimated cost:** ~$0.02 per 1M tokens. A typical annual report chunk is ~200 tokens, so 10,000 chunks ≈ 2M tokens ≈ $0.04.

**Runtime:** Approximately 1,000–2,000 chunks/minute at batch_size=64, depending on API rate limits.

---

## 9. RAG Search Weights Tuning

The hybrid score formula:

```
combined = rag_vector_weight  * vector_score    (cosine similarity, 0–1)
         + rag_keyword_weight * keyword_score   (term frequency, normalised 0–1)
         + source_boost                         (≤ rag_source_boost_weight)
         + recency_boost                        (≤ rag_recency_boost_weight)
```

### Default weights (balanced)

```dotenv
RAG_VECTOR_WEIGHT=0.6
RAG_KEYWORD_WEIGHT=0.3
RAG_SOURCE_BOOST_WEIGHT=0.07
RAG_RECENCY_BOOST_WEIGHT=0.03
```

### Keyword-heavy (lower embedding coverage, early rollout)

```dotenv
RAG_VECTOR_WEIGHT=0.3
RAG_KEYWORD_WEIGHT=0.6
RAG_SOURCE_BOOST_WEIGHT=0.07
RAG_RECENCY_BOOST_WEIGHT=0.03
```

### Vector-dominant (high coverage, semantic queries)

```dotenv
RAG_VECTOR_WEIGHT=0.75
RAG_KEYWORD_WEIGHT=0.15
RAG_SOURCE_BOOST_WEIGHT=0.07
RAG_RECENCY_BOOST_WEIGHT=0.03
```

### Source authority boosts

| Source Level | Max Boost | Examples |
|---|---|---|
| `official_exchange` | `rag_source_boost_weight` (0.07) | sec.gov, sse.com.cn, hkexnews.hk |
| `official_company` | `rag_source_boost_weight × 0.85` | Company IR pages |
| `authoritative_media` | `rag_source_boost_weight × 0.5` | eastmoney.com, xueqiu.com, nasdaq.com |
| `general` | `0.0` | Blogs, forums |

---

## 10. MMR Diversity Settings

Phase 2D.5 introduces **True Cosine-MMR** when chunk embedding vectors are available:

```
MMR(d) = λ * Rel(d, q) - (1-λ) * max_{s ∈ Selected} cos(d, s)
```

When vectors are absent (keyword-only results), the system falls back to **per-doc cap** diversity.

The `diagnostics.mmr_strategy` field in search responses reports which strategy was used:

| Strategy | Condition | Description |
|---|---|---|
| `"cosine"` | All candidates have `embedding_vector` | True semantic diversity via cosine similarity |
| `"per_doc_cap"` | Some/all candidates lack vectors | Limit to `rag_mmr_max_per_doc` chunks per document |
| `"disabled"` | `RAG_MMR_ENABLED=false` | No diversity filtering |

### Configuration

```dotenv
RAG_MMR_ENABLED=true         # Enable MMR diversity
RAG_MMR_LAMBDA=0.7           # 0=max diversity, 1=max relevance
RAG_MMR_MAX_PER_DOC=2        # Max chunks per document in per_doc_cap fallback
```

### Tuning `RAG_MMR_LAMBDA`

| Lambda | Effect | Use case |
|---|---|---|
| `0.5` | Balanced diversity and relevance | General use |
| `0.7` (default) | Relevance-leaning with diversity | Most financial queries |
| `0.9` | High relevance, minimal diversity | Known-document lookup |
| `0.3` | High diversity | Exploratory research |

---

## 11. Running the Eval Suite

### Quick offline eval (no DB needed)

```bash
uv run scripts/run_rag_eval.py
```

This uses the mock DB (returns each eval case's own document), so it runs entirely offline and completes in seconds.

### With real database

```bash
uv run scripts/run_rag_eval.py \
  --db-url "postgresql+asyncpg://user:pass@localhost/tradingagents" \
  --search-mode hybrid \
  --top-k 5
```

### Save reports

```bash
uv run scripts/run_rag_eval.py \
  --output /tmp/rag_eval_report.json \
  --html /tmp/rag_eval_report.html
```

### Passing thresholds

| Metric | Target | Notes |
|---|---|---|
| Recall@5 | ≥ 0.85 | Fraction of cases with ≥1 keyword in top-5 |
| MRR | ≥ 0.70 | Mean reciprocal rank of first keyword hit |
| nDCG@5 | ≥ 0.75 | Normalised discounted cumulative gain |

---

## 12. Monitoring and Observability

### Key diagnostics returned by `financial_rag_search`

```json
{
  "diagnostics": {
    "search_mode_requested":            "hybrid",
    "search_mode_used":                 "hybrid",
    "vector_available":                 true,
    "keyword_fallback_used":            false,
    "embedding_provider":               "openai",
    "candidate_count":                  20,
    "returned_count":                   5,
    "mmr_enabled":                      true,
    "mmr_strategy":                     "cosine",
    "score_weights":                    {"vector": 0.6, "keyword": 0.3, "source": 0.07, "recency": 0.03},
    "embedding_coverage_in_candidates": 1.0,
    "official_source_ratio":            0.6
  }
}
```

### Log messages to monitor

| Message | Severity | Action |
|---|---|---|
| `"Vector embedding unavailable … fallback keyword"` | INFO | Check `OPENAI_API_KEY`; monitor frequency |
| `"backfill running with EMBEDDING_PROVIDER=mock"` | WARNING | Set `EMBEDDING_PROVIDER=openai` before backfill |
| `"OpenAI batch embed attempt N failed"` | WARNING | Transient; will retry |
| `"OpenAI batch embedding failed after N attempts"` | ERROR | API down or key invalid |
| `"backfill complete: scanned=X embedded=Y failed=Z"` | INFO | Check `failed` count |

---

## 13. Troubleshooting

### Vector search returns 0 results

1. Check `diagnostics.vector_available` — if `false`, embedding failed
2. Check `diagnostics.keyword_fallback_used` — if `true`, vector is unavailable
3. Run `check_pgvector_ready()` and check `embedding_coverage`
4. Verify `EMBEDDING_PROVIDER=openai` and `OPENAI_API_KEY` are set
5. Run backfill: `uv run scripts/backfill_embeddings.py --dry-run`

### High latency in hybrid mode

1. Check if the HNSW index exists: `SELECT indexname FROM pg_indexes WHERE tablename = 'financial_document_chunks'`
2. If missing, re-run migration or create manually:
   ```sql
   CREATE INDEX ON financial_document_chunks
     USING hnsw (embedding_vector vector_cosine_ops)
     WITH (m = 16, ef_construction = 64);
   ```
3. Reduce `EMBEDDING_BATCH_SIZE` to lower API call latency

### Embedding backfill is slow

1. Increase `EMBEDDING_BATCH_SIZE` (max 2048 for `text-embedding-3-small`)
2. Check OpenAI rate limits (default: 1M tokens/min for tier 2)
3. Use `--limit` to run backfill in stages:
   ```bash
   for limit in 1000 2000 3000; do
     uv run scripts/backfill_embeddings.py --limit $limit --yes
   done
   ```

### `pgvector` extension not found

```sql
-- Check if extension is available
SELECT name FROM pg_available_extensions WHERE name = 'vector';

-- If missing, install pgvector (see §1) then:
CREATE EXTENSION vector;
```

If pgvector cannot be installed (e.g., managed cloud Postgres without extension support), use keyword-only mode:

```dotenv
EMBEDDING_PROVIDER=mock
# And in search calls: search_mode=keyword
```

Keyword RAG is fully functional without pgvector; only semantic/hybrid search requires it.

---

*Last updated: Phase 2D.5 — 2026-06-24*
