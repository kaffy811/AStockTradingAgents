from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_report_documents_zero_count_is_not_ok(monkeypatch):
    from app.services.company_v2_debug_service import company_v2_debug_service

    async def fake_discover(*args, **kwargs):
        return []

    monkeypatch.setattr(company_v2_debug_service, "discover_reports", fake_discover)
    env = await company_v2_debug_service.build_module(
        "CN",
        "600519",
        "report_documents",
        include_raw=False,
        providers=["pdf"],
        force_refresh=True,
        max_raw_chars=1000,
        db=None,
    )

    assert env.ok is False
    assert env.render.has_displayable_data is False
    assert env.render.reason == "REPORT_PDF_NOT_FOUND"
    assert env.diagnosis["primary_issue"] == "REPORT_PDF_NOT_FOUND"
    assert "documents_count" not in env.completion.filled_fields
    assert env.normalized.rows[0]["documents_count"] == 0


@pytest.mark.asyncio
async def test_report_rag_zero_chunks_distinguishes_pdf_missing_and_not_ingested(monkeypatch):
    from app.services.company_v2_debug_service import company_v2_debug_service

    async def fake_discover(*args, **kwargs):
        return []

    class ScalarResult:
        def __init__(self, value):
            self.value = value

        def scalar(self):
            return self.value

    class FakeDb:
        def __init__(self, values):
            self.values = list(values)

        async def execute(self, *args, **kwargs):
            return ScalarResult(self.values.pop(0))

    monkeypatch.setattr(company_v2_debug_service, "discover_reports", fake_discover)

    missing_pdf = await company_v2_debug_service.build_module(
        "CN", "600519", "report_rag",
        include_raw=False, providers=["pdf"], force_refresh=True, max_raw_chars=1000, db=None,
    )
    assert missing_pdf.ok is False
    assert missing_pdf.diagnosis["primary_issue"] == "REPORT_PDF_NOT_FOUND"

    not_ingested = await company_v2_debug_service.build_module(
        "CN", "600519", "report_rag",
        include_raw=False,
        providers=["pdf"],
        force_refresh=True,
        max_raw_chars=1000,
        db=FakeDb([1, 0, 0]),
    )
    assert not_ingested.ok is False
    assert not_ingested.render.reason == "REPORT_NOT_INGESTED"
    assert not_ingested.diagnosis["primary_issue"] == "REPORT_NOT_INGESTED"
    assert "chunks_count" not in not_ingested.completion.filled_fields
    assert "embedding_count" not in not_ingested.completion.filled_fields


@pytest.mark.asyncio
async def test_ai_status_structured_summary_separates_rag_unavailable():
    from app.services.company_v2_debug_service import company_v2_debug_service

    env = await company_v2_debug_service.build_module(
        "CN",
        "600519",
        "ai_analysis_status",
        include_raw=False,
        providers=["baostock"],
        force_refresh=True,
        max_raw_chars=1000,
        db=None,
    )

    row = env.normalized.rows[0]
    assert row["structured_summary_available"] is True
    assert row["rag_available"] is False
    assert "结构化财务数据摘要可用；年报 RAG 尚未接入。" in row["summary"]


@pytest.mark.asyncio
async def test_baostock_kline_fallback_price_label(monkeypatch):
    import app.services.company_v2_debug_service as service_module
    from app.services.company_v2_debug_service import company_v2_debug_service

    async def fake_runner(*args, **kwargs):
        return {
            "provider": "baostock",
            "endpoint": "query_history_k_data_plus",
            "attempted": True,
            "success": True,
            "status": "success",
            "rows_count": 1,
            "raw_sample": [{
                "date": "2026-07-08",
                "close": 1199.3,
                "pe_ttm": 20.1,
                "pb": 8.2,
            }],
        }

    monkeypatch.setattr(service_module, "run_provider_with_debug", fake_runner)
    env = await company_v2_debug_service.build_module(
        "CN", "600519", "quote_overview",
        include_raw=False, providers=["baostock"], force_refresh=True, max_raw_chars=1000, db=None,
    )

    row = env.normalized.rows[0]
    assert row["latest_price"] == 1199.3
    assert row["price_is_realtime"] is False
    assert row["price_label"] == "最近收盘价"
    assert row["price_as_of"] == "2026-07-08"
    assert row["latest_price_source"] == "baostock_kline_fallback"


@pytest.mark.asyncio
async def test_realtime_price_label(monkeypatch):
    import app.services.company_v2_debug_service as service_module
    from app.services.company_v2_debug_service import company_v2_debug_service

    async def fake_runner(*args, **kwargs):
        return {
            "provider": "akshare",
            "endpoint": "stock_zh_a_spot_em",
            "attempted": True,
            "success": True,
            "status": "success",
            "rows_count": 1,
            "raw_sample": [{
                "trade_date": "2026-07-09",
                "latest_price": 1201.5,
                "pe": 20.2,
                "pb": 8.3,
            }],
        }

    monkeypatch.setattr(service_module, "run_provider_with_debug", fake_runner)
    env = await company_v2_debug_service.build_module(
        "CN", "600519", "quote_overview",
        include_raw=False, providers=["akshare"], force_refresh=True, max_raw_chars=1000, db=None,
    )

    row = env.normalized.rows[0]
    assert row["price_is_realtime"] is True
    assert row["price_label"] == "最新价"
    assert row["price_as_of"] == "2026-07-09"
    assert row["latest_price_source"] == "akshare_spot_em"


@pytest.mark.asyncio
async def test_financial_display_metadata_preserves_raw_values(monkeypatch):
    from app.services.company_v2_debug_service import company_v2_debug_service

    async def fake_financial(env, providers, include_raw, max_raw_chars, *, context=None):
        env.normalized.rows = [{
            "roe": 0.1234,
            "gross_margin": 0,
            "current_ratio": 1.456,
            "quick_ratio": None,
            "roe_source": "unit",
            "gross_margin_source": "unit",
            "current_ratio_source": "unit",
        }]
        env.normalized.metrics = env.normalized.rows[0]

    monkeypatch.setattr(company_v2_debug_service, "_build_financial", fake_financial)
    env = await company_v2_debug_service.build_module(
        "CN", "600519", "profitability",
        include_raw=False, providers=["baostock"], force_refresh=True, max_raw_chars=1000, db=None,
    )

    assert env.normalized.fields["roe"]["value"] == 0.1234
    assert env.normalized.fields["roe"]["raw_value"] == 0.1234
    assert env.normalized.fields["roe"]["display_value"] == "12.34%"
    assert env.normalized.fields["gross_margin"]["value"] == 0
    assert env.normalized.fields["gross_margin"]["display_value"] == "0.00%"
    assert env.completion.still_missing_fields["roa"] == "FIELD_MISSING"


def test_frontend_staged_default_and_no_advice_or_legacy_message():
    root = Path(__file__).resolve().parents[3]
    stock_detail = (root / "frontend/src/views/StockDetailView.vue").read_text()
    company_v2_files = [
        root / "frontend/src/views/CompanyV2View.vue",
        root / "frontend/src/components/company-v2/CompanyV2DebugPanel.vue",
        root / "frontend/src/components/company-v2/CompanyV2Section.vue",
        root / "frontend/src/components/company-v2/CompanyV2MetricCards.vue",
        root / "frontend/src/components/company-v2/CompanyV2FallbackTable.vue",
    ]
    source = "\n".join(path.read_text() for path in company_v2_files)

    assert "import.meta.env.PROD ? 'legacy' : 'v2'" in stock_detail
    assert "companyV2Query.value !== '0'" in stock_detail
    assert "CompanyFundamentalsPanel" in stock_detail
    assert "DATA_MODE=free：BaoStock 和 AkShare 均未返回数据" not in source
    assert "target_price" not in source
    assert "analyst_rating" not in source
    for phrase in ("建议买入", "建议卖出", "目标价", "保证上涨"):
        assert phrase not in source
