# Phase 6W-R2.1 — Embedding Configuration

**Generated:** 2026-08-12  
**Branch:** release/demo-staging  
**HEAD:** a542bc1

---

## Configuration Applied

Added to root `.env`:

```
REPORT_EMBEDDING_PROVIDER=local
REPORT_EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
```

Root `.env` now contains both variables. Verified via grep.

---

## sentence-transformers Installation Status

| Check | Result |
|-------|--------|
| `sentence-transformers` in `backend/pyproject.toml` | **ABSENT** |
| `sentence-transformers` in venv | **NOT INSTALLED** |

**Impact analysis:**

`LocalSentenceTransformerProvider.__init__()` catches `ImportError` and sets `self._init_error = str(e)`.  
`is_available()` returns `False` when `_init_error` is set.  
`report_embedding_service.py` checks `provider.is_available()` — if False, returns `{"status": "skipped"}` without failing.  
Result: embedding step is **skipped**, `rag_status` stays `"chunked"`.

---

## Keyword Retrieval Path — NOT Affected by Embedding Provider

The indexed fast-path in `report_chat_copilot_agent.py` uses:

```python
def _query_indexed_report_db_evidence(self, ...):
    # Pure SQL ILIKE keyword search on company_v2_report_rag_chunks.text
    # Lines 558–648
    # search_mode = "indexed_db_lexical"
    # NO vector similarity, NO embeddings
```

`_is_indexed_report()` returns `True` when `rag_status in {"indexed","embedded","ready","chunked"}`.  
`rag_status="chunked"` → `True` → keyword search is triggered.

**Conclusion: REPORT_EMBEDDING_PROVIDER=local with sentence-transformers absent is NOT a P0 blocker for RAG retrieval.**

The config is correct and will activate properly when `sentence-transformers` is installed in future.

---

## Embedding Provider Decision Matrix

| Provider | sentence-transformers | Embedding | Keyword RAG | Decision |
|----------|----------------------|-----------|-------------|----------|
| `mock` | Not needed | Random vectors | Works | Unreliable similarity; keyword only works |
| `local` (no s-t) | Missing | Skipped | **Works** | **Current state — acceptable** |
| `local` (s-t installed) | Present | 384-dim BAAI/bge | Works | Full RAG quality |
| `openai` | Not needed | text-embedding-3 | Works | Requires OPENAI_API_KEY |

---

## If Full Vector RAG Is Required Later

```bash
# In backend container:
pip install sentence-transformers

# OR add to pyproject.toml:
# sentence-transformers = ">=2.2.0"
# Then: uv sync
```

Model will be downloaded on first initialization (~130MB for BAAI/bge-small-zh-v1.5).

---

*No application code was modified. Config-only change to root .env.*
