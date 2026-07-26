from __future__ import annotations

import importlib
import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest


def test_baostock_is_runtime_dependency_and_importable():
    module = importlib.import_module("baostock")
    assert module is not None


@pytest.mark.asyncio
async def test_baostock_import_failure_returns_provider_unavailable(monkeypatch):
    from app.datasource import baostock_client as bc

    monkeypatch.setattr(bc.importlib.util, "find_spec", lambda name: None if name == "baostock" else object())
    result = await bc.baostock_client.get_financial_history_bulk(
        "600519.SH",
        start_year=2024,
        end_year=2024,
        mode="annual",
    )
    stats = result["_bulk_stats"]
    assert stats["status"] == "unavailable"
    assert stats["reason_code"] == "PROVIDER_UNAVAILABLE"
    assert all(result[key] == [] for key in ("profit", "growth", "balance", "operation", "cash_flow", "dupont"))


def test_annual_history_keeps_multiple_years_and_marks_metadata():
    from app.datasource.history_financial_provider import _build_module_history_from_rows

    raw_rows = [
        {"stat_date": "2022-12-31", "roe_avg": "10", "gpMargin": "80", "npMargin": "40"},
        {"stat_date": "2023-12-31", "roe_avg": "11", "gpMargin": "81", "npMargin": "41"},
        {"stat_date": "2024-12-31", "roe_avg": "12", "gpMargin": "82", "npMargin": "42"},
        {"stat_date": "2024-09-30", "roe_avg": "9", "gpMargin": "79", "npMargin": "39"},
        {"stat_date": "2024-12-31", "roe_avg": "12", "gpMargin": "82", "npMargin": "42"},
    ]
    result = _build_module_history_from_rows(
        "profitability",
        raw_rows,
        ts_code="600519.SH",
        start_year=2022,
        end_year=2024,
        period="annual",
        data_success=True,
        provider_status="success",
    )
    periods = [row["period"] for row in result["history"]]
    assert periods == ["2022-12-31", "2023-12-31", "2024-12-31"]
    assert [row["report_year"] for row in result["history"]] == [2022, 2023, 2024]
    assert {row["report_period_type"] for row in result["history"]} == {"annual"}
    assert result["history_coverage"]["insufficient_history"] is False


def test_single_annual_point_is_insufficient_history():
    from app.datasource.history_financial_provider import _build_module_history_from_rows

    result = _build_module_history_from_rows(
        "profitability",
        [{"stat_date": "2024-12-31", "roe_avg": "12"}],
        ts_code="600519.SH",
        start_year=2022,
        end_year=2024,
        period="annual",
        data_success=True,
        provider_status="partial",
    )
    assert result["period_type"] == "point_in_time"
    assert result["history_coverage"]["insufficient_history"] is True


def test_cninfo_metadata_extracts_official_source_and_pdf_url():
    from app.datasource.cninfo_provider import extract_report_metadata, validate_pdf_url

    report = extract_report_metadata(
        {
            "secCode": "600519",
            "secName": "贵州茅台",
            "announcementTitle": "贵州茅台2024年年度报告",
            "announcementTime": 1745942400000,
            "announcementId": "1219999999",
            "orgId": "gssh0600519",
            "adjunctUrl": "finalpage/2025-04-30/1219999999.PDF",
            "adjunctType": "PDF",
        },
        "600519",
        2024,
    )
    assert report["source_url"].startswith("http://www.cninfo.com.cn/new/disclosure/detail")
    assert report["pdf_url"].startswith("https://static.cninfo.com.cn/")
    assert validate_pdf_url(report["pdf_url"])[0] is True
    assert report["report_type"] == "annual"


def test_cninfo_canonical_request_contract_and_mappings():
    from app.datasource.cninfo_provider import (
        categories_for_report_type,
        cninfo_request_contract,
        normalize_report_type,
        period_from_type_year,
    )

    assert normalize_report_type("semi") == "semi_annual"
    assert normalize_report_type("annual_report") == "annual"
    assert normalize_report_type("q1_report") == "q1"
    assert normalize_report_type("q3_report") == "q3"
    assert period_from_type_year("semi", 2024) == "20240630"
    assert period_from_type_year("q1", 2024) == "20240331"
    assert period_from_type_year("q3", 2024) == "20240930"
    assert categories_for_report_type("annual") == ["category_ndbg_szsh", "category_ndbg_sse"]
    assert categories_for_report_type("semi") == ["category_bndbg_szsh", "category_bndbg_sse"]
    assert "category_yjdbg_szsh" in categories_for_report_type("q1")
    assert "category_sjdbg_szsh" in categories_for_report_type("q3")

    sse = cninfo_request_contract("600519", "annual")
    szse = cninfo_request_contract("300750", "annual")
    assert sse["column"] == "sse"
    assert szse["column"] == "szse"
    assert sse["query_endpoint_scheme"] == "http"
    assert "CNINFO" in sse["query_endpoint_scheme_reason"]
    assert "HTTPS" in sse["query_endpoint_scheme_reason"]


def test_cninfo_pdf_url_validation_is_https_whitelist_only():
    from app.datasource.cninfo_provider import validate_pdf_url

    assert validate_pdf_url("https://static.cninfo.com.cn/finalpage/2025-04-30/1.PDF")[0] is True
    assert validate_pdf_url("http://static.cninfo.com.cn/finalpage/2025-04-30/1.PDF")[0] is False
    assert validate_pdf_url("https://example.com/finalpage/2025-04-30/1.PDF")[0] is False
    assert validate_pdf_url("https://static.cninfo.com.cn/finalpage/2025-04-30/1.txt")[0] is False


@pytest.mark.asyncio
async def test_cninfo_legacy_tool_reuses_canonical_provider(monkeypatch):
    from app.tools.reports.cninfo_report_search_tool import CninfoReportSearchTool
    from app.tools.reports import cninfo_report_search_tool as tool_mod

    async def fake_search(*args, **kwargs):
        return {
            "announcements": [
                {
                    "secCode": "600519",
                    "secName": "贵州茅台",
                    "announcementTitle": "贵州茅台2024年年度报告",
                    "announcementTime": 1745942400000,
                    "announcementId": "1219999999",
                    "orgId": "gssh0600519",
                    "adjunctUrl": "finalpage/2025-04-30/1219999999.PDF",
                    "adjunctType": "PDF",
                }
            ],
            "diagnostics": {"status": "success"},
        }

    monkeypatch.setattr(tool_mod, "search_announcements_with_diagnostics", fake_search)
    rows = await CninfoReportSearchTool().search("600519", "贵州茅台", "annual", 2024)
    assert rows
    assert rows[0]["pdf_url"].startswith("https://static.cninfo.com.cn/")
    assert rows[0]["source_url"].startswith("http://www.cninfo.com.cn/new/disclosure/detail")
    assert rows[0]["canonical_report_type"] == "annual"


@pytest.mark.asyncio
async def test_report_document_upsert_accepts_company_v2_candidate_and_persists_source_url():
    from app.services.report_document_service import ReportDocumentService

    candidate = {
        "symbol": "600519",
        "report_type": "annual",
        "period_end": "2024-12-31",
        "title": "贵州茅台2024年年度报告",
        "source": "cninfo",
        "source_url": "http://www.cninfo.com.cn/new/disclosure/detail?announcementId=1&orgId=x",
        "pdf_url": "https://static.cninfo.com.cn/finalpage/2025-04-30/1.PDF",
        "announcement_date": "2025-04-30",
        "report_year": 2024,
        "confidence": 0.95,
    }
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    inserted = {}

    def _add(doc):
        doc.id = 7
        inserted["doc"] = doc

    mock_db.add = MagicMock(side_effect=_add)
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    result = await ReportDocumentService().upsert_discovered_report(candidate, mock_db)
    assert result["status"] == "inserted"
    assert inserted["doc"].ts_code == "600519.SH"
    assert inserted["doc"].source_url.startswith("http://www.cninfo.com.cn/new/disclosure/detail")
    assert inserted["doc"].pdf_url.startswith("https://static.cninfo.com.cn/")


@pytest.mark.asyncio
async def test_report_rag_service_bridges_to_company_v2_when_legacy_chunks_empty(monkeypatch):
    from app.services.report_rag_service import ReportRagService
    from app.services import company_v2_report_rag_retriever as retriever_module

    async def _empty_vector(*args, **kwargs):
        return []

    async def _empty_keyword(*args, **kwargs):
        return []

    def _retrieve(**kwargs):
        return {
            "chunks": [
                {
                    "chunk_id": 101,
                    "report_id": kwargs["report_id"],
                    "report_type": "annual",
                    "report_year": 2024,
                    "section_title": "主要会计数据",
                    "text_excerpt": "营业收入和净利润字段来自财报片段。",
                    "score": 0.88,
                    "score_detail": {"embedding_score": 0.8, "keyword_score": 0.7},
                    "source_url": "https://static.cninfo.com.cn/finalpage/2025-04-30/1.PDF",
                }
            ],
            "retrieval_mode": "hybrid",
        }

    svc = ReportRagService()
    monkeypatch.setattr(svc, "_vector_search", _empty_vector)
    monkeypatch.setattr(svc, "_keyword_search", _empty_keyword)
    monkeypatch.setattr(retriever_module.company_v2_report_rag_retriever, "retrieve", _retrieve)

    result = await svc.query("600519.SH", "贵州茅台最新财报表现如何？", MagicMock(), report_id=7)
    assert result["provider"] == "company_v2_report_rag"
    assert result["chunks"][0]["report_id"] == 7
    assert "营业收入" in result["chunks"][0]["content"]


def test_financial_report_question_routes_to_report_skill_not_gfa():
    from app.agents.chat_skills.base import SkillContext
    from app.agents.chat_skills.general_financial_answer_skill import GeneralFinancialAnswerSkill
    from app.agents.chat_skills.report_explanation_skill import ReportExplanationSkill

    ctx = SkillContext(user_id="u", session_id="s", db=None)
    message = "贵州茅台最新财报表现如何？"
    assert ReportExplanationSkill().can_handle(message, ctx) is True
    assert GeneralFinancialAnswerSkill().can_handle(message, ctx) is False


@pytest.mark.asyncio
async def test_report_chat_preserves_rag_chunks_when_llm_unavailable(monkeypatch):
    from app.agent.report_chat_copilot_agent import ReportChatCopilotAgent
    from app.core.config import settings
    from app.models.report_document import ReportDocument
    from app.services.report_rag_service import ReportRagService

    doc = ReportDocument(
        id=7,
        ts_code="600519.SH",
        report_type="annual",
        report_year=2025,
        period_end="2025-12-31",
        title="贵州茅台2025年年度报告",
        disclosure_date="2026-04-16",
    )
    result = MagicMock()
    result.scalars.return_value.first.return_value = doc
    fake_db = AsyncMock()
    fake_db.execute = AsyncMock(return_value=result)

    async def fake_query(*args, **kwargs):
        return {
            "chunks": [
                {
                    "chunk_id": 1,
                    "report_id": 7,
                    "report_type": "annual",
                    "report_year": 2025,
                    "period": "2025",
                    "section_title": "主要会计数据",
                    "content": "营业收入来自财报片段。",
                    "score": 0.9,
                }
            ],
            "partial": False,
            "errors": [],
            "provider": "company_v2_report_rag",
            "search_mode": "hybrid",
            "fallback_used": False,
        }

    monkeypatch.setattr(ReportRagService, "query", fake_query)
    monkeypatch.setattr(settings, "ai_enabled", False, raising=False)
    response = await ReportChatCopilotAgent().chat(
        market="CN",
        symbol="600519",
        question="贵州茅台最新财报表现如何？",
        db=fake_db,
        stock_name="贵州茅台",
        force_refresh=True,
    )
    assert response["rag_status"] == "local"
    assert len(response["source_chunks"]) == 1
    assert response["source_chunks"][0]["report_id"] == 7


def test_demo_readiness_script_is_allowlist_only_and_sanitized():
    import scripts.phase6u_demo_data_readiness as script

    assert script.ALLOWLIST == {"600519", "300750", "000725", "000001", "601686"}
    source = inspect.getsource(script)
    assert '"local_path":' not in source
    assert "symbols outside allowlist are not permitted" in source
    assert "secret" in source.lower()
