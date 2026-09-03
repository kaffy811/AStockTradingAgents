"""
app/core/error_codes.py — Stable API error codes for free-mode production.

All API error responses include an `error_code` field drawn from this module.
Frontend can branch on these codes to show localised copy.
"""

# ── Auth（Phase 6N-8A）─────────────────────────────────────────────────────────
AUTH_REQUIRED = "AUTH_REQUIRED"
"""Missing / invalid / expired access token. Frontend must show a login prompt,
NEVER a data-source-failure message."""

FORBIDDEN = "FORBIDDEN"
"""Authenticated but not allowed to access this resource."""

# ── Data source ───────────────────────────────────────────────────────────────
FREE_SOURCE_LIMITED = "FREE_SOURCE_LIMITED"
"""The requested metric is not available in free-mode data sources (BaoStock/AkShare)."""

DATA_SOURCE_UNAVAILABLE = "DATA_SOURCE_UNAVAILABLE"
"""All configured data sources for this query failed or are offline (network/timeout)."""

DATA_SOURCE_EMPTY = "DATA_SOURCE_EMPTY"
"""Data sources were reachable but returned no data for this query (Phase 6N-8A)."""

# ── Quote / market data（Phase 6N-8B）────────────────────────────────────────
QUOTE_PROVIDER_UNAVAILABLE = "QUOTE_PROVIDER_UNAVAILABLE"
"""Real-time or recent quote providers (Eastmoney/Sina/AkShare) are offline or network-
disconnected. Frontend should NOT attribute this to BaoStock/AkShare data absence.
Backend falls back to BaoStock kline recent close + valuation fields."""

SHARE_CAPITAL_MISSING = "SHARE_CAPITAL_MISSING"
"""market_cap cannot be computed because total_share / circ_share is unavailable from
free data sources. Display '—' with this reason."""

ALL_NULL_ROWS = "ALL_NULL_ROWS"
"""A financial module returned rows but all core fields are null/empty after low-cost
fill attempts. The frontend should hide the section and add it to unavailable list."""

CACHE_UNAVAILABLE = "CACHE_UNAVAILABLE"
"""Redis cache service is in circuit-breaker OPEN state; data was fetched directly
from provider. This is NOT a provider failure."""

PROVIDER_NETWORK_ERROR = "PROVIDER_NETWORK_ERROR"
PROVIDER_EMPTY = "PROVIDER_EMPTY"
PROVIDER_SCHEMA_CHANGED = "PROVIDER_SCHEMA_CHANGED"
PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
PROVIDER_EXCEPTION = "PROVIDER_EXCEPTION"
KLINE_PROVIDER_UNAVAILABLE = "KLINE_PROVIDER_UNAVAILABLE"
PDF_NOT_FOUND = "PDF_NOT_FOUND"
MAPPING_ERROR = "MAPPING_ERROR"
RENDER_ERROR = "RENDER_ERROR"
RENDER_RULE_ERROR = "RENDER_RULE_ERROR"
FRONTEND_RENDER_ERROR = "FRONTEND_RENDER_ERROR"

# ── Report PDF pipeline ───────────────────────────────────────────────────────
REPORT_PDF_NOT_FOUND = "REPORT_PDF_NOT_FOUND"
"""No annual/semi-annual report PDF found for this stock in the discovery index."""

REPORT_DISCOVERY_FAILED = "REPORT_DISCOVERY_FAILED"
"""Report discovery service failed to query CNINFO / SSE / SZSE."""

REPORT_DOWNLOAD_FAILED = "REPORT_DOWNLOAD_FAILED"
"""PDF download failed (network error or domain not on whitelist)."""

REPORT_PARSE_FAILED = "REPORT_PARSE_FAILED"
"""PDF text extraction failed (corrupted file or unsupported encoding)."""

# ── Report RAG / Embedding ────────────────────────────────────────────────────
REPORT_RAG_NOT_READY = "REPORT_RAG_NOT_READY"
"""No report chunks indexed for this stock; RAG cannot answer the question."""

REPORT_EMBEDDING_UNAVAILABLE = "REPORT_EMBEDDING_UNAVAILABLE"
"""Embedding provider is unavailable or misconfigured; cannot embed new chunks."""

# ── Report Chat ───────────────────────────────────────────────────────────────
REPORT_CHAT_RATE_LIMITED = "REPORT_CHAT_RATE_LIMITED"
"""Request rate limit exceeded. See Retry-After header for backoff duration."""

REPORT_CHAT_NO_EVIDENCE = "REPORT_CHAT_NO_EVIDENCE"
"""No relevant evidence found in the report index for the given question."""

# ── AI analysis（Phase 6N-8B）────────────────────────────────────────────────
DATA_PACK_EMPTY = "DATA_PACK_EMPTY"
"""Insufficient structured financial data to generate AI analysis. User should
refresh financial data or ingest an annual report PDF."""

REPORT_NOT_INGESTED = "REPORT_NOT_INGESTED"
"""No indexable annual report PDF ingested yet for this stock."""

AI_KEY_MISSING = "AI_KEY_MISSING"
"""AI service (LLM / embedding) is not configured (missing API key)."""

SOURCE_CHUNKS_EMPTY = "SOURCE_CHUNKS_EMPTY"
"""RAG retrieval returned zero source chunks; cannot generate report-grounded analysis."""

# ── Safety / Compliance ───────────────────────────────────────────────────────
INVESTMENT_ADVICE_BLOCKED = "INVESTMENT_ADVICE_BLOCKED"
"""Question was rejected because it requested investment advice (buy/sell/target price)."""

PROMPT_INJECTION_BLOCKED = "PROMPT_INJECTION_BLOCKED"
"""Question contained prompt injection patterns and was rejected before LLM call."""

SOURCE_CHUNK_INVALID = "SOURCE_CHUNK_INVALID"
"""Answer references source chunks that failed Review Agent validation."""

# ── Infrastructure ────────────────────────────────────────────────────────────
CORS_NOT_CONFIGURED = "CORS_NOT_CONFIGURED"
"""Request origin is not on the CORS allowlist (configured via CORS_ORIGINS env var)."""

# ── Unknown / Internal ────────────────────────────────────────────────────────
INTERNAL_ERROR = "INTERNAL_ERROR"
"""Unexpected internal error. Check server logs (request_id) for details."""
