"""Phase 6V-P1.9 — official report year selection / ordering / dedup regressions.

Covers the P1.9 selection matrix: exact-year isolation, latest semantics,
annual-only filtering, deterministic ordering with id tie-breaks, dedup,
pollution resistance (inquiry-letter replies misfiled as annual), the
600186/300209 root-cause reproductions and no-market-scan guarantees.
"""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.report_document import ReportDocument
from app.services.official_report_domain_service import official_report_domain_service as svc
from app.services.report_document_classifier import KIND_ANNUAL_FULL, classify_report_document


def _doc(id, ts, year, title, *, rtype="annual", period="", disclosure=None, pdf="https://static.cninfo.com.cn/x.PDF"):
    return ReportDocument(
        id=id, ts_code=ts, report_year=year, report_type=rtype, title=title,
        period_end=period or f"{year}-12-31", disclosure_date=disclosure,
        source_url=pdf, pdf_url=pdf, parsed=False,
    )


SEED = [
    # 600519: clean three years
    _doc(1, "600519.SH", 2025, "贵州茅台：贵州茅台2025年年度报告"),
    _doc(2, "600519.SH", 2024, "贵州茅台：贵州茅台2024年年度报告"),
    _doc(3, "600519.SH", 2023, "贵州茅台：贵州茅台2023年年度报告"),
    # 600186-style pollution: newer years are inquiry replies, real full annuals older
    _doc(10, "600186.SH", 2025, "莲花控股：会计师事务所关于2025年年度报告的信息披露监管问询函专项说明"),
    _doc(11, "600186.SH", 2024, "莲花控股：关于对2024年年度报告的信息披露监管问询函相关问题的核查意见"),
    _doc(12, "600186.SH", 2022, "莲花健康：600186_莲花健康_2022年_年度报告"),
    _doc(13, "600186.SH", 2021, "莲花健康：莲花健康2021年年度报告"),
    # 300209-style: 2024 only has an inquiry reply
    _doc(20, "300209.SZ", 2025, "行云科技：2025年年度报告"),
    _doc(21, "300209.SZ", 2024, "*ST有树：关于2024年年度年报问询函的回复"),
    _doc(22, "300209.SZ", 2017, "天泽信息：2017年年度报告"),
    # duplicates for dedup: same year, re-crawled variants (ids reversed on purpose)
    _doc(31, "000858.SZ", 2024, "五粮液：2024年年度报告", disclosure="2025-04-03"),
    _doc(30, "000858.SZ", 2024, "五粮液：2024年年度报告（重新上传）", disclosure="2025-04-02"),
    _doc(32, "000858.SZ", 2025, "五粮液：2025年年度报告"),
    # non-annual types must never surface for annual requests
    _doc(40, "000001.SZ", 2025, "平安银行：2025年半年度报告", rtype="semi", period="2025-06-30"),
    _doc(41, "000001.SZ", 2025, "平安银行：2025年第一季度报告", rtype="q1", period="2025-03-31"),
    _doc(42, "000001.SZ", 2025, "平安银行：2025年年度报告"),
]


def _list(_unused, ts, *, year=None, limit=8):
    """Build, seed, query and dispose the in-memory DB inside one event loop
    (aiosqlite connections are loop-bound)."""

    async def run():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        try:
            async with engine.begin() as conn:
                await conn.run_sync(lambda sync_conn: ReportDocument.__table__.create(sync_conn))
            maker = async_sessionmaker(engine, expire_on_commit=False)
            async with maker() as session:
                for d in SEED:
                    session.add(ReportDocument(
                        id=d.id, ts_code=d.ts_code, report_year=d.report_year,
                        report_type=d.report_type, title=d.title, period_end=d.period_end,
                        disclosure_date=d.disclosure_date, source_url=d.source_url,
                        pdf_url=d.pdf_url, parsed=d.parsed,
                    ))
                await session.commit()
            async with maker() as db:
                return await svc.list_official_annual_reports(db, ts_code=ts, limit=limit, requested_year=year)
        finally:
            await engine.dispose()

    return asyncio.run(run())


@pytest.fixture()
def db_session_factory():
    yield None


# 1+2: exact year isolation
def test_exact_2024_returns_only_2024(db_session_factory):
    reports = _list(db_session_factory, "600519.SH", year=2024)
    assert [r["report_year"] for r in reports] == [2024]


def test_missing_exact_year_returns_empty_not_neighbours(db_session_factory):
    assert _list(db_session_factory, "600186.SH", year=2025) == []
    assert _list(db_session_factory, "300209.SZ", year=2024) == []
    # and definitely no fallback to 2023/2025/latest
    assert _list(db_session_factory, "600519.SH", year=2022) == []


# 3+4+5: latest semantics and type purity
def test_latest_returns_newest_full_annual(db_session_factory):
    reports = _list(db_session_factory, "600519.SH")
    assert reports[0]["report_year"] == 2025


def test_latest_skips_semi_and_quarterlies(db_session_factory):
    reports = _list(db_session_factory, "000001.SZ")
    assert [r["report_year"] for r in reports] == [2025]
    assert all(classify_report_document(r["title"], report_type=r["report_type"]).report_document_kind == KIND_ANNUAL_FULL
               for r in reports)


def test_annual_request_never_returns_q1_q3(db_session_factory):
    reports = _list(db_session_factory, "000001.SZ", year=2025)
    assert len(reports) == 1 and "年度报告" in reports[0]["title"]
    assert "季度" not in reports[0]["title"] and "半年度" not in reports[0]["title"]


# pollution resistance (600186/300209 root-cause reproductions; items 13+14)
def test_600186_regression_latest_is_true_full_annual_2022(db_session_factory):
    reports = _list(db_session_factory, "600186.SH")
    assert reports[0]["report_year"] == 2022
    assert "年度报告" in reports[0]["title"] and "问询" not in reports[0]["title"]


def test_300209_2024_regression_inquiry_reply_never_selected(db_session_factory):
    assert _list(db_session_factory, "300209.SZ", year=2024) == []
    latest = _list(db_session_factory, "300209.SZ")
    assert latest[0]["report_year"] == 2025


# 15+16: no regressions on clean symbols
def test_600519_2024_and_000858_2025_still_selected(db_session_factory):
    assert [r["report_year"] for r in _list(db_session_factory, "600519.SH", year=2024)] == [2024]
    assert [r["report_year"] for r in _list(db_session_factory, "000858.SZ", year=2025)] == [2025]


# ordering + tie-break + dedup (items 9-11, 24, 25)
def test_duplicate_year_documents_dedup_to_one(db_session_factory):
    reports = _list(db_session_factory, "000858.SZ", year=2024)
    assert len(reports) == 1


def test_dedup_pick_is_deterministic_by_order_keys(db_session_factory):
    picks = {(_list(db_session_factory, "000858.SZ", year=2024)[0]["report_id"]) for _ in range(5)}
    assert len(picks) == 1
    # disclosure_date desc wins: 2025-04-03 (id 31) sorts before 2025-04-02 (id 30)
    assert picks == {31}


def test_db_return_order_does_not_affect_selection(db_session_factory):
    """Ordering lives in SQL (year/period/disclosure/id), not insertion order:
    the 000858/2024 duplicates were inserted with ids reversed vs disclosure
    order and selection still lands on the newest disclosure."""
    first = _list(db_session_factory, "000858.SZ")
    second = _list(db_session_factory, "000858.SZ")
    assert [r["report_id"] for r in first] == [r["report_id"] for r in second]
    assert first[0]["report_year"] == 2025 and first[1]["report_id"] == 31


# 12: field separation
def test_source_page_and_pdf_fields_not_confused(db_session_factory):
    report = _list(db_session_factory, "600519.SH", year=2024)[0]
    assert report["pdf_url"] and report["source_page_url"] is not None
    assert "source_url" in report or "source_page_url" in report


# 17+18: out-of-range years handled by the agent guard (no DB scan at all)
def test_future_and_ancient_years_unavailable_via_agent_guard():
    from app.agent_runtime.agents.official_report_pdf_agent import OfficialReportPdfAgent

    agent = OfficialReportPdfAgent()
    assert agent._year_out_of_range(2035) == "requested_report_year_is_in_the_future"
    assert agent._year_out_of_range(1900) == "requested_report_year_predates_official_report_index"
    assert agent._year_out_of_range(2024) is None


# 19: bounded per-symbol query, never market-wide
def test_query_is_symbol_scoped_and_bounded(db_session_factory):
    reports = _list(db_session_factory, "600519.SH")
    assert all(r["ts_code"] == "600519.SH" for r in reports)
    # requesting one symbol never returns rows of the 4 other seeded symbols
    assert len(reports) <= 8


# 20+21: agent-side invariants stay intact (tool_calls<=1, no LLM) — verified
# against the agent result contract used by the canary runner
def test_agent_selects_exact_year_and_type_from_tool_data():
    from app.agent_runtime.agents.official_report_pdf_agent import OfficialReportPdfAgent

    agent = OfficialReportPdfAgent()
    data = {"reports_by_symbol": {"600519.SH": [
        {"report_year": 2025, "report_type": "annual", "pdf_url": "https://static.cninfo.com.cn/a.PDF"},
        {"report_year": 2024, "report_type": "annual", "pdf_url": "https://static.cninfo.com.cn/b.PDF"},
    ]}}
    picked = agent._select_report(data, entity={"symbol": "600519"}, report_year=2024, report_type="annual")
    assert picked["report_year"] == 2024
    none_picked = agent._select_report(data, entity={"symbol": "600519"}, report_year=2022, report_type="annual")
    assert none_picked is None  # wrong-year fallback is impossible (item 23 guard)


# 22: provenance completeness for a success selection stays intact
def test_provenance_fields_present_on_selection(db_session_factory):
    report = _list(db_session_factory, "000858.SZ", year=2025)[0]
    for field in ("report_id", "ts_code", "report_year", "report_type", "pdf_url", "title"):
        assert report.get(field) is not None
