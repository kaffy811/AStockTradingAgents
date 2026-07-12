from __future__ import annotations

import os

# Phase 6T-J1: unit tests explicitly inject the in-memory RAG repository so the
# suite never writes the production company_v2_report_rag_* tables. Persistence
# tests construct DatabaseCompanyV2ReportRagRepository explicitly with isolated
# report_ids and clean up after themselves.
os.environ.setdefault("COMPANY_V2_RAG_REPOSITORY_BACKEND", "memory")

os.environ["CORS_ORIGINS"] = (
    "["
    '"http://localhost:3000",'
    '"http://localhost:3001",'
    '"http://localhost:3002",'
    '"http://localhost:5173",'
    '"http://localhost:5174",'
    '"http://127.0.0.1:3000",'
    '"http://127.0.0.1:3001",'
    '"http://127.0.0.1:3002",'
    '"http://127.0.0.1:5173",'
    '"http://127.0.0.1:5174"'
    "]"
)
