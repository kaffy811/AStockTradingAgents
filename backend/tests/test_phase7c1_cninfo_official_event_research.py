from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import uuid

import pytest

from app.agents import chat_orchestrator
from app.services.official_company_event_service import (
    OfficialCompanyEventService,
    classify_official_event,
)


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _Scalars(self._rows)


class _DB:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, _stmt):
        return _Result(self.rows)


def _entity():
    return SimpleNamespace(
        market="CN",
        symbol="600519",
        short_name="贵州茅台",
        full_name="贵州茅台酒股份有限公司",
    )


def _event(**overrides):
    value = {
        "title": "贵州茅台2025年年度报告",
        "published_at": "2026-03-31",
        "source": "CNINFO",
        "source_url": "https://static.cninfo.com.cn/finalpage/example.PDF",
        "event_type": "财报/业绩",
        "symbol": "600519",
        "company_name": "贵州茅台",
        "as_of": "2026-04-01T00:00:00+00:00",
        "coverage": "persisted_cninfo_report_metadata",
        "quality": "official_metadata",
    }
    value.update(overrides)
    return value


@pytest.mark.asyncio
async def test_official_company_event_answer_is_fulfilled_and_public(monkeypatch):
    async def resolve(*_args, **_kwargs):
        return {"entities": [_entity()], "ambiguity": False}

    async def list_events(*_args, **_kwargs):
        return {
            "fulfillment": "fulfilled",
            "reason_code": None,
            "events": [_event()],
            "coverage": "cninfo_persisted_metadata_only",
            "quality": "official_metadata",
            "as_of": "2026-04-01T00:00:00+00:00",
        }

    monkeypatch.setattr(chat_orchestrator.security_entity_resolver, "resolve", resolve)
    monkeypatch.setattr(chat_orchestrator.official_company_event_service, "list_persisted_events", list_events)

    result = await chat_orchestrator.process_message(
        "贵州茅台最近有什么官方公告？", _DB([]), uuid.uuid4()
    )

    assert result.metadata["route"] == "official_company_events"
    assert result.metadata["fulfillment"] == "fulfilled"
    assert result.metadata["events"][0]["source"] == "CNINFO"
    assert result.metadata["events"][0]["published_at"]
    assert result.metadata["events"][0]["as_of"]
    assert "公告标题" in result.answer
    assert "官方来源链接" in result.answer
    assert "report_documents" not in result.answer
    assert "report_id" not in result.answer


@pytest.mark.asyncio
async def test_explicit_report_disclosure_routes_to_official_report_analysis(monkeypatch):
    async def resolve(*_args, **_kwargs):
        return {"entities": [_entity()], "ambiguity": False}

    async def list_events(*_args, **_kwargs):
        return {
            "fulfillment": "partial",
            "reason_code": "INCOMPLETE_PERSISTED_CNINFO_COVERAGE",
            "events": [_event()],
            "coverage": "cninfo_persisted_metadata_only",
            "quality": "partial",
            "as_of": "2026-04-01T00:00:00+00:00",
        }

    monkeypatch.setattr(chat_orchestrator.security_entity_resolver, "resolve", resolve)
    monkeypatch.setattr(chat_orchestrator.official_company_event_service, "list_persisted_events", list_events)

    result = await chat_orchestrator.process_message(
        "贵州茅台最近一期财报披露了什么重点？", _DB([]), uuid.uuid4()
    )
    assert result.metadata["route"] == "official_report_analysis"
    assert result.metadata["fulfillment"] == "partial"
    assert result.metadata["reason_code"] == "REPORT_RAG_EVIDENCE_NOT_RENDERED"
    assert "Report RAG" in result.answer


@pytest.mark.asyncio
async def test_requested_event_types_do_not_fall_back_to_unrelated_reports(monkeypatch):
    async def resolve(*_args, **_kwargs):
        return {"entities": [_entity()], "ambiguity": False}

    async def list_events(*_args, **_kwargs):
        return {
            "fulfillment": "fulfilled",
            "reason_code": None,
            "events": [_event(event_type="财报/业绩")],
            "coverage": "cninfo_persisted_metadata_only",
            "quality": "official_metadata",
            "as_of": "2026-04-01T00:00:00+00:00",
        }

    monkeypatch.setattr(chat_orchestrator.security_entity_resolver, "resolve", resolve)
    monkeypatch.setattr(chat_orchestrator.official_company_event_service, "list_persisted_events", list_events)

    result = await chat_orchestrator.process_message(
        "贵州茅台近期是否有分红、回购、股东变动或风险公告？", _DB([]), uuid.uuid4()
    )
    assert result.metadata["fulfillment"] == "unavailable"
    assert result.metadata["reason_code"] == "NO_MATCHING_PERSISTED_CNINFO_EVENTS"
    assert "未使用其它公告或新闻替代" in result.answer


@pytest.mark.asyncio
async def test_no_persisted_event_returns_unavailable_without_fabrication(monkeypatch):
    async def resolve(*_args, **_kwargs):
        return {"entities": [_entity()], "ambiguity": False}

    async def list_events(*_args, **_kwargs):
        return {
            "fulfillment": "unavailable",
            "reason_code": "NO_PERSISTED_CNINFO_EVENTS",
            "events": [],
            "coverage": "cninfo_persisted_metadata_only",
            "quality": "unavailable",
            "as_of": None,
        }

    monkeypatch.setattr(chat_orchestrator.security_entity_resolver, "resolve", resolve)
    monkeypatch.setattr(chat_orchestrator.official_company_event_service, "list_persisted_events", list_events)

    result = await chat_orchestrator.process_message(
        "贵州茅台近期是否有分红公告？", _DB([]), uuid.uuid4()
    )
    assert result.metadata["fulfillment"] == "unavailable"
    assert result.metadata["reason_code"] == "NO_PERSISTED_CNINFO_EVENTS"
    assert "未补充或编造事件" in result.answer


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "新能源汽车行业最近有什么重要新闻？",
        "AI 热潮带动了哪些半导体设备公司？",
        "最近市场热点新闻是什么？",
    ],
)
async def test_unapproved_news_scopes_fail_closed_before_any_tool(monkeypatch, query):
    async def forbidden(*_args, **_kwargs):
        raise AssertionError("entity/provider path must not run")

    monkeypatch.setattr(chat_orchestrator.security_entity_resolver, "resolve", forbidden)
    monkeypatch.setattr(chat_orchestrator.official_company_event_service, "list_persisted_events", forbidden)

    result = await chat_orchestrator.process_message(query, _DB([]), uuid.uuid4())
    assert result.metadata["fulfillment"] == "unavailable"
    assert result.metadata["reason_code"] == "NO_APPROVED_INDUSTRY_NEWS_SOURCE"
    assert not result.tool_events
    assert "提供股票代码" not in result.answer


@pytest.mark.asyncio
async def test_persisted_projection_filters_incomplete_rows_and_hides_database_id():
    rows = [
        SimpleNamespace(
            id=987654,
            ts_code="600519.SH",
            title="贵州茅台关于回购股份的公告",
            disclosure_date="2026-08-20",
            source_url="https://www.cninfo.com.cn/new/disclosure/detail?announcementId=public",
            pdf_url=None,
            created_at=datetime(2026, 8, 21, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            id=123456,
            ts_code="600519.SH",
            title="缺少官方链接的公告",
            disclosure_date="2026-08-19",
            source_url="",
            pdf_url="",
            created_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
        ),
    ]
    result = await OfficialCompanyEventService().list_persisted_events(
        _DB(rows), market="CN", symbol="600519", company_name="贵州茅台"
    )
    assert result["fulfillment"] == "partial"
    assert result["events"][0]["event_type"] == "回购"
    assert "id" not in result["events"][0]
    assert result["events"][0]["source"] == "CNINFO"
    assert result["events"][0]["as_of"]


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("2025年年度报告", "财报/业绩"),
        ("关于利润分配方案的公告", "分红"),
        ("关于回购股份的公告", "回购"),
        ("股东减持股份计划公告", "股东增减持"),
        ("重大资产重组公告", "并购重组"),
        ("董事辞职公告", "治理与管理层"),
        ("重大合同进展公告", "业务进展"),
        ("重大诉讼风险提示公告", "监管/诉讼/风险"),
        ("其它事项公告", "其它官方披露"),
    ],
)
def test_event_classification(title, expected):
    assert classify_official_event(title) == expected
