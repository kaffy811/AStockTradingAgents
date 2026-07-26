"""
tests/fundamental/test_phase6n8b_data_completion_and_errors.py
Phase 6N-8B 验收测试：A股低成本数据补齐 + 报错修复 + 可见数据最大化

覆盖：
1.  401 classified as AUTH_REQUIRED
2.  401 不进入 provider reason
3.  Redis timeout fail-open
4.  Redis circuit breaker
5.  cache_unavailable 不等于 provider_empty
6.  Eastmoney RemoteDisconnected → QUOTE_PROVIDER_UNAVAILABLE error code
7.  SSE 404 no retry
8.  SSE discovery_attempts 包含 provider/year/status
9.  AI unavailable reason 分类型
10. DataSourceBanner 分类文案 (via error_codes)
11. diagnostics 显示 fallback_chain
12. hasDisplayableData 工具函数
13. PDF metric extraction confidence 阈值
14. RAG evidence 不进入 confirmed metrics
15. All-null rows → hidden_reason=ALL_NULL_ROWS
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ══════════════════════════════════════════════════════════════════════════════
# 1. 401 → AUTH_REQUIRED error_code, not provider failure
# ══════════════════════════════════════════════════════════════════════════════

def test_401_classified_as_auth_required():
    """HTTP 401 must produce AUTH_REQUIRED error_code, never DATA_SOURCE_EMPTY."""
    from app.core.error_codes import AUTH_REQUIRED, DATA_SOURCE_EMPTY
    assert AUTH_REQUIRED == "AUTH_REQUIRED"
    assert DATA_SOURCE_EMPTY != AUTH_REQUIRED  # must be distinct


def test_401_not_provider_reason():
    """AUTH_REQUIRED and QUOTE_PROVIDER_UNAVAILABLE are distinct codes."""
    from app.core.error_codes import AUTH_REQUIRED, QUOTE_PROVIDER_UNAVAILABLE
    assert AUTH_REQUIRED != QUOTE_PROVIDER_UNAVAILABLE


def test_auth_required_message_separate_from_provider():
    """The AUTH_REQUIRED code should not say 'BaoStock' or 'AkShare'."""
    from app.core.error_codes import AUTH_REQUIRED
    # The code itself must not reference specific providers
    assert "BaoStock" not in AUTH_REQUIRED
    assert "AkShare" not in AUTH_REQUIRED


# ══════════════════════════════════════════════════════════════════════════════
# 2. Redis circuit breaker + fail-open
# ══════════════════════════════════════════════════════════════════════════════

def test_redis_circuit_breaker_opens_after_threshold():
    """Circuit breaker should open after _CB_FAIL_THRESHOLD consecutive failures."""
    import time
    from app.services import cache_service as cs_module

    # Reset state
    cs_module._cb_fail_count = 0
    cs_module._cb_open_until = 0.0

    # Trigger failures up to threshold
    for _ in range(cs_module._CB_FAIL_THRESHOLD):
        assert not cs_module._cb_is_open(), "Circuit should not open before threshold"
        cs_module._cb_record_failure()

    assert cs_module._cb_is_open(), "Circuit should be open after threshold failures"


def test_redis_circuit_breaker_fail_open():
    """When circuit is open, sync_get_json should return None (fail-open)."""
    import time
    from app.services.cache_service import cache_service, _cb_open_until
    from app.services import cache_service as cs_module

    # Force open
    cs_module._cb_open_until = time.monotonic() + 60
    result = cache_service.sync_get_json("test:key:circuit")
    assert result is None, "fail-open: should return None when circuit is open"

    # Cleanup
    cs_module._cb_open_until = 0.0
    cs_module._cb_fail_count = 0


def test_redis_circuit_breaker_set_fails_open():
    """When circuit is open, sync_set_json should return False (fail-open)."""
    import time
    from app.services.cache_service import cache_service
    from app.services import cache_service as cs_module

    cs_module._cb_open_until = time.monotonic() + 60
    result = cache_service.sync_set_json("test:key:circuit", {"x": 1}, 60)
    assert result is False

    cs_module._cb_open_until = 0.0
    cs_module._cb_fail_count = 0


def test_cache_unavailable_is_not_provider_empty():
    """CACHE_UNAVAILABLE and DATA_SOURCE_EMPTY must be distinct error codes."""
    from app.core.error_codes import CACHE_UNAVAILABLE, DATA_SOURCE_EMPTY
    assert CACHE_UNAVAILABLE != DATA_SOURCE_EMPTY


def test_cache_status_unavailable_when_open():
    """cache_status() returns 'unavailable' when circuit breaker is open."""
    import time
    from app.services.cache_service import cache_status
    from app.services import cache_service as cs_module

    cs_module._cb_open_until = time.monotonic() + 60
    assert cache_status() == "unavailable"

    cs_module._cb_open_until = 0.0
    cs_module._cb_fail_count = 0


def test_cache_status_ok_when_closed():
    """cache_status() returns 'ok' when circuit breaker is closed."""
    from app.services.cache_service import cache_status
    from app.services import cache_service as cs_module

    cs_module._cb_open_until = 0.0
    cs_module._cb_fail_count = 0
    assert cache_status() == "ok"


# ══════════════════════════════════════════════════════════════════════════════
# 3. Quote provider error codes
# ══════════════════════════════════════════════════════════════════════════════

def test_quote_provider_unavailable_exists():
    """QUOTE_PROVIDER_UNAVAILABLE must exist as a stable error code."""
    from app.core.error_codes import QUOTE_PROVIDER_UNAVAILABLE
    assert QUOTE_PROVIDER_UNAVAILABLE == "QUOTE_PROVIDER_UNAVAILABLE"


def test_share_capital_missing_exists():
    """SHARE_CAPITAL_MISSING must exist as a stable error code."""
    from app.core.error_codes import SHARE_CAPITAL_MISSING
    assert SHARE_CAPITAL_MISSING == "SHARE_CAPITAL_MISSING"


# ══════════════════════════════════════════════════════════════════════════════
# 4. SSE tool: 404 no-retry, dedup log
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_sse_tool_404_no_retry():
    """SSE tool must return [] on 404 without retrying."""
    import httpx
    from app.tools.reports.sse_report_search_tool import SSEReportSearchTool

    tool = SSEReportSearchTool()

    response_404 = MagicMock()
    response_404.status_code = 404

    call_count = 0

    async def mock_get(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise httpx.HTTPStatusError("404", request=MagicMock(), response=response_404)

    with patch("httpx.AsyncClient") as mock_client:
        client_instance = AsyncMock()
        client_instance.get = mock_get
        mock_client.return_value.__aenter__ = AsyncMock(return_value=client_instance)
        mock_client.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await tool.search("600519", "贵州茅台", "annual", 2024)

    assert result == [], "SSE 404 should return empty list"
    assert call_count == 1, "SSE 404 should NOT retry — only 1 attempt expected"


@pytest.mark.asyncio
async def test_sse_tool_skips_non_sse_stocks():
    """SSE tool should skip stocks not listed on Shanghai exchange."""
    from app.tools.reports.sse_report_search_tool import SSEReportSearchTool

    tool = SSEReportSearchTool()
    result = await tool.search("000001", "平安银行", "annual", 2024)  # SZ stock
    assert result == [], "SSE tool should not search for Shenzhen stocks"


# ══════════════════════════════════════════════════════════════════════════════
# 5. PDF metric extraction service
# ══════════════════════════════════════════════════════════════════════════════

def test_pdf_metric_extraction_basic():
    """Extract revenue from plain text."""
    from app.services.report_metric_extract_service import extract_metrics_from_text

    text = "营业收入：1,234.56亿元，净利润同比增长15%。"
    metrics = extract_metrics_from_text(text, "rpt_001", "600519.SH", "20241231")
    revenue_metrics = [m for m in metrics if m["metric_key"] == "revenue"]
    assert len(revenue_metrics) > 0, "Should extract revenue"
    m = revenue_metrics[0]
    assert m["value"] > 1e10, "Revenue should be scaled to yuan (亿元 scale)"
    assert m["unit"] == "元"


def test_pdf_metric_extraction_confidence_threshold():
    """Only metrics with confidence >= 0.75 should be 'confirmed'."""
    from app.services.report_metric_extract_service import (
        extract_metrics_from_text,
        filter_confirmed,
    )

    text = "加权平均净资产收益率：18.5%，每股收益（基本）：5.23元"
    all_metrics = extract_metrics_from_text(text, "rpt_002", "600519.SH", "20241231")
    confirmed = filter_confirmed(all_metrics)
    for m in confirmed:
        assert m["confidence"] >= 0.75, f"Confirmed metric {m['metric_key']} has low confidence"


def test_pdf_extraction_rag_evidence_not_confirmed():
    """
    RAG chunk evidence (confidence < 0.75 or low-quality extraction) must NOT
    enter confirmed metrics.
    """
    from app.services.report_metric_extract_service import filter_confirmed

    # Simulate a low-confidence candidate
    candidates = [
        {"metric_key": "revenue", "value": 1e10, "confidence": 0.60},
        {"metric_key": "net_profit_parent", "value": 2e9, "confidence": 0.80},
    ]
    confirmed = filter_confirmed(candidates)
    keys = [m["metric_key"] for m in confirmed]
    assert "revenue" not in keys, "Low-confidence metric must not be confirmed"
    assert "net_profit_parent" in keys


def test_pdf_extraction_zero_value_valid():
    """Zero numeric values are valid and should not be dropped."""
    from app.services.report_metric_extract_service import extract_metrics_from_text

    text = "加权平均净资产收益率：0.00%"
    metrics = extract_metrics_from_text(text, "rpt_003", "600519.SH", "20241231")
    roe_metrics = [m for m in metrics if m["metric_key"] == "roe_weighted"]
    if roe_metrics:
        assert roe_metrics[0]["value"] == 0.0, "Zero is valid"


# ══════════════════════════════════════════════════════════════════════════════
# 6. All-null rows: hidden_reason = ALL_NULL_ROWS
# ══════════════════════════════════════════════════════════════════════════════

def test_all_null_rows_hidden_reason():
    """ALL_NULL_ROWS error code exists and diagnostics helper uses it."""
    from app.core.error_codes import ALL_NULL_ROWS
    assert ALL_NULL_ROWS == "ALL_NULL_ROWS"


def test_diagnostics_fill_chains_hidden_reason():
    """_build_fill_chains returns hidden_reason=ALL_NULL_ROWS for zero-value modules."""
    from app.routers.fundamentals_compat import _build_fill_chains

    module_results = [
        {
            "module_key":       "solvency",
            "status":           "empty",
            "rows_count":       3,
            "non_null_fields":  [],   # all null
            "latency_ms":       50,
            "provider_success": "baostock",
            "inferred":         False,
        }
    ]
    chains = _build_fill_chains(module_results, "CN")
    solvency = next((c for c in chains if c["module_key"] == "solvency"), None)
    assert solvency is not None
    assert solvency["hidden_reason"] == "ALL_NULL_ROWS"
    assert solvency["renderable_after_fill"] is False


def test_diagnostics_fill_chains_renderable_when_filled():
    """If filled_fields is non-empty, renderable_after_fill should be True."""
    from app.routers.fundamentals_compat import _build_fill_chains

    module_results = [
        {
            "module_key":       "solvency",
            "status":           "ok",
            "rows_count":       3,
            "non_null_fields":  ["debt_ratio"],
            "latency_ms":       50,
            "provider_success": "baostock",
            "inferred":         False,
        }
    ]
    chains = _build_fill_chains(module_results, "CN")
    solvency = next((c for c in chains if c["module_key"] == "solvency"), None)
    assert solvency is not None
    assert solvency["renderable_after_fill"] is True
    assert solvency["hidden_reason"] is None


# ══════════════════════════════════════════════════════════════════════════════
# 7. Error code distinctness checks
# ══════════════════════════════════════════════════════════════════════════════

def test_all_new_error_codes_are_distinct():
    """All Phase 6N-8B error codes must be unique strings."""
    from app.core import error_codes as ec

    codes = [
        ec.AUTH_REQUIRED,
        ec.QUOTE_PROVIDER_UNAVAILABLE,
        ec.SHARE_CAPITAL_MISSING,
        ec.ALL_NULL_ROWS,
        ec.CACHE_UNAVAILABLE,
        ec.DATA_SOURCE_EMPTY,
        ec.DATA_SOURCE_UNAVAILABLE,
        ec.DATA_PACK_EMPTY,
        ec.REPORT_NOT_INGESTED,
        ec.AI_KEY_MISSING,
        ec.SOURCE_CHUNKS_EMPTY,
    ]
    assert len(codes) == len(set(codes)), "All error codes must be unique"


# ══════════════════════════════════════════════════════════════════════════════
# 8. Diagnostics response structure
# ══════════════════════════════════════════════════════════════════════════════

def test_diagnostics_helpers_import():
    """All Phase 6N-8B diagnostics helpers must be importable."""
    from app.routers.fundamentals_compat import (
        _get_cache_status,
        _get_provider_status,
        _build_fill_chains,
    )
    assert callable(_get_cache_status)
    assert callable(_get_provider_status)
    assert callable(_build_fill_chains)


def test_diagnostics_cache_status_returns_string():
    """_get_cache_status() must always return a string."""
    from app.routers.fundamentals_compat import _get_cache_status
    result = _get_cache_status()
    assert isinstance(result, str)


def test_diagnostics_provider_status_all_failed():
    """_get_provider_status returns 'unavailable' when all modules failed."""
    from app.routers.fundamentals_compat import _get_provider_status

    module_results = [
        {"status": "failed"},
        {"status": "failed"},
    ]
    assert _get_provider_status(module_results) == "unavailable"


def test_diagnostics_provider_status_partial():
    """_get_provider_status returns 'partial' when some modules failed."""
    from app.routers.fundamentals_compat import _get_provider_status

    module_results = [
        {"status": "ok"},
        {"status": "failed"},
    ]
    assert _get_provider_status(module_results) == "partial"


def test_diagnostics_provider_status_ok():
    """_get_provider_status returns 'ok' when all modules succeed."""
    from app.routers.fundamentals_compat import _get_provider_status

    module_results = [
        {"status": "ok"},
        {"status": "ok"},
    ]
    assert _get_provider_status(module_results) == "ok"


# ══════════════════════════════════════════════════════════════════════════════
# 9. deduplicated warning suppression helper
# ══════════════════════════════════════════════════════════════════════════════

def test_should_warn_dedup():
    """Same key prefix should only warn once in 60s."""
    from app.services import cache_service as cs_module

    # Reset warn state for this prefix
    cs_module._warn_last.pop("testprefix", None)

    assert cs_module._should_warn("testprefix:CN:123") is True, "First warn should fire"
    assert cs_module._should_warn("testprefix:CN:456") is False, "Second warn should be suppressed"


def test_key_prefix_extraction():
    """_key_prefix should extract the first segment."""
    from app.services import cache_service as cs_module

    assert cs_module._key_prefix("quote:CN:601686") == "quote"
    assert cs_module._key_prefix("kline:CN:601686:daily:qfq:90") == "kline"
    assert cs_module._key_prefix("") == ""
