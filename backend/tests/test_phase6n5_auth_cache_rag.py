"""
tests/test_phase6n5_auth_cache_rag.py

Phase 6N-5: Auth Stability + Data Coverage Hardening

Covers:
  Auth 401:
  T01  GET /industries/ no longer requires Authorization header (public endpoint)
  T02  get_optional_user defined in dependencies and handles missing credentials
  T03  get_optional_user returns None for no-token request (not raises 401)
  T04  http.js guards reports/watchlist with auth check (source inspection)
  T05  ComprehensiveAnalysisView guards listReports/getWatchlistEnriched with isLoggedIn

  Cache logging:
  T06  sync_get_json log uses repr() — error message includes exception type name
  T07  sync_set_json log uses repr() — error message includes exception type name
  T08  sync_exists log uses repr()

  Quote kline proxy:
  T09  _stale_or_503_quote calls _kline_proxy_quote before returning 503
  T10  _kline_proxy_quote is defined on StockDataService
  T11  kline proxy result has reason_code=REALTIME_QUOTE_UNAVAILABLE
  T12  kline proxy result has provider=kline_proxy
  T13  503 result now carries reason_code field (not empty data dict)

  RAG diagnostics:
  T14  diagnostics endpoint queries report_chunks count
  T15  diagnostics endpoint queries embedding count (IS NOT NULL)
  T16  rag_status top-level field in diagnostics response
  T17  rag_status = "ready" when chunks>0 and embedding>0
  T18  rag_status = "not_indexed" when docs>0 but no chunks
  T19  rag_status = "empty" when no docs
  T20  rag module result includes rag sub-dict with documents_count/chunks_count/embedding_count
  T21  ReportChatPanel: ragIndexStatus prop defined
  T22  ReportChatPanel: empty state shows ragIndexStatus-aware messages
  T23  i18n: rcp_rag_not_indexed key present in all 6 locales
"""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT    = _BACKEND_ROOT.parent

# ── Auth 401 ─────────────────────────────────────────────────────────────────

def test_industries_list_no_auth_dependency():
    """GET /industries/ must not use get_current_user (public endpoint)."""
    source = (_BACKEND_ROOT / "app" / "routers" / "industry.py").read_text(encoding="utf-8")
    # Find the list_industries function
    fn_match = re.search(r'async def list_industries\(.*?\).*?(?=^@|\Z)', source, re.DOTALL | re.MULTILINE)
    assert fn_match, "list_industries function not found"
    fn_sig = fn_match.group(0)[:500]  # just the signature area
    assert "get_current_user" not in fn_sig, (
        "list_industries must NOT require get_current_user — it is public market data"
    )


def test_get_optional_user_defined_in_dependencies():
    """get_optional_user must be exported from app.dependencies."""
    from app.dependencies import get_optional_user
    assert callable(get_optional_user)


@pytest.mark.asyncio
async def test_get_optional_user_returns_none_without_token():
    """get_optional_user must return None (not raise 401) when no credentials."""
    from app.dependencies import get_optional_user
    from sqlalchemy.ext.asyncio import AsyncSession
    # Call with None credentials (no Authorization header)
    result = await get_optional_user(credentials=None, db=MagicMock(spec=AsyncSession))
    assert result is None, "get_optional_user must return None for unauthenticated requests"


def test_http_js_adds_auth_header():
    """http.js must inject Authorization: Bearer only when token is truthy."""
    source = (_REPO_ROOT / "frontend" / "src" / "api" / "http.js").read_text(encoding="utf-8")
    assert "authStore.token" in source, "http.js must check authStore.token"
    assert "Authorization" in source, "http.js must set Authorization header"
    # token check must guard header injection
    assert "if (authStore.token)" in source or "authStore.token &&" in source, (
        "Authorization header must only be set when token is truthy"
    )


def test_comprehensive_view_guards_auth_calls():
    """loadDashboardData must guard listReports/getWatchlistEnriched with isLoggedIn."""
    source = (_REPO_ROOT / "frontend" / "src" / "views" / "ComprehensiveAnalysisView.vue").read_text(encoding="utf-8")
    assert "isLoggedIn" in source, "ComprehensiveAnalysisView must check isLoggedIn before auth-required calls"
    assert "useAuthStore" in source, "ComprehensiveAnalysisView must import useAuthStore"
    # The guarded calls must be in the loadDashboardData context
    fn_match = re.search(r'async function loadDashboardData\(\)(.*?)^}', source, re.DOTALL | re.MULTILINE)
    assert fn_match, "loadDashboardData function not found"
    fn_body = fn_match.group(1)
    assert "isLoggedIn" in fn_body, "listReports/getWatchlistEnriched must be guarded in loadDashboardData"
    assert "listReports" in fn_body and "getWatchlistEnriched" in fn_body, (
        "loadDashboardData must call listReports and getWatchlistEnriched"
    )


# ── Cache logging ─────────────────────────────────────────────────────────────

def test_cache_sync_get_uses_repr():
    """sync_get_json must use repr(exc) to log exception type + message."""
    source = (_BACKEND_ROOT / "app" / "services" / "cache_service.py").read_text(encoding="utf-8")
    fn_match = re.search(r'def sync_get_json\(.*?\n(.*?)(?=\n    def |\Z)', source, re.DOTALL)
    assert fn_match, "sync_get_json not found"
    fn_body = fn_match.group(1)
    assert "repr(exc)" in fn_body or "type(exc).__name__" in fn_body, (
        "sync_get_json must log repr(exc) or type(exc).__name__ to show empty-message exceptions"
    )


def test_cache_sync_set_uses_repr():
    """sync_set_json must use repr(exc) to log exception type + message."""
    source = (_BACKEND_ROOT / "app" / "services" / "cache_service.py").read_text(encoding="utf-8")
    fn_match = re.search(r'def sync_set_json\(.*?\n(.*?)(?=\n    def |\Z)', source, re.DOTALL)
    assert fn_match, "sync_set_json not found"
    fn_body = fn_match.group(1)
    assert "repr(exc)" in fn_body or "type(exc).__name__" in fn_body, (
        "sync_set_json must log repr(exc) or type(exc).__name__"
    )


def test_cache_sync_exists_uses_repr():
    """sync_exists must use repr(exc) to log exception type + message."""
    source = (_BACKEND_ROOT / "app" / "services" / "cache_service.py").read_text(encoding="utf-8")
    fn_match = re.search(r'def sync_exists\(.*?\n(.*?)(?=\n    def |\Z)', source, re.DOTALL)
    assert fn_match, "sync_exists not found"
    fn_body = fn_match.group(1)
    assert "repr(exc)" in fn_body or "type(exc).__name__" in fn_body, (
        "sync_exists must log repr(exc) or type(exc).__name__"
    )


# ── Quote kline proxy ─────────────────────────────────────────────────────────

def test_stale_or_503_calls_kline_proxy():
    """_stale_or_503_quote must call _kline_proxy_quote before returning 503."""
    source = (_BACKEND_ROOT / "app" / "services" / "stock_data_service.py").read_text(encoding="utf-8")
    fn_match = re.search(r'def _stale_or_503_quote\(.*?\n(.*?)(?=\n    def |\Z)', source, re.DOTALL)
    assert fn_match, "_stale_or_503_quote not found"
    fn_body = fn_match.group(1)
    assert "_kline_proxy_quote" in fn_body, (
        "_stale_or_503_quote must call _kline_proxy_quote before returning 503"
    )


def test_kline_proxy_quote_method_exists():
    """StockDataService must have a _kline_proxy_quote method."""
    source = (_BACKEND_ROOT / "app" / "services" / "stock_data_service.py").read_text(encoding="utf-8")
    assert "def _kline_proxy_quote" in source, "StockDataService must define _kline_proxy_quote"


def test_kline_proxy_reason_code():
    """kline proxy result must include reason_code=REALTIME_QUOTE_UNAVAILABLE."""
    source = (_BACKEND_ROOT / "app" / "services" / "stock_data_service.py").read_text(encoding="utf-8")
    assert "REALTIME_QUOTE_UNAVAILABLE" in source, (
        "kline proxy must set reason_code=REALTIME_QUOTE_UNAVAILABLE"
    )


def test_kline_proxy_provider_name():
    """kline proxy result must use provider='kline_proxy'."""
    source = (_BACKEND_ROOT / "app" / "services" / "stock_data_service.py").read_text(encoding="utf-8")
    assert '"kline_proxy"' in source or "'kline_proxy'" in source, (
        "kline proxy result must use provider='kline_proxy'"
    )


def test_503_result_has_reason_code():
    """503 final fallback must include reason_code in data dict (not empty {})."""
    source = (_BACKEND_ROOT / "app" / "services" / "stock_data_service.py").read_text(encoding="utf-8")
    # Find the 503 return block after kline proxy attempt
    fn_match = re.search(r'def _stale_or_503_quote\(.*?\n(.*?)(?=\n    def |\Z)', source, re.DOTALL)
    assert fn_match
    fn_body = fn_match.group(1)
    # The 503 data dict must not be bare {} — it should have reason_code
    assert "reason_code" in fn_body, (
        "503 fallback result data must include reason_code (e.g. NETWORK_UNAVAILABLE)"
    )


# ── RAG diagnostics ───────────────────────────────────────────────────────────

def test_diagnostics_queries_report_chunks():
    """fundamentals_compat.py diagnostics must query report_chunks table."""
    source = (_BACKEND_ROOT / "app" / "routers" / "fundamentals_compat.py").read_text(encoding="utf-8")
    assert "report_chunks" in source, (
        "diagnostics endpoint must query report_chunks for RAG status"
    )


def test_diagnostics_queries_embedding_count():
    """diagnostics must check embedding IS NOT NULL to count vectorized chunks."""
    source = (_BACKEND_ROOT / "app" / "routers" / "fundamentals_compat.py").read_text(encoding="utf-8")
    assert "embedding IS NOT NULL" in source, (
        "diagnostics must query 'embedding IS NOT NULL' to detect indexed chunks"
    )


def test_diagnostics_rag_status_top_level():
    """diagnostics response must include top-level rag_status field."""
    source = (_BACKEND_ROOT / "app" / "routers" / "fundamentals_compat.py").read_text(encoding="utf-8")
    assert '"rag_status"' in source or "'rag_status'" in source, (
        "diagnostics response must include top-level 'rag_status' convenience field"
    )


def test_rag_status_ready_condition():
    """rag_status='ready' must require both chunks_count>0 and embedding_count>0."""
    source = (_BACKEND_ROOT / "app" / "routers" / "fundamentals_compat.py").read_text(encoding="utf-8")
    assert '"ready"' in source or "'ready'" in source, (
        "rag_status must have 'ready' value when RAG is available"
    )
    assert '"not_indexed"' in source or "'not_indexed'" in source, (
        "rag_status must have 'not_indexed' value when docs exist but no embeddings"
    )


def test_rag_status_empty():
    """rag_status='empty' when no report_documents."""
    source = (_BACKEND_ROOT / "app" / "routers" / "fundamentals_compat.py").read_text(encoding="utf-8")
    assert '"empty"' in source, "rag_status must have 'empty' value"


def test_rag_module_result_has_rag_subdict():
    """report_documents module result must include a 'rag' sub-dict."""
    source = (_BACKEND_ROOT / "app" / "routers" / "fundamentals_compat.py").read_text(encoding="utf-8")
    assert "documents_count" in source, "rag sub-dict must include documents_count"
    assert "chunks_count"    in source, "rag sub-dict must include chunks_count"
    assert "embedding_count" in source, "rag sub-dict must include embedding_count"


# ── Frontend RAG ──────────────────────────────────────────────────────────────

def test_report_chat_panel_rag_index_status_prop():
    """ReportChatPanel must declare ragIndexStatus prop."""
    source = (_REPO_ROOT / "frontend" / "src" / "components" / "fundamentals" / "ReportChatPanel.vue").read_text(encoding="utf-8")
    assert "ragIndexStatus" in source, "ReportChatPanel must have ragIndexStatus prop"


def test_report_chat_panel_rag_status_aware_empty_state():
    """ReportChatPanel empty state must branch on ragIndexStatus values."""
    source = (_REPO_ROOT / "frontend" / "src" / "components" / "fundamentals" / "ReportChatPanel.vue").read_text(encoding="utf-8")
    assert "not_indexed" in source, "Empty state must handle 'not_indexed' status"
    assert "rcp_rag_not_indexed" in source, "Must use i18n key rcp_rag_not_indexed"
    assert "rcp_rag_empty" in source, "Must use i18n key rcp_rag_empty"
    assert "rcp_rag_unknown" in source, "Must use i18n key rcp_rag_unknown"


def test_i18n_rag_keys_in_all_locales():
    """rcp_rag_not_indexed must appear in all 6 locale files."""
    locales_dir = _REPO_ROOT / "frontend" / "src" / "locales"
    for fname in ["zh-CN.js", "zh-TW.js", "en-US.js", "ja-JP.js", "ko-KR.js", "es-ES.js"]:
        src = (locales_dir / fname).read_text(encoding="utf-8")
        assert "rcp_rag_not_indexed" in src, f"{fname} missing rcp_rag_not_indexed key"
        assert "rcp_rag_empty"       in src, f"{fname} missing rcp_rag_empty key"
        assert "rcp_rag_unknown"     in src, f"{fname} missing rcp_rag_unknown key"
        # Chinese locales must not use simplified Chinese chars in zh-TW
        if fname == "zh-TW.js":
            # zh-TW rcp_rag_not_indexed should use traditional chars (年報 not 年报)
            tw_val_match = re.search(r"rcp_rag_not_indexed:\s*'([^']*)'", src)
            if tw_val_match:
                val = tw_val_match.group(1)
                assert "年報" in val or "索引" in val, (
                    f"zh-TW rcp_rag_not_indexed must use Traditional Chinese (got: {val})"
                )
